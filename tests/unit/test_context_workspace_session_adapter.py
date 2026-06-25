from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from crxzipple.app.integration.context_workspace_session import (
    SessionContextNodeProvider,
)
from crxzipple.app.integration.context_workspace_session_evidence import (
    evidence_type,
)
from crxzipple.modules.context_workspace.application import (
    ContextActionInput,
    ContextOwnerRegistry,
    ContextObservationSnapshotService,
    ContextTreeService,
    ContextWorkspaceService,
    EnsureContextWorkspaceInput,
    RecordContextSnapshotInput,
    ContextObservationRenderInput,
    ContextSliceBuilderService,
)
from crxzipple.modules.context_workspace.domain import ContextAction
from crxzipple.modules.context_workspace.infrastructure import (
    InMemoryContextNodeRepository,
    InMemoryContextOperationRepository,
    InMemoryContextSnapshotRepository,
    InMemoryContextWorkspaceRepository,
)
from crxzipple.modules.session.application import (
    AppendSessionItemInput,
    CompactSessionSegmentInput,
    EnsureSessionInput,
    ListSessionItemsInput,
    MergeSessionItemMetadataInput,
    ResetSessionInput,
    SessionApplicationService,
)

from crxzipple.modules.session.infrastructure import (
    InMemorySessionInstanceRepository,
    InMemorySessionItemRepository,
    InMemorySessionRepository,
)
from crxzipple.modules.session.domain import (
    SessionItem,
    SessionItemKind,
)
from crxzipple.modules.tool.application.result_envelope import (
    TOOL_RESULT_ENVELOPE_METADATA_KEY,
)


class SessionItemFixtureKind(StrEnum):
    MESSAGE = "message"
    TOOL_RESULT = "tool_result"
    EVENT = "event"


@dataclass(frozen=True, slots=True)
class AppendSessionItemFixtureInput:
    session_key: str
    role: str
    content_payload: dict[str, object]
    kind: SessionItemFixtureKind = SessionItemFixtureKind.MESSAGE
    metadata: dict[str, object] = field(default_factory=dict)
    source_kind: str | None = None
    source_id: str | None = None


@dataclass(frozen=True, slots=True)
class ArchiveSessionItemsFixtureInput:
    session_key: str
    archived_through_sequence_no: int | None = None
    max_sequence_no: int | None = None
    session_id: str | None = None
    reason: str = "test"


def test_session_adapter_populates_current_instance_and_message_nodes() -> None:
    session_service = _session_service()
    session_service.ensure_session(
        EnsureSessionInput(
            key="session:tree",
            agent_id="assistant",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:tree",
            role="user",
            content_payload={"blocks": [{"type": "text", "text": "hello tree"}]},
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:tree",
            role="assistant",
            content_payload={"blocks": [{"type": "text", "text": "tree received"}]},
        ),
    )
    services = _context_services(session_service)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:tree",
            agent_id="assistant",
        ),
    )
    tree = services["tree"].list_tree("session:tree")

    assert {node.id for node in tree.nodes} >= {
        "session.instance.active",
        "session.segments.active",
        "session.segment.active",
        "session.items.current",
    }
    active_instance = next(node for node in tree.nodes if node.id == "session.instance.active")
    assert active_instance.parent_id == "session.current"
    assert active_instance.kind == "session_instance"
    current_segment = next(node for node in tree.nodes if node.id == "session.segment.active")
    assert current_segment.parent_id == "session.segments.active"
    messages_node = next(node for node in tree.nodes if node.id == "session.items.current")
    assert messages_node.parent_id == "session.segment.active"
    assert messages_node.owner_ref["from_sequence_no"] == 1
    assert messages_node.owner_ref["to_sequence_no"] == 2
    assert messages_node.state.collapsed is False

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:tree",
            node_id="session.items.current",
            action=ContextAction.EXPAND,
        ),
    )
    expanded_tree = services["tree"].list_tree("session:tree")
    message_nodes = [
        node
        for node in expanded_tree.nodes
        if node.parent_id == "session.items.current"
    ]

    assert [node.owner_ref["sequence_no"] for node in message_nodes] == [1, 2]
    assert "hello tree" in message_nodes[0].summary
    assert "hello tree" in message_nodes[0].content
    assert message_nodes[0].metadata["role"] == "user"
    assert message_nodes[0].metadata["content_block_types"] == ["text"]


def test_session_adapter_exposes_current_turn_and_execution_step_refs() -> None:
    session_service = _session_service()
    session_service.ensure_session(
        EnsureSessionInput(
            key="session:turn-tree",
            agent_id="assistant",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:turn-tree",
            role="user",
            content_payload={"blocks": [{"type": "text", "text": "check weather"}]},
            source_kind="orchestration_run",
            source_id="run-turn-tree",
        ),
    )
    services = _context_services(
        session_service,
        execution_query=_FakeExecutionQuery(
            turn_id="run-turn-tree",
            summary_payload={
                "llm_invocation_id": "llm-invocation-1",
                "tool_call_names": ["open_meteo_weather.forecast_weather"],
            },
        ),
    )

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:turn-tree",
            agent_id="assistant",
            metadata={"last_run_id": "run-turn-tree"},
        ),
    )
    tree = services["tree"].list_tree("session:turn-tree")
    nodes = {node.id: node for node in tree.nodes}

    assert "session.turn.current" in nodes
    assert nodes["session.turn.current"].kind == "session_turn"
    assert nodes["session.turn.current"].parent_id == "session.segment.active"
    assert "session.steps.current" in nodes
    assert nodes["session.steps.current"].kind == "session_steps_root"
    assert nodes["session.steps.current"].parent_id == "session.turn.current"
    assert "session.step.step-1" in nodes
    assert nodes["session.step.step-1"].kind == "session_step"
    assert nodes["session.step.step-1"].owner_ref["step_id"] == "step-1"
    assert "session.step.item.item-1" in nodes
    assert nodes["session.step.item.item-1"].kind == "runtime_llm_invocation"
    assert (
        nodes["session.step.item.item-1"].owner_ref["llm_invocation_id"]
        == "llm-invocation-1"
    )


def test_session_adapter_projects_execution_item_runtime_semantic_kind() -> None:
    session_service = _session_service()
    session_service.ensure_session(
        EnsureSessionInput(
            key="session:semantic-step",
            agent_id="assistant",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:semantic-step",
            role="user",
            content_payload={"blocks": [{"type": "text", "text": "continue"}]},
            source_kind="orchestration_run",
            source_id="run-semantic-step",
        ),
    )
    services = _context_services(
        session_service,
        execution_query=_FakeExecutionQuery(
            turn_id="run-semantic-step",
            summary_payload={
                "runtime_semantic_kind": "runtime.assistant_progress",
                "llm_invocation_id": "llm-invocation-progress",
                "llm_response_item_id": "llm-response-progress",
                "session_item_id": "session-item-progress",
            },
        ),
    )

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:semantic-step",
            agent_id="assistant",
            metadata={"last_run_id": "run-semantic-step"},
        ),
    )
    nodes = {
        node.id: node
        for node in services["tree"].list_tree("session:semantic-step").nodes
    }
    item_node = nodes["session.step.item.item-1"]

    assert item_node.kind == "runtime_assistant_progress"
    assert item_node.owner_ref["runtime_semantic_kind"] == "runtime.assistant_progress"
    assert item_node.owner_ref["llm_response_item_id"] == "llm-response-progress"
    assert item_node.owner_ref["session_item_id"] == "session-item-progress"
    assert item_node.metadata["runtime_semantic_kind"] == "runtime.assistant_progress"
    assert "runtime_semantic_kind" in item_node.summary


def test_session_adapter_projects_final_and_blocked_runtime_semantic_nodes() -> None:
    session_service = _session_service()
    session_service.ensure_session(
        EnsureSessionInput(
            key="session:terminal-semantics",
            agent_id="assistant",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:terminal-semantics",
            role="user",
            content_payload={"blocks": [{"type": "text", "text": "continue"}]},
            source_kind="orchestration_run",
            source_id="run-terminal-semantics",
        ),
    )
    services = _context_services(
        session_service,
        execution_query=_FakeExecutionQueryWithSteps(
            turn_id="run-terminal-semantics",
            steps=[
                _FakeExecutionEntity(
                    id="step-final",
                    kind="llm",
                    status="completed",
                    step_index=1,
                ),
            ],
            items_by_step_id={
                "step-final": [
                    _FakeExecutionEntity(
                        id="item-final-answer",
                        kind="llm_invocation",
                        status="completed",
                        summary_payload={
                            "runtime_semantic_kind": "runtime.final_answer",
                            "llm_invocation_id": "llm-final",
                            "llm_response_item_id": "response-final",
                            "session_item_id": "session-final",
                        },
                    ),
                    _FakeExecutionEntity(
                        id="item-blocked",
                        kind="continuation_decision",
                        status="completed",
                        summary_payload={
                            "runtime_semantic_kind": "runtime.blocked_state",
                            "run_status": "blocked",
                        },
                    ),
                ],
            },
        ),
    )

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:terminal-semantics",
            agent_id="assistant",
            metadata={"last_run_id": "run-terminal-semantics"},
        ),
    )
    nodes = {
        node.id: node
        for node in services["tree"].list_tree("session:terminal-semantics").nodes
    }

    final_node = nodes["session.step.item.item-final-answer"]
    blocked_node = nodes["session.step.item.item-blocked"]

    assert final_node.kind == "runtime_final_answer"
    assert final_node.owner_ref["runtime_semantic_kind"] == "runtime.final_answer"
    assert final_node.owner_ref["session_item_id"] == "session-final"
    assert blocked_node.kind == "runtime_blocked_state"
    assert blocked_node.owner_ref["runtime_semantic_kind"] == "runtime.blocked_state"


def test_session_adapter_projects_tool_batch_runtime_ref_nodes() -> None:
    session_service = _session_service()
    session_service.ensure_session(
        EnsureSessionInput(
            key="session:tool-batch-step",
            agent_id="assistant",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:tool-batch-step",
            role="user",
            content_payload={"blocks": [{"type": "text", "text": "use tool"}]},
            source_kind="orchestration_run",
            source_id="run-tool-batch-step",
        ),
    )
    services = _context_services(
        session_service,
        execution_query=_FakeExecutionQueryWithSteps(
            turn_id="run-tool-batch-step",
            steps=[
                _FakeExecutionEntity(
                    id="step-llm",
                    kind="llm",
                    status="completed",
                    step_index=1,
                ),
                _FakeExecutionEntity(
                    id="step-tool-batch",
                    kind="tool_batch",
                    status="completed",
                    step_index=2,
                ),
            ],
            items_by_step_id={
                "step-llm": [
                    _FakeExecutionEntity(
                        id="item-tool-call",
                        kind="tool_call",
                        status="completed",
                        summary_payload={
                            "runtime_semantic_kind": "runtime.assistant_tool_call",
                            "llm_invocation_id": "llm-invocation-tools",
                            "llm_response_item_id": "llm-response-tool-call",
                            "tool_call_id": "call-weather",
                            "tool_call_names": ["weather.forecast"],
                        },
                    ),
                ],
                "step-tool-batch": [
                    _FakeExecutionEntity(
                        id="item-tool-run",
                        kind="tool_run",
                        status="completed",
                        summary_payload={
                            "tool_call_id": "call-weather",
                            "tool_run_id": "tool-run-weather",
                        },
                    ),
                    _FakeExecutionEntity(
                        id="item-tool-result",
                        kind="tool_result",
                        status="completed",
                        summary_payload={
                            "runtime_semantic_kind": "runtime.tool_result",
                            "tool_call_id": "call-weather",
                            "tool_run_id": "tool-run-weather",
                            "session_item_id": "session-item-tool-result",
                        },
                    ),
                ],
            },
        ),
    )

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:tool-batch-step",
            agent_id="assistant",
            metadata={"last_run_id": "run-tool-batch-step"},
        ),
    )
    nodes = {
        node.id: node
        for node in services["tree"].list_tree("session:tool-batch-step").nodes
    }

    tool_batch_step = nodes["session.step.step-tool-batch"]
    assert tool_batch_step.kind == "session_step"
    assert tool_batch_step.owner_ref["kind"] == "tool_batch"
    assert tool_batch_step.owner_ref["status"] == "completed"

    tool_run = nodes["session.step.item.item-tool-run"]
    assert tool_run.parent_id == "session.step.step-tool-batch"
    assert tool_run.kind == "runtime_tool_run"
    assert tool_run.owner_ref["tool_call_id"] == "call-weather"
    assert tool_run.owner_ref["tool_run_id"] == "tool-run-weather"

    tool_result = nodes["session.step.item.item-tool-result"]
    assert tool_result.parent_id == "session.step.step-tool-batch"
    assert tool_result.kind == "runtime_tool_result"
    assert tool_result.owner_ref["runtime_semantic_kind"] == "runtime.tool_result"
    assert tool_result.owner_ref["session_item_id"] == "session-item-tool-result"

    tool_call = nodes["session.step.item.item-tool-call"]
    assert tool_call.parent_id == "session.step.step-llm"
    assert tool_call.kind == "runtime_assistant_tool_call"
    assert tool_call.owner_ref["llm_response_item_id"] == "llm-response-tool-call"
    assert tool_call.owner_ref["tool_call_id"] == "call-weather"


