from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTabModel,
)
from crxzipple.modules.operations.application.read_models.tool_source_catalog_rows import (
    source_tab_tone,
)


def tool_page_tabs(
    *,
    run_count: int,
    sources: list[Any],
    functions: list[Any],
    worker_count: int,
    waiting_run_count: int,
    provider_history_count: int,
    active_run_count: int,
    risky_tool_count: int,
    artifact_count: int,
    observed_event_count: int,
) -> tuple[OperationsTabModel, ...]:
    return (
        OperationsTabModel(id="runs", label="Tool Runs", count=run_count),
        OperationsTabModel(
            id="sources",
            label="Sources",
            count=len(sources),
            tone=source_tab_tone(sources, functions),
        ),
        OperationsTabModel(id="workers", label="Workers", count=worker_count),
        OperationsTabModel(id="queue", label="Queue", count=waiting_run_count),
        OperationsTabModel(id="capabilities", label="Capabilities"),
        OperationsTabModel(
            id="provider_limits",
            label="Provider Limits",
        ),
        OperationsTabModel(
            id="provider_history",
            label="Provider History",
            count=provider_history_count,
        ),
        OperationsTabModel(
            id="diagnostics",
            label="Diagnostics",
            count=active_run_count,
            tone="warning" if active_run_count else "neutral",
        ),
        OperationsTabModel(
            id="risk",
            label="Risk",
            count=risky_tool_count,
            tone="warning" if risky_tool_count else "neutral",
        ),
        OperationsTabModel(
            id="artifacts",
            label="Artifacts",
            count=artifact_count,
        ),
        OperationsTabModel(
            id="events",
            label="Events",
            count=observed_event_count,
        ),
        OperationsTabModel(id="strategies", label="Strategies"),
    )
