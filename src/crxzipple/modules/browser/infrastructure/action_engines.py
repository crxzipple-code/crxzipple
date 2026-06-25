from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from dataclasses import replace
from typing import Any

from crxzipple.modules.browser.domain import (
    BrowserActionFamily,
    BrowserActionResult,
    BrowserExecutionPlan,
    BrowserPageActionCommand,
    BrowserProfileRuntimeState,
    BrowserTab,
    BrowserValidationError,
)
from crxzipple.modules.browser.application.network_capture import (
    BrowserNetworkCaptureService,
)
from crxzipple.modules.daemon import DaemonApplicationService

from ..application.ports import BrowserActionEngine, BrowserRefStore
from .action_engine_payloads import (
    _ACTION_EFFECT_KINDS,
    _action_result_envelope,
    _action_result_message,
    _capture_action_effect_page_state,
    _click_coordinates,
    _drag_source_ref,
    _drag_source_selector,
    _drag_target_ref,
    _drag_target_selector,
    _LOCATOR_ACTION_KINDS,
    _payload_int_any,
    _payload_number_any,
    _payload_text,
    _payload_value_any,
    _RETRYABLE_TRANSIENT_ACTION_KINDS,
    _serialize_frame_path,
    _serialize_tab,
    _SUPPORTED_KINDS,
    _timeout_kwargs,
    _timeout_ms,
)
from .action_engine_batch import execute_browser_batch
from .action_engine_refs import BrowserRefOverlayMixin
from .action_engine_interactions import BrowserInteractionPrimitivesMixin
from .action_engine_wait import BrowserWaitActionMixin
from .action_engine_cdp import execute_cdp_raw
from .action_engine_trace_runner import BrowserActionTraceRunnerMixin
from .action_engine_snapshot_runner import BrowserSnapshotActionMixin
from .action_engine_snapshots import (
    _is_transient_page_context_error,
    _normalize_form_fields,
    _normalize_text_payload,
)
from .cdp_urls import browser_ref_to_cdp_http_base
from .daemon_leases import host_daemon_lease
from .action_trace import BrowserActionTraceService
from .devtools import BrowserDevToolsAdapter
from .diagnostics import BrowserDiagnosticsService
from .dom_inspection import BrowserDomInspectionService, DOM_INSPECTION_KINDS
from .environment_control import BrowserEnvironmentControlService
from .network_capture import InMemoryBrowserNetworkCaptureStore
from .network_actions import BrowserNetworkActionService
from .network_cdp_capture import CdpNetworkCaptureController
from .network_insight import BrowserNetworkInsightService
from .network_page_fetch import BrowserPageNetworkFetchService
from .peripheral_actions import BrowserPeripheralActionService
from .playwright import PlaywrightCdpSessionPool
from .cdp_sessions import BrowserCdpSessionBroker
from .script_insight import BrowserScriptInsightService, SCRIPT_INSIGHT_KINDS
from .storage_inspection import BrowserStorageInspectionService

_DEEP_STORAGE_KINDS = frozenset(
    {
        "storage-indexeddb-list",
        "storage-indexeddb-get",
        "storage-indexeddb-query",
        "storage-cache-list",
        "storage-cache-get",
        "service-worker-list",
        "service-worker-inspect",
    }
)
_ENVIRONMENT_CONTROL_KINDS = frozenset(
    {
        "emulation-set",
        "emulation-reset",
        "permissions-grant",
        "permissions-clear",
        "geolocation-set",
        "network-conditions-set",
    }
)
_DIAGNOSTIC_KINDS = frozenset(
    {
        "diagnostics-collect",
        "performance-metrics",
        "trace-start",
        "trace-stop",
        "trace-export",
        "page-lifecycle",
        "page-errors",
    }
)
_NETWORK_CAPTURE_KINDS = frozenset(
    {
        "network-start-capture",
        "network-stop-capture",
        "network-list-requests",
        "network-get-request",
        "network-get-response-body",
        "network-get-request-body",
        "network-fetch-as-page",
        "network-replay-request",
        "network-clear-capture",
    }
)
def _host_lease_user_data_dir(
    *,
    plan: BrowserExecutionPlan,
    runtime_state: BrowserProfileRuntimeState,
) -> str | None:
    runtime_user_data_dir = runtime_state.metadata.get("user_data_dir")
    if isinstance(runtime_user_data_dir, str) and runtime_user_data_dir.strip():
        return runtime_user_data_dir.strip()
    return plan.profile.user_data_dir




