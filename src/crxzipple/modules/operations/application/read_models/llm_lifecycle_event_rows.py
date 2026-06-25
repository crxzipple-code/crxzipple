from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.observation_models import (
    OperationsObservedEvent,
)


def event_transport_label(event: OperationsObservedEvent) -> str:
    payload = event.payload if isinstance(event.payload, dict) else {}
    preview = payload.get("provider_request_payload_preview")
    preview = preview if isinstance(preview, dict) else {}
    return _text(payload.get("transport")) or _text(preview.get("transport")) or "-"


def event_continuation_label(event: OperationsObservedEvent) -> str:
    payload = event.payload if isinstance(event.payload, dict) else {}
    preview = payload.get("provider_request_payload_preview")
    preview = preview if isinstance(preview, dict) else {}
    has_previous = payload.get("has_previous_response_id")
    if not isinstance(has_previous, bool):
        has_previous = preview.get("has_previous_response_id")
    previous_response_id = _text(payload.get("previous_response_id")) or _text(
        preview.get("previous_response_id"),
    )
    if has_previous is True and previous_response_id:
        return f"previous_response_id={previous_response_id}"
    if has_previous is True:
        return "previous_response_id present"
    if has_previous is False:
        return "initial request"
    return "-"


def event_input_delta_label(event: OperationsObservedEvent) -> str:
    payload = event.payload if isinstance(event.payload, dict) else {}
    preview = payload.get("provider_request_payload_preview")
    preview = preview if isinstance(preview, dict) else {}
    delta_mode = payload.get("input_delta_mode")
    if not isinstance(delta_mode, bool):
        delta_mode = preview.get("input_delta_mode")
    baseline = payload.get("input_baseline_count")
    if not isinstance(baseline, int):
        baseline = preview.get("input_baseline_count")
    delta = payload.get("input_delta_count")
    if not isinstance(delta, int):
        delta = preview.get("input_delta_count")
    parts: list[str] = []
    if isinstance(delta_mode, bool):
        parts.append(f"mode={str(delta_mode).lower()}")
    if isinstance(delta, int):
        parts.append(f"delta={delta}")
    if isinstance(baseline, int):
        parts.append(f"baseline={baseline}")
    return "; ".join(parts) if parts else "-"


def event_payload_preview(value: Any) -> str:
    try:
        import json

        return _truncate(json.dumps(_sanitize_payload(value), ensure_ascii=False), 240)
    except Exception:
        return _truncate(str(value), 240)


def event_tone(event: OperationsObservedEvent) -> str:
    if event.level == "error":
        return "danger"
    if event.level == "warning":
        return "warning"
    if event.status in {"succeeded", "completed", "ready"}:
        return "success"
    if event.status in {"running", "started"}:
        return "info"
    return "neutral"


def _sanitize_payload(value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        return "..."
    if isinstance(value, dict):
        return {
            str(key): _sanitize_payload(item, depth=depth + 1)
            for key, item in list(value.items())[:24]
        }
    if isinstance(value, (list, tuple)):
        return tuple(_sanitize_payload(item, depth=depth + 1) for item in value[:24])
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _truncate(value: Any, limit: int = 160) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return f"{text[: max(limit - 1, 0)]}..."


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
