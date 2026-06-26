from __future__ import annotations

from typing import Any, Mapping

from crxzipple.modules.browser.domain import (
    BrowserExecutionPlan,
    BrowserPageActionCommand,
    BrowserProfileRuntimeState,
    BrowserTab,
    BrowserValidationError,
)
from crxzipple.modules.browser.domain.value_objects import _normalize_optional_text

from .action_engine_locators import (
    _locator_exact,
    _locator_ordinal,
)
from .action_engine_payloads import (
    _is_pointer_interception_error,
    _payload_bool_any,
    _payload_number_any,
    _payload_text_any,
    _probe_timeout,
    _timeout_kwargs,
)
from .action_engine_scripts import _TARGET_INFO_EXPRESSION
from .action_engine_snapshots import _main_frame


class BrowserInteractionPrimitivesMixin:
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
