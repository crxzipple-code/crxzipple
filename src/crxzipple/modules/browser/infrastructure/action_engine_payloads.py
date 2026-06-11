"""Payload and result helpers for the browser action engine."""

from __future__ import annotations

from typing import Any, Mapping

from crxzipple.modules.browser.domain import (
    BrowserActionTarget,
    BrowserPageActionCommand,
    BrowserTab,
    BrowserValidationError,
)
from crxzipple.modules.browser.domain.value_objects import _normalize_optional_text

from .cdp_sessions import BrowserCdpSessionBroker
from .script_insight import SCRIPT_INSIGHT_KINDS

_LOCATOR_ACTION_KINDS = frozenset(
    {
        "click",
        "type",
        "press",
        "hover",
        "drag",
        "scroll-into-view",
        "select",
        "fill",
        "upload",
        "download",
    }
)
_SUPPORTED_KINDS = frozenset(
    _LOCATOR_ACTION_KINDS
    | {
        "batch",
        "console",
        "cookies",
        "dialog",
        "wait-download",
        "resize",
        "wait",
        "snapshot",
        "screenshot",
        "pdf",
        "evaluate",
        "storage",
        "storage-indexeddb-list",
        "storage-indexeddb-get",
        "storage-indexeddb-query",
        "storage-cache-list",
        "storage-cache-get",
        "service-worker-list",
        "service-worker-inspect",
        "dom-inspect",
        "dom-box-model",
        "dom-computed-style",
        "dom-clickability",
        "dom-highlight",
        "dom-mutation-wait",
        "emulation-set",
        "emulation-reset",
        "permissions-grant",
        "permissions-clear",
        "geolocation-set",
        "network-conditions-set",
        "diagnostics-collect",
        "performance-metrics",
        "trace-start",
        "trace-stop",
        "trace-export",
        "page-lifecycle",
        "page-errors",
        "network-inspect",
        "network-start-capture",
        "network-stop-capture",
        "network-list-requests",
        "network-get-request",
        "network-get-response-body",
        "network-get-request-body",
        "network-fetch-as-page",
        "network-replay-request",
        "network-clear-capture",
        "action-trace",
        "cdp-raw",
    }
    | SCRIPT_INSIGHT_KINDS
)
_MAX_BATCH_ACTIONS = 100
_MAX_BATCH_DEPTH = 5
_RETRYABLE_TRANSIENT_ACTION_KINDS = frozenset(
    {
        "click",
        "type",
        "fill",
        "press",
        "hover",
        "scroll-into-view",
        "select",
        "download",
        "wait",
        "snapshot",
        "evaluate",
    }
)
_ACTION_EFFECT_KINDS = frozenset(
    {
        "click",
        "type",
        "fill",
        "select",
        "press",
        "evaluate",
        "hover",
        "scroll-into-view",
    }
)


def _timeout_ms(command: BrowserPageActionCommand) -> float | None:
    if command.timeout_ms is None:
        return None
    return float(command.timeout_ms)


def _timeout_kwargs(timeout: float | None) -> dict[str, float]:
    if timeout is None:
        return {}
    return {"timeout": timeout}


def _probe_timeout(timeout: float | None, *, ceiling_ms: float = 2_000.0) -> float:
    if timeout is None:
        return ceiling_ms
    return min(timeout, ceiling_ms)


def _is_pointer_interception_error(exc: Exception) -> bool:
    message = str(exc).lower()
    markers = (
        "intercepts pointer events",
        "subtree intercepts pointer events",
        "receives pointer events",
        "would receive pointer events",
        "would receive the click",
        "another element",
    )
    return any(marker in message for marker in markers)


def _payload_text(
    payload: Mapping[str, Any],
    *,
    key: str,
    required: bool = True,
) -> str | None:
    value = payload.get(key)
    if value is None:
        if required:
            raise BrowserValidationError(f"payload.{key} is required.")
        return None
    if not isinstance(value, str) or not value.strip():
        if required:
            raise BrowserValidationError(f"payload.{key} is required.")
        return None
    return value.strip()


def _payload_text_any(
    payload: Mapping[str, Any],
    *keys: str,
) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _payload_bool_any(
    payload: Mapping[str, Any],
    *keys: str,
) -> bool | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, bool):
            return value
    return None


