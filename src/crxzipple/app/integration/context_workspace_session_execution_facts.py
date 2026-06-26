"""Execution-summary facts used by the Session context tree adapter."""

from __future__ import annotations

from crxzipple.app.integration.context_workspace_session_content_values import (
    optional_int,
    optional_text,
)
from crxzipple.app.integration.context_workspace_session_tool_lifecycle import (
    nested_tool_lifecycle_sources,
)


def consumed_draft_input_through_sequence_no_from_summaries(
    summaries: tuple[dict[str, object], ...],
    *,
    session_id: str,
) -> int | None:
    consumed_through: int | None = None
    for summary in summaries:
        consumption = summary.get("llm_transcript_consumption")
        if not isinstance(consumption, dict):
            continue
        sequence_range = consumption.get("draft_input_sequence_range")
        if not isinstance(sequence_range, dict):
            continue
        sessions = sequence_range.get("sessions")
        if not isinstance(sessions, list):
            continue
        for item in sessions:
            if not isinstance(item, dict):
                continue
            if optional_text(item.get("session_id")) != session_id:
                continue
            to_sequence_no = optional_int(item.get("to_sequence_no"))
            if to_sequence_no is None:
                continue
            consumed_through = (
                to_sequence_no
                if consumed_through is None
                else max(consumed_through, to_sequence_no)
            )
    return consumed_through


def tool_lifecycle_facts_from_execution_summaries(
    summaries: tuple[dict[str, object], ...],
) -> dict[str, dict[str, object]]:
    facts_by_ref: dict[str, dict[str, object]] = {}
    for summary in summaries:
        facts = _explicit_tool_lifecycle_fact_payload(summary)
        if not facts:
            continue
        for ref in _tool_lifecycle_fact_refs(summary, facts):
            current = facts_by_ref.setdefault(ref, {})
            current.update(facts)
        replacement_facts = _replacement_tool_lifecycle_fact_payload(summary, facts)
        for ref in _tool_lifecycle_superseded_target_refs(facts):
            current = facts_by_ref.setdefault(ref, {})
            current.update(replacement_facts)
    return facts_by_ref


def _explicit_tool_lifecycle_fact_payload(
    summary: dict[str, object],
) -> dict[str, object]:
    payload: dict[str, object] = {}
    for source in _tool_lifecycle_summary_sources(summary):
        for key in (
            "superseded",
            "superseded_by_tool_call_id",
            "replaced_by_tool_call_id",
            "replacement_tool_call_id",
            "supersedes_tool_call_id",
            "supersedes_tool_run_id",
            "supersedes_result_session_item_id",
            "lifecycle_status",
            "evidence_lifecycle_status",
            "evidence_lifecycle",
        ):
            if key in source:
                payload[key] = source[key]
    return payload


def _tool_lifecycle_summary_sources(
    summary: dict[str, object],
) -> tuple[dict[str, object], ...]:
    sources: list[dict[str, object]] = []
    sources.extend(nested_tool_lifecycle_sources(summary))
    metadata = summary.get("metadata")
    sources.extend(nested_tool_lifecycle_sources(metadata))
    return tuple(sources)


def _tool_lifecycle_fact_refs(
    summary: dict[str, object],
    facts: dict[str, object],
) -> tuple[str, ...]:
    refs: list[str] = []
    for source in (summary, facts):
        for key in ("tool_call_id", "result_session_item_id", "tool_run_id"):
            value = optional_text(source.get(key))
            if value is not None:
                refs.append(value)
    return tuple(dict.fromkeys(refs))


def _tool_lifecycle_superseded_target_refs(
    facts: dict[str, object],
) -> tuple[str, ...]:
    refs: list[str] = []
    for key in (
        "supersedes_tool_call_id",
        "supersedes_tool_run_id",
        "supersedes_result_session_item_id",
    ):
        value = optional_text(facts.get(key))
        if value is not None:
            refs.append(value)
    return tuple(dict.fromkeys(refs))


def _replacement_tool_lifecycle_fact_payload(
    summary: dict[str, object],
    facts: dict[str, object],
) -> dict[str, object]:
    payload: dict[str, object] = {
        "superseded": True,
        "lifecycle_status": "superseded",
    }
    replacement_tool_call_id = (
        optional_text(summary.get("tool_call_id"))
        or optional_text(facts.get("tool_call_id"))
        or optional_text(facts.get("replacement_tool_call_id"))
        or optional_text(facts.get("superseded_by_tool_call_id"))
    )
    if replacement_tool_call_id is not None:
        payload["superseded_by_tool_call_id"] = replacement_tool_call_id
    return payload


__all__ = [
    "consumed_draft_input_through_sequence_no_from_summaries",
    "tool_lifecycle_facts_from_execution_summaries",
]
