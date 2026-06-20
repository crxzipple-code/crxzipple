from __future__ import annotations

from hashlib import sha256

import pytest

from crxzipple.modules.context_workspace.application import (
    CONTEXT_INSTRUCTIONS_NODE_ID,
    CONTEXT_TREE_SCHEMA_VERSION,
    EXECUTION_CURRENT_NODE_ID,
    SESSION_CURRENT_NODE_ID,
    BuildContextControlSliceInput,
    ContextActionInput,
    ContextControlSliceService,
    ContextNodeUpsertInput,
    ContextSliceBuilderService,
    ContextObservationSnapshotService,
    ContextTreeService,
    ContextWorkspaceService,
    EnsureContextWorkspaceInput,
    RecordContextSnapshotInput,
    ContextObservationRenderInput,
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
    InMemoryContextSnapshotRepository,
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
    root_ids = [node.id for node in tree.nodes if node.parent_id is None]
    assert root_ids == [
        root_node_module.RUNTIME_ROOT_NODE_ID,
        root_node_module.TASK_ROOT_NODE_ID,
        root_node_module.SESSION_ROOT_NODE_ID,
        root_node_module.CAPABILITIES_ROOT_NODE_ID,
        root_node_module.KNOWLEDGE_ROOT_NODE_ID,
        root_node_module.RENDER_ROOT_NODE_ID,
    ]
    assert nodes_by_id[CONTEXT_INSTRUCTIONS_NODE_ID].parent_id == (
        root_node_module.RUNTIME_ROOT_NODE_ID
    )
    assert nodes_by_id[EXECUTION_CURRENT_NODE_ID].parent_id == (
        root_node_module.RUNTIME_ROOT_NODE_ID
    )
    assert nodes_by_id[SESSION_CURRENT_NODE_ID].parent_id == (
        root_node_module.SESSION_ROOT_NODE_ID
    )
    assert nodes_by_id["tools.available"].parent_id == (
        root_node_module.CAPABILITIES_ROOT_NODE_ID
    )
    assert nodes_by_id["skills.available"].parent_id == (
        root_node_module.CAPABILITIES_ROOT_NODE_ID
    )
    assert nodes_by_id["memory.visible"].parent_id == (
        root_node_module.KNOWLEDGE_ROOT_NODE_ID
    )
    assert nodes_by_id["artifacts.session"].parent_id == (
        root_node_module.KNOWLEDGE_ROOT_NODE_ID
    )
    assert nodes_by_id["runtime.contract"].parent_id == CONTEXT_INSTRUCTIONS_NODE_ID
    assert nodes_by_id["agent.identity"].parent_id == CONTEXT_INSTRUCTIONS_NODE_ID
    assert nodes_by_id["agent.home"].parent_id == CONTEXT_INSTRUCTIONS_NODE_ID
    assert nodes_by_id["context.priority"].parent_id == CONTEXT_INSTRUCTIONS_NODE_ID
    assert nodes_by_id["context.tree_usage"].parent_id == CONTEXT_INSTRUCTIONS_NODE_ID
    assert nodes_by_id["run.flow"].parent_id == EXECUTION_CURRENT_NODE_ID
    assert nodes_by_id["run.goal"].parent_id == root_node_module.TASK_ROOT_NODE_ID
    assert nodes_by_id["run.environment"].parent_id == EXECUTION_CURRENT_NODE_ID
    assert nodes_by_id["run.permissions"].parent_id == EXECUTION_CURRENT_NODE_ID
    assert nodes_by_id["run.provider"].parent_id == EXECUTION_CURRENT_NODE_ID
    assert nodes_by_id["run.context_budget"].parent_id == EXECUTION_CURRENT_NODE_ID
    assert nodes_by_id["run.constraints"].parent_id == EXECUTION_CURRENT_NODE_ID
    assert nodes_by_id["work.plan"].parent_id == root_node_module.TASK_ROOT_NODE_ID
    assert "evidence.frontier" not in nodes_by_id
    assert nodes_by_id["execution.continuation"].parent_id == EXECUTION_CURRENT_NODE_ID
    assert not any(
        node.parent_id == SESSION_CURRENT_NODE_ID
        for node in (
            nodes_by_id["runtime.contract"],
            nodes_by_id["agent.home"],
            nodes_by_id["run.flow"],
            nodes_by_id["run.environment"],
            nodes_by_id["work.plan"],
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
    assert workspace_resource.parent_id == root_node_module.KNOWLEDGE_ROOT_NODE_ID
    assert workspace_resource.kind == "workspace_resource_group"
    assert "Optional task workspace" in workspace_resource.summary


def test_control_slice_returns_refs_without_owner_refresh_or_content_resolution() -> None:
    services = _services()
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:control-slice",
            agent_id="assistant",
        ),
    )
    services["tree"].upsert_nodes(
        ContextNodeUpsertInput(
            session_key="session:control-slice",
            parent_node_id="session.current",
            action=ContextAction.EXPAND,
            nodes=(
                ContextNodeSeed(
                    node_id="session.step.item.control-user",
                    parent_id="session.current",
                    owner="session",
                    kind="session_item",
                    title="User Message",
                    content="this text must not enter the control slice",
                    state=ContextNodeState(included_in_next_slice=True),
                    owner_ref={
                        "session_item_id": "item-control-user",
                        "role": "user",
                    },
                ),
            ),
        ),
    )

    control_slice = services["control_slice"].build_control_slice(
        session_key="session:control-slice",
        run_id="run-control-slice",
    )

    selected = {
        item.node_id: item.to_payload()
        for item in control_slice.selected_refs
    }
    assert "session.step.item.control-user" in selected
    selected_item = selected["session.step.item.control-user"]
    assert selected_item["owner_ref"]["session_item_id"] == "item-control-user"
    assert "content" not in selected_item
    assert "text" not in selected_item
    assert control_slice.report.selected_node_ids


def test_llm_request_control_slice_scans_tree_and_preserves_protocol_refs() -> None:
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    workspace_service = ContextWorkspaceService(
        workspace_repository=workspaces,
        node_repository=nodes,
    )
    tree_service = ContextTreeService(
        workspace_repository=workspaces,
        node_repository=nodes,
        operation_repository=InMemoryContextOperationRepository(),
    )
    workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:hot-path-control-slice",
            agent_id="assistant",
            refresh_expanded_children=False,
        ),
    )
    tree_service.upsert_nodes(
        ContextNodeUpsertInput(
            session_key="session:hot-path-control-slice",
            parent_node_id="session.current",
            action=ContextAction.EXPAND,
            nodes=(
                ContextNodeSeed(
                    node_id="session.step.item.tree-user",
                    parent_id="session.current",
                    owner="session",
                    kind="session_item",
                    title="Tree selected user message",
                    state=ContextNodeState(included_in_next_slice=True),
                    owner_ref={
                        "session_item_id": "item-tree-user",
                        "role": "user",
                    },
                ),
            ),
        ),
    )
    control_slice_builder = ContextControlSliceService(
        workspace_repository=workspaces,
        node_repository=nodes,
    )

    control_slice = control_slice_builder.build_control_slice(
        data=BuildContextControlSliceInput(
            session_key="session:hot-path-control-slice",
            run_id="run-hot-path-control-slice",
            audience="llm_request",
            metadata={
                "protocol_required_refs": [
                    {
                        "session_item_id": "item-user-1",
                        "role": "user",
                        "owner_module": "session",
                        "owner_kind": "session_item",
                    },
                    {
                        "item_id": "item-tool-result-1",
                        "role": "tool",
                        "kind": "tool_result",
                    },
                ],
            },
        ),
    )

    assert control_slice.metadata["tree_scan_performed"] is True
    assert control_slice.report.metadata["tree_scan_performed"] is True
    session_item_ids = [
        item.owner_ref["session_item_id"]
        for item in control_slice.selected_refs
        if item.owner_ref.get("session_item_id")
    ]
    assert session_item_ids == [
        "item-tree-user",
        "item-user-1",
        "item-tool-result-1",
    ]
    session_item_kinds = [
        item.kind
        for item in control_slice.selected_refs
        if item.owner_ref.get("session_item_id")
    ]
    assert session_item_kinds == [
        "session_item",
        "session_item",
        "session_item",
    ]
    assert "session.step.item.tree-user" in control_slice.report.selected_node_ids


