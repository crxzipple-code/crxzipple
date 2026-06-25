from __future__ import annotations

import calendar
import re
from typing import Any, Mapping

from crxzipple.modules.browser.domain import (
    BrowserActionTarget,
    BrowserExecutionPlan,
    BrowserPageActionCommand,
    BrowserProfileRuntimeState,
    BrowserTab,
    BrowserValidationError,
)
from crxzipple.modules.browser.domain.value_objects import _normalize_optional_text

from .action_engine_locators import (
    _active_overlay,
    _allows_implicit_selector_ordinal,
    _locator_exact,
    _locator_ordinal,
    _scope_ref_id,
    _scope_selector,
    _stored_ref_name,
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
from .action_engine_snapshots import _main_frame, _resolve_frame_context
from .role_snapshot import describe_role_locator


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
