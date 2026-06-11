from __future__ import annotations

from hashlib import sha256

import pytest

from crxzipple.modules.context_workspace.application import (
    CONTEXT_INSTRUCTIONS_NODE_ID,
    CONTEXT_TREE_SCHEMA_VERSION,
    EXECUTION_CURRENT_NODE_ID,
    SESSION_CURRENT_NODE_ID,
    ContextActionInput,
    ContextNodeUpsertInput,
    ContextRenderService,
    ContextTreeService,
    ContextWorkspaceService,
    EnsureContextWorkspaceInput,
    RecordContextRenderSnapshotInput,
    RenderContextPromptInput,
)
from crxzipple.modules.context_workspace.application.runtime_contract import (
    load_runtime_contract,
)
import crxzipple.modules.context_workspace.application.root_nodes as root_node_module
import crxzipple.modules.context_workspace.application.runtime_contract as runtime_contract_module
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextActionNotAllowedError,
    ContextNodeSeed,
    ContextNodeState,
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
    nodes_by_id = {node.id: node for node in tree.nodes}
    assert [node.id for node in tree.nodes[:3]] == [
        CONTEXT_INSTRUCTIONS_NODE_ID,
        "runtime.contract",
        "execution.guide",
    ]
    root_ids = [node.id for node in tree.nodes if node.parent_id is None]
    assert root_ids == [
        CONTEXT_INSTRUCTIONS_NODE_ID,
        EXECUTION_CURRENT_NODE_ID,
        SESSION_CURRENT_NODE_ID,
        "tools.available",
        "skills.available",
        "memory.visible",
        "artifacts.session",
    ]
    assert nodes_by_id["runtime.contract"].parent_id == CONTEXT_INSTRUCTIONS_NODE_ID
    assert nodes_by_id["agent.identity"].parent_id == CONTEXT_INSTRUCTIONS_NODE_ID
    assert nodes_by_id["agent.home"].parent_id == CONTEXT_INSTRUCTIONS_NODE_ID
    assert nodes_by_id["context.priority"].parent_id == CONTEXT_INSTRUCTIONS_NODE_ID
    assert nodes_by_id["context.tree_usage"].parent_id == CONTEXT_INSTRUCTIONS_NODE_ID
    assert nodes_by_id["run.flow"].parent_id == EXECUTION_CURRENT_NODE_ID
    assert nodes_by_id["run.goal"].parent_id == EXECUTION_CURRENT_NODE_ID
    assert nodes_by_id["run.environment"].parent_id == EXECUTION_CURRENT_NODE_ID
    assert nodes_by_id["run.permissions"].parent_id == EXECUTION_CURRENT_NODE_ID
    assert nodes_by_id["run.provider"].parent_id == EXECUTION_CURRENT_NODE_ID
    assert nodes_by_id["run.context_budget"].parent_id == EXECUTION_CURRENT_NODE_ID
    assert nodes_by_id["run.constraints"].parent_id == EXECUTION_CURRENT_NODE_ID
    assert nodes_by_id["work.plan"].parent_id == EXECUTION_CURRENT_NODE_ID
    assert nodes_by_id["evidence.frontier"].parent_id == EXECUTION_CURRENT_NODE_ID
    assert nodes_by_id["execution.continuation"].parent_id == EXECUTION_CURRENT_NODE_ID
    assert not any(
        node.parent_id == SESSION_CURRENT_NODE_ID
        for node in (
            nodes_by_id["runtime.contract"],
            nodes_by_id["agent.home"],
            nodes_by_id["run.flow"],
            nodes_by_id["run.environment"],
            nodes_by_id["work.plan"],
            nodes_by_id["evidence.frontier"],
            nodes_by_id["execution.continuation"],
        )
    )
    runtime_contract = nodes_by_id["runtime.contract"]
    assert runtime_contract.owner == "runtime"
    assert runtime_contract.kind == "runtime_contract"
    assert not runtime_contract.state.collapsed
    assert runtime_contract.metadata["contract_version"]
    assert runtime_contract.metadata["content_hash"]
    assert "workspace.resources" not in {node.id for node in tree.nodes}
    assert tree.estimate.text_tokens > 0


def test_workspace_resource_root_is_only_created_for_bound_workspace() -> None:
    services = _services()

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:workspace",
            agent_id="assistant",
            metadata={"workspace_dir": "/tmp/crxzipple-task-workspace"},
        ),
    )
    tree = services["tree"].list_tree("session:workspace")

    workspace_resource = next(
        node for node in tree.nodes if node.id == "workspace.resources"
    )
    assert workspace_resource.kind == "workspace_resource_group"
    assert "Optional task workspace" in workspace_resource.summary


def test_runtime_contract_loader_reads_versioned_prompt_asset() -> None:
    contract = load_runtime_contract()

    assert contract.version
    assert contract.content_hash == sha256(contract.content.encode("utf-8")).hexdigest()
    assert len(contract.content_hash) == 64
    assert "CRXZipple Runtime Contract" in contract.content
    assert "Context Tree is the prompt surface" in contract.content


