from __future__ import annotations

from dataclasses import dataclass

import pytest

from crxzipple.modules.agent.domain import AgentProfile
from crxzipple.modules.agent.domain.value_objects import (
    AgentInstructionPolicy,
    AgentLlmRoutingPolicy,
    AgentRuntimePreferences,
)
from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmCapability,
    LlmMessageRole,
    LlmProfile,
    LlmProviderKind,
    ToolSchema,
)
from crxzipple.modules.orchestration.application.llm_resolver import (
    ResolvedLlmSelection,
)
from crxzipple.modules.orchestration.application.runtime_llm_request_draft import (
    RuntimeLlmRequestDraftCollector,
)
from crxzipple.modules.orchestration.application.runtime_request_mode import RuntimeRequestMode
from crxzipple.modules.orchestration.application.tool_resolver import (
    ResolvedTool,
    ResolvedToolSet,
)
from crxzipple.modules.orchestration.domain import (
    ExecutionOwnerReference,
    ExecutionStepItem,
    ExecutionStepItemKind,
    ExecutionStepItemStatus,
    InboundInstruction,
    OrchestrationRun,
    OrchestrationValidationError,
)
from crxzipple.modules.session.application import (
    ListSessionItemsInput,
    SessionItemsBundle,
)
from crxzipple.modules.session.domain import (
    Session,
    SessionItem,
    SessionItemKind,
    SessionItemPhase,
)
from crxzipple.modules.tool.domain import Tool, ToolExecutionTarget


def test_build_collects_normal_turn_inputs_for_context_workspace() -> None:
    collector = _collector()
    run = _run()
    resolved_tools = _resolved_tools()

    result = collector.build(run, resolved_tools=resolved_tools)

    assert result.llm_id == "llm.default"
    assert result.session_key == "session:assistant"
    assert result.active_session_id == "active-session"
    assert result.mode is RuntimeRequestMode.NORMAL_TURN
    assert result.surface_policy.surface == "interactive"
    assert result.workspace_dir == "/workspace/session"
    assert len(result.messages) == 1
    assert result.messages[0].role is LlmMessageRole.USER
    assert result.messages[0].metadata == {
        "runtime_request_block_kind": "current_inbound",
        "source": "web",
        "source_kind": "orchestration_run",
        "source_id": "run-1",
    }
    assert tuple(schema.name for schema in result.tool_schemas) == ("weather.lookup",)
    assert result.report is not None
    assert result.report.transcript_message_count == 1
    assert result.report.context_budget_source == "context_window_scaled"
    assert result.report.context_budget_estimated_tokens == 300
    assert collector.session_service.replay_inputs == []
    assert len(collector.session_service.item_inputs) == 1
    assert collector.session_service.item_inputs[0].limit == 1


def test_build_normal_turn_uses_current_inbound_not_session_replay_as_draft_input() -> None:
    session_service = _FakeSessionService()
    session_service.items = (
        _session_item(
            id="item-first-user",
            sequence_no=1,
            text="去东航官网给我查昆明到上海周日的票",
            role="user",
        ),
        _session_item(
            id="item-first-assistant",
            sequence_no=2,
            text="请确认周日日期和上海到达机场。",
            role="assistant",
            phase=SessionItemPhase.FINAL_ANSWER,
        ),
        _session_item(
            id="item-second-user",
            sequence_no=3,
            text="6月21日 虹桥",
            role="user",
        ),
    )
    collector = _collector(session_service=session_service)

    result = collector.build(_run(), resolved_tools=_resolved_tools())

    assert [message.metadata.get("runtime_request_block_kind") for message in result.messages] == [
        "current_inbound",
    ]
    assert [item.source for item in result.input_items] == ["current_inbound"]
    assert result.report is not None
    budget = result.report.to_payload()["transcript"]["budget"]
    assert budget == {}


