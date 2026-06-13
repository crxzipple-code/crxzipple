from __future__ import annotations

import pytest

from crxzipple.app.integration.context_workspace_orchestration.adapter import (
    ContextWorkspacePromptSnapshotAdapter,
)
from crxzipple.modules.artifacts.application.services import ArtifactBinary
from crxzipple.modules.artifacts.domain.entities import (
    Artifact,
    ArtifactKind,
    ArtifactVariant,
)
from crxzipple.modules.context_workspace.application import (
    CONTEXT_INSTRUCTIONS_NODE_ID,
    CONTEXT_TREE_SCHEMA_VERSION,
    EXECUTION_CURRENT_NODE_ID,
    SESSION_CURRENT_NODE_ID,
    ContextNodeUpsertInput,
    ContextRenderService,
    ContextTreeService,
    ContextWorkspaceService,
    EnsureContextWorkspaceInput,
)
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextEstimate,
    ContextNodeSeed,
    ContextNodeState,
)
from crxzipple.modules.context_workspace.infrastructure import (
    InMemoryContextNodeRepository,
    InMemoryContextOperationRepository,
    InMemoryContextRenderSnapshotRepository,
    InMemoryContextWorkspaceRepository,
)
from crxzipple.modules.llm.domain import (
    LlmCapability,
    LlmMessage,
    LlmMessageRole,
    ToolSchema,
)
from crxzipple.modules.orchestration.application.engine import OrchestrationEngine
from crxzipple.modules.orchestration.application.engine_session_recorder import (
    InboundSessionRecord,
)
from crxzipple.modules.orchestration.application.ports import (
    ContextRenderSnapshotRecord,
)
from crxzipple.modules.orchestration.application.prompt_input import (
    RunPromptInput,
)
from crxzipple.modules.orchestration.application.prompting import (
    PromptBlock,
    PromptMode,
    PromptReport,
)
from crxzipple.modules.orchestration.application.tool_resolver import (
    ResolvedTool,
    ResolvedToolSet,
)
from crxzipple.modules.orchestration.domain import (
    InboundInstruction,
    OrchestrationRun,
    OrchestrationValidationError,
)
from crxzipple.modules.tool.domain import Tool, ToolExecutionTarget


def test_context_workspace_adapter_records_tree_snapshot_for_run_prompt() -> None:
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    snapshots = InMemoryContextRenderSnapshotRepository()
    adapter = ContextWorkspacePromptSnapshotAdapter(
        workspace_service=ContextWorkspaceService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
        render_service=ContextRenderService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
    )

    snapshot_record = adapter.record_run_prompt_snapshot(
        run=_run(),
        prompt=_prompt(
            tool_schemas=(ToolSchema(name="fetch_weather", description="Fetch weather."),),
        ),
    )
    snapshot = snapshots.get_by_run("run-context")
    workspace = workspaces.get_by_session("session:context")

    assert snapshot is not None
    assert workspace is not None
    assert snapshot_record is not None
    assert snapshot_record.snapshot_id == snapshot.id
    assert snapshot_record.prompt_body == snapshot.prompt_body
    persisted_estimate = snapshot.estimate.to_payload()
    assert persisted_estimate["text_chars"] == len(snapshot.prompt_body)
    assert persisted_estimate["text_tokens"] == snapshot.metadata[
        "rendered_prompt_estimated_tokens"
    ]
    assert {
        key: value
        for key, value in snapshot_record.estimate.items()
        if key in persisted_estimate
    } == persisted_estimate
    assert "breakdown" in snapshot_record.estimate
    assert snapshot_record.included_node_ids == snapshot.included_node_ids
    assert snapshot_record.tool_schemas is None
    assert snapshot_record.tool_schema_mirror_available is False
    assert "<context_tree" in snapshot.prompt_body
    assert "run.flow" in snapshot.included_node_ids
    assert "run.goal" in snapshot.included_node_ids
    assert "run.environment" in snapshot.included_node_ids
    assert "run.permissions" in snapshot.included_node_ids
    assert "run.provider" in snapshot.included_node_ids
    assert "run.context_budget" in snapshot.included_node_ids
    assert "run.constraints" in snapshot.included_node_ids
    assert "evidence.frontier" in snapshot.included_node_ids
    assert "execution.continuation" in snapshot.included_node_ids
    assert "session.current" in snapshot.included_node_ids
    continuation_node = nodes.get(
        workspace_id=workspace.id,
        node_id="execution.continuation",
    )
    assert continuation_node is not None
    assert continuation_node.parent_id == EXECUTION_CURRENT_NODE_ID
    assert continuation_node.metadata["status"] == "accepted"
    assert continuation_node.metadata["stage"] == "accepted"
    assert "No pending public continuation state." in continuation_node.content
    assert snapshot.provider_attachments["prompt_input"]["session_item_count"] == 1
    assert workspace.metadata["available_tool_names"] == ["fetch_weather"]
    assert workspace.metadata["run_flow_node"]["mode"] == "normal_turn"
    assert snapshot.metadata["parallel_recording"] is True
    assert snapshot.metadata["tree_schema_version"] == CONTEXT_TREE_SCHEMA_VERSION
    assert snapshot.metadata["root_node_ids"][:3] == [
        CONTEXT_INSTRUCTIONS_NODE_ID,
        EXECUTION_CURRENT_NODE_ID,
        SESSION_CURRENT_NODE_ID,
    ]
    assert snapshot.metadata["context_instructions_node_id"] == (
        CONTEXT_INSTRUCTIONS_NODE_ID
    )
    assert snapshot.metadata["execution_current_node_id"] == EXECUTION_CURRENT_NODE_ID
    assert snapshot.metadata["session_current_node_id"] == SESSION_CURRENT_NODE_ID
    assert snapshot.metadata["history_delivery"] == "context_tree"
    assert snapshot.metadata["runtime_contract_version"] == "2026-06-10"
    assert snapshot.metadata["runtime_contract_hash"]
    assert snapshot.metadata["runtime_contract"]["node_id"] == "runtime.contract"
    assert snapshot_record.metadata["runtime_contract_version"] == "2026-06-10"
    assert snapshot.metadata["direct_transcript_message_count"] == 1
    assert snapshot.metadata["direct_transcript_roles"] == ["user"]
    assert snapshot.metadata["direct_transcript_chars"] == len("hello tree")
    assert snapshot.metadata["direct_transcript_estimated_tokens"] > 0
    assert snapshot.metadata["rendered_prompt_chars"] == len(snapshot.prompt_body)
    assert snapshot.metadata["rendered_prompt_estimated_tokens"] > 0
    assert snapshot.metadata["rendered_prompt_estimate"]["text_chars"] == len(
        snapshot.prompt_body,
    )
    assert snapshot.metadata["node_visible_estimate"]["text_chars"] >= 0
    assert "rendered_prompt" in snapshot.metadata["node_estimate_breakdown"]
    assert "node_visible" in snapshot.metadata["node_estimate_breakdown"]
    assert snapshot.metadata["node_estimate_breakdown"]["plan"]["present"] is True
    assert snapshot.metadata["work_plan_status"] == "empty"
    assert snapshot.metadata["work_plan_update_count"] == 0
    top_rendered_nodes = snapshot.metadata["node_estimate_breakdown"][
        "top_rendered_nodes"
    ]
    assert top_rendered_nodes
    assert snapshot.metadata["top_rendered_nodes"] == top_rendered_nodes
    assert top_rendered_nodes[0]["node_id"]
    assert top_rendered_nodes[0]["text_chars"] >= top_rendered_nodes[-1]["text_chars"]
    assert snapshot.metadata["mirrored_tool_schema_estimated_tokens"] == 0
    assert snapshot.metadata["estimated_provider_prompt_tokens"] >= (
        snapshot.metadata["rendered_prompt_estimated_tokens"]
        + snapshot.metadata["direct_transcript_estimated_tokens"]
    )
    assert snapshot.metadata["duplicate_tool_delivery_risk"] is False
    assert snapshot.metadata["tree_session_item_count"] == 0
    assert snapshot.metadata["session_item_node_refs"] == []
    assert snapshot.metadata["current_inbound_node_id"] is None
    assert snapshot.metadata["tree_tool_interaction_count"] == 0
    assert snapshot.metadata["tool_interaction_node_refs"] == []
    assert snapshot.metadata["tree_evidence_item_count"] == 0
    assert snapshot.metadata["evidence_node_refs"] == []
    assert snapshot.metadata["node_estimate_breakdown"]["evidence"][
        "final_response_requires_evidence_path"
    ] is False
    assert snapshot.metadata["final_response_requires_evidence_path"] is False
    assert snapshot.metadata["verified_evidence_path_count"] == 0
    assert snapshot.metadata["verified_evidence_paths"] == []
    assert snapshot.metadata["browser_verified_evidence_path_count"] == 0
    assert snapshot.metadata["browser_verified_evidence_paths"] == []
    assert snapshot.metadata["session_estimated_text_tokens"] >= 0
    assert snapshot.metadata["session_item_range_node_count"] >= 0
    assert snapshot.metadata["session_range_warning_count"] == 0
    assert snapshot.metadata["session_range_blocked_count"] == 0
    assert snapshot.metadata["session_range_limited_count"] == 0
    assert snapshot.metadata["session_budget_status"] == "ok"
    assert snapshot.metadata["artifact_content_block_count"] == 0
    assert snapshot.metadata["artifact_content_estimated_tokens"] == 0
    assert snapshot.metadata["artifact_content_candidate_count"] == 0
    assert snapshot.metadata["artifact_content_budget"]["status"] == "ok"
    assert "current_inbound_message_id" not in snapshot.metadata
    assert snapshot.metadata["current_inbound_session_item_id"] == "item-user-1"