def test_control_slice_does_not_refresh_owner_children() -> None:
    class _ExplodingOwnerRegistry:
        def get(self, owner):  # noqa: ANN001
            raise AssertionError("control slice must not refresh owner children")

    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    workspace_service = ContextWorkspaceService(
        workspace_repository=workspaces,
        node_repository=nodes,
        owner_registry=_ExplodingOwnerRegistry(),
    )
    workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:control-no-refresh",
            agent_id="assistant",
            refresh_expanded_children=False,
        ),
    )
    control_slice_builder = ContextControlSliceService(
        workspace_repository=workspaces,
        node_repository=nodes,
    )

    control_slice = control_slice_builder.build_control_slice(
        session_key="session:control-no-refresh",
        run_id="run-control-no-refresh",
    )

    assert control_slice.session_key == "session:control-no-refresh"


def test_trace_slice_includes_execution_continuation_control_state() -> None:
    services = _services()
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:continuation-slice",
            agent_id="assistant",
            metadata={
                "execution_continuation_node": {
                    "summary": (
                        "Run is waiting for one background tool and approval."
                    ),
                    "content": "\n".join(
                        [
                            "Run status: waiting",
                            "Run stage: running",
                            "Waiting reason: waiting_for_tool",
                            "Pending background tool runs: tool-run-1",
                            "Pending approval: request_id=approval-1",
                        ],
                    ),
                    "metadata": {
                        "status": "waiting",
                        "waiting_reason": "waiting_for_tool",
                        "pending_tool_run_count": 1,
                        "pending_tool_run_ids": ["tool-run-1"],
                        "pending_approval_request_id": "approval-1",
                    },
                },
            },
        ),
    )

    llm_slice = services["slice"].build_slice(
        session_key="session:continuation-slice",
        run_id="run-continuation-slice",
    )
    context_slice = services["slice"].build_slice(
        session_key="session:continuation-slice",
        run_id="run-continuation-slice",
        audience="trace_timeline",
    )
    assert "execution.continuation" not in {
        item.item_id for item in llm_slice.items
    }
    continuation = next(
        item
        for item in context_slice.items
        if item.item_id == "execution.continuation"
    )

    assert continuation.owner == "orchestration"
    assert continuation.kind == "continuation_state"
    assert "Waiting reason: waiting_for_tool" in continuation.text
    assert continuation.owner_ref["pending_tool_run_count"] == 1
    assert continuation.owner_ref["pending_approval_request_id"] == "approval-1"
    assert continuation.metadata["status"] == "available"


