from __future__ import annotations

from datetime import datetime
from typing import Any

from crxzipple.modules.context_workspace.application import (
    ContextSliceBuilderService,
    ContextObservationSnapshotService,
    ContextTreeService,
    ContextWorkspaceService,
    EnsureContextWorkspaceInput,
    RecordContextSnapshotInput,
    ContextObservationRenderInput,
)
from crxzipple.modules.context_workspace.infrastructure import (
    InMemoryContextNodeRepository,
    InMemoryContextOperationRepository,
    InMemoryContextSnapshotRepository,
    InMemoryContextWorkspaceRepository,
)
from crxzipple.modules.operations.application.projections import (
    OPERATIONS_PROJECTION_MODULES,
    OperationsProjectionMaterializer,
)
from crxzipple.modules.operations.application.read_models.context_workspace import (
    ContextWorkspaceOperationsReadModelProvider,
)


def test_context_workspace_operations_page_exposes_tree_without_node_content() -> None:
    services = _context_services()
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:context",
            agent_id="assistant",
        ),
    )
    rendered = services["observation"].render_observation(
        ContextObservationRenderInput(session_key="session:context", run_id="run:context"),
    )
    services["observation"].record_snapshot(
        RecordContextSnapshotInput(
            session_key="session:context",
            run_id="run:context",
            debug_body=rendered.debug_body,
            estimate=rendered.estimate,
            included_node_ids=rendered.included_node_ids,
            metadata={
                "history_delivery": "context_tree",
                "draft_input_message_count": 1,
                "draft_input_estimated_tokens": 12,
                "mirrored_tool_schema_estimated_tokens": 34,
                "tool_schema_mirror_budget_status": "limited",
                "tool_schema_mirror_skipped_count": 2,
                "debug_body_estimated_tokens": 56,
                "estimated_provider_input_tokens": 102,
                "duplicate_tool_delivery_risk": True,
                "tree_session_item_count": 2,
                "tree_tool_interaction_count": 1,
                "tree_evidence_item_count": 4,
                "folded_history_node_count": 3,
                "session_estimated_text_tokens": 128,
                "session_range_warning_count": 1,
                "session_range_blocked_count": 0,
                "session_range_limited_count": 2,
                "session_item_node_refs": [
                    {"node_id": "session.item.active.1"},
                    {"node_id": "session.item.active.2"},
                ],
                "current_inbound_node_id": "session.item.active.2",
            },
        ),
    )
    provider = ContextWorkspaceOperationsReadModelProvider(
        workspace_service=services["workspace"],
        tree_service=services["tree"],
        observation_snapshot_service=services["observation"],
        slice_builder=services["slice"],
    )

    page = provider.page()
    overview = provider.overview()
    sections = {section.id: section for section in page.sections}

    assert page.module == "context_workspace"
    assert page.health == "healthy"
    assert sections["workspaces"].rows[0].cells["session"] == "session:context"
    assert sections["visible_nodes"].total >= 1
    assert "content" not in sections["visible_nodes"].rows[0].cells
    assert sections["node_status"].total >= 1
    node_status_rows = [row.cells for row in sections["node_status"].rows]
    context_workspace_root_row = next(
        row
        for row in node_status_rows
        if row["owner"] == "context_workspace" and row["kind"] == "runtime_root"
    )
    assert context_workspace_root_row["session"] == "session:context"
    assert context_workspace_root_row["total"] == "1"
    assert context_workspace_root_row["snapshot_visible"] == "1"
    assert context_workspace_root_row["collapsed"] == "0"
    assert "content" not in context_workspace_root_row
    assert sections["snapshots"].rows[0].cells["run"] == "run:context"
    assert sections["snapshots"].rows[0].cells["history"] == "context_tree"
    assert sections["snapshots"].rows[0].cells["tree_items"] == "2"
    assert sections["snapshots"].rows[0].cells["evidence"] == "4"
    assert sections["snapshots"].rows[0].cells["folded"] == "3"
    assert sections["snapshots"].rows[0].cells["session_tokens"] == "128"
    assert sections["snapshots"].rows[0].cells["range_warnings"] == "1"
    assert sections["snapshots"].rows[0].cells["range_limited"] == "2"
    assert sections["snapshots"].rows[0].cells["session_refs"] == "2"
    assert (
        sections["snapshots"].rows[0].cells["current_node"]
        == "session.item.active.2"
    )
    assert sections["context_budget"].rows[0].cells["provider_tokens"] == "102"
    assert sections["context_budget"].rows[0].cells["tree_tokens"] == "56"
    assert sections["context_budget"].rows[0].cells["draft_input_tokens"] == "12"
    assert sections["context_budget"].rows[0].cells["schema_tokens"] == "34"
    assert sections["context_budget"].rows[0].cells["schema_budget_status"] == "limited"
    assert sections["context_budget"].rows[0].cells["schema_budget_skipped"] == "2"
    assert sections["context_budget"].rows[0].cells["duplicate_risk"] == "yes"
    assert sections["observation_slices"].rows[0].cells["audience"] == (
        "operations_projection"
    )
    assert sections["observation_slices"].rows[0].cells["session"] == (
        "session:context"
    )
    assert sections["observation_slices"].rows[0].cells["run"] == "run:context"
    assert overview.module == "context_workspace"
    assert overview.queue[0]["session"] == "session:context"
    assert next(metric for metric in page.metrics if metric.id == "snapshot_tokens").value == "102"
    assert next(metric for metric in page.metrics if metric.id == "session_range_risks").value == "3"
    assert next(metric for metric in page.metrics if metric.id == "observation_slices").value == "1"