def test_build_auto_llm_routing_uses_current_inbound_not_session_replay_window() -> None:
    session_service = _FakeSessionService()
    session_service.items = (
        _session_item(
            id="item-current",
            sequence_no=1,
            text="查昆明到上海周日的票",
            role="user",
        ),
        _session_item(
            id="item-progress",
            sequence_no=2,
            text="我已经定位到移动站接口，下一步验证请求参数。",
            role="assistant",
        ),
    )
    resolver = _FakeLlmResolver(expected_requested_llm_id="auto")
    events_service = _FakeEventService()
    collector = _collector(
        session_service=session_service,
        llm_resolver=resolver,
        events_service=events_service,
    )

    result = collector.build(
        _run(metadata={"session_key": "session:assistant", "requested_llm_id": "auto"}),
        resolved_tools=_resolved_tools(),
    )

    assert result.llm_id == "llm.default"
    assert len(resolver.calls) == 1
    input_content = resolver.calls[0]["input_content"]
    assert isinstance(input_content, dict)
    assert "blocks" in input_content
    assert "current request" in str(input_content["blocks"])
    assert "移动站接口" not in str(input_content["blocks"])
    assert len(input_content["blocks"]) == 1
    llm_events = [
        event for event in events_service.events if event.name == "orchestration.llm_resolved"
    ]
    assert len(llm_events) == 1
    event_payload = llm_events[0].payload
    assert event_payload["routing_input_block_count"] == 1
    assert "session_replay_window" not in event_payload
    assert resolver.calls[0]["validate_access"] is True
    assert session_service.replay_inputs == []
    assert len(session_service.item_inputs) == 1
    assert session_service.item_inputs[0].limit == 1


def test_build_can_skip_llm_access_validation_for_request_preview() -> None:
    resolver = _FakeLlmResolver()
    collector = _collector(llm_resolver=resolver)

    collector.build(
        _run(),
        resolved_tools=_resolved_tools(),
        validate_llm_access=False,
    )

    assert resolver.calls[0]["validate_access"] is False


def test_build_normal_turn_does_not_use_session_fact_items_for_provider_replay() -> None:
    session_service = _FakeSessionService()
    session_service.items = (
        SessionItem(
            id="item-call-1",
            session_key="session:assistant",
            session_id="active-session",
            sequence_no=1,
            role="assistant",
            kind=SessionItemKind.TOOL_CALL,
            content_payload={"arguments": {"city": "Kunming"}},
            source_module="llm",
            source_kind="llm_response_item",
            source_id="llm-item-1",
            provider_item_id="provider-call-1",
            call_id="call-weather-1",
            tool_name="weather.lookup",
        ),
        SessionItem(
            id="item-result-1",
            session_key="session:assistant",
            session_id="active-session",
            sequence_no=2,
            role="tool",
            kind=SessionItemKind.TOOL_RESULT,
            content_payload={
                "tool_call_id": "call-weather-1",
                "tool_name": "weather.lookup",
                "status": "succeeded",
                "content": [{"type": "text", "text": "sunny"}],
            },
            source_module="tool",
            source_kind="tool_run",
            source_id="tool-run-1",
            call_id="call-weather-1",
            tool_name="weather.lookup",
            metadata={"tool_status": "succeeded"},
        ),
    )
    collector = _collector(session_service=session_service)

    result = collector.build(_run(), resolved_tools=_resolved_tools())

    assert session_service.replay_inputs == []
    assert len(session_service.item_inputs) == 1
    assert session_service.item_inputs[0].limit == 1
    assert [message.metadata.get("runtime_request_block_kind") for message in result.messages] == [
        "current_inbound",
    ]
    assert result.report is not None
    assert result.report.transcript_tool_result_stats == {}
    report_payload = result.report.to_payload()
    transcript_budget = report_payload["transcript"]["budget"]
    assert transcript_budget == {}


