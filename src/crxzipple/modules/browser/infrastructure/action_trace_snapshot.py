from __future__ import annotations

import re
from typing import Any, Mapping

from crxzipple.modules.browser.domain import (
    BrowserActionTarget,
    BrowserPageActionCommand,
    BrowserTab,
    BrowserValidationError,
)

from .action_trace_payloads import (
    _bounded_text,
    _json_safe_payload,
    _payload_bool_any,
    _payload_int_any,
    _payload_text_any,
)

_TRACE_DEFAULT_INTERACTIVE_REF_LIMIT = 40

_ACTION_TRACE_INNER_KINDS = frozenset(
    {
        "click",
        "type",
        "press",
        "hover",
        "drag",
        "scroll-into-view",
        "select",
        "fill",
        "wait",
        "evaluate",
        "dom-mutation-wait",
    }
)

_ACTION_TRACE_CONTROL_PAYLOAD_KEYS = frozenset(
    {
        "action",
        "action_kind",
        "actionKind",
        "action_ref",
        "actionRef",
        "action_selector",
        "actionSelector",
        "action_payload",
        "actionPayload",
        "action_timeout_ms",
        "actionTimeoutMs",
        "trace_id",
        "traceId",
        "include_network",
        "includeNetwork",
        "include_storage_diff",
        "includeStorageDiff",
        "include_lifecycle_diff",
        "includeLifecycleDiff",
        "capture_id",
        "captureId",
        "max_requests",
        "maxRequests",
        "max_body_bytes",
        "maxBodyBytes",
        "network_limit",
        "networkLimit",
        "snapshot_format",
        "snapshotFormat",
        "snapshot_mode",
        "snapshotMode",
        "snapshot_limit",
        "snapshotLimit",
        "active_overlay",
        "activeOverlay",
        "console_limit",
        "consoleLimit",
        "page_error_limit",
        "pageErrorLimit",
        "stabilize_ms",
        "stabilizeMs",
    }
)


def _action_trace_snapshot_payload(
    payload: Mapping[str, Any],
    *,
    action_ref: str | None = None,
) -> dict[str, Any]:
    snapshot_payload: dict[str, Any] = {
        "format": _payload_text_any(payload, "snapshot_format", "snapshotFormat")
        or "interactive",
        "mode": _payload_text_any(payload, "snapshot_mode", "snapshotMode")
        or "efficient",
        "compact": True,
    }
    limit = _payload_int_any(payload, "snapshot_limit", "snapshotLimit", minimum=1)
    limit = _trace_snapshot_limit_for_action_ref(
        snapshot_format=str(snapshot_payload["format"]),
        current_limit=limit,
        action_ref=action_ref,
    )
    if limit is not None:
        snapshot_payload["limit"] = limit
    active_overlay = _payload_bool_any(payload, "active_overlay", "activeOverlay")
    if active_overlay is not None:
        snapshot_payload["active_overlay"] = active_overlay
    return snapshot_payload


def _trace_snapshot_limit_for_action_ref(
    *,
    snapshot_format: str,
    current_limit: int | None,
    action_ref: str | None,
) -> int | None:
    if snapshot_format != "interactive":
        return current_limit
    ref_ordinal = _trace_ref_ordinal(action_ref)
    if ref_ordinal is None:
        return current_limit
    if current_limit is None:
        return (
            ref_ordinal if ref_ordinal > _TRACE_DEFAULT_INTERACTIVE_REF_LIMIT else None
        )
    return max(current_limit, ref_ordinal, _TRACE_DEFAULT_INTERACTIVE_REF_LIMIT)


def _trace_ref_ordinal(ref: str | None) -> int | None:
    if ref is None:
        return None
    match = re.fullmatch(r"r([1-9][0-9]*)", ref.strip().lower())
    if match is None:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _action_trace_snapshot_command(
    *,
    command: BrowserPageActionCommand,
    tab: BrowserTab,
    payload: Mapping[str, Any],
) -> BrowserPageActionCommand:
    return BrowserPageActionCommand(
        profile_name=command.profile_name,
        kind="snapshot",
        target=BrowserActionTarget(target_id=tab.target_id),
        payload=payload,
        timeout_ms=command.timeout_ms,
    )


