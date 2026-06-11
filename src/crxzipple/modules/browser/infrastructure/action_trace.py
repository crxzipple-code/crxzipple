from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import re
import time
from typing import Any, Mapping

from crxzipple.modules.browser.domain import (
    BrowserActionTarget,
    BrowserExecutionPlan,
    BrowserPageActionCommand,
    BrowserProfileRuntimeState,
    BrowserTab,
    BrowserValidationError,
)

ActionTraceSnapshot = Callable[[BrowserPageActionCommand], Mapping[str, Any]]
ActionTraceNetworkAction = Callable[[BrowserPageActionCommand], Mapping[str, Any]]
ActionTraceInnerExecutor = Callable[
    [BrowserPageActionCommand, int],
    tuple[Any, str | None, tuple[int, ...] | None],
]
ActionTraceMessageReader = Callable[[int], list[dict[str, Any]]]

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
_TRACE_STORAGE_SNAPSHOT_EXPRESSION = """
/*__crxzipple_action_trace_storage_snapshot__*/
() => {
  const summarize = (store) => {
    const keys = [];
    try {
      for (let index = 0; index < store.length && keys.length < 200; index += 1) {
        const key = store.key(index);
        if (key) keys.push(String(key));
      }
      return { count: store.length, keys };
    } catch (error) {
      return {
        count: null,
        keys: [],
        error: error && error.message ? String(error.message) : String(error),
      };
    }
  };
  return {
    local: summarize(window.localStorage),
    session: summarize(window.sessionStorage),
  };
}
""".strip()
_TRACE_LIFECYCLE_SNAPSHOT_EXPRESSION = """
/*__crxzipple_action_trace_lifecycle_snapshot__*/
() => ({
  url: String(window.location.href || ""),
  title: String(document.title || ""),
  ready_state: String(document.readyState || ""),
  visibility_state: String(document.visibilityState || ""),
  focused: Boolean(document.hasFocus && document.hasFocus()),
  history_length: Number.isFinite(Number(history.length)) ? Number(history.length) : null,
  online: Boolean(navigator.onLine),
})
""".strip()


