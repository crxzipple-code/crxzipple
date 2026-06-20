from __future__ import annotations

import json

from crxzipple.modules.tool.application.result_envelope import (
    TOOL_RESULT_ENVELOPE_METADATA_KEY,
)


def render_tool_result_model_text(payload: dict[str, object]) -> str | None:
    metadata = _dict_value(payload.get("metadata"))
    details = _dict_value(payload.get("details"))
    artifact_ids = _metadata_artifact_ids(metadata)
    body_removed = details.get("body_removed_from_details") is True
    output_payload = _dict_value(payload.get("output_payload"))
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
    endpoint = _optional_text(details.get("endpoint"))
    method = _optional_text(details.get("method"))
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
        and not _has_provider_replay_detail_fields(details, output_payload)
        and envelope.get("truncated") is not True
        and not artifact_ids
        and not body_removed
    ):
        return None
    lines = ["tool_result:"]
    _append_optional_line(lines, "status", envelope.get("status"))
    _append_optional_line(lines, "summary", envelope.get("summary"))
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
            + _bounded_text(
                json.dumps(
                    provider_replay_payload,
                    ensure_ascii=True,
                    sort_keys=True,
                ),
                limit=2400,
        ),
    )
    _append_detail_fact_lines(lines, details=details, output_payload=output_payload)
    if not has_provider_replay_payload:
        _append_result_excerpt_line(
            lines,
            details=details,
            output_payload=output_payload,
            include_body=not body_removed,
        )
    _append_text_list_line(lines, "failure_signatures", envelope.get("failure_signatures"))
    refs = _text_list(envelope.get("evidence_refs"))
    if artifact_ids:
        refs = tuple(dict.fromkeys((*refs, *artifact_ids)))
    if refs:
        lines.append(f"artifact_refs: {', '.join(refs)}")
    omitted_count = _optional_int(envelope.get("omitted_count"))
    omitted_chars = _optional_int(envelope.get("omitted_chars"))
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
    _append_text_list_line(lines, "warnings", envelope.get("warnings"))
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


def _has_provider_replay_detail_fields(
    details: dict[str, object],
    output_payload: dict[str, object],
) -> bool:
    for key in (
        "command",
        "exit_code",
        "working_directory",
        "endpoint",
        "method",
        "current_url",
        "title",
        "stdout_excerpt",
        "stderr_excerpt",
        "stdout",
        "stderr",
    ):
        if details.get(key) not in (None, "", [], {}):
            return True
        if output_payload.get(key) not in (None, "", [], {}):
            return True
    if _result_excerpt(details=details, output_payload=output_payload) is not None:
        return True
    return False


def _append_detail_fact_lines(
    lines: list[str],
    *,
    details: dict[str, object],
    output_payload: dict[str, object],
) -> None:
    for label, key in (
        ("command", "command"),
        ("exit_code", "exit_code"),
        ("working_directory", "working_directory"),
        ("endpoint", "endpoint"),
        ("method", "method"),
        ("current_url", "current_url"),
        ("title", "title"),
    ):
        _append_optional_line(
            lines,
            label,
            details.get(key, output_payload.get(key)),
        )
    stdout = _optional_text(details.get("stdout_excerpt")) or _optional_text(
        output_payload.get("stdout_excerpt"),
    )
    if stdout is None:
        stdout = _optional_text(details.get("stdout")) or _optional_text(
            output_payload.get("stdout"),
        )
    stderr = _optional_text(details.get("stderr_excerpt")) or _optional_text(
        output_payload.get("stderr_excerpt"),
    )
    if stderr is None:
        stderr = _optional_text(details.get("stderr")) or _optional_text(
            output_payload.get("stderr"),
        )
    if stdout is not None:
        lines.append(f"stdout_excerpt: {_bounded_text(stdout, limit=2000)}")
    if stderr is not None:
        lines.append(f"stderr_excerpt: {_bounded_text(stderr, limit=2000)}")


def _append_result_excerpt_line(
    lines: list[str],
    *,
    details: dict[str, object],
    output_payload: dict[str, object],
    include_body: bool,
) -> None:
    excerpt = _result_excerpt(
        details=details,
        output_payload=output_payload,
        include_body=include_body,
    )
    if excerpt is not None:
        lines.append(f"result_excerpt: {_bounded_text(excerpt, limit=2400)}")


def _result_excerpt(
    *,
    details: dict[str, object],
    output_payload: dict[str, object],
    include_body: bool = True,
) -> str | None:
    candidates: list[object] = []
    output_keys = (
        "content",
        "text",
        "result",
        "data",
        "json",
        "response",
        "items",
        "records",
        "rows",
        "markdown",
        "html",
    )
    detail_keys = (
        "result",
        "data",
        "json",
        "response",
        "items",
        "records",
        "rows",
        "markdown",
        "html",
    )
    if include_body:
        output_keys = (*output_keys, "body")
        detail_keys = (*detail_keys, "body")
    for key in output_keys:
        value = output_payload.get(key)
        if value not in (None, "", [], {}):
            candidates.append(value)
    for key in detail_keys:
        value = details.get(key)
        if value not in (None, "", [], {}):
            candidates.append(value)
    for value in candidates:
        text = _content_excerpt(value)
        if text is not None:
            return text
    return None


def _content_excerpt(value: object) -> str | None:
    text = _optional_text(value)
    if text is not None and not isinstance(value, (dict, list, tuple)):
        return text
    if isinstance(value, list):
        block_text = _text_from_content_blocks(value)
        if block_text is not None:
            return block_text
    try:
        encoded = json.dumps(value, ensure_ascii=True, sort_keys=True)
    except (TypeError, ValueError):
        return text
    return _optional_text(encoded)


def _text_from_content_blocks(value: list[object]) -> str | None:
    chunks: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type not in {"text", "output_text", "markdown"}:
            continue
        text = _optional_text(item.get("text"))
        if text is not None:
            chunks.append(text)
    return "\n".join(chunks) if chunks else None


def _append_optional_line(
    lines: list[str],
    label: str,
    value: object,
) -> None:
    text = _optional_text(value)
    if text is not None:
        lines.append(f"{label}: {text}")


def _append_text_list_line(
    lines: list[str],
    label: str,
    value: object,
) -> None:
    values = _text_list(value)
    if values:
        lines.append(f"{label}: {'; '.join(values[:8])}")


def _dict_value(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _metadata_artifact_ids(metadata: dict[str, object]) -> tuple[str, ...]:
    raw = metadata.get("artifact_ids")
    if not isinstance(raw, list):
        raw = metadata.get("browser_artifact_ids")
    if not isinstance(raw, list):
        return ()
    values = [_optional_text(item) for item in raw]
    return tuple(dict.fromkeys(value for value in values if value is not None))


def _text_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    values = [_optional_text(item) for item in value]
    return tuple(dict.fromkeys(item for item in values if item is not None))


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bounded_text(value: str, *, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: max(0, limit - 1)].rstrip()}…"
