from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.operations.application.read_models.context_workspace_page_sources import (
    safe_list_snapshots,
    safe_list_workspaces,
    safe_operations_slice_rows,
    safe_tree_views,
)
from crxzipple.modules.operations.application.read_models.context_workspace_row_helpers import (
    nodes_from_view,
)
from crxzipple.modules.operations.application.read_models.context_workspace_node_status_rows import (
    node_status_rows,
)
from crxzipple.modules.operations.application.read_models.context_workspace_rows import (
    diagnostic_rows,
    filter_workspaces,
    node_rows,
    workspace_rows,
)
from crxzipple.modules.operations.application.read_models.context_workspace_snapshot_rows import (
    context_budget_rows,
    filter_snapshots,
    snapshot_rows,
)
from crxzipple.modules.operations.application.read_models.ports_context import (
    OperationsContextObservationSnapshotPort,
    OperationsContextSliceBuilderPort,
    OperationsContextTreePort,
    OperationsContextWorkspacePort,
)


@dataclass(frozen=True, slots=True)
class ContextWorkspacePageFacts:
    now: datetime
    filtered_workspaces: tuple[Any, ...]
    visible_workspaces: tuple[Any, ...]
    tree_views: tuple[Any, ...]
    snapshots: tuple[Any, ...]
    slice_rows: tuple[dict[str, str], ...]
    workspace_table_rows: tuple[dict[str, str], ...]
    node_table_rows: tuple[dict[str, str], ...]
    node_status_table_rows: tuple[dict[str, str], ...]
    node_status_total: int
    snapshot_table_rows: tuple[dict[str, str], ...]
    snapshot_total: int
    context_budget_table_rows: tuple[dict[str, str], ...]
    diagnostic_table_rows: tuple[dict[str, str], ...]
    health: str


def collect_context_workspace_page_facts(
    *,
    workspace_service: OperationsContextWorkspacePort | None,
    tree_service: OperationsContextTreePort | None,
    observation_snapshot_service: OperationsContextObservationSnapshotPort | None,
    slice_builder: OperationsContextSliceBuilderPort | None,
    query: Any,
) -> ContextWorkspacePageFacts:
    now = datetime.now(timezone.utc)
    workspaces, workspace_error = safe_list_workspaces(
        workspace_service,
        limit=max(int(query.limit), 100),
        offset=0,
    )
    filtered = filter_workspaces(workspaces, query.search)
    visible = filtered[query.offset : query.offset + query.limit]
    tree_views, tree_error = safe_tree_views(tree_service, visible)
    snapshots, snapshot_error = safe_list_snapshots(
        observation_snapshot_service,
        limit=min(max(int(query.limit), 40), 100),
        offset=0,
    )
    slice_rows, slice_error = safe_operations_slice_rows(
        slice_builder,
        visible,
        snapshots,
        limit=int(query.limit),
    )
    diagnostic_table_rows = diagnostic_rows(
        workspace_error=workspace_error,
        tree_error=tree_error,
        snapshot_error=snapshot_error,
        slice_error=slice_error,
    )
    filtered_snapshots = filter_snapshots(snapshots, query.search)
    return ContextWorkspacePageFacts(
        now=now,
        filtered_workspaces=filtered,
        visible_workspaces=visible,
        tree_views=tree_views,
        snapshots=snapshots,
        slice_rows=slice_rows,
        workspace_table_rows=workspace_rows(visible, tree_views),
        node_table_rows=node_rows(tree_views, int(query.limit)),
        node_status_table_rows=node_status_rows(tree_views, int(query.limit)),
        node_status_total=len(node_status_rows(tree_views, 10_000)),
        snapshot_table_rows=snapshot_rows(snapshots, query.search, int(query.limit)),
        snapshot_total=len(filtered_snapshots),
        context_budget_table_rows=context_budget_rows(
            snapshots,
            query.search,
            int(query.limit),
        ),
        diagnostic_table_rows=diagnostic_table_rows,
        health=_health(
            workspace_service_available=workspace_service is not None,
            tree_service_available=tree_service is not None,
            observation_snapshot_service_available=(
                observation_snapshot_service is not None
            ),
            diagnostic_rows=diagnostic_table_rows,
        ),
    )


def visible_node_count(tree_views: tuple[Any, ...]) -> int:
    return sum(len(nodes_from_view(view)) for view in tree_views)


def _health(
    *,
    workspace_service_available: bool,
    tree_service_available: bool,
    observation_snapshot_service_available: bool,
    diagnostic_rows: tuple[dict[str, str], ...],
) -> str:
    if diagnostic_rows:
        return "error"
    if not (
        workspace_service_available
        and tree_service_available
        and observation_snapshot_service_available
    ):
        return "warning"
    return "healthy"


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()