def test_context_workspace_snapshot_records_direct_session_item_refs() -> None:
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    snapshots = InMemoryContextRenderSnapshotRepository()
    adapter = ContextWorkspacePromptSnapshotAdapter(
        workspace_service=ContextWorkspaceService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
        render_service=ContextRenderService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
    )

    snapshot_record = adapter.record_run_prompt_snapshot(
        run=_run(),
        prompt=_prompt(
            extra_messages=(
                LlmMessage(
                    role=LlmMessageRole.ASSISTANT,
                    content={
                        "type": "function_call",
                        "call_id": "call-weather-1",
                        "name": "weather.lookup",
                        "arguments": {"city": "Kunming"},
                    },
                    metadata={
                        "session_item_id": "item-call-1",
                        "session_id": "session-instance-1",
                        "sequence_no": 2,
                        "kind": "tool_call",
                        "phase": "commentary",
                        "source_module": "llm",
                        "source_kind": "llm_response_item",
                        "source_id": "llm-item-1",
                        "provider_item_id": "provider-call-1",
                        "tool_call_id": "call-weather-1",
                        "tool_name": "weather.lookup",
                    },
                ),
                LlmMessage(
                    role=LlmMessageRole.TOOL,
                    content=[{"type": "text", "text": "sunny"}],
                    tool_call_id="call-weather-1",
                    name="weather.lookup",
                    metadata={
                        "session_item_id": "item-result-1",
                        "session_id": "session-instance-1",
                        "sequence_no": 3,
                        "kind": "tool_result",
                        "phase": "unknown",
                        "source_module": "tool",
                        "source_kind": "tool_run",
                        "source_id": "tool-run-1",
                        "tool_call_id": "call-weather-1",
                        "tool_name": "weather.lookup",
                        "tool_status": "succeeded",
                    },
                ),
            ),
        ),
    )
    snapshot = snapshots.get_by_run("run-context")

    assert snapshot is not None
    assert snapshot_record is not None
    assert snapshot.metadata["direct_session_item_count"] == 3
    assert snapshot.metadata["direct_session_item_frontier"] == {
        "from_sequence_no": 1,
        "to_sequence_no": 3,
        "item_count": 3,
        "from_item_id": "item-user-1",
        "to_item_id": "item-result-1",
    }
    assert snapshot.metadata["direct_transcript_budget"]["source"] == "session_items"
    assert (
        snapshot.metadata["direct_transcript_budget"][
            "protocol_required_preserved"
        ]
        is True
    )
    assert [
        ref["item_id"] for ref in snapshot.metadata["direct_session_item_refs"]
    ] == ["item-user-1", "item-call-1", "item-result-1"]
    assert [ref["item_id"] for ref in snapshot.included_refs] == [
        "item-user-1",
        "item-call-1",
        "item-result-1",
    ]
    assert snapshot.metadata["protocol_required_ref_count"] == 2
    assert [
        ref["item_id"] for ref in snapshot.metadata["protocol_required_refs"]
    ] == ["item-call-1", "item-result-1"]
    assert [ref["item_id"] for ref in snapshot.protocol_required_refs] == [
        "item-call-1",
        "item-result-1",
    ]
    assert snapshot.metadata["protocol_required_refs"][0]["budget_class"] == (
        "protocol_required"
    )
    assert snapshot_record.metadata["direct_session_item_count"] == 3
    assert [ref["item_id"] for ref in snapshot_record.included_refs] == [
        "item-user-1",
        "item-call-1",
        "item-result-1",
    ]
    assert [ref["item_id"] for ref in snapshot_record.protocol_required_refs] == [
        "item-call-1",
        "item-result-1",
    ]
    assert snapshot.provider_attachments["prompt_input"]["session_item_count"] == 3
    assert (
        snapshot.provider_attachments["prompt_input"]["transcript_budget_source"]
        == "session_items"
    )
    assert (
        snapshot.provider_attachments["prompt_input"]["transcript_budget_truncated"]
        is False
    )
    assert snapshot.provider_attachments["prompt_input"]["transcript_frontier"] == {
        "from_sequence_no": 1,
        "to_sequence_no": 3,
        "from_item_id": "item-user-1",
        "to_item_id": "item-result-1",
        "item_count": 3,
    }
    assert (
        snapshot.provider_attachments["prompt_input"]["protocol_required_ref_count"]
        == 2
    )
    assert [
        ref["item_id"] for ref in snapshot.provider_attachments["session_item_refs"]
    ] == ["item-user-1", "item-call-1", "item-result-1"]


def test_context_workspace_snapshot_merges_execution_chain_protocol_refs() -> None:
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    snapshots = InMemoryContextRenderSnapshotRepository()
    adapter = ContextWorkspacePromptSnapshotAdapter(
        workspace_service=ContextWorkspaceService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
        render_service=ContextRenderService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
    )

    execution_ref = {
        "owner_module": "orchestration",
        "owner_kind": "execution_step_item",
        "owner_id": "item-exec-result-1",
        "execution_step_item_id": "item-exec-result-1",
        "execution_step_id": "step-tools",
        "execution_chain_id": "chain-run-context",
        "turn_id": "run-context",
        "kind": "tool_result",
        "tool_call_id": "call-weather-1",
        "tool_name": "weather.lookup",
        "tool_run_id": "tool-run-1",
        "result_session_item_id": "item-result-1",
        "protocol_required": True,
        "budget_class": "protocol_required",
        "render_mode": "ref",
        "visibility": "model_visible",
    }
    snapshot_record = adapter.record_run_prompt_snapshot(
        run=_run(),
        prompt=_prompt(
            transcript_budget={
                "source": "session_items",
                "protocol_required_refs": [execution_ref],
                "execution_chain_protocol_required_refs": [execution_ref],
                "execution_chain_protocol_required_ref_count": 1,
                "protocol_required_preserved": True,
            },
        ),
    )
    snapshot = snapshots.get_by_run("run-context")

    assert snapshot is not None
    assert snapshot_record is not None
    assert snapshot.metadata["execution_chain_protocol_required_ref_count"] == 1
    assert snapshot.metadata["execution_chain_protocol_required_refs"][0][
        "execution_step_item_id"
    ] == "item-exec-result-1"
    assert any(
        ref.get("execution_step_item_id") == "item-exec-result-1"
        for ref in snapshot.metadata["protocol_required_refs"]
    )
    assert any(
        ref.get("execution_step_item_id") == "item-exec-result-1"
        for ref in snapshot.protocol_required_refs
    )
    assert (
        snapshot.provider_attachments["prompt_input"][
            "protocol_required_ref_count"
        ]
        == 1
    )
    assert snapshot.provider_attachments["execution_chain_protocol_required_refs"][0][
        "tool_run_id"
    ] == "tool-run-1"


def test_context_workspace_adapter_forwards_prompt_flow_default_tool_schemas() -> None:
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    snapshots = InMemoryContextRenderSnapshotRepository()
    workspace_service = ContextWorkspaceService(
        workspace_repository=workspaces,
        node_repository=nodes,
    )
    tree_service = ContextTreeService(
        workspace_repository=workspaces,
        node_repository=nodes,
        operation_repository=InMemoryContextOperationRepository(),
    )
    adapter = ContextWorkspacePromptSnapshotAdapter(
        workspace_service=workspace_service,
        render_service=ContextRenderService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
    )
    workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:context",
            agent_id="assistant",
        ),
    )
    tree_service.upsert_nodes(
        ContextNodeUpsertInput(
            session_key="session:context",
            parent_node_id="tools.available",
            action=ContextAction.EXPAND,
            nodes=(
                ContextNodeSeed(
                    node_id="tools.tool.fetch_weather",
                    parent_id="tools.available",
                    owner="tool",
                    kind="tool_function",
                    title="Fetch Weather",
                    summary="Fetch current weather for a location.",
                    state=ContextNodeState(collapsed=False, loaded=True),
                    owner_ref={"tool_id": "fetch_weather"},
                    metadata={
                        "provider_schema": {
                            "name": "fetch_weather",
                            "description": "Fetch current weather.",
                            "input_schema": {
                                "type": "object",
                                "properties": {
                                    "location": {"type": "string"},
                                },
                                "required": ["location"],
                            },
                        },
                    },
                ),
            ),
        ),
    )

    snapshot_record = adapter.record_run_prompt_snapshot(
        run=_run(),
        prompt=_prompt(
            tool_schemas=(ToolSchema(name="fetch_weather", description="Fetch weather."),),
            flow_hint={
                "default_tool_schema_ids": ["fetch_weather"],
                "default_tool_schema_source": "runtime_policy.browser_bootstrap",
            },
        ),
    )
    snapshot = snapshots.get_by_run("run-context")
    tree = tree_service.list_tree("session:context")
    tool_node = next(node for node in tree.nodes if node.id == "tools.tool.fetch_weather")

    assert snapshot is not None
    assert snapshot_record is not None
    assert snapshot_record.tool_schemas is not None
    assert [schema.name for schema in snapshot_record.tool_schemas] == ["fetch_weather"]
    assert snapshot.metadata["tool_schema_mirror_budget"]["default_schema_source"] == (
        "runtime_policy.browser_bootstrap"
    )
    assert snapshot.metadata["tool_schema_mirror_budget"]["default_requested_count"] == 1
    assert snapshot.metadata["tool_schema_mirror_budget"]["default_mirrored_count"] == 1
    assert tool_node.state.schema_enabled is False


