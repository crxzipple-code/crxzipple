from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.tool_source_cli_rows import (
    cli_process_health_rows,
)
from crxzipple.modules.operations.application.read_models.tool_source_catalog_rows import (
    discovery_failure_rows,
    function_catalog_rows,
    source_health_rows,
)
from crxzipple.modules.operations.application.read_models.tool_source_common import (
    columns,
)


def source_health_section(
    sources: tuple[Any, ...],
    *,
    functions: tuple[Any, ...],
    discovery_runs_by_source: dict[str, tuple[Any, ...]],
) -> OperationsTableSectionModel:
    rows = source_health_rows(
        sources,
        functions=functions,
        discovery_runs_by_source=discovery_runs_by_source,
    )
    return OperationsTableSectionModel(
        id="source_health",
        title="Source Health",
        columns=columns(
            ("source", "Source"),
            ("kind", "Kind"),
            ("endpoint", "Endpoint"),
            ("runtime", "Runtime Dependency"),
            ("status", "Status"),
            ("discovery", "Discovery"),
            ("tools_list", "Tools/List"),
            ("functions", "Functions"),
            ("revision", "Revision"),
            ("updated", "Updated"),
        ),
        rows=rows,
        total=len(rows),
        empty_state="No Tool sources are registered.",
    )


def discovery_failures_section(
    sources: tuple[Any, ...],
    *,
    discovery_runs_by_source: dict[str, tuple[Any, ...]],
) -> OperationsTableSectionModel:
    rows = discovery_failure_rows(
        sources,
        discovery_runs_by_source=discovery_runs_by_source,
    )
    return OperationsTableSectionModel(
        id="discovery_failures",
        title="Discovery Failures",
        columns=columns(
            ("source", "Source"),
            ("kind", "Kind"),
            ("time", "Time"),
            ("error", "Error"),
            ("functions", "Functions"),
            ("backends", "Backends"),
        ),
        rows=rows[:50],
        total=len(rows),
        empty_state="No Tool discovery failures recorded.",
    )


def function_catalog_section(functions: tuple[Any, ...]) -> OperationsTableSectionModel:
    rows = function_catalog_rows(functions)
    return OperationsTableSectionModel(
        id="function_catalog",
        title="Function Catalog Risks",
        columns=columns(
            ("function", "Function"),
            ("source", "Source"),
            ("kind", "Kind"),
            ("status", "Status"),
            ("enabled", "Enabled"),
            ("revision", "Revision"),
            ("schema", "Schema"),
        ),
        rows=rows[:80],
        total=len(rows),
        empty_state="No stale, deprecated, disabled, or deleted functions.",
    )


def cli_process_health_section(
    sources: tuple[Any, ...],
    *,
    functions: tuple[Any, ...],
) -> OperationsTableSectionModel:
    rows = cli_process_health_rows(sources, functions=functions)
    return OperationsTableSectionModel(
        id="cli_process_health",
        title="CLI Process Health",
        columns=columns(
            ("source", "Source"),
            ("status", "Status"),
            ("functions", "Functions"),
            ("policy", "Policy"),
        ),
        rows=rows,
        total=len(rows),
        empty_state="No CLI sources are registered.",
    )