def test_session_adapter_keeps_assistant_item_source_refs_when_collapsed() -> None:
    session_service = _session_service()
    session_service.ensure_session(
        EnsureSessionInput(
            key="session:item-commentary",
            agent_id="assistant",
        ),
    )
    session_service.append_item(
        AppendSessionItemInput(
            session_key="session:item-commentary",
            kind=SessionItemKind.USER_MESSAGE,
            role="user",
            content_payload={"blocks": [{"type": "text", "text": "continue"}]},
            source_module="orchestration",
            source_kind="orchestration_run",
            source_id="run-item-commentary",
        ),
    )
    assistant_item = session_service.append_item(
        AppendSessionItemInput(
            session_key="session:item-commentary",
            kind=SessionItemKind.ASSISTANT_MESSAGE,
            role="assistant",
            content_payload={
                "blocks": [
                    {
                        "type": "text",
                        "text": "HISTORICAL_ASSISTANT_COMMENTARY",
                    },
                ],
            },
            source_module="llm",
            source_kind="llm_response_item",
            source_id="llm-item-commentary-1",
            provider_item_id="provider-commentary-1",
        ),
    )
    services = _context_services(session_service)
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:item-commentary",
            agent_id="assistant",
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:item-commentary",
            node_id="session.items.current",
            action=ContextAction.EXPAND,
        ),
    )
    expanded_tree = services["tree"].list_tree("session:item-commentary")
    assistant_node = next(
        node
        for node in expanded_tree.nodes
        if node.owner_ref.get("session_item_id") == assistant_item.id
    )

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:item-commentary",
            node_id=assistant_node.id,
            action=ContextAction.COLLAPSE,
        ),
    )
    collapsed_tree = services["tree"].list_tree("session:item-commentary")
    collapsed_node = next(
        node for node in collapsed_tree.nodes if node.id == assistant_node.id
    )

    assert collapsed_node.state.collapsed is True
    assert collapsed_node.owner_ref["session_item_id"] == assistant_item.id
    assert collapsed_node.owner_ref["source_module"] == "llm"
    assert collapsed_node.owner_ref["source_kind"] == "llm_response_item"
    assert collapsed_node.owner_ref["source_id"] == "llm-item-commentary-1"
    assert collapsed_node.metadata["source_kind"] == "llm_response_item"
    assert collapsed_node.metadata["source_id"] == "llm-item-commentary-1"


def test_session_adapter_renders_expanded_messages_as_context_debug_xml() -> None:
    session_service = _session_service()
    session_service.ensure_session(
        EnsureSessionInput(
            key="session:render",
            agent_id="assistant",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:render",
            role="user",
            content_payload={"blocks": [{"type": "text", "text": "render me"}]},
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:render",
            role="assistant",
            content_payload={
                "type": "function_call",
                "call_id": "call-1",
                "name": "echo",
                "arguments": {"message": "render me"},
            },
            metadata={
                "tool_call_id": "call-1",
                "tool_name": "echo",
            },
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:render",
            role="tool",
            kind=SessionItemFixtureKind.TOOL_RESULT,
            content_payload={
                "tool_name": "echo",
                "tool_call_id": "call-1",
                "status": "succeeded",
                "content": [{"type": "text", "text": "echoed"}],
            },
            metadata={
                "tool_call_id": "call-1",
                "tool_name": "echo",
            },
        ),
    )
    services = _context_services(session_service)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:render",
            agent_id="assistant",
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:render",
            node_id="session.items.current",
            action=ContextAction.EXPAND,
        ),
    )

    rendered = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:render"),
    )

    assert '<item role="user" sequence="1" kind="message"' in rendered.debug_body
    assert "render me" in rendered.debug_body
    assert '<tool_interaction tool_name="echo"' in rendered.debug_body
    tool_interaction_line = next(
        line
        for line in rendered.debug_body.splitlines()
        if '<tool_interaction tool_name="echo"' in line
    )
    assert 'status="succeeded"' in rendered.debug_body
    assert 'sequence="2-3"' in rendered.debug_body
    assert 'call_id="call-1"' not in tool_interaction_line
    assert 'frontier="false"' not in tool_interaction_line
    assert 'consumed="true"' not in tool_interaction_line
    assert 'superseded="false"' not in tool_interaction_line
    assert "<refs " not in rendered.debug_body
    assert "<arguments>" not in rendered.debug_body
    assert "<result>" not in rendered.debug_body

    tree = services["tree"].list_tree("session:render")
    tool_node = next(node for node in tree.nodes if node.kind == "tool_interaction")
    assert tool_node.state.collapsed is True
    assert tool_node.state.consumed is True
    assert tool_node.metadata["superseded"] is False
    assert tool_node.owner_ref["superseded"] is False
    assert tool_node.metadata["snapshot_visibility_status"] == "folded_consumed_history"
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:render",
            node_id=tool_node.id,
            action=ContextAction.EXPAND,
        ),
    )
    expanded_render = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:render"),
    )

    assert "<arguments>" not in expanded_render.debug_body
    assert "<result>" not in expanded_render.debug_body
    assert "content_omitted" in expanded_render.debug_body

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:render",
            node_id=tool_node.id,
            action=ContextAction.PIN,
        ),
    )
    pinned_render = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:render"),
    )

    assert "<arguments>" in pinned_render.debug_body
    assert "&quot;message&quot;: &quot;render me&quot;" in pinned_render.debug_body
    assert "<result>" in pinned_render.debug_body
    assert "echoed" in pinned_render.debug_body


def test_session_adapter_renders_assistant_progress_before_tool_interaction() -> None:
    session_service = _session_service()
    session_service.ensure_session(
        EnsureSessionInput(
            key="session:assistant-progress",
            agent_id="assistant",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:assistant-progress",
            role="user",
            content_payload={"blocks": [{"type": "text", "text": "inspect page"}]},
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:assistant-progress",
            role="assistant",
            content_payload={
                "blocks": [
                    {
                        "type": "text",
                        "text": "我先检查页面状态。",
                    },
                ],
                "text": "我先检查页面状态。",
                "finish_reason": "tool_calls",
            },
            source_kind="llm_invocation",
            source_id="inv-progress",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:assistant-progress",
            role="assistant",
            content_payload={
                "type": "function_call",
                "call_id": "call-1",
                "name": "browser.snapshot",
                "arguments": {},
            },
            source_kind="llm_invocation",
            source_id="inv-progress",
            metadata={
                "tool_call_id": "call-1",
                "tool_name": "browser.snapshot",
            },
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:assistant-progress",
            role="tool",
            kind=SessionItemFixtureKind.TOOL_RESULT,
            content_payload={
                "tool_name": "browser.snapshot",
                "tool_call_id": "call-1",
                "status": "succeeded",
                "content": [{"type": "text", "text": "snapshot ok"}],
            },
            metadata={
                "tool_call_id": "call-1",
                "tool_name": "browser.snapshot",
            },
        ),
    )
    services = _context_services(session_service)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:assistant-progress",
            agent_id="assistant",
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:assistant-progress",
            node_id="session.items.current",
            action=ContextAction.EXPAND,
        ),
    )

    rendered = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:assistant-progress"),
    )

    assert '<item role="assistant" sequence="2" kind="message"' in rendered.debug_body
    assert "我先检查页面状态。" in rendered.debug_body
    assert '<tool_interaction tool_name="browser.snapshot"' in rendered.debug_body
    assert 'sequence="3-4"' in rendered.debug_body


def test_session_adapter_does_not_infer_current_run_frontier_without_execution_fact() -> None:
    session_service = _session_service()
    session = session_service.ensure_session(
        EnsureSessionInput(
            key="session:current-tool-tail",
            agent_id="assistant",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:current-tool-tail",
            role="user",
            content_payload={"blocks": [{"type": "text", "text": "inspect current run"}]},
            source_kind="orchestration_run",
            source_id="run-current-tool-tail",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:current-tool-tail",
            role="assistant",
            content_payload={
                "type": "function_call",
                "call_id": "call-current",
                "name": "browser.observe",
                "arguments": {"mode": "wide"},
            },
            metadata={
                "tool_call_id": "call-current",
                "tool_name": "browser.observe",
            },
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:current-tool-tail",
            role="tool",
            kind=SessionItemFixtureKind.TOOL_RESULT,
            content_payload={
                "tool_name": "browser.observe",
                "tool_call_id": "call-current",
                "status": "succeeded",
                "metadata": {
                    "verified_ref": "current-ref",
                },
                "content": [
                    {
                        "type": "text",
                        "text": "visible observation " + ("x" * 240) + " SECRET_TAIL",
                    },
                ],
            },
            metadata={
                "tool_call_id": "call-current",
                "tool_name": "browser.observe",
            },
        ),
    )
    services = _context_services(session_service)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:current-tool-tail",
            agent_id="assistant",
            metadata={"last_run_id": "run-current-tool-tail"},
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:current-tool-tail",
            node_id="session.items.current",
            action=ContextAction.EXPAND,
        ),
    )
    frontier_render = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:current-tool-tail"),
    )

    assert '<tool_interaction tool_name="browser.observe"' in frontier_render.debug_body
    assert 'call_id="call-current"' not in frontier_render.debug_body
    assert 'lifecycle="frontier"' not in frontier_render.debug_body
    assert 'frontier="true"' not in frontier_render.debug_body
    assert 'consumed="false"' not in frontier_render.debug_body
    assert "<arguments>" not in frontier_render.debug_body
    assert "<result>" not in frontier_render.debug_body
    assert "SECRET_TAIL" not in frontier_render.debug_body

    tree = services["tree"].list_tree("session:current-tool-tail")
    tool_node = next(node for node in tree.nodes if node.kind == "tool_interaction")
    assert tool_node.state.collapsed is True
    assert tool_node.state.consumed is True
    assert tool_node.metadata["lifecycle_status"] == "observed"
    assert tool_node.metadata["frontier"] is False
    assert tool_node.metadata["consumed"] is True
    assert tool_node.metadata["observed"] is True
    assert tool_node.metadata["superseded"] is False
    assert tool_node.metadata["snapshot_visibility_status"] == "folded_consumed_history"
    assert tool_node.metadata["collapsed_by_default"] is True
    assert session.active_session_id in tool_node.id


def test_session_adapter_uses_execution_consumption_for_current_run_frontier() -> None:
    session_service = _session_service()
    session = session_service.ensure_session(
        EnsureSessionInput(
            key="session:execution-consumed",
            agent_id="assistant",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:execution-consumed",
            role="user",
            content_payload={"blocks": [{"type": "text", "text": "continue tool chain"}]},
            source_kind="orchestration_run",
            source_id="run-execution-consumed",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:execution-consumed",
            role="assistant",
            content_payload={
                "type": "function_call",
                "call_id": "call-consumed",
                "name": "context_tree.expand",
                "arguments": {"node_id": "tools.browser"},
            },
            metadata={
                "tool_call_id": "call-consumed",
                "tool_name": "context_tree.expand",
            },
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:execution-consumed",
            role="tool",
            kind=SessionItemFixtureKind.TOOL_RESULT,
            content_payload={
                "tool_name": "context_tree.expand",
                "tool_call_id": "call-consumed",
                "status": "succeeded",
                "content": [
                    {
                        "type": "text",
                        "text": "consumed preview " + ("x" * 260) + " CONSUMED_SECRET_TAIL",
                    },
                ],
            },
            metadata={
                "tool_call_id": "call-consumed",
                "tool_name": "context_tree.expand",
            },
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:execution-consumed",
            role="assistant",
            content_payload={
                "type": "function_call",
                "call_id": "call-frontier",
                "name": "browser.runtime.evaluate",
                "arguments": {"expression": "window.$nuxt"},
            },
            metadata={
                "tool_call_id": "call-frontier",
                "tool_name": "browser.runtime.evaluate",
            },
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:execution-consumed",
            role="tool",
            kind=SessionItemFixtureKind.TOOL_RESULT,
            content_payload={
                "tool_name": "browser.runtime.evaluate",
                "tool_call_id": "call-frontier",
                "status": "succeeded",
                "content": [{"type": "text", "text": "FRONTIER_VISIBLE"}],
            },
            metadata={
                "tool_call_id": "call-frontier",
                "tool_name": "browser.runtime.evaluate",
            },
        ),
    )
    execution_query = _FakeExecutionQuery(
        turn_id="run-execution-consumed",
        summary_payload={
            "llm_transcript_consumption": {
                "draft_input_sequence_range": {
                    "sessions": [
                        {
                            "session_id": session.active_session_id,
                            "from_sequence_no": 1,
                            "to_sequence_no": 3,
                            "item_count": 3,
                        },
                    ],
                },
            },
        },
    )
    services = _context_services(session_service, execution_query=execution_query)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:execution-consumed",
            agent_id="assistant",
            metadata={"last_run_id": "run-execution-consumed"},
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:execution-consumed",
            node_id="session.items.current",
            action=ContextAction.EXPAND,
        ),
    )
    rendered = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:execution-consumed"),
    )
    tree = services["tree"].list_tree("session:execution-consumed")
    consumed_node = next(
        node
        for node in tree.nodes
        if node.kind == "tool_interaction"
        and node.metadata["tool_call_id"] == "call-consumed"
    )
    frontier_node = next(
        node
        for node in tree.nodes
        if node.kind == "tool_interaction"
        and node.metadata["tool_call_id"] == "call-frontier"
    )

    assert consumed_node.state.collapsed is True
    assert consumed_node.state.opened is False
    assert consumed_node.state.consumed is True
    assert consumed_node.metadata["frontier"] is False
    assert consumed_node.metadata["consumed"] is True
    assert consumed_node.metadata["opened_by_default"] is False
    assert consumed_node.metadata["consumed_through_sequence_no"] == 3
    assert consumed_node.metadata["snapshot_visibility_status"] == "folded_consumed_history"
    assert frontier_node.state.collapsed is False
    assert frontier_node.state.consumed is False
    assert frontier_node.metadata["frontier"] is True
    assert frontier_node.metadata["consumed"] is False
    assert frontier_node.metadata["consumed_through_sequence_no"] == 3
    assert frontier_node.metadata["snapshot_visibility_status"] == "frontier_protocol_tail"
    assert 'call_id="call-consumed"' not in rendered.debug_body
    assert 'call_id="call-frontier"' in rendered.debug_body
    consumed_line = next(
        line
        for line in rendered.debug_body.splitlines()
        if '<tool_interaction tool_name="context_tree.expand"' in line
    )
    assert "current-turn result_sha256=" in consumed_line
    assert "consumed preview" not in consumed_line
    assert "CONSUMED_SECRET_TAIL" not in rendered.debug_body
    assert "FRONTIER_VISIBLE" in rendered.debug_body