def test_context_workspace_adapter_expands_prompt_flow_tool_schema_groups() -> None:
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    snapshots = InMemoryContextRenderSnapshotRepository()
    workspace_service = ContextWorkspaceService(
        workspace_repository=workspaces,
        node_repository=nodes,
    )
    tree_service = ContextTreeService(
        workspace_repository=workspaces,
        node_repository=nodes,
        operation_repository=InMemoryContextOperationRepository(),
    )
    adapter = ContextWorkspacePromptSnapshotAdapter(
        workspace_service=workspace_service,
        render_service=ContextRenderService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
        tree_service=tree_service,
    )
    workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:context",
            agent_id="assistant",
        ),
    )
    common_actions = (ContextAction.EXPAND, ContextAction.COLLAPSE)
    tree_service.upsert_nodes(
        ContextNodeUpsertInput(
            session_key="session:context",
            parent_node_id="tools.available",
            action=ContextAction.EXPAND,
            nodes=(
                ContextNodeSeed(
                    node_id="tools.bundle.bundled.local_package.browser",
                    parent_id="tools.available",
                    owner="tool",
                    kind="tool_bundle",
                    title="Browser",
                    summary="Browser tools.",
                    state=ContextNodeState(collapsed=True, loaded=True),
                    actions=common_actions,
                    owner_ref={"source_id": "bundled.local_package.browser"},
                    metadata={"source_id": "bundled.local_package.browser"},
                ),
                ContextNodeSeed(
                    node_id="tools.bundle.bundled.local_package.browser.group.observation",
                    parent_id="tools.bundle.bundled.local_package.browser",
                    owner="tool",
                    kind="tool_bundle_group",
                    title="Browser Observation",
                    summary="Observe browser state.",
                    state=ContextNodeState(collapsed=True, loaded=True),
                    actions=common_actions,
                    owner_ref={
                        "source_id": "bundled.local_package.browser",
                        "group_key": "observation",
                    },
                    metadata={
                        "default_tool_schema_ids": ["browser.observe"],
                        "default_tool_schema_source": (
                            "bundled.local_package.browser.prompt_group.observation"
                        ),
                        "default_tool_schema_max_count": 1,
                    },
                ),
                ContextNodeSeed(
                    node_id="tools.tool.browser.observe",
                    parent_id="tools.bundle.bundled.local_package.browser.group.observation",
                    owner="tool",
                    kind="tool_function",
                    title="browser.observe",
                    summary="Inspect page state.",
                    state=ContextNodeState(collapsed=False, loaded=True),
                    owner_ref={"tool_id": "browser.observe"},
                    metadata={
                        "provider_schema": {
                            "name": "browser.observe",
                            "description": "Inspect browser page state.",
                            "input_schema": {"type": "object", "properties": {}},
                        },
                    },
                ),
            ),
        ),
    )

    snapshot_record = adapter.record_run_prompt_snapshot(
        run=_run(),
        prompt=_prompt(
            tool_schemas=(
                ToolSchema(
                    name="browser.observe",
                    description="Inspect browser page state.",
                ),
            ),
            flow_hint={
                "default_tool_schema_group_refs": [
                    {
                        "source_id": "bundled.local_package.browser",
                        "group_key": "observation",
                    },
                ],
            },
        ),
    )
    snapshot = snapshots.get_by_run("run-context")
    tree = tree_service.list_tree("session:context")
    group_node = next(
        node
        for node in tree.nodes
        if node.id == "tools.bundle.bundled.local_package.browser.group.observation"
    )
    tool_node = next(node for node in tree.nodes if node.id == "tools.tool.browser.observe")

    assert snapshot is not None
    assert snapshot_record is not None
    assert snapshot_record.tool_schemas is not None
    assert [schema.name for schema in snapshot_record.tool_schemas] == [
        "browser.observe",
    ]
    assert group_node.state.collapsed is False
    assert tool_node.state.schema_enabled is False
    assert snapshot.metadata["tool_schema_mirror_budget"]["default_schema_source"] == (
        "bundled.local_package.browser.prompt_group.observation"
    )
    assert snapshot.metadata["tool_schema_mirror_budget"]["default_requested_count"] == 1
    assert snapshot.metadata["tool_schema_mirror_budget"]["default_mirrored_count"] == 1


def test_context_workspace_adapter_bootstraps_browser_starter_schemas_from_source_policy() -> None:
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    snapshots = InMemoryContextRenderSnapshotRepository()
    workspace_service = ContextWorkspaceService(
        workspace_repository=workspaces,
        node_repository=nodes,
    )
    tree_service = ContextTreeService(
        workspace_repository=workspaces,
        node_repository=nodes,
        operation_repository=InMemoryContextOperationRepository(),
    )
    adapter = ContextWorkspacePromptSnapshotAdapter(
        workspace_service=workspace_service,
        render_service=ContextRenderService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
        tree_service=tree_service,
    )
    workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:context",
            agent_id="assistant",
        ),
    )
    group_defaults = {
        "navigation": ("browser.navigate", "browser.tabs.list"),
        "observation": ("browser.observe",),
        "network": ("browser.network.inspect",),
        "code_insight": ("browser.runtime.inspect", "browser.script.find_request"),
        "action_trace": ("browser.action.trace",),
    }
    common_actions = (ContextAction.EXPAND, ContextAction.COLLAPSE)
    tree_service.upsert_nodes(
        ContextNodeUpsertInput(
            session_key="session:context",
            parent_node_id="tools.available",
            action=ContextAction.EXPAND,
            nodes=(
                ContextNodeSeed(
                    node_id="tools.bundle.bundled.local_package.browser",
                    parent_id="tools.available",
                    owner="tool",
                    kind="tool_bundle",
                    title="Browser",
                    summary="Browser tools.",
                    state=ContextNodeState(collapsed=True, loaded=True),
                    actions=common_actions,
                    owner_ref={"source_id": "bundled.local_package.browser"},
                    metadata={
                        "source_id": "bundled.local_package.browser",
                        "prompt": {
                            "default_tool_schema_group_refs": [
                                {
                                    "source_id": "bundled.local_package.browser",
                                    "group_key": group_key,
                                    "reason": f"browser_starter_{group_key}",
                                }
                                for group_key in group_defaults
                            ],
                        },
                    },
                ),
                *(
                    seed
                    for index, (group_key, tool_ids) in enumerate(
                        group_defaults.items(),
                        start=1,
                    )
                    for seed in (
                        _browser_group_seed(
                            group_key=group_key,
                            tool_ids=tool_ids,
                            display_order=index * 10,
                        ),
                        *(
                            _browser_tool_seed(
                                tool_id=tool_id,
                                parent_id=(
                                    "tools.bundle.bundled.local_package.browser"
                                    f".group.{group_key}"
                                ),
                                display_order=tool_index * 10,
                            )
                            for tool_index, tool_id in enumerate(tool_ids, start=1)
                        ),
                    )
                ),
            ),
        ),
    )

    snapshot_record = adapter.record_run_prompt_snapshot(
        run=_run(),
        prompt=_prompt(
            tool_schemas=tuple(
                ToolSchema(name=tool_id, description=f"{tool_id} tool.")
                for tool_ids in group_defaults.values()
                for tool_id in tool_ids
            ),
        ),
    )
    snapshot = snapshots.get_by_run("run-context")

    assert snapshot is not None
    assert snapshot_record is not None
    assert snapshot_record.tool_schemas is not None
    mirrored_names = {schema.name for schema in snapshot_record.tool_schemas}
    assert mirrored_names >= {
        "browser.navigate",
        "browser.tabs.list",
        "browser.observe",
        "browser.network.inspect",
        "browser.runtime.inspect",
        "browser.script.find_request",
        "browser.action.trace",
    }
    budget = snapshot.metadata["tool_schema_mirror_budget"]
    assert budget["default_requested_count"] == 7
    assert budget["default_mirrored_count"] == 7
    assert budget["default_group_ref_count"] == 5
    assert {
        ref.get("reason")
        for ref in budget["default_group_refs"]
        if isinstance(ref, dict)
    } >= {"browser_starter_network", "browser_starter_code_insight"}
    assert snapshot.metadata["tool_schema_mirror_default_group_ref_count"] == 5
    assert {
        ref.get("reason")
        for ref in snapshot.metadata["tool_schema_mirror_default_group_refs"]
        if isinstance(ref, dict)
    } >= {"browser_starter_network", "browser_starter_code_insight"}
    assert snapshot.metadata["tool_schema_mirror_default_group_match_count"] == 5
    assert {
        match.get("reason")
        for match in snapshot.metadata["tool_schema_mirror_default_group_matches"]
        if isinstance(match, dict)
    } >= {"browser_starter_network", "browser_starter_code_insight"}
    assert snapshot.metadata["tool_schema_mirror_default_schema_reasons"][
        "browser.network.inspect"
    ] == "browser_starter_network"
    assert snapshot.metadata["tool_schema_mirror_default_mirrored"]


