from __future__ import annotations

import json

from crxzipple.modules.llm.application.tool_result_replay_excerpt import (
    append_detail_fact_lines,
    append_result_excerpt_line,
    has_provider_replay_detail_fields,
)
from crxzipple.modules.llm.application.tool_result_replay_fields import (
    append_optional_line,
    append_text_list_line,
    bounded_text,
    dict_value,
    metadata_artifact_ids,
    optional_int,
    optional_text,
    text_list,
)
from crxzipple.modules.tool.application.result_envelope import (
    TOOL_RESULT_ENVELOPE_METADATA_KEY,
)


def render_tool_result_model_text(payload: dict[str, object]) -> str | None:
    metadata = dict_value(payload.get("metadata"))
    details = dict_value(payload.get("details"))
    artifact_ids = metadata_artifact_ids(metadata)
    body_removed = details.get("body_removed_from_details") is True
    output_payload = dict_value(payload.get("output_payload"))
    envelope = metadata.get(TOOL_RESULT_ENVELOPE_METADATA_KEY)
    if isinstance(envelope, dict):
        content = _render_envelope_model_text(
            envelope,
            details=details,
            output_payload=output_payload,
            artifact_ids=artifact_ids,
            body_removed=body_removed,
        )
        if content is not None:
            return content
    if not artifact_ids and not body_removed:
        return None
    lines = ["tool_result:"]
    endpoint = optional_text(details.get("endpoint"))
    method = optional_text(details.get("method"))
    if endpoint is not None:
        lines.append(f"endpoint: {endpoint}")
    if method is not None:
        lines.append(f"method: {method}")
    if artifact_ids:
        lines.append(f"artifact_refs: {', '.join(artifact_ids)}")
    if body_removed:
        lines.append(
            "body_excerpt_unavailable: full body stored outside model-visible replay window",
        )
    lines.append("full_result_refs: use artifact refs or read handles when needed")
    return "\n".join(lines)


def _render_envelope_model_text(
    envelope: dict[str, object],
    *,
    details: dict[str, object],
    output_payload: dict[str, object],
    artifact_ids: tuple[str, ...],
    body_removed: bool,
) -> str | None:
    if (
        not _has_provider_replay_envelope_fields(envelope)
        and not has_provider_replay_detail_fields(details, output_payload)
        and envelope.get("truncated") is not True
        and not artifact_ids
        and not body_removed
    ):
        return None
    lines = ["tool_result:"]
    append_optional_line(lines, "status", envelope.get("status"))
    append_optional_line(lines, "summary", envelope.get("summary"))
    key_facts = envelope.get("key_facts")
    if isinstance(key_facts, dict) and key_facts:
        lines.append(
            "key_facts: "
            + json.dumps(key_facts, ensure_ascii=True, sort_keys=True),
        )
    provider_replay_payload = envelope.get("provider_replay_payload")
    has_provider_replay_payload = (
        isinstance(provider_replay_payload, dict) and bool(provider_replay_payload)
    )
    if has_provider_replay_payload:
        lines.append(
            "provider_replay_payload: "
            + bounded_text(
                json.dumps(
                    provider_replay_payload,
                    ensure_ascii=True,
                    sort_keys=True,
                ),
                limit=2400,
        ),
    )
    append_detail_fact_lines(lines, details=details, output_payload=output_payload)
    if not has_provider_replay_payload:
        append_result_excerpt_line(
            lines,
            details=details,
            output_payload=output_payload,
            include_body=not body_removed,
        )
    append_text_list_line(lines, "failure_signatures", envelope.get("failure_signatures"))
    refs = text_list(envelope.get("evidence_refs"))
    if artifact_ids:
        refs = tuple(dict.fromkeys((*refs, *artifact_ids)))
    if refs:
        lines.append(f"artifact_refs: {', '.join(refs)}")
    omitted_count = optional_int(envelope.get("omitted_count"))
    omitted_chars = optional_int(envelope.get("omitted_chars"))
    if omitted_count is not None:
        lines.append(f"omitted_count: {omitted_count}")
    if omitted_chars is not None:
        lines.append(f"omitted_chars: {omitted_chars}")
    if envelope.get("truncated") is True or body_removed:
        reasons: list[str] = []
        if envelope.get("truncated") is True:
            reasons.append("truncated")
        if body_removed:
            reasons.append("body_removed")
        lines.append(f"body_excerpt_policy: {', '.join(reasons)}")
    read_handles = envelope.get("read_handles")
    if isinstance(read_handles, list) and read_handles:
        lines.append(
            "read_handles: "
            + json.dumps(read_handles[:8], ensure_ascii=True, sort_keys=True),
        )
    append_text_list_line(lines, "warnings", envelope.get("warnings"))
    lines.append("full_result_refs: use artifact refs or read handles when needed")
    return "\n".join(lines)


def _has_provider_replay_envelope_fields(envelope: dict[str, object]) -> bool:
    for key in (
        "summary",
        "key_facts",
        "provider_replay_payload",
        "failure_signatures",
        "evidence_refs",
        "read_handles",
        "warnings",
    ):
        value = envelope.get(key)
        if value not in (None, "", [], {}):
            return True
    return False


__all__ = ["render_tool_result_model_text"]
