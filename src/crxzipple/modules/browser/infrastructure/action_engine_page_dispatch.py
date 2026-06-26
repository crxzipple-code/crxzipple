from __future__ import annotations

from dataclasses import replace
from typing import Any

from crxzipple.modules.browser.domain import (
    BrowserExecutionPlan,
    BrowserPageActionCommand,
    BrowserProfileRuntimeState,
    BrowserTab,
    BrowserValidationError,
)

from .action_engine_batch import execute_browser_batch
from .action_engine_cdp import execute_cdp_raw
from .action_engine_payloads import (
    _click_coordinates,
    _drag_source_ref,
    _drag_source_selector,
    _LOCATOR_ACTION_KINDS,
    _payload_int_any,
    _timeout_ms,
)
from .action_engine_snapshots import _normalize_form_fields
from .dom_inspection import DOM_INSPECTION_KINDS
from .script_insight import SCRIPT_INSIGHT_KINDS

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


class BrowserPageDispatchMixin:
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
        fill_fields = (
            _normalize_form_fields(command.payload.get("fields"))
            if command.kind == "fill"
            else ()
        )
        effective_command = command
        if (
            command.kind == "drag"
            and command.target.ref is None
            and command.target.selector is None
        ):
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
                (
                    command.kind in _LOCATOR_ACTION_KINDS
                    or command.kind in DOM_INSPECTION_KINDS
                )
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
                raise BrowserValidationError(
                    "Browser network action service is not configured.",
                )
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
                limit=(
                    _payload_int_any(command.payload, "console_limit", minimum=1)
                    or 100
                ),
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
                raise BrowserValidationError(
                    "Browser script insight service is not configured.",
                )
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

        primitive_result = self._execute_page_primitive_action(
            plan=plan,
            tab=tab,
            page=page,
            runtime_state=runtime_state,
            command=command,
            context=context,
            locator=locator,
            resolved_selector=resolved_selector,
            resolved_frame_path=resolved_frame_path,
            fill_fields=fill_fields,
            coordinate_target=coordinate_target,
            timeout=timeout,
            effective_command=effective_command,
        )
        if primitive_result is not None:
            return primitive_result

        raise BrowserValidationError(
            f"Action engine '{self.family}' does not support '{command.kind}'.",
        )