def test_context_workspace_snapshot_metadata_locates_session_item_nodes() -> None:
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    snapshots = InMemoryContextRenderSnapshotRepository()
    workspace_service = ContextWorkspaceService(
        workspace_repository=workspaces,
        node_repository=nodes,
    )
    tree_service = ContextTreeService(
        workspace_repository=workspaces,
        node_repository=nodes,
        operation_repository=InMemoryContextOperationRepository(),
    )
    adapter = ContextWorkspacePromptSnapshotAdapter(
        workspace_service=workspace_service,
        render_service=ContextRenderService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
    )
    workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:context",
            agent_id="assistant",
        ),
    )
    tree_service.upsert_nodes(
        ContextNodeUpsertInput(
            session_key="session:context",
            parent_node_id="session.current",
            action=ContextAction.EXPAND,
            nodes=(
                ContextNodeSeed(
                    node_id="session.items.current",
                    parent_id="session.current",
                    owner="session",
                    kind="session_item_range",
                    title="Current Items",
                    summary="Current active messages.",
                    state=ContextNodeState(collapsed=False, loaded=True),
                ),
                ContextNodeSeed(
                    node_id="session.item.session-instance-1.1",
                    parent_id="session.items.current",
                    owner="session",
                    kind="session_item",
                    title="1. user",
                    summary="Delivered as provider user message for this turn.",
                    state=ContextNodeState(collapsed=False, loaded=True),
                    owner_ref={
                        "session_id": "session-instance-1",
                        "message_id": "message-user-1",
                        "sequence_no": 1,
                    },
                ),
                ContextNodeSeed(
                    node_id="session.evidence.current",
                    parent_id="session.current",
                    owner="session",
                    kind="evidence_ledger",
                    title="Current Evidence Ledger",
                    summary="One compact evidence item.",
                    state=ContextNodeState(collapsed=False, loaded=True),
                ),
                ContextNodeSeed(
                    node_id="session.evidence.session-instance-1.call-weather",
                    parent_id="session.evidence.current",
                    owner="session",
                    kind="session_evidence",
                    title="observation: browser.network.replay_request",
                    summary="browser.network.replay_request succeeded.",
                    state=ContextNodeState(collapsed=False, loaded=True),
                    metadata={
                        "tool_name": "browser.network.replay_request",
                        "verified": True,
                        "facts": {"evidence_path": "network_truth"},
                    },
                    owner_ref={"evidence_lifecycle_status": "verified"},
                ),
            ),
        ),
    )

    adapter.record_run_prompt_snapshot(run=_run(), prompt=_prompt())
    snapshot = snapshots.get_by_run("run-context")

    assert snapshot is not None
    assert snapshot.metadata["tree_session_item_count"] == 1
    assert snapshot.metadata["session_item_node_refs"] == [
        {
            "node_id": "session.item.session-instance-1.1",
            "session_id": "session-instance-1",
            "sequence_no": 1,
        },
    ]
    assert (
        snapshot.metadata["current_inbound_node_id"]
        == "session.item.session-instance-1.1"
    )
    assert snapshot.metadata["tree_evidence_item_count"] == 1
    assert snapshot.metadata["evidence_node_refs"] == [
        {"node_id": "session.evidence.session-instance-1.call-weather"},
    ]
    assert snapshot.metadata["final_response_requires_evidence_path"] is True
    assert snapshot.metadata["verified_evidence_paths"] == ["network_truth"]
    assert snapshot.metadata["browser_verified_evidence_paths"] == ["network_truth"]


def test_context_workspace_adapter_previews_tree_prompt_without_snapshot_write() -> None:
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    snapshots = InMemoryContextRenderSnapshotRepository()
    adapter = ContextWorkspacePromptSnapshotAdapter(
        workspace_service=ContextWorkspaceService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
        render_service=ContextRenderService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
    )

    snapshot_record = adapter.preview_run_prompt_snapshot(
        run=_run(),
        prompt=_prompt(
            tool_schemas=(ToolSchema(name="fetch_weather", description="Fetch weather."),),
        ),
    )

    assert snapshot_record is not None
    assert snapshot_record.snapshot_id == "ctxpreview_run-context"
    assert "<context_tree" in snapshot_record.prompt_body
    assert "tools.available" in snapshot_record.included_node_ids
    assert snapshots.get_by_run("run-context") is None


def test_context_workspace_adapter_returns_recorded_run_snapshot_when_available() -> None:
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    snapshots = InMemoryContextRenderSnapshotRepository()
    adapter = ContextWorkspacePromptSnapshotAdapter(
        workspace_service=ContextWorkspaceService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
        render_service=ContextRenderService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
    )
    recorded = adapter.record_run_prompt_snapshot(
        run=_run(),
        prompt=_prompt(
            tool_schemas=(ToolSchema(name="fetch_weather", description="Fetch weather."),),
        ),
    )

    loaded = adapter.get_recorded_run_prompt_snapshot(
        run=_run(),
        prompt=_prompt(
            tool_schemas=(ToolSchema(name="fetch_weather", description="Fetch weather."),),
        ),
    )

    assert loaded is not None
    assert recorded is not None
    assert loaded.snapshot_id == recorded.snapshot_id
    assert loaded.prompt_body == recorded.prompt_body
    assert loaded.metadata["runtime_contract_hash"] == recorded.metadata["runtime_contract_hash"]
    assert loaded.provider_attachments["prompt_input"]["session_item_count"] == 1


def test_context_workspace_adapter_records_parent_snapshot_reference() -> None:
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    snapshots = InMemoryContextRenderSnapshotRepository()
    adapter = ContextWorkspacePromptSnapshotAdapter(
        workspace_service=ContextWorkspaceService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
        render_service=ContextRenderService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
    )
    first = adapter.record_run_prompt_snapshot(run=_run(), prompt=_prompt())
    assert first is not None
    first_stored = snapshots.get(first.snapshot_id)
    assert first_stored is not None
    run = _run()
    run.metadata["context_render_snapshot_id"] = first.snapshot_id

    second = adapter.record_run_prompt_snapshot(run=run, prompt=_prompt())

    assert second is not None
    assert second.parent_snapshot_id == first.snapshot_id
    assert second.parent_tree_revision == first_stored.tree_revision
    stored = snapshots.get(second.snapshot_id)
    assert stored is not None
    assert stored.parent_snapshot_id == first.snapshot_id
    assert stored.parent_tree_revision == first_stored.tree_revision


def test_context_workspace_adapter_records_agent_and_runtime_blocks_as_tree_content() -> None:
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    snapshots = InMemoryContextRenderSnapshotRepository()
    adapter = ContextWorkspacePromptSnapshotAdapter(
        workspace_service=ContextWorkspaceService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
        render_service=ContextRenderService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
    )

    snapshot_record = adapter.record_run_prompt_snapshot(
        run=_run(),
        prompt=_prompt(
            system_messages=(
                ("agent_instruction", "Be precise."),
                ("runtime_context", "# Runtime Context\n\n- Agent: assistant"),
            ),
        ),
    )

    assert snapshot_record is not None
    assert "agent.identity" in snapshot_record.prompt_body
    assert "Be precise." in snapshot_record.prompt_body
    assert "run.environment" in snapshot_record.prompt_body
    assert "- Agent: assistant" in snapshot_record.prompt_body


def test_context_workspace_adapter_mirrors_pinned_artifact_blocks(tmp_path) -> None:
    artifact_path = tmp_path / "image.png"
    artifact_path.write_bytes(b"png")
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    operations = InMemoryContextOperationRepository()
    snapshots = InMemoryContextRenderSnapshotRepository()
    workspace_service = ContextWorkspaceService(
        workspace_repository=workspaces,
        node_repository=nodes,
    )
    tree_service = ContextTreeService(
        workspace_repository=workspaces,
        node_repository=nodes,
        operation_repository=operations,
    )
    render_service = ContextRenderService(
        workspace_repository=workspaces,
        node_repository=nodes,
        snapshot_repository=snapshots,
    )
    workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:context",
            agent_id="assistant",
        ),
    )
    tree_service.upsert_nodes(
        ContextNodeUpsertInput(
            session_key="session:context",
            parent_node_id="artifacts.session",
            action=ContextAction.PIN,
            nodes=(
                ContextNodeSeed(
                    node_id="artifacts.artifact.image-1",
                    parent_id="artifacts.session",
                    owner="artifacts",
                    kind="artifact_image",
                    title="image.png",
                    summary="Image artifact.",
                    state=ContextNodeState(loaded=True, pinned=True),
                    actions=(ContextAction.PIN, ContextAction.UNPIN),
                    owner_ref={
                        "artifact_id": "image-1",
                        "preferred_variant": "llm",
                    },
                    estimate=ContextEstimate(image_count=1),
                    metadata={"mime_type": "image/png", "name": "image.png"},
                ),
            ),
        ),
    )
    adapter = ContextWorkspacePromptSnapshotAdapter(
        workspace_service=workspace_service,
        render_service=render_service,
        artifact_service=_FakeArtifactService(artifact_path),
    )

    snapshot_record = adapter.record_run_prompt_snapshot(
        run=_run(),
        prompt=_prompt(llm_capabilities=(LlmCapability.VISION_INPUT,)),
    )

    assert snapshot_record is not None
    assert snapshot_record.artifact_content_blocks == (
        {
            "type": "image",
            "mime_type": "image/png",
            "data": "cG5n",
        },
    )
    snapshot = snapshots.get_by_run("run-context")
    assert snapshot is not None
    assert snapshot.provider_attachments["artifact_content_candidates"][0]["artifact_id"] == "image-1"
    assert snapshot.metadata["artifact_content_block_count"] == 1
    assert snapshot.metadata["artifact_content_candidate_count"] == 1
    assert snapshot.metadata["artifact_content_image_count"] == 1
    assert snapshot.metadata["artifact_content_file_count"] == 0
    assert snapshot.metadata["artifact_content_estimated_tokens"] == 0


