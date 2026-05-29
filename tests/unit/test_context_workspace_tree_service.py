from __future__ import annotations

import pytest

from crxzipple.modules.context_workspace.application import (
    ContextActionInput,
    ContextRenderService,
    ContextTreeService,
    ContextWorkspaceService,
    EnsureContextWorkspaceInput,
    RecordContextRenderSnapshotInput,
    RenderContextPromptInput,
)
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextActionNotAllowedError,
)
from crxzipple.modules.context_workspace.infrastructure import (
    InMemoryContextNodeRepository,
    InMemoryContextOperationRepository,
    InMemoryContextRenderSnapshotRepository,
    InMemoryContextWorkspaceRepository,
)


def test_ensure_workspace_creates_default_root_nodes() -> None:
    services = _services()

    workspace = services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:test",
            agent_id="assistant",
        ),
    )
    tree = services["tree"].list_tree("session:test")

    assert tree.workspace.id == workspace.id
    assert [node.id for node in tree.nodes][:4] == [
        "agent.identity",
        "run.flow",
        "run.runtime",
        "session.current",
    ]
    assert tree.estimate.text_tokens > 0


def test_node_actions_update_state_revision_and_operation_log() -> None:
    services = _services()
    workspace = services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:test",
            agent_id="assistant",
        ),
    )
    previous_revision = workspace.active_revision

    result = services["tree"].apply_action(
        ContextActionInput(
            session_key="session:test",
            node_id="tools.available",
            action=ContextAction.EXPAND,
        ),
    )

    assert not result.node.state.collapsed
    assert result.node.state.loaded
    assert result.workspace.active_revision == previous_revision + 1
    assert services["operations"].list_for_workspace(workspace.id)[0].action is (
        ContextAction.EXPAND
    )


def test_ensure_workspace_merges_metadata_for_existing_workspace() -> None:
    services = _services()
    workspace = services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:test",
            agent_id="assistant",
            metadata={"workspace_dir": "/old"},
        ),
    )
    previous_revision = workspace.active_revision

    updated = services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:test",
            agent_id="assistant",
            metadata={"workspace_dir": "/new", "prompt_surface": "interactive"},
        ),
    )

    assert updated.id == workspace.id
    assert updated.metadata["workspace_dir"] == "/new"
    assert updated.metadata["prompt_surface"] == "interactive"
    assert updated.active_revision == previous_revision + 1


def test_ensure_workspace_refreshes_run_flow_node_from_metadata() -> None:
    services = _services()

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:test",
            agent_id="assistant",
            metadata={
                "run_flow_node": {
                    "mode": "heartbeat",
                    "title": "Flow: Heartbeat",
                    "summary": "Handle a lightweight heartbeat check.",
                    "metadata": {"mode": "heartbeat", "reason": "manual"},
                },
            },
        ),
    )
    flow_node = next(
        node
        for node in services["tree"].list_tree("session:test").nodes
        if node.id == "run.flow"
    )

    assert flow_node.owner == "orchestration"
    assert flow_node.kind == "run_flow"
    assert flow_node.title == "Flow: Heartbeat"
    assert "lightweight heartbeat" in flow_node.summary
    assert flow_node.metadata["reason"] == "manual"


def test_workspace_and_snapshot_services_list_recent_items() -> None:
    services = _services()
    first = services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:first",
            agent_id="assistant",
        ),
    )
    second = services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:second",
            agent_id="assistant",
        ),
    )
    rendered = services["render"].render_prompt_body(
        RenderContextPromptInput(session_key="session:second"),
    )
    snapshot = services["render"].record_render_snapshot(
        RecordContextRenderSnapshotInput(
            session_key="session:second",
            run_id="run:second",
            prompt_body=rendered.prompt_body,
            estimate=rendered.estimate,
            included_node_ids=rendered.included_node_ids,
        ),
    )

    workspaces = services["workspace"].list_workspaces(limit=10)
    snapshots = services["render"].list_recent_snapshots(limit=10)

    assert {workspace.id for workspace in workspaces} == {first.id, second.id}
    assert snapshots == (snapshot,)


def test_unsupported_action_is_rejected() -> None:
    services = _services()
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:test",
            agent_id="assistant",
        ),
    )

    with pytest.raises(ContextActionNotAllowedError):
        services["tree"].apply_action(
            ContextActionInput(
                session_key="session:test",
                node_id="session.current",
                action=ContextAction.ENABLE_TOOL_SCHEMA,
            ),
        )


def test_render_prompt_body_and_snapshot_are_tree_backed() -> None:
    services = _services()
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:test",
            agent_id="assistant",
        ),
    )

    rendered = services["render"].render_prompt_body(
        RenderContextPromptInput(session_key="session:test", run_id="run-1"),
    )
    snapshot = services["render"].record_render_snapshot(
        RecordContextRenderSnapshotInput(
            session_key="session:test",
            run_id="run-1",
            prompt_body=rendered.prompt_body,
            estimate=rendered.estimate,
            included_node_ids=rendered.included_node_ids,
        ),
    )

    assert "<context_tree" in rendered.prompt_body
    assert "tools.available" in rendered.included_node_ids
    assert services["snapshots"].get_by_run("run-1") == snapshot


def test_render_prompt_merges_provider_attachments_from_input() -> None:
    services = _services()
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:test",
            agent_id="assistant",
        ),
    )

    rendered = services["render"].render_prompt_body(
        RenderContextPromptInput(
            session_key="session:test",
            provider_attachments={
                "tool_schemas": [{"name": "existing", "input_schema": {}}],
                "images": [{"id": "image-1"}],
            },
        ),
    )

    assert rendered.provider_attachments == {
        "tool_schemas": [{"name": "existing", "input_schema": {}}],
        "images": [{"id": "image-1"}],
    }


def _services():
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
        "operations": operations,
        "snapshots": snapshots,
    }
