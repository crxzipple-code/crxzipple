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
    InboundInstruction,
    OrchestrationRun,
    OrchestrationValidationError,
)
from crxzipple.modules.session.application import (
    ListSessionMessagesInput,
    SessionMessagesBundle,
)
from crxzipple.modules.session.domain import (
    Session,
    SessionMessage,
    SessionMessageVisibility,
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
    assert [message.metadata["session_message_id"] for message in result.messages] == [
        "msg-current",
        "msg-assistant",
    ]
    assert tuple(message.role for message in result.messages) == (
        LlmMessageRole.USER,
        LlmMessageRole.ASSISTANT,
    )
    assert tuple(schema.name for schema in result.tool_schemas) == ("weather.lookup",)
    assert result.skills_catalog is not None
    assert result.report is not None
    assert result.report.transcript_message_count == 2
    assert result.report.context_budget_source == "context_window_scaled"
    assert result.report.context_budget_estimated_tokens == 300
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
) -> RunPromptInputCollector:
    return RunPromptInputCollector(
        agent_service=_FakeAgentService(),
        llm_port=_FakeLlmPort(),
        skill_catalog_port=skill_catalog or _FakeSkillCatalogPort(),
        session_service=_FakeSessionService(),
        llm_resolver=_FakeLlmResolver(),
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


def _session_bundle() -> SessionMessagesBundle:
    session = Session(
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
    messages = (
        _message(
            id="msg-old",
            sequence_no=1,
            text="old turn",
        ),
        _message(
            id="msg-current",
            sequence_no=2,
            text="current request",
            source_kind="orchestration_run",
            source_id="run-1",
        ),
        _message(
            id="msg-archived",
            sequence_no=3,
            text="archived",
            visibility=SessionMessageVisibility.ARCHIVED,
        ),
        _message(
            id="msg-other-session",
            session_id="previous-session",
            sequence_no=4,
            text="previous instance",
        ),
        _message(
            id="msg-assistant",
            sequence_no=5,
            role="assistant",
            text="working on it",
        ),
    )
    return SessionMessagesBundle(session=session, messages=messages)


def _message(
    *,
    id: str,
    sequence_no: int,
    text: str,
    role: str = "user",
    session_id: str = "active-session",
    source_kind: str | None = None,
    source_id: str | None = None,
    visibility: SessionMessageVisibility = SessionMessageVisibility.DEFAULT,
) -> SessionMessage:
    return SessionMessage(
        id=id,
        session_key="session:assistant",
        session_id=session_id,
        sequence_no=sequence_no,
        role=role,
        content_payload={"blocks": [{"type": "text", "text": text}]},
        source_kind=source_kind,
        source_id=source_id,
        visibility=visibility,
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
        self.inputs: list[ListSessionMessagesInput] = []

    def get_session_with_messages(
        self,
        data: ListSessionMessagesInput,
    ) -> SessionMessagesBundle:
        self.inputs.append(data)
        assert data.session_key == "session:assistant"
        assert data.active_session_only is True
        return _session_bundle()


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