def _action_trace_inner_command(
    *,
    command: BrowserPageActionCommand,
    tab: BrowserTab,
) -> BrowserPageActionCommand:
    action_kind = _payload_text_any(
        command.payload,
        "action_kind",
        "actionKind",
        "action",
    )
    if action_kind is None:
        raise BrowserValidationError("payload.action is required for action-trace.")
    action_kind = action_kind.lower()
    if action_kind not in _ACTION_TRACE_INNER_KINDS:
        supported = ", ".join(sorted(_ACTION_TRACE_INNER_KINDS))
        raise BrowserValidationError(
            f"payload.action must be one of {supported}.",
        )
    action_ref = (
        _payload_text_any(command.payload, "action_ref", "actionRef")
        or command.target.ref
    )
    action_selector = (
        _payload_text_any(command.payload, "action_selector", "actionSelector")
        or command.target.selector
    )
    return BrowserPageActionCommand(
        profile_name=command.profile_name,
        kind=action_kind,
        target=BrowserActionTarget(
            target_id=tab.target_id,
            ref=action_ref,
            selector=action_selector,
        ),
        payload=_trace_action_payload(command.payload),
        timeout_ms=(
            _payload_int_any(
                command.payload,
                "action_timeout_ms",
                "actionTimeoutMs",
                minimum=1,
            )
            or command.timeout_ms
        ),
    )


def _trace_action_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    raw_action_payload = payload.get("action_payload")
    if raw_action_payload is None:
        raw_action_payload = payload.get("actionPayload")
    if isinstance(raw_action_payload, Mapping):
        return dict(raw_action_payload)
    if raw_action_payload is not None:
        raise BrowserValidationError("payload.action_payload must be an object.")
    return {
        str(key): value
        for key, value in payload.items()
        if str(key) not in _ACTION_TRACE_CONTROL_PAYLOAD_KEYS
    }


def _trace_snapshot_payload(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    value = snapshot.get("value")
    snapshot_text = _trace_snapshot_text(snapshot)
    return {
        "kind": snapshot.get("kind"),
        "format": snapshot.get("format"),
        "generation": snapshot.get("generation"),
        "ref_count": snapshot.get("ref_count"),
        "frame_count": snapshot.get("frame_count"),
        "mode": snapshot.get("mode"),
        "compact": snapshot.get("compact"),
        "value": _json_safe_payload(value),
        "snapshot_preview": _bounded_text(snapshot_text, limit=4000)
        if snapshot_text
        else "",
    }


def _trace_snapshot_diff(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> dict[str, Any]:
    before_text = _trace_snapshot_text(before)
    after_text = _trace_snapshot_text(after)
    before_refs = _payload_int_any(before, "ref_count", minimum=0) or 0
    after_refs = _payload_int_any(after, "ref_count", minimum=0) or 0
    before_frames = _payload_int_any(before, "frame_count", minimum=0) or 0
    after_frames = _payload_int_any(after, "frame_count", minimum=0) or 0
    return {
        "snapshot_changed": before_text != after_text,
        "before_chars": len(before_text),
        "after_chars": len(after_text),
        "ref_count_delta": after_refs - before_refs,
        "frame_count_delta": after_frames - before_frames,
    }


def _trace_snapshot_text(snapshot: Mapping[str, Any]) -> str:
    value = snapshot.get("value")
    if isinstance(value, Mapping):
        snapshot_value = value.get("snapshot")
        if isinstance(snapshot_value, str):
            return snapshot_value
        return str(value)
    if isinstance(value, str):
        return value
    return ""


def _trace_delta_items(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    remaining_before: dict[str, int] = {}
    for item in before:
        key = _trace_item_key(item)
        remaining_before[key] = remaining_before.get(key, 0) + 1
    delta: list[dict[str, Any]] = []
    for item in after:
        key = _trace_item_key(item)
        count = remaining_before.get(key, 0)
        if count:
            remaining_before[key] = count - 1
            continue
        delta.append(_json_safe_payload(item))
    return delta


def _trace_item_key(item: Mapping[str, Any]) -> str:
    safe_item = _json_safe_payload(item)
    return (
        repr(sorted(safe_item.items()))
        if isinstance(safe_item, dict)
        else repr(safe_item)
    )


def _serialize_frame_path(frame_path: tuple[int, ...] | None) -> list[int] | None:
    if frame_path is None:
        return None
    return list(frame_path)