def test_runtime_contract_loader_reads_versioned_prompt_asset() -> None:
    contract = load_runtime_contract()

    assert contract.version
    assert contract.content_hash == sha256(contract.content.encode("utf-8")).hexdigest()
    assert len(contract.content_hash) == 64
    assert "CRXZipple Runtime Contract" in contract.content
    assert "Runtime context is managed by CRXZipple" in contract.content
    assert "capability.search" in contract.content


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
            metadata={"workspace_dir": "/new", "runtime_request_surface": "interactive"},
        ),
    )

    assert updated.id == workspace.id
    assert updated.metadata["workspace_dir"] == "/new"
    assert updated.metadata["runtime_request_surface"] == "interactive"
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
                    summary="in_progress: tighten context tree tests",
                    content="working_plan:\n  objective: tighten context tree tests",
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

    assert plan_node.summary == "in_progress: tighten context tree tests"
    assert plan_node.parent_id == root_node_module.TASK_ROOT_NODE_ID
    assert "tighten context tree tests" in plan_node.content
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
    rendered = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:second"),
    )
    snapshot = services["render"].record_snapshot(
        RecordContextSnapshotInput(
            session_key="session:second",
            run_id="run:second",
            debug_body=rendered.debug_body,
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


def test_render_observation_and_snapshot_are_tree_backed() -> None:
    services = _services()
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:test",
            agent_id="assistant",
        ),
    )

    rendered = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:test", run_id="run-1"),
    )
    snapshot = services["render"].record_snapshot(
        RecordContextSnapshotInput(
            session_key="session:test",
            run_id="run-1",
            debug_body=rendered.debug_body,
            estimate=rendered.estimate,
            included_node_ids=rendered.included_node_ids,
        ),
    )

    assert "<context_tree" in rendered.debug_body
    assert f'schema_version="{CONTEXT_TREE_SCHEMA_VERSION}"' in rendered.debug_body
    assert "<context_instructions>" not in rendered.debug_body
    assert "context.instructions" in rendered.included_node_ids
    assert "runtime.contract" in rendered.included_node_ids
    assert "execution.continuation" in rendered.included_node_ids
    assert "CRXZipple Runtime Contract" in rendered.debug_body
    assert "Cite verified evidence labels" not in rendered.debug_body
    assert "Cite evidence labels" in rendered.debug_body
    assert "runtime_and_code" not in rendered.debug_body
    assert "network_truth" not in rendered.debug_body
    assert "context.tree_usage" in rendered.included_node_ids
    assert "Capability discovery usage:" not in rendered.debug_body
    assert "tools.available" in rendered.included_node_ids
    assert rendered.tree_schema_version == CONTEXT_TREE_SCHEMA_VERSION
    assert rendered.root_node_ids[:3] == (
        root_node_module.RUNTIME_ROOT_NODE_ID,
        root_node_module.TASK_ROOT_NODE_ID,
        root_node_module.SESSION_ROOT_NODE_ID,
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
    expanded_render = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:test", run_id="run-2"),
    )

    assert "Capability discovery usage:" in expanded_render.debug_body
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
    rendered = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:test", run_id="run-2"),
    )
    latest_tree = services["tree"].list_tree("session:test")
    latest_usage = next(
        node for node in latest_tree.nodes if node.id == "context.tree_usage"
    )

    assert "Capability discovery usage:" in rendered.debug_body
    assert not latest_usage.state.collapsed


def test_snapshots_keep_run_history_and_latest_lookup() -> None:
    services = _services()
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:test",
            agent_id="assistant",
        ),
    )
    rendered = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:test", run_id="run-1"),
    )
    first = services["render"].record_snapshot(
        RecordContextSnapshotInput(
            session_key="session:test",
            run_id="run-1",
            debug_body=rendered.debug_body,
            estimate=rendered.estimate,
            included_node_ids=("first",),
            snapshot_id="ctxsnap_first",
        ),
    )
    second = services["render"].record_snapshot(
        RecordContextSnapshotInput(
            session_key="session:test",
            run_id="run-1",
            debug_body=rendered.debug_body,
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


def test_render_observation_excludes_human_visible_hidden_nodes() -> None:
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
                    content="This blocked reason must not enter the agent context.",
                    state=ContextNodeState(
                        collapsed=False,
                        loaded=True,
                        snapshot_visible=False,
                    ),
                    actions=(ContextAction.PIN, ContextAction.UNPIN),
                    display_order=90,
                ),
            ),
        ),
    )

    tree = services["tree"].list_tree("session:test")
    rendered = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:test"),
    )

    assert any(node.id == "runtime.policy.blocked-detail" for node in tree.nodes)
    assert "runtime.policy.blocked-detail" not in rendered.included_node_ids
    assert "This blocked reason must not enter the agent context." not in (
        rendered.debug_body
    )


