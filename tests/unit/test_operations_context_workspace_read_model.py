from __future__ import annotations

from datetime import datetime
from typing import Any

from crxzipple.modules.context_workspace.application import (
    ContextRenderService,
    ContextTreeService,
    ContextWorkspaceService,
    EnsureContextWorkspaceInput,
    RecordContextRenderSnapshotInput,
    RenderContextPromptInput,
)
from crxzipple.modules.context_workspace.infrastructure import (
    InMemoryContextNodeRepository,
    InMemoryContextOperationRepository,
    InMemoryContextRenderSnapshotRepository,
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
    rendered = services["render"].render_prompt_body(
        RenderContextPromptInput(session_key="session:context", run_id="run:context"),
    )
    services["render"].record_render_snapshot(
        RecordContextRenderSnapshotInput(
            session_key="session:context",
            run_id="run:context",
            prompt_body=rendered.prompt_body,
            estimate=rendered.estimate,
            included_node_ids=rendered.included_node_ids,
        ),
    )
    provider = ContextWorkspaceOperationsReadModelProvider(
        workspace_service=services["workspace"],
        tree_service=services["tree"],
        render_service=services["render"],
    )

    page = provider.page()
    overview = provider.overview()
    sections = {section.id: section for section in page.sections}

    assert page.module == "context_workspace"
    assert page.health == "healthy"
    assert sections["workspaces"].rows[0].cells["session"] == "session:context"
    assert sections["visible_nodes"].total >= 1
    assert "content" not in sections["visible_nodes"].rows[0].cells
    assert sections["render_snapshots"].rows[0].cells["run"] == "run:context"
    assert overview.module == "context_workspace"
    assert overview.queue[0]["session"] == "session:context"


def test_context_workspace_projection_is_materialized_as_operations_module() -> None:
    provider = ContextWorkspaceOperationsReadModelProvider(
        workspace_service=None,
        tree_service=None,
        render_service=None,
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
    snapshots = InMemoryContextRenderSnapshotRepository()
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
        "render": ContextRenderService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
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