def test_context_workspace_adapter_downgrades_opened_image_for_non_vision_model(
    tmp_path,
) -> None:
    artifact_path = tmp_path / "image.png"
    artifact_path.write_bytes(b"png")
    workspace_service, tree_service, render_service, snapshots = (
        _context_workspace_services()
    )
    workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:context",
            agent_id="assistant",
        ),
    )
    _upsert_opened_artifact(
        tree_service,
        kind="artifact_image",
        artifact_id="image-1",
        title="image.png",
        mime_type="image/png",
        preferred_variant="llm",
    )
    adapter = ContextWorkspacePromptSnapshotAdapter(
        workspace_service=workspace_service,
        render_service=render_service,
        artifact_service=_FakeArtifactService(artifact_path),
    )

    snapshot_record = adapter.record_run_prompt_snapshot(
        run=_run(),
        prompt=_prompt(llm_capabilities=()),
    )

    assert snapshot_record is not None
    assert snapshot_record.artifact_content_blocks == (
        {
            "type": "text",
            "text": "[image attachment omitted for non-vision model:image.png]",
        },
    )
    snapshot = snapshots.get_by_run("run-context")
    assert snapshot is not None
    assert snapshot.provider_attachments["prompt_input"]["llm_capabilities"] == []
    assert snapshot.metadata["artifact_content_omitted_count"] == 1
    assert snapshot.metadata["artifact_content_budget"]["status"] == "omitted"


def test_context_workspace_adapter_reports_large_opened_artifact_budget(
    tmp_path,
) -> None:
    artifact_path = tmp_path / "image.png"
    artifact_path.write_bytes(b"x" * 1_500_001)
    workspace_service, tree_service, render_service, snapshots = (
        _context_workspace_services()
    )
    workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:context",
            agent_id="assistant",
        ),
    )
    _upsert_opened_artifact(
        tree_service,
        kind="artifact_image",
        artifact_id="image-1",
        title="image.png",
        mime_type="image/png",
        preferred_variant="llm",
    )
    adapter = ContextWorkspacePromptSnapshotAdapter(
        workspace_service=workspace_service,
        render_service=render_service,
        artifact_service=_FakeArtifactService(artifact_path),
    )

    snapshot_record = adapter.record_run_prompt_snapshot(
        run=_run(),
        prompt=_prompt(llm_capabilities=(LlmCapability.VISION_INPUT,)),
    )

    assert snapshot_record is not None
    assert snapshot_record.artifact_content_blocks == (
        {
            "type": "text",
            "text": "[image attachment omitted - exceeds llm size budget:image.png]",
        },
    )


def test_context_workspace_adapter_decodes_opened_text_file_artifact(tmp_path) -> None:
    artifact_path = tmp_path / "result.json"
    artifact_path.write_text('{"answer": 42}', encoding="utf-8")
    workspace_service, tree_service, render_service, snapshots = (
        _context_workspace_services()
    )
    workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:context",
            agent_id="assistant",
        ),
    )
    _upsert_opened_artifact(
        tree_service,
        kind="artifact_file",
        artifact_id="file-1",
        title="result.json",
        mime_type="application/json",
        preferred_variant="original",
    )
    adapter = ContextWorkspacePromptSnapshotAdapter(
        workspace_service=workspace_service,
        render_service=render_service,
        artifact_service=_FakeArtifactService(
            artifact_path,
            artifact_id="file-1",
            kind=ArtifactKind.FILE,
            mime_type="application/json",
            name="result.json",
        ),
    )

    snapshot_record = adapter.record_run_prompt_snapshot(
        run=_run(),
        prompt=_prompt(),
    )

    assert snapshot_record is not None
    assert snapshot_record.artifact_content_blocks == (
        {
            "type": "text",
            "text": '[file:result.json]\n{"answer": 42}',
        },
    )
    snapshot = snapshots.get_by_run("run-context")
    assert snapshot is not None
    assert snapshot.metadata["artifact_content_block_count"] == 1
    assert snapshot.metadata["artifact_content_text_block_count"] == 1
    assert snapshot.metadata["artifact_content_estimated_tokens"] > 0


def test_engine_preview_uses_context_tree_without_recording_snapshot() -> None:
    snapshot_port = _FakeContextSnapshotPort(
        prompt_body="<context_tree><node id=\"session.current\" /></context_tree>",
        tool_schemas=(ToolSchema(name="fetch_weather", description="Fetch weather."),),
        metadata={"runtime_contract_hash": "preview-hash"},
        provider_attachments={
            "tool_schemas": [{"name": "fetch_weather", "input_schema": {}}],
            "prompt_input": {"session_item_count": 1},
        },
    )
    engine = OrchestrationEngine(
        prompt_inputs=_FakeRunPromptInputCollector(
            tool_schemas=(
                ToolSchema(name="fetch_weather", description="Fetch weather."),
                ToolSchema(name="web_search", description="Search the web."),
            ),
        ),
        session_recorder=_FakeSessionRecorder(),
        llm_port=object(),
        tool_resolver=_FakeToolResolver(),
        tool_execution_port=object(),
        context_snapshot_port=snapshot_port,
    )

    preview = engine.preview_prompt(_run())

    assert preview.llm_id == "test-llm"
    assert preview.messages[0].metadata == {
        "prompt_block_kind": "context_workspace",
        "context_render_snapshot_id": "preview-run-context",
    }
    assert "session.current" in preview.messages[0].content
    assert [schema.name for schema in preview.tool_schemas] == ["fetch_weather"]
    assert preview.prompt_report is not None
    assert preview.prompt_report.context_render is not None
    assert preview.prompt_report.context_render.snapshot_id == "preview-run-context"
    assert preview.context_render_snapshot_id == "preview-run-context"
    assert preview.context_render_metadata["runtime_contract_hash"] == "preview-hash"
    assert preview.provider_attachments["prompt_input"]["session_item_count"] == 1
    assert preview.provider_attachments["tool_schemas"][0]["name"] == "fetch_weather"
    assert preview.context_surface["snapshot_id"] == "preview-run-context"
    assert "session.current" in str(preview.context_surface["rendered_context"])
    assert preview.context_surface["provider_attachment_mirror"]["prompt_input"][
        "session_item_count"
    ] == 1
    assert preview.tool_surface["id"] == "tool_surface:preview-run-context"
    assert preview.tool_surface["mirrored_schema_names"] == ["fetch_weather"]
    assert snapshot_port.preview_calls == [("run-context", "session:context")]
    assert snapshot_port.calls == []

    context = engine._build_advance_context(_run())  # noqa: SLF001

    assert context.context_render_snapshot_id == "snapshot-run-context"
    assert context.prompt.report is not None
    assert context.prompt.report.context_render is not None
    assert context.prompt.report.context_render.snapshot_id == "snapshot-run-context"
    assert snapshot_port.calls == [("run-context", "session:context")]


def test_engine_preview_replays_recorded_context_tree_when_snapshot_exists() -> None:
    snapshot_port = _FakeContextSnapshotPort(
        metadata={
            "history_delivery": "context_tree",
            "runtime_contract_hash": "live-hash",
        },
        provider_attachments={"prompt_input": {"session_item_count": 1}},
    )
    snapshot_port.recorded_snapshot = snapshot_port._snapshot_record(  # noqa: SLF001
        snapshot_id="snapshot-run-context",
        metadata={
            "history_delivery": "context_tree",
            "runtime_contract_hash": "recorded-hash",
        },
        provider_attachments={"prompt_input": {"session_item_count": 1}},
    )
    engine = OrchestrationEngine(
        prompt_inputs=_FakeRunPromptInputCollector(),
        session_recorder=_FakeSessionRecorder(),
        llm_port=object(),
        tool_resolver=_FakeToolResolver(),
        tool_execution_port=object(),
        context_snapshot_port=snapshot_port,
    )

    preview = engine.preview_prompt(_run())

    assert preview.context_render_snapshot_id == "snapshot-run-context"
    assert preview.context_render_metadata["runtime_contract_hash"] == "recorded-hash"
    assert preview.provider_attachments["prompt_input"]["session_item_count"] == 1
    assert preview.provider_request_options["request_metadata"][
        "context_render_snapshot_id"
    ] == "snapshot-run-context"
    assert preview.context_surface["snapshot_id"] == "snapshot-run-context"
    assert preview.tool_surface["id"] == "tool_surface:snapshot-run-context"
    assert snapshot_port.preview_calls == []


def test_engine_preview_does_not_include_post_run_transcript_messages() -> None:
    snapshot_port = _FakeContextSnapshotPort(
        metadata={"direct_transcript_message_count": 1},
    )
    snapshot_port.recorded_snapshot = snapshot_port._snapshot_record(  # noqa: SLF001
        snapshot_id="snapshot-run-context",
    )
    engine = OrchestrationEngine(
        prompt_inputs=_FakeRunPromptInputCollector(
            extra_messages=(
                LlmMessage(
                    role=LlmMessageRole.ASSISTANT,
                    content="post-run answer",
                ),
            ),
        ),
        session_recorder=_FakeSessionRecorder(),
        llm_port=object(),
        tool_resolver=_FakeToolResolver(),
        tool_execution_port=object(),
        context_snapshot_port=snapshot_port,
    )

    preview = engine.preview_prompt(_run())

    assert [message.content for message in preview.messages] == ["hello tree"]