def test_render_prompt_merges_provider_attachments_from_input() -> None:
    services = _services()
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:test",
            agent_id="assistant",
        ),
    )

    rendered = services["render"].render_observation(
        ContextObservationRenderInput(
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


def test_context_slice_builder_excludes_runtime_control_nodes_from_llm_slice() -> None:
    services = _services()
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:slice",
            agent_id="assistant",
        ),
    )
    services["tree"].upsert_nodes(
        ContextNodeUpsertInput(
            session_key="session:slice",
            action=ContextAction.UPSERT,
            nodes=(
                ContextNodeSeed(
                    node_id="session.turn.current",
                    parent_id=SESSION_CURRENT_NODE_ID,
                    owner="session",
                    kind="session_turn",
                    title="Current Turn",
                    summary="Current turn run-1.",
                    state=ContextNodeState(collapsed=False, loaded=True),
                    owner_ref={"run_id": "run-1"},
                    display_order=10,
                ),
                ContextNodeSeed(
                    node_id="session.step.llm-1",
                    parent_id="session.turn.current",
                    owner="session",
                    kind="session_step",
                    title="LLM Step",
                    summary="LLM step completed.",
                    state=ContextNodeState(collapsed=False, loaded=True),
                    owner_ref={"step_id": "step-1"},
                    display_order=20,
                ),
                ContextNodeSeed(
                    node_id="session.step.item.llm-item-1",
                    parent_id="session.step.llm-1",
                    owner="session",
                    kind="runtime_llm_invocation",
                    title="LLM Invocation",
                    summary="llm_invocation; status=completed",
                    state=ContextNodeState(collapsed=True, loaded=True),
                    owner_ref={"llm_invocation_id": "llm-1"},
                    display_order=30,
                ),
                ContextNodeSeed(
                    node_id="tool.function.weather",
                    parent_id="tools.available",
                    owner="tool",
                    kind="tool_function",
                    title="Weather",
                    summary="Weather function.",
                    state=ContextNodeState(
                        collapsed=True,
                        loaded=True,
                        schema_enabled=True,
                    ),
                    owner_ref={
                        "source_id": "open_meteo",
                        "tool_id": "open_meteo_weather.forecast_weather",
                    },
                    display_order=40,
                ),
                ContextNodeSeed(
                    node_id="runtime.hidden",
                    parent_id=EXECUTION_CURRENT_NODE_ID,
                    owner="runtime",
                    kind="policy_detail",
                    title="Hidden",
                    summary="Hidden detail.",
                    state=ContextNodeState(
                        collapsed=False,
                        loaded=True,
                        snapshot_visible=False,
                    ),
                    display_order=50,
                ),
            ),
        ),
    )

    context_slice = services["slice"].build_slice(
        session_key="session:slice",
        run_id="run-1",
        provider_profile="codex",
    )
    trace_slice = services["slice"].build_slice(
        session_key="session:slice",
        run_id="run-1",
        audience="trace_timeline",
        provider_profile="codex",
    )

    item_ids = {item.item_id for item in context_slice.items}
    trace_item_ids = {item.item_id for item in trace_slice.items}
    assert "session.turn.current" not in item_ids
    assert "session.step.llm-1" not in item_ids
    assert "session.step.item.llm-item-1" not in item_ids
    assert "session.turn.current" in trace_item_ids
    assert "session.step.llm-1" in trace_item_ids
    assert "session.step.item.llm-item-1" in trace_item_ids
    assert "runtime.hidden" not in item_ids
    assert context_slice.report.loss["omitted_node_count"] >= 1
    assert [tool.function_name for tool in context_slice.active_tools] == [
        "open_meteo_weather.forecast_weather",
    ]
    assert context_slice.slice_id.startswith("ctxslice_")
    assert context_slice.audience == "llm_request"
    assert context_slice.metadata["provider_profile"] == "codex"
    assert context_slice.report.metadata["audience"] == "llm_request"


