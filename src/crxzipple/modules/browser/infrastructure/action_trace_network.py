from __future__ import annotations

from typing import Any, Mapping

from .action_trace_payloads import (
    _json_safe_payload,
    _payload_text_any,
    _trace_error_list,
)


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
            [
                request
                for request in requests
                if (
                    isinstance(request.get("initiator_summary"), Mapping)
                    and _payload_text_any(request["initiator_summary"], "script_url")
                    is not None
                )
            ]
        ),
        "script_frames": script_frames[:10],
        "api_candidates": api_candidates[:10],
    }