def test_session_adapter_without_execution_fact_does_not_infer_tool_frontier() -> None:
    session_service = _session_service()
    session_service.ensure_session(
        EnsureSessionInput(
            key="session:no-inferred-frontier",
            agent_id="assistant",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:no-inferred-frontier",
            role="user",
            content_payload={"blocks": [{"type": "text", "text": "continue browser task"}]},
            source_kind="orchestration_run",
            source_id="run-no-inferred-frontier",
        ),
    )
    for index in range(1, 4):
        call_id = f"call-legacy-{index}"
        session_service.append_item_fixture(
            AppendSessionItemFixtureInput(
                session_key="session:no-inferred-frontier",
                role="assistant",
                content_payload={
                    "type": "function_call",
                    "call_id": call_id,
                    "name": "browser.observe",
                    "arguments": {"step": index},
                },
                metadata={
                    "tool_call_id": call_id,
                    "tool_name": "browser.observe",
                },
            ),
        )
        session_service.append_item_fixture(
            AppendSessionItemFixtureInput(
                session_key="session:no-inferred-frontier",
                role="tool",
                kind=SessionItemFixtureKind.TOOL_RESULT,
                content_payload={
                    "tool_name": "browser.observe",
                    "tool_call_id": call_id,
                    "status": "succeeded",
                    "content": [
                        {
                            "type": "text",
                            "text": f"result {index} SECRET_{index}",
                        },
                    ],
                },
                metadata={
                    "tool_call_id": call_id,
                    "tool_name": "browser.observe",
                },
            ),
        )
    services = _context_services(session_service)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:no-inferred-frontier",
            agent_id="assistant",
            metadata={"last_run_id": "run-no-inferred-frontier"},
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:no-inferred-frontier",
            node_id="session.items.current",
            action=ContextAction.EXPAND,
        ),
    )
    rendered = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:no-inferred-frontier"),
    )
    tool_nodes = {
        node.metadata["tool_call_id"]: node
        for node in services["tree"].list_tree("session:no-inferred-frontier").nodes
        if node.kind == "tool_interaction"
    }

    assert tool_nodes["call-legacy-1"].metadata["frontier"] is False
    assert tool_nodes["call-legacy-1"].metadata["consumed"] is True
    assert tool_nodes["call-legacy-2"].metadata["frontier"] is False
    assert tool_nodes["call-legacy-2"].metadata["consumed"] is True
    assert tool_nodes["call-legacy-3"].metadata["frontier"] is False
    assert tool_nodes["call-legacy-3"].metadata["consumed"] is True
    assert "SECRET_1" not in rendered.debug_body
    assert "SECRET_2" not in rendered.debug_body
    assert "SECRET_3" not in rendered.debug_body


def test_session_adapter_without_execution_fact_does_not_infer_llm_tool_batch_frontier() -> None:
    session_service = _session_service()
    session_service.ensure_session(
        EnsureSessionInput(
            key="session:no-inferred-batch-frontier",
            agent_id="assistant",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:no-inferred-batch-frontier",
            role="user",
            content_payload={"blocks": [{"type": "text", "text": "continue browser task"}]},
            source_kind="orchestration_run",
            source_id="run-no-inferred-batch-frontier",
        ),
    )
    batches = (
        ("inv-old", ("call-old",)),
        ("inv-latest", ("call-latest-a", "call-latest-b")),
    )
    for source_id, call_ids in batches:
        for call_id in call_ids:
            session_service.append_item_fixture(
                AppendSessionItemFixtureInput(
                    session_key="session:no-inferred-batch-frontier",
                    role="assistant",
                    content_payload={
                        "type": "function_call",
                        "call_id": call_id,
                        "name": "browser.evaluate",
                        "arguments": {"call_id": call_id},
                    },
                    source_kind="llm_invocation",
                    source_id=source_id,
                    metadata={
                        "tool_call_id": call_id,
                        "tool_name": "browser.evaluate",
                    },
                ),
            )
        for call_id in call_ids:
            session_service.append_item_fixture(
                AppendSessionItemFixtureInput(
                    session_key="session:no-inferred-batch-frontier",
                    role="tool",
                    kind=SessionItemFixtureKind.TOOL_RESULT,
                    content_payload={
                        "tool_name": "browser.evaluate",
                        "tool_call_id": call_id,
                        "status": "succeeded",
                        "content": [{"type": "text", "text": f"{call_id} result"}],
                    },
                    metadata={
                        "tool_call_id": call_id,
                        "tool_name": "browser.evaluate",
                    },
                ),
            )
    services = _context_services(session_service)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:no-inferred-batch-frontier",
            agent_id="assistant",
            metadata={"last_run_id": "run-no-inferred-batch-frontier"},
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:no-inferred-batch-frontier",
            node_id="session.items.current",
            action=ContextAction.EXPAND,
        ),
    )
    services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:no-inferred-batch-frontier"),
    )
    tool_nodes = {
        node.metadata["tool_call_id"]: node
        for node in services["tree"].list_tree("session:no-inferred-batch-frontier").nodes
        if node.kind == "tool_interaction"
    }

    assert tool_nodes["call-old"].metadata["frontier"] is False
    assert tool_nodes["call-old"].metadata["consumed"] is True
    assert tool_nodes["call-latest-a"].metadata["frontier"] is False
    assert tool_nodes["call-latest-a"].metadata["consumed"] is True
    assert tool_nodes["call-latest-b"].metadata["frontier"] is False
    assert tool_nodes["call-latest-b"].metadata["consumed"] is True


def test_session_adapter_keeps_long_browser_tool_chain_under_context_budget() -> None:
    session_service = _session_service()
    session = session_service.ensure_session(
        EnsureSessionInput(
            key="session:long-browser-chain",
            agent_id="assistant",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:long-browser-chain",
            role="user",
            content_payload={"blocks": [{"type": "text", "text": "inspect airline fares"}]},
            source_kind="orchestration_run",
            source_id="run-long-browser-chain",
        ),
    )
    for index in range(1, 56):
        call_id = f"call-browser-{index}"
        session_service.append_item_fixture(
            AppendSessionItemFixtureInput(
                session_key="session:long-browser-chain",
                role="assistant",
                content_payload={
                    "type": "function_call",
                    "call_id": call_id,
                    "name": "browser.network.fetch",
                    "arguments": {
                        "url": f"https://example.test/api/fares/{index}",
                        "method": "POST",
                    },
                },
                metadata={
                    "tool_call_id": call_id,
                    "tool_name": "browser.network.fetch",
                },
            ),
        )
        session_service.append_item_fixture(
            AppendSessionItemFixtureInput(
                session_key="session:long-browser-chain",
                role="tool",
                kind=SessionItemFixtureKind.TOOL_RESULT,
                content_payload={
                    "tool_name": "browser.network.fetch",
                    "tool_call_id": call_id,
                    "tool_run_id": f"tool-run-browser-{index}",
                    "status": "succeeded",
                    "details": {
                        "kind": "network-fetch-as-page",
                        "endpoint": f"/portal/v3/shopping/briefInfo/{index}",
                        "method": "POST",
                        "request_id": f"req-browser-{index}",
                        "body_removed_from_details": True,
                    },
                    "metadata": {
                        "artifact_ids": [f"artifact-browser-body-{index}"],
                        "request_id": f"req-browser-{index}",
                        "payload_shape": {
                            "depCityCode": "str",
                            "arrCityCode": "str",
                        },
                        "result_shape": {
                            "data": {
                                "flightItems": {
                                    "type": "list",
                                    "count": index,
                                },
                            },
                        },
                    },
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"raw browser body {index} "
                                + ("x" * 3200)
                                + f" OLD_BROWSER_SECRET_{index}"
                            ),
                        },
                    ],
                },
                metadata={
                    "tool_call_id": call_id,
                    "tool_name": "browser.network.fetch",
                },
            ),
        )
    execution_query = _FakeExecutionQuery(
        turn_id="run-long-browser-chain",
        summary_payload={
            "llm_transcript_consumption": {
                "draft_input_sequence_range": {
                    "sessions": [
                        {
                            "session_id": session.active_session_id,
                            "from_sequence_no": 1,
                            "to_sequence_no": 109,
                            "item_count": 109,
                        },
                    ],
                },
            },
        },
    )
    services = _context_services(session_service, execution_query=execution_query)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:long-browser-chain",
            agent_id="assistant",
            metadata={"last_run_id": "run-long-browser-chain"},
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:long-browser-chain",
            node_id="session.items.current",
            action=ContextAction.EXPAND,
        ),
    )
    rendered = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:long-browser-chain"),
    )
    tree = services["tree"].list_tree("session:long-browser-chain")
    tool_nodes = [node for node in tree.nodes if node.kind == "tool_interaction"]
    range_nodes = [
        node
        for node in tree.nodes
        if node.kind == "session_tool_interaction_range"
    ]
    frontier_nodes = [node for node in tool_nodes if node.metadata["frontier"] is True]
    consumed_nodes = [node for node in tool_nodes if node.metadata["consumed"] is True]

    assert len(tool_nodes) == 9
    assert len(range_nodes) == 1
    assert range_nodes[0].metadata["hidden_tool_interaction_count"] == 46
    assert range_nodes[0].metadata["range_reason_code"] == (
        "active_consumed_tool_history_fold"
    )
    assert [node.metadata["tool_call_id"] for node in frontier_nodes] == [
        "call-browser-55",
    ]
    assert [node.metadata["tool_call_id"] for node in consumed_nodes] == [
        f"call-browser-{index}" for index in range(47, 55)
    ]
    assert rendered.estimate.text_chars < 50_000
    assert rendered.estimate.text_tokens < 13_000
    assert "OLD_BROWSER_SECRET_1" not in rendered.debug_body
    assert "OLD_BROWSER_SECRET_54" not in rendered.debug_body
    assert "OLD_BROWSER_SECRET_55" not in rendered.debug_body
    assert "tool_result_ref:" in rendered.debug_body
    assert "body_storage: externalized" in rendered.debug_body
    assert "artifact-browser-body-55" in rendered.debug_body
    assert 'frontier="true"' in rendered.debug_body

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:long-browser-chain",
            node_id=range_nodes[0].id,
            action=ContextAction.EXPAND,
        ),
    )
    expanded_tree = services["tree"].list_tree("session:long-browser-chain")
    expanded_tool_nodes = [
        node for node in expanded_tree.nodes if node.kind == "tool_interaction"
    ]
    hidden_tool_nodes = [
        node for node in expanded_tool_nodes if node.parent_id == range_nodes[0].id
    ]

    assert len(expanded_tool_nodes) == 55
    assert len(hidden_tool_nodes) == 46
    assert hidden_tool_nodes[0].metadata["tool_call_id"] == "call-browser-1"