def test_context_workspace_projection_is_materialized_as_operations_module() -> None:
    provider = ContextWorkspaceOperationsReadModelProvider(
        workspace_service=None,
        tree_service=None,
        observation_snapshot_service=None,
    )
    store = _FakeProjectionStore()
    materializer = OperationsProjectionMaterializer(
        source_provider=_ContextWorkspaceProjectionSource(provider),
        projection_store=store,
    )

    materialized = materializer.materialize_modules(("context_workspace",))

    assert "context_workspace" in OPERATIONS_PROJECTION_MODULES
    assert materialized == 1
    assert store.records[("context_workspace", "page")]["payload"]["module"] == (
        "context_workspace"
    )
    assert store.records[("context_workspace", "overview")]["payload"]["module"] == (
        "context_workspace"
    )


def _context_services() -> dict[str, Any]:
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    operations = InMemoryContextOperationRepository()
    snapshots = InMemoryContextSnapshotRepository()
    return {
        "workspace": ContextWorkspaceService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
        "tree": ContextTreeService(
            workspace_repository=workspaces,
            node_repository=nodes,
            operation_repository=operations,
        ),
        "observation": ContextObservationSnapshotService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
        "slice": ContextSliceBuilderService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
    }


class _ContextWorkspaceProjectionSource:
    def __init__(self, provider: ContextWorkspaceOperationsReadModelProvider) -> None:
        self._provider = provider

    def context_workspace_page(self, query: Any | None = None) -> object:
        return self._provider.page(query)

    def module_overview(self, module: str) -> object:
        assert module == "context_workspace"
        return self._provider.overview()


class _FakeProjectionStore:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], dict[str, object]] = {}

    def record_projection(
        self,
        *,
        module: str,
        kind: str,
        payload: dict[str, object],
        query_key: str = "default",
        updated_at: datetime | None = None,
    ) -> None:
        self.records[(module, kind)] = {
            "payload": payload,
            "query_key": query_key,
            "updated_at": updated_at,
        }

    def clear(self, *, module: str | None = None, kind: str | None = None) -> int:
        removed = 0
        for key in tuple(self.records):
            record_module, record_kind = key
            if module is not None and record_module != module:
                continue
            if kind is not None and record_kind != kind:
                continue
            del self.records[key]
            removed += 1
        return removed