def test_context_slice_builder_applies_audience_boundaries() -> None:
    services = _services()
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:slice-audience",
            agent_id="assistant",
        ),
    )
    services["tree"].upsert_nodes(
        ContextNodeUpsertInput(
            session_key="session:slice-audience",
            action=ContextAction.UPSERT,
            nodes=(
                ContextNodeSeed(
                    node_id="session.item.user",
                    parent_id=SESSION_CURRENT_NODE_ID,
                    owner="session",
                    kind="session_item",
                    title="User Message",
                    summary="User asked for flights.",
                    content="Check official flights.",
                    state=ContextNodeState(collapsed=False, loaded=True),
                    display_order=10,
                ),
                ContextNodeSeed(
                    node_id="runtime.policy.visible",
                    parent_id=EXECUTION_CURRENT_NODE_ID,
                    owner="runtime",
                    kind="policy_detail",
                    title="Runtime Policy",
                    summary="Runtime policy detail.",
                    state=ContextNodeState(collapsed=False, loaded=True),
                    display_order=20,
                ),
                ContextNodeSeed(
                    node_id="runtime.policy.hidden",
                    parent_id=EXECUTION_CURRENT_NODE_ID,
                    owner="runtime",
                    kind="policy_detail",
                    title="Hidden Runtime Policy",
                    summary="Hidden runtime policy detail.",
                    state=ContextNodeState(
                        collapsed=False,
                        loaded=True,
                        snapshot_visible=False,
                    ),
                    display_order=30,
                ),
                ContextNodeSeed(
                    node_id="tool.function.command",
                    parent_id="tools.available",
                    owner="tool",
                    kind="tool_function",
                    title="Command",
                    summary="Command function.",
                    state=ContextNodeState(
                        collapsed=True,
                        loaded=True,
                        schema_enabled=True,
                    ),
                    owner_ref={
                        "source_id": "configured.command",
                        "tool_id": "command.exec",
                    },
                    display_order=40,
                ),
            ),
        ),
    )

    user_slice = services["slice"].build_slice(
        session_key="session:slice-audience",
        run_id="run-audience",
        audience="user_timeline",
    )
    trace_slice = services["slice"].build_slice(
        session_key="session:slice-audience",
        run_id="run-audience",
        audience="trace_timeline",
    )
    debug_slice = services["slice"].build_slice(
        session_key="session:slice-audience",
        run_id="run-audience",
        audience="debug_tree",
    )
    operations_slice = services["slice"].build_slice(
        session_key="session:slice-audience",
        run_id="run-audience",
        audience="operations_projection",
    )

    user_item_ids = {item.item_id for item in user_slice.items}
    trace_item_ids = {item.item_id for item in trace_slice.items}
    debug_item_ids = {item.item_id for item in debug_slice.items}
    operations_item_ids = {item.item_id for item in operations_slice.items}

    assert user_slice.audience == "user_timeline"
    assert "session.item.user" in user_item_ids
    assert "runtime.policy.visible" not in user_item_ids
    assert user_slice.active_tools == ()

    assert trace_slice.audience == "trace_timeline"
    assert "session.item.user" in trace_item_ids
    assert "runtime.policy.visible" in trace_item_ids
    assert "runtime.policy.hidden" not in trace_item_ids
    assert [tool.function_name for tool in trace_slice.active_tools] == [
        "command.exec",
    ]

    assert debug_slice.audience == "debug_tree"
    assert "runtime.policy.hidden" in debug_item_ids

    assert operations_slice.audience == "operations_projection"
    assert "tool.function.command" in operations_item_ids
    assert [tool.function_name for tool in operations_slice.active_tools] == [
        "command.exec",
    ]
    assert operations_slice.report.metadata["audience"] == "operations_projection"


def test_context_slice_builder_resolves_session_item_text_from_owner() -> None:
    services = _services(
        session_item_resolver=_FakeSessionItemResolver(
            {
                "item-1": _FakeSessionItem(
                    {
                        "blocks": [
                            {"type": "text", "text": "live owner text"},
                            {"type": "image_ref", "artifact_id": "artifact-1"},
                        ],
                    },
                ),
            },
        ),
    )
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:owner-resolve",
            agent_id="assistant",
        ),
    )
    services["tree"].upsert_nodes(
        ContextNodeUpsertInput(
            session_key="session:owner-resolve",
            action=ContextAction.UPSERT,
            nodes=(
                ContextNodeSeed(
                    node_id="session.item.item-1",
                    parent_id=SESSION_CURRENT_NODE_ID,
                    owner="session",
                    kind="session_item",
                    title="Assistant Message",
                    summary="Assistant message.",
                    content="stale tree text",
                    state=ContextNodeState(collapsed=False, loaded=True),
                    owner_ref={"session_item_id": "item-1"},
                    display_order=10,
                ),
            ),
        ),
    )

    context_slice = services["slice"].build_slice(
        session_key="session:owner-resolve",
        run_id="run-1",
        provider_profile="codex",
    )

    item = next(
        item
        for item in context_slice.items
        if item.item_id == "session.item.item-1"
    )
    assert item.text == "live owner text\n[image:artifact-1]"
    assert item.metadata["resolved_from_owner"] is True
    assert item.metadata["owner_resolution"] == "owner_resolved"
    assert context_slice.report.unresolved_refs == ()
    stored_node = services["nodes"].get(
        workspace_id=context_slice.metadata["workspace_id"],
        node_id="session.item.item-1",
    )
    assert stored_node is not None
    assert stored_node.content == "stale tree text"