def test_session_adapter_keeps_plain_tool_history_results_compact_by_default() -> None:
    session_service = _session_service()
    session = session_service.ensure_session(
        EnsureSessionInput(
            key="session:plain-tool-history",
            agent_id="assistant",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:plain-tool-history",
            role="user",
            content_payload={"blocks": [{"type": "text", "text": "keep going"}]},
            source_kind="orchestration_run",
            source_id="run-plain-tool-history",
        ),
    )
    for index in range(1, 51):
        _append_tool_pair(
            session_service,
            session_key="session:plain-tool-history",
            call_id=f"call-plain-{index}",
            tool_name="debug.echo",
            arguments={"index": index},
            result_text=f"plain result {index} SECRET_PLAIN_{index}",
        )
    execution_query = _FakeExecutionQuery(
        turn_id="run-plain-tool-history",
        summary_payload={
            "llm_transcript_consumption": {
                "draft_input_sequence_range": {
                    "sessions": [
                        {
                            "session_id": session.active_session_id,
                            "from_sequence_no": 1,
                            "to_sequence_no": 99,
                            "item_count": 99,
                        },
                    ],
                },
            },
        },
    )
    services = _context_services(session_service, execution_query=execution_query)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:plain-tool-history",
            agent_id="assistant",
            metadata={"last_run_id": "run-plain-tool-history"},
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:plain-tool-history",
            node_id="session.items.current",
            action=ContextAction.EXPAND,
        ),
    )
    rendered = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:plain-tool-history"),
    )
    tree = services["tree"].list_tree("session:plain-tool-history")
    tool_nodes = [node for node in tree.nodes if node.kind == "tool_interaction"]
    frontier_nodes = [node for node in tool_nodes if node.metadata["frontier"] is True]

    assert [node.metadata["tool_call_id"] for node in frontier_nodes] == [
        "call-plain-50",
    ]
    assert "SECRET_PLAIN_1" not in rendered.debug_body
    assert "SECRET_PLAIN_49" not in rendered.debug_body
    assert "SECRET_PLAIN_50" in rendered.debug_body
    assert rendered.debug_body.count("<result>") == 1


def test_session_adapter_projects_current_run_evidence_ledger_from_tool_results() -> None:
    session_service = _session_service()
    session_service.ensure_session(
        EnsureSessionInput(
            key="session:evidence",
            agent_id="assistant",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:evidence",
            role="user",
            content_payload={"blocks": [{"type": "text", "text": "verify airfare"}]},
            source_kind="orchestration_run",
            source_id="run-evidence",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:evidence",
            role="assistant",
            content_payload={
                "type": "function_call",
                "call_id": "call-expand",
                "name": "context_tree.expand",
                "arguments": {"node_id": "tools.available"},
            },
            metadata={
                "tool_call_id": "call-expand",
                "tool_name": "context_tree.expand",
            },
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:evidence",
            role="tool",
            kind=SessionItemFixtureKind.TOOL_RESULT,
            content_payload={
                "tool_name": "context_tree.expand",
                "tool_call_id": "call-expand",
                "status": "succeeded",
                "content": [{"type": "text", "text": "expanded tools"}],
            },
            metadata={
                "tool_call_id": "call-expand",
                "tool_name": "context_tree.expand",
            },
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:evidence",
            role="assistant",
            content_payload={
                "type": "function_call",
                "call_id": "call-network",
                "name": "browser.network.fetch",
                "arguments": {"url": "https://www.ceair.com/zh/cny/home"},
            },
            metadata={
                "tool_call_id": "call-network",
                "tool_name": "browser.network.fetch",
            },
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:evidence",
            role="tool",
            kind=SessionItemFixtureKind.TOOL_RESULT,
            content_payload={
                "tool_name": "browser.network.fetch",
                "tool_call_id": "call-network",
                "tool_run_id": "tool-run-network",
                "status": "succeeded",
                "details": {
                    "kind": "network-fetch-as-page",
                    "url": "https://www.ceair.com/zh/cny/home",
                    "endpoint": "/portal/v3/shopping/briefInfo",
                    "method": "POST",
                    "status_code": 200,
                    "request_id": "req-east-1",
                    "body_removed_from_details": True,
                },
                "metadata": {
                    "host_service_key": "host:browser:crxzipple",
                    "profile": "crxzipple",
                    "target_id": "tab-east",
                    "artifact_ids": ["artifact-network-body"],
                    "payload_shape": {
                        "depCityCode": "str",
                        "arrCityCode": "str",
                    },
                    "result_shape": {
                        "data": {
                            "flightItems": {
                                "type": "list",
                                "count": 35,
                                "item": {"flightSort": {"price": "int"}},
                            },
                        },
                    },
                    "runtime_globals": ["$nuxt", "__NUXT__"],
                    "verified_ref": "ref-flight-date",
                    "request_id": "req-east-1",
                },
                "content": [
                    {
                        "type": "text",
                        "text": "response preview " + ("x" * 260) + " SECRET_BODY",
                    },
                ],
            },
            metadata={
                "tool_call_id": "call-network",
                "tool_name": "browser.network.fetch",
            },
        ),
    )
    services = _context_services(session_service)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:evidence",
            agent_id="assistant",
            metadata={"last_run_id": "run-evidence"},
        ),
    )

    tree = services["tree"].list_tree("session:evidence")
    assert not any(node.id == "session.evidence.current" for node in tree.nodes)
    assert not any(node.kind == "session_evidence" for node in tree.nodes)

    rendered = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:evidence"),
    )

    assert "Current Evidence Ledger" not in rendered.debug_body
    assert '<evidence ' not in rendered.debug_body
    assert 'type="api_endpoint"' not in rendered.debug_body
    assert "SECRET_BODY" not in rendered.debug_body


def test_session_adapter_renders_tool_result_envelope_refs() -> None:
    session_service = _session_service()
    session_service.ensure_session(
        EnsureSessionInput(
            key="session:tool-result-envelope",
            agent_id="assistant",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:tool-result-envelope",
            role="assistant",
            content_payload={
                "type": "function_call",
                "call_id": "call-large-result",
                "name": "debug.large_result",
                "arguments": {},
            },
            metadata={
                "tool_call_id": "call-large-result",
                "tool_name": "debug.large_result",
            },
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:tool-result-envelope",
            role="tool",
            kind=SessionItemFixtureKind.TOOL_RESULT,
            content_payload={
                "tool_name": "debug.large_result",
                "tool_call_id": "call-large-result",
                "status": "succeeded",
                "content": [{"type": "text", "text": "short preview"}],
                "metadata": {
                    "artifact_ids": ["artifact-large-result"],
                    TOOL_RESULT_ENVELOPE_METADATA_KEY: {
                        "status": "ok",
                        "summary": "Large result was externalized.",
                        "key_facts": {"original_text_chars": 24000},
                        "warnings": [],
                        "evidence_refs": ["artifact-large-result"],
                        "read_handles": [
                            {
                                "kind": "artifact",
                                "artifact_id": "artifact-large-result",
                                "mime_type": "text/plain",
                            },
                        ],
                        "omitted_count": 1,
                        "omitted_chars": 22400,
                        "truncated": True,
                    },
                },
            },
            metadata={
                "tool_call_id": "call-large-result",
                "tool_name": "debug.large_result",
            },
        ),
    )
    services = _context_services(session_service)
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:tool-result-envelope",
            agent_id="assistant",
        ),
    )
    tree = services["tree"].list_tree("session:tool-result-envelope")
    tool_node = next(node for node in tree.nodes if node.kind == "tool_interaction")
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:tool-result-envelope",
            node_id=tool_node.id,
            action=ContextAction.EXPAND,
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:tool-result-envelope",
            node_id=tool_node.id,
            action=ContextAction.PIN,
        ),
    )

    rendered = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:tool-result-envelope"),
    )

    assert '<result_summary source="tool_result_envelope"' in rendered.debug_body
    assert 'truncated="true"' in rendered.debug_body
    assert 'omitted_chars="22400"' in rendered.debug_body
    assert "<summary>" in rendered.debug_body
    assert "Large result was externalized." in rendered.debug_body
    assert "<evidence_path>" not in rendered.debug_body
    assert "network_truth (Trace Network Truth)" not in rendered.debug_body
    assert "<artifact_refs>" in rendered.debug_body
    assert "artifact-large-result" in rendered.debug_body
    assert "<read_handles>" in rendered.debug_body
    assert "short preview" not in rendered.debug_body
    assert "<result>" not in rendered.debug_body


def test_evidence_type_classifies_api_shape_and_verified_browser_facts() -> None:
    assert (
        evidence_type(
            tool_name="browser.network.fetch_as_page",
            status="succeeded",
            facts={"kind": "network-fetch-as-page", "result_shape": {"data": "dict"}},
        )
        == "api_endpoint"
    )
    assert (
        evidence_type(
            tool_name="browser.runtime.evaluate",
            status="succeeded",
            facts={"result_shape": {"value": "dict"}},
        )
        == "result_shape"
    )
    assert (
        evidence_type(
            tool_name="browser.runtime.evaluate",
            status="succeeded",
            facts={"payload_shape": {"depCityCode": "str"}},
        )
        == "payload_shape"
    )
    assert (
        evidence_type(
            tool_name="browser.click",
            status="succeeded",
            facts={"selector": "#submit"},
        )
        == "observation"
    )
    assert (
        evidence_type(
            tool_name="browser.click",
            status="failed",
            facts={"selector": "#submit"},
        )
        == "failed_attempt"
    )


def test_evidence_ledger_honors_explicit_superseded_lifecycle() -> None:
    session_service = _session_service()
    session_service.ensure_session(
        EnsureSessionInput(
            key="session:evidence-superseded",
            agent_id="assistant",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:evidence-superseded",
            role="user",
            content_payload={"blocks": [{"type": "text", "text": "check endpoint"}]},
            source_kind="orchestration_run",
            source_id="run-evidence-superseded",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:evidence-superseded",
            role="assistant",
            content_payload={
                "type": "function_call",
                "call_id": "call-old-endpoint",
                "name": "browser.network.fetch",
                "arguments": {"url": "https://example.test/old"},
            },
            metadata={
                "tool_call_id": "call-old-endpoint",
                "tool_name": "browser.network.fetch",
            },
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:evidence-superseded",
            role="tool",
            kind=SessionItemFixtureKind.TOOL_RESULT,
            content_payload={
                "tool_name": "browser.network.fetch",
                "tool_call_id": "call-old-endpoint",
                "status": "succeeded",
                "details": {
                    "kind": "network-fetch-as-page",
                    "endpoint": "/old",
                    "method": "POST",
                    "tool_lifecycle": {
                        "lifecycle_status": "superseded",
                        "superseded_by_tool_call_id": "call-new-endpoint",
                    },
                },
                "metadata": {
                    "payload_shape": {"old": "str"},
                },
                "content": [{"type": "text", "text": "old endpoint worked"}],
            },
            metadata={
                "tool_call_id": "call-old-endpoint",
                "tool_name": "browser.network.fetch",
            },
        ),
    )
    services = _context_services(session_service)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:evidence-superseded",
            agent_id="assistant",
            metadata={"last_run_id": "run-evidence-superseded"},
        ),
    )

    tree = services["tree"].list_tree("session:evidence-superseded")
    assert not any(node.kind == "session_evidence" for node in tree.nodes)

    rendered = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:evidence-superseded"),
    )

    assert '<evidence ' not in rendered.debug_body


def test_session_adapter_keeps_orphan_function_call_as_message_node() -> None:
    session_service = _session_service()
    session_service.ensure_session(
        EnsureSessionInput(
            key="session:orphan-call",
            agent_id="assistant",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:orphan-call",
            role="assistant",
            content_payload={
                "type": "function_call",
                "call_id": "pending-call",
                "name": "slow_tool",
                "arguments": {"query": "pending"},
            },
            metadata={
                "tool_call_id": "pending-call",
                "tool_name": "slow_tool",
            },
        ),
    )
    services = _context_services(session_service)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:orphan-call",
            agent_id="assistant",
        ),
    )
    rendered = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:orphan-call"),
    )

    assert '<item role="assistant" sequence="1" kind="message"' in rendered.debug_body
    assert "tool_call:" in rendered.debug_body
    assert "name: slow_tool" in rendered.debug_body
    assert "tool_interaction" not in rendered.debug_body


