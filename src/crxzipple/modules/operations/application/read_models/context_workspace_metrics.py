from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.context_workspace_row_helpers import (
    health_tone,
    nodes_from_view,
)
from crxzipple.modules.operations.application.read_models.context_workspace_snapshot_rows import (
    snapshot_provider_tokens,
    snapshot_session_range_risk_count,
)
from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
)


def metrics(
    *,
    health: str,
    workspaces: tuple[Any, ...],
    tree_views: tuple[Any, ...],
    snapshots: tuple[Any, ...],
    slice_rows: tuple[dict[str, str], ...],
) -> tuple[MetricCardModel, ...]:
    nodes = tuple(node for view in tree_views for node in nodes_from_view(view))
    snapshot_visible_nodes = tuple(
        node for node in nodes if bool(getattr(node.state, "snapshot_visible", False))
    )
    pinned_nodes = tuple(node for node in nodes if bool(getattr(node.state, "pinned", False)))
    token_total = sum(snapshot_provider_tokens(snapshot) for snapshot in snapshots[:20])
    range_risk_count = sum(
        snapshot_session_range_risk_count(snapshot)
        for snapshot in snapshots[:20]
    )
    return (
        MetricCardModel("health", "Health", health.title(), "context tree", health_tone(health)),
        MetricCardModel(
            "workspaces",
            "Workspaces",
            str(len(workspaces)),
            "recent sessions",
            "info",
        ),
        MetricCardModel(
            "nodes",
            "Visible Nodes",
            str(len(nodes)),
            f"{len(snapshot_visible_nodes)} snapshot-visible",
            "info",
        ),
        MetricCardModel(
            "pinned",
            "Pinned",
            str(len(pinned_nodes)),
            "agent/user pinned nodes",
            "success" if pinned_nodes else "neutral",
        ),
        MetricCardModel(
            "snapshots",
            "Context Snapshots",
            str(len(snapshots)),
            "recent context snapshots",
            "info",
        ),
        MetricCardModel(
            "snapshot_tokens",
            "Provider Wire Tokens",
            str(token_total),
            "recent provider estimate",
            "info",
        ),
        MetricCardModel(
            "session_range_risks",
            "Session Range Risks",
            str(range_risk_count),
            "recent hidden/split/blocked ranges",
            "warning" if range_risk_count else "success",
        ),
        MetricCardModel(
            "observation_slices",
            "Observation Slices",
            str(len(slice_rows)),
            "operations projection slices",
            "success" if slice_rows else "neutral",
        ),
    )
