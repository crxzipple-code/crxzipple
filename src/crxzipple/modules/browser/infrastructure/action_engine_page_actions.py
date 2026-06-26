from __future__ import annotations

from typing import Any

from crxzipple.modules.browser.domain import (
    BrowserExecutionPlan,
    BrowserPageActionCommand,
    BrowserProfileRuntimeState,
    BrowserTab,
    BrowserValidationError,
)

from .action_engine_payloads import (
    _drag_target_ref,
    _drag_target_selector,
    _payload_number_any,
    _payload_text,
    _payload_value_any,
    _serialize_frame_path,
    _timeout_kwargs,
)
from .action_engine_snapshots import _normalize_text_payload


class BrowserPagePrimitiveActionMixin:
    def _execute_page_primitive_action(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page: Any,
        runtime_state: BrowserProfileRuntimeState,
        command: BrowserPageActionCommand,
        context: Any,
        locator: Any,
        resolved_selector: str | None,
        resolved_frame_path: tuple[int, ...] | None,
        fill_fields: tuple[dict[str, object], ...],
        coordinate_target: tuple[float, float] | None,
        timeout: int,
        effective_command: BrowserPageActionCommand,
    ) -> tuple[Any, str | None, tuple[int, ...] | None] | None:
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
            return self._execute_fill_action(
                plan=plan,
                tab=tab,
                page=page,
                runtime_state=runtime_state,
                command=command,
                locator=locator,
                resolved_selector=resolved_selector,
                resolved_frame_path=resolved_frame_path,
                fill_fields=fill_fields,
                timeout=timeout,
            )

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

        return None

    def _execute_fill_action(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page: Any,
        runtime_state: BrowserProfileRuntimeState,
        command: BrowserPageActionCommand,
        locator: Any,
        resolved_selector: str | None,
        resolved_frame_path: tuple[int, ...] | None,
        fill_fields: tuple[dict[str, object], ...],
        timeout: int,
    ) -> tuple[Any, str | None, tuple[int, ...] | None]:
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
                    value_repr = raw_value if isinstance(raw_value, str) else str(raw_value)
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


__all__ = ["BrowserPagePrimitiveActionMixin"]
