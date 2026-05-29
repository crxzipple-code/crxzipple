from __future__ import annotations

from crxzipple.app.integration.context_workspace_workspace import (
    WorkspaceContextNodeProvider,
)
from crxzipple.modules.context_workspace.application import (
    ContextActionInput,
    ContextOwnerRegistry,
    ContextTreeService,
    ContextWorkspaceService,
    EnsureContextWorkspaceInput,
)
from crxzipple.modules.context_workspace.domain import ContextAction
from crxzipple.modules.context_workspace.infrastructure import (
    InMemoryContextNodeRepository,
    InMemoryContextOperationRepository,
    InMemoryContextWorkspaceRepository,
)


def test_workspace_adapter_expands_bootstrap_file_handles(tmp_path) -> None:
    (tmp_path / "AGENTS.md").write_text(
        "# Agent Contract\n\nFollow the project boundaries.",
        encoding="utf-8",
    )
    (tmp_path / "SOUL.md").write_text(
        "A short runtime identity note.",
        encoding="utf-8",
    )
    services = _context_services()

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:workspace",
            agent_id="assistant",
            metadata={"workspace_dir": str(tmp_path)},
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:workspace",
            node_id="workspace.bootstrap",
            action=ContextAction.EXPAND,
        ),
    )
    tree = services["tree"].list_tree("session:workspace")
    file_nodes = [
        node for node in tree.nodes if node.parent_id == "workspace.bootstrap"
    ]

    assert [node.title for node in file_nodes] == ["AGENTS.md", "SOUL.md"]
    assert "Follow the project boundaries" in file_nodes[0].summary
    assert file_nodes[0].owner_ref == {"path": "AGENTS.md"}
    assert file_nodes[0].metadata["source"] == "workspace.bootstrap"


def _context_services():
    registry = ContextOwnerRegistry()
    registry.register(WorkspaceContextNodeProvider())
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    operations = InMemoryContextOperationRepository()
    return {
        "workspace": ContextWorkspaceService(
            workspace_repository=workspaces,
            node_repository=nodes,
            owner_registry=registry,
        ),
        "tree": ContextTreeService(
            workspace_repository=workspaces,
            node_repository=nodes,
            operation_repository=operations,
            owner_registry=registry,
        ),
    }