def test_runtime_contract_loader_rejects_empty_prompt_asset(monkeypatch) -> None:
    class _EmptyPromptResource:
        def joinpath(self, _filename):  # noqa: ANN001, ANN201
            return self

        def read_text(self, *, encoding):  # noqa: ANN001, ANN201
            assert encoding == "utf-8"
            return "   "

    monkeypatch.setattr(
        runtime_contract_module,
        "files",
        lambda _package: _EmptyPromptResource(),
    )

    with pytest.raises(RuntimeError, match="empty"):
        load_runtime_contract()


def test_runtime_contract_loader_surfaces_missing_prompt_asset(monkeypatch) -> None:
    class _MissingPromptResource:
        def joinpath(self, _filename):  # noqa: ANN001, ANN201
            return self

        def read_text(self, *, encoding):  # noqa: ANN001, ANN201
            assert encoding == "utf-8"
            raise FileNotFoundError("runtime_contract.md")

    monkeypatch.setattr(
        runtime_contract_module,
        "files",
        lambda _package: _MissingPromptResource(),
    )

    with pytest.raises(FileNotFoundError):
        load_runtime_contract()


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


def test_pin_state_is_scoped_to_context_workspace_session() -> None:
    services = _services()
    first_workspace = services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:first",
            agent_id="assistant",
        ),
    )
    second_workspace = services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:second",
            agent_id="assistant",
        ),
    )

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:first",
            node_id="tools.available",
            action=ContextAction.PIN,
        ),
    )
    first_tree = services["tree"].list_tree("session:first")
    second_tree = services["tree"].list_tree("session:second")
    first_tools = next(node for node in first_tree.nodes if node.id == "tools.available")
    second_tools = next(node for node in second_tree.nodes if node.id == "tools.available")

    assert first_workspace.id != second_workspace.id
    assert first_tools.state.pinned
    assert not second_tools.state.pinned


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
            metadata={"workspace_dir": "/new", "prompt_input": "interactive"},
        ),
    )

    assert updated.id == workspace.id
    assert updated.metadata["workspace_dir"] == "/new"
    assert updated.metadata["prompt_input"] == "interactive"
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
    assert flow_node.parent_id == EXECUTION_CURRENT_NODE_ID
    assert flow_node.title == "Flow: Heartbeat"
    assert "lightweight heartbeat" in flow_node.summary
    assert flow_node.metadata["reason"] == "manual"


def test_ensure_workspace_preserves_visible_working_plan_node() -> None:
    services = _services()
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:test",
            agent_id="assistant",
        ),
    )
    services["tree"].upsert_nodes(
        ContextNodeUpsertInput(
            session_key="session:test",
            action=ContextAction.UPSERT,
            nodes=(
                ContextNodeSeed(
                    node_id="work.plan",
                    owner="context_workspace",
                    kind="working_plan",
                    title="Working Plan",
                    summary="in_progress: tighten prompt tree tests",
                    content="working_plan:\n  objective: tighten prompt tree tests",
                    state=ContextNodeState(
                        collapsed=False,
                        loaded=True,
                        pinned=True,
                    ),
                    actions=(
                        ContextAction.PIN,
                        ContextAction.UNPIN,
                        ContextAction.ESTIMATE,
                    ),
                    owner_ref={"status": "in_progress", "public_plan": True},
                    display_order=18,
                    metadata={
                        "status": "in_progress",
                        "public_plan": True,
                    },
                ),
            ),
        ),
    )

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:test",
            agent_id="assistant",
            metadata={"workspace_dir": "/tmp/new"},
        ),
    )
    plan_node = next(
        node
        for node in services["tree"].list_tree("session:test").nodes
        if node.id == "work.plan"
    )

    assert plan_node.summary == "in_progress: tighten prompt tree tests"
    assert plan_node.parent_id == EXECUTION_CURRENT_NODE_ID
    assert "tighten prompt tree tests" in plan_node.content
    assert plan_node.state.pinned
    assert plan_node.owner_ref["status"] == "in_progress"
    assert plan_node.metadata["public_plan"] is True


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
    assert f'schema_version="{CONTEXT_TREE_SCHEMA_VERSION}"' in rendered.prompt_body
    assert "<context_instructions>" not in rendered.prompt_body
    assert "context.instructions" in rendered.included_node_ids
    assert "runtime.contract" in rendered.included_node_ids
    assert "execution.continuation" in rendered.included_node_ids
    assert "CRXZipple Runtime Contract" in rendered.prompt_body
    assert "Cite verified evidence labels" in rendered.prompt_body
    assert "runtime_and_code" not in rendered.prompt_body
    assert "network_truth" not in rendered.prompt_body
    assert "context.tree_usage" in rendered.included_node_ids
    assert "Context Tree usage:" not in rendered.prompt_body
    assert "tools.available" in rendered.included_node_ids
    assert rendered.tree_schema_version == CONTEXT_TREE_SCHEMA_VERSION
    assert rendered.root_node_ids[:3] == (
        CONTEXT_INSTRUCTIONS_NODE_ID,
        EXECUTION_CURRENT_NODE_ID,
        SESSION_CURRENT_NODE_ID,
    )
    assert services["snapshots"].get_by_run("run-1") == snapshot
    assert snapshot.metadata["tree_schema_version"] == CONTEXT_TREE_SCHEMA_VERSION

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:test",
            node_id="context.tree_usage",
            action=ContextAction.EXPAND,
        ),
    )
    expanded_render = services["render"].render_prompt_body(
        RenderContextPromptInput(session_key="session:test", run_id="run-2"),
    )

    assert "Context Tree usage:" in expanded_render.prompt_body
    assert snapshot.metadata["context_instructions_node_id"] == (
        CONTEXT_INSTRUCTIONS_NODE_ID
    )
    assert snapshot.metadata["execution_current_node_id"] == EXECUTION_CURRENT_NODE_ID
    assert snapshot.metadata["session_current_node_id"] == SESSION_CURRENT_NODE_ID


