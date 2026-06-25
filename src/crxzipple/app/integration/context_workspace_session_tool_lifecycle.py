from __future__ import annotations

from crxzipple.app.integration.context_workspace_session_evidence import (
    evidence_facts,
    evidence_type,
)
from crxzipple.modules.session.domain import SessionItem


def is_failed_tool_status(status: str) -> bool:
    return status.strip().lower() not in {"succeeded", "completed", "success"}


def tool_interaction_observed(
    *,
    tool_name: str,
    status: str,
    result_message: SessionItem,
) -> bool:
    if is_failed_tool_status(status):
        return False
    payload = result_message.content_payload
    details = payload.get("details")
    metadata = payload.get("metadata")
    facts = evidence_facts(
        tool_name=tool_name,
        payload=payload,
        details=details,
        metadata=metadata,
    )
    resolved_evidence_type = evidence_type(
        tool_name=tool_name,
        status=status,
        facts=facts,
    )
    return resolved_evidence_type in {
        "api_endpoint",
        "result_shape",
        "payload_shape",
        "user_visible_result",
        "observation",
    }


def tool_interaction_superseded(
    result_message: SessionItem,
    lifecycle_facts: dict[str, object] | None = None,
) -> bool:
    for source in tool_interaction_fact_sources(
        result_message,
        lifecycle_facts=lifecycle_facts,
    ):
        if _truthy(source.get("superseded")):
            return True
        lifecycle_status = _optional_text(source.get("lifecycle_status"))
        if lifecycle_status == "superseded":
            return True
    return False


def tool_interaction_superseded_by_tool_call_id(
    result_message: SessionItem,
    lifecycle_facts: dict[str, object] | None = None,
) -> str | None:
    for source in tool_interaction_fact_sources(
        result_message,
        lifecycle_facts=lifecycle_facts,
    ):
        for key in (
            "superseded_by_tool_call_id",
            "replaced_by_tool_call_id",
            "replacement_tool_call_id",
        ):
            value = _optional_text(source.get(key))
            if value is not None:
                return _truncate(value, 180)
    return None


def tool_interaction_fact_sources(
    result_message: SessionItem,
    lifecycle_facts: dict[str, object] | None = None,
) -> tuple[dict[str, object], ...]:
    sources: list[dict[str, object]] = []
    if lifecycle_facts:
        sources.append(lifecycle_facts)
    for candidate in (
        result_message.metadata,
        result_message.content_payload,
        result_message.content_payload.get("metadata"),
        result_message.content_payload.get("details"),
    ):
        sources.extend(nested_tool_lifecycle_sources(candidate))
    return tuple(sources)


def nested_tool_lifecycle_sources(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, dict):
        return ()
    sources: list[dict[str, object]] = []
    for key in ("tool_lifecycle", "evidence_lifecycle"):
        nested = value.get(key)
        if isinstance(nested, dict):
            sources.append(nested)
    return tuple(sources)


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    if isinstance(value, int | float):
        return value != 0
    return False


def _truncate(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3].rstrip()}..."