def test_engine_adds_context_workspace_body_to_real_prompt() -> None:
    snapshot_port = _FakeContextSnapshotPort(
        prompt_body="<context_tree><node id=\"session.current\" /></context_tree>",
    )
    engine = OrchestrationEngine(
        prompt_inputs=_FakeRunPromptInputCollector(),
        session_recorder=_FakeSessionRecorder(),
        llm_port=object(),
        tool_resolver=_FakeToolResolver(),
        tool_execution_port=object(),
        context_snapshot_port=snapshot_port,
    )

    context = engine._build_advance_context(_run())  # noqa: SLF001

    first_message = context.prompt.messages[0]
    assert first_message.role is LlmMessageRole.SYSTEM
    assert first_message.metadata == {
        "prompt_block_kind": "context_workspace",
        "context_render_snapshot_id": "snapshot-run-context",
    }
    assert "session.current" in first_message.content


def test_engine_carries_context_contract_metadata_for_llm_invocation() -> None:
    snapshot_port = _FakeContextSnapshotPort(
        tool_schemas=(ToolSchema(name="fetch_weather", description="Fetch weather."),),
        metadata={
            "history_delivery": "context_tree",
            "runtime_contract_version": "2026-06-09",
            "runtime_contract_hash": "abc123",
            "runtime_contract": {
                "node_id": "runtime.contract",
                "contract_version": "2026-06-09",
                "content_hash": "abc123",
            },
            "tree_schema_version": CONTEXT_TREE_SCHEMA_VERSION,
            "mirrored_tool_schema_count": 1,
            "mirrored_tool_schema_estimated_tokens": 18,
            "tool_schema_mirror_budget_status": "ok",
            "tool_schema_mirror_skipped_count": 0,
            "tool_schema_mirror_default_schema_source": "source_prompt.default",
            "tool_schema_mirror_available_count": 4,
            "tool_schema_mirror_enabled_candidate_count": 2,
            "tool_schema_mirror_default_requested_count": 1,
            "tool_schema_mirror_default_candidate_count": 1,
            "tool_schema_mirror_default_mirrored_count": 1,
            "tool_schema_mirror_duplicate_count": 0,
            "tool_schema_mirror_groups": [
                {
                    "node_id": "tools.bundle.bundled.local_package.browser.group.network",
                    "kind": "tool_bundle_group",
                    "source_id": "bundled.local_package.browser",
                    "group_key": "network",
                    "title": "Network Capture & Replay",
                    "state": "collapsed",
                    "visibility": "visible_collapsed",
                    "function_count": 10,
                    "default_group": True,
                    "default_schema_count": 6,
                },
            ],
            "tool_schema_mirror_group_count": 12,
            "tool_schema_mirror_visible_group_count": 12,
            "tool_schema_mirror_collapsed_group_count": 12,
            "tool_schema_mirror_default_group_count": 5,
            "tool_schema_mirror_default_group_refs": [
                {
                    "source_id": "bundled.local_package.browser",
                    "group_key": "network",
                    "reason": "browser_starter_network",
                },
            ],
            "tool_schema_mirror_default_group_ref_count": 1,
            "tool_schema_mirror_default_group_matches": [
                {
                    "node_id": "tools.bundle.bundled.local_package.browser.group.network",
                    "source_id": "bundled.local_package.browser",
                    "group_key": "network",
                    "priority": "200",
                    "reason": "browser_starter_network",
                },
            ],
            "tool_schema_mirror_default_group_match_count": 1,
            "tool_schema_mirror_default_schema_reasons": {
                "browser.network.inspect": "browser_starter_network",
            },
            "tool_schema_mirror_default_mirrored": [
                {
                    "node_id": "tools.tool.browser.network.inspect",
                    "name": "browser.network.inspect",
                    "priority": 200,
                    "bootstrap_reason": "browser_starter_network",
                },
            ],
            "tool_schema_mirror_skipped": [],
            "tool_schema_mirror_skipped_by_reason": {},
            "tool_schema_mirror_max_count": 32,
            "tool_schema_mirror_max_estimated_tokens": 24000,
            "rendered_prompt_estimated_tokens": 120,
            "direct_transcript_estimated_tokens": 30,
            "artifact_content_estimated_tokens": 6,
            "artifact_content_block_count": 1,
            "artifact_content_candidate_count": 1,
            "artifact_content_image_count": 0,
            "artifact_content_file_count": 0,
            "artifact_content_omitted_count": 0,
            "estimated_provider_prompt_tokens": 154,
            "duplicate_tool_delivery_risk": False,
            "session_budget_status": "ok",
            "mirrored_node_count": 2,
            "current_inbound_session_item_id": "item-user-1",
        },
    )
    engine = OrchestrationEngine(
        prompt_inputs=_FakeRunPromptInputCollector(
            tool_schemas=(ToolSchema(name="fetch_weather", description="Fetch weather."),),
            extra_messages=(
                LlmMessage(
                    role=LlmMessageRole.ASSISTANT,
                    content={
                        "type": "function_call",
                        "call_id": "call-weather-1",
                        "name": "fetch_weather",
                        "arguments": {"location": "Kunming"},
                    },
                    tool_call_id="call-weather-1",
                    metadata={
                        "session_item_id": "item-assistant-tool-1",
                        "session_id": "session-instance-1",
                        "sequence_no": 2,
                        "kind": "message",
                        "source_kind": "llm_invocation",
                        "source_id": "llm-1",
                        "tool_call_id": "call-weather-1",
                        "tool_name": "fetch_weather",
                    },
                ),
                LlmMessage(
                    role=LlmMessageRole.TOOL,
                    content="weather result",
                    name="fetch_weather",
                    tool_call_id="call-weather-1",
                    metadata={
                        "session_item_id": "item-tool-result-1",
                        "session_id": "session-instance-1",
                        "sequence_no": 3,
                        "kind": "tool_result",
                        "source_kind": "tool_run",
                        "source_id": "tool-run-1",
                        "tool_call_id": "call-weather-1",
                        "tool_name": "fetch_weather",
                        "tool_status": "succeeded",
                    },
                ),
            ),
        ),
        session_recorder=_FakeSessionRecorder(),
        llm_port=object(),
        tool_resolver=_FakeToolResolver(tools=(_resolved_tool("fetch_weather"),)),
        tool_execution_port=object(),
        context_snapshot_port=snapshot_port,
    )

    context = engine._build_advance_context(_run())  # noqa: SLF001

    assert context.context_render_snapshot_metadata["runtime_contract_hash"] == "abc123"
    from crxzipple.modules.orchestration.application.engine import _llm_request_metadata

    request_metadata = _llm_request_metadata(context)
    assert request_metadata["prompt_mode"] == "normal_turn"
    assert request_metadata["tree_schema_version"] == CONTEXT_TREE_SCHEMA_VERSION
    assert request_metadata["context_render_snapshot_id"] == "snapshot-run-context"
    assert request_metadata["runtime_contract_version"] == "2026-06-09"
    assert request_metadata["runtime_contract_hash"] == "abc123"
    assert request_metadata["mirrored_tool_schema_count"] == 1
    assert request_metadata["mirrored_tool_schema_estimated_tokens"] == 18
    assert request_metadata["tool_schema_mirror_budget_status"] == "ok"
    assert request_metadata["tool_schema_mirror_skipped_count"] == 0
    assert request_metadata["tool_schema_mirror_default_schema_source"] == (
        "source_prompt.default"
    )
    assert request_metadata["tool_schema_mirror_available_count"] == 4
    assert request_metadata["tool_schema_mirror_enabled_candidate_count"] == 2
    assert request_metadata["tool_schema_mirror_default_requested_count"] == 1
    assert request_metadata["tool_schema_mirror_default_candidate_count"] == 1
    assert request_metadata["tool_schema_mirror_default_mirrored_count"] == 1
    assert request_metadata["tool_schema_mirror_duplicate_count"] == 0
    assert request_metadata["tool_schema_mirror_group_count"] == 12
    assert request_metadata["tool_schema_mirror_visible_group_count"] == 12
    assert request_metadata["tool_schema_mirror_collapsed_group_count"] == 12
    assert request_metadata["tool_schema_mirror_default_group_count"] == 5
    assert request_metadata["tool_schema_mirror_groups"][0]["group_key"] == "network"
    assert request_metadata["tool_schema_mirror_groups"][0]["default_group"] is True
    assert request_metadata["tool_schema_mirror_default_group_ref_count"] == 1
    assert request_metadata["tool_schema_mirror_default_group_refs"] == [
        {
            "source_id": "bundled.local_package.browser",
            "group_key": "network",
            "reason": "browser_starter_network",
        },
    ]
    assert request_metadata["tool_schema_mirror_default_group_match_count"] == 1
    assert request_metadata["tool_schema_mirror_default_group_matches"] == [
        {
            "node_id": "tools.bundle.bundled.local_package.browser.group.network",
            "source_id": "bundled.local_package.browser",
            "group_key": "network",
            "priority": "200",
            "reason": "browser_starter_network",
        },
    ]
    assert request_metadata["tool_schema_mirror_default_schema_reasons"] == {
        "browser.network.inspect": "browser_starter_network",
    }
    assert request_metadata["tool_schema_mirror_default_mirrored"][0]["name"] == (
        "browser.network.inspect"
    )
    assert request_metadata["tool_surface_id"] == "tool_surface:snapshot-run-context"
    assert request_metadata["tool_surface_mirrored_schema_names"] == ["fetch_weather"]
    assert request_metadata["tool_surface_mirrored_schema_count"] == 1
    assert request_metadata["tool_surface_always_visible_count"] == 1
    assert request_metadata["tool_surface_context_selected_count"] == 0
    assert request_metadata["tool_surface_function_refs"] == [
        {
            "tool_id": "fetch_weather",
            "name": "fetch_weather",
            "enabled": True,
            "always_visible": True,
            "source_id": "bundled.local_package.browser",
            "group_key": "network",
        },
    ]
    assert request_metadata["tool_surface_source_refs"] == [
        {"source_id": "bundled.local_package.browser"},
    ]
    assert request_metadata["tool_surface_group_refs"] == [
        {
            "source_id": "bundled.local_package.browser",
            "group_key": "network",
        },
    ]
    assert "tool_schema_mirror_skipped" not in request_metadata
    assert "tool_schema_mirror_skipped_by_reason" not in request_metadata
    assert request_metadata["tool_schema_mirror_max_count"] == 32
    assert request_metadata["tool_schema_mirror_max_estimated_tokens"] == 24000
    assert request_metadata["rendered_prompt_estimated_tokens"] == 120
    assert request_metadata["direct_transcript_estimated_tokens"] == 30
    assert request_metadata["artifact_content_estimated_tokens"] == 6
    assert request_metadata["artifact_content_block_count"] == 1
    assert request_metadata["artifact_content_candidate_count"] == 1
    assert request_metadata["artifact_content_image_count"] == 0
    assert request_metadata["artifact_content_file_count"] == 0
    assert request_metadata["artifact_content_omitted_count"] == 0
    assert request_metadata["estimated_provider_prompt_tokens"] == 154
    assert request_metadata["duplicate_tool_delivery_risk"] is False
    assert request_metadata["session_budget_status"] == "ok"
    assert request_metadata["runtime_contract"]["node_id"] == "runtime.contract"
    assert "direct_transcript_session_item_count" not in request_metadata
    assert "direct_transcript_sequence_range" not in request_metadata
    assert request_metadata["current_inbound_ref"] == {
        "item_id": "item-user-1",
        "session_id": "session-instance-1",
        "sequence_no": 1,
        "role": "user",
        "source_kind": "orchestration_run",
        "source_id": "run-context",
    }
    assert request_metadata["direct_tool_protocol_call_ids"] == ["call-weather-1"]
    assert request_metadata["direct_tool_protocol_refs"] == [
        {
            "item_id": "item-assistant-tool-1",
            "session_id": "session-instance-1",
            "sequence_no": 2,
            "role": "assistant",
            "kind": "message",
            "source_kind": "llm_invocation",
            "source_id": "llm-1",
            "tool_call_id": "call-weather-1",
            "tool_name": "fetch_weather",
        },
        {
            "item_id": "item-tool-result-1",
            "session_id": "session-instance-1",
            "sequence_no": 3,
            "role": "tool",
            "kind": "tool_result",
            "source_kind": "tool_run",
            "source_id": "tool-run-1",
            "tool_call_id": "call-weather-1",
            "tool_name": "fetch_weather",
            "tool_status": "succeeded",
        },
    ]


