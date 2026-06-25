from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from crxzipple.modules.operations.application.read_models.diagnostics_common import (
    contains_key,
    enum_value,
    has_key,
    optional_text,
    summary_list,
    summary_payload,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    ExecutionStepItemKind,
)


def kind_count(items: Iterable[Any], kind: ExecutionStepItemKind) -> int:
    return sum(
        1 for item in items if enum_value(getattr(item, "kind", "")) == kind.value
    )


def tool_call_count(items: tuple[Any, ...]) -> int:
    explicit = kind_count(items, ExecutionStepItemKind.TOOL_CALL)
    if explicit:
        return explicit
    return kind_count(items, ExecutionStepItemKind.TOOL_RUN)


def unique_summary_ids(items: tuple[Any, ...], key: str) -> list[str]:
    ids: list[str] = []
    for item in items:
        for raw_id in summary_list(summary_payload(item), key):
            normalized = optional_text(raw_id)
            if normalized is not None and normalized not in ids:
                ids.append(normalized)
    return ids


def ui_step_count(items: tuple[Any, ...]) -> int:
    count = 0
    for item in items:
        payload = summary_payload(item)
        tool_id = optional_text(payload.get("tool_id")) or ""
        tool_name = optional_text(payload.get("tool_name")) or ""
        if tool_id.startswith("browser.") or tool_name.startswith("browser."):
            count += 1
    return count


def first_step_index(
    steps: tuple[Any, ...],
    items: tuple[Any, ...],
    *,
    predicate: Any,
) -> int | None:
    step_index_by_id = {
        str(getattr(step, "id", "")): int(getattr(step, "step_index", 0) or 0)
        for step in steps
    }
    matches = [
        step_index_by_id.get(str(getattr(item, "step_id", "")))
        for item in items
        if predicate(summary_payload(item))
    ]
    normalized = [value for value in matches if value is not None]
    return min(normalized) if normalized else None


def looks_like_candidate_discovery(payload: dict[str, object]) -> bool:
    return contains_key(
        payload,
        {
            "endpoint",
            "api_endpoint",
            "request_url",
            "url",
            "path",
            "file_path",
            "command",
            "candidate",
            "candidates",
            "resource",
            "resource_url",
        },
    )


def looks_like_candidate_validation(payload: dict[str, object]) -> bool:
    return contains_key(
        payload,
        {
            "validated",
            "validation",
            "validation_result",
            "verified",
            "verified_fact",
            "evidence",
            "evidence_type",
            "result_shape",
        },
    )


def repeated_probe_observation(metadata: object) -> dict[str, object]:
    if not isinstance(metadata, dict):
        return {}
    value = metadata.get("repeated_probe_observation")
    return dict(value) if isinstance(value, dict) else {}


def tool_result_contract_counts(items: tuple[Any, ...]) -> dict[str, int]:
    result_items = [
        item
        for item in items
        if enum_value(getattr(item, "kind", ""))
        == ExecutionStepItemKind.TOOL_RESULT.value
    ]
    summary_count = 0
    exit_code_count = 0
    read_handle_count = 0
    truncated_count = 0
    for item in result_items:
        payload = summary_payload(item)
        if optional_text(payload.get("result_summary")) or optional_text(
            payload.get("summary")
        ) or optional_text(payload.get("tool_result_summary")):
            summary_count += 1
        if has_key(payload, "exit_code"):
            exit_code_count += 1
        read_handle_count += len(summary_list(payload, "read_handles"))
        truncated = payload.get("truncated")
        output_truncated = payload.get("output_truncated")
        if truncated is True or output_truncated is True:
            truncated_count += 1
    return {
        "items": len(result_items),
        "summary_count": summary_count,
        "exit_code_count": exit_code_count,
        "read_handle_count": read_handle_count,
        "truncated_count": truncated_count,
    }


def terminal_status(status: object) -> str:
    value = enum_value(status)
    if value in {"completed", "cancelled", "failed"}:
        return value
    return "non_terminal"