@dataclass(slots=True)
class CdpBackedPlaywrightActionEngine(
    BrowserSnapshotActionMixin,
    BrowserRefOverlayMixin,
    BrowserInteractionPrimitivesMixin,
    BrowserWaitActionMixin,
    BrowserActionTraceRunnerMixin,
    BrowserActionEngine,
):
    session_pool: PlaywrightCdpSessionPool
    ref_store: BrowserRefStore
    daemon_service: DaemonApplicationService = field(repr=False)
    cdp_session_broker: BrowserCdpSessionBroker = field(
        default_factory=BrowserCdpSessionBroker,
        repr=False,
    )
    devtools_adapter: BrowserDevToolsAdapter | None = field(default=None, repr=False)
    action_trace_service: BrowserActionTraceService = field(
        default_factory=BrowserActionTraceService,
        repr=False,
    )
    script_insight_service: BrowserScriptInsightService | None = field(
        default=None,
        repr=False,
    )
    network_capture_service: BrowserNetworkCaptureService = field(
        default_factory=lambda: BrowserNetworkCaptureService(
            capture_store=InMemoryBrowserNetworkCaptureStore(),
        ),
        repr=False,
    )
    network_capture_controller: CdpNetworkCaptureController | None = field(
        default=None,
        repr=False,
    )
    network_page_fetch_service: BrowserPageNetworkFetchService = field(
        default_factory=BrowserPageNetworkFetchService,
        repr=False,
    )
    network_action_service: BrowserNetworkActionService | None = field(
        default=None,
        repr=False,
    )
    network_insight_service: BrowserNetworkInsightService = field(
        default_factory=BrowserNetworkInsightService,
        repr=False,
    )
    storage_inspection_service: BrowserStorageInspectionService = field(
        default_factory=BrowserStorageInspectionService,
        repr=False,
    )
    dom_inspection_service: BrowserDomInspectionService = field(
        default_factory=BrowserDomInspectionService,
        repr=False,
    )
    peripheral_action_service: BrowserPeripheralActionService = field(
        default_factory=BrowserPeripheralActionService,
        repr=False,
    )
    environment_control_service: BrowserEnvironmentControlService = field(
        default_factory=BrowserEnvironmentControlService,
        repr=False,
    )
    diagnostics_service: BrowserDiagnosticsService = field(
        default_factory=BrowserDiagnosticsService,
        repr=False,
    )
    family: BrowserActionFamily = "cdp-backed-playwright"

    def __post_init__(self) -> None:
        if self.devtools_adapter is None:
            self.devtools_adapter = BrowserDevToolsAdapter(
                cdp_session_broker=self.cdp_session_broker,
            )
        if self.script_insight_service is None:
            self.script_insight_service = BrowserScriptInsightService(
                devtools_adapter=self.devtools_adapter,
            )
        if self.network_capture_controller is None:
            self.network_capture_controller = CdpNetworkCaptureController(
                capture_service=self.network_capture_service,
                cdp_session_broker=self.cdp_session_broker,
            )
        if self.network_action_service is None:
            self.network_action_service = BrowserNetworkActionService(
                network_capture_service=self.network_capture_service,
                network_capture_controller=self.network_capture_controller,
                network_page_fetch_service=self.network_page_fetch_service,
            )

    def supports(
        self,
        *,
        command: BrowserPageActionCommand,
    ) -> bool:
        return command.kind in _SUPPORTED_KINDS

    def execute(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
        tab: BrowserTab | None,
        command: BrowserPageActionCommand,
    ) -> BrowserActionResult:
        if tab is None:
            raise BrowserValidationError("cdp-backed-playwright actions require a tab.")
        with host_daemon_lease(
            daemon_service=self.daemon_service,
            plan=plan,
            user_data_dir=_host_lease_user_data_dir(
                plan=plan,
                runtime_state=runtime_state,
            ),
        ):
            cdp_url = self._runtime_cdp_url(plan=plan, runtime_state=runtime_state)
            max_attempts = (
                2
                if command.kind in _RETRYABLE_TRANSIENT_ACTION_KINDS
                else 1
            )
            last_error: Exception | None = None
            effect_before: dict[str, Any] | None = None
            for attempt in range(max_attempts):
                page = self.session_pool.resolve_page(
                    profile=plan.profile,
                    target_id=tab.target_id,
                    timeout_ms=command.timeout_ms,
                    cdp_url=cdp_url,
                )
                try:
                    effect_before = (
                        _capture_action_effect_page_state(page)
                        if command.kind in _ACTION_EFFECT_KINDS
                        else None
                    )
                    result_value, resolved_selector, resolved_frame_path = self._execute_on_page(
                        plan=plan,
                        tab=tab,
                        page=page,
                        runtime_state=runtime_state,
                        command=command,
                    )
                    break
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    if attempt + 1 < max_attempts and _is_transient_page_context_error(exc):
                        continue
                    raise
            else:
                assert last_error is not None
                raise last_error
        effect_after = (
            _capture_action_effect_page_state(page)
            if command.kind in _ACTION_EFFECT_KINDS
            else None
        )
        if command.kind == "snapshot" and isinstance(result_value, dict):
            runtime_state.remember_page_snapshot(
                target_id=tab.target_id,
                generation=int(result_value.get("generation") or 1),
                snapshot_format=str(result_value.get("format") or "snapshot"),
                ref_count=int(result_value.get("ref_count") or 0),
                frame_count=int(result_value.get("frame_count") or 0),
            )
        else:
            runtime_state.remember_page_action(
                target_id=tab.target_id,
                action_kind=command.kind,
            )
        value = {
            "engine": self.family,
            "control_family": plan.control_family,
            "profile": plan.profile.name,
            "tab": _serialize_tab(tab),
            "ref": command.target.ref,
            "selector": resolved_selector,
            "frame_path": _serialize_frame_path(resolved_frame_path),
            "payload": dict(command.payload),
            "result": result_value,
        }
        envelope = _action_result_envelope(
            kind=command.kind,
            tool_ok=True,
            before=effect_before if command.kind in _ACTION_EFFECT_KINDS else None,
            after=effect_after,
            result=result_value,
        )
        if envelope is not None:
            value["action_envelope"] = envelope
        return BrowserActionResult(
            command=command,
            ok=True,
            target_id=tab.target_id,
            value=value,
            message=_action_result_message(command.kind, envelope=envelope),
        )

    def clear_profile(
        self,
        *,
        profile_name: str,
    ) -> None:
        if self.network_capture_controller is not None:
            self.network_capture_controller.clear_profile(profile_name=profile_name)
        self.session_pool.clear_profile(profile_name=profile_name)

    def _execute_on_page(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        command: BrowserPageActionCommand,
        batch_depth: int = 0,
    ) -> tuple[Any, str | None, tuple[int, ...] | None]:
        timeout = _timeout_ms(command)
        fill_fields = _normalize_form_fields(command.payload.get("fields")) if command.kind == "fill" else ()
        effective_command = command
        if command.kind == "drag" and command.target.ref is None and command.target.selector is None:
            source_ref = _drag_source_ref(command)
            source_selector = _drag_source_selector(command)
            if source_ref is not None or source_selector is not None:
                effective_command = replace(
                    command,
                    target=replace(
                        command.target,
                        ref=source_ref,
                        selector=source_selector,
                    ),
                )
        coordinate_target = (
            _click_coordinates(command.payload)
            if command.kind == "click"
            else None
        )
        context, locator, resolved_selector, resolved_frame_path = self._locator(
            plan=plan,
            tab=tab,
            page=page,
            runtime_state=runtime_state,
            command=effective_command,
            required=(
                (command.kind in _LOCATOR_ACTION_KINDS or command.kind in DOM_INSPECTION_KINDS)
                and not bool(fill_fields)
                and coordinate_target is None
            ),
        )

        if command.kind == "batch":
            return (
                execute_browser_batch(
                    plan=plan,
                    tab=tab,
                    runtime_state=runtime_state,
                    command=command,
                    batch_depth=batch_depth,
                    execute_inner=lambda action, next_batch_depth: self._execute_on_page(
                        plan=plan,
                        tab=tab,
                        page=page,
                        runtime_state=runtime_state,
                        command=action,
                        batch_depth=next_batch_depth,
                    ),
                ),
                resolved_selector,
                resolved_frame_path,
            )

        if command.kind == "action-trace":
            return (
                self._execute_action_trace(
                    plan=plan,
                    tab=tab,
                    page=page,
                    runtime_state=runtime_state,
                    command=command,
                    batch_depth=batch_depth,
                ),
                resolved_selector,
                resolved_frame_path,
            )

        if command.kind in _NETWORK_CAPTURE_KINDS:
            if self.network_action_service is None:
                raise BrowserValidationError("Browser network action service is not configured.")
            return (
                self.network_action_service.execute(
                    plan=plan,
                    tab=tab,
                    page=page,
                    command=command,
                ),
                resolved_selector,
                resolved_frame_path,
            )

        if command.kind in DOM_INSPECTION_KINDS:
            if locator is None:
                raise BrowserValidationError(
                    f"Browser action '{command.kind}' requires ref or selector targeting.",
                )
            devtools_event_listeners = self._devtools_event_listeners_for_command(
                plan=plan,
                tab=tab,
                page=page,
                command=effective_command,
            )
            return (
                self.dom_inspection_service.execute(
                    kind=command.kind,
                    locator=locator,
                    selector=resolved_selector,
                    payload=command.payload,
                    command_timeout_ms=timeout,
                    devtools_event_listeners=devtools_event_listeners,
                ),
                resolved_selector,
                resolved_frame_path,
            )

        if command.kind in _DEEP_STORAGE_KINDS:
            return (
                self.storage_inspection_service.execute(
                    page=page,
                    kind=command.kind,
                    payload=command.payload,
                ),
                resolved_selector,
                resolved_frame_path,
            )

        if command.kind in _ENVIRONMENT_CONTROL_KINDS:
            return (
                self.environment_control_service.execute(
                    page=page,
                    kind=command.kind,
                    payload=command.payload,
                    profile_name=plan.profile.name,
                    target_id=tab.target_id,
                    page_url=tab.url,
                ),
                resolved_selector,
                resolved_frame_path,
            )

        if command.kind in _DIAGNOSTIC_KINDS:
            console_messages = self.session_pool.get_console_messages(
                page=page,
                level=None,
                limit=_payload_int_any(command.payload, "console_limit", minimum=1) or 100,
                clear=False,
            )
            page_errors: list[dict[str, Any]] = []
            get_page_errors = getattr(self.session_pool, "get_page_errors", None)
            if callable(get_page_errors):
                page_errors = get_page_errors(
                    page=page,
                    limit=_payload_int_any(
                        command.payload,
                        "error_limit",
                        "page_error_limit",
                        minimum=1,
                    ) or 100,
                    clear=False,
                )
            return (
                self.diagnostics_service.execute(
                    page=page,
                    kind=command.kind,
                    payload=command.payload,
                    console_messages=console_messages,
                    page_errors=page_errors,
                    profile_name=plan.profile.name,
                    target_id=tab.target_id,
                    page_url=tab.url,
                ),
                resolved_selector,
                resolved_frame_path,
            )

        if command.kind == "console":
            return (
                self.peripheral_action_service.execute_console(
                    session_pool=self.session_pool,
                    page=page,
                    payload=command.payload,
                ),
                resolved_selector,
                resolved_frame_path,
            )

        if command.kind == "cookies":
            return (
                self.storage_inspection_service.execute_cookies(
                    page=page,
                    payload=command.payload,
                ),
                resolved_selector,
                resolved_frame_path,
            )

        if command.kind == "storage":
            return (
                self.storage_inspection_service.execute_browser_storage(
                    page=page,
                    payload=command.payload,
                ),
                resolved_selector,
                resolved_frame_path,
            )

        if command.kind == "network-inspect":
            return (
                self.network_insight_service.execute(
                    page=page,
                    payload=command.payload,
                ),
                resolved_selector,
                resolved_frame_path,
            )

        if command.kind in SCRIPT_INSIGHT_KINDS:
            if self.script_insight_service is None:
                raise BrowserValidationError("Browser script insight service is not configured.")
            return (
                self.script_insight_service.execute(
                    page=page,
                    kind=command.kind,
                    payload=command.payload,
                ),
                resolved_selector,
                resolved_frame_path,
            )

        if command.kind == "cdp-raw":
            return (
                execute_cdp_raw(page=page, payload=command.payload),
                resolved_selector,
                resolved_frame_path,
            )

        if command.kind == "dialog":
            return (
                self.peripheral_action_service.execute_dialog(
                    page=page,
                    payload=command.payload,
                    timeout_ms=timeout,
                ),
                resolved_selector,
                resolved_frame_path,
            )

        if command.kind == "click":
            button = command.payload.get("button")
            if locator is None and coordinate_target is not None:
                click_result = self._coordinate_click(
                    page=page,
                    x=coordinate_target[0],
                    y=coordinate_target[1],
                    button=button,
                    double_click=bool(command.payload.get("double_click", False)),
                )
                return click_result, resolved_selector, resolved_frame_path
            click_mode = self._click(
                locator=locator,
                timeout=timeout,
                button=button,
                force=bool(command.payload.get("force", False)),
                double_click=bool(command.payload.get("double_click", False)),
            )
            return {"kind": "click", "mode": click_mode}, resolved_selector, resolved_frame_path

        if command.kind == "type":
            text = _payload_text(command.payload, key="text")
            input_mode = self._input_text(
                locator=locator,
                text=text,
                payload={**dict(command.payload), "input_mode": "type"},
                timeout=timeout,
                action_kind="type",
                default_mode="type",
            )
            return {"kind": "type", "text": text, "input_mode": input_mode}, resolved_selector, resolved_frame_path

        if command.kind == "press":
            key = _payload_text(command.payload, key="key")
            if locator is None:
                page.keyboard.press(key, **_timeout_kwargs(timeout))
            else:
                locator.press(key, **_timeout_kwargs(timeout))
            return {"kind": "press", "key": key}, resolved_selector, resolved_frame_path

        if command.kind == "hover":
            locator.hover(**_timeout_kwargs(timeout))
            return {"kind": "hover"}, resolved_selector, resolved_frame_path

        if command.kind == "drag":
            target_ref = _drag_target_ref(command.payload)
            target_selector = _drag_target_selector(command.payload)
            if target_ref is not None:
                (
                    _target_context,
                    target_locator,
                    _resolved_target_selector,
                    _resolved_target_frame_path,
                ) = self._locator_from_ref(
                    plan=plan,
                    tab=tab,
                    page=page,
                    runtime_state=runtime_state,
                    ref_id=target_ref,
                )
            else:
                if target_selector is None:
                    raise BrowserValidationError(
                        "drag requires end_ref/end_selector or target_ref/target_selector.",
                    )
                target_locator = context.locator(target_selector)
            locator.drag_to(target_locator, **_timeout_kwargs(timeout))
            return (
                {
                    "kind": "drag",
                    "start_ref": effective_command.target.ref,
                    "start_selector": effective_command.target.selector,
                    "end_ref": target_ref,
                    "end_selector": target_selector,
                },
                resolved_selector,
                resolved_frame_path,
            )

        if command.kind == "resize":
            width = int(_payload_number_any(command.payload, "width") or 0)
            height = int(_payload_number_any(command.payload, "height") or 0)
            if width < 1 or height < 1:
                raise BrowserValidationError("payload.width and payload.height are required.")
            set_viewport_size = getattr(page, "set_viewport_size", None)
            if not callable(set_viewport_size):
                raise BrowserValidationError(
                    "Playwright page does not support set_viewport_size().",
                )
            set_viewport_size({"width": width, "height": height})
            return (
                {
                    "kind": "resize",
                    "width": width,
                    "height": height,
                },
                resolved_selector,
                resolved_frame_path,
            )

        if command.kind == "scroll-into-view":
            locator.scroll_into_view_if_needed(**_timeout_kwargs(timeout))
            return {"kind": "scroll-into-view"}, resolved_selector, resolved_frame_path

        if command.kind == "select":
            values = command.payload.get("values")
            if values is None:
                value = _payload_text(command.payload, key="value")
                selection: Any = value
            elif isinstance(values, (list, tuple)):
                selection = list(values)
            else:
                selection = values
            selected = locator.select_option(selection, **_timeout_kwargs(timeout))
            return (
                {"kind": "select", "selected": selected},
                resolved_selector,
                resolved_frame_path,
            )

        if command.kind == "fill":
            if fill_fields:
                filled: list[dict[str, Any]] = []
                for field in fill_fields:
                    (
                        _field_context,
                        field_locator,
                        field_selector,
                        field_frame_path,
                    ) = self._locator_from_ref(
                        plan=plan,
                        tab=tab,
                        page=page,
                        runtime_state=runtime_state,
                        ref_id=str(field["ref"]),
                    )
                    field_type = str(field["type"])
                    raw_value = field["value"]
                    if field_type in {"checkbox", "radio"}:
                        checked = bool(raw_value)
                        set_checked = getattr(field_locator, "set_checked", None)
                        if not callable(set_checked):
                            raise BrowserValidationError(
                                f"Playwright locator for ref '{field['ref']}' does not support set_checked().",
                            )
                        set_checked(checked, **_timeout_kwargs(timeout))
                        value_repr: Any = checked
                    else:
                        value_repr = (
                            raw_value
                            if isinstance(raw_value, str)
                            else str(raw_value)
                        )
                        self._ensure_editable_text_target(locator=field_locator, action_kind="fill")
                        field_locator.fill(str(value_repr), **_timeout_kwargs(timeout))
                    filled.append(
                        {
                            "ref": field["ref"],
                            "type": field_type,
                            "value": value_repr,
                            "selector": field_selector,
                            "frame_path": _serialize_frame_path(field_frame_path),
                        }
                    )
                return {"kind": "fill", "fields": filled}, resolved_selector, resolved_frame_path

            text = _payload_text(command.payload, key="text")
            try:
                self._ensure_editable_text_target(locator=locator, action_kind="fill")
            except BrowserValidationError as exc:
                return (
                    self._fill_via_custom_overlay(
                        plan=plan,
                        tab=tab,
                        page=page,
                        runtime_state=runtime_state,
                        command=command,
                        locator=locator,
                        resolved_selector=resolved_selector,
                        text=text,
                        timeout=timeout,
                        original_error=exc,
                    ),
                    resolved_selector,
                    resolved_frame_path,
                )
            locator.fill(text, **_timeout_kwargs(timeout))
            return {"kind": "fill", "text": text}, resolved_selector, resolved_frame_path

        if command.kind == "upload":
            upload_paths = _normalize_text_payload(
                _payload_value_any(command.payload, "paths", "path"),
            )
            if not upload_paths:
                raise BrowserValidationError("payload.paths is required.")
            set_input_files = getattr(locator, "set_input_files", None)
            if not callable(set_input_files):
                raise BrowserValidationError(
                    "Playwright locator does not support set_input_files().",
                )
            set_input_files(upload_paths, **_timeout_kwargs(timeout))
            return {"kind": "upload", "paths": upload_paths}, resolved_selector, resolved_frame_path

        if command.kind == "download":
            button = command.payload.get("button")
            return (
                self.peripheral_action_service.execute_download(
                    page=page,
                    timeout_ms=timeout,
                    trigger=lambda: self._click(
                        locator=locator,
                        timeout=timeout,
                        button=button,
                        force=bool(command.payload.get("force", False)),
                        double_click=bool(command.payload.get("double_click", False)),
                    ),
                ),
                resolved_selector,
                resolved_frame_path,
            )

        if command.kind == "wait-download":
            return (
                self.peripheral_action_service.execute_wait_download(
                    page=page,
                    timeout_ms=timeout,
                ),
                resolved_selector,
                resolved_frame_path,
            )

        if command.kind == "wait":
            return (
                self._wait(
                    plan=plan,
                    tab=tab,
                    page=page,
                    runtime_state=runtime_state,
                    locator=locator,
                    command=command,
                    timeout=timeout,
                ),
                resolved_selector,
                resolved_frame_path,
            )

        if command.kind == "snapshot":
            return (
                self._snapshot(
                    plan=plan,
                    tab=tab,
                    page=page,
                    runtime_state=runtime_state,
                    command=command,
                ),
                resolved_selector,
                resolved_frame_path,
            )

        if command.kind == "screenshot":
            return (
                self.peripheral_action_service.execute_screenshot(
                    page=page,
                    payload=command.payload,
                    timeout_ms=timeout,
                ),
                resolved_selector,
                resolved_frame_path,
            )

        if command.kind == "pdf":
            return (
                self.peripheral_action_service.execute_pdf(
                    page=page,
                    payload=command.payload,
                ),
                resolved_selector,
                resolved_frame_path,
            )

        if command.kind == "evaluate":
            return (
                self.peripheral_action_service.execute_evaluate(
                    page=page,
                    locator=locator,
                    payload=command.payload,
                ),
                resolved_selector,
                resolved_frame_path,
            )

        raise BrowserValidationError(
            f"Action engine '{self.family}' does not support '{command.kind}'.",
        )











    def _runtime_cdp_url(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
    ) -> str | None:
        cached = runtime_state.metadata.get("cdp_base_url")
        if isinstance(cached, str) and cached.strip():
            return cached.strip()
        derived = browser_ref_to_cdp_http_base(runtime_state.browser_ref)
        if derived is not None:
            return derived
        return plan.profile.cdp_url