def test_engine_uses_context_mirror_as_real_tool_schema_surface() -> None:
    snapshot_port = _FakeContextSnapshotPort(
        tool_schemas=(ToolSchema(name="fetch_weather", description="Fetch weather."),),
    )
    engine = OrchestrationEngine(
        prompt_inputs=_FakeRunPromptInputCollector(
            tool_schemas=(
                ToolSchema(name="fetch_weather", description="Fetch weather."),
                ToolSchema(name="web_search", description="Search the web."),
            ),
        ),
        session_recorder=_FakeSessionRecorder(),
        llm_port=object(),
        tool_resolver=_FakeToolResolver(
            tools=(
                _resolved_tool("fetch_weather"),
                _resolved_tool("web_search"),
            ),
        ),
        tool_execution_port=object(),
        context_snapshot_port=snapshot_port,
    )

    context = engine._build_advance_context(_run())  # noqa: SLF001

    assert [schema.name for schema in context.prompt.tool_schemas] == ["fetch_weather"]
    assert [item.tool.id for item in context.resolved_tools.tools] == ["fetch_weather"]


def test_engine_drops_provider_tool_surface_when_context_mirror_not_ready() -> None:
    snapshot_port = _FakeContextSnapshotPort(tool_schemas=None)
    engine = OrchestrationEngine(
        prompt_inputs=_FakeRunPromptInputCollector(
            tool_schemas=(ToolSchema(name="web_search", description="Search the web."),),
        ),
        session_recorder=_FakeSessionRecorder(),
        llm_port=object(),
        tool_resolver=_FakeToolResolver(tools=(_resolved_tool("web_search"),)),
        tool_execution_port=object(),
        context_snapshot_port=snapshot_port,
    )

    context = engine._build_advance_context(_run())  # noqa: SLF001

    assert context.prompt.tool_schemas == ()
    assert context.resolved_tools.tools == ()


def test_engine_allows_context_mirror_to_disable_all_tool_schemas() -> None:
    snapshot_port = _FakeContextSnapshotPort(tool_schemas=())
    engine = OrchestrationEngine(
        prompt_inputs=_FakeRunPromptInputCollector(
            tool_schemas=(ToolSchema(name="web_search", description="Search the web."),),
        ),
        session_recorder=_FakeSessionRecorder(),
        llm_port=object(),
        tool_resolver=_FakeToolResolver(tools=(_resolved_tool("web_search"),)),
        tool_execution_port=object(),
        context_snapshot_port=snapshot_port,
    )

    context = engine._build_advance_context(_run())  # noqa: SLF001

    assert context.prompt.tool_schemas == ()
    assert context.resolved_tools.tools == ()


def test_engine_appends_context_artifact_blocks_to_real_prompt() -> None:
    snapshot_port = _FakeContextSnapshotPort(
        artifact_content_blocks=(
            {
                "type": "image",
                "mime_type": "image/png",
                "data": "cG5n",
            },
        ),
    )
    engine = OrchestrationEngine(
        prompt_inputs=_FakeRunPromptInputCollector(),
        session_recorder=_FakeSessionRecorder(),
        llm_port=object(),
        tool_resolver=_FakeToolResolver(),
        tool_execution_port=object(),
        context_snapshot_port=snapshot_port,
    )

    context = engine._build_advance_context(_run())  # noqa: SLF001

    artifact_message = context.prompt.messages[-1]
    assert artifact_message.role is LlmMessageRole.USER
    assert artifact_message.metadata["prompt_block_kind"] == "context_artifacts"
    assert artifact_message.content[1]["type"] == "image"
    assert artifact_message.content[1]["data"] == "cG5n"


def test_engine_fails_when_context_render_record_is_missing() -> None:
    engine = OrchestrationEngine(
        prompt_inputs=_FakeRunPromptInputCollector(
            tool_schemas=(ToolSchema(name="web_search", description="Search the web."),),
        ),
        session_recorder=_FakeSessionRecorder(),
        llm_port=object(),
        tool_resolver=_FakeToolResolver(tools=(_resolved_tool("web_search"),)),
        tool_execution_port=object(),
        context_snapshot_port=_MissingContextSnapshotPort(),
    )

    with pytest.raises(
        OrchestrationValidationError,
        match="Context Workspace prompt render did not return a snapshot",
    ):
        engine._build_advance_context(_run())  # noqa: SLF001

    with pytest.raises(
        OrchestrationValidationError,
        match="Context Workspace prompt preview did not return a render record",
    ):
        engine.preview_prompt(_run())


def _context_workspace_services():
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    operations = InMemoryContextOperationRepository()
    snapshots = InMemoryContextRenderSnapshotRepository()
    workspace_service = ContextWorkspaceService(
        workspace_repository=workspaces,
        node_repository=nodes,
    )
    tree_service = ContextTreeService(
        workspace_repository=workspaces,
        node_repository=nodes,
        operation_repository=operations,
    )
    render_service = ContextRenderService(
        workspace_repository=workspaces,
        node_repository=nodes,
        snapshot_repository=snapshots,
    )
    return workspace_service, tree_service, render_service, snapshots


def _upsert_opened_artifact(
    tree_service: ContextTreeService,
    *,
    kind: str,
    artifact_id: str,
    title: str,
    mime_type: str,
    preferred_variant: str,
) -> None:
    tree_service.upsert_nodes(
        ContextNodeUpsertInput(
            session_key="session:context",
            parent_node_id="artifacts.session",
            action=ContextAction.PIN,
            nodes=(
                ContextNodeSeed(
                    node_id=f"artifacts.artifact.{artifact_id}",
                    parent_id="artifacts.session",
                    owner="artifacts",
                    kind=kind,
                    title=title,
                    summary=f"{title} artifact.",
                    state=ContextNodeState(loaded=True, pinned=True),
                    actions=(ContextAction.PIN, ContextAction.UNPIN),
                    owner_ref={
                        "artifact_id": artifact_id,
                        "preferred_variant": preferred_variant,
                    },
                    estimate=ContextEstimate(
                        image_count=1 if kind == "artifact_image" else 0,
                        file_count=1 if kind == "artifact_file" else 0,
                    ),
                    metadata={"mime_type": mime_type, "name": title},
                ),
            ),
        ),
    )