def test_session_adapter_renders_failed_tool_interaction_error_details() -> None:
    session_service = _session_service()
    session_service.ensure_session(
        EnsureSessionInput(
            key="session:failed-tool",
            agent_id="assistant",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:failed-tool",
            role="assistant",
            content_payload={
                "type": "function_call",
                "call_id": "call-failed",
                "name": "browser.snapshot",
                "arguments": {"format": "interactive"},
            },
            metadata={
                "tool_call_id": "call-failed",
                "tool_name": "browser.snapshot",
            },
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:failed-tool",
            role="tool",
            kind=SessionItemFixtureKind.TOOL_RESULT,
            content_payload={
                "tool_name": "browser.snapshot",
                "tool_call_id": "call-failed",
                "status": "failed",
                "error": {
                    "code": "setup_needed",
                    "message": "Browser profile is not ready.",
                },
                "content": [
                    {
                        "type": "text",
                        "text": "Browser profile is not ready.",
                    },
                ],
            },
            metadata={
                "tool_call_id": "call-failed",
                "tool_name": "browser.snapshot",
            },
        ),
    )
    services = _context_services(session_service)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:failed-tool",
            agent_id="assistant",
        ),
    )
    rendered = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:failed-tool"),
    )

    assert '<tool_interaction tool_name="browser.snapshot"' in rendered.debug_body
    assert 'status="failed"' in rendered.debug_body
    assert 'lifecycle="failed"' in rendered.debug_body
    assert 'frontier="false"' not in rendered.debug_body
    assert 'consumed="true"' not in rendered.debug_body
    assert 'failed="true"' in rendered.debug_body
    tool_interaction_line = next(
        line
        for line in rendered.debug_body.splitlines()
        if '<tool_interaction tool_name="browser.snapshot"' in line
    )
    assert 'superseded="false"' not in tool_interaction_line
    assert "<error>" not in rendered.debug_body
    assert "&quot;code&quot;: &quot;setup_needed&quot;" in rendered.debug_body
    assert "Browser profile is not ready." in rendered.debug_body
    tree = services["tree"].list_tree("session:failed-tool")
    tool_node = next(node for node in tree.nodes if node.kind == "tool_interaction")
    assert tool_node.state.collapsed is True
    assert tool_node.state.consumed is True
    assert tool_node.metadata["lifecycle_status"] == "failed"
    assert tool_node.metadata["failed"] is True
    assert tool_node.metadata["superseded"] is False

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:failed-tool",
            node_id=tool_node.id,
            action=ContextAction.EXPAND,
        ),
    )
    expanded_render = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:failed-tool"),
    )
    assert "<error>" not in expanded_render.debug_body

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:failed-tool",
            node_id=tool_node.id,
            action=ContextAction.PIN,
        ),
    )
    pinned_render = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:failed-tool"),
    )
    assert "<error>" in pinned_render.debug_body
    assert "&quot;code&quot;: &quot;setup_needed&quot;" in pinned_render.debug_body


def test_session_adapter_renders_explicit_superseded_tool_interaction_lifecycle() -> None:
    session_service = _session_service()
    session_service.ensure_session(
        EnsureSessionInput(
            key="session:superseded-tool",
            agent_id="assistant",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:superseded-tool",
            role="assistant",
            content_payload={
                "type": "function_call",
                "call_id": "call-old-endpoint",
                "name": "browser.network.inspect",
                "arguments": {"url": "/old"},
            },
            metadata={
                "tool_call_id": "call-old-endpoint",
                "tool_name": "browser.network.inspect",
            },
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:superseded-tool",
            role="tool",
            kind=SessionItemFixtureKind.TOOL_RESULT,
            content_payload={
                "tool_name": "browser.network.inspect",
                "tool_call_id": "call-old-endpoint",
                "status": "succeeded",
                "metadata": {
                    "tool_lifecycle": {
                        "superseded": True,
                        "superseded_by_tool_call_id": "call-new-endpoint",
                    },
                },
                "content": [
                    {
                        "type": "text",
                        "text": "old endpoint was replaced by a later request",
                    },
                ],
            },
            metadata={
                "tool_call_id": "call-old-endpoint",
                "tool_name": "browser.network.inspect",
            },
        ),
    )
    services = _context_services(session_service)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:superseded-tool",
            agent_id="assistant",
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:superseded-tool",
            node_id="session.items.current",
            action=ContextAction.EXPAND,
        ),
    )
    rendered = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:superseded-tool"),
    )

    assert '<tool_interaction tool_name="browser.network.inspect"' in rendered.debug_body
    assert 'lifecycle="superseded"' in rendered.debug_body
    assert 'superseded="true"' in rendered.debug_body
    tree = services["tree"].list_tree("session:superseded-tool")
    tool_node = next(node for node in tree.nodes if node.kind == "tool_interaction")
    assert tool_node.metadata["lifecycle_status"] == "superseded"
    assert tool_node.metadata["superseded"] is True
    assert tool_node.metadata["superseded_by_tool_call_id"] == "call-new-endpoint"
    assert tool_node.owner_ref["superseded"] is True
    assert tool_node.owner_ref["superseded_by_tool_call_id"] == "call-new-endpoint"


def test_session_adapter_uses_execution_lifecycle_fact_for_superseded_tool_interaction() -> None:
    session_service = _session_service()
    session = session_service.ensure_session(
        EnsureSessionInput(
            key="session:execution-superseded-tool",
            agent_id="assistant",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:execution-superseded-tool",
            role="user",
            content_payload={"blocks": [{"type": "text", "text": "inspect endpoint"}]},
            source_kind="orchestration_run",
            source_id="run-execution-superseded",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:execution-superseded-tool",
            role="assistant",
            content_payload={
                "type": "function_call",
                "call_id": "call-old-endpoint",
                "name": "browser.network.inspect",
                "arguments": {"url": "/old"},
            },
            metadata={
                "tool_call_id": "call-old-endpoint",
                "tool_name": "browser.network.inspect",
            },
        ),
    )
    result_message = session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:execution-superseded-tool",
            role="tool",
            kind=SessionItemFixtureKind.TOOL_RESULT,
            content_payload={
                "tool_name": "browser.network.inspect",
                "tool_call_id": "call-old-endpoint",
                "tool_run_id": "tool-run-old-endpoint",
                "status": "succeeded",
                "metadata": {
                    "payload_shape": {"query": "str"},
                },
                "content": [{"type": "text", "text": "old endpoint response"}],
            },
            metadata={
                "tool_call_id": "call-old-endpoint",
                "tool_name": "browser.network.inspect",
            },
        ),
    )
    execution_query = _FakeExecutionQuery(
        turn_id="run-execution-superseded",
        summary_payload={
            "llm_transcript_consumption": {
                "draft_input_sequence_range": {
                    "sessions": [
                        {
                            "session_id": session.active_session_id,
                            "from_sequence_no": 1,
                            "to_sequence_no": 3,
                            "item_count": 3,
                        },
                    ],
                },
            },
            "tool_call_id": "call-old-endpoint",
            "tool_run_id": "tool-run-old-endpoint",
            "result_session_item_id": result_message.id,
            "tool_lifecycle": {
                "superseded": True,
                "superseded_by_tool_call_id": "call-new-endpoint",
            },
        },
    )
    services = _context_services(session_service, execution_query=execution_query)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:execution-superseded-tool",
            agent_id="assistant",
            metadata={"last_run_id": "run-execution-superseded"},
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:execution-superseded-tool",
            node_id="session.items.current",
            action=ContextAction.EXPAND,
        ),
    )
    rendered = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:execution-superseded-tool"),
    )
    tree = services["tree"].list_tree("session:execution-superseded-tool")
    tool_node = next(node for node in tree.nodes if node.kind == "tool_interaction")

    assert 'lifecycle="superseded"' in rendered.debug_body
    assert 'superseded="true"' in rendered.debug_body
    assert tool_node.metadata["lifecycle_status"] == "superseded"
    assert tool_node.metadata["superseded"] is True
    assert tool_node.metadata["superseded_by_tool_call_id"] == "call-new-endpoint"
    assert not any(node.kind == "session_evidence" for node in tree.nodes)


def test_session_adapter_maps_explicit_replacement_fact_to_superseded_target() -> None:
    session_service = _session_service()
    session = session_service.ensure_session(
        EnsureSessionInput(
            key="session:execution-replacement-tool",
            agent_id="assistant",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:execution-replacement-tool",
            role="user",
            content_payload={"blocks": [{"type": "text", "text": "inspect endpoint"}]},
            source_kind="orchestration_run",
            source_id="run-execution-replacement",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:execution-replacement-tool",
            role="assistant",
            content_payload={
                "type": "function_call",
                "call_id": "call-old-endpoint",
                "name": "browser.network.inspect",
                "arguments": {"url": "/old"},
            },
            metadata={
                "tool_call_id": "call-old-endpoint",
                "tool_name": "browser.network.inspect",
            },
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:execution-replacement-tool",
            role="tool",
            kind=SessionItemFixtureKind.TOOL_RESULT,
            content_payload={
                "tool_name": "browser.network.inspect",
                "tool_call_id": "call-old-endpoint",
                "tool_run_id": "tool-run-old-endpoint",
                "status": "succeeded",
                "metadata": {
                    "payload_shape": {"query": "str"},
                },
                "content": [{"type": "text", "text": "old endpoint response"}],
            },
            metadata={
                "tool_call_id": "call-old-endpoint",
                "tool_name": "browser.network.inspect",
            },
        ),
    )
    execution_query = _FakeExecutionQuery(
        turn_id="run-execution-replacement",
        summary_payload={
            "llm_transcript_consumption": {
                "draft_input_sequence_range": {
                    "sessions": [
                        {
                            "session_id": session.active_session_id,
                            "from_sequence_no": 1,
                            "to_sequence_no": 3,
                            "item_count": 3,
                        },
                    ],
                },
            },
            "tool_call_id": "call-new-endpoint",
            "tool_run_id": "tool-run-new-endpoint",
            "tool_lifecycle": {
                "supersedes_tool_call_id": "call-old-endpoint",
            },
        },
    )
    services = _context_services(session_service, execution_query=execution_query)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:execution-replacement-tool",
            agent_id="assistant",
            metadata={"last_run_id": "run-execution-replacement"},
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:execution-replacement-tool",
            node_id="session.items.current",
            action=ContextAction.EXPAND,
        ),
    )
    rendered = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:execution-replacement-tool"),
    )
    tree = services["tree"].list_tree("session:execution-replacement-tool")
    tool_node = next(node for node in tree.nodes if node.kind == "tool_interaction")

    assert 'lifecycle="superseded"' in rendered.debug_body
    assert 'superseded="true"' in rendered.debug_body
    assert tool_node.metadata["lifecycle_status"] == "superseded"
    assert tool_node.metadata["superseded"] is True
    assert tool_node.metadata["superseded_by_tool_call_id"] == "call-new-endpoint"
    assert not any(node.kind == "session_evidence" for node in tree.nodes)


def test_session_adapter_renders_async_control_history_as_traceable_context_debug_xml() -> None:
    session_service = _session_service()
    session_service.ensure_session(
        EnsureSessionInput(
            key="session:async-control",
            agent_id="assistant",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:async-control",
            role="user",
            content_payload={"blocks": [{"type": "text", "text": "start async work"}]},
            source_kind="orchestration_run",
            source_id="run-async-control",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:async-control",
            role="assistant",
            content_payload={
                "type": "function_call",
                "call_id": "call-yield-1",
                "name": "sessions_yield",
                "arguments": {"reason": "wait for delegated work"},
            },
            source_kind="llm_invocation",
            source_id="llm-yield",
            metadata={
                "tool_call_id": "call-yield-1",
                "tool_name": "sessions_yield",
            },
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:async-control",
            role="tool",
            kind=SessionItemFixtureKind.TOOL_RESULT,
            content_payload={
                "tool_name": "sessions_yield",
                "tool_call_id": "call-yield-1",
                "status": "succeeded",
                "content": [
                    {
                        "type": "text",
                        "text": "Yielded control: wait for delegated work.",
                    },
                ],
            },
            source_kind="tool_run",
            source_id="tool-run-yield",
            metadata={
                "tool_call_id": "call-yield-1",
                "tool_name": "sessions_yield",
            },
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:async-control",
            role="assistant",
            content_payload={
                "type": "function_call",
                "call_id": "call-bg-1",
                "name": "background_echo",
                "arguments": {"message": "background hello"},
            },
            source_kind="llm_invocation",
            source_id="llm-background",
            metadata={
                "tool_call_id": "call-bg-1",
                "tool_name": "background_echo",
            },
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:async-control",
            role="tool",
            kind=SessionItemFixtureKind.TOOL_RESULT,
            content_payload={
                "tool_name": "background_echo",
                "tool_call_id": "call-bg-1",
                "status": "succeeded",
                "content": [
                    {"type": "text", "text": "background hello"},
                ],
            },
            source_kind="tool_run",
            source_id="tool-run-background",
            metadata={
                "tool_call_id": "call-bg-1",
                "tool_name": "background_echo",
            },
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:async-control",
            role="tool",
            kind=SessionItemFixtureKind.TOOL_RESULT,
            content_payload={
                "tool_name": "background_echo",
                "tool_call_id": "approval-background-1",
                "status": "approved",
                "content": [
                    {
                        "type": "text",
                        "text": "Approved once for this turn only for running background_echo.",
                    },
                ],
            },
            source_kind="approval_request",
            source_id="approval-background-1",
            metadata={
                "tool_call_id": "approval-background-1",
                "tool_name": "background_echo",
            },
        ),
    )
    services = _context_services(session_service)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:async-control",
            agent_id="assistant",
        ),
    )
    rendered = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:async-control"),
    )

    assert '<tool_interaction tool_name="sessions_yield"' in rendered.debug_body
    assert "wait for delegated work" not in rendered.debug_body
    assert '<tool_interaction tool_name="background_echo"' in rendered.debug_body
    assert "background hello" not in rendered.debug_body
    assert "approval-background-1" in rendered.debug_body
    assert "Approved once for this turn only" not in rendered.debug_body
    assert "result_sha256=" in rendered.debug_body