def test_context_slice_does_not_fallback_to_session_node_content_without_resolver() -> None:
    services = _services()
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:no-resolver",
            agent_id="assistant",
        ),
    )
    services["tree"].upsert_nodes(
        ContextNodeUpsertInput(
            session_key="session:no-resolver",
            action=ContextAction.UPSERT,
            nodes=(
                ContextNodeSeed(
                    node_id="session.item.item-1",
                    parent_id=SESSION_CURRENT_NODE_ID,
                    owner="session",
                    kind="session_item",
                    title="User Message",
                    summary="User message.",
                    content="stale tree text must not become model input",
                    state=ContextNodeState(collapsed=False, loaded=True),
                    owner_ref={"session_item_id": "item-1"},
                    display_order=10,
                ),
            ),
        ),
    )

    context_slice = services["slice"].build_slice(
        session_key="session:no-resolver",
        run_id="run-1",
        provider_profile="codex",
    )

    item = next(
        item
        for item in context_slice.items
        if item.item_id == "session.item.item-1"
    )
    assert item.text == ""
    assert item.content is None
    assert item.metadata["resolved_from_owner"] is False
    assert item.metadata["owner_resolution"] == "owner_unresolved"
    assert context_slice.report.unresolved_refs[0]["reason"] == (
        "session_item_resolver_unavailable"
    )


def test_context_slice_does_not_embed_handle_only_owner_node_content() -> None:
    services = _services()
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:handle-only-content",
            agent_id="assistant",
        ),
    )
    services["tree"].upsert_nodes(
        ContextNodeUpsertInput(
            session_key="session:handle-only-content",
            action=ContextAction.UPSERT,
            nodes=(
                ContextNodeSeed(
                    node_id="agent.home.AGENT.md",
                    parent_id="agent.home",
                    owner="agent",
                    kind="agent_home_file",
                    title="AGENT.md",
                    summary="Agent home file handle.",
                    content="raw agent home body must not become model input",
                    state=ContextNodeState(pinned=True, loaded=True),
                    owner_ref={"name": "AGENT.md", "role": "agent_instructions"},
                    display_order=10,
                ),
            ),
        ),
    )

    context_slice = services["slice"].build_slice(
        session_key="session:handle-only-content",
        run_id="run-1",
        provider_profile="codex",
    )

    item = next(
        item
        for item in context_slice.items
        if item.item_id == "agent.home.AGENT.md"
    )
    assert item.text == ""
    assert item.content is None
    assert item.summary == "Agent home file handle."
    assert item.metadata["owner_resolution"] == "handle_only"


def test_context_slice_defaults_unknown_owner_content_to_handle_only() -> None:
    services = _services()
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:unknown-owner-content",
            agent_id="assistant",
        ),
    )
    services["tree"].upsert_nodes(
        ContextNodeUpsertInput(
            session_key="session:unknown-owner-content",
            action=ContextAction.UPSERT,
            nodes=(
                ContextNodeSeed(
                    node_id="external.debug.raw-1",
                    parent_id=root_node_module.RUNTIME_ROOT_NODE_ID,
                    owner="external_debug",
                    kind="diagnostic_blob",
                    title="Raw Diagnostic",
                    summary="Diagnostic handle.",
                    content="this raw diagnostic must not become model input",
                    state=ContextNodeState(included_in_next_slice=True, loaded=True),
                    owner_ref={"diagnostic_id": "raw-1"},
                    display_order=10,
                ),
            ),
        ),
    )

    context_slice = services["slice"].build_slice(
        session_key="session:unknown-owner-content",
        run_id="run-1",
        provider_profile="codex",
    )

    item = next(
        item for item in context_slice.items if item.item_id == "external.debug.raw-1"
    )
    assert item.text == ""
    assert item.content is None
    assert item.summary == "Diagnostic handle."
    assert item.metadata["owner_resolution"] == "handle_only"


def test_context_slice_allows_embedded_runtime_control_content() -> None:
    services = _services()
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:runtime-control-content",
            agent_id="assistant",
        ),
    )
    services["tree"].upsert_nodes(
        ContextNodeUpsertInput(
            session_key="session:runtime-control-content",
            action=ContextAction.UPSERT,
            nodes=(
                ContextNodeSeed(
                    node_id="task.runtime-control-goal",
                    parent_id=root_node_module.TASK_ROOT_NODE_ID,
                    owner="orchestration",
                    kind="run_goal",
                    title="Run Goal",
                    summary="Current goal.",
                    content="Use the official source and report uncertainty.",
                    state=ContextNodeState(included_in_next_slice=True, loaded=True),
                    owner_ref={"source": "test"},
                    display_order=10,
                ),
            ),
        ),
    )

    context_slice = services["slice"].build_slice(
        session_key="session:runtime-control-content",
        run_id="run-1",
        provider_profile="codex",
    )

    item = next(
        item
        for item in context_slice.items
        if item.item_id == "task.runtime-control-goal"
    )
    assert item.text == "Use the official source and report uncertainty."
    assert item.content is None
    assert item.metadata["owner_resolution"] == "embedded"