@dataclass(slots=True)
class BrowserActionTraceService:
    def execute(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page: Any,
        runtime_state: BrowserProfileRuntimeState,
        command: BrowserPageActionCommand,
        batch_depth: int,
        snapshot: ActionTraceSnapshot,
        network_action: ActionTraceNetworkAction,
        execute_inner: ActionTraceInnerExecutor,
        console_messages: ActionTraceMessageReader,
        page_errors: ActionTraceMessageReader,
    ) -> dict[str, Any]:
        del runtime_state
        trace_id = _payload_text_any(command.payload, "trace_id", "traceId") or (
            f"trace-{tab.target_id}-{time.time_ns()}"
        )
        action_command = _action_trace_inner_command(command=command, tab=tab)
        snapshot_payload = _action_trace_snapshot_payload(
            command.payload,
            action_ref=action_command.target.ref,
        )
        include_network = _payload_bool_any(
            command.payload,
            "include_network",
            "includeNetwork",
        )
        if include_network is None:
            include_network = True
        include_storage_diff = _payload_bool_any(
            command.payload,
            "include_storage_diff",
            "includeStorageDiff",
        )
        if include_storage_diff is None:
            include_storage_diff = True
        include_lifecycle_diff = _payload_bool_any(
            command.payload,
            "include_lifecycle_diff",
            "includeLifecycleDiff",
        )
        if include_lifecycle_diff is None:
            include_lifecycle_diff = True
        console_limit = _payload_int_any(
            command.payload,
            "console_limit",
            "consoleLimit",
            minimum=1,
        ) or 50
        page_error_limit = _payload_int_any(
            command.payload,
            "page_error_limit",
            "pageErrorLimit",
            minimum=1,
        ) or 50

        before_snapshot = _snapshot_result(
            snapshot(
                _action_trace_snapshot_command(
                    command=command,
                    tab=tab,
                    payload=snapshot_payload,
                )
            ),
        )
        console_before = console_messages(console_limit)
        page_errors_before = page_errors(page_error_limit)
        storage_before = _trace_storage_snapshot(page) if include_storage_diff else None
        lifecycle_before = (
            _trace_lifecycle_snapshot(page)
            if include_lifecycle_diff
            else None
        )

        network_start: dict[str, Any] | None = None
        network_stop: dict[str, Any] | None = None
        network_list: dict[str, Any] | None = None
        capture_id: str | None = None
        trace_errors: list[dict[str, str]] = []
        if include_network:
            capture_id = _payload_text_any(command.payload, "capture_id", "captureId")
            if capture_id is None:
                capture_id = _trace_capture_id(trace_id)
            try:
                network_start = _mapping_result(
                    network_action(
                        BrowserPageActionCommand(
                            profile_name=command.profile_name,
                            kind="network-start-capture",
                            target=BrowserActionTarget(target_id=tab.target_id),
                            payload={
                                "capture_id": capture_id,
                                "max_requests": _payload_int_any(
                                    command.payload,
                                    "max_requests",
                                    "maxRequests",
                                    minimum=1,
                                )
                                or 200,
                                "max_body_bytes": _payload_int_any(
                                    command.payload,
                                    "max_body_bytes",
                                    "maxBodyBytes",
                                    minimum=0,
                                )
                                or 262_144,
                                "metadata": {
                                    "source": "browser.action_trace",
                                    "trace_id": trace_id,
                                    "action_kind": action_command.kind,
                                    "action_target": {
                                        "target_id": action_command.target.target_id,
                                        "ref": action_command.target.ref,
                                        "selector": action_command.target.selector,
                                    },
                                },
                            },
                            timeout_ms=command.timeout_ms,
                        )
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                trace_errors.append(
                    {
                        "source": "network-start-capture",
                        "message": _trace_error_message(exc),
                    }
                )
                capture_id = None

        action_result: Any | None = None
        action_selector: str | None = None
        action_frame_path: tuple[int, ...] | None = None
        action_error: dict[str, str] | None = None
        try:
            action_result, action_selector, action_frame_path = execute_inner(
                action_command,
                batch_depth + 1,
            )
        except Exception as exc:  # noqa: BLE001
            action_error = {
                "type": exc.__class__.__name__,
                "message": _trace_error_message(exc),
            }

        stabilize_ms = _payload_int_any(
            command.payload,
            "stabilize_ms",
            "stabilizeMs",
            minimum=0,
        )
        if stabilize_ms is None:
            stabilize_ms = 200
        if stabilize_ms:
            try:
                page.wait_for_timeout(float(stabilize_ms))
            except Exception as exc:  # noqa: BLE001
                trace_errors.append(
                    {
                        "source": "stabilize",
                        "message": _trace_error_message(exc),
                    }
                )

        if include_network and capture_id is not None:
            try:
                network_stop = _mapping_result(
                    network_action(
                        BrowserPageActionCommand(
                            profile_name=command.profile_name,
                            kind="network-stop-capture",
                            target=BrowserActionTarget(target_id=tab.target_id),
                            payload={"capture_id": capture_id},
                            timeout_ms=command.timeout_ms,
                        )
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                trace_errors.append(
                    {
                        "source": "network-stop-capture",
                        "message": _trace_error_message(exc),
                    }
                )
            try:
                network_list = _mapping_result(
                    network_action(
                        BrowserPageActionCommand(
                            profile_name=command.profile_name,
                            kind="network-list-requests",
                            target=BrowserActionTarget(target_id=tab.target_id),
                            payload={
                                "capture_id": capture_id,
                                "limit": _payload_int_any(
                                    command.payload,
                                    "network_limit",
                                    "networkLimit",
                                    minimum=1,
                                )
                                or 50,
                            },
                            timeout_ms=command.timeout_ms,
                        )
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                trace_errors.append(
                    {
                        "source": "network-list-requests",
                        "message": _trace_error_message(exc),
                    }
                )

        after_snapshot = _snapshot_result(
            snapshot(
                _action_trace_snapshot_command(
                    command=command,
                    tab=tab,
                    payload=snapshot_payload,
                )
            ),
        )
        console_after = console_messages(console_limit)
        page_errors_after = page_errors(page_error_limit)
        storage_after = _trace_storage_snapshot(page) if include_storage_diff else None
        lifecycle_after = (
            _trace_lifecycle_snapshot(page)
            if include_lifecycle_diff
            else None
        )

        diff = _trace_snapshot_diff(before_snapshot, after_snapshot)
        console_delta = _trace_delta_items(console_before, console_after)
        page_error_delta = _trace_delta_items(page_errors_before, page_errors_after)
        storage_delta = (
            _trace_storage_delta(storage_before, storage_after)
            if storage_before is not None or storage_after is not None
            else None
        )
        lifecycle_delta = (
            _trace_lifecycle_delta(lifecycle_before, lifecycle_after)
            if lifecycle_before is not None or lifecycle_after is not None
            else None
        )
        network_payload = _trace_network_payload(
            capture_id=capture_id,
            start=network_start,
            stop=network_stop,
            listed=network_list,
        )
        recommendation = _trace_recommendation(
            action_error=action_error,
            diff=diff,
            network=network_payload,
            console_delta=console_delta,
            page_error_delta=page_error_delta,
            storage_delta=storage_delta,
            lifecycle_delta=lifecycle_delta,
        )
        return {
            "kind": "action-trace",
            "trace_id": trace_id,
            "profile_name": plan.profile.name,
            "target_id": tab.target_id,
            "action": {
                "kind": action_command.kind,
                "target": {
                    "target_id": action_command.target.target_id,
                    "ref": action_command.target.ref,
                    "selector": action_command.target.selector,
                },
                "payload": dict(action_command.payload),
                "ok": action_error is None,
                "error": action_error,
                "resolved_selector": action_selector,
                "frame_path": _serialize_frame_path(action_frame_path),
                "result": _json_safe_payload(action_result),
            },
            "before": _trace_snapshot_payload(before_snapshot),
            "after": _trace_snapshot_payload(after_snapshot),
            "diff": diff,
            "console": {
                "before_count": len(console_before),
                "after_count": len(console_after),
                "new": console_delta,
            },
            "page_errors": {
                "before_count": len(page_errors_before),
                "after_count": len(page_errors_after),
                "new": page_error_delta,
            },
            "network": network_payload,
            "storage": storage_delta,
            "lifecycle": lifecycle_delta,
            "recommendation": recommendation,
            "action_envelope": _trace_action_envelope(
                action_command=action_command,
                action_error=action_error,
                diff=diff,
                network=network_payload,
                console_delta=console_delta,
                page_error_delta=page_error_delta,
                storage_delta=storage_delta,
                lifecycle_delta=lifecycle_delta,
                recommendation=recommendation,
            ),
            "stabilize_ms": stabilize_ms,
            "errors": trace_errors,
        }


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
            ref_ordinal
            if ref_ordinal > _TRACE_DEFAULT_INTERACTIVE_REF_LIMIT
            else None
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


def _snapshot_result(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise BrowserValidationError("Browser action trace snapshot returned an invalid result.")
    return dict(value)


def _mapping_result(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise BrowserValidationError("Browser action trace callback returned an invalid result.")
    return dict(value)


def _trace_capture_id(trace_id: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_.:-]+", "-", trace_id).strip("-")
    if not normalized:
        normalized = hashlib.sha1(trace_id.encode("utf-8")).hexdigest()[:12]
    return f"{normalized}-network"


def _trace_error_message(exc: Exception) -> str:
    message = " ".join(str(exc).split())
    if not message:
        message = exc.__class__.__name__
    if len(message) > 500:
        return f"{message[:497].rstrip()}..."
    return message


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
    return repr(sorted(safe_item.items())) if isinstance(safe_item, dict) else repr(safe_item)


def _trace_storage_snapshot(page: Any) -> dict[str, Any]:
    try:
        raw_snapshot = page.evaluate(_TRACE_STORAGE_SNAPSHOT_EXPRESSION)
        snapshot = _json_safe_payload(raw_snapshot)
        if not isinstance(snapshot, dict):
            snapshot = {}
        return {
            "local": _trace_storage_bucket(snapshot.get("local")),
            "session": _trace_storage_bucket(snapshot.get("session")),
            "errors": _trace_error_list(snapshot.get("errors")),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "local": _trace_storage_bucket(None),
            "session": _trace_storage_bucket(None),
            "errors": [{"source": "storage-snapshot", "message": _trace_error_message(exc)}],
        }


def _trace_storage_bucket(value: Any) -> dict[str, Any]:
    payload = value if isinstance(value, Mapping) else {}
    raw_keys = payload.get("keys")
    keys = sorted(
        {
            key
            for key in (
                _payload_text_any({"value": item}, "value")
                for item in (raw_keys if isinstance(raw_keys, list | tuple) else [])
            )
            if key is not None
        }
    )
    count = _payload_int_any(payload, "count", minimum=0)
    error = _payload_text_any(payload, "error")
    out: dict[str, Any] = {
        "count": count if count is not None else len(keys),
        "keys": keys,
    }
    if error is not None:
        out["error"] = error
    return out


def _trace_storage_delta(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
) -> dict[str, Any]:
    before_payload = before if isinstance(before, Mapping) else {}
    after_payload = after if isinstance(after, Mapping) else {}
    local = _trace_storage_bucket_delta(
        before_payload.get("local"),
        after_payload.get("local"),
    )
    session = _trace_storage_bucket_delta(
        before_payload.get("session"),
        after_payload.get("session"),
    )
    errors = [
        *_trace_error_list(before_payload.get("errors")),
        *_trace_error_list(after_payload.get("errors")),
    ]
    return {
        "changed": bool(local["changed"] or session["changed"]),
        "local": local,
        "session": session,
        "errors": errors,
    }


def _trace_storage_bucket_delta(before: Any, after: Any) -> dict[str, Any]:
    before_bucket = _trace_storage_bucket(before)
    after_bucket = _trace_storage_bucket(after)
    before_keys = set(before_bucket["keys"])
    after_keys = set(after_bucket["keys"])
    before_count = _payload_int_any(before_bucket, "count", minimum=0) or 0
    after_count = _payload_int_any(after_bucket, "count", minimum=0) or 0
    added = sorted(after_keys - before_keys)
    removed = sorted(before_keys - after_keys)
    count_delta = after_count - before_count
    return {
        "changed": bool(added or removed or count_delta),
        "before_count": before_count,
        "after_count": after_count,
        "count_delta": count_delta,
        "added_keys": added[:50],
        "removed_keys": removed[:50],
        "truncated": len(added) > 50 or len(removed) > 50,
    }


def _trace_lifecycle_snapshot(page: Any) -> dict[str, Any]:
    try:
        raw_snapshot = page.evaluate(_TRACE_LIFECYCLE_SNAPSHOT_EXPRESSION)
        snapshot = _json_safe_payload(raw_snapshot)
        if isinstance(snapshot, dict):
            return snapshot
        return {"errors": [{"source": "lifecycle-snapshot", "message": "invalid lifecycle payload"}]}
    except Exception as exc:  # noqa: BLE001
        return {
            "errors": [{"source": "lifecycle-snapshot", "message": _trace_error_message(exc)}],
        }


def _trace_lifecycle_delta(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
) -> dict[str, Any]:
    before_payload = before if isinstance(before, Mapping) else {}
    after_payload = after if isinstance(after, Mapping) else {}
    fields = (
        "url",
        "title",
        "ready_state",
        "visibility_state",
        "focused",
        "history_length",
        "online",
    )
    changed_fields: dict[str, dict[str, Any]] = {}
    for field_name in fields:
        before_value = before_payload.get(field_name)
        after_value = after_payload.get(field_name)
        if before_value == after_value:
            continue
        changed_fields[field_name] = {
            "before": _json_safe_payload(before_value),
            "after": _json_safe_payload(after_value),
        }
    errors = [
        *_trace_error_list(before_payload.get("errors")),
        *_trace_error_list(after_payload.get("errors")),
    ]
    return {
        "changed": bool(changed_fields),
        "before": _trace_lifecycle_payload(before_payload),
        "after": _trace_lifecycle_payload(after_payload),
        "changed_fields": changed_fields,
        "errors": errors,
    }


def _trace_lifecycle_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "url": _payload_text_any(value, "url"),
        "title": _payload_text_any(value, "title"),
        "ready_state": _payload_text_any(value, "ready_state"),
        "visibility_state": _payload_text_any(value, "visibility_state"),
        "focused": value.get("focused") if isinstance(value.get("focused"), bool) else None,
        "history_length": _payload_int_any(value, "history_length", minimum=0),
        "online": value.get("online") if isinstance(value.get("online"), bool) else None,
    }


def _trace_network_payload(
    *,
    capture_id: str | None,
    start: Mapping[str, Any] | None,
    stop: Mapping[str, Any] | None,
    listed: Mapping[str, Any] | None,
) -> dict[str, Any]:
    requests = listed.get("requests") if isinstance(listed, Mapping) else None
    if not isinstance(requests, list):
        requests = []
    serialized_requests = [
        _trace_network_request_payload(item)
        for item in requests
        if isinstance(item, Mapping)
    ]
    start_errors = start.get("errors") if isinstance(start, Mapping) else []
    stop_errors = stop.get("errors") if isinstance(stop, Mapping) else []
    listed_errors = listed.get("errors") if isinstance(listed, Mapping) else []
    return {
        "capture_id": capture_id,
        "started": start is not None,
        "stopped": stop is not None,
        "request_count": len(serialized_requests),
        "requests": serialized_requests,
        "causality": _trace_network_causality(serialized_requests),
        "errors": [
            *_trace_error_list(start_errors),
            *_trace_error_list(stop_errors),
            *_trace_error_list(listed_errors),
        ],
    }


def _trace_error_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        _json_safe_payload(item)
        for item in value
        if isinstance(item, Mapping)
    ]


def _trace_network_request_payload(request: Mapping[str, Any]) -> dict[str, Any]:
    payload = _json_safe_payload(request)
    if not isinstance(payload, dict):
        payload = dict(request)
    payload["initiator_summary"] = _trace_request_initiator_summary(payload)
    return payload


def _trace_request_initiator_summary(request: Mapping[str, Any]) -> dict[str, Any]:
    initiator = request.get("initiator")
    if not isinstance(initiator, Mapping):
        return {"type": None, "source": "unknown"}
    initiator_type = _payload_text_any(initiator, "type")
    frame = _trace_first_initiator_call_frame(initiator)
    summary: dict[str, Any] = {
        "type": initiator_type,
        "source": "cdp-initiator",
    }
    if frame is not None:
        function_name = _payload_text_any(frame, "functionName", "function_name")
        script_url = _payload_text_any(frame, "url")
        summary.update(
            {
                "function_name": function_name,
                "script_url": script_url,
                "line_number": _trace_one_based_number(frame.get("lineNumber")),
                "column_number": _trace_one_based_number(frame.get("columnNumber")),
            }
        )
    else:
        summary.update(
            {
                "script_url": _payload_text_any(initiator, "url"),
                "line_number": _trace_one_based_number(initiator.get("lineNumber")),
                "column_number": _trace_one_based_number(initiator.get("columnNumber")),
            }
        )
    summary["has_stack"] = frame is not None
    summary["has_async_parent"] = any(
        key in initiator for key in ("parent", "parentId", "asyncStackTrace")
    )
    return summary


def _trace_first_initiator_call_frame(
    initiator: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    stack = initiator.get("stack")
    while isinstance(stack, Mapping):
        call_frames = stack.get("callFrames")
        if isinstance(call_frames, list):
            for frame in call_frames:
                if isinstance(frame, Mapping):
                    return frame
        stack = stack.get("parent")
    return None


def _trace_one_based_number(value: Any) -> int | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return None
    if numeric < 0:
        return None
    return numeric + 1


def _trace_network_causality(requests: list[dict[str, Any]]) -> dict[str, Any]:
    initiator_counts: dict[str, int] = {}
    script_frames: list[dict[str, Any]] = []
    api_candidates: list[dict[str, Any]] = []
    for request in requests:
        initiator_summary = request.get("initiator_summary")
        initiator_summary = (
            initiator_summary if isinstance(initiator_summary, Mapping) else {}
        )
        initiator_type = _payload_text_any(initiator_summary, "type") or "unknown"
        initiator_counts[initiator_type] = initiator_counts.get(initiator_type, 0) + 1
        script_url = _payload_text_any(initiator_summary, "script_url")
        if script_url is not None:
            frame = {
                "script_url": script_url,
                "function_name": _payload_text_any(
                    initiator_summary,
                    "function_name",
                ),
                "line_number": initiator_summary.get("line_number"),
                "column_number": initiator_summary.get("column_number"),
                "request_id": _payload_text_any(request, "request_id"),
                "url": _payload_text_any(request, "url"),
            }
            if frame not in script_frames:
                script_frames.append(frame)
        resource_type = (_payload_text_any(request, "resource_type") or "").lower()
        if resource_type in {"xhr", "fetch"} or initiator_type == "script":
            api_candidates.append(
                {
                    "request_id": _payload_text_any(request, "request_id"),
                    "method": _payload_text_any(request, "method"),
                    "url": _payload_text_any(request, "url"),
                    "status": request.get("status"),
                    "resource_type": resource_type or None,
                    "initiator": dict(initiator_summary),
                }
            )
    return {
        "initiator_counts": dict(sorted(initiator_counts.items())),
        "script_request_count": len(
            [request for request in requests if (
                isinstance(request.get("initiator_summary"), Mapping)
                and _payload_text_any(request["initiator_summary"], "script_url") is not None
            )]
        ),
        "script_frames": script_frames[:10],
        "api_candidates": api_candidates[:10],
    }


def _trace_recommendation(
    *,
    action_error: Mapping[str, Any] | None,
    diff: Mapping[str, Any],
    network: Mapping[str, Any],
    console_delta: list[dict[str, Any]],
    page_error_delta: list[dict[str, Any]],
    storage_delta: Mapping[str, Any] | None = None,
    lifecycle_delta: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if action_error is not None and _trace_has_observable_effect(
        action_error=action_error,
        diff=diff,
        network=network,
        console_delta=console_delta,
        page_error_delta=page_error_delta,
        storage_delta=storage_delta,
        lifecycle_delta=lifecycle_delta,
    ):
        return {
            "next_action": "continue-from-after-snapshot",
            "reason": (
                "The wrapped page action reported failure, but page state changed. "
                "Treat the after snapshot and lifecycle delta as the current "
                "browser state before deciding the next step."
            ),
        }
    if action_error is not None:
        return {
            "next_action": "inspect-target",
            "reason": (
                "The wrapped page action failed. Inspect clickability, selector/ref "
                "freshness, or overlay state before retrying."
            ),
        }
    if page_error_delta:
        return {
            "next_action": "inspect-page-errors",
            "reason": "The action produced new page errors.",
        }
    request_count = _payload_int_any(network, "request_count", minimum=0) or 0
    if request_count > 0:
        causality = network.get("causality")
        script_frames = (
            causality.get("script_frames")
            if isinstance(causality, Mapping)
            else None
        )
        if isinstance(script_frames, list) and script_frames:
            return {
                "next_action": "inspect-script-initiator",
                "reason": (
                    "The action produced network activity with a script initiator. "
                    "Inspect the initiating script or replay the candidate request."
                ),
            }
        return {
            "next_action": "inspect-network-delta",
            "reason": "The action produced browser network activity that may reveal an API path.",
        }
    if lifecycle_delta is not None and bool(lifecycle_delta.get("changed")):
        return {
            "next_action": "inspect-page-lifecycle",
            "reason": "The action changed page lifecycle state such as URL, title, readiness, or focus.",
        }
    if storage_delta is not None and bool(storage_delta.get("changed")):
        return {
            "next_action": "inspect-storage-delta",
            "reason": "The action changed browser storage keys without visible network activity.",
        }
    if bool(diff.get("snapshot_changed")):
        return {
            "next_action": "continue-from-after-snapshot",
            "reason": "The visible interaction snapshot changed after the action.",
        }
    if console_delta:
        return {
            "next_action": "inspect-console-delta",
            "reason": "The action produced new console output without a visible snapshot change.",
        }
    return {
        "next_action": "observe-or-inspect-clickability",
        "reason": (
            "The action completed but no visible snapshot or network change was detected."
        ),
    }


def _trace_action_envelope(
    *,
    action_command: BrowserPageActionCommand,
    action_error: Mapping[str, Any] | None,
    diff: Mapping[str, Any],
    network: Mapping[str, Any],
    console_delta: list[dict[str, Any]],
    page_error_delta: list[dict[str, Any]],
    storage_delta: Mapping[str, Any] | None,
    lifecycle_delta: Mapping[str, Any] | None,
    recommendation: Mapping[str, Any],
) -> dict[str, Any]:
    tool_ok = action_error is None
    observed_effect = _trace_has_observable_effect(
        action_error=action_error,
        diff=diff,
        network=network,
        console_delta=console_delta,
        page_error_delta=page_error_delta,
        storage_delta=storage_delta,
        lifecycle_delta=lifecycle_delta,
    )
    page_effect_ok = observed_effect
    lifecycle_payload = lifecycle_delta if isinstance(lifecycle_delta, Mapping) else {}
    before = lifecycle_payload.get("before")
    after = lifecycle_payload.get("after")
    return {
        "kind": action_command.kind,
        "tool_ok": tool_ok,
        "page_effect_ok": page_effect_ok,
        "page_effect_status": (
            "action_failed_with_observed_effect"
            if not tool_ok and observed_effect
            else "action_failed"
            if not tool_ok
            else "observed_change"
            if page_effect_ok
            else "no_observable_change"
        ),
        "before": _trace_envelope_state(before),
        "after": _trace_envelope_state(after),
        "changes": _trace_envelope_changes(
            diff=diff,
            network=network,
            console_delta=console_delta,
            page_error_delta=page_error_delta,
            storage_delta=storage_delta,
            lifecycle_delta=lifecycle_delta,
        ),
        "result": {
            "recommendation": _json_safe_payload(recommendation),
        },
        "next_action": _payload_text_any(recommendation, "next_action"),
        "errors": [dict(action_error)] if isinstance(action_error, Mapping) else [],
    }


def _trace_has_observable_effect(
    *,
    action_error: Mapping[str, Any] | None,
    diff: Mapping[str, Any],
    network: Mapping[str, Any],
    console_delta: list[dict[str, Any]],
    page_error_delta: list[dict[str, Any]],
    storage_delta: Mapping[str, Any] | None,
    lifecycle_delta: Mapping[str, Any] | None,
) -> bool:
    request_count = _payload_int_any(network, "request_count", minimum=0) or 0
    network_changed = request_count > 0
    if action_error is not None and _trace_action_error_prevented_page_action(
        action_error,
    ):
        network_changed = False
    return bool(
        diff.get("snapshot_changed")
        or network_changed
        or console_delta
        or page_error_delta
        or (isinstance(storage_delta, Mapping) and storage_delta.get("changed"))
        or (isinstance(lifecycle_delta, Mapping) and lifecycle_delta.get("changed"))
    )


def _trace_action_error_prevented_page_action(action_error: Mapping[str, Any]) -> bool:
    message = (_payload_text_any(action_error, "message") or "").lower()
    if not message:
        return False
    return (
        "strict mode violation" in message
        or ("resolved to " in message and " elements" in message)
        or (
            "browser ref" in message
            and (
                "was not found" in message
                or "is stale" in message
                or "does not expose a supported locator" in message
                or "frame path" in message
                or "requires nth" in message
            )
        )
    )


def _trace_envelope_state(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {
        key: _json_safe_payload(value.get(key))
        for key in (
            "url",
            "title",
            "ready_state",
            "visibility_state",
            "focused",
            "history_length",
            "online",
        )
        if value.get(key) is not None
    }


def _trace_envelope_changes(
    *,
    diff: Mapping[str, Any],
    network: Mapping[str, Any],
    console_delta: list[dict[str, Any]],
    page_error_delta: list[dict[str, Any]],
    storage_delta: Mapping[str, Any] | None,
    lifecycle_delta: Mapping[str, Any] | None,
) -> dict[str, Any]:
    changes: dict[str, Any] = {
        "snapshot_changed": bool(diff.get("snapshot_changed")),
        "ref_count_delta": diff.get("ref_count_delta"),
        "network_request_count": _payload_int_any(
            network,
            "request_count",
            minimum=0,
        )
        or 0,
        "console_new_count": len(console_delta),
        "page_error_new_count": len(page_error_delta),
    }
    if isinstance(storage_delta, Mapping):
        changes["storage_changed"] = bool(storage_delta.get("changed"))
    if isinstance(lifecycle_delta, Mapping):
        changed_fields = lifecycle_delta.get("changed_fields")
        if isinstance(changed_fields, Mapping):
            changes["lifecycle_changed_fields"] = dict(changed_fields)
        changes["lifecycle_changed"] = bool(lifecycle_delta.get("changed"))
    return changes


def _serialize_frame_path(frame_path: tuple[int, ...] | None) -> list[int] | None:
    if frame_path is None:
        return None
    return list(frame_path)


def _bounded_text(value: str, *, limit: int) -> str:
    normalized = value.strip()
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3].rstrip()}..."


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


def _json_safe_payload(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_payload(item) for item in value]
    return str(value)
