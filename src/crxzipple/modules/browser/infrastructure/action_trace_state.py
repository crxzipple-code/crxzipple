from __future__ import annotations

from typing import Any, Mapping

from .action_trace_payloads import (
    _json_safe_payload,
    _payload_int_any,
    _payload_text_any,
    _trace_error_list,
    _trace_error_message,
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
            "errors": [
                {"source": "storage-snapshot", "message": _trace_error_message(exc)}
            ],
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
        return {
            "errors": [
                {"source": "lifecycle-snapshot", "message": "invalid lifecycle payload"}
            ]
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "errors": [
                {"source": "lifecycle-snapshot", "message": _trace_error_message(exc)}
            ],
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
        "focused": value.get("focused")
        if isinstance(value.get("focused"), bool)
        else None,
        "history_length": _payload_int_any(value, "history_length", minimum=0),
        "online": value.get("online")
        if isinstance(value.get("online"), bool)
        else None,
    }