def test_build_merges_execution_chain_protocol_refs_into_transcript_budget() -> None:
    execution_query = _FakeExecutionQuery(
        items=(
            ExecutionStepItem(
                id="item-exec-call-1",
                step_id="step-tools",
                chain_id="chain-run-1",
                turn_id="run-1",
                item_index=0,
                kind=ExecutionStepItemKind.TOOL_CALL,
                status=ExecutionStepItemStatus.COMPLETED,
                owner=ExecutionOwnerReference(
                    owner_kind="tool_call",
                    owner_id="call-weather-1",
                ),
                summary_payload={
                    "tool_call_id": "call-weather-1",
                    "tool_name": "weather.lookup",
                    "tool_id": "tool.weather",
                    "call_session_item_id": "item-call-1",
                    "mode": "inline",
                },
            ),
            ExecutionStepItem(
                id="item-exec-result-1",
                step_id="step-tools",
                chain_id="chain-run-1",
                turn_id="run-1",
                item_index=1,
                kind=ExecutionStepItemKind.TOOL_RESULT,
                status=ExecutionStepItemStatus.COMPLETED,
                owner=ExecutionOwnerReference(
                    owner_kind="session_item",
                    owner_id="item-result-1",
                ),
                summary_payload={
                    "tool_call_id": "call-weather-1",
                    "tool_name": "weather.lookup",
                    "tool_id": "tool.weather",
                    "tool_run_id": "tool-run-1",
                    "result_session_item_id": "item-result-1",
                    "tool_execution_plan": {
                        "tool_call_id": "call-weather-1",
                        "tool_name": "weather.lookup",
                    },
                },
            ),
        ),
    )
    collector = _collector(execution_query=execution_query)

    result = collector.build(_run(), resolved_tools=_resolved_tools())

    assert result.report is not None
    transcript_budget = result.report.to_payload()["transcript"]["budget"]
    assert transcript_budget["execution_chain_protocol_required_ref_count"] == 2
    assert [
        ref["execution_step_item_id"]
        for ref in transcript_budget["execution_chain_protocol_required_refs"]
    ] == ["item-exec-call-1", "item-exec-result-1"]
    assert {
        ref["owner_module"]
        for ref in transcript_budget["execution_chain_protocol_required_refs"]
    } == {"orchestration"}
    protocol_ref_ids = {
        ref.get("execution_step_item_id")
        for ref in transcript_budget["protocol_required_refs"]
    }
    assert {"item-exec-call-1", "item-exec-result-1"} <= protocol_ref_ids
    result_ref = transcript_budget["execution_chain_protocol_required_refs"][1]
    assert result_ref["tool_run_id"] == "tool-run-1"
    assert result_ref["result_session_item_id"] == "item-result-1"
    assert result_ref["tool_execution_plan"]["tool_name"] == "weather.lookup"
    call_ref = transcript_budget["execution_chain_protocol_required_refs"][0]
    assert call_ref["call_session_item_id"] == "item-call-1"


def test_build_memory_flush_uses_maintenance_surface() -> None:
    collector = _collector()

    result = collector.build(
        _run(),
        resolved_tools=_resolved_tools(),
        mode=RuntimeRequestMode.MEMORY_FLUSH,
    )

    assert result.mode is RuntimeRequestMode.MEMORY_FLUSH
    assert result.surface_policy.surface == "maintenance_write"
    assert result.surface_policy.require_tool_call is False
    assert result.surface_policy.record_assistant_messages is False
    assert tuple(schema.name for schema in result.tool_schemas) == ("weather.lookup",)


def test_build_memory_flush_prefers_session_fact_items_without_message_read() -> None:
    session_service = _FakeSessionService()
    session_service.items = (
        SessionItem(
            id="item-memory-call",
            session_key="session:assistant",
            session_id="active-session",
            sequence_no=1,
            role="assistant",
            kind=SessionItemKind.TOOL_CALL,
            content_payload={"arguments": {"note": "durable preference"}},
            source_module="llm",
            source_kind="llm_response_item",
            source_id="llm-item-memory-call",
            call_id="call-memory-write",
            tool_name="memory_write_daily",
        ),
        SessionItem(
            id="item-memory-result",
            session_key="session:assistant",
            session_id="active-session",
            sequence_no=2,
            role="tool",
            kind=SessionItemKind.TOOL_RESULT,
            content_payload={
                "tool_call_id": "call-memory-write",
                "tool_name": "memory_write_daily",
                "status": "succeeded",
                "content": [{"type": "text", "text": "stored"}],
            },
            source_module="tool",
            source_kind="tool_run",
            source_id="tool-run-memory-write",
            call_id="call-memory-write",
            tool_name="memory_write_daily",
            metadata={"tool_status": "succeeded"},
        ),
    )
    collector = _collector(session_service=session_service)

    result = collector.build(
        _run(),
        resolved_tools=_resolved_tools(),
        mode=RuntimeRequestMode.MEMORY_FLUSH,
    )

    assert result.mode is RuntimeRequestMode.MEMORY_FLUSH
    assert session_service.replay_inputs == []
    assert len(session_service.item_inputs) == 1
    assert session_service.item_inputs[0].active_session_only is True
    assert session_service.item_inputs[0].limit is None
    assert [message.metadata.get("session_item_id") for message in result.messages] == [
        "item-memory-call",
        "item-memory-result",
    ]
    assert result.report is not None
    budget = result.report.to_payload()["transcript"]["budget"]
    assert budget["source"] == "session_items"
    assert "session_replay_window" not in budget
    assert result.transcript_policy["session_replay_window"] == {
        "session_key": "session:assistant",
        "active_session_only": True,
        "from_sequence_no": 1,
        "to_sequence_no": 2,
        "item_count": 2,
        "protocol_call_ids": ["call-memory-write"],
    }
    assert budget["frontier"] == {
        "from_sequence_no": 1,
        "to_sequence_no": 2,
        "from_item_id": "item-memory-call",
        "to_item_id": "item-memory-result",
        "item_count": 2,
    }