def test_session_adapter_renders_attachment_history_as_handles() -> None:
    session_service = _session_service()
    session_service.ensure_session(
        EnsureSessionInput(
            key="session:attachments",
            agent_id="assistant",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:attachments",
            role="user",
            content_payload={
                "blocks": [
                        {
                            "type": "image_ref",
                            "artifact_id": "artifact-image-1",
                            "mime_type": "image/png",
                            "name": "screen.png",
                            "data": "raw-image-bytes-should-not-render",
                        },
                        {
                            "type": "file_ref",
                            "artifact_id": "artifact-file-1",
                            "mime_type": "application/pdf",
                            "name": "report.pdf",
                            "text": "raw file body should not render",
                        },
                ],
            },
        ),
    )
    services = _context_services(session_service)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:attachments",
            agent_id="assistant",
        ),
    )
    tree = services["tree"].list_tree("session:attachments")
    attachment_node = next(
        node for node in tree.nodes if node.id.startswith("session.item.")
    )
    rendered = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:attachments"),
    )

    assert attachment_node.metadata["content_block_types"] == ["image_ref", "file_ref"]
    assert attachment_node.estimate.image_count == 1
    assert attachment_node.estimate.file_count == 1
    assert "[image:screen.png]" in rendered.debug_body
    assert "[file:report.pdf]" in rendered.debug_body
    assert "artifact-image-1" not in rendered.debug_body
    assert "artifact-file-1" not in rendered.debug_body
    assert "raw-image-bytes-should-not-render" not in rendered.debug_body
    assert "raw file body should not render" not in rendered.debug_body


def test_session_adapter_renders_current_segment_without_active_pagination() -> None:
    session_service = _session_service()
    session_service.ensure_session(
        EnsureSessionInput(
            key="session:current-render",
            agent_id="assistant",
        ),
    )
    for index in range(1, 4):
        session_service.append_item_fixture(
            AppendSessionItemFixtureInput(
                session_key="session:current-render",
                role="user",
                content_payload={
                    "blocks": [{"type": "text", "text": f"current render {index}"}],
                },
            ),
        )
    services = _context_services(session_service, recent_limit=2)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:current-render",
            agent_id="assistant",
        ),
    )
    rendered = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:current-render"),
    )

    assert "current render 1" in rendered.debug_body
    assert "current render 2" in rendered.debug_body
    assert "current render 3" in rendered.debug_body
    assert "older messages are available before" not in rendered.debug_body


def test_session_adapter_does_not_synthesize_compacted_segment_from_active_archives() -> None:
    session_service = _session_service()
    session = session_service.ensure_session(
        EnsureSessionInput(
            key="session:archive-only",
            agent_id="assistant",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:archive-only",
            role="user",
            content_payload={
                "blocks": [{"type": "text", "text": "legacy archived body"}],
            },
        ),
    )
    session_service.archive_item_fixtures(
        ArchiveSessionItemsFixtureInput(
            session_key="session:archive-only",
            session_id=session.active_session_id,
            max_sequence_no=1,
            reason="legacy_archive_only",
        ),
    )
    services = _context_services(session_service, recent_limit=2)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:archive-only",
            agent_id="assistant",
        ),
    )
    tree = services["tree"].list_tree("session:archive-only")
    node_ids = {node.id for node in tree.nodes}
    current_segment = next(node for node in tree.nodes if node.id == "session.segment.active")
    rendered = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:archive-only"),
    )

    assert f"session.segment.compacted.{session.active_session_id}" not in node_ids
    assert current_segment.owner_ref["item_count"] == 0
    assert "legacy archived body" not in rendered.debug_body


def test_session_adapter_renders_folded_history_only_after_range_expand() -> None:
    session_service = _session_service()
    session = session_service.ensure_session(
        EnsureSessionInput(
            key="session:folded-render",
            agent_id="assistant",
        ),
    )
    old_session_id = session.active_session_id
    for index in range(1, 3):
        session_service.append_item_fixture(
            AppendSessionItemFixtureInput(
                session_key="session:folded-render",
                role="user",
                content_payload={
                    "blocks": [{"type": "text", "text": f"folded render {index}"}],
                },
            ),
        )
    _compact_session_segment(
        session_service,
        session_key="session:folded-render",
        session_id=old_session_id,
        summary_text="Compacted folded render history.",
        archived_through_sequence_no=2,
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:folded-render",
            role="user",
            content_payload={
                "blocks": [{"type": "text", "text": "folded render 3"}],
            },
        ),
    )
    services = _context_services(session_service, recent_limit=2)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:folded-render",
            agent_id="assistant",
        ),
    )
    collapsed_render = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:folded-render"),
    )

    assert "folded render 1" not in collapsed_render.debug_body
    assert "folded render 2" not in collapsed_render.debug_body
    assert "Compacted folded render history." in collapsed_render.debug_body
    assert "folded render 3" in collapsed_render.debug_body

    compacted_node_id = f"session.segment.compacted.{old_session_id}"
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:folded-render",
            node_id=compacted_node_id,
            action=ContextAction.EXPAND,
        ),
    )
    range_only_render = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:folded-render"),
    )

    assert "Messages 1-2" in range_only_render.debug_body
    assert "folded render 1" not in range_only_render.debug_body
    assert "folded render 2" not in range_only_render.debug_body

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:folded-render",
            node_id=f"session.segment.items.{old_session_id}.1.2",
            action=ContextAction.EXPAND,
        ),
    )
    expanded_render = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:folded-render"),
    )

    assert "folded render 1" in expanded_render.debug_body
    assert "folded render 2" in expanded_render.debug_body


def test_session_segment_compaction_keeps_tool_history_folded_until_range_expand() -> None:
    session_service = _session_service()
    session = session_service.ensure_session(
        EnsureSessionInput(
            key="session:segment-tool-history",
            agent_id="assistant",
        ),
    )
    old_session_id = session.active_session_id
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:segment-tool-history",
            role="user",
            content_payload={
                "blocks": [{"type": "text", "text": "Check the weather in Kunming."}],
            },
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:segment-tool-history",
            role="assistant",
            content_payload={
                "type": "function_call",
                "call_id": "call-weather-1",
                "name": "fetch_weather",
                "arguments": {"city": "Kunming"},
            },
            metadata={
                "tool_call_id": "call-weather-1",
                "tool_name": "fetch_weather",
            },
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:segment-tool-history",
            role="tool",
            kind=SessionItemFixtureKind.TOOL_RESULT,
            content_payload={
                "tool_name": "fetch_weather",
                "tool_call_id": "call-weather-1",
                "status": "succeeded",
                "content": [{"type": "text", "text": "Kunming is sunny."}],
            },
            metadata={
                "tool_call_id": "call-weather-1",
                "tool_name": "fetch_weather",
            },
        ),
    )
    summary = session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:segment-tool-history",
            role="assistant",
            content_payload={
                "blocks": [
                    {
                        "type": "text",
                        "text": "The old segment checked Kunming weather.",
                    },
                ],
            },
        ),
    )
    compacted = session_service.compact_active_segment(
        CompactSessionSegmentInput(
            session_key="session:segment-tool-history",
            session_id=old_session_id,
            summary_item_id=summary.id,
            summary_text="The old segment checked Kunming weather.",
            compaction_run_id="run-compact-weather",
            archived_through_item_sequence_no=3,
            reason="test_compaction",
        ),
    )
    new_message = session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:segment-tool-history",
            role="user",
            content_payload={
                "blocks": [{"type": "text", "text": "Continue after compaction."}],
            },
        ),
    )
    services = _context_services(session_service, recent_limit=8)

    assert compacted.active_session_id != old_session_id
    assert new_message.session_id == compacted.active_session_id

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:segment-tool-history",
            agent_id="assistant",
        ),
    )
    collapsed_render = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:segment-tool-history"),
    )

    assert "The old segment checked Kunming weather." in collapsed_render.debug_body
    assert "Continue after compaction." in collapsed_render.debug_body
    assert "Kunming is sunny." not in collapsed_render.debug_body
    assert '<tool_interaction tool_name="fetch_weather"' not in (
        collapsed_render.debug_body
    )
    runtime_contract_index = collapsed_render.debug_body.index("runtime.contract")
    current_user_intent_index = collapsed_render.debug_body.index(
        "Continue after compaction.",
    )
    folded_summary_index = collapsed_render.debug_body.index(
        "The old segment checked Kunming weather.",
    )
    assert runtime_contract_index < current_user_intent_index < folded_summary_index

    compacted_node_id = f"session.segment.compacted.{old_session_id}"
    range_node_id = f"session.segment.items.{old_session_id}.1.3"
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:segment-tool-history",
            node_id=compacted_node_id,
            action=ContextAction.EXPAND,
        ),
    )
    range_only_render = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:segment-tool-history"),
    )

    assert "Messages 1-3" in range_only_render.debug_body
    assert "Kunming is sunny." not in range_only_render.debug_body
    assert '<tool_interaction tool_name="fetch_weather"' not in (
        range_only_render.debug_body
    )

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:segment-tool-history",
            node_id=range_node_id,
            action=ContextAction.EXPAND,
        ),
    )
    expanded_render = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:segment-tool-history"),
    )
    snapshot = services["render"].record_snapshot(
        RecordContextSnapshotInput(
            session_key="session:segment-tool-history",
            run_id="run-after-compaction",
            debug_body=expanded_render.debug_body,
            provider_attachments=expanded_render.provider_attachments,
            estimate=expanded_render.estimate,
            included_node_ids=expanded_render.included_node_ids,
            mirrored_node_ids=expanded_render.mirrored_node_ids,
            metadata={"source": "test"},
        ),
    )

    assert '<tool_interaction tool_name="fetch_weather"' in expanded_render.debug_body
    assert 'call_id="call-weather-1"' not in expanded_render.debug_body
    assert "Kunming is sunny." not in expanded_render.debug_body
    assert "Continue after compaction." in expanded_render.debug_body
    assert compacted_node_id in expanded_render.included_node_ids
    assert range_node_id in expanded_render.included_node_ids
    assert snapshot.debug_body == expanded_render.debug_body
    assert snapshot.included_node_ids == expanded_render.included_node_ids

    tool_node = next(
        node
        for node in services["tree"].list_tree("session:segment-tool-history").nodes
        if node.kind == "tool_interaction"
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:segment-tool-history",
            node_id=tool_node.id,
            action=ContextAction.EXPAND,
        ),
    )
    tool_expanded_render = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:segment-tool-history"),
    )

    assert "Kunming is sunny." not in tool_expanded_render.debug_body
    assert "content_omitted" in tool_expanded_render.debug_body

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:segment-tool-history",
            node_id=tool_node.id,
            action=ContextAction.PIN,
        ),
    )
    tool_pinned_render = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:segment-tool-history"),
    )

    assert "Kunming is sunny." in tool_pinned_render.debug_body