def test_debug_tree_does_not_render_handle_only_owner_node_content() -> None:
    services = _services()
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:handle-only-debug",
            agent_id="assistant",
        ),
    )
    services["tree"].upsert_nodes(
        ContextNodeUpsertInput(
            session_key="session:handle-only-debug",
            action=ContextAction.UPSERT,
            nodes=(
                ContextNodeSeed(
                    node_id="agent.home.AGENT.md",
                    parent_id="agent.home",
                    owner="agent",
                    kind="agent_home_file",
                    title="AGENT.md",
                    summary="Agent home file handle.",
                    content="raw agent home body must not become debug XML",
                    state=ContextNodeState(pinned=True, loaded=True),
                    owner_ref={"name": "AGENT.md", "role": "agent_instructions"},
                    display_order=10,
                ),
            ),
        ),
    )

    rendered = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:handle-only-debug"),
    )

    assert "Agent home file handle." in rendered.debug_body
    assert "raw agent home body must not become debug XML" not in rendered.debug_body


def test_context_slice_builder_reports_unresolved_session_item_refs_only() -> None:
    services = _services()
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:unresolved-ref",
            agent_id="assistant",
        ),
    )
    services["tree"].upsert_nodes(
        ContextNodeUpsertInput(
            session_key="session:unresolved-ref",
            action=ContextAction.UPSERT,
            nodes=(
                ContextNodeSeed(
                    node_id="session.item.item-1",
                    parent_id=SESSION_CURRENT_NODE_ID,
                    owner="session",
                    kind="session_item",
                    title="Assistant Message",
                    summary="Assistant message.",
                    content="",
                    state=ContextNodeState(collapsed=False, loaded=True),
                    owner_ref={"session_item_id": "item-1"},
                    display_order=10,
                ),
            ),
        ),
    )

    context_slice = services["slice"].build_slice(
        session_key="session:unresolved-ref",
        run_id="run-1",
        provider_profile="codex",
    )

    item = next(
        item
        for item in context_slice.items
        if item.item_id == "session.item.item-1"
    )
    assert item.text == ""
    assert item.metadata["resolved_from_owner"] is False
    assert item.metadata["owner_resolution"] == "owner_unresolved"
    assert context_slice.report.unresolved_refs == (
        {
            "node_id": "session.item.item-1",
            "owner": "session",
            "kind": "session_item",
            "owner_ref": {"session_item_id": "item-1"},
            "reason": "session_item_resolver_unavailable",
        },
    )
    assert context_slice.report.loss["unresolved_ref_count"] == 1


def test_context_slice_builder_keeps_non_session_owner_refs_handle_only() -> None:
    services = _services()
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:handle-only",
            agent_id="assistant",
            metadata={"workspace_dir": "/tmp/crxzipple-task-workspace"},
        ),
    )
    for node_id in (
        "skills.available",
        "artifacts.session",
        "memory.visible",
        "workspace.resources",
    ):
        services["tree"].apply_action(
            ContextActionInput(
                session_key="session:handle-only",
                node_id=node_id,
                action=ContextAction.EXPAND,
            ),
        )
    services["tree"].upsert_nodes(
        ContextNodeUpsertInput(
            session_key="session:handle-only",
            action=ContextAction.UPSERT,
            nodes=(
                ContextNodeSeed(
                    node_id="skills.available.skill.browser",
                    parent_id="skills.available",
                    owner="skills",
                    kind="skill",
                    title="Browser Skill",
                    summary="Use browser automation when needed.",
                    content="",
                    state=ContextNodeState(included_in_next_slice=True),
                    owner_ref={"skill_name": "browser", "resolved_path": "/skills/browser/SKILL.md"},
                    display_order=10,
                ),
                ContextNodeSeed(
                    node_id="artifacts.session.report-1",
                    parent_id="artifacts.session",
                    owner="artifacts",
                    kind="artifact",
                    title="Report",
                    summary="Flight evidence report.",
                    content="",
                    state=ContextNodeState(opened=True),
                    owner_ref={"artifact_id": "artifact-1"},
                    display_order=20,
                ),
                ContextNodeSeed(
                    node_id="memory.visible.item-1",
                    parent_id="memory.visible",
                    owner="memory",
                    kind="memory_item",
                    title="Preference",
                    summary="Use official sources first.",
                    content="",
                    state=ContextNodeState(pinned=True),
                    owner_ref={"memory_id": "memory-1"},
                    display_order=30,
                ),
                ContextNodeSeed(
                    node_id="workspace.resources.agents",
                    parent_id="workspace.resources",
                    owner="workspace",
                    kind="workspace_resource",
                    title="AGENTS.md",
                    summary="Repository agent contract handle.",
                    content="",
                    state=ContextNodeState(included_in_next_slice=True),
                    owner_ref={"path": "AGENTS.md"},
                    display_order=40,
                ),
            ),
        ),
    )

    context_slice = services["slice"].build_slice(
        session_key="session:handle-only",
        run_id="run-1",
        provider_profile="codex",
    )

    by_id = {item.item_id: item for item in context_slice.items}
    assert (
        by_id["skills.available.skill.browser"].metadata["owner_resolution"]
        == "handle_only"
    )
    assert (
        by_id["artifacts.session.report-1"].metadata["owner_resolution"]
        == "handle_only"
    )
    assert (
        by_id["memory.visible.item-1"].metadata["owner_resolution"]
        == "handle_only"
    )
    assert (
        by_id["workspace.resources.agents"].metadata["owner_resolution"]
        == "handle_only"
    )
    assert context_slice.report.unresolved_refs == ()
    assert context_slice.report.loss["unresolved_ref_count"] == 0