@pytest.mark.parametrize(
    ("agent_id", "active_session_id", "metadata", "expected"),
    [
        (
            None,
            "active-session",
            {"session_key": "session:assistant"},
            "agent_id is required",
        ),
        (
            "assistant",
            None,
            {"session_key": "session:assistant"},
            "active_session_id is required",
        ),
        ("assistant", "active-session", {}, "metadata.session_key is required"),
    ],
)
def test_build_requires_runtime_binding_fields(
    agent_id: str | None,
    active_session_id: str | None,
    metadata: dict[str, object],
    expected: str,
) -> None:
    collector = _collector()

    with pytest.raises(OrchestrationValidationError, match=expected):
        collector.build(
            _run(
                agent_id=agent_id,
                active_session_id=active_session_id,
                metadata=metadata,
            )
        )


def _collector(
    *,
    session_service: "_FakeSessionService | None" = None,
    execution_query: "_FakeExecutionQuery | None" = None,
    llm_resolver: "_FakeLlmResolver | None" = None,
    events_service: "_FakeEventService | None" = None,
) -> RuntimeLlmRequestDraftCollector:
    return RuntimeLlmRequestDraftCollector(
        agent_service=_FakeAgentService(),
        llm_port=_FakeLlmPort(),
        session_service=session_service or _FakeSessionService(),
        llm_resolver=llm_resolver or _FakeLlmResolver(),
        execution_query=execution_query,
        events_service=events_service,
    )


def _run(
    *,
    agent_id: str | None = "assistant",
    active_session_id: str | None = "active-session",
    metadata: dict[str, object] | None = None,
) -> OrchestrationRun:
    return OrchestrationRun(
        id="run-1",
        inbound_instruction=InboundInstruction(
            source="web",
            content={"blocks": [{"type": "text", "text": "current request"}]},
        ),
        active_session_id=active_session_id,
        agent_id=agent_id,
        metadata=(
            {"session_key": "session:assistant"}
            if metadata is None
            else metadata
        ),
    )


def _resolved_tools() -> ResolvedToolSet:
    return ResolvedToolSet(
        tools=(
            ResolvedTool(
                tool=Tool(
                    id="tool.weather",
                    name="weather.lookup",
                    description="Lookup weather.",
                ),
                schema=ToolSchema(
                    name="weather.lookup",
                    description="Lookup weather.",
                ),
                target=ToolExecutionTarget(),
            ),
        ),
    )


def _profile() -> AgentProfile:
    return AgentProfile(
        id="assistant",
        name="Assistant",
        instruction_policy=AgentInstructionPolicy(
            system_prompt="You are a helpful runtime agent.",
        ),
        llm_routing_policy=AgentLlmRoutingPolicy(default_llm_id="llm.default"),
        runtime_preferences=AgentRuntimePreferences(
            home_dir="/agents/assistant",
            workspace="/workspace/profile",
        ),
    )


def _llm_profile() -> LlmProfile:
    return LlmProfile(
        id="llm.default",
        provider=LlmProviderKind.OPENAI,
        api_family=LlmApiFamily.OPENAI_RESPONSES,
        model_name="gpt-test",
        context_window_tokens=2000,
        capabilities=(LlmCapability.TOOL_CALLING,),
    )


def _session() -> Session:
    return Session(
        id="session:assistant",
        agent_id="assistant",
        active_session_id="active-session",
        metadata={
            "runtime_binding": {
                "agent_id": "assistant",
                "workspace": "/workspace/session",
            },
        },
    )