def test_static_guide_nodes_refresh_once_then_preserve_user_state() -> None:
    services = _services()
    workspace = services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:test",
            agent_id="assistant",
        ),
    )
    usage_node = services["nodes"].get(
        workspace_id=workspace.id,
        node_id="context.tree_usage",
    )
    assert usage_node is not None
    usage_node.revision = None
    usage_node.apply_state(ContextNodeState(collapsed=False, loaded=True))
    services["nodes"].save(usage_node)

    refreshed_tree = services["tree"].list_tree("session:test")
    refreshed_usage = next(
        node for node in refreshed_tree.nodes if node.id == "context.tree_usage"
    )

    assert refreshed_usage.revision == root_node_module.CONTEXT_STATIC_GUIDE_REVISION
    assert refreshed_usage.state.collapsed

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:test",
            node_id="context.tree_usage",
            action=ContextAction.EXPAND,
        ),
    )
    rendered = services["render"].render_prompt_body(
        RenderContextPromptInput(session_key="session:test", run_id="run-2"),
    )
    latest_tree = services["tree"].list_tree("session:test")
    latest_usage = next(
        node for node in latest_tree.nodes if node.id == "context.tree_usage"
    )

    assert "Context Tree usage:" in rendered.prompt_body
    assert not latest_usage.state.collapsed


def test_render_snapshots_keep_run_history_and_latest_lookup() -> None:
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
    first = services["render"].record_render_snapshot(
        RecordContextRenderSnapshotInput(
            session_key="session:test",
            run_id="run-1",
            prompt_body=rendered.prompt_body,
            estimate=rendered.estimate,
            included_node_ids=("first",),
            snapshot_id="ctxsnap_first",
        ),
    )
    second = services["render"].record_render_snapshot(
        RecordContextRenderSnapshotInput(
            session_key="session:test",
            run_id="run-1",
            prompt_body=rendered.prompt_body,
            estimate=rendered.estimate,
            included_node_ids=("second",),
            snapshot_id="ctxsnap_second",
        ),
    )

    assert services["snapshots"].get_by_run("run-1") == second
    assert {item.id for item in services["render"].list_recent_snapshots(limit=10)} >= {
        first.id,
        second.id,
    }


def test_render_prompt_body_excludes_human_visible_hidden_nodes() -> None:
    services = _services()
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:test",
            agent_id="assistant",
        ),
    )
    services["tree"].upsert_nodes(
        ContextNodeUpsertInput(
            session_key="session:test",
            parent_node_id="run.environment",
            action=ContextAction.ESTIMATE,
            nodes=(
                ContextNodeSeed(
                    node_id="runtime.policy.blocked-detail",
                    parent_id="run.environment",
                    owner="runtime",
                    kind="policy_detail",
                    title="Blocked Detail",
                    summary="Visible only to human/runtime control.",
                    content="This blocked reason must not enter the agent prompt.",
                    state=ContextNodeState(
                        collapsed=False,
                        loaded=True,
                        prompt_visible=False,
                    ),
                    actions=(ContextAction.PIN, ContextAction.UNPIN),
                    display_order=90,
                ),
            ),
        ),
    )

    tree = services["tree"].list_tree("session:test")
    rendered = services["render"].render_prompt_body(
        RenderContextPromptInput(session_key="session:test"),
    )

    assert any(node.id == "runtime.policy.blocked-detail" for node in tree.nodes)
    assert "runtime.policy.blocked-detail" not in rendered.included_node_ids
    assert "This blocked reason must not enter the agent prompt." not in (
        rendered.prompt_body
    )


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
        "nodes": nodes,
    }