def test_session_segment_compaction_slice_uses_summary_not_archived_range() -> None:
    session_service = _session_service()
    session = session_service.ensure_session(
        EnsureSessionInput(
            key="session:segment-llm-slice",
            agent_id="assistant",
        ),
    )
    old_session_id = session.active_session_id
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:segment-llm-slice",
            role="user",
            content_payload={
                "blocks": [{"type": "text", "text": "old private detail"}],
            },
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:segment-llm-slice",
            role="assistant",
            content_payload={
                "type": "function_call",
                "call_id": "call-old-1",
                "name": "fetch_old",
                "arguments": {"query": "old"},
            },
            metadata={
                "tool_call_id": "call-old-1",
                "tool_name": "fetch_old",
            },
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:segment-llm-slice",
            role="tool",
            kind=SessionItemFixtureKind.TOOL_RESULT,
            content_payload={
                "tool_name": "fetch_old",
                "tool_call_id": "call-old-1",
                "status": "succeeded",
                "content": [{"type": "text", "text": "old tool payload"}],
            },
            metadata={
                "tool_call_id": "call-old-1",
                "tool_name": "fetch_old",
            },
        ),
    )
    summary = session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:segment-llm-slice",
            role="assistant",
            content_payload={
                "blocks": [{"type": "text", "text": "Compacted old segment."}],
            },
        ),
    )
    session_service.compact_active_segment(
        CompactSessionSegmentInput(
            session_key="session:segment-llm-slice",
            session_id=old_session_id,
            summary_item_id=summary.id,
            summary_text="Compacted old segment.",
            compaction_run_id="run-compact-slice",
            archived_through_item_sequence_no=3,
            reason="test_compaction",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:segment-llm-slice",
            role="user",
            content_payload={
                "blocks": [{"type": "text", "text": "new active request"}],
            },
        ),
    )
    services = _context_services(session_service, recent_limit=8)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:segment-llm-slice",
            agent_id="assistant",
        ),
    )
    compacted_node_id = f"session.segment.compacted.{old_session_id}"
    range_node_id = f"session.segment.items.{old_session_id}.1.3"
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:segment-llm-slice",
            node_id=compacted_node_id,
            action=ContextAction.EXPAND,
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:segment-llm-slice",
            node_id=range_node_id,
            action=ContextAction.EXPAND,
        ),
    )

    llm_slice = services["slice"].build_slice(
        session_key="session:segment-llm-slice",
        run_id="run-after-compact",
        audience="llm_request",
        provider_profile="codex-http",
    )
    debug_slice = services["slice"].build_slice(
        session_key="session:segment-llm-slice",
        run_id="run-after-compact",
        audience="debug_tree",
        provider_profile="codex-http",
    )

    llm_item_ids = {item.item_id for item in llm_slice.items}
    debug_item_ids = {item.item_id for item in debug_slice.items}
    llm_text = "\n".join(
        f"{item.summary}\n{item.text}" for item in llm_slice.items
    )

    assert compacted_node_id in llm_item_ids
    assert range_node_id not in llm_item_ids
    assert f"session.item.{old_session_id}.1" not in llm_item_ids
    assert "old private detail" not in llm_text
    assert "old tool payload" not in llm_text
    assert "Compacted old segment." in llm_text
    assert "new active request" in llm_text
    assert range_node_id in debug_item_ids
    assert f"session.item.{old_session_id}.1" in debug_item_ids
    assert llm_slice.report.loss["archived_ref_count"] >= 1
    assert any(
        ref.get("session_item_id")
        for ref in llm_slice.report.archived_refs
    )
    expanded_render = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:segment-llm-slice"),
    )
    snapshot = services["render"].record_snapshot(
        RecordContextSnapshotInput(
            session_key="session:segment-llm-slice",
            run_id="run-after-compact",
            debug_body=expanded_render.debug_body,
            provider_attachments=expanded_render.provider_attachments,
            estimate=expanded_render.estimate,
            included_node_ids=expanded_render.included_node_ids,
            mirrored_node_ids=expanded_render.mirrored_node_ids,
            metadata={"source": "test"},
        ),
    )

    assert snapshot.metadata["archived_ref_count"] >= 1
    assert any(
        ref.get("session_item_id")
        for ref in snapshot.metadata["archived_refs"]
        if isinstance(ref, dict)
    )


def test_session_adapter_current_segment_remains_stable_after_tool_messages() -> None:
    session_service = _session_service()
    session_service.ensure_session(
        EnsureSessionInput(
            key="session:stable-current",
            agent_id="assistant",
        ),
    )
    for index in range(1, 6):
        session_service.append_item_fixture(
            AppendSessionItemFixtureInput(
                session_key="session:stable-current",
                role="user",
                content_payload={
                    "blocks": [{"type": "text", "text": f"message {index}"}],
                },
            ),
        )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:stable-current",
            role="user",
            content_payload={
                "blocks": [{"type": "text", "text": "check flights from Kunming"}],
            },
        ),
    )
    services = _context_services(session_service, recent_limit=2)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:stable-current",
            agent_id="assistant",
        ),
    )
    first_render = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:stable-current"),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:stable-current",
            role="assistant",
            content_payload={
                "type": "function_call",
                "call_id": "call-extra",
                "name": "context_tree.list",
                "arguments": {},
            },
            metadata={"tool_call_id": "call-extra", "tool_name": "context_tree.list"},
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:stable-current",
            role="tool",
            kind=SessionItemFixtureKind.TOOL_RESULT,
            content_payload={
                "tool_name": "context_tree.list",
                "tool_call_id": "call-extra",
                "status": "succeeded",
                "content": [{"type": "text", "text": "listed"}],
            },
            metadata={"tool_call_id": "call-extra", "tool_name": "context_tree.list"},
        ),
    )
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:stable-current",
            agent_id="assistant",
        ),
    )
    second_render = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:stable-current"),
    )
    tree = services["tree"].list_tree("session:stable-current")
    node_ids = {node.id for node in tree.nodes}

    assert "message 1" in first_render.debug_body
    assert "message 1" in second_render.debug_body
    assert "message 5" in second_render.debug_body
    assert "check flights from Kunming" in second_render.debug_body
    assert "older messages are available before" not in second_render.debug_body
    assert all(
        node.parent_id is None or node.parent_id in node_ids
        for node in tree.nodes
    )


def test_session_adapter_warns_browser_investigation_no_gain_loop() -> None:
    session_service = _session_service()
    session_service.ensure_session(
        EnsureSessionInput(
            key="session:browser-no-gain",
            agent_id="assistant",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:browser-no-gain",
            role="user",
            content_payload={"blocks": [{"type": "text", "text": "inspect browser"}]},
            source_kind="orchestration_run",
            source_id="run-browser-no-gain",
        ),
    )
    _append_tool_pair(
        session_service,
        session_key="session:browser-no-gain",
        call_id="call-extract",
        tool_name="browser.script.extract_request",
        arguments={"script_id": "5", "start_column": 28431},
        result_text=(
            "Browser script request extract:\n"
            "- Endpoint candidates: 5\n"
            "- /self-service/before/flight-search"
        ),
    )
    _append_tool_pair(
        session_service,
        session_key="session:browser-no-gain",
        call_id="call-capture",
        tool_name="browser.network.start_capture",
        arguments={"capture_id": "cap-flight"},
        result_text="Network capture started:\n- Capture: cap-flight",
    )
    _append_tool_pair(
        session_service,
        session_key="session:browser-no-gain",
        call_id="call-probe-1",
        tool_name="browser.evaluate",
        arguments={"fn": "() => window.location.href", "target_id": "tab-1"},
        result_text="Evaluate result: https://example.com",
    )
    _append_tool_pair(
        session_service,
        session_key="session:browser-no-gain",
        call_id="call-list",
        tool_name="browser.network.list_requests",
        arguments={"capture_id": "cap-flight"},
        result_text="Network requests: 0 shown of 0\n- No matching requests.",
    )
    _append_tool_pair(
        session_service,
        session_key="session:browser-no-gain",
        call_id="call-probe-2",
        tool_name="browser.evaluate",
        arguments={"fn": "() => window.location.href", "target_id": "tab-1"},
        result_text="Evaluate result: https://example.com",
    )
    services = _context_services(session_service)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:browser-no-gain",
            agent_id="assistant",
            metadata={"last_run_id": "run-browser-no-gain"},
        ),
    )
    tree = services["tree"].list_tree("session:browser-no-gain")
    warnings = [node for node in tree.nodes if node.kind == "investigation_warning"]
    rendered = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:browser-no-gain"),
    )

    assert warnings == []
    assert "browser.network_capture_no_requests" not in rendered.debug_body
    assert "browser.endpoint_candidate_not_escalated" not in rendered.debug_body
    assert "browser.same_probe_repeated" not in rendered.debug_body
    assert "concrete action may be needed" not in rendered.debug_body
    assert "possible_next_step" not in rendered.debug_body


def test_session_adapter_exposes_folded_history_as_exact_archived_ranges() -> None:
    session_service = _session_service()
    session = session_service.ensure_session(
        EnsureSessionInput(
            key="session:folded",
            agent_id="assistant",
        ),
    )
    old_session_id = session.active_session_id
    for index in range(1, 6):
        session_service.append_item_fixture(
            AppendSessionItemFixtureInput(
                session_key="session:folded",
                role="user",
                content_payload={
                    "blocks": [{"type": "text", "text": f"archived message {index}"}],
                },
            ),
        )
    _compact_session_segment(
        session_service,
        session_key="session:folded",
        session_id=old_session_id,
        summary_text="Compacted archived message history.",
        archived_through_sequence_no=5,
    )
    services = _context_services(session_service, recent_limit=2)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:folded",
            agent_id="assistant",
        ),
    )
    tree = services["tree"].list_tree("session:folded")
    folded_node = next(
        node
        for node in tree.nodes
        if node.id == f"session.segment.compacted.{old_session_id}"
    )
    assert folded_node.state.collapsed is True
    assert folded_node.owner_ref["message_scope"] == "archived"

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:folded",
            node_id=folded_node.id,
            action=ContextAction.EXPAND,
        ),
    )
    expanded_tree = services["tree"].list_tree("session:folded")
    range_nodes = [
        node for node in expanded_tree.nodes if node.parent_id == folded_node.id
    ]

    assert all(node.id.startswith("session.segment.items.") for node in range_nodes)
    assert [node.owner_ref["from_sequence_no"] for node in range_nodes] == [1, 3, 5]
    assert [node.owner_ref["to_sequence_no"] for node in range_nodes] == [2, 4, 5]

    first_range = range_nodes[0]
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:folded",
            node_id=first_range.id,
            action=ContextAction.EXPAND,
        ),
    )
    message_tree = services["tree"].list_tree("session:folded")
    archived_message_nodes = [
        node for node in message_tree.nodes if node.parent_id == first_range.id
    ]

    assert [node.owner_ref["sequence_no"] for node in archived_message_nodes] == [1, 2]
    assert {
        node.owner_ref["visibility"] for node in archived_message_nodes
    } == {"archived"}


def test_session_adapter_caps_folded_history_range_pages() -> None:
    session_service = _session_service()
    session = session_service.ensure_session(
        EnsureSessionInput(
            key="session:folded-range-cap",
            agent_id="assistant",
        ),
    )
    old_session_id = session.active_session_id
    for index in range(1, 8):
        session_service.append_item_fixture(
            AppendSessionItemFixtureInput(
                session_key="session:folded-range-cap",
                role="user",
                content_payload={
                    "blocks": [{"type": "text", "text": f"archived cap {index}"}],
                },
            ),
        )
    _compact_session_segment(
        session_service,
        session_key="session:folded-range-cap",
        session_id=old_session_id,
        summary_text="Compacted capped range history.",
        archived_through_sequence_no=7,
    )
    services = _context_services(
        session_service,
        recent_limit=1,
        historical_range_limit=3,
    )

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:folded-range-cap",
            agent_id="assistant",
        ),
    )
    compacted_node_id = f"session.segment.compacted.{old_session_id}"
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:folded-range-cap",
            node_id=compacted_node_id,
            action=ContextAction.EXPAND,
        ),
    )
    expanded_tree = services["tree"].list_tree("session:folded-range-cap")
    children = [node for node in expanded_tree.nodes if node.parent_id == compacted_node_id]
    range_nodes = [node for node in children if node.kind == "session_item_range"]
    notice = next(node for node in children if node.kind == "session_range_notice")

    assert [node.owner_ref["from_sequence_no"] for node in range_nodes] == [1, 2, 3]
    assert notice.metadata["notice_kind"] == "range_limit"
    assert notice.metadata["range_reason_code"] == "range_page_limit"
    assert notice.metadata["omitted_range_count"] == 4
    assert notice.metadata["omitted_item_count"] == 4


def test_session_adapter_splits_over_budget_folded_range_before_messages() -> None:
    session_service = _session_service()
    session = session_service.ensure_session(
        EnsureSessionInput(
            key="session:folded-budget",
            agent_id="assistant",
        ),
    )
    old_session_id = session.active_session_id
    for index in range(1, 5):
        session_service.append_item_fixture(
            AppendSessionItemFixtureInput(
                session_key="session:folded-budget",
                role="user",
                content_payload={
                    "blocks": [
                        {
                            "type": "text",
                            "text": f"budget body {index} " + ("x" * 160),
                        },
                    ],
                },
            ),
        )
    _compact_session_segment(
        session_service,
        session_key="session:folded-budget",
        session_id=old_session_id,
        summary_text="Compacted over-budget history.",
        archived_through_sequence_no=4,
    )
    services = _context_services(
        session_service,
        recent_limit=4,
        range_token_soft_limit=100,
    )

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:folded-budget",
            agent_id="assistant",
        ),
    )
    compacted_node_id = f"session.segment.compacted.{old_session_id}"
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:folded-budget",
            node_id=compacted_node_id,
            action=ContextAction.EXPAND,
        ),
    )
    range_tree = services["tree"].list_tree("session:folded-budget")
    range_node = next(
        node
        for node in range_tree.nodes
        if node.parent_id == compacted_node_id
        and node.kind == "session_item_range"
    )

    assert range_node.metadata["range_budget_status"] == "split_required"
    assert range_node.metadata["range_reason_code"] == "split_required"

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:folded-budget",
            node_id=range_node.id,
            action=ContextAction.EXPAND,
        ),
    )
    split_tree = services["tree"].list_tree("session:folded-budget")
    split_ranges = [node for node in split_tree.nodes if node.parent_id == range_node.id]

    assert [node.kind for node in split_ranges] == [
        "session_item_range",
        "session_item_range",
    ]
    assert [node.owner_ref["from_sequence_no"] for node in split_ranges] == [1, 3]
    assert [node.owner_ref["to_sequence_no"] for node in split_ranges] == [2, 4]
    assert all(node.metadata["range_budget_status"] == "ok" for node in split_ranges)
    assert all(node.metadata["range_reason_code"] == "within_budget" for node in split_ranges)


