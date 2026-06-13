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
from crxzipple.modules.orchestration.application.prompt_input import (
    RunPromptInputCollector,
)
from crxzipple.modules.orchestration.application.prompting import PromptMode
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
    SessionItemVisibility,
)
from crxzipple.modules.skills.application import SkillCatalogPrompt
from crxzipple.modules.tool.domain import Tool, ToolExecutionTarget


def test_build_collects_normal_turn_inputs_for_context_workspace() -> None:
    skill_catalog = _FakeSkillCatalogPort(
        prompt=SkillCatalogPrompt(
            content="- weather.lookup: check weather",
            metadata={"available_skill_names": ["weather"]},
        ),
    )
    collector = _collector(skill_catalog=skill_catalog)
    run = _run()
    resolved_tools = _resolved_tools()

    result = collector.build(run, resolved_tools=resolved_tools)

    assert result.llm_id == "llm.default"
    assert result.session_key == "session:assistant"
    assert result.active_session_id == "active-session"
    assert result.mode is PromptMode.NORMAL_TURN
    assert result.surface_policy.surface == "interactive"
    assert result.workspace_dir == "/workspace/session"
    assert [message.metadata["session_item_id"] for message in result.messages] == [
        "item-current",
    ]
    assert tuple(message.role for message in result.messages) == (LlmMessageRole.USER,)
    assert tuple(schema.name for schema in result.tool_schemas) == ("weather.lookup",)
    assert result.skills_catalog is not None
    assert result.report is not None
    assert result.report.transcript_message_count == 1
    assert result.report.context_budget_source == "context_window_scaled"
    assert result.report.context_budget_estimated_tokens == 300
    assert len(collector.session_service.item_inputs) == 1
    assert skill_catalog.calls == [
        {
            "workspace_dir": "/workspace/session",
            "surface": "interactive",
            "available_tool_ids": ("tool.weather",),
            "interface": "web",
            "agent_id": "assistant",
            "run_id": "run-1",
            "session_key": "session:assistant",
            "active_session_id": "active-session",
        }
    ]


def test_build_prefers_model_visible_session_items_for_provider_replay() -> None:
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
            visibility=SessionItemVisibility(model_visible=True),
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
            visibility=SessionItemVisibility(model_visible=True),
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

    assert len(session_service.item_inputs) == 1
    assert [message.metadata.get("session_item_id") for message in result.messages] == [
        "item-call-1",
        "item-result-1",
    ]
    assert result.messages[0].content == {
        "type": "function_call",
        "call_id": "call-weather-1",
        "name": "weather.lookup",
        "arguments": {"city": "Kunming"},
    }
    assert result.messages[1].tool_call_id == "call-weather-1"
    assert result.report is not None
    assert result.report.transcript_tool_result_stats["tool_result_item_count"] == 1
    report_payload = result.report.to_payload()
    transcript_budget = report_payload["transcript"]["budget"]
    assert transcript_budget["source"] == "session_items"
    assert transcript_budget["frontier"] == {
        "from_sequence_no": 1,
        "to_sequence_no": 2,
        "from_item_id": "item-call-1",
        "to_item_id": "item-result-1",
        "item_count": 2,
    }
    assert transcript_budget["protocol_required_preserved"] is True
    assert [ref["item_id"] for ref in transcript_budget["protocol_required_refs"]] == [
        "item-call-1",
        "item-result-1",
    ]


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


def test_build_memory_flush_uses_maintenance_surface_without_skills_catalog() -> None:
    skill_catalog = _FakeSkillCatalogPort(
        prompt=SkillCatalogPrompt(content="- unused", metadata={}),
    )
    collector = _collector(skill_catalog=skill_catalog)

    result = collector.build(
        _run(),
        resolved_tools=_resolved_tools(),
        mode=PromptMode.MEMORY_FLUSH,
    )

    assert result.mode is PromptMode.MEMORY_FLUSH
    assert result.surface_policy.surface == "maintenance_write"
    assert result.surface_policy.require_tool_call is True
    assert result.surface_policy.record_assistant_messages is False
    assert result.skills_catalog is None
    assert tuple(schema.name for schema in result.tool_schemas) == ("weather.lookup",)
    assert skill_catalog.calls == []


