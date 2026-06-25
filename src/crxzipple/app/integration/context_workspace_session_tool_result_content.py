from __future__ import annotations

from crxzipple.app.integration.context_workspace_session_blocks import (
    blocks_prompt_content,
)
from crxzipple.app.integration.context_workspace_session_content_values import (
    json_fragment,
    optional_int,
    optional_text,
)
from crxzipple.app.integration.context_workspace_session_evidence import (
    small_structured_evidence_fact,
)
from crxzipple.modules.session.domain import SessionItem
from crxzipple.modules.tool.application.result_envelope import (
    TOOL_RESULT_ENVELOPE_METADATA_KEY,
)
from crxzipple.shared.content_blocks import (
    content_blocks_from_payload,
)


def tool_result_content(message: SessionItem) -> str:
    compact_content = _large_tool_result_ref_content(message)
    if compact_content is not None:
        return compact_content
    return blocks_prompt_content(content_blocks_from_payload(message.content_payload))


def tool_result_envelope_metadata(message: SessionItem) -> dict[str, object] | None:
    metadata = message.content_payload.get("metadata")
    if not isinstance(metadata, dict):
        return None
    envelope = metadata.get(TOOL_RESULT_ENVELOPE_METADATA_KEY)
    if not isinstance(envelope, dict):
        return None
    return dict(envelope)


def tool_result_error_json(message: SessionItem) -> str | None:
    error = message.content_payload.get("error")
    if error is None:
        return None
    return json_fragment(error)


def _large_tool_result_ref_content(message: SessionItem) -> str | None:
    payload = message.content_payload
    details = payload.get("details")
    metadata = payload.get("metadata")
    if not isinstance(details, dict):
        details = {}
    if not isinstance(metadata, dict):
        metadata = {}
    artifact_ids = _metadata_artifact_ids(metadata)
    body_removed = details.get("body_removed_from_details") is True
    envelope = metadata.get(TOOL_RESULT_ENVELOPE_METADATA_KEY)
    if isinstance(envelope, dict):
        envelope_content = _tool_result_envelope_ref_content(
            envelope,
            artifact_ids=artifact_ids,
            body_removed=body_removed,
        )
        if envelope_content is not None:
            return envelope_content
    if not artifact_ids and not body_removed:
        return None
    lines = ["tool_result_ref:"]
    lines.append("body_storage: externalized")
    endpoint = optional_text(details.get("endpoint"))
    method = optional_text(details.get("method"))
    request_id = optional_text(metadata.get("request_id")) or optional_text(
        details.get("request_id"),
    )
    if endpoint is not None:
        lines.append(f"endpoint: {endpoint}")
    if method is not None:
        lines.append(f"method: {method}")
    if request_id is not None:
        lines.append(f"request_id: {request_id}")
    if artifact_ids:
        lines.append(f"artifact_refs: {', '.join(artifact_ids)}")
    payload_shape = small_structured_evidence_fact(metadata.get("payload_shape"))
    if payload_shape is not None:
        lines.append(f"payload_shape: {json_fragment(payload_shape)}")
    result_shape = small_structured_evidence_fact(metadata.get("result_shape"))
    if result_shape is not None:
        lines.append(f"result_shape: {json_fragment(result_shape)}")
    lines.append("full_result_refs: artifact refs or read handles are available when needed")
    return "\n".join(lines)


def _tool_result_envelope_ref_content(
    envelope: dict[str, object],
    *,
    artifact_ids: tuple[str, ...],
    body_removed: bool,
) -> str | None:
    truncated = envelope.get("truncated") is True
    if not truncated and not artifact_ids and not body_removed:
        return None
    lines = ["tool_result_ref:"]
    lines.append("body_storage: externalized")
    status = optional_text(envelope.get("status"))
    summary = optional_text(envelope.get("summary"))
    if status is not None:
        lines.append(f"status: {status}")
    if summary is not None:
        lines.append(f"summary: {summary}")
    key_facts = envelope.get("key_facts")
    if isinstance(key_facts, dict) and key_facts:
        lines.append(f"key_facts: {json_fragment(key_facts)}")
    refs = _envelope_text_list(envelope.get("evidence_refs"))
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
    read_handles = small_structured_evidence_fact(envelope.get("read_handles"))
    if read_handles is not None:
        lines.append(f"read_handles: {json_fragment(read_handles)}")
    warnings = _envelope_text_list(envelope.get("warnings"))
    if warnings:
        lines.append(f"warnings: {'; '.join(warnings)}")
    lines.append("full_result_refs: artifact refs or read handles are available when needed")
    return "\n".join(lines)


def _metadata_artifact_ids(metadata: dict[str, object]) -> tuple[str, ...]:
    raw = metadata.get("artifact_ids")
    if not isinstance(raw, list):
        return ()
    values = [optional_text(item) for item in raw]
    return tuple(dict.fromkeys(item for item in values if item is not None))


def _envelope_text_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    normalized = [optional_text(item) for item in value]
    return tuple(dict.fromkeys(item for item in normalized if item is not None))