def _browser_group_seed(
    *,
    group_key: str,
    tool_ids: tuple[str, ...],
    display_order: int,
) -> ContextNodeSeed:
    return ContextNodeSeed(
        node_id=f"tools.bundle.bundled.local_package.browser.group.{group_key}",
        parent_id="tools.bundle.bundled.local_package.browser",
        owner="tool",
        kind="tool_bundle_group",
        title=group_key.replace("_", " ").title(),
        summary=f"Browser {group_key} tools.",
        state=ContextNodeState(collapsed=True, loaded=True),
        actions=(ContextAction.EXPAND, ContextAction.COLLAPSE),
        owner_ref={
            "source_id": "bundled.local_package.browser",
            "group_key": group_key,
        },
        metadata={
            "source_id": "bundled.local_package.browser",
            "group_key": group_key,
            "default_tool_schema_ids": list(tool_ids),
            "default_tool_schema_source": f"bundled.local_package.browser.prompt_group.{group_key}",
            "default_tool_schema_max_count": len(tool_ids),
        },
        display_order=display_order,
    )


def _browser_tool_seed(
    *,
    tool_id: str,
    parent_id: str,
    display_order: int,
) -> ContextNodeSeed:
    return ContextNodeSeed(
        node_id=f"tools.tool.{tool_id}",
        parent_id=parent_id,
        owner="tool",
        kind="tool_function",
        title=tool_id,
        summary=f"{tool_id} tool.",
        state=ContextNodeState(collapsed=False, loaded=True),
        owner_ref={"tool_id": tool_id, "source_id": "bundled.local_package.browser"},
        metadata={
            "provider_schema": {
                "name": tool_id,
                "description": f"{tool_id} tool.",
                "input_schema": {"type": "object", "properties": {}},
            },
        },
        display_order=display_order,
    )


def _run() -> OrchestrationRun:
    return OrchestrationRun(
        id="run-context",
        inbound_instruction=InboundInstruction(
            source="unit-test",
            content="hello tree",
        ),
        active_session_id="session-instance-1",
        agent_id="assistant",
        metadata={"session_key": "session:context"},
    )


def _prompt(
    *,
    tool_schemas: tuple[ToolSchema, ...] = (),
    system_messages: tuple[tuple[str, str], ...] = (),
    llm_capabilities: tuple[LlmCapability, ...] = (),
    extra_messages: tuple[LlmMessage, ...] = (),
    flow_hint: dict[str, object] | None = None,
    transcript_budget: dict[str, object] | None = None,
) -> RunPromptInput:
    return RunPromptInput(
        llm_id="test-llm",
        session_key="session:context",
        active_session_id="session-instance-1",
        messages=(
            LlmMessage(
                role=LlmMessageRole.USER,
                content="hello tree",
                metadata={
                    "session_item_id": "item-user-1",
                    "session_id": "session-instance-1",
                    "sequence_no": 1,
                    "source_kind": "orchestration_run",
                    "source_id": "run-context",
                },
            ),
            *extra_messages,
        ),
        llm_capabilities=llm_capabilities,
        tool_schemas=tool_schemas,
        flow_hint=dict(flow_hint or {}),
        context_blocks=tuple(
            PromptBlock(kind=kind, content=content)
            for kind, content in system_messages
        ),
        report=PromptReport(
            mode=PromptMode.NORMAL_TURN,
            context_blocks=(),
            context_budget_source="fixed",
            context_budget_chars=0,
            context_budget_estimated_tokens=0,
            llm_context_window_tokens=None,
            context_chars=0,
            context_estimated_tokens=0,
            transcript_message_count=1,
            transcript_chars=10,
            transcript_estimated_tokens=3,
            transcript_budget=dict(transcript_budget or {}),
        ),
    )


class _FakeRunPromptInputCollector:
    detailed_phase_metrics_enabled = False
    metrics = None

    def __init__(
        self,
        *,
        tool_schemas: tuple[ToolSchema, ...] = (),
        system_messages: tuple[tuple[str, str], ...] = (),
        extra_messages: tuple[LlmMessage, ...] = (),
    ) -> None:
        self._tool_schemas = tool_schemas
        self._system_messages = system_messages
        self._extra_messages = extra_messages

    def build(self, run, *, resolved_tools):  # noqa: ANN001, ANN201
        del run, resolved_tools
        return _prompt(
            tool_schemas=self._tool_schemas,
            system_messages=self._system_messages,
            extra_messages=self._extra_messages,
        )


class _FakeSessionRecorder:
    def ensure_inbound_message(self, run, *, session_key):  # noqa: ANN001, ANN201
        assert run.id == "run-context"
        assert session_key == "session:context"
        return InboundSessionRecord(
            user_session_item_id="item-user-1",
        )


class _FakeToolResolver:
    def __init__(self, *, tools: tuple[ResolvedTool, ...] = ()) -> None:
        self._tools = tools

    def resolve(self, run):  # noqa: ANN001, ANN201
        assert run.id == "run-context"
        return ResolvedToolSet(tools=self._tools)


class _FakeContextSnapshotPort:
    def __init__(
        self,
        *,
        tool_schemas: tuple[ToolSchema, ...] | None = None,
        prompt_body: str | None = None,
        tool_schema_mirror_available: bool | None = None,
        artifact_content_blocks: tuple[dict[str, object], ...] = (),
        metadata: dict[str, object] | None = None,
        provider_attachments: dict[str, object] | None = None,
    ) -> None:
        self._tool_schemas = tool_schemas
        self._prompt_body = prompt_body
        self._artifact_content_blocks = artifact_content_blocks
        self._metadata = dict(metadata or {})
        self._provider_attachments = dict(provider_attachments or {})
        self._tool_schema_mirror_available = (
            tool_schemas is not None
            if tool_schema_mirror_available is None
            else tool_schema_mirror_available
        )
        self.calls: list[tuple[str, str]] = []
        self.preview_calls: list[tuple[str, str]] = []
        self.recorded_snapshot: ContextRenderSnapshotRecord | None = None

    def get_recorded_run_prompt_snapshot(
        self,
        *,
        run: OrchestrationRun,
        prompt: RunPromptInput,
    ) -> ContextRenderSnapshotRecord | None:
        del run, prompt
        return self.recorded_snapshot

    def preview_run_prompt_snapshot(
        self,
        *,
        run: OrchestrationRun,
        prompt: RunPromptInput,
    ) -> ContextRenderSnapshotRecord:
        self.preview_calls.append((run.id, prompt.session_key))
        return self._snapshot_record(snapshot_id=f"preview-{run.id}")

    def record_run_prompt_snapshot(
        self,
        *,
        run: OrchestrationRun,
        prompt: RunPromptInput,
    ) -> ContextRenderSnapshotRecord:
        self.calls.append((run.id, prompt.session_key))
        return self._snapshot_record(snapshot_id=f"snapshot-{run.id}")

    def _snapshot_record(
        self,
        *,
        snapshot_id: str,
        metadata: dict[str, object] | None = None,
        provider_attachments: dict[str, object] | None = None,
    ) -> ContextRenderSnapshotRecord:
        return ContextRenderSnapshotRecord(
            snapshot_id=snapshot_id,
            prompt_body=self._prompt_body,
            tool_schemas=self._tool_schemas,
            tool_schema_mirror_available=self._tool_schema_mirror_available,
            artifact_content_blocks=self._artifact_content_blocks,
            metadata=dict(self._metadata if metadata is None else metadata),
            provider_attachments=dict(
                self._provider_attachments
                if provider_attachments is None
                else provider_attachments,
            ),
        )


class _MissingContextSnapshotPort:
    def get_recorded_run_prompt_snapshot(
        self,
        *,
        run: OrchestrationRun,
        prompt: RunPromptInput,
    ) -> None:
        del run, prompt
        return None

    def preview_run_prompt_snapshot(
        self,
        *,
        run: OrchestrationRun,
        prompt: RunPromptInput,
    ) -> None:
        del run, prompt
        return None

    def record_run_prompt_snapshot(
        self,
        *,
        run: OrchestrationRun,
        prompt: RunPromptInput,
    ) -> None:
        del run, prompt
        return None


def _resolved_tool(tool_id: str) -> ResolvedTool:
    return ResolvedTool(
        tool=Tool(
            id=tool_id,
            name=tool_id,
            description=f"{tool_id} description.",
        ),
        schema=ToolSchema(name=tool_id, description=f"{tool_id} description."),
        target=ToolExecutionTarget(),
    )


class _FakeArtifactService:
    def __init__(
        self,
        path,
        *,
        artifact_id: str = "image-1",
        kind: ArtifactKind = ArtifactKind.IMAGE,
        mime_type: str = "image/png",
        name: str = "image.png",
    ) -> None:
        self.path = path
        self.variant = (
            ArtifactVariant.LLM if kind is ArtifactKind.IMAGE else ArtifactVariant.ORIGINAL
        )
        self.artifact = Artifact(
            id=artifact_id,
            kind=kind,
            mime_type=mime_type,
            storage_key=f"{artifact_id}/original",
            llm_storage_key=f"{artifact_id}/llm" if kind is ArtifactKind.IMAGE else None,
            name=name,
        )

    def resolve_variant(
        self,
        artifact_id: str,
        *,
        variant: ArtifactVariant,
    ) -> ArtifactBinary:
        assert artifact_id == self.artifact.id
        assert variant is self.variant
        return ArtifactBinary(
            artifact=self.artifact,
            path=self.path,
            variant=variant,
        )
