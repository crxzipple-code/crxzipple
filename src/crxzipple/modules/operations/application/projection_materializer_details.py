from __future__ import annotations

from collections.abc import Callable
from typing import Any

from crxzipple.modules.operations.application.projection_materializer_json import (
    int_value,
    json_ready,
)
from crxzipple.modules.operations.application.projection_memory_details import (
    extract_memory_space_detail_projections,
)
from crxzipple.modules.operations.application.read_models import (
    LlmOperationsQuery,
    OperationsReadModelProvider,
    ToolOperationsQuery,
)

_TABLE_PROJECTION_LIMIT = 200


def module_table_projections(
    provider: OperationsReadModelProvider,
    module: str,
) -> tuple[
    tuple[tuple[str, dict[str, Any]], ...],
    tuple[tuple[str, str, dict[str, Any]], ...],
]:
    if module == "tool":
        return _collect_paginated_table_projection(
            page_loader=lambda offset, limit: json_ready(
                provider.tool_page(ToolOperationsQuery(limit=limit, offset=offset)),
            ),
            table_key="tool_runs",
            detail_payload_key="tool_run_details",
            detail_id_key="run_id",
            detail_kind="tool_run_detail",
        )
    if module == "llm":
        return _collect_paginated_table_projection(
            page_loader=lambda offset, limit: json_ready(
                provider.llm_page(LlmOperationsQuery(limit=limit, offset=offset)),
            ),
            table_key="recent_invocations",
            detail_payload_key="invocation_details",
            detail_id_key="invocation_id",
            detail_kind="llm_invocation_detail",
        )
    return (), ()


def extract_detail_projections(
    module: str,
    page_payload: dict[str, Any],
) -> tuple[tuple[str, str, dict[str, Any]], ...]:
    if module == "tool":
        return extract_list_detail_projections(
            page_payload=page_payload,
            payload_key="tool_run_details",
            id_key="run_id",
            detail_kind="tool_run_detail",
        )
    if module == "llm":
        return extract_list_detail_projections(
            page_payload=page_payload,
            payload_key="invocation_details",
            id_key="invocation_id",
            detail_kind="llm_invocation_detail",
        )
    if module == "memory":
        return (
            *extract_list_detail_projections(
                page_payload=page_payload,
                payload_key="file_details",
                id_key="file_id",
                detail_kind="memory_file_detail",
            ),
            *extract_memory_space_detail_projections(page_payload),
        )
    return ()


def module_detail_kinds(module: str) -> tuple[str, ...]:
    if module == "tool":
        return ("tool_run_detail",)
    if module == "llm":
        return ("llm_invocation_detail",)
    if module == "memory":
        return ("memory_file_detail", "memory_space_detail")
    return ()


def extract_list_detail_projections(
    *,
    page_payload: dict[str, Any],
    payload_key: str,
    id_key: str,
    detail_kind: str,
) -> tuple[tuple[str, str, dict[str, Any]], ...]:
    details = page_payload.get(payload_key)
    page_payload[payload_key] = []
    if not isinstance(details, list):
        return ()
    projections: list[tuple[str, str, dict[str, Any]]] = []
    for item in details:
        if not isinstance(item, dict):
            continue
        query_key = str(item.get(id_key) or "").strip()
        if not query_key:
            continue
        projections.append((detail_kind, query_key, dict(item)))
    return tuple(projections)


def _collect_paginated_table_projection(
    *,
    page_loader: Callable[[int, int], Any],
    table_key: str,
    detail_payload_key: str,
    detail_id_key: str,
    detail_kind: str,
) -> tuple[
    tuple[tuple[str, dict[str, Any]], ...],
    tuple[tuple[str, str, dict[str, Any]], ...],
]:
    rows: list[dict[str, Any]] = []
    total = 0
    section_payload: dict[str, Any] | None = None
    detail_by_key: dict[str, dict[str, Any]] = {}
    offset = 0
    while True:
        page_payload = page_loader(offset, _TABLE_PROJECTION_LIMIT)
        if not isinstance(page_payload, dict):
            break
        section = page_payload.get(table_key)
        if not isinstance(section, dict):
            break
        if section_payload is None:
            section_payload = dict(section)
        page_rows = [
            row
            for row in section.get("rows", ())
            if isinstance(row, dict)
        ]
        total = max(int_value(section.get("total")), len(rows) + len(page_rows))
        rows.extend(dict(row) for row in page_rows)
        for projection_kind, query_key, detail_payload in extract_list_detail_projections(
            page_payload=page_payload,
            payload_key=detail_payload_key,
            id_key=detail_id_key,
            detail_kind=detail_kind,
        ):
            if projection_kind == detail_kind:
                detail_by_key[query_key] = detail_payload
        offset += _TABLE_PROJECTION_LIMIT
        if len(rows) >= total or len(page_rows) < _TABLE_PROJECTION_LIMIT:
            break
    details = tuple(
        (detail_kind, key, payload)
        for key, payload in detail_by_key.items()
    )
    if section_payload is None:
        return (), details
    section_payload["rows"] = rows
    section_payload["total"] = total
    return ((table_key, section_payload),), details
