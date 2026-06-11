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


def test_workspace_adapter_expands_task_workspace_resource_file_handles(tmp_path) -> None:
    (tmp_path / "AGENTS.md").write_text(
        "# Agent Contract\n\nFollow the project boundaries.",
        encoding="utf-8",
    )
    (tmp_path / "BOOTSTRAP.md").write_text(
        "Prepare this workspace before a turn.",
        encoding="utf-8",
    )
    (tmp_path / "TOOLS.md").write_text(
        "Use project tools when grounded facts are needed.",
        encoding="utf-8",
    )
    for name in ("AGENT.md", "SOUL.md", "USER.md", "IDENTITY.md"):
        (tmp_path / name).write_text(
            f"{name} belongs to agent home, not workspace resources.",
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
            node_id="workspace.resources",
            action=ContextAction.EXPAND,
        ),
    )
    tree = services["tree"].list_tree("session:workspace")
    file_nodes = [
        node for node in tree.nodes if node.parent_id == "workspace.resources"
    ]

    assert [node.title for node in file_nodes] == [
        "AGENTS.md",
        "BOOTSTRAP.md",
        "TOOLS.md",
    ]
    assert "Follow the project boundaries" in file_nodes[0].summary
    assert file_nodes[0].owner_ref == {"path": "AGENTS.md"}
    assert file_nodes[0].metadata["source"] == "workspace.resources"
    assert {"AGENT.md", "SOUL.md", "USER.md", "IDENTITY.md"}.isdisjoint(
        {node.title for node in file_nodes},
    )


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
