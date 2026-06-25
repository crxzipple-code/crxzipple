from __future__ import annotations

from collections import Counter
from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
)
from crxzipple.modules.operations.application.read_models.presenters import (
    title_label,
    truncate_text,
)
from crxzipple.modules.operations.application.read_models.tool_source_catalog_labels import (
    source_endpoint_label,
    source_health_tone,
    source_runtime_dependency_label,
    source_tools_list_label,
)
from crxzipple.modules.operations.application.read_models.tool_source_common import (
    record_datetime_label,
    record_text,
    record_value,
)


def source_tab_tone(sources: tuple[Any, ...], functions: tuple[Any, ...]) -> str:
    if any(record_value(source, "status") == "error" for source in sources):
        return "danger"
    if any(
        record_value(function, "status") in {"stale", "deprecated"}
        or not bool(getattr(function, "enabled", True))
        for function in functions
    ):
        return "warning"
    return "neutral"


def source_health_rows(
    sources: tuple[Any, ...],
    *,
    functions: tuple[Any, ...],
    discovery_runs_by_source: dict[str, tuple[Any, ...]],
) -> tuple[OperationsTableRowModel, ...]:
    function_totals = Counter(record_text(function, "source_id") for function in functions)
    active_totals = Counter(
        record_text(function, "source_id")
        for function in functions
        if record_value(function, "status") == "active"
        and bool(getattr(function, "enabled", True))
    )
    rows = []
    for source in sorted(sources, key=lambda item: record_text(item, "source_id")):
        source_id = record_text(source, "source_id")
        latest_discovery = _first(discovery_runs_by_source.get(source_id, ()))
        discovery_status = (
            record_value(source, "last_discovery_status")
            or record_value(latest_discovery, "status")
        )
        status = record_value(source, "status") or "unknown"
        rows.append(
            OperationsTableRowModel(
                id=source_id,
                cells={
                    "source": source_id,
                    "kind": title_label(record_value(source, "kind") or "-"),
                    "endpoint": source_endpoint_label(source),
                    "runtime": source_runtime_dependency_label(source),
                    "status": title_label(status),
                    "discovery": title_label(discovery_status or "not_run"),
                    "tools_list": source_tools_list_label(source, discovery_status),
                    "functions": f"{active_totals[source_id]}/{function_totals[source_id]}",
                    "revision": str(getattr(source, "revision", "-")),
                    "updated": record_datetime_label(source, "updated_at"),
                },
                status=status,
                tone=source_health_tone(status, discovery_status),
            ),
        )
    return tuple(rows)


def discovery_failure_rows(
    sources: tuple[Any, ...],
    *,
    discovery_runs_by_source: dict[str, tuple[Any, ...]],
) -> tuple[OperationsTableRowModel, ...]:
    source_by_id = {record_text(source, "source_id"): source for source in sources}
    rows: list[OperationsTableRowModel] = []
    for source_id, runs in discovery_runs_by_source.items():
        for run in runs:
            if record_value(run, "status") != "failed":
                continue
            rows.append(
                OperationsTableRowModel(
                    id=f"{source_id}:{record_text(run, 'discovery_run_id')}",
                    cells={
                        "source": source_id,
                        "kind": title_label(
                            record_value(source_by_id.get(source_id), "kind") or "-",
                        ),
                        "time": record_datetime_label(run, "discovered_at"),
                        "error": truncate_text(
                            record_text(run, "error_message") or "-",
                            120,
                        ),
                        "functions": str(getattr(run, "function_count", 0)),
                        "backends": str(getattr(run, "provider_backend_count", 0)),
                    },
                    status="failed",
                    tone="danger",
                ),
            )
    return tuple(rows)


def function_catalog_rows(functions: tuple[Any, ...]) -> tuple[OperationsTableRowModel, ...]:
    rows: list[OperationsTableRowModel] = []
    for function in sorted(functions, key=lambda item: record_text(item, "function_id")):
        status = record_value(function, "status") or "unknown"
        enabled = bool(getattr(function, "enabled", True))
        if status == "active" and enabled:
            continue
        rows.append(
            OperationsTableRowModel(
                id=record_text(function, "function_id"),
                cells={
                    "function": record_text(function, "function_id"),
                    "source": record_text(function, "source_id"),
                    "kind": title_label(record_value(function, "runtime_kind") or "-"),
                    "status": title_label(status),
                    "enabled": "Yes" if enabled else "No",
                    "revision": str(getattr(function, "revision", "-")),
                    "schema": truncate_text(
                        record_text(function, "schema_hash") or "-",
                        14,
                    ),
                },
                status=status,
                tone="warning" if status in {"stale", "deprecated"} else "danger",
            ),
        )
    return tuple(rows)


def _first(values: tuple[Any, ...] | list[Any]) -> Any | None:
    return values[0] if values else None