def test_build_memory_flush_prefers_model_visible_session_items_without_message_read() -> None:
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
            visibility=SessionItemVisibility(model_visible=True),
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
            visibility=SessionItemVisibility(model_visible=True),
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
        mode=PromptMode.MEMORY_FLUSH,
    )

    assert result.mode is PromptMode.MEMORY_FLUSH
    assert len(session_service.item_inputs) == 1
    assert [message.metadata.get("session_item_id") for message in result.messages] == [
        "item-memory-call",
        "item-memory-result",
    ]
    assert result.report is not None
    budget = result.report.to_payload()["transcript"]["budget"]
    assert budget["source"] == "session_items"
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
    skill_catalog: "_FakeSkillCatalogPort | None" = None,
    session_service: "_FakeSessionService | None" = None,
    execution_query: "_FakeExecutionQuery | None" = None,
) -> RunPromptInputCollector:
    return RunPromptInputCollector(
        agent_service=_FakeAgentService(),
        llm_port=_FakeLlmPort(),
        skill_catalog_port=skill_catalog or _FakeSkillCatalogPort(),
        session_service=session_service or _FakeSessionService(),
        llm_resolver=_FakeLlmResolver(),
        execution_query=execution_query,
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
        content_payload={"blocks": [{"type": "text", "text": text}]},
        visibility=SessionItemVisibility(model_visible=True),
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
        self.items: tuple[SessionItem, ...] = _default_session_items()

    def get_session_with_items(
        self,
        data: ListSessionItemsInput,
    ) -> SessionItemsBundle:
        self.item_inputs.append(data)
        assert data.session_key == "session:assistant"
        assert data.active_session_only is True
        assert data.model_visible is True
        return SessionItemsBundle(session=_session(), items=self.items)

    def list_model_visible_items(
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
    def resolve(
        self,
        *,
        requested_llm_id: str | None,
        routing_policy,
        input_content,
        workspace_dir: str | None = None,
    ) -> ResolvedLlmSelection:
        assert requested_llm_id == "llm.default"
        assert routing_policy.default_llm_id == "llm.default"
        assert workspace_dir == "/workspace/session"
        return ResolvedLlmSelection(
            requested_llm_id="llm.default",
            resolved_llm_id="llm.default",
            strategy="test",
        )


@dataclass(slots=True)
class _FakeSkillCatalogResolution:
    prompt_catalog: SkillCatalogPrompt | None
    skills: tuple[object, ...] = ()


class _FakeSkillCatalogPort:
    def __init__(self, prompt: SkillCatalogPrompt | None = None) -> None:
        self.prompt = prompt
        self.calls: list[dict[str, object]] = []

    def build_prompt_catalog(
        self,
        *,
        workspace_dir: str | None,
        surface: str,
    ) -> SkillCatalogPrompt | None:
        return self.prompt

    def list_available(self, *, workspace_dir: str | None, surface: str) -> tuple:
        return ()

    def resolve_prompt_catalog(
        self,
        *,
        workspace_dir: str | None,
        surface: str,
        available_tool_ids: tuple[str, ...],
        interface: str | None = None,
        agent_id: str | None = None,
        run_id: str | None = None,
        session_key: str | None = None,
        active_session_id: str | None = None,
    ) -> _FakeSkillCatalogResolution:
        self.calls.append(
            {
                "workspace_dir": workspace_dir,
                "surface": surface,
                "available_tool_ids": available_tool_ids,
                "interface": interface,
                "agent_id": agent_id,
                "run_id": run_id,
                "session_key": session_key,
                "active_session_id": active_session_id,
            }
        )
        return _FakeSkillCatalogResolution(prompt_catalog=self.prompt)