def _payload_number_any(
    payload: Mapping[str, Any],
    *keys: str,
) -> float | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _click_coordinates(payload: Mapping[str, Any]) -> tuple[float, float] | None:
    has_x = "x" in payload and payload.get("x") is not None
    has_y = "y" in payload and payload.get("y") is not None
    if not has_x and not has_y:
        return None
    x = _payload_number_any(payload, "x")
    y = _payload_number_any(payload, "y")
    if x is None or y is None:
        raise BrowserValidationError("payload.x and payload.y must both be numbers for coordinate click.")
    return x, y


def _payload_value_any(
    payload: Mapping[str, Any],
    *keys: str,
) -> Any:
    for key in keys:
        if key in payload:
            return payload.get(key)
    return None


def _payload_int_any(
    payload: Mapping[str, Any],
    *keys: str,
    minimum: int = 0,
) -> int | None:
    value = _payload_value_any(payload, *keys)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BrowserValidationError(f"payload.{keys[0]} must be an integer.")
    resolved = int(value)
    if resolved < minimum:
        raise BrowserValidationError(
            f"payload.{keys[0]} must be greater than or equal to {minimum}.",
        )
    return resolved


def _normalize_batch_kind(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BrowserValidationError("batch actions require kind.")
    normalized = value.strip().lower()
    if normalized == "scrollintoview":
        return "scroll-into-view"
    return normalized


def _coerce_batch_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _batch_action_timeout_ms(raw: Mapping[str, Any], inherited_timeout_ms: int | None) -> int | None:
    value = _payload_value_any(raw, "timeout_ms", "timeoutMs")
    if value is None:
        return inherited_timeout_ms
    if isinstance(value, bool):
        raise BrowserValidationError("batch action timeout_ms must be an integer.")
    if not isinstance(value, (int, float)):
        raise BrowserValidationError("batch action timeout_ms must be an integer.")
    resolved = int(value)
    if resolved < 1:
        raise BrowserValidationError("batch action timeout_ms must be greater than or equal to 1.")
    return resolved


def _count_batch_actions(actions: Any) -> int:
    if not isinstance(actions, (list, tuple)):
        return 0
    count = 0
    for raw_action in actions:
        if not isinstance(raw_action, Mapping):
            continue
        count += 1
        if _normalize_batch_kind(raw_action.get("kind")) == "batch":
            count += _count_batch_actions(raw_action.get("actions"))
    return count


def _normalize_batch_action(
    *,
    raw_action: Mapping[str, Any],
    profile_name: str,
    inherited_target_id: str | None,
    inherited_timeout_ms: int | None,
    depth: int,
) -> BrowserPageActionCommand:
    if depth > _MAX_BATCH_DEPTH:
        raise BrowserValidationError(
            f"Batch nesting depth exceeds maximum of {_MAX_BATCH_DEPTH}.",
        )
    kind = _normalize_batch_kind(raw_action.get("kind"))
    if kind not in _SUPPORTED_KINDS:
        raise BrowserValidationError(f"Unsupported batch action kind '{kind}'.")

    target_id = _payload_text_any(raw_action, "target_id", "targetId")
    if inherited_target_id is not None and target_id is not None and target_id != inherited_target_id:
        raise BrowserValidationError("batched action target_id must match request target_id.")
    effective_target_id = target_id or inherited_target_id
    payload = _coerce_batch_payload(raw_action.get("payload"))

    if kind == "batch":
        nested_actions = raw_action.get("actions")
        if not isinstance(nested_actions, (list, tuple)) or not nested_actions:
            raise BrowserValidationError("batch requires actions.")
        payload.setdefault("actions", list(nested_actions))
        stop_on_error = _payload_value_any(raw_action, "stop_on_error", "stopOnError")
        if isinstance(stop_on_error, bool):
            payload.setdefault("stop_on_error", stop_on_error)
        return BrowserPageActionCommand(
            profile_name=profile_name,
            kind="batch",
            target=BrowserActionTarget(target_id=effective_target_id),
            payload=payload,
            timeout_ms=_batch_action_timeout_ms(raw_action, inherited_timeout_ms),
        )

    ref = _payload_text_any(raw_action, "ref")
    selector = _payload_text_any(raw_action, "selector")

    for key, payload_keys in (
        ("text", ("text",)),
        ("date", ("date",)),
        ("query", ("query",)),
        ("command_text", ("command_text", "commandText")),
        ("command_ref", ("command_ref", "commandRef")),
        ("command_selector", ("command_selector", "commandSelector")),
        ("toolbar_ref", ("toolbar_ref", "toolbarRef")),
        ("toolbar_selector", ("toolbar_selector", "toolbarSelector")),
        ("option_text", ("option_text", "optionText")),
        ("option_ref", ("option_ref", "optionRef")),
        ("option_selector", ("option_selector", "optionSelector")),
        ("overlay_selector", ("overlay_selector", "overlaySelector")),
        ("overlay_text", ("overlay_text", "overlayText")),
        ("input_mode", ("input_mode", "inputMode")),
        ("select_via", ("select_via", "selectVia")),
        ("navigate_key", ("navigate_key", "navigateKey")),
        ("confirm_key", ("confirm_key", "confirmKey")),
        ("month_direction", ("month_direction", "monthDirection")),
        ("next_month_ref", ("next_month_ref", "nextMonthRef")),
        ("next_month_selector", ("next_month_selector", "nextMonthSelector")),
        ("prev_month_ref", ("prev_month_ref", "prevMonthRef")),
        ("prev_month_selector", ("prev_month_selector", "prevMonthSelector")),
        ("trigger", ("trigger",)),
        ("key", ("key",)),
        ("button", ("button",)),
        ("value", ("value",)),
        ("expression", ("expression",)),
        ("fn", ("fn",)),
        ("url", ("url",)),
        ("state", ("state",)),
        ("load_state", ("load_state", "loadState")),
        ("text_gone", ("text_gone", "textGone")),
        ("frame_selector", ("frame_selector", "frameSelector")),
        ("refs_mode", ("refs_mode", "refsMode")),
        ("mode", ("mode",)),
        ("type", ("type",)),
        ("start_ref", ("start_ref", "startRef")),
        ("start_selector", ("start_selector", "startSelector")),
        ("end_ref", ("end_ref", "endRef")),
        ("end_selector", ("end_selector", "endSelector")),
        ("target_ref", ("target_ref",)),
        ("target_selector", ("target_selector",)),
        ("scope_ref", ("scope_ref", "scopeRef")),
        ("scope_selector", ("scope_selector", "scopeSelector")),
        ("to_ref", ("to_ref",)),
        ("to_selector", ("to_selector",)),
    ):
        value = _payload_value_any(raw_action, *payload_keys)
        if value is not None:
            payload.setdefault(key, value)

    for key, payload_keys in (
        ("double_click", ("double_click", "doubleClick")),
        ("compact", ("compact",)),
        ("full_page", ("full_page", "fullPage")),
        ("print_background", ("print_background", "printBackground")),
        ("active_overlay", ("active_overlay", "activeOverlay")),
        ("exact", ("exact",)),
        ("clear_existing", ("clear_existing", "clearExisting")),
        ("open_first", ("open_first", "openFirst")),
        ("open_picker", ("open_picker", "openPicker")),
    ):
        value = _payload_value_any(raw_action, *payload_keys)
        if isinstance(value, bool):
            payload.setdefault(key, value)

    for key, payload_keys in (
        ("delay_ms", ("delay_ms", "delayMs")),
        ("time_ms", ("time_ms", "timeMs")),
        ("depth", ("depth",)),
        ("limit", ("limit",)),
        ("width", ("width",)),
        ("height", ("height",)),
        ("option_steps", ("option_steps", "optionSteps")),
        ("advance_months", ("advance_months", "advanceMonths")),
    ):
        value = _payload_value_any(raw_action, *payload_keys)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            payload.setdefault(key, int(value))
    for key in ("x", "y"):
        value = _payload_value_any(raw_action, key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            payload.setdefault(key, float(value))

    if "arg" in raw_action:
        payload.setdefault("arg", raw_action.get("arg"))
    if isinstance(raw_action.get("args"), list):
        payload.setdefault("args", list(raw_action["args"]))
    if isinstance(raw_action.get("values"), (list, tuple)):
        payload.setdefault("values", list(raw_action["values"]))
    if isinstance(raw_action.get("fields"), (list, tuple)):
        payload.setdefault("fields", list(raw_action["fields"]))
    if isinstance(raw_action.get("paths"), (list, tuple)):
        payload.setdefault("paths", list(raw_action["paths"]))
    if isinstance(raw_action.get("path"), str):
        payload.setdefault("path", raw_action["path"])

    return BrowserPageActionCommand(
        profile_name=profile_name,
        kind=kind,
        target=BrowserActionTarget(
            target_id=effective_target_id,
            ref=ref,
            selector=selector,
        ),
        payload=payload,
        timeout_ms=_batch_action_timeout_ms(raw_action, inherited_timeout_ms),
    )


def _drag_source_ref(command: BrowserPageActionCommand) -> str | None:
    return command.target.ref or _payload_text_any(
        command.payload,
        "start_ref",
        "startRef",
    )


def _drag_source_selector(command: BrowserPageActionCommand) -> str | None:
    return command.target.selector or _payload_text_any(
        command.payload,
        "start_selector",
        "startSelector",
    )


def _drag_target_ref(payload: Mapping[str, Any]) -> str | None:
    return _payload_text_any(
        payload,
        "end_ref",
        "endRef",
        "target_ref",
        "to_ref",
    )


def _drag_target_selector(payload: Mapping[str, Any]) -> str | None:
    return _payload_text_any(
        payload,
        "end_selector",
        "endSelector",
        "target_selector",
        "to_selector",
    )


def _json_safe_payload(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_payload(item) for item in value]
    return str(value)


def _capture_action_effect_page_state(page: Any) -> dict[str, Any]:
    state: dict[str, Any] = {}
    url = _normalize_optional_text(getattr(page, "url", None))
    if url is not None:
        state["url"] = url
    title = getattr(page, "title", None)
    if not callable(title):
        normalized_title = _normalize_optional_text(title)
        if normalized_title is not None:
            state["title"] = normalized_title
    return state


def _action_result_envelope(
    *,
    kind: str,
    tool_ok: bool,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    result: Any,
) -> dict[str, Any] | None:
    if before is None and after is None:
        return None
    before_payload = dict(before or {})
    after_payload = dict(after or {})
    changes = _action_effect_changes(before_payload, after_payload)
    page_effect_ok = bool(changes)
    status = "observed_change" if page_effect_ok else "no_observable_change"
    errors = [
        item
        for item in (
            *list(before_payload.get("errors") or ()),
            *list(after_payload.get("errors") or ()),
        )
        if isinstance(item, dict)
    ]
    return {
        "kind": kind,
        "tool_ok": bool(tool_ok),
        "page_effect_ok": page_effect_ok,
        "page_effect_status": status,
        "before": _action_effect_visible_state(before_payload),
        "after": _action_effect_visible_state(after_payload),
        "changes": changes,
        "result": _json_safe_payload(result),
        "next_action": (
            "observe-current-state"
            if page_effect_ok
            else "use-action-trace-or-observe"
        ),
        "errors": errors,
    }


def _action_effect_visible_state(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _json_safe_payload(value.get(key))
        for key in (
            "url",
            "title",
            "ready_state",
            "focused",
            "active_element",
            "validation_errors",
        )
        if value.get(key) is not None
    }


def _action_effect_changes(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    changes: dict[str, dict[str, Any]] = {}
    for key in (
        "url",
        "title",
        "ready_state",
        "focused",
        "active_element",
        "validation_errors",
    ):
        before_value = _json_safe_payload(before.get(key))
        after_value = _json_safe_payload(after.get(key))
        if before_value != after_value:
            changes[key] = {
                "before": before_value,
                "after": after_value,
            }
    return changes


def _action_result_message(
    kind: str,
    *,
    envelope: Mapping[str, Any] | None,
) -> str:
    if envelope is None:
        return f"Executed {kind} via cdp-backed-playwright."
    if envelope.get("page_effect_ok") is True:
        return f"Executed {kind} via cdp-backed-playwright; observed page effect."
    return (
        f"Executed {kind} via cdp-backed-playwright; no observable page effect. "
        "Use browser.action.trace or browser.observe to verify the next step."
    )


def _new_page_cdp_session(page: Any) -> Any:
    return BrowserCdpSessionBroker().open_command_session(page)


def _send_cdp_session_command(
    session: Any,
    method: str,
    params: Mapping[str, Any] | None = None,
) -> Any:
    return BrowserCdpSessionBroker().send_command(session, method, params)


def _detach_cdp_session(session: Any) -> None:
    BrowserCdpSessionBroker().detach(session)


def _serialize_tab(tab: BrowserTab) -> dict[str, Any]:
    return {
        "target_id": tab.target_id,
        "url": tab.url,
        "title": tab.title,
        "type": tab.type,
        "ws_url": tab.ws_url,
        "json_endpoints": dict(tab.json_endpoints) if tab.json_endpoints else None,
    }


def _serialize_frame_path(frame_path: tuple[int, ...] | None) -> list[int] | None:
    if frame_path is None:
        return None
    return list(frame_path)
