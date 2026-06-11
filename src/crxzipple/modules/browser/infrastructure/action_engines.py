from __future__ import annotations

import calendar
from dataclasses import replace
from dataclasses import dataclass
from dataclasses import field
import re
from typing import Any, Mapping

from crxzipple.modules.browser.domain import (
    BrowserActionFamily,
    BrowserActionResult,
    BrowserActionTarget,
    BrowserExecutionPlan,
    BrowserPageActionCommand,
    BrowserProfileRuntimeState,
    BrowserStoredRef,
    BrowserTab,
    BrowserValidationError,
)
from crxzipple.modules.browser.application.network_capture import (
    BrowserNetworkCaptureService,
)
from crxzipple.modules.browser.domain.value_objects import _normalize_optional_text
from crxzipple.modules.daemon import DaemonApplicationService

from ..application.ports import BrowserActionEngine, BrowserRefStore
from .action_engine_locators import (
    _active_overlay,
    _allows_implicit_selector_ordinal,
    _command_overlay_source_refs,
    _command_overlay_source_scope_selectors,
    _command_overlay_source_selectors,
    _devtools_ref_marker_value,
    _explicit_overlay_kind,
    _locator_exact,
    _locator_ordinal,
    _scope_ref_id,
    _scope_selector,
    _stored_ref_name,
    _wait_prefers_active_overlay,
)
from .action_engine_payloads import (
    _ACTION_EFFECT_KINDS,
    _action_result_envelope,
    _action_result_message,
    _capture_action_effect_page_state,
    _click_coordinates,
    _count_batch_actions,
    _detach_cdp_session,
    _drag_source_ref,
    _drag_source_selector,
    _drag_target_ref,
    _drag_target_selector,
    _is_pointer_interception_error,
    _json_safe_payload,
    _LOCATOR_ACTION_KINDS,
    _MAX_BATCH_ACTIONS,
    _MAX_BATCH_DEPTH,
    _normalize_batch_action,
    _payload_bool_any,
    _payload_int_any,
    _payload_number_any,
    _payload_text,
    _payload_text_any,
    _payload_value_any,
    _probe_timeout,
    _RETRYABLE_TRANSIENT_ACTION_KINDS,
    _new_page_cdp_session,
    _send_cdp_session_command,
    _serialize_frame_path,
    _serialize_tab,
    _SUPPORTED_KINDS,
    _timeout_kwargs,
    _timeout_ms,
)
from .action_engine_snapshot_runner import BrowserSnapshotActionMixin
from .action_engine_snapshots import (
    _active_overlay_selector,
    _associated_overlay_selector,
    _is_transient_page_context_error,
    _main_frame,
    _normalize_form_fields,
    _normalize_text_payload,
    _resolve_frame_context,
)
from .action_engine_scripts import (
    _ACTIVE_OVERLAY_SELECTOR_EXPRESSION,
    _ASSOCIATED_OVERLAY_SELECTOR_EXPRESSION,
    _TARGET_INFO_EXPRESSION,
    _TEXT_MATCH_ORDINAL_EXPRESSION,
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
from .role_snapshot import (
    describe_role_locator,
)
from .script_insight import BrowserScriptInsightService, SCRIPT_INSIGHT_KINDS
from .storage_inspection import BrowserStorageInspectionService

_DEVTOOLS_REF_ATTRIBUTE = "data-crxzipple-backend-ref"
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


def _stored_ref_has_precise_locator(item: BrowserStoredRef) -> bool:
    return item.selector is not None or item.backend_node_id is not None or item.uid is not None


def _stored_refs_look_compatible(
    protected: BrowserStoredRef,
    current: BrowserStoredRef,
) -> bool:
    if protected.frame_path != current.frame_path:
        return False
    protected_role = _normalize_optional_text(protected.role)
    current_role = _normalize_optional_text(current.role)
    if protected_role is not None and current_role is not None and protected_role != current_role:
        return False
    protected_name = _stored_ref_name(protected)
    current_name = _stored_ref_name(current)
    if protected_name is not None and current_name is not None and protected_name != current_name:
        return False
    return True


def _merge_protected_ref_locator(
    *,
    current: BrowserStoredRef,
    protected: BrowserStoredRef,
) -> BrowserStoredRef:
    return replace(
        current,
        selector=protected.selector or current.selector,
        scope_selector=protected.scope_selector or current.scope_selector,
        uid=protected.uid or current.uid,
        backend_node_id=protected.backend_node_id or current.backend_node_id,
        bbox=current.bbox or protected.bbox,
        evidence=current.evidence or protected.evidence,
        confidence=(
            current.confidence
            if current.confidence is not None
            else protected.confidence
        ),
    )


@dataclass(slots=True)
class CdpBackedPlaywrightActionEngine(BrowserSnapshotActionMixin, BrowserActionEngine):
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
                self._batch(
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

        if command.kind == "action-trace":
            protected_ref = self._action_trace_protected_ref(
                plan=plan,
                tab=tab,
                command=command,
            )
            snapshot_calls = 0

            def snapshot_action(
                snapshot_command: BrowserPageActionCommand,
            ) -> Mapping[str, Any]:
                nonlocal snapshot_calls
                snapshot_calls += 1
                result = self._snapshot(
                    plan=plan,
                    tab=tab,
                    page=page,
                    runtime_state=runtime_state,
                    command=snapshot_command,
                )
                runtime_state.remember_page_snapshot(
                    target_id=tab.target_id,
                    generation=int(result.get("generation") or 1),
                    snapshot_format=str(result.get("format") or "snapshot"),
                    ref_count=int(result.get("ref_count") or 0),
                    frame_count=int(result.get("frame_count") or 0),
                )
                if snapshot_calls == 1 and protected_ref is not None:
                    self._restore_action_trace_protected_ref(
                        plan=plan,
                        tab=tab,
                        protected_ref=protected_ref,
                    )
                return result

            def network_action(
                network_command: BrowserPageActionCommand,
            ) -> Mapping[str, Any]:
                if self.network_action_service is None:
                    raise BrowserValidationError("Browser network action service is not configured.")
                return self.network_action_service.execute(
                    plan=plan,
                    tab=tab,
                    page=page,
                    command=network_command,
                )

            def execute_inner(
                inner_command: BrowserPageActionCommand,
                next_batch_depth: int,
            ) -> tuple[Any, str | None, tuple[int, ...] | None]:
                return self._execute_on_page(
                    plan=plan,
                    tab=tab,
                    page=page,
                    runtime_state=runtime_state,
                    command=inner_command,
                    batch_depth=next_batch_depth,
                )

            def console_messages(limit: int) -> list[dict[str, Any]]:
                return [
                    dict(item)
                    for item in self.session_pool.get_console_messages(
                        page=page,
                        level=None,
                        limit=limit,
                        clear=False,
                    )
                    if isinstance(item, dict)
                ]

            def page_errors(limit: int) -> list[dict[str, Any]]:
                get_page_errors = getattr(self.session_pool, "get_page_errors", None)
                if not callable(get_page_errors):
                    return []
                return [
                    dict(item)
                    for item in get_page_errors(
                        page=page,
                        limit=limit,
                        clear=False,
                    )
                    if isinstance(item, dict)
                ]

            return (
                self.action_trace_service.execute(
                    plan=plan,
                    tab=tab,
                    page=page,
                    runtime_state=runtime_state,
                    command=command,
                    batch_depth=batch_depth,
                    snapshot=snapshot_action,
                    network_action=network_action,
                    execute_inner=execute_inner,
                    console_messages=console_messages,
                    page_errors=page_errors,
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
            method = _payload_text_any(command.payload, "method")
            if method is None:
                raise BrowserValidationError("payload.method is required for cdp-raw.")
            params = command.payload.get("params")
            if params is None:
                params = {}
            if not isinstance(params, Mapping):
                raise BrowserValidationError("payload.params must be an object.")
            session = _new_page_cdp_session(page)
            try:
                raw_result = _send_cdp_session_command(session, method, params)
            finally:
                _detach_cdp_session(session)
            return (
                {
                    "kind": "cdp-raw",
                    "method": method,
                    "result": _json_safe_payload(raw_result),
                },
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











    def _batch(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        command: BrowserPageActionCommand,
        batch_depth: int,
    ) -> dict[str, Any]:
        if batch_depth > _MAX_BATCH_DEPTH:
            raise BrowserValidationError(
                f"Batch nesting depth exceeds maximum of {_MAX_BATCH_DEPTH}.",
            )
        raw_actions = command.payload.get("actions")
        if not isinstance(raw_actions, (list, tuple)) or not raw_actions:
            raise BrowserValidationError("batch requires actions.")
        if _count_batch_actions(raw_actions) > _MAX_BATCH_ACTIONS:
            raise BrowserValidationError(f"Batch exceeds maximum of {_MAX_BATCH_ACTIONS} actions.")

        actions: list[BrowserPageActionCommand] = []
        for raw_action in raw_actions:
            if not isinstance(raw_action, Mapping):
                raise BrowserValidationError("batch actions must be objects.")
            actions.append(
                _normalize_batch_action(
                    raw_action=raw_action,
                    profile_name=plan.profile.name,
                    inherited_target_id=tab.target_id,
                    inherited_timeout_ms=command.timeout_ms,
                    depth=batch_depth + 1,
                )
            )
        if not actions:
            raise BrowserValidationError("batch requires actions.")
        stop_on_error = command.payload.get("stop_on_error")
        if not isinstance(stop_on_error, bool):
            stop_on_error = True

        results: list[dict[str, Any]] = []
        for action in actions:
            try:
                result_value, _selector, _frame_path = self._execute_on_page(
                    plan=plan,
                    tab=tab,
                    page=page,
                    runtime_state=runtime_state,
                    command=action,
                    batch_depth=batch_depth + 1,
                )
                if action.kind == "snapshot" and isinstance(result_value, dict):
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
                        action_kind=action.kind,
                    )
                results.append(
                    {
                        "ok": True,
                        "kind": action.kind,
                        "result": result_value,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                results.append(
                    {
                        "ok": False,
                        "kind": action.kind,
                        "error": str(exc),
                    }
                )
                if stop_on_error:
                    break
        return {
            "kind": "batch",
            "stop_on_error": stop_on_error,
            "results": results,
        }

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

    def _trigger_locator(
        self,
        *,
        locator,
        payload: Mapping[str, Any],
        timeout: float | None,
    ) -> dict[str, Any]:
        trigger = (_payload_text_any(payload, "trigger") or "click").strip().lower()
        if trigger == "click":
            return {
                "trigger": "click",
                "mode": self._click(
                    locator=locator,
                    timeout=timeout,
                    button="left",
                    force=bool(payload.get("force", False)),
                    double_click=False,
                ),
            }
        if trigger == "hover":
            locator.hover(**_timeout_kwargs(timeout))
            return {"trigger": "hover"}
        if trigger == "press":
            key = _payload_text_any(payload, "key") or "ArrowDown"
            locator.press(key, **_timeout_kwargs(timeout))
            return {"trigger": "press", "key": key}
        raise BrowserValidationError("trigger must be click, hover, or press.")

    def _toolbar_command_locator(
        self,
        *,
        root,
        payload: Mapping[str, Any],
    ):
        command_text = _payload_text_any(payload, "command_text", "commandText", "text")
        if command_text is None:
            raise BrowserValidationError("toolbar-action requires command_text, command_ref, or command_selector.")
        exact = _locator_exact(payload)
        ordinal = _locator_ordinal(payload)
        for role in ("button", "menuitem", "tab", "link", "checkbox", "radio"):
            get_by_role = getattr(root, "get_by_role", None)
            if callable(get_by_role):
                locator = get_by_role(role, name=command_text, exact=exact)
                if ordinal is not None:
                    nth_method = getattr(locator, "nth", None)
                    if callable(nth_method):
                        locator = nth_method(ordinal)
                return locator, describe_role_locator(role=role, name=command_text, nth=ordinal)
        locator = self._text_locator(
            root=root,
            text=command_text,
            exact=exact,
            ordinal=ordinal,
        )
        description = f"text={command_text}"
        if ordinal is not None:
            description = f"{description}[ordinal={ordinal}]"
        return locator, description

    def _input_text(
        self,
        *,
        locator,
        text: str,
        payload: Mapping[str, Any],
        timeout: float | None,
        action_kind: str,
        default_mode: str = "fill",
    ) -> str:
        input_mode = (_payload_text_any(payload, "input_mode", "inputMode") or default_mode).strip().lower()
        if input_mode not in {"fill", "type"}:
            raise BrowserValidationError("input_mode must be fill or type.")
        self._ensure_editable_text_target(locator=locator, action_kind=action_kind)
        if input_mode == "type":
            type_kwargs: dict[str, Any] = _timeout_kwargs(timeout)
            delay = _payload_number_any(payload, "delay_ms", "delayMs")
            if delay is not None:
                type_kwargs["delay"] = float(delay)
            type_method = getattr(locator, "type", None)
            if callable(type_method):
                type_method(text, **type_kwargs)
            else:
                locator.fill(text, **_timeout_kwargs(timeout))
                input_mode = "fill"
        else:
            locator.fill(text, **_timeout_kwargs(timeout))
        return input_mode

    def _text_target_editability(self, *, locator) -> dict[str, Any]:
        info = self._target_info(locator=locator)
        tag = str(info.get("tag") or "").strip().lower()
        role = str(info.get("role") or "").strip().lower()
        content_editable = bool(info.get("content_editable"))
        read_only = bool(info.get("read_only"))
        disabled = bool(info.get("disabled"))
        editable = (
            content_editable
            or tag in {"input", "textarea"}
            or role in {"textbox", "combobox", "searchbox", "spinbutton"}
        )
        return {
            **info,
            "tag": tag,
            "role": role,
            "editable": editable,
            "read_only": read_only,
            "disabled": disabled,
        }

    def _ensure_editable_text_target(self, *, locator, action_kind: str) -> None:
        info = self._text_target_editability(locator=locator)
        tag = str(info.get("tag") or "")
        role = str(info.get("role") or "")
        editable = bool(info.get("editable"))
        read_only = bool(info.get("read_only"))
        disabled = bool(info.get("disabled"))
        if editable and not read_only and not disabled:
            return
        target_bits = [part for part in (f"tag={tag}" if tag else None, f"role={role}" if role else None) if part]
        target_desc = ", ".join(target_bits) if target_bits else "unknown target"
        raise BrowserValidationError(
            f"Browser action '{action_kind}' targeted a non-editable element ({target_desc}). Choose an input/textbox/contenteditable ref or selector.",
        )

    def _can_fill_via_custom_overlay(self, *, locator, payload: Mapping[str, Any]) -> bool:
        allow_custom = _payload_bool_any(payload, "allow_custom_input", "allowCustomInput")
        if allow_custom is False:
            return False
        info = self._text_target_editability(locator=locator)
        if bool(info.get("disabled")):
            return False
        tag = str(info.get("tag") or "")
        role = str(info.get("role") or "")
        if allow_custom is True:
            return True
        return bool(info.get("read_only")) or tag == "select" or role in {
            "combobox",
            "searchbox",
            "spinbutton",
        }

    def _fill_via_custom_overlay(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        command: BrowserPageActionCommand,
        locator,
        resolved_selector: str | None,
        text: str,
        timeout: float | None,
        original_error: BrowserValidationError,
    ) -> dict[str, Any]:
        if not self._can_fill_via_custom_overlay(
            locator=locator,
            payload=command.payload,
        ):
            raise original_error

        trigger = self._trigger_locator(
            locator=locator,
            payload=command.payload,
            timeout=timeout,
        )
        overlay_payload = self._custom_overlay_payload(
            command=command,
            resolved_selector=resolved_selector,
            text=text,
        )
        overlay_wait = self._wait_for_overlay_surface(
            plan=plan,
            page=page,
            runtime_state=runtime_state,
            tab=tab,
            command=command,
            payload=overlay_payload,
            timeout=timeout,
        )
        overlay_selector = _normalize_optional_text(
            overlay_wait.get("overlay_selector"),
        )
        root = _main_frame(page)
        if overlay_selector is not None:
            root = root.locator(overlay_selector)

        source_selector = _payload_text_any(
            overlay_payload,
            "overlay_source_selector",
            "overlaySourceSelector",
        )
        source_scope_selector = (
            _payload_text_any(
                overlay_payload,
                "overlay_source_scope_selector",
                "overlaySourceScopeSelector",
            )
            or next(
                iter(
                    self._overlay_source_scope_selectors_for_command(
                        plan=plan,
                        tab=tab,
                        runtime_state=runtime_state,
                        command=command,
                    )
                ),
                None,
            )
        )
        option_locator = self._text_locator(
            root=root,
            text=text,
            exact=_locator_exact(overlay_payload),
            ordinal=_locator_ordinal(overlay_payload),
            source_selector=source_selector,
            source_scope_selector=source_scope_selector,
        )
        selection_mode = self._click(
            locator=option_locator,
            timeout=timeout,
            button=command.payload.get("button"),
            force=bool(command.payload.get("force", False)),
            double_click=bool(command.payload.get("double_click", False)),
        )
        remembered_overlay = self._remember_overlay_binding(
            plan=plan,
            page=page,
            runtime_state=runtime_state,
            tab=tab,
            command=command,
            payload=overlay_payload,
            resolved_selector=resolved_selector,
            overlay_selector=overlay_selector,
        )
        return {
            "kind": "fill",
            "text": text,
            "input_mode": "custom-overlay",
            "trigger": trigger,
            "overlay": overlay_wait,
            "selected": {
                "text": text,
                "mode": selection_mode,
                "overlay_selector": remembered_overlay or overlay_selector,
            },
        }

    def _custom_overlay_payload(
        self,
        *,
        command: BrowserPageActionCommand,
        resolved_selector: str | None,
        text: str,
    ) -> dict[str, Any]:
        payload = dict(command.payload)
        payload.setdefault("active_overlay", True)
        payload.setdefault("overlay_text", text)
        if command.target.ref is not None:
            payload.setdefault("overlay_source_ref", command.target.ref)
        if resolved_selector is not None:
            payload.setdefault("overlay_source_selector", resolved_selector)
        elif command.target.selector is not None:
            payload.setdefault("overlay_source_selector", command.target.selector)
        return payload

    def _target_info(self, *, locator) -> dict[str, Any]:
        evaluate = getattr(locator, "evaluate", None)
        if not callable(evaluate):
            return {}
        try:
            value = evaluate(_TARGET_INFO_EXPRESSION)
        except Exception:  # noqa: BLE001
            return {}
        if not isinstance(value, Mapping):
            return {}
        return {
            "tag": str(value.get("tag") or "").strip().lower() or None,
            "role": str(value.get("role") or "").strip().lower() or None,
            "type": str(value.get("type") or "").strip().lower() or None,
            "content_editable": bool(value.get("contentEditable") or value.get("content_editable")),
            "read_only": bool(value.get("readOnly") or value.get("read_only")),
            "disabled": bool(value.get("disabled")),
            "checked": bool(value.get("checked")),
            "value": value.get("value"),
        }

    def _derive_date_option_text(self, *, date_value: str) -> str:
        for separator in ("-", "/", "."):
            parts = [segment.strip() for segment in date_value.split(separator)]
            if len(parts) == 3 and all(parts):
                tail = parts[-1]
                if tail.isdigit():
                    return str(int(tail))
        digits = "".join(character for character in date_value if character.isdigit())
        if len(digits) >= 1 and date_value.strip().isdigit():
            return str(int(digits))
        return date_value


    def _derive_date_target_month(
        self,
        *,
        date_value: str | None,
        month_header_text: str | None,
    ) -> dict[str, Any] | None:
        resolved_text = _normalize_optional_text(month_header_text)
        month_key: str | None = None
        if date_value is not None:
            for separator in ("-", "/", "."):
                parts = [segment.strip() for segment in date_value.split(separator)]
                if len(parts) != 3 or not all(parts):
                    continue
                year_text, month_text, _day_text = parts
                if not (year_text.isdigit() and len(year_text) == 4 and month_text.isdigit()):
                    continue
                year = int(year_text)
                month = int(month_text)
                if not 1 <= month <= 12:
                    continue
                month_key = f"{year:04d}-{month:02d}"
                if resolved_text is None:
                    resolved_text = f"{calendar.month_name[month]} {year:04d}"
                break
        if resolved_text is None and month_key is None:
            return None
        result: dict[str, Any] = {}
        if resolved_text is not None:
            result["text"] = resolved_text
        if month_key is not None:
            result["key"] = month_key
        return result

    def _month_key_from_text(self, text: str | None) -> str | None:
        normalized = _normalize_optional_text(text)
        if normalized is None:
            return None
        direct_match = re.search(r"(?P<year>\d{4})\D+(?P<month>\d{1,2})", normalized)
        if direct_match:
            year = int(direct_match.group("year"))
            month = int(direct_match.group("month"))
            if 1 <= month <= 12:
                return f"{year:04d}-{month:02d}"
        lowered = normalized.lower()
        year_match = re.search(r"(?P<year>\d{4})", lowered)
        if year_match is None:
            return None
        year = int(year_match.group("year"))
        for month in range(1, 13):
            names = {
                calendar.month_name[month].lower(),
                calendar.month_abbr[month].lower(),
            }
            if any(name and name in lowered for name in names):
                return f"{year:04d}-{month:02d}"
        return None

    def _month_delta(self, *, current_key: str | None, target_key: str | None) -> int | None:
        if current_key is None or target_key is None:
            return None
        try:
            current_year, current_month = (int(part) for part in current_key.split("-", 1))
            target_year, target_month = (int(part) for part in target_key.split("-", 1))
        except (TypeError, ValueError):
            return None
        return (target_year - current_year) * 12 + (target_month - current_month)



    def _locator_display_text(self, locator) -> str | None:  # noqa: ANN001
        evaluate = getattr(locator, "evaluate", None)
        if not callable(evaluate):
            return None
        try:
            resolved = evaluate(
                "(element) => (element.innerText || element.textContent || element.getAttribute('aria-label') || '').trim()",
            )
        except Exception:  # noqa: BLE001
            return None
        return _normalize_optional_text(resolved)

    def _target_locator_from_payload(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        payload: Mapping[str, Any],
        ref_keys: tuple[str, ...],
        selector_keys: tuple[str, ...],
    ) -> tuple[Any, Any, str | None, tuple[int, ...]] | None:
        ref_id = _payload_text_any(payload, *ref_keys)
        if ref_id is not None:
            return self._locator_from_ref(
                plan=plan,
                tab=tab,
                page=page,
                runtime_state=runtime_state,
                ref_id=ref_id,
            )
        selector = _payload_text_any(payload, *selector_keys)
        if selector is None:
            return None
        scope_payload = dict(payload)
        temp_command = BrowserPageActionCommand(
            profile_name=plan.profile.name,
            kind="click",
            target=BrowserActionTarget(
                target_id=tab.target_id,
                selector=selector,
            ),
            payload=scope_payload,
        )
        return self._locator(
            plan=plan,
            tab=tab,
            page=page,
            runtime_state=runtime_state,
            command=temp_command,
            required=True,
        )

    def _bulk_selection_root(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        command: BrowserPageActionCommand,
    ) -> tuple[Any, bool, str | None, tuple[int, ...]]:
        scope_ref = _scope_ref_id(command.payload)
        scope_selector = _scope_selector(command.payload)
        if scope_ref is not None and scope_selector is not None:
            raise BrowserValidationError(
                "payload.scope_ref and payload.scope_selector are mutually exclusive.",
            )
        if scope_ref is not None:
            _context, locator, description, frame_path = self._locator_from_ref(
                plan=plan,
                tab=tab,
                page=page,
                runtime_state=runtime_state,
                ref_id=scope_ref,
            )
            return locator, True, description, frame_path
        if scope_selector is not None:
            return _main_frame(page).locator(scope_selector), True, scope_selector, ()
        if command.target.ref is not None:
            _context, locator, description, frame_path = self._locator_from_ref(
                plan=plan,
                tab=tab,
                page=page,
                runtime_state=runtime_state,
                ref_id=command.target.ref,
            )
            return locator, True, description, frame_path
        if command.target.selector is not None:
            return _main_frame(page).locator(command.target.selector), True, command.target.selector, ()
        if _active_overlay(command.payload):
            overlay_selector = self._resolved_active_overlay_selector(
                page=page,
                runtime_state=runtime_state,
                tab=tab,
                command=command,
            )
            if overlay_selector is not None:
                return _main_frame(page).locator(overlay_selector), True, overlay_selector, ()
        return _main_frame(page), False, None, ()


    def _set_locator_checked(
        self,
        *,
        locator,
        checked: bool,
        timeout: float | None,
        force: bool,
    ) -> str:
        set_checked = getattr(locator, "set_checked", None)
        if callable(set_checked):
            set_checked(checked, **_timeout_kwargs(timeout))
            return "set_checked"
        method = getattr(locator, "check" if checked else "uncheck", None)
        if callable(method):
            method(**_timeout_kwargs(timeout))
            return "check" if checked else "uncheck"
        return self._click(
            locator=locator,
            timeout=timeout,
            button="left",
            force=force,
            double_click=False,
        )

    def _click(
        self,
        *,
        locator,
        timeout: float | None,
        button: Any,
        force: bool,
        double_click: bool,
    ) -> str:
        method_name = "dblclick" if double_click else "click"
        method = getattr(locator, method_name, None)
        if not callable(method):
            raise BrowserValidationError(
                f"Playwright locator does not support '{method_name}'.",
            )

        kwargs: dict[str, Any] = {}
        if isinstance(button, str) and button.strip():
            kwargs["button"] = button.strip()

        if force:
            method(**kwargs, **_timeout_kwargs(timeout), force=True)
            return "force"

        try:
            method(**kwargs, **_timeout_kwargs(_probe_timeout(timeout)))
            return "direct"
        except Exception as exc:  # noqa: BLE001
            if not _is_pointer_interception_error(exc):
                raise

        method(**kwargs, **_timeout_kwargs(timeout), force=True)
        return "force"

    def _coordinate_click(
        self,
        *,
        page,
        x: float,
        y: float,
        button: Any,
        double_click: bool,
    ) -> dict[str, Any]:
        mouse = getattr(page, "mouse", None)
        click = getattr(mouse, "click", None)
        if not callable(click):
            raise BrowserValidationError(
                "Playwright page does not support coordinate mouse clicks.",
            )
        kwargs: dict[str, Any] = {}
        if isinstance(button, str) and button.strip():
            kwargs["button"] = button.strip()
        if double_click:
            kwargs["click_count"] = 2
        click(x, y, **kwargs)
        return {
            "kind": "click",
            "mode": "coordinate",
            "x": x,
            "y": y,
            "button": kwargs.get("button"),
            "double_click": double_click,
        }

    def _locator(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        command: BrowserPageActionCommand,
        required: bool,
    ) -> tuple[Any, Any | None, str | None, tuple[int, ...] | None]:
        if command.target.ref is not None:
            return self._locator_from_ref(
                plan=plan,
                tab=tab,
                page=page,
                runtime_state=runtime_state,
                ref_id=command.target.ref,
            )
        if command.target.selector is None:
            if required:
                raise BrowserValidationError(
                    f"Browser action '{command.kind}' requires ref or selector targeting.",
                )
            return page, None, None, None
        root = self._scoped_root(
            plan=plan,
            tab=tab,
            page=page,
            runtime_state=runtime_state,
            command=command,
        )
        locator_factory = getattr(root, "locator", None)
        if not callable(locator_factory):
            raise BrowserValidationError(
                f"Browser action '{command.kind}' does not support scoped selector resolution.",
            )
        locator = locator_factory(command.target.selector)
        ordinal = _locator_ordinal(command.payload)
        if ordinal is None and _allows_implicit_selector_ordinal(command):
            ordinal = self._preferred_selector_ordinal(
                locator=locator,
                command=command,
            )
        if ordinal is not None:
            nth_method = getattr(locator, "nth", None)
            if not callable(nth_method):
                raise BrowserValidationError(
                    f"Browser action '{command.kind}' does not support ordinal selector resolution.",
                )
            locator = nth_method(ordinal)
        description = command.target.selector
        scope_selector = _scope_selector(command.payload)
        scope_ref = _scope_ref_id(command.payload)
        if scope_selector is not None:
            description = f"{scope_selector} >> {description}"
        elif scope_ref is not None:
            description = f"{scope_ref} >> {description}"
        if ordinal is not None:
            ordinal_label = "auto-ordinal" if _locator_ordinal(command.payload) is None else "ordinal"
            description = f"{description}[{ordinal_label}={ordinal}]"
        return _main_frame(page), locator, description, ()

    def _preferred_selector_ordinal(
        self,
        *,
        locator,
        command: BrowserPageActionCommand,
    ) -> int | None:
        count = getattr(locator, "count", None)
        nth = getattr(locator, "nth", None)
        if not callable(count) or not callable(nth):
            return None
        try:
            candidate_count = int(count())
        except Exception:  # noqa: BLE001
            return None
        if candidate_count <= 1:
            return None
        best_ordinal: int | None = None
        best_score: int | None = None
        for index in range(candidate_count):
            candidate = nth(index)
            info = self._locator_target_info(candidate)
            score = self._score_selector_candidate(info=info, command=command)
            if best_score is None or score > best_score:
                best_score = score
                best_ordinal = index
        return best_ordinal

    def _locator_target_info(
        self,
        locator,
    ) -> Mapping[str, Any]:
        evaluate = getattr(locator, "evaluate", None)
        if not callable(evaluate):
            return {}
        try:
            value = evaluate(_TARGET_INFO_EXPRESSION)
        except Exception:  # noqa: BLE001
            return {}
        if isinstance(value, Mapping):
            return value
        return {}

    def _score_selector_candidate(
        self,
        *,
        info: Mapping[str, Any],
        command: BrowserPageActionCommand,
    ) -> int:
        tag = str(info.get("tag") or "").strip().lower()
        role = str(info.get("role") or "").strip().lower()
        score = 0
        if bool(info.get("focused")):
            score += 10_000
        if bool(info.get("visible", True)):
            score += 5_000
        if not bool(info.get("disabled", False)):
            score += 2_000
        if command.kind in {"fill", "type", "wait", "press"}:
            if tag in {"input", "textarea", "select"}:
                score += 700
            if role in {"textbox", "combobox", "searchbox", "spinbutton"}:
                score += 800
            if bool(info.get("contentEditable")):
                score += 650
            if not bool(info.get("readOnly", False)):
                score += 250
        if command.kind == "select" and tag == "select":
            score += 900
        return score

    def _locator_from_ref(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        ref_id: str,
    ) -> tuple[Any, Any, str | None, tuple[int, ...]]:
        stored_refs = self.ref_store.get_tab_refs(
            profile_name=plan.profile.name,
            target_id=tab.target_id,
        )
        page_state = runtime_state.page_state(target_id=tab.target_id) or {}
        current_generation = int(page_state.get("current_ref_generation") or 0)
        for item in stored_refs:
            if item.ref != ref_id:
                continue
            if (
                item.selector is None
                and item.role is None
                and item.backend_node_id is None
            ):
                raise BrowserValidationError(
                    f"Browser ref '{ref_id}' does not expose a supported locator.",
                )
            context = _resolve_frame_context(page, item.frame_path)
            generation_mismatch = current_generation and item.generation != current_generation
            devtools_locator, devtools_description = self._devtools_locator_from_ref_item(
                page=page,
                context=context,
                item=item,
            )
            anchored_locator, anchored_description = self._anchored_locator_from_ref_item(
                context=context,
                item=item,
            )
            role_locator = self._semantic_locator_from_ref_item(context=context, item=item)
            prefer_semantic = (
                anchored_locator is not None
                or role_locator is not None
                and (
                    item.snapshot_format in {"interactive", "role", "aria"}
                    or item.selector is None
                    or item.nth is not None
                )
            )
            if generation_mismatch:
                if devtools_locator is not None:
                    return (
                        context,
                        devtools_locator,
                        devtools_description,
                        item.frame_path,
                    )
                if anchored_locator is not None:
                    return (
                        context,
                        anchored_locator,
                        anchored_description,
                        item.frame_path,
                    )
                if role_locator is not None:
                    return (
                        context,
                        role_locator,
                        describe_role_locator(
                            role=item.role or "generic",
                            name=_stored_ref_name(item),
                            nth=item.nth,
                        ),
                        item.frame_path,
                    )
                raise BrowserValidationError(
                    f"Browser ref '{ref_id}' is stale for tab '{tab.target_id}'.",
                )
            if devtools_locator is not None:
                return (
                    context,
                    devtools_locator,
                    devtools_description,
                    item.frame_path,
                )
            if (
                item.selector is not None
                and not generation_mismatch
                and item.nth is None
            ):
                return (
                    context,
                    context.locator(item.selector),
                    item.selector,
                    item.frame_path,
                )
            if prefer_semantic and anchored_locator is not None:
                return (
                    context,
                    anchored_locator,
                    anchored_description,
                    item.frame_path,
                )
            if prefer_semantic and item.role is not None:
                return (
                    context,
                    role_locator,
                    describe_role_locator(
                        role=item.role,
                        name=_stored_ref_name(item),
                        nth=item.nth,
                    ),
                    item.frame_path,
                )
            if item.selector is not None:
                return (
                    context,
                    context.locator(item.selector),
                    item.selector,
                    item.frame_path,
                )
            if role_locator is not None and item.role is not None:
                return (
                    context,
                    role_locator,
                    describe_role_locator(
                        role=item.role,
                        name=_stored_ref_name(item),
                        nth=item.nth,
                    ),
                    item.frame_path,
                )
            raise BrowserValidationError(
                f"Browser ref '{ref_id}' does not expose a supported locator.",
            )
        raise BrowserValidationError(
            f"Browser ref '{ref_id}' was not found for tab '{tab.target_id}'.",
        )

    def _action_trace_protected_ref(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        command: BrowserPageActionCommand,
    ) -> BrowserStoredRef | None:
        ref_id = (
            _payload_text_any(command.payload, "action_ref", "actionRef")
            or command.target.ref
        )
        if ref_id is None:
            return None
        item = self._stored_ref_for_ref_id(plan=plan, tab=tab, ref_id=ref_id)
        if item is None or not _stored_ref_has_precise_locator(item):
            return None
        return item

    def _restore_action_trace_protected_ref(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        protected_ref: BrowserStoredRef,
    ) -> None:
        current_refs = list(
            self.ref_store.get_tab_refs(
                profile_name=plan.profile.name,
                target_id=tab.target_id,
            )
        )
        for index, item in enumerate(current_refs):
            if item.ref != protected_ref.ref:
                continue
            if not _stored_refs_look_compatible(protected_ref, item):
                return
            if _stored_ref_has_precise_locator(item):
                return
            current_refs[index] = _merge_protected_ref_locator(
                current=item,
                protected=protected_ref,
            )
            self.ref_store.save_tab_refs(
                profile_name=plan.profile.name,
                target_id=tab.target_id,
                refs=tuple(current_refs),
            )
            return

    def _stored_ref_for_command(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        command: BrowserPageActionCommand,
    ) -> BrowserStoredRef | None:
        ref_id = command.target.ref
        if ref_id is None:
            return None
        return self._stored_ref_for_ref_id(plan=plan, tab=tab, ref_id=ref_id)

    def _stored_ref_for_ref_id(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        ref_id: str,
    ) -> BrowserStoredRef | None:
        for item in self.ref_store.get_tab_refs(
            profile_name=plan.profile.name,
            target_id=tab.target_id,
        ):
            if item.ref == ref_id:
                return item
        return None

    def _devtools_event_listeners_for_command(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        command: BrowserPageActionCommand,
    ) -> dict[str, Any] | None:
        if self.devtools_adapter is None:
            return None
        item = self._stored_ref_for_command(plan=plan, tab=tab, command=command)
        if item is None or item.backend_node_id is None or item.frame_path:
            return None
        try:
            return self.devtools_adapter.get_event_listeners_for_backend_node(
                page,
                backend_node_id=item.backend_node_id,
                depth=1,
                pierce=True,
            )
        except BrowserValidationError as exc:
            return {"error": str(exc), "listeners": []}

    def _devtools_locator_from_ref_item(
        self,
        *,
        page,
        context,
        item: BrowserStoredRef,
    ) -> tuple[Any, str] | tuple[None, None]:
        if item.backend_node_id is None:
            return None, None
        if item.frame_path:
            return None, None
        locator_factory = getattr(context, "locator", None)
        if not callable(locator_factory):
            return None, None
        adapter = self.devtools_adapter
        if adapter is None:
            return None, None
        marker_value = _devtools_ref_marker_value(item)
        try:
            adapter.mark_backend_node(
                page,
                backend_node_id=item.backend_node_id,
                attribute_name=_DEVTOOLS_REF_ATTRIBUTE,
                attribute_value=marker_value,
            )
        except BrowserValidationError:
            return None, None
        selector = f'[{_DEVTOOLS_REF_ATTRIBUTE}="{marker_value}"]'
        return locator_factory(selector), f"backendNodeId={item.backend_node_id}"

    def _anchored_locator_from_ref_item(
        self,
        *,
        context,
        item: BrowserStoredRef,
    ) -> tuple[Any, str] | tuple[None, None]:
        scope_selector = _normalize_optional_text(item.scope_selector)
        if scope_selector is None:
            return None, None
        scoped_root = context.locator(scope_selector)

        role_locator = self._semantic_locator_from_ref_item(context=scoped_root, item=item)
        if role_locator is not None:
            return (
                role_locator,
                f"{scope_selector} >> {describe_role_locator(role=item.role or 'generic', name=_stored_ref_name(item), nth=item.nth)}",
            )

        name = _stored_ref_name(item)
        if name is None:
            return None, None
        text_factory = getattr(scoped_root, "get_by_text", None)
        if not callable(text_factory):
            return None, None
        text_locator = text_factory(name, exact=True)
        if item.nth is not None:
            nth_method = getattr(text_locator, "nth", None)
            if not callable(nth_method):
                raise BrowserValidationError(
                    f"Browser ref '{item.ref}' requires nth text resolution, but the Playwright locator does not support nth().",
                )
            text_locator = nth_method(item.nth)
        description = f'{scope_selector} >> text="{name}"'
        if item.nth is not None:
            description = f"{description}[nth={item.nth}]"
        return text_locator, description

    def _semantic_locator_from_ref_item(self, *, context, item: BrowserStoredRef):  # noqa: ANN001
        locator_factory = getattr(context, "get_by_role", None)
        if not callable(locator_factory) or item.role is None:
            return None
        role_kwargs: dict[str, Any] = {}
        name = _stored_ref_name(item)
        if name is not None:
            role_kwargs["name"] = name
            role_kwargs["exact"] = True
        role_locator = locator_factory(item.role, **role_kwargs)
        if item.nth is not None:
            nth_method = getattr(role_locator, "nth", None)
            if not callable(nth_method):
                raise BrowserValidationError(
                    f"Browser ref '{item.ref}' requires nth role resolution, but the Playwright locator does not support nth().",
                )
            role_locator = nth_method(item.nth)
        return role_locator

    def _resolved_active_overlay_selector(
        self,
        *,
        page,
        runtime_state: BrowserProfileRuntimeState,
        tab: BrowserTab,
        command: BrowserPageActionCommand | None = None,
        overlay_kind: str | None = None,
        source_refs: tuple[str, ...] = (),
        source_selectors: tuple[str, ...] = (),
        source_scope_selectors: tuple[str, ...] = (),
    ) -> str | None:
        candidate_refs = source_refs
        candidate_selectors = source_selectors
        candidate_scope_selectors = source_scope_selectors
        if command is not None:
            candidate_refs = candidate_refs + _command_overlay_source_refs(command)
            candidate_selectors = candidate_selectors + _command_overlay_source_selectors(
                command,
            )
            candidate_scope_selectors = (
                candidate_scope_selectors
                + _command_overlay_source_scope_selectors(command)
                + self._overlay_source_scope_selectors_for_command(
                    plan=None,
                    tab=tab,
                    runtime_state=runtime_state,
                    command=command,
                )
            )
            if overlay_kind is None:
                overlay_kind = self._overlay_kind_for_command(
                    runtime_state=runtime_state,
                    tab=tab,
                    command=command,
                )
        stored = runtime_state.active_overlay_selector(
            target_id=tab.target_id,
            overlay_kind=overlay_kind,
            source_refs=candidate_refs,
            source_selectors=candidate_selectors,
            source_scope_selectors=candidate_scope_selectors,
        )
        if stored is not None:
            return stored
        return _active_overlay_selector(page)

    def _overlay_source_selector_for_command(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        command: BrowserPageActionCommand,
    ) -> str | None:
        explicit_selector = _payload_text_any(
            command.payload,
            "overlay_source_selector",
            "overlaySourceSelector",
        )
        if explicit_selector is not None:
            return explicit_selector

        source_ref = _payload_text_any(
            command.payload,
            "overlay_source_ref",
            "overlaySourceRef",
        )
        if source_ref is not None:
            try:
                _context, _locator, description, _frame_path = self._locator_from_ref(
                    plan=plan,
                    tab=tab,
                    page=page,
                    runtime_state=runtime_state,
                    ref_id=source_ref,
                )
            except BrowserValidationError:
                description = None
            if isinstance(description, str) and description.strip().startswith(("#", ".", "body ", "body>", "input", "button", "select", "textarea", "[")):
                return description.strip()

        overlay_context = runtime_state.active_overlay_context(target_id=tab.target_id)
        if isinstance(overlay_context, dict):
            return _normalize_optional_text(overlay_context.get("source_selector"))
        return None

    def _overlay_source_scope_selectors_for_command(
        self,
        *,
        plan: BrowserExecutionPlan | None,
        tab: BrowserTab,
        runtime_state: BrowserProfileRuntimeState,
        command: BrowserPageActionCommand,
    ) -> tuple[str, ...]:
        candidates: list[str] = list(_command_overlay_source_scope_selectors(command))
        for ref_id in _command_overlay_source_refs(command):
            resolved_scope = self._stored_ref_scope_selector(
                plan=plan,
                tab=tab,
                ref_id=ref_id,
            )
            if resolved_scope is not None:
                candidates.append(resolved_scope)
        overlay_context = runtime_state.active_overlay_context(target_id=tab.target_id)
        if isinstance(overlay_context, dict):
            runtime_scope = _normalize_optional_text(
                overlay_context.get("source_scope_selector"),
            )
            if runtime_scope is not None:
                candidates.append(runtime_scope)
        seen: set[str] = set()
        resolved: list[str] = []
        for candidate in candidates:
            normalized = _normalize_optional_text(candidate)
            if normalized is None or normalized in seen:
                continue
            seen.add(normalized)
            resolved.append(normalized)
        return tuple(resolved)

    def _stored_ref_scope_selector(
        self,
        *,
        plan: BrowserExecutionPlan | None,
        tab: BrowserTab,
        ref_id: str,
    ) -> str | None:
        if plan is None:
            return None
        for item in self.ref_store.get_tab_refs(
            profile_name=plan.profile.name,
            target_id=tab.target_id,
        ):
            if item.ref == ref_id:
                return _normalize_optional_text(item.scope_selector)
        return None

    def _remember_overlay_binding(
        self,
        *,
        plan: BrowserExecutionPlan,
        page,
        runtime_state: BrowserProfileRuntimeState,
        tab: BrowserTab,
        command: BrowserPageActionCommand,
        payload: Mapping[str, Any],
        resolved_selector: str | None = None,
        overlay_selector: str | None = None,
    ) -> str | None:
        resolved_overlay = overlay_selector
        if resolved_overlay is None:
            resolved_overlay = _payload_text_any(
                payload,
                "overlay_selector",
                "overlaySelector",
            )
        if resolved_overlay is None:
            resolved_overlay = _active_overlay_selector(page)
        if resolved_overlay is None:
            return None
        runtime_state.remember_active_overlay(
            target_id=tab.target_id,
            overlay_selector=resolved_overlay,
            overlay_kind=self._overlay_kind_for_command(
                runtime_state=runtime_state,
                tab=tab,
                command=command,
            ),
            source_ref=next(iter(_command_overlay_source_refs(command)), None),
            source_selector=next(
                iter(
                    _command_overlay_source_selectors(
                        command,
                        resolved_selector=resolved_selector,
                    )
                ),
                None,
            ),
            source_scope_selector=next(
                iter(
                    self._overlay_source_scope_selectors_for_command(
                        plan=plan,
                        tab=tab,
                        runtime_state=runtime_state,
                        command=command,
                    )
                ),
                None,
            ),
        )
        return resolved_overlay

    def _overlay_kind_for_command(
        self,
        *,
        runtime_state: BrowserProfileRuntimeState,
        tab: BrowserTab,
        command: BrowserPageActionCommand,
    ) -> str | None:
        explicit = _explicit_overlay_kind(command.payload)
        if explicit is not None:
            return explicit
        overlay_context = runtime_state.active_overlay_context(target_id=tab.target_id)
        if isinstance(overlay_context, dict):
            return _normalize_optional_text(overlay_context.get("kind"))
        return None

    def _clear_overlay_binding(
        self,
        *,
        runtime_state: BrowserProfileRuntimeState,
        tab: BrowserTab,
    ) -> None:
        runtime_state.clear_active_overlay(target_id=tab.target_id)

    def _scoped_root(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        command: BrowserPageActionCommand,
    ):
        scope_ref = _scope_ref_id(command.payload)
        scope_selector = _scope_selector(command.payload)
        if scope_ref is not None and scope_selector is not None:
            raise BrowserValidationError(
                "payload.scope_ref and payload.scope_selector are mutually exclusive.",
            )
        if scope_ref is not None:
            _context, scope_locator, _description, _frame_path = self._locator_from_ref(
                plan=plan,
                tab=tab,
                page=page,
                runtime_state=runtime_state,
                ref_id=scope_ref,
            )
            return scope_locator
        context = _main_frame(page)
        if scope_selector is not None:
            return context.locator(scope_selector)
        if _active_overlay(command.payload) or _wait_prefers_active_overlay(command):
            overlay_selector = self._resolved_active_overlay_selector(
                page=page,
                runtime_state=runtime_state,
                tab=tab,
                command=command,
            )
            if overlay_selector is not None:
                return context.locator(overlay_selector)
        return context

    def _text_locator(
        self,
        *,
        root,
        text: str,
        exact: bool,
        ordinal: int | None,
        source_selector: str | None = None,
        source_scope_selector: str | None = None,
    ):
        search_root = root
        if not callable(getattr(search_root, "get_by_text", None)):
            locator_factory = getattr(root, "locator", None)
            if callable(locator_factory):
                search_root = locator_factory("body")

        text_factory = getattr(search_root, "get_by_text", None)
        if callable(text_factory):
            locator = text_factory(text, exact=exact)
        else:
            locator_factory = getattr(search_root, "locator", None)
            if not callable(locator_factory):
                raise BrowserValidationError("Browser text wait could not construct a locator.")
            locator = locator_factory("text=" + text)
        resolved_ordinal = ordinal
        if resolved_ordinal is None:
            resolved_ordinal = self._preferred_text_ordinal(
                root=search_root,
                text=text,
                exact=exact,
                source_selector=source_selector,
                source_scope_selector=source_scope_selector,
            )
        if resolved_ordinal is not None:
            nth_method = getattr(locator, "nth", None)
            if not callable(nth_method):
                raise BrowserValidationError("Browser text wait does not support ordinal selection.")
            locator = nth_method(resolved_ordinal)
        return locator

    def _preferred_text_ordinal(
        self,
        *,
        root,
        text: str,
        exact: bool,
        source_selector: str | None,
        source_scope_selector: str | None,
    ) -> int | None:
        normalized_source = _normalize_optional_text(source_selector)
        normalized_source_scope = _normalize_optional_text(source_scope_selector)
        if normalized_source is None and normalized_source_scope is None:
            return None
        evaluate = getattr(root, "evaluate", None)
        if not callable(evaluate):
            return None
        try:
            resolved = evaluate(
                _TEXT_MATCH_ORDINAL_EXPRESSION,
                {
                    "text": text,
                    "exact": exact,
                    "sourceSelector": normalized_source,
                    "sourceScopeSelector": normalized_source_scope,
                },
            )
        except Exception:  # noqa: BLE001
            return None
        try:
            numeric = int(resolved)
        except (TypeError, ValueError):
            return None
        return numeric if numeric >= 0 else None


    def _wait_for_overlay_surface(
        self,
        *,
        plan: BrowserExecutionPlan,
        page,
        runtime_state: BrowserProfileRuntimeState,
        tab: BrowserTab,
        command: BrowserPageActionCommand,
        payload: Mapping[str, Any],
        timeout: float | None,
    ) -> dict[str, Any]:
        overlay_selector = _payload_text_any(payload, "overlay_selector", "overlaySelector")
        if overlay_selector is not None:
            page.locator(overlay_selector).wait_for(
                state="visible",
                **_timeout_kwargs(timeout),
            )
            return {
                "waited_for_overlay": True,
                "overlay_selector": overlay_selector,
            }

        overlay_text = _payload_text_any(payload, "overlay_text", "overlayText")
        if overlay_text is not None:
            overlay_locator = self._text_locator(
                root=_main_frame(page),
                text=overlay_text,
                exact=_locator_exact(payload),
                ordinal=_locator_ordinal(payload),
                source_selector=_payload_text_any(
                    payload,
                    "overlay_source_selector",
                    "overlaySourceSelector",
                ),
                source_scope_selector=_payload_text_any(
                    payload,
                    "overlay_source_scope_selector",
                    "overlaySourceScopeSelector",
                )
                or _scope_selector(payload),
            )
            overlay_locator.wait_for(**_timeout_kwargs(timeout))
            resolved_overlay_selector = _active_overlay_selector(page) or self._resolved_active_overlay_selector(
                page=page,
                runtime_state=runtime_state,
                tab=tab,
                command=command,
            )
            return {
                "waited_for_overlay": True,
                "overlay_text": overlay_text,
                "exact": _locator_exact(payload),
                "ordinal": _locator_ordinal(payload),
                "overlay_selector": resolved_overlay_selector,
            }

        if _active_overlay(payload):
            overlay_kind = self._overlay_kind_for_command(
                runtime_state=runtime_state,
                tab=tab,
                command=command,
            )
            source_selector = self._overlay_source_selector_for_command(
                plan=plan,
                tab=tab,
                page=page,
                runtime_state=runtime_state,
                command=command,
            )
            source_scope_selector = next(
                iter(
                    self._overlay_source_scope_selectors_for_command(
                        plan=plan,
                        tab=tab,
                        runtime_state=runtime_state,
                        command=command,
                    )
                ),
                None,
            )
            if source_selector is not None or source_scope_selector is not None:
                page.wait_for_function(
                    _ASSOCIATED_OVERLAY_SELECTOR_EXPRESSION,
                    {
                        "overlayKind": _normalize_optional_text(overlay_kind),
                        "sourceSelector": source_selector,
                        "sourceScopeSelector": source_scope_selector,
                    },
                    **_timeout_kwargs(timeout),
                )
            else:
                page.wait_for_function(
                    _ACTIVE_OVERLAY_SELECTOR_EXPRESSION,
                    **_timeout_kwargs(timeout),
                )
            resolved_overlay_selector = (
                _associated_overlay_selector(
                    page,
                    overlay_kind=overlay_kind,
                    source_selector=source_selector,
                    source_scope_selector=source_scope_selector,
                )
                or _active_overlay_selector(page)
                or self._resolved_active_overlay_selector(
                    page=page,
                    runtime_state=runtime_state,
                    tab=tab,
                    command=command,
                    overlay_kind=overlay_kind,
                    source_scope_selectors=(
                        (source_scope_selector,) if source_scope_selector is not None else ()
                    ),
                )
            )
            return {
                "waited_for_overlay": True,
                "active_overlay": True,
                "overlay_source_bound": bool(source_selector or source_scope_selector),
                "overlay_selector": resolved_overlay_selector,
            }

        return {"waited_for_overlay": False}



    def _overlay_association_reason(
        self,
        *,
        payload: Mapping[str, Any],
        resolved_overlay_selector: str | None,
        source_selector: str | None,
        source_scope_selector: str | None,
    ) -> str | None:
        if _payload_text_any(payload, "overlay_selector", "overlaySelector") is not None:
            return "explicit-overlay-selector"
        if source_scope_selector is not None and resolved_overlay_selector is not None:
            return "source-scope"
        if source_selector is not None and resolved_overlay_selector is not None:
            return "source-selector"
        if _active_overlay(payload) and resolved_overlay_selector is not None:
            return "active-overlay"
        if resolved_overlay_selector is not None:
            return "overlay-detected"
        return None





    def _wait(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        locator,
        command: BrowserPageActionCommand,
        timeout: float | None,
    ) -> dict[str, Any]:
        if locator is not None:
            state = _payload_text_any(command.payload, "state") or "visible"
            wait_kwargs: dict[str, Any] = {"state": state}
            wait_kwargs.update(_timeout_kwargs(timeout))
            locator.wait_for(**wait_kwargs)
            return {"kind": "wait", "state": state}

        text_values = _normalize_text_payload(_payload_value_any(command.payload, "text"))
        if text_values:
            root = self._scoped_root(
                plan=plan,
                tab=tab,
                page=page,
                runtime_state=runtime_state,
                command=command,
            )
            exact = _locator_exact(command.payload)
            ordinal = _locator_ordinal(command.payload)
            text_locator = self._text_locator(
                root=root,
                text=text_values[0],
                exact=exact,
                ordinal=ordinal,
                source_selector=self._overlay_source_selector_for_command(
                    plan=plan,
                    tab=tab,
                    page=page,
                    runtime_state=runtime_state,
                    command=command,
                ),
                source_scope_selector=next(
                    iter(
                        self._overlay_source_scope_selectors_for_command(
                            plan=plan,
                            tab=tab,
                            runtime_state=runtime_state,
                            command=command,
                        )
                    ),
                    None,
                ),
            )
            text_locator.wait_for(**_timeout_kwargs(timeout))
            return {
                "kind": "wait",
                "text": text_values,
                "exact": exact,
                "ordinal": ordinal,
            }

        text_gone_values = _normalize_text_payload(
            _payload_value_any(command.payload, "text_gone", "textGone"),
        )
        if text_gone_values:
            root = self._scoped_root(
                plan=plan,
                tab=tab,
                page=page,
                runtime_state=runtime_state,
                command=command,
            )
            exact = _locator_exact(command.payload)
            ordinal = _locator_ordinal(command.payload)
            text_locator = self._text_locator(
                root=root,
                text=text_gone_values[0],
                exact=exact,
                ordinal=ordinal,
                source_selector=self._overlay_source_selector_for_command(
                    plan=plan,
                    tab=tab,
                    page=page,
                    runtime_state=runtime_state,
                    command=command,
                ),
                source_scope_selector=next(
                    iter(
                        self._overlay_source_scope_selectors_for_command(
                            plan=plan,
                            tab=tab,
                            runtime_state=runtime_state,
                            command=command,
                        )
                    ),
                    None,
                ),
            )
            text_locator.wait_for(
                state="hidden",
                **_timeout_kwargs(timeout),
            )
            return {
                "kind": "wait",
                "text_gone": text_gone_values,
                "exact": exact,
                "ordinal": ordinal,
            }

        url = _payload_text_any(command.payload, "url")
        if url is not None:
            page.wait_for_url(url, **_timeout_kwargs(timeout))
            return {"kind": "wait", "url": url}

        load_state = _payload_text_any(command.payload, "load_state", "loadState")
        if load_state is not None:
            page.wait_for_load_state(load_state, **_timeout_kwargs(timeout))
            return {"kind": "wait", "load_state": load_state}

        expression = _payload_text_any(command.payload, "expression", "fn")
        if expression is not None:
            page.wait_for_function(expression, **_timeout_kwargs(timeout))
            return {"kind": "wait", "expression": expression}

        delay_ms = _payload_number_any(command.payload, "delay_ms", "time_ms", "timeMs")
        if delay_ms is not None:
            page.wait_for_timeout(float(delay_ms))
            return {"kind": "wait", "delay_ms": float(delay_ms)}

        raise BrowserValidationError(
            "wait requires selector, payload.text, payload.text_gone, payload.url, payload.load_state, payload.expression/payload.fn, or payload.delay_ms.",
        )