def _default_session_items() -> tuple[SessionItem, ...]:
    return (
        _session_item(
            id="item-current",
            sequence_no=1,
            text="current request",
            role="user",
            source_module="orchestration",
            source_kind="orchestration_run",
            source_id="run-1",
        ),
        _session_item(
            id="item-assistant",
            sequence_no=2,
            text="working on it",
            role="assistant",
            source_module="llm",
            source_kind="llm_response_item",
            source_id="llm-item-assistant",
        ),
        _session_item(
            id="item-other-session",
            session_id="previous-session",
            sequence_no=3,
            text="previous instance",
        ),
    )


def _session_item(
    *,
    id: str,
    sequence_no: int,
    text: str,
    role: str = "user",
    session_id: str = "active-session",
    source_module: str | None = None,
    source_kind: str | None = None,
    source_id: str | None = None,
    phase: SessionItemPhase = SessionItemPhase.UNKNOWN,
) -> SessionItem:
    kind = (
        SessionItemKind.ASSISTANT_MESSAGE
        if role == "assistant"
        else SessionItemKind.USER_MESSAGE
    )
    return SessionItem(
        id=id,
        session_key="session:assistant",
        session_id=session_id,
        sequence_no=sequence_no,
        kind=kind,
        role=role,
        phase=phase,
        content_payload={"blocks": [{"type": "text", "text": text}]},
        source_module=source_module,
        source_kind=source_kind,
        source_id=source_id,
    )


class _FakeAgentService:
    def get_profile(self, profile_id: str) -> AgentProfile:
        assert profile_id == "assistant"
        return _profile()

    def list_profiles(self) -> list[AgentProfile]:
        return [_profile()]


class _FakeLlmPort:
    def get_profile(self, llm_id: str) -> LlmProfile:
        assert llm_id == "llm.default"
        return _llm_profile()


class _FakeSessionService:
    def __init__(self) -> None:
        self.item_inputs: list[ListSessionItemsInput] = []
        self.replay_inputs: list[object] = []
        self.items: tuple[SessionItem, ...] = _default_session_items()

    def get_session_with_items(
        self,
        data: ListSessionItemsInput,
    ) -> SessionItemsBundle:
        self.item_inputs.append(data)
        assert data.session_key == "session:assistant"
        assert data.active_session_only is True
        session = _session()
        active_items = tuple(
            item
            for item in self.items
            if not data.active_session_only or item.session_id == session.active_session_id
        )
        items = active_items[-data.limit :] if data.limit is not None else active_items
        return SessionItemsBundle(session=session, items=items)

    def list_items(
        self,
        data: ListSessionItemsInput,
    ) -> list[SessionItem]:
        return list(self.get_session_with_items(data).items)


class _ExecutionChainRef:
    id = "chain-run-1"


class _ExecutionStepRef:
    id = "step-tools"


class _FakeExecutionQuery:
    def __init__(
        self,
        *,
        items: tuple[ExecutionStepItem, ...] = (),
    ) -> None:
        self.items = items

    def list_execution_chains(self, turn_id: str) -> list[_ExecutionChainRef]:
        assert turn_id == "run-1"
        return [_ExecutionChainRef()]

    def list_execution_steps(self, chain_id: str) -> list[_ExecutionStepRef]:
        assert chain_id == "chain-run-1"
        return [_ExecutionStepRef()]

    def list_execution_step_items(self, step_id: str) -> list[ExecutionStepItem]:
        assert step_id == "step-tools"
        return list(self.items)


class _FakeLlmResolver:
    def __init__(self, *, expected_requested_llm_id: str = "llm.default") -> None:
        self.expected_requested_llm_id = expected_requested_llm_id
        self.calls: list[dict[str, object]] = []

    def resolve(
        self,
        *,
        requested_llm_id: str | None,
        routing_policy,
        input_content,
        workspace_dir: str | None = None,
        validate_access: bool = True,
    ) -> ResolvedLlmSelection:
        self.calls.append(
            {
                "requested_llm_id": requested_llm_id,
                "routing_policy": routing_policy,
                "input_content": input_content,
                "workspace_dir": workspace_dir,
                "validate_access": validate_access,
            },
        )
        assert requested_llm_id == self.expected_requested_llm_id
        assert routing_policy.default_llm_id == "llm.default"
        assert workspace_dir == "/workspace/session"
        return ResolvedLlmSelection(
            requested_llm_id=str(requested_llm_id or ""),
            resolved_llm_id="llm.default",
            strategy="test",
        )


class _FakeEventService:
    def __init__(self) -> None:
        self.events: list[object] = []

    def publish(self, event) -> None:
        self.events.append(event)