def test_session_adapter_marks_single_message_over_budget_reason_code() -> None:
    session_service = _session_service()
    session = session_service.ensure_session(
        EnsureSessionInput(
            key="session:folded-budget-blocked",
            agent_id="assistant",
        ),
    )
    old_session_id = session.active_session_id
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:folded-budget-blocked",
            role="user",
            content_payload={
                "blocks": [
                    {
                        "type": "text",
                        "text": "single over budget " + ("x" * 520),
                    },
                ],
            },
        ),
    )
    _compact_session_segment(
        session_service,
        session_key="session:folded-budget-blocked",
        session_id=old_session_id,
        summary_text="Compacted blocked range history.",
        archived_through_sequence_no=1,
    )
    services = _context_services(
        session_service,
        recent_limit=1,
        range_token_soft_limit=60,
    )

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:folded-budget-blocked",
            agent_id="assistant",
        ),
    )
    compacted_node_id = f"session.segment.compacted.{old_session_id}"
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:folded-budget-blocked",
            node_id=compacted_node_id,
            action=ContextAction.EXPAND,
        ),
    )
    range_tree = services["tree"].list_tree("session:folded-budget-blocked")
    range_node = next(
        node
        for node in range_tree.nodes
        if node.parent_id == compacted_node_id
        and node.kind == "session_item_range"
    )

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:folded-budget-blocked",
            node_id=range_node.id,
            action=ContextAction.EXPAND,
        ),
    )
    blocked_tree = services["tree"].list_tree("session:folded-budget-blocked")
    notice = next(
        node
        for node in blocked_tree.nodes
        if node.parent_id == range_node.id
        and node.kind == "session_range_notice"
    )

    assert notice.metadata["notice_kind"] == "range_budget"
    assert notice.metadata["range_budget_status"] == "blocked"
    assert notice.metadata["range_reason_code"] == "over_budget"


def test_session_adapter_keeps_reset_history_as_folded_ranges() -> None:
    session_service = _session_service()
    session = session_service.ensure_session(
        EnsureSessionInput(
            key="session:reset",
            agent_id="assistant",
        ),
    )
    old_session_id = session.active_session_id
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:reset",
            role="user",
            content_payload={"blocks": [{"type": "text", "text": "before reset"}]},
        ),
    )
    session_service.reset_session(
        ResetSessionInput(
            session_key="session:reset",
            reason="manual",
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:reset",
            role="user",
            content_payload={"blocks": [{"type": "text", "text": "after reset"}]},
        ),
    )
    services = _context_services(session_service, recent_limit=2)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:reset",
            agent_id="assistant",
        ),
    )
    tree = services["tree"].list_tree("session:reset")
    folded_node = next(
        node
        for node in tree.nodes
        if node.id == f"session.segment.closed.{old_session_id}"
    )

    assert folded_node.state.collapsed is True
    assert folded_node.owner_ref["segment_kind"] == "closed"
    assert folded_node.summary == "Closed segment #1 is available."

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:reset",
            node_id=folded_node.id,
            action=ContextAction.EXPAND,
        ),
    )
    range_tree = services["tree"].list_tree("session:reset")
    range_node = next(node for node in range_tree.nodes if node.parent_id == folded_node.id)

    assert range_node.id.startswith("session.segment.items.")
    assert range_node.owner_ref["session_id"] == old_session_id
    assert range_node.owner_ref["segment_kind"] == "closed"

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:reset",
            node_id=range_node.id,
            action=ContextAction.EXPAND,
        ),
    )
    message_tree = services["tree"].list_tree("session:reset")
    reset_history = [
        node for node in message_tree.nodes if node.parent_id == range_node.id
    ]

    assert [node.owner_ref["session_id"] for node in reset_history] == [old_session_id]
    assert reset_history[0].owner_ref["visibility"] == "default"
    assert "before reset" in reset_history[0].summary


def test_session_adapter_uses_segment_summary_before_loading_compacted_messages() -> None:
    session_service = _session_service()
    session = session_service.ensure_session(
        EnsureSessionInput(
            key="session:segment-summary",
            agent_id="assistant",
        ),
    )
    old_session_id = session.active_session_id
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key="session:segment-summary",
            role="user",
            content_payload={
                "blocks": [{"type": "text", "text": "secret old body"}],
            },
        ),
    )
    _compact_session_segment(
        session_service,
        session_key="session:segment-summary",
        session_id=old_session_id,
        summary_text="Condensed old segment summary.",
        archived_through_sequence_no=1,
    )
    services = _context_services(session_service, recent_limit=2)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:segment-summary",
            agent_id="assistant",
        ),
    )
    collapsed_render = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:segment-summary"),
    )

    compacted_node_id = f"session.segment.compacted.{old_session_id}"
    assert "Condensed old segment summary." in collapsed_render.debug_body
    assert "secret old body" not in collapsed_render.debug_body

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:segment-summary",
            node_id=compacted_node_id,
            action=ContextAction.EXPAND,
        ),
    )
    range_only_render = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:segment-summary"),
    )

    assert "Messages 1-1" in range_only_render.debug_body
    assert "secret old body" not in range_only_render.debug_body

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:segment-summary",
            node_id=f"session.segment.items.{old_session_id}.1.1",
            action=ContextAction.EXPAND,
        ),
    )
    expanded_render = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:segment-summary"),
    )

    assert "secret old body" in expanded_render.debug_body


def _context_services(
    session_service: SessionApplicationService,
    *,
    execution_query=None,  # noqa: ANN001
    recent_limit: int = 8,
    historical_range_limit: int = 24,
    range_token_soft_limit: int = 1200,
):
    registry = ContextOwnerRegistry()
    registry.register(
        SessionContextNodeProvider(
            session_service,
            execution_query=execution_query,
            recent_limit=recent_limit,
            historical_range_limit=historical_range_limit,
            range_token_soft_limit=range_token_soft_limit,
        ),
    )
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    operations = InMemoryContextOperationRepository()
    snapshots = InMemoryContextSnapshotRepository()
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
        "render": ContextObservationSnapshotService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
        "slice": ContextSliceBuilderService(
            workspace_repository=workspaces,
            node_repository=nodes,
            owner_registry=registry,
            session_item_resolver=session_service,
        ),
    }


class _TestSessionService:
    def __init__(self, inner: SessionApplicationService) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def append_item_fixture(self, data: AppendSessionItemFixtureInput) -> SessionItem:
        item = self._inner.append_item(
            AppendSessionItemInput(
                session_key=data.session_key,
                role=data.role,
                kind=_session_item_kind_from_message_input(data),
                content_payload=dict(data.content_payload),
                source_module="session",
                source_kind=data.source_kind,
                source_id=data.source_id,
                call_id=_message_input_tool_call_id(data),
                tool_name=_message_input_tool_name(data),
                metadata=dict(data.metadata),
            ),
        )
        return item

    def archive_item_fixtures(self, data: ArchiveSessionItemsFixtureInput) -> None:
        archived_through_sequence_no = (
            data.archived_through_sequence_no
            if data.archived_through_sequence_no is not None
            else data.max_sequence_no
        )
        if archived_through_sequence_no is None:
            return
        items = self._inner.list_items(
            ListSessionItemsInput(
                session_key=data.session_key,
                active_session_only=True,
            ),
        )
        for item in items:
            if item.sequence_no <= archived_through_sequence_no:
                self._inner.merge_item_metadata(
                    MergeSessionItemMetadataInput(
                        item_id=item.id,
                        metadata={
                            "visibility_state": "archived",
                            "archived_reason": data.reason,
                        },
                    ),
                )


def _session_service() -> _TestSessionService:
    uow = _FakeSessionUnitOfWork()
    return _TestSessionService(SessionApplicationService(lambda: uow))


def _append_tool_pair(
    session_service: SessionApplicationService,
    *,
    session_key: str,
    call_id: str,
    tool_name: str,
    arguments: dict[str, object],
    result_text: str,
    status: str = "succeeded",
) -> None:
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key=session_key,
            role="assistant",
            content_payload={
                "type": "function_call",
                "call_id": call_id,
                "name": tool_name,
                "arguments": arguments,
            },
            metadata={"tool_call_id": call_id, "tool_name": tool_name},
        ),
    )
    session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key=session_key,
            role="tool",
            kind=SessionItemFixtureKind.TOOL_RESULT,
            content_payload={
                "tool_name": tool_name,
                "tool_call_id": call_id,
                "status": status,
                "content": [{"type": "text", "text": result_text}],
            },
            metadata={"tool_call_id": call_id, "tool_name": tool_name},
        ),
    )


def _session_item_kind_from_message_input(
    data: AppendSessionItemFixtureInput,
) -> SessionItemKind:
    if data.kind is SessionItemFixtureKind.TOOL_RESULT or data.role == "tool":
        return SessionItemKind.TOOL_RESULT
    if data.role == "assistant" and data.content_payload.get("type") == "function_call":
        return SessionItemKind.TOOL_CALL
    if data.role == "user":
        return SessionItemKind.USER_MESSAGE
    if data.role == "assistant":
        return SessionItemKind.ASSISTANT_MESSAGE
    return SessionItemKind.UNKNOWN


def _message_input_tool_call_id(data: AppendSessionItemFixtureInput) -> str | None:
    return (
        _optional_text_for_test(data.metadata.get("tool_call_id"))
        or _optional_text_for_test(data.content_payload.get("call_id"))
        or _optional_text_for_test(data.content_payload.get("tool_call_id"))
    )


def _message_input_tool_name(data: AppendSessionItemFixtureInput) -> str | None:
    return (
        _optional_text_for_test(data.metadata.get("tool_name"))
        or _optional_text_for_test(data.content_payload.get("name"))
        or _optional_text_for_test(data.content_payload.get("tool_name"))
    )


def _compact_session_segment(
    session_service: SessionApplicationService,
    *,
    session_key: str,
    session_id: str,
    summary_text: str = "Compacted session summary.",
    archived_through_sequence_no: int | None = None,
) -> None:
    summary = session_service.append_item_fixture(
        AppendSessionItemFixtureInput(
            session_key=session_key,
            role="assistant",
            content_payload={"blocks": [{"type": "text", "text": summary_text}]},
        ),
    )
    summary_item = next(
        item
        for item in session_service.list_items(
            ListSessionItemsInput(
                session_key=session_key,
                active_session_only=True,
            ),
        )
        if item.sequence_no == summary.sequence_no
    )
    session_service.compact_active_segment(
        CompactSessionSegmentInput(
            session_key=session_key,
            session_id=session_id,
            summary_item_id=summary_item.id,
            summary_text=summary_text,
            compaction_run_id=f"run-compact-{session_key}",
            archived_through_item_sequence_no=archived_through_sequence_no,
            reason="test_compaction",
        ),
    )


class _FakeSessionUnitOfWork:
    def __init__(self) -> None:
        self.sessions = InMemorySessionRepository()
        self.session_items = InMemorySessionItemRepository()
        self.session_instances = InMemorySessionInstanceRepository()

    def __enter__(self) -> "_FakeSessionUnitOfWork":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        del exc_type, exc, tb

    def collect(self, aggregate) -> None:  # noqa: ANN001
        del aggregate

    def commit(self) -> None:
        return None

    def flush(self) -> None:
        return None

    def rollback(self) -> None:
        return None


def _optional_text_for_test(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


class _FakeExecutionQuery:
    def __init__(self, *, turn_id: str, summary_payload: dict[str, object]) -> None:
        self._turn_id = turn_id
        self._summary_payload = summary_payload

    def list_execution_chains(self, turn_id: str):  # noqa: ANN201
        if turn_id != self._turn_id:
            return []
        return [_FakeExecutionEntity(id="chain-1")]

    def list_execution_steps(self, chain_id: str):  # noqa: ANN201
        if chain_id != "chain-1":
            return []
        return [
            _FakeExecutionEntity(
                id="step-1",
                kind="llm",
                status="completed",
                step_index=1,
            ),
        ]

    def list_execution_step_items(self, step_id: str):  # noqa: ANN201
        if step_id != "step-1":
            return []
        return [
            _FakeExecutionEntity(
                id="item-1",
                kind="llm_invocation",
                status="completed",
                summary_payload=self._summary_payload,
            ),
        ]


class _FakeExecutionQueryWithSteps:
    def __init__(
        self,
        *,
        turn_id: str,
        steps: list[_FakeExecutionEntity],
        items_by_step_id: dict[str, list[_FakeExecutionEntity]],
    ) -> None:
        self._turn_id = turn_id
        self._steps = steps
        self._items_by_step_id = items_by_step_id

    def list_execution_chains(self, turn_id: str):  # noqa: ANN201
        if turn_id != self._turn_id:
            return []
        return [_FakeExecutionEntity(id="chain-1", status="completed")]

    def list_execution_steps(self, chain_id: str):  # noqa: ANN201
        if chain_id != "chain-1":
            return []
        return list(self._steps)

    def list_execution_step_items(self, step_id: str):  # noqa: ANN201
        return list(self._items_by_step_id.get(step_id, ()))


class _FakeExecutionEntity:
    def __init__(self, **kwargs: object) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)
