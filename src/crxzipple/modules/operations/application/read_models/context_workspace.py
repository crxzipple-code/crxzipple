from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.operations.application.read_models.context_workspace_row_helpers import (
    section_rows,
    table_section,
)
from crxzipple.modules.operations.application.read_models.context_workspace_metrics import (
    metrics,
)
from crxzipple.modules.operations.application.read_models.context_workspace_page_facts import (
    collect_context_workspace_page_facts,
    visible_node_count,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsModuleOverview,
    OperationsModuleRoleModel,
    OperationsTabModel,
    RuntimeActionModel,
)
from crxzipple.modules.operations.application.read_models.modules import (
    OperationsModulePage,
)
from crxzipple.modules.operations.application.read_models.ports_context import (
    OperationsContextObservationSnapshotPort,
    OperationsContextSliceBuilderPort,
    OperationsContextTreePort,
    OperationsContextWorkspacePort,
)
from crxzipple.shared.time import format_datetime_utc


@dataclass(frozen=True, slots=True)
class ContextWorkspaceOperationsQuery:
    search: str = ""
    limit: int = 80
    offset: int = 0


@dataclass(slots=True)
class ContextWorkspaceOperationsReadModelProvider:
    workspace_service: OperationsContextWorkspacePort | None
    tree_service: OperationsContextTreePort | None
    observation_snapshot_service: OperationsContextObservationSnapshotPort | None
    slice_builder: OperationsContextSliceBuilderPort | None = None

    def overview(self) -> OperationsModuleOverview:
        page = self.page(ContextWorkspaceOperationsQuery(limit=40))
        workspaces = section_rows(page.sections, "workspaces")
        nodes = section_rows(page.sections, "visible_nodes")
        snapshots = section_rows(page.sections, "snapshots")
        return OperationsModuleOverview(
            module=page.module,
            title=page.title,
            subtitle=page.subtitle,
            health=page.health,
            updated_at=page.updated_at,
            metrics=page.metrics,
            queue=workspaces,
            lane_locks=nodes,
            executor=snapshots,
            actions=page.actions,
        )

    def page(
        self,
        query: ContextWorkspaceOperationsQuery | None = None,
    ) -> OperationsModulePage:
        query = _normalize_query(query)
        facts = collect_context_workspace_page_facts(
            workspace_service=self.workspace_service,
            tree_service=self.tree_service,
            observation_snapshot_service=self.observation_snapshot_service,
            slice_builder=self.slice_builder,
            query=query,
        )
        sections = (
            table_section(
                section_id="workspaces",
                title="Context Workspaces",
                rows=facts.workspace_table_rows,
                total=len(facts.filtered_workspaces),
                empty_state="No context workspaces.",
            ),
            table_section(
                section_id="visible_nodes",
                title="Visible Nodes",
                rows=facts.node_table_rows,
                total=visible_node_count(facts.tree_views),
                empty_state="No context nodes.",
            ),
            table_section(
                section_id="node_status",
                title="Node Status",
                rows=facts.node_status_table_rows,
                total=facts.node_status_total,
                empty_state="No context node status.",
            ),
            table_section(
                section_id="snapshots",
                title="Context Snapshots",
                rows=facts.snapshot_table_rows,
                total=facts.snapshot_total,
                empty_state="No context snapshots.",
            ),
            table_section(
                section_id="context_budget",
                title="Context Budget",
                rows=facts.context_budget_table_rows,
                total=facts.snapshot_total,
                empty_state="No context budget snapshots.",
            ),
            table_section(
                section_id="observation_slices",
                title="Observation Slices",
                rows=facts.slice_rows,
                total=len(facts.slice_rows),
                empty_state="No operations projection slices.",
            ),
            table_section(
                section_id="diagnostics",
                title="Diagnostics",
                rows=facts.diagnostic_table_rows,
                total=len(facts.diagnostic_table_rows),
                empty_state="No diagnostics.",
            ),
        )
        return OperationsModulePage(
            module="context_workspace",
            title="Context Workspace",
            subtitle="观察会话绑定的 Context Tree、可见节点、估算体积与上下文快照。",
            health=facts.health,
            updated_at=format_datetime_utc(facts.now),
            auto_refresh=True,
            role=OperationsModuleRoleModel(
                label="Context Workspace operator",
                can_operate=True,
                scope="context_workspace",
            ),
            metrics=metrics(
                health=facts.health,
                workspaces=facts.filtered_workspaces,
                tree_views=facts.tree_views,
                snapshots=facts.snapshots,
                slice_rows=facts.slice_rows,
            ),
            tabs=tuple(
                OperationsTabModel(
                    id=section.id,
                    label=section.title,
                    count=section.total,
                )
                for section in sections
            ),
            active_tab="workspaces",
            actions=(
                RuntimeActionModel(
                    id="open_context_tree",
                    label="Open Context Tree",
                    owner="context_workspace",
                    kind="navigation",
                    allowed=True,
                ),
            ),
            sections=sections,
        )


def _normalize_query(
    query: ContextWorkspaceOperationsQuery | None,
) -> ContextWorkspaceOperationsQuery:
    if query is None:
        return ContextWorkspaceOperationsQuery()
    return ContextWorkspaceOperationsQuery(
        search=_text(query.search),
        limit=max(1, min(int(query.limit), 200)),
        offset=max(0, int(query.offset)),
    )


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()
