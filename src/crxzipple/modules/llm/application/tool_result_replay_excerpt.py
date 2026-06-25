from __future__ import annotations

import json

from crxzipple.modules.llm.application.tool_result_replay_fields import (
    append_optional_line,
    bounded_text,
    optional_text,
)


def has_provider_replay_detail_fields(
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
    if result_excerpt(details=details, output_payload=output_payload) is not None:
        return True
    return False


def append_detail_fact_lines(
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
        append_optional_line(
            lines,
            label,
            details.get(key, output_payload.get(key)),
        )
    stdout = optional_text(details.get("stdout_excerpt")) or optional_text(
        output_payload.get("stdout_excerpt"),
    )
    if stdout is None:
        stdout = optional_text(details.get("stdout")) or optional_text(
            output_payload.get("stdout"),
        )
    stderr = optional_text(details.get("stderr_excerpt")) or optional_text(
        output_payload.get("stderr_excerpt"),
    )
    if stderr is None:
        stderr = optional_text(details.get("stderr")) or optional_text(
            output_payload.get("stderr"),
        )
    if stdout is not None:
        lines.append(f"stdout_excerpt: {bounded_text(stdout, limit=2000)}")
    if stderr is not None:
        lines.append(f"stderr_excerpt: {bounded_text(stderr, limit=2000)}")


def append_result_excerpt_line(
    lines: list[str],
    *,
    details: dict[str, object],
    output_payload: dict[str, object],
    include_body: bool,
) -> None:
    excerpt = result_excerpt(
        details=details,
        output_payload=output_payload,
        include_body=include_body,
    )
    if excerpt is not None:
        lines.append(f"result_excerpt: {bounded_text(excerpt, limit=2400)}")


def result_excerpt(
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
        text = content_excerpt(value)
        if text is not None:
            return text
    return None


def content_excerpt(value: object) -> str | None:
    text = optional_text(value)
    if text is not None and not isinstance(value, (dict, list, tuple)):
        return text
    if isinstance(value, list):
        block_text = text_from_content_blocks(value)
        if block_text is not None:
            return block_text
    try:
        encoded = json.dumps(value, ensure_ascii=True, sort_keys=True)
    except (TypeError, ValueError):
        return text
    return optional_text(encoded)


def text_from_content_blocks(value: list[object]) -> str | None:
    chunks: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type not in {"text", "output_text", "markdown"}:
            continue
        text = optional_text(item.get("text"))
        if text is not None:
            chunks.append(text)
    return "\n".join(chunks) if chunks else None


__all__ = [
    "append_detail_fact_lines",
    "append_result_excerpt_line",
    "content_excerpt",
    "has_provider_replay_detail_fields",
    "result_excerpt",
    "text_from_content_blocks",
]
