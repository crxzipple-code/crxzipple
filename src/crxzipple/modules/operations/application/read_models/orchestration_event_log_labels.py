from __future__ import annotations


_EVENT_LABELS = {
    "orchestration.run.accepted": "Run Accepted",
    "orchestration.run.queued": "Run Queued",
    "orchestration.run.claimed": "Run Claimed",
    "orchestration.run.worker_lease_recovered": "Worker Lease Recovered",
    "orchestration.run.resumed": "Run Resumed",
    "orchestration.run.waiting": "Run Waiting",
    "orchestration.run.completed": "Run Completed",
    "orchestration.run.failed": "Run Failed",
    "orchestration.run.cancelled": "Run Cancelled",
    "orchestration.ingress.requested": "Ingress Requested",
    "orchestration.ingress.queued": "Ingress Queued",
    "orchestration.ingress.claimed": "Ingress Claimed",
    "orchestration.ingress.completed": "Ingress Completed",
    "orchestration.ingress.failed": "Ingress Failed",
    "orchestration.executor.assignment.requested": "Executor Assignment Requested",
    "orchestration.executor.lease.registered": "Executor Registered",
    "orchestration.executor.lease.heartbeated": "Executor Heartbeat",
    "orchestration.executor.lease.expired": "Executor Lease Expired",
    "orchestration.runtime.status": "Runtime Status",
    "orchestration.run.message_appended": "Run Message Appended",
    "orchestration.run.tool_updated": "Tool Updated",
    "orchestration.run.llm_text_delta": "LLM Text Delta",
    "orchestration.llm_resolved": "LLM Resolved",
}


def event_display_label(event_name: str, payload: dict[str, object]) -> str:
    label = _optional_str(payload.get("display_label"))
    if label:
        return label
    normalized = event_name.strip().lower()
    if normalized in _EVENT_LABELS:
        return _EVENT_LABELS[normalized]
    return title_from_event_name(event_name)


def title_from_event_name(event_name: str) -> str:
    tail = event_name.removeprefix("orchestration.")
    parts = [
        part
        for segment in tail.split(".")
        for part in segment.split("_")
        if part.strip()
    ]
    if not parts:
        return "Event"
    return " ".join(part[:1].upper() + part[1:] for part in parts)


def _optional_str(value: object | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None
