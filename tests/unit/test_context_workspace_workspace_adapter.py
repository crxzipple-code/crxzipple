from __future__ import annotations

from crxzipple.app.integration.context_workspace_workspace import (
    WorkspaceContextNodeProvider,
)
from crxzipple.modules.context_workspace.application import (
    ContextActionInput,
    ContextOwnerRegistry,
    ContextSliceBuilderService,
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
    assert "Follow the project boundaries" not in file_nodes[0].summary
    assert "available through workspace file tools" in file_nodes[0].summary
    assert file_nodes[0].owner_ref == {"path": "AGENTS.md"}
    assert file_nodes[0].metadata["source"] == "workspace.resources"
    assert file_nodes[0].metadata["content_available_via"] == "workspace_read"
    assert {"AGENT.md", "SOUL.md", "USER.md", "IDENTITY.md"}.isdisjoint(
        {node.title for node in file_nodes},
    )

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:workspace",
            node_id=file_nodes[0].id,
            action=ContextAction.PIN,
        ),
    )
    context_slice = services["slice"].build_slice(
        session_key="session:workspace",
        run_id="run-workspace",
        provider_profile="codex",
    )
    slice_items = {item.item_id: item for item in context_slice.items}
    workspace_item = slice_items[file_nodes[0].id]

    assert "Follow the project boundaries" not in workspace_item.summary
    assert "Follow the project boundaries" not in workspace_item.text
    assert workspace_item.metadata["owner_resolution"] == "handle_only"


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
        "slice": ContextSliceBuilderService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
    }