def test_context_slice_requires_explicit_or_protocol_tool_result_inclusion() -> None:
    services = _services()
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:tool-result-slice",
            agent_id="assistant",
        ),
    )
    services["tree"].upsert_nodes(
        ContextNodeUpsertInput(
            session_key="session:tool-result-slice",
            action=ContextAction.UPSERT,
            nodes=(
                ContextNodeSeed(
                    node_id="session.step.item.tool-result-default",
                    parent_id="session.current",
                    owner="session",
                    kind="runtime_tool_result",
                    title="Tool Result",
                    summary="Completed tool result.",
                    content="This result should stay out unless selected.",
                    state=ContextNodeState(collapsed=True),
                    owner_ref={
                        "tool_call_id": "call-default",
                        "tool_run_id": "tool-run-default",
                    },
                    display_order=10,
                ),
                ContextNodeSeed(
                    node_id="session.step.item.tool-result-protocol",
                    parent_id="session.current",
                    owner="session",
                    kind="runtime_tool_result",
                    title="Protocol Tool Result",
                    summary="Protocol-required tool result.",
                    content="This result must enter the next provider input.",
                    state=ContextNodeState(collapsed=True),
                    owner_ref={
                        "tool_call_id": "call-protocol",
                        "tool_run_id": "tool-run-protocol",
                        "protocol_required": True,
                    },
                    display_order=20,
                ),
                ContextNodeSeed(
                    node_id="session.step.item.tool-result-selected",
                    parent_id="session.current",
                    owner="session",
                    kind="runtime_tool_result",
                    title="Selected Tool Result",
                    summary="Explicitly selected tool result.",
                    content="This result is selected by tree state.",
                    state=ContextNodeState(included_in_next_slice=True),
                    owner_ref={
                        "tool_call_id": "call-selected",
                        "tool_run_id": "tool-run-selected",
                    },
                    display_order=30,
                ),
                ContextNodeSeed(
                    node_id="session.step.item.tool-result-pinned",
                    parent_id="session.current",
                    owner="session",
                    kind="runtime_tool_result",
                    title="Pinned Tool Result",
                    summary="Pinned tool result.",
                    content="This result is pinned by tree state.",
                    state=ContextNodeState(pinned=True),
                    owner_ref={
                        "tool_call_id": "call-pinned",
                        "tool_run_id": "tool-run-pinned",
                    },
                    display_order=40,
                ),
            ),
        ),
    )

    context_slice = services["slice"].build_slice(
        session_key="session:tool-result-slice",
        run_id="run-tool-result-slice",
    )
    item_ids = {item.item_id for item in context_slice.items}

    assert "session.step.item.tool-result-default" not in item_ids
    assert "session.step.item.tool-result-protocol" in item_ids
    assert "session.step.item.tool-result-selected" in item_ids
    assert "session.step.item.tool-result-pinned" in item_ids


class _FakeSessionItem:
    def __init__(self, content_payload: dict[str, object]) -> None:
        self.content_payload = content_payload


class _FakeSessionItemResolver:
    def __init__(self, items: dict[str, _FakeSessionItem]) -> None:
        self._items = items

    def get_item(self, item_id: str) -> _FakeSessionItem:
        return self._items[item_id]


class _FailingContextNodeRepository:
    def save(self, node):  # noqa: ANN001, ANN201
        raise AssertionError("llm request control slice must not save nodes")

    def save_many(self, nodes):  # noqa: ANN001, ANN201
        raise AssertionError("llm request control slice must not save nodes")

    def delete_subtrees(self, *, workspace_id, root_node_ids):  # noqa: ANN001, ANN201
        raise AssertionError("llm request control slice must not delete nodes")

    def get(self, *, workspace_id, node_id):  # noqa: ANN001, ANN201
        raise AssertionError("llm request control slice must not load nodes")

    def list_for_workspace(self, workspace_id):  # noqa: ANN001, ANN201
        raise AssertionError("llm request control slice must not scan tree")


def _services(session_item_resolver=None):  # noqa: ANN001
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
        "render": ContextObservationSnapshotService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
        "slice": ContextSliceBuilderService(
            workspace_repository=workspaces,
            node_repository=nodes,
            session_item_resolver=session_item_resolver,
        ),
        "control_slice": ContextControlSliceService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
        "operations": operations,
        "snapshots": snapshots,
        "nodes": nodes,
    }
