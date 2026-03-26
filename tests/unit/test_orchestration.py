from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import timedelta, timezone, datetime
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from crxzipple.core.config import load_settings
from crxzipple.modules.agent.application import RegisterAgentProfileInput
from crxzipple.modules.authorization.domain import AuthorizationEffect, AuthorizationPolicy
from crxzipple.modules.dispatch.application import (
    CreateDispatchTaskInput,
    EnqueueDispatchTaskInput,
    RecoverAbandonedDispatchTasksInput,
)
from crxzipple.modules.agent.domain import (
    AgentInstructionPolicy,
    AgentLlmRoutingPolicy,
    AgentRuntimePreferences,
)
from crxzipple.modules.dispatch.domain import DispatchPolicy, DispatchTaskStatus
from crxzipple.modules.llm.application import RegisterLlmProfileInput
from crxzipple.modules.llm.application.adapters import (
    LlmAdapterRequest,
    LlmAdapterResponse,
)
from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmMessageRole,
    LlmProviderKind,
    LlmResult,
    ToolCallIntent,
)
from crxzipple.modules.memory.application import (
    ApproveMemoryCandidateInput,
    CreateMemoryCandidateInput,
    ListMemoryEntriesInput,
)
from crxzipple.modules.orchestration.application import (
    AcceptOrchestrationRunInput,
    AdvanceOrchestrationRunInput,
    CompleteOrchestrationRunInput,
    EnqueueOrchestrationRunInput,
    FailOrchestrationRunInput,
    PrepareSessionRunInput,
    RequestCompactionInput,
    RequestDueHeartbeatsInput,
    RequestHeartbeatInput,
    RequestMemoryFlushInput,
    ResolveApprovalRequestInput,
    ResumeOrchestrationRunInput,
    ResolveSessionBundleInput,
    RouteOrchestrationRunInput,
    WaitOnToolInput,
)
from crxzipple.modules.orchestration.domain import (
    ApprovalDecision,
    DeliveryTarget,
    InboundInstruction,
    OrchestrationQueuePolicy,
    OrchestrationRunStage,
    OrchestrationRunStatus,
    OrchestrationValidationError,
)
from crxzipple.modules.session.application import (
    AppendSessionMessageInput,
    ListSessionMessagesInput,
)
from crxzipple.modules.session.domain import (
    DirectSessionScope,
    SessionMessageKind,
    SessionRouteContext,
)
from crxzipple.modules.tool.application import ExecuteToolInput, RegisterToolInput
from crxzipple.modules.tool.domain import (
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolExecutionSupport,
    ToolMode,
    ToolRunStatus,
)
from tests.unit.support import SqliteTestHarness


class _StaticTextAdapter:
    def __init__(self, *, text: str) -> None:
        self.text = text
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        return LlmAdapterResponse(result=LlmResult(text=self.text))


class _SequentialTextAdapter:
    def __init__(self, *texts: str) -> None:
        self._texts = list(texts)
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        text = self._texts.pop(0) if self._texts else ""
        return LlmAdapterResponse(result=LlmResult(text=text))


class _ToolCallAdapter:
    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        return LlmAdapterResponse(
            result=LlmResult(
                text="calling tool",
                tool_calls=(
                    ToolCallIntent(
                        id="call-1",
                        name="search_docs",
                        arguments={"query": "ddd"},
                    ),
                ),
            ),
        )


class _InlineToolLoopAdapter:
    def __init__(self) -> None:
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        tool_messages = [
            message
            for message in request.messages
            if message.role is LlmMessageRole.TOOL
        ]
        if not tool_messages:
            return LlmAdapterResponse(
                result=LlmResult(
                    tool_calls=(
                        ToolCallIntent(
                            id="call-echo-1",
                            name="echo",
                            arguments={"message": "hello from tool"},
                        ),
                    ),
                ),
            )
        return LlmAdapterResponse(result=LlmResult(text="tool loop complete"))


class _BackgroundToolAdapter:
    def __init__(self) -> None:
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        return LlmAdapterResponse(
            result=LlmResult(
                tool_calls=(
                    ToolCallIntent(
                        id="call-bg-1",
                        name="background_echo",
                        arguments={"message": "background hello"},
                    ),
                ),
            ),
        )


class _BackgroundResumeAdapter:
    def __init__(self) -> None:
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        tool_messages = [
            message
            for message in request.messages
            if message.role is LlmMessageRole.TOOL
        ]
        if not tool_messages:
            return LlmAdapterResponse(
                result=LlmResult(
                    tool_calls=(
                        ToolCallIntent(
                            id="call-bg-1",
                            name="background_echo",
                            arguments={"message": "background hello"},
                        ),
                    ),
                ),
            )
        return LlmAdapterResponse(result=LlmResult(text="background loop complete"))


class _BackgroundApprovalAdapter:
    def __init__(self) -> None:
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        tool_messages = [
            message
            for message in request.messages
            if message.role is LlmMessageRole.TOOL
        ]
        if not tool_messages:
            return LlmAdapterResponse(
                result=LlmResult(
                    tool_calls=(
                        ToolCallIntent(
                            id="call-bg-approval-1",
                            name="background_echo",
                            arguments={"message": "background approval hello"},
                        ),
                    ),
                ),
            )
        return LlmAdapterResponse(
            result=LlmResult(text="background approval flow complete"),
        )


class _EffectApprovalAdapter:
    def __init__(self) -> None:
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        tool_messages = [
            message
            for message in request.messages
            if message.role is LlmMessageRole.TOOL
        ]
        echo_messages = [
            message
            for message in tool_messages
            if message.name == "echo"
        ]
        if not tool_messages:
            return LlmAdapterResponse(
                result=LlmResult(
                    tool_calls=(
                        ToolCallIntent(
                            id="call-echo-1",
                            name="echo",
                            arguments={"message": "hello after approval"},
                        ),
                    ),
                ),
            )
        if not echo_messages:
            raise AssertionError("approval replay should provide an echo tool result")
        return LlmAdapterResponse(result=LlmResult(text="approval flow complete"))


class _MultiToolApprovalAdapter:
    def __init__(self) -> None:
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        tool_messages = [
            message
            for message in request.messages
            if message.role is LlmMessageRole.TOOL
        ]
        if not tool_messages:
            return LlmAdapterResponse(
                result=LlmResult(
                    tool_calls=(
                        ToolCallIntent(
                            id="call-echo-1",
                            name="echo",
                            arguments={"message": "first gated echo"},
                        ),
                        ToolCallIntent(
                            id="call-echo-2",
                            name="echo",
                            arguments={"message": "second orphaned echo"},
                        ),
                    ),
                ),
            )
        return LlmAdapterResponse(result=LlmResult(text="multi approval flow complete"))


class _EffectApprovalOrVisibleAdapter:
    def __init__(self) -> None:
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        tool_messages = [
            message
            for message in request.messages
            if message.role is LlmMessageRole.TOOL
        ]
        echo_messages = [
            message
            for message in tool_messages
            if message.name == "echo"
        ]
        if not tool_messages:
            return LlmAdapterResponse(
                result=LlmResult(
                    tool_calls=(
                        ToolCallIntent(
                            id="call-echo-1",
                            name="echo",
                            arguments={"message": "hello after approval"},
                        ),
                    ),
                ),
            )
        if not echo_messages:
            return LlmAdapterResponse(
                result=LlmResult(
                    tool_calls=(
                        ToolCallIntent(
                            id="call-echo-2",
                            name="echo",
                            arguments={"message": "hello after approval"},
                        ),
                    ),
                ),
            )
        return LlmAdapterResponse(result=LlmResult(text="approval flow complete"))


class _EffectDeniedFallbackAdapter:
    def __init__(self) -> None:
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        system_text = "\n\n".join(
            str(message.content)
            for message in request.messages
            if message.role is LlmMessageRole.SYSTEM
        )
        if "The user denied the requested additional access." in system_text:
            return LlmAdapterResponse(
                result=LlmResult(text="fallback after denial"),
            )
        return LlmAdapterResponse(
            result=LlmResult(
                tool_calls=(
                    ToolCallIntent(
                        id="call-echo-1",
                        name="echo",
                        arguments={"message": "hello after approval"},
                    ),
                ),
            ),
        )


class _SkillLoadingAdapter:
    def __init__(self) -> None:
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        tool_messages = [
            message
            for message in request.messages
            if message.role is LlmMessageRole.TOOL
        ]
        skill_messages = [
            message
            for message in tool_messages
            if message.name == "open_skill"
        ]
        if not skill_messages:
            return LlmAdapterResponse(
                result=LlmResult(
                    tool_calls=(
                        ToolCallIntent(
                            id="call-skill-1",
                            name="open_skill",
                            arguments={"skill": "repo-review"},
                        ),
                    ),
                ),
            )
        return LlmAdapterResponse(result=LlmResult(text="used repo-review skill"))


class _MemorySearchAndGetAdapter:
    def __init__(self, *, entry_id: str) -> None:
        self.entry_id = entry_id
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        tool_messages = [
            message
            for message in request.messages
            if message.role is LlmMessageRole.TOOL
        ]
        search_messages = [
            message
            for message in tool_messages
            if message.name == "memory_search"
        ]
        get_messages = [
            message
            for message in tool_messages
            if message.name == "memory_get"
        ]
        if not search_messages:
            return LlmAdapterResponse(
                result=LlmResult(
                    tool_calls=(
                        ToolCallIntent(
                            id="call-memory-search-1",
                            name="memory_search",
                            arguments={"query": "approval model", "limit": 3},
                        ),
                    ),
                ),
            )
        if not get_messages:
            return LlmAdapterResponse(
                result=LlmResult(
                    tool_calls=(
                        ToolCallIntent(
                            id="call-memory-get-1",
                            name="memory_get",
                            arguments={"entry_id": self.entry_id},
                        ),
                    ),
                ),
            )
        return LlmAdapterResponse(result=LlmResult(text="memory-guided answer"))


class _FailingAdapter:
    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        del request
        raise RuntimeError("sample adapter failure")


class _SlowStaticTextAdapter:
    def __init__(self, *, text: str, delay_seconds: float) -> None:
        self.text = text
        self.delay_seconds = delay_seconds
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        time.sleep(self.delay_seconds)
        return LlmAdapterResponse(result=LlmResult(text=self.text))


class OrchestrationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = SqliteTestHarness()
        self.harness.initialize_schema()
        self.container = self.harness.build_container()
        self._skills_tempdir = tempfile.TemporaryDirectory()
        skills_root = Path(self._skills_tempdir.name)
        self._global_skills_patcher = patch(
            "crxzipple.modules.orchestration.application.skills_context.DEFAULT_GLOBAL_SKILLS_DIR",
            skills_root / "global",
        )
        self._system_skills_patcher = patch(
            "crxzipple.modules.orchestration.application.skills_context.DEFAULT_SYSTEM_SKILLS_DIR",
            skills_root / "system",
        )
        self._global_skills_patcher.start()
        self._system_skills_patcher.start()

    def tearDown(self) -> None:
        self._system_skills_patcher.stop()
        self._global_skills_patcher.stop()
        self._skills_tempdir.cleanup()
        self.harness.close()

    def _register_agent_and_llm(
        self,
        *,
        llm_id: str = "openai.gpt-5.4-mini",
        context_window_tokens: int | None = None,
        runtime_preferences: AgentRuntimePreferences | None = None,
    ) -> None:
        self.container.llm_service.register_profile(
            RegisterLlmProfileInput(
                id=llm_id,
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
                context_window_tokens=context_window_tokens,
            ),
        )
        self.container.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="assistant",
                name="Assistant",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Be helpful and concise.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(default_llm_id=llm_id),
                runtime_preferences=runtime_preferences or AgentRuntimePreferences(),
            ),
        )

    def test_accept_prepare_session_queue_and_claim_run(self) -> None:
        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-1",
                inbound_instruction=InboundInstruction(
                    source="http",
                    content="Summarize this",
                    metadata={"request_id": "req-1"},
                ),
                delivery_target=DeliveryTarget(
                    interface_name="http",
                    address="request:req-1",
                ),
                priority=20,
                max_steps=6,
            ),
        )

        self.assertEqual(run.status, OrchestrationRunStatus.ACCEPTED)
        self.assertEqual(run.stage, OrchestrationRunStage.ACCEPTED)

        prepared = self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="writer",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    label="browser",
                    surface="chat",
                    direct_scope=DirectSessionScope.MAIN,
                    metadata={"request_id": "req-1"},
                ),
                priority=10,
            ),
        )
        queued = self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )
        claimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )

        self.assertEqual(prepared.stage, OrchestrationRunStage.BULK_READY)
        self.assertEqual(queued.status, OrchestrationRunStatus.QUEUED)
        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed.id, run.id)
        self.assertEqual(claimed.status, OrchestrationRunStatus.RUNNING)
        self.assertEqual(claimed.stage, OrchestrationRunStage.RUNNING)
        self.assertEqual(claimed.worker_id, "worker-1")
        self.assertEqual(claimed.bulk_key, "conversation:main:webchat:default:main")
        self.assertTrue(claimed.active_session_id)
        self.assertIsNotNone(claimed.started_at)
        self.assertEqual(claimed.metadata["session_key"], "agent:writer:main")
        self.assertEqual(claimed.metadata["session_kind"], "main")
        dispatch_task = self.container.dispatch_service.get_task(run.id)
        self.assertEqual(dispatch_task.status, DispatchTaskStatus.CLAIMED)
        self.assertEqual(dispatch_task.policy, DispatchPolicy.FIFO)
        self.assertEqual(dispatch_task.claimed_by, "worker-1")
        self.assertIsNotNone(dispatch_task.lease_expires_at)

    def test_tool_resolver_applies_authorized_tool_access_override(self) -> None:
        custom_harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            authorization_enabled=True,
            authorization_policy_paths=(
                str(
                    Path(__file__).resolve().parents[2]
                    / "config"
                    / "authorization_policies"
                    / "default.yaml"
                ),
            ),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        custom_harness.initialize_schema(settings=settings)
        container = custom_harness.build_container(settings=settings)
        try:
            container.llm_service.register_profile(
                RegisterLlmProfileInput(
                    id="openai.gpt-5.4-mini",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4-mini",
                ),
            )
            container.agent_service.register_profile(
                RegisterAgentProfileInput(
                    id="assistant",
                    name="Assistant",
                    instruction_policy=AgentInstructionPolicy(system_prompt="Be helpful."),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.gpt-5.4-mini",
                    ),
                ),
            )
            container.tool_service.register(
                RegisterToolInput(
                    id="brave_search.news_search",
                    name="News Search",
                    description="Search news.",
                    supported_environments=(ToolEnvironment.REMOTE,),
                    required_effect_ids=("network_search",),
                ),
            )
            container.tool_service.register(
                RegisterToolInput(
                    id="open_meteo_weather.forecast_weather",
                    name="Forecast Weather",
                    description="Get weather data.",
                    supported_environments=(ToolEnvironment.REMOTE,),
                    required_effect_ids=("weather_data",),
                ),
            )
            container.authorization_service.grant_agent_tool_access(
                agent_id="assistant",
                tool_id="brave_search.news_search",
            )

            run = container.orchestration_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-tool-access-allow",
                    inbound_instruction=InboundInstruction(source="cli", content="hello"),
                ),
            )
            container.orchestration_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        llm_id="openai.gpt-5.4-mini",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )

            resolved = container.orchestration_service.engine.tool_resolver.resolve(
                container.orchestration_service.get_run(run.id),
            )

            self.assertEqual(
                [item.tool.id for item in resolved.tools],
                [
                    "brave_search.news_search",
                    "open_meteo_weather.forecast_weather",
                ],
            )
            weather_tool = resolved.by_name("open_meteo_weather.forecast_weather")
            self.assertIsNotNone(weather_tool)
            assert weather_tool is not None
            execution = container.orchestration_service.engine.tool_resolver.execution_decision(
                container.orchestration_service.get_run(run.id),
                tool=weather_tool.tool,
                target=weather_tool.target,
            )
            self.assertEqual(execution.mode, "approval_required")
            self.assertIsNotNone(execution.approval)
            assert execution.approval is not None
            self.assertEqual(execution.approval.id, "weather_data")
        finally:
            custom_harness.close()

    def test_tool_resolver_applies_authorized_effect_access(self) -> None:
        custom_harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            authorization_enabled=True,
            authorization_policy_paths=(
                str(
                    Path(__file__).resolve().parents[2]
                    / "config"
                    / "authorization_policies"
                    / "default.yaml"
                ),
            ),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        custom_harness.initialize_schema(settings=settings)
        container = custom_harness.build_container(settings=settings)
        try:
            container.llm_service.register_profile(
                RegisterLlmProfileInput(
                    id="openai.gpt-5.4-mini",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4-mini",
                ),
            )
            container.agent_service.register_profile(
                RegisterAgentProfileInput(
                    id="assistant",
                    name="Assistant",
                    instruction_policy=AgentInstructionPolicy(system_prompt="Be helpful."),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.gpt-5.4-mini",
                    ),
                ),
            )
            container.tool_service.register(
                RegisterToolInput(
                    id="brave_search.news_search",
                    name="News Search",
                    description="Search news.",
                    supported_environments=(ToolEnvironment.REMOTE,),
                    required_effect_ids=("network_search",),
                ),
            )
            container.tool_service.register(
                RegisterToolInput(
                    id="open_meteo_weather.forecast_weather",
                    name="Forecast Weather",
                    description="Get weather data.",
                    supported_environments=(ToolEnvironment.REMOTE,),
                    required_effect_ids=("weather_data",),
                ),
            )
            container.authorization_service.grant_agent_effect_access(
                agent_id="assistant",
                effect_id="network_search",
            )

            run = container.orchestration_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-effect-access-allow",
                    inbound_instruction=InboundInstruction(source="cli", content="hello"),
                ),
            )
            container.orchestration_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        llm_id="openai.gpt-5.4-mini",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )

            resolved = container.orchestration_service.engine.tool_resolver.resolve(
                container.orchestration_service.get_run(run.id),
            )

            self.assertEqual(
                [item.tool.id for item in resolved.tools],
                [
                    "brave_search.news_search",
                    "open_meteo_weather.forecast_weather",
                ],
            )
            search_tool = resolved.by_name("brave_search.news_search")
            weather_tool = resolved.by_name("open_meteo_weather.forecast_weather")
            self.assertIsNotNone(search_tool)
            self.assertIsNotNone(weather_tool)
            assert search_tool is not None
            assert weather_tool is not None
            search_execution = container.orchestration_service.engine.tool_resolver.execution_decision(
                container.orchestration_service.get_run(run.id),
                tool=search_tool.tool,
                target=search_tool.target,
            )
            weather_execution = container.orchestration_service.engine.tool_resolver.execution_decision(
                container.orchestration_service.get_run(run.id),
                tool=weather_tool.tool,
                target=weather_tool.target,
            )
            self.assertEqual(search_execution.mode, "allow")
            self.assertEqual(weather_execution.mode, "approval_required")
        finally:
            custom_harness.close()

    def test_tool_resolver_blocks_tool_when_authorization_explicitly_denies_tool_access(self) -> None:
        custom_harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            authorization_enabled=True,
            authorization_policy_paths=(
                str(
                    Path(__file__).resolve().parents[2]
                    / "config"
                    / "authorization_policies"
                    / "default.yaml"
                ),
            ),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        custom_harness.initialize_schema(settings=settings)
        container = custom_harness.build_container(settings=settings)
        try:
            container.llm_service.register_profile(
                RegisterLlmProfileInput(
                    id="openai.gpt-5.4-mini",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4-mini",
                ),
            )
            container.agent_service.register_profile(
                RegisterAgentProfileInput(
                    id="assistant",
                    name="Assistant",
                    instruction_policy=AgentInstructionPolicy(system_prompt="Be helpful."),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.gpt-5.4-mini",
                    ),
                ),
            )
            container.tool_service.register(
                RegisterToolInput(
                    id="echo",
                    name="Echo",
                    description="Echo input.",
                ),
            )
            container.tool_service.register(
                RegisterToolInput(
                    id="filesystem.read_text",
                    name="Read Text",
                    description="Read a file.",
                ),
            )
            container.authorization_service.upsert_policy(
                AuthorizationPolicy(
                    id="deny_echo_tool_access",
                    description="Do not expose echo to this agent.",
                    effect=AuthorizationEffect.DENY,
                    actions=("tool.access_tool",),
                    resource_kind="tool",
                    resource_id="echo",
                    context_match={"agent_id": "assistant"},
                    priority=1000,
                ),
            )

            run = container.orchestration_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-tool-access-deny",
                    inbound_instruction=InboundInstruction(source="cli", content="hello"),
                ),
            )
            container.orchestration_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        llm_id="openai.gpt-5.4-mini",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )

            resolved = container.orchestration_service.engine.tool_resolver.resolve(
                container.orchestration_service.get_run(run.id),
            )

            self.assertEqual(
                [item.tool.id for item in resolved.tools],
                ["filesystem.read_text"],
            )
        finally:
            custom_harness.close()

    def test_tool_resolver_blocks_tool_when_authorization_explicitly_denies_effect_access(self) -> None:
        custom_harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            authorization_enabled=True,
            authorization_policy_paths=(
                str(
                    Path(__file__).resolve().parents[2]
                    / "config"
                    / "authorization_policies"
                    / "default.yaml"
                ),
            ),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        custom_harness.initialize_schema(settings=settings)
        container = custom_harness.build_container(settings=settings)
        try:
            container.llm_service.register_profile(
                RegisterLlmProfileInput(
                    id="openai.gpt-5.4-mini",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4-mini",
                ),
            )
            container.agent_service.register_profile(
                RegisterAgentProfileInput(
                    id="assistant",
                    name="Assistant",
                    instruction_policy=AgentInstructionPolicy(system_prompt="Be helpful."),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.gpt-5.4-mini",
                    ),
                ),
            )
            container.tool_service.register(
                RegisterToolInput(
                    id="brave_search.news_search",
                    name="News Search",
                    description="Search news.",
                    supported_environments=(ToolEnvironment.REMOTE,),
                    required_effect_ids=("network_search",),
                ),
            )
            container.authorization_service.upsert_policy(
                AuthorizationPolicy(
                    id="deny_network_search_effect_access",
                    description="Do not expose network search to this agent.",
                    effect=AuthorizationEffect.DENY,
                    actions=("tool.access_effect",),
                    resource_kind="tool",
                    resource_match={"authorization_effect_ids": ["network_search"]},
                    context_match={"agent_id": "assistant"},
                    priority=1000,
                ),
            )

            run = container.orchestration_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-effect-access-deny",
                    inbound_instruction=InboundInstruction(source="cli", content="hello"),
                ),
            )
            container.orchestration_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        llm_id="openai.gpt-5.4-mini",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )

            resolved = container.orchestration_service.engine.tool_resolver.resolve(
                container.orchestration_service.get_run(run.id),
            )

            self.assertEqual(resolved.tools, ())
        finally:
            custom_harness.close()

    def test_claim_next_queued_run_prefers_lower_priority(self) -> None:
        low_priority = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-low",
                inbound_instruction=InboundInstruction(source="cli", content="first"),
                priority=50,
            ),
        )
        high_priority = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-high",
                inbound_instruction=InboundInstruction(source="cli", content="second"),
                priority=5,
            ),
        )

        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=low_priority.id,
                agent_id="writer",
                bulk_key="conversation:one",
                lane_key="bulk:conversation:one",
            ),
        )
        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=high_priority.id,
                agent_id="writer",
                bulk_key="conversation:two",
                lane_key="bulk:conversation:two",
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=low_priority.id),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=high_priority.id),
        )

        claimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed.id, high_priority.id)

    def test_claim_next_queued_run_skips_blocked_lane(self) -> None:
        active = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-active",
                inbound_instruction=InboundInstruction(source="cli", content="active"),
                priority=50,
            ),
        )

        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=active.id,
                agent_id="writer",
                bulk_key="conversation:lane-a",
                lane_key="bulk:conversation:lane-a",
            ),
        )

        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=active.id),
        )
        first = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )

        blocked = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-blocked",
                inbound_instruction=InboundInstruction(source="cli", content="blocked"),
                priority=1,
            ),
        )
        available = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-available",
                inbound_instruction=InboundInstruction(source="cli", content="available"),
                priority=10,
            ),
        )

        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=blocked.id,
                agent_id="writer",
                bulk_key="conversation:lane-a",
                lane_key="bulk:conversation:lane-a",
            ),
        )
        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=available.id,
                agent_id="writer",
                bulk_key="conversation:lane-b",
                lane_key="bulk:conversation:lane-b",
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=blocked.id),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=available.id),
        )

        second = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-2",
        )

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        assert first is not None
        assert second is not None
        self.assertEqual(first.id, active.id)
        self.assertEqual(second.id, available.id)

    def test_claim_next_queued_run_blocks_lane_while_waiting(self) -> None:
        waiting = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-waiting",
                inbound_instruction=InboundInstruction(source="cli", content="waiting"),
                priority=5,
            ),
        )

        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=waiting.id,
                agent_id="writer",
                bulk_key="conversation:lane-wait",
                lane_key="bulk:conversation:lane-wait",
            ),
        )

        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=waiting.id),
        )

        claimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )
        assert claimed is not None
        self.container.orchestration_service.wait_on_tool(
            WaitOnToolInput(
                run_id=waiting.id,
                worker_id="worker-1",
                pending_tool_run_ids=("tool-run-1",),
                reason="tool_background_wait",
            ),
        )

        queued = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-same-lane",
                inbound_instruction=InboundInstruction(source="cli", content="queued"),
                priority=1,
            ),
        )
        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=queued.id,
                agent_id="writer",
                bulk_key="conversation:lane-wait",
                lane_key="bulk:conversation:lane-wait",
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=queued.id),
        )

        blocked = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-2",
        )

        self.assertIsNone(blocked)

    def test_claim_next_queued_run_ignores_foreign_dispatch_owner_kind(self) -> None:
        self._register_agent_and_llm()

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-owner-filter",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
                priority=50,
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        foreign_task = self.container.dispatch_service.create_task(
            CreateDispatchTaskInput(
                task_id="foreign-tool-task",
                owner_kind="tool_run",
                owner_id="tool-run-1",
                priority=1,
            ),
        )
        self.container.dispatch_service.enqueue_task(
            EnqueueDispatchTaskInput(
                task_id=foreign_task.id,
                priority=1,
            ),
        )

        claimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed.id, run.id)

        still_queued = self.container.dispatch_service.get_task(foreign_task.id)
        self.assertEqual(still_queued.status, DispatchTaskStatus.QUEUED)

    def test_heartbeat_run_extends_dispatch_lease(self) -> None:
        self._register_agent_and_llm()

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-heartbeat",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )
        claimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )
        assert claimed is not None
        first_task = self.container.dispatch_service.get_task(run.id)
        assert first_task.lease_expires_at is not None

        time.sleep(0.01)
        heartbeated = self.container.orchestration_service.heartbeat_run(
            run.id,
            worker_id="worker-1",
        )
        updated_task = self.container.dispatch_service.get_task(run.id)

        self.assertEqual(heartbeated.status, OrchestrationRunStatus.RUNNING)
        assert updated_task.lease_expires_at is not None
        self.assertGreater(updated_task.lease_expires_at, first_task.lease_expires_at)

    def test_recovered_dispatch_task_fails_running_orchestration_run(self) -> None:
        self._register_agent_and_llm()

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-recover-fail",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )
        claimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )
        assert claimed is not None

        dispatch_task = self.container.dispatch_service.get_task(run.id)
        assert dispatch_task.lease_expires_at is not None
        recovered = self.container.dispatch_service.recover_abandoned_tasks(
            RecoverAbandonedDispatchTasksInput(
                owner_kind="orchestration_run",
                reason="Orchestration worker lease expired before completion.",
                now=dispatch_task.lease_expires_at + timedelta(seconds=1),
            ),
        )

        self.assertEqual([task.id for task in recovered], [run.id])
        failed_run = self.container.orchestration_service.get_run(run.id)
        failed_task = self.container.dispatch_service.get_task(run.id)

        self.assertEqual(failed_run.status, OrchestrationRunStatus.FAILED)
        assert failed_run.error is not None
        self.assertEqual(failed_run.error.code, "worker_lease_expired")
        self.assertIn("failed for safety", failed_run.error.message)
        self.assertEqual(failed_task.status, DispatchTaskStatus.FAILED)

    def test_wait_on_tool_reconciles_when_tool_finished_before_wait_mapping(self) -> None:
        self._register_agent_and_llm()

        tool = self.container.tool_service.register(
            RegisterToolInput(
                id="background_echo",
                name="Background Echo",
                description="Only runs in the background.",
                supported_modes=(ToolMode.BACKGROUND,),
                runtime_key="background_echo",
            ),
        )

        async def background_echo(arguments: dict[str, object]) -> dict[str, object]:
            return {"message": arguments.get("message")}

        self.container.local_tool_catalog.register(tool, background_echo)

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-early-tool-finish",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )
        claimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )
        assert claimed is not None

        queued_tool_run = asyncio.run(
            self.container.tool_service.execute(
                ExecuteToolInput(
                    tool_id="background_echo",
                    arguments={"message": "background hello"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )
        finished_tool_run = self.container.tool_service.process_next_queued_run(
            worker_id="tool-worker-1",
        )

        self.assertEqual(queued_tool_run.status, ToolRunStatus.QUEUED)
        self.assertIsNotNone(finished_tool_run)
        assert finished_tool_run is not None
        self.assertEqual(finished_tool_run.status, ToolRunStatus.SUCCEEDED)

        reconciled = self.container.orchestration_service.wait_on_tool(
            WaitOnToolInput(
                run_id=run.id,
                worker_id="worker-1",
                pending_tool_run_ids=(queued_tool_run.id,),
                reason="tool_background_wait",
            ),
        )

        self.assertEqual(reconciled.status, OrchestrationRunStatus.QUEUED)
        self.assertEqual(reconciled.stage, OrchestrationRunStage.QUEUED)
        self.assertEqual(reconciled.pending_tool_run_ids, ())
        self.assertEqual(reconciled.queue_policy, OrchestrationQueuePolicy.RESUME_FIRST)

    def test_effect_request_waits_for_confirmation_and_resumes_after_allow_once(self) -> None:
        self.container.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="local-capability",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
            ),
        )
        self.container.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="writer",
                name="Writer",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Use tools when needed.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(default_llm_id="local-capability"),
            ),
        )

        tool = self.container.tool_service.register(
            RegisterToolInput(
                id="echo",
                name="Echo",
                description="Echoes a message.",
                supported_modes=(ToolMode.INLINE,),
                runtime_key="echo",
                required_effect_ids=("local_tool_access",),
            ),
        )

        async def echo(arguments: dict[str, object]) -> dict[str, object]:
            return {"echo": arguments.get("message")}

        self.container.local_tool_catalog.register(tool, echo)
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            _EffectApprovalAdapter(),
        )

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-capability-approval",
                inbound_instruction=InboundInstruction(source="cli", content="complete the task"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="writer",
                    llm_id="local-capability",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        waiting = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )
        assert waiting is not None
        self.assertEqual(waiting.status, OrchestrationRunStatus.WAITING)
        self.assertEqual(waiting.stage, OrchestrationRunStage.WAITING_FOR_CONFIRMATION)
        pending_request = waiting.pending_approval_request()
        self.assertIsNotNone(pending_request)
        assert pending_request is not None
        self.assertEqual(pending_request.effect_id, "local_tool_access")
        self.assertEqual(pending_request.tool_ids, ("echo",))
        self.assertEqual(pending_request.tool_name, "echo")

        resumed = self.container.orchestration_service.resolve_approval_request(
            ResolveApprovalRequestInput(
                run_id=run.id,
                request_id=pending_request.request_id,
                decision=ApprovalDecision.ALLOW_ONCE,
            ),
        )
        self.assertEqual(resumed.status, OrchestrationRunStatus.QUEUED)

        completed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )
        assert completed is not None
        self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
        assert completed.result_payload is not None
        self.assertEqual(completed.result_payload.get("output_text"), "approval flow complete")

    def test_process_next_queued_run_includes_approval_resume_flow_prompt(self) -> None:
        self.container.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="local-capability",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
            ),
        )
        self.container.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="writer",
                name="Writer",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Write carefully.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(
                    default_llm_id="local-capability",
                ),
            ),
        )
        tool = self.container.tool_service.register(
            RegisterToolInput(
                id="echo",
                name="Echo",
                description="Returns the input payload for local inline execution tests.",
                supported_modes=(ToolMode.INLINE,),
                runtime_key="echo",
                required_effect_ids=("local_tool_access",),
            ),
        )

        async def echo(arguments: dict[str, object]) -> dict[str, object]:
            return {"echo": arguments.get("message")}

        self.container.local_tool_catalog.register(tool, echo)
        adapter = _EffectApprovalAdapter()
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-approval-resume-flow-prompt",
                inbound_instruction=InboundInstruction(source="cli", content="complete the task"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="writer",
                    llm_id="local-capability",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        waiting = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )
        assert waiting is not None
        pending_request = waiting.pending_approval_request()
        assert pending_request is not None

        self.container.orchestration_service.resolve_approval_request(
            ResolveApprovalRequestInput(
                run_id=run.id,
                request_id=pending_request.request_id,
                decision=ApprovalDecision.ALLOW_ONCE,
            ),
        )
        completed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(completed)
        assert completed is not None
        self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
        self.assertGreaterEqual(len(adapter.requests), 2)
        resume_system_messages = [
            message
            for message in adapter.requests[1].messages
            if message.role is LlmMessageRole.SYSTEM
        ]
        self.assertTrue(
            any(
                "# Approval Update" in str(message.content)
                and "approved the requested additional access" in str(message.content)
                and "valid only for the current turn" in str(message.content)
                for message in resume_system_messages
            ),
        )
        refreshed_run = self.container.orchestration_service.get_run(run.id)
        session_messages = self.container.session_service.list_messages(
            ListSessionMessagesInput(
                session_key=str(refreshed_run.metadata["session_key"]),
            ),
        )
        self.assertTrue(
            any(
                message.kind is SessionMessageKind.TOOL_RESULT
                and message.source_kind == "approval_request"
                and (message.content or "").find("running echo") >= 0
                and (message.content or "").find("must be requested again later") >= 0
                for message in session_messages
            ),
        )

    def test_approval_does_not_persist_unprocessed_tool_calls_from_same_invocation(self) -> None:
        self.container.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="local-capability",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
            ),
        )
        self.container.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="writer",
                name="Writer",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Use tools when needed.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(default_llm_id="local-capability"),
            ),
        )

        tool = self.container.tool_service.register(
            RegisterToolInput(
                id="echo",
                name="Echo",
                description="Echoes a message.",
                supported_modes=(ToolMode.INLINE,),
                runtime_key="echo",
                required_effect_ids=("local_tool_access",),
            ),
        )

        async def echo(arguments: dict[str, object]) -> dict[str, object]:
            return {"echo": arguments.get("message")}

        self.container.local_tool_catalog.register(tool, echo)
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            _MultiToolApprovalAdapter(),
        )

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-multi-tool-approval",
                inbound_instruction=InboundInstruction(source="cli", content="complete the task"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="writer",
                    llm_id="local-capability",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        waiting = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )
        assert waiting is not None
        pending_request = waiting.pending_approval_request()
        assert pending_request is not None
        self.assertEqual(pending_request.request_id, "call-echo-1")

        session_messages = self.container.session_service.list_messages(
            ListSessionMessagesInput(
                session_key=str(waiting.metadata["session_key"]),
            ),
        )
        function_call_ids = [
            str(message.metadata.get("tool_call_id", "")).strip()
            for message in session_messages
            if message.role == "assistant"
            and message.content_payload.get("type") == "function_call"
        ]
        self.assertEqual(function_call_ids, ["call-echo-1"])

    def test_prompt_preview_filters_orphan_function_calls_from_transcript(self) -> None:
        self._register_agent_and_llm()

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-orphan-tool-call-preview",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        run = self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        session_key = str(run.metadata["session_key"])
        active_session_id = run.active_session_id
        assert active_session_id is not None

        self.container.session_service.append_message(
            AppendSessionMessageInput(
                session_key=session_key,
                session_id=active_session_id,
                role="assistant",
                kind=SessionMessageKind.MESSAGE,
                content_payload={
                    "type": "function_call",
                    "call_id": "orphan-call-1",
                    "name": "echo",
                    "arguments": {"message": "orphan"},
                },
                source_kind="llm_invocation",
                source_id="llm-1",
                metadata={
                    "tool_call_id": "orphan-call-1",
                    "tool_name": "echo",
                },
            ),
        )
        self.container.session_service.append_message(
            AppendSessionMessageInput(
                session_key=session_key,
                session_id=active_session_id,
                role="assistant",
                kind=SessionMessageKind.MESSAGE,
                content_payload={
                    "type": "function_call",
                    "call_id": "paired-call-1",
                    "name": "echo",
                    "arguments": {"message": "paired"},
                },
                source_kind="llm_invocation",
                source_id="llm-1",
                metadata={
                    "tool_call_id": "paired-call-1",
                    "tool_name": "echo",
                },
            ),
        )
        self.container.session_service.append_message(
            AppendSessionMessageInput(
                session_key=session_key,
                session_id=active_session_id,
                role="tool",
                kind=SessionMessageKind.TOOL_RESULT,
                content="paired result",
                content_payload={
                    "tool_name": "echo",
                    "tool_call_id": "paired-call-1",
                    "status": "succeeded",
                    "output": {"echo": "paired"},
                },
                source_kind="tool_run",
                source_id="tool-run-1",
                metadata={
                    "tool_call_id": "paired-call-1",
                    "tool_name": "echo",
                },
            ),
        )

        preview = self.container.orchestration_service.preview_prompt(run.id)
        transcript_function_call_ids = [
            str(message.tool_call_id)
            for message in preview.messages
            if message.role is LlmMessageRole.ASSISTANT
            and isinstance(message.content, dict)
            and message.content.get("type") == "function_call"
        ]
        self.assertEqual(transcript_function_call_ids, ["paired-call-1"])

    def test_recover_abandoned_runs_continues_resolved_approval_recovery(self) -> None:
        self.container.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="local-capability",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
            ),
        )
        self.container.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="writer",
                name="Writer",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Use tools when needed.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(default_llm_id="local-capability"),
            ),
        )

        tool = self.container.tool_service.register(
            RegisterToolInput(
                id="echo",
                name="Echo",
                description="Echoes a message.",
                supported_modes=(ToolMode.INLINE,),
                runtime_key="echo",
                required_effect_ids=("local_tool_access",),
            ),
        )

        async def echo(arguments: dict[str, object]) -> dict[str, object]:
            return {"echo": arguments.get("message")}

        self.container.local_tool_catalog.register(tool, echo)
        adapter = _EffectApprovalAdapter()
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-approval-recovery-contract",
                inbound_instruction=InboundInstruction(source="cli", content="complete the task"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="writer",
                    llm_id="local-capability",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        waiting = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )
        assert waiting is not None
        pending_request = waiting.pending_approval_request()
        assert pending_request is not None

        with patch.object(
            self.container.orchestration_service,
            "_continue_recovery_contract",
            side_effect=lambda run_id: self.container.orchestration_service.get_run(run_id),
        ):
            stalled = self.container.orchestration_service.resolve_approval_request(
                ResolveApprovalRequestInput(
                    run_id=run.id,
                    request_id=pending_request.request_id,
                    decision=ApprovalDecision.ALLOW_ONCE,
                ),
            )

        self.assertEqual(stalled.status, OrchestrationRunStatus.WAITING)
        self.assertEqual(stalled.stage, OrchestrationRunStage.WAITING_FOR_CONFIRMATION)
        recovery_contract = stalled.metadata.get("recovery_contract")
        assert isinstance(recovery_contract, dict)
        self.assertEqual(recovery_contract.get("kind"), "approval")
        self.assertEqual(recovery_contract.get("state"), "resolved_allow_pending_replay")

        recovered = self.container.orchestration_service.recover_abandoned_runs()
        self.assertTrue(any(item.id == run.id for item in recovered))

        resumed = self.container.orchestration_service.get_run(run.id)
        self.assertEqual(resumed.status, OrchestrationRunStatus.QUEUED)
        self.assertEqual(resumed.stage, OrchestrationRunStage.QUEUED)

        completed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )
        assert completed is not None
        self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
        self.assertEqual(completed.result_payload.get("output_text"), "approval flow complete")

    def test_process_next_queued_run_includes_approval_denied_flow_prompt(self) -> None:
        self.container.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="local-capability",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
            ),
        )
        self.container.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="writer",
                name="Writer",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Write carefully.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(
                    default_llm_id="local-capability",
                ),
            ),
        )
        tool = self.container.tool_service.register(
            RegisterToolInput(
                id="echo",
                name="Echo",
                description="Returns the input payload for local inline execution tests.",
                supported_modes=(ToolMode.INLINE,),
                runtime_key="echo",
                required_effect_ids=("local_tool_access",),
            ),
        )

        async def echo(arguments: dict[str, object]) -> dict[str, object]:
            return {"echo": arguments.get("message")}

        self.container.local_tool_catalog.register(tool, echo)
        adapter = _EffectDeniedFallbackAdapter()
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-approval-denied-flow-prompt",
                inbound_instruction=InboundInstruction(source="cli", content="complete the task"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="writer",
                    llm_id="local-capability",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        waiting = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )
        assert waiting is not None
        pending_request = waiting.pending_approval_request()
        assert pending_request is not None

        resumed = self.container.orchestration_service.resolve_approval_request(
            ResolveApprovalRequestInput(
                run_id=run.id,
                request_id=pending_request.request_id,
                decision=ApprovalDecision.DENY,
            ),
        )
        self.assertEqual(resumed.status, OrchestrationRunStatus.QUEUED)

        completed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(completed)
        assert completed is not None
        self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
        self.assertEqual(completed.result_payload["output_text"], "fallback after denial")
        denied_system_messages = [
            message
            for message in adapter.requests[1].messages
            if message.role is LlmMessageRole.SYSTEM
        ]
        self.assertTrue(
            any(
                "# Approval Update" in str(message.content)
                and "denied the requested additional access" in str(message.content)
                for message in denied_system_messages
            ),
        )

    def test_allow_for_agent_persists_auth_rule_without_mutating_agent_profile(self) -> None:
        custom_harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            authorization_enabled=True,
            authorization_policy_paths=(
                str(
                    Path(__file__).resolve().parents[2]
                    / "config"
                    / "authorization_policies"
                    / "default.yaml"
                ),
            ),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        custom_harness.initialize_schema(settings=settings)
        container = custom_harness.build_container(settings=settings)
        try:
            container.llm_service.register_profile(
                RegisterLlmProfileInput(
                    id="local-capability",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4-mini",
                ),
            )
            container.agent_service.register_profile(
                RegisterAgentProfileInput(
                    id="writer",
                    name="Writer",
                    instruction_policy=AgentInstructionPolicy(
                        system_prompt="Use tools when needed.",
                    ),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="local-capability",
                    ),
                ),
            )

            tool = container.tool_service.register(
                RegisterToolInput(
                    id="echo",
                    name="Echo",
                    description="Echoes a message.",
                    supported_modes=(ToolMode.INLINE,),
                    runtime_key="echo",
                    required_effect_ids=("local_tool_access",),
                ),
            )

            async def echo(arguments: dict[str, object]) -> dict[str, object]:
                return {"echo": arguments.get("message")}

            container.local_tool_catalog.register(tool, echo)
            container.llm_adapter_registry.register(
                LlmApiFamily.OPENAI_RESPONSES,
                _EffectApprovalOrVisibleAdapter(),
            )

            run = container.orchestration_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-effect-agent-approval",
                    inbound_instruction=InboundInstruction(
                        source="cli",
                        content="complete the task",
                    ),
                ),
            )
            container.orchestration_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="writer",
                        llm_id="local-capability",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.orchestration_service.enqueue(
                EnqueueOrchestrationRunInput(run_id=run.id),
            )

            waiting = container.orchestration_service.process_next_queued_run(
                worker_id="worker-1",
            )
            assert waiting is not None
            pending_request = waiting.pending_approval_request()
            assert pending_request is not None

            resumed = container.orchestration_service.resolve_approval_request(
                ResolveApprovalRequestInput(
                    run_id=run.id,
                    request_id=pending_request.request_id,
                    decision=ApprovalDecision.ALWAYS_FOR_AGENT,
                ),
            )
            self.assertEqual(resumed.status, OrchestrationRunStatus.QUEUED)

            profile = container.agent_service.get_profile("writer")
            self.assertEqual(profile.tool_preferences.requested_effect_ids, ())
            policies = container.authorization_service.list_policies()
            self.assertTrue(
                any(policy.actions == ("tool.access_effect",) for policy in policies),
            )

            completed = container.orchestration_service.process_next_queued_run(
                worker_id="worker-1",
            )
            assert completed is not None
            self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)

            followup = container.orchestration_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-effect-agent-followup",
                    inbound_instruction=InboundInstruction(
                        source="cli",
                        content="complete the follow-up task",
                    ),
                ),
            )
            followup = container.orchestration_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=followup.id,
                    context=SessionRouteContext(
                        agent_id="writer",
                        llm_id="local-capability",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            resolver = container.orchestration_service.engine.tool_resolver
            resolved = resolver.resolve(followup)

            self.assertIsNotNone(resolved.by_name("echo"))
        finally:
            custom_harness.close()

    def test_process_next_queued_run_heartbeats_dispatch_during_long_execution(self) -> None:
        custom_harness = SqliteTestHarness()
        custom_settings = replace(
            load_settings(),
            orchestration_run_lease_seconds=1,
            orchestration_run_heartbeat_seconds=0.05,
        )
        custom_harness.initialize_schema(settings=custom_settings)
        container = custom_harness.build_container(settings=custom_settings)
        try:
            adapter = _SlowStaticTextAdapter(
                text="slow llm response",
                delay_seconds=0.15,
            )
            container.llm_adapter_registry.register(
                LlmApiFamily.OPENAI_RESPONSES,
                adapter,
            )
            container.llm_service.register_profile(
                RegisterLlmProfileInput(
                    id="openai.gpt-5.4-mini",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4-mini",
                ),
            )
            container.agent_service.register_profile(
                RegisterAgentProfileInput(
                    id="assistant",
                    name="Assistant",
                    instruction_policy=AgentInstructionPolicy(
                        system_prompt="Be helpful and concise.",
                    ),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.gpt-5.4-mini",
                    ),
                ),
            )

            run = container.orchestration_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-heartbeat-loop",
                    inbound_instruction=InboundInstruction(source="cli", content="hello"),
                ),
            )
            container.orchestration_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        llm_id="openai.gpt-5.4-mini",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.orchestration_service.enqueue(
                EnqueueOrchestrationRunInput(run_id=run.id),
            )

            processed = container.orchestration_service.process_next_queued_run(
                worker_id="worker-1",
            )

            self.assertIsNotNone(processed)
            assert processed is not None
            self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
            self.assertIn(
                "dispatch.task.heartbeated",
                [event.name for event in container.event_bus.published_events],
            )
        finally:
            custom_harness.close()

    def test_run_lifecycle_can_advance_wait_resume_and_complete(self) -> None:
        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-lifecycle",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        claimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )
        assert claimed is not None

        advanced = self.container.orchestration_service.advance_run(
            AdvanceOrchestrationRunInput(
                run_id=run.id,
                worker_id="worker-1",
                stage=OrchestrationRunStage.LLM,
                step_increment=1,
            ),
        )
        waiting = self.container.orchestration_service.wait_on_tool(
            WaitOnToolInput(
                run_id=run.id,
                worker_id="worker-1",
                pending_tool_run_ids=("tool-run-1", "tool-run-2"),
                reason="tool_background_wait",
            ),
        )
        resumed = self.container.orchestration_service.resume_run(
            ResumeOrchestrationRunInput(
                run_id=run.id,
                reason="tool_results_ready",
            ),
        )
        reclaimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )
        assert reclaimed is not None
        completed = self.container.orchestration_service.complete_run(
            CompleteOrchestrationRunInput(
                run_id=run.id,
                worker_id="worker-1",
                result_payload={"output": "done"},
            ),
        )

        self.assertEqual(advanced.stage, OrchestrationRunStage.LLM)
        self.assertEqual(advanced.current_step, 1)
        self.assertEqual(waiting.status, OrchestrationRunStatus.WAITING)
        self.assertEqual(waiting.stage, OrchestrationRunStage.WAITING_ON_TOOL)
        self.assertEqual(
            waiting.pending_tool_run_ids,
            ("tool-run-1", "tool-run-2"),
        )
        self.assertEqual(resumed.status, OrchestrationRunStatus.QUEUED)
        self.assertEqual(resumed.stage, OrchestrationRunStage.QUEUED)
        self.assertEqual(resumed.pending_tool_run_ids, ())
        self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
        self.assertEqual(completed.stage, OrchestrationRunStage.COMPLETED)
        self.assertEqual(completed.result_payload, {"output": "done"})
        dispatch_task = self.container.dispatch_service.get_task(run.id)
        self.assertEqual(dispatch_task.status, DispatchTaskStatus.COMPLETED)

    def test_resume_first_queue_policy_claims_before_fifo_with_same_priority(self) -> None:
        waiting = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-resume-first",
                inbound_instruction=InboundInstruction(source="cli", content="resume me"),
                priority=10,
            ),
        )
        fifo = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-fifo",
                inbound_instruction=InboundInstruction(source="cli", content="fifo"),
                priority=10,
            ),
        )

        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=waiting.id,
                agent_id="writer",
                bulk_key="conversation:resume",
                lane_key="bulk:conversation:resume",
            ),
        )
        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=fifo.id,
                agent_id="writer",
                bulk_key="conversation:fifo",
                lane_key="bulk:conversation:fifo",
            ),
        )

        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=waiting.id),
        )
        claimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )
        assert claimed is not None
        self.container.orchestration_service.wait_on_tool(
            WaitOnToolInput(
                run_id=waiting.id,
                worker_id="worker-1",
                pending_tool_run_ids=("tool-run-1",),
            ),
        )

        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=fifo.id),
        )
        resumed = self.container.orchestration_service.resume_run(
            ResumeOrchestrationRunInput(
                run_id=waiting.id,
                queue_policy=OrchestrationQueuePolicy.RESUME_FIRST,
                reason="tool_results_ready",
            ),
        )
        next_claimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-2",
        )

        self.assertEqual(
            resumed.queue_policy,
            OrchestrationQueuePolicy.RESUME_FIRST,
        )
        self.assertIsNotNone(next_claimed)
        assert next_claimed is not None
        self.assertEqual(next_claimed.id, waiting.id)

    def test_jump_queue_claims_before_fifo_with_same_priority(self) -> None:
        fifo = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-fifo",
                inbound_instruction=InboundInstruction(source="cli", content="fifo"),
                priority=10,
            ),
        )
        jump_queue = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-jump-queue",
                inbound_instruction=InboundInstruction(
                    source="cli",
                    content="jump queue",
                ),
                priority=10,
                queue_policy=OrchestrationQueuePolicy.JUMP_QUEUE,
            ),
        )

        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=fifo.id,
                agent_id="writer",
                bulk_key="conversation:fifo",
                lane_key="bulk:conversation:fifo",
            ),
        )
        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=jump_queue.id,
                agent_id="writer",
                bulk_key="conversation:jump",
                lane_key="bulk:conversation:jump",
            ),
        )

        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=fifo.id),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=jump_queue.id),
        )

        claimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed.id, jump_queue.id)

    def test_resume_first_claims_before_jump_queue_with_same_priority(self) -> None:
        resume_first = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-resume-first-priority",
                inbound_instruction=InboundInstruction(
                    source="cli",
                    content="resume first",
                ),
                priority=10,
                queue_policy=OrchestrationQueuePolicy.RESUME_FIRST,
            ),
        )
        jump_queue = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-jump-queue-priority",
                inbound_instruction=InboundInstruction(
                    source="cli",
                    content="jump queue",
                ),
                priority=10,
                queue_policy=OrchestrationQueuePolicy.JUMP_QUEUE,
            ),
        )

        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=resume_first.id,
                agent_id="writer",
                bulk_key="conversation:resume-first",
                lane_key="bulk:conversation:resume-first",
            ),
        )
        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=jump_queue.id,
                agent_id="writer",
                bulk_key="conversation:jump-queue",
                lane_key="bulk:conversation:jump-queue",
            ),
        )

        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=jump_queue.id),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=resume_first.id),
        )

        claimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed.id, resume_first.id)

    def test_lane_jump_queue_claims_before_fifo_with_same_priority_in_same_lane(self) -> None:
        fifo = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-lane-fifo",
                inbound_instruction=InboundInstruction(source="cli", content="fifo"),
                priority=10,
            ),
        )
        lane_jump_queue = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-lane-jump",
                inbound_instruction=InboundInstruction(
                    source="cli",
                    content="lane jump queue",
                ),
                priority=10,
                queue_policy=OrchestrationQueuePolicy.LANE_JUMP_QUEUE,
            ),
        )

        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=fifo.id,
                agent_id="writer",
                bulk_key="conversation:lane-shared",
                lane_key="bulk:conversation:lane-shared",
            ),
        )
        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=lane_jump_queue.id,
                agent_id="writer",
                bulk_key="conversation:lane-shared",
                lane_key="bulk:conversation:lane-shared",
            ),
        )

        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=fifo.id),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=lane_jump_queue.id),
        )

        claimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed.id, lane_jump_queue.id)

    def test_lane_jump_queue_does_not_jump_ahead_of_other_lane_heads(self) -> None:
        other_lane_fifo = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-other-lane-fifo",
                inbound_instruction=InboundInstruction(
                    source="cli",
                    content="other lane fifo",
                ),
                priority=10,
            ),
        )
        same_lane_fifo = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-shared-lane-fifo",
                inbound_instruction=InboundInstruction(
                    source="cli",
                    content="shared lane fifo",
                ),
                priority=10,
            ),
        )
        lane_jump_queue = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-shared-lane-jump",
                inbound_instruction=InboundInstruction(
                    source="cli",
                    content="shared lane jump",
                ),
                priority=10,
                queue_policy=OrchestrationQueuePolicy.LANE_JUMP_QUEUE,
            ),
        )

        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=other_lane_fifo.id,
                agent_id="writer",
                bulk_key="conversation:lane-a",
                lane_key="bulk:conversation:lane-a",
            ),
        )
        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=same_lane_fifo.id,
                agent_id="writer",
                bulk_key="conversation:lane-b",
                lane_key="bulk:conversation:lane-b",
            ),
        )
        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=lane_jump_queue.id,
                agent_id="writer",
                bulk_key="conversation:lane-b",
                lane_key="bulk:conversation:lane-b",
            ),
        )

        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=other_lane_fifo.id),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=same_lane_fifo.id),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=lane_jump_queue.id),
        )

        claimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed.id, other_lane_fifo.id)

    def test_waiting_run_can_fail_without_reclaim(self) -> None:
        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-fail",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )
        claimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )
        assert claimed is not None
        self.container.orchestration_service.wait_on_tool(
            WaitOnToolInput(
                run_id=run.id,
                worker_id="worker-1",
                pending_tool_run_ids=("tool-run-1",),
            ),
        )

        failed = self.container.orchestration_service.fail_run(
            FailOrchestrationRunInput(
                run_id=run.id,
                worker_id=None,
                message="tool background failed",
                code="tool_failed",
                details={"tool_run_id": "tool-run-1"},
            ),
        )

        self.assertEqual(failed.status, OrchestrationRunStatus.FAILED)
        self.assertEqual(failed.stage, OrchestrationRunStage.FAILED)
        assert failed.error is not None
        self.assertEqual(failed.error.code, "tool_failed")
        self.assertEqual(
            failed.error.details["tool_run_id"],
            "tool-run-1",
        )

    def test_orchestration_resolves_session_bundle_via_router_and_session_resolver(self) -> None:
        bundle = self.container.orchestration_service.resolve_session_bundle(
            ResolveSessionBundleInput(
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    label="browser",
                    surface="chat",
                    direct_scope=DirectSessionScope.MAIN,
                    metadata={"scope": "main"},
                ),
                ensure=True,
            ),
        )

        self.assertEqual(bundle.routing.key_resolution.key, "agent:assistant:main")
        self.assertEqual(
            bundle.routing.bulk_key,
            "conversation:main:webchat:default:main",
        )
        self.assertEqual(
            bundle.routing.lane_key,
            "bulk:conversation:main:webchat:default:main",
        )
        self.assertTrue(bundle.resolution.resolution.created)
        self.assertIsNotNone(bundle.session)
        self.assertIsNotNone(bundle.active_instance)
        assert bundle.session is not None
        assert bundle.active_instance is not None
        self.assertEqual(bundle.session.id, "agent:assistant:main")
        self.assertEqual(bundle.active_instance.kind.value, "main")

    def test_process_next_queued_run_completes_minimal_llm_loop(self) -> None:
        adapter = _StaticTextAdapter(text="hello from fake llm")
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-process",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        processed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
        self.assertEqual(processed.stage, OrchestrationRunStage.COMPLETED)
        self.assertEqual(processed.current_step, 1)
        assert processed.result_payload is not None
        self.assertEqual(processed.result_payload["output_text"], "hello from fake llm")
        self.assertEqual(
            processed.result_payload["llm_id"],
            "openai.gpt-5.4-mini",
        )
        self.assertEqual(processed.worker_id, "worker-1")

        self.assertEqual(len(adapter.requests), 1)
        self.assertEqual(adapter.requests[0].messages[0].role, LlmMessageRole.SYSTEM)
        self.assertEqual(
            adapter.requests[0].messages[0].content,
            "Be helpful and concise.",
        )
        self.assertEqual(adapter.requests[0].messages[1].role, LlmMessageRole.SYSTEM)
        self.assertIn("# Runtime Context", str(adapter.requests[0].messages[1].content))
        self.assertEqual(adapter.requests[0].messages[-1].role, LlmMessageRole.USER)
        self.assertEqual(adapter.requests[0].messages[-1].content, "hello")

        session_messages = self.container.session_service.list_messages(
            ListSessionMessagesInput(
                session_key="agent:assistant:main",
                active_session_only=True,
            ),
        )
        self.assertEqual([message.role for message in session_messages], ["user", "assistant"])
        self.assertEqual(session_messages[0].source_kind, "orchestration_run")
        self.assertEqual(session_messages[0].source_id, run.id)
        self.assertEqual(session_messages[1].source_kind, "llm_invocation")

    def test_process_next_queued_run_scales_system_budget_to_llm_context_window(
        self,
    ) -> None:
        adapter = _StaticTextAdapter(text="hello from fake llm")
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self.container.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="small-window",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-small",
                context_window_tokens=2_000,
            ),
        )
        self.container.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="assistant",
                name="Assistant",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="A" * 20_000,
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(default_llm_id="small-window"),
                runtime_preferences=AgentRuntimePreferences(),
            ),
        )

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-small-window-budget",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="small-window",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        processed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        prompt_report = processed.metadata["prompt_report"]
        self.assertEqual(prompt_report["system_budget"]["source"], "context_window_scaled")
        self.assertEqual(prompt_report["system_budget"]["max_estimated_tokens"], 300)
        self.assertEqual(prompt_report["system_budget"]["llm_context_window_tokens"], 2_000)
        self.assertLessEqual(prompt_report["system"]["estimated_tokens"], 300)
        self.assertTrue(
            any(
                block["kind"] == "agent_instruction" and block["truncated"]
                for block in prompt_report["system_blocks"]
            ),
        )

    def test_process_next_queued_run_injects_agents_workspace_context(self) -> None:
        adapter = _StaticTextAdapter(text="hello from fake llm")
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        with tempfile.TemporaryDirectory() as tempdir:
            workspace = Path(tempdir)
            (workspace / "AGENTS.md").write_text(
                "# AGENTS.md\n\nFollow workspace conventions.\n",
                encoding="utf-8",
            )
            (workspace / "SOUL.md").write_text(
                "Respond with calm confidence.\n",
                encoding="utf-8",
            )
            (workspace / "TOOLS.md").write_text(
                "Prefer tools when grounded facts are needed.\n",
                encoding="utf-8",
            )
            self._register_agent_and_llm(
                runtime_preferences=AgentRuntimePreferences(workspace=str(workspace)),
            )

            run = self.container.orchestration_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-workspace-context",
                    inbound_instruction=InboundInstruction(source="cli", content="hello"),
                ),
            )
            self.container.orchestration_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        llm_id="openai.gpt-5.4-mini",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            self.container.orchestration_service.enqueue(
                EnqueueOrchestrationRunInput(run_id=run.id),
            )

            processed = self.container.orchestration_service.process_next_queued_run(
                worker_id="worker-1",
            )

            self.assertIsNotNone(processed)
            self.assertEqual(len(adapter.requests), 1)
            messages = adapter.requests[0].messages
            self.assertGreaterEqual(len(messages), 4)
            system_messages = [
                message
                for message in messages
                if message.role is LlmMessageRole.SYSTEM
            ]
            self.assertEqual(str(system_messages[0].content), "Be helpful and concise.")
            self.assertIn("# Runtime Context", str(system_messages[1].content))
            self.assertIn("- Agent: assistant", str(system_messages[1].content))
            self.assertIn("- Model: openai.gpt-5.4-mini", str(system_messages[1].content))
            self.assertIn("# Session Start", str(system_messages[2].content))
            self.assertIn("# Agent Home Context", str(system_messages[3].content))
            self.assertIn("## AGENTS.md", str(system_messages[3].content))
            self.assertIn("Follow workspace conventions.", str(system_messages[3].content))
            self.assertIn("## SOUL.md", str(system_messages[3].content))
            self.assertIn("Respond with calm confidence.", str(system_messages[3].content))
            self.assertIn("## TOOLS.md", str(system_messages[3].content))
            self.assertIn(
                "Prefer tools when grounded facts are needed.",
                str(system_messages[3].content),
            )
            self.assertIn(
                f"- Agent home / workdir: {workspace}",
                str(system_messages[1].content),
            )
            self.assertEqual(processed.metadata["prompt_mode"], "session_start")
            self.assertEqual(processed.metadata["prompt_report"]["mode"], "session_start")
            self.assertEqual(
                [block["kind"] for block in processed.metadata["prompt_report"]["system_blocks"]],
                ["agent_instruction", "runtime_context", "flow_prompt", "project_context"],
            )
            self.assertGreater(
                processed.metadata["prompt_report"]["system"]["estimated_tokens"],
                0,
            )
            self.assertGreater(
                processed.metadata["prompt_report"]["transcript"]["estimated_tokens"],
                0,
            )
            self.assertEqual(processed.metadata["workspace_context_workspace"], str(workspace))
            self.assertIn(
                {"path": "AGENTS.md", "chars": len("# AGENTS.md\n\nFollow workspace conventions.")},
                processed.metadata["workspace_context_files"],
            )
            self.assertIn(
                {"path": "SOUL.md", "chars": len("Respond with calm confidence.")},
                processed.metadata["workspace_context_files"],
            )
            self.assertIn(
                {
                    "path": "TOOLS.md",
                    "chars": len("Prefer tools when grounded facts are needed."),
                },
                processed.metadata["workspace_context_files"],
            )
            self.assertEqual(messages[-1].role, LlmMessageRole.USER)
            self.assertEqual(messages[-1].content, "hello")

    def test_process_next_queued_run_extracts_pending_memory_candidate(self) -> None:
        adapter = _StaticTextAdapter(
            text=(
                "Use effect-based approvals as the default human-facing approval unit, "
                "and keep tool-level overrides only for explicit exceptions."
            ),
        )
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-memory-candidate",
                inbound_instruction=InboundInstruction(
                    source="cli",
                    content="What should our approval model look like?",
                ),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        processed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )

        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
        self.assertEqual(processed.metadata["memory_candidate_count"], 1)
        self.assertEqual(len(processed.metadata["memory_candidate_ids"]), 1)

        candidates = self.container.memory_service.list_candidates()
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].run_id, run.id)
        self.assertEqual(candidates[0].agent_id, "assistant")
        self.assertIn(
            "What should our approval model look like?",
            candidates[0].content,
        )
        self.assertIn(
            "effect-based approvals",
            candidates[0].summary,
        )

    def test_process_next_queued_run_injects_recalled_memory(self) -> None:
        memory_candidate = self.container.memory_service.create_candidate(
            CreateMemoryCandidateInput(
                agent_id="assistant",
                title="Approval model",
                content="Use effect-based approvals as the default human-facing approval unit.",
                summary="Effect-based approvals are the default approval unit.",
                tags=("approval", "design"),
            ),
        )
        self.container.memory_service.approve_candidate(
            ApproveMemoryCandidateInput(candidate_id=memory_candidate.id),
        )

        adapter = _StaticTextAdapter(text="approval answer from recalled memory")
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-memory-recall",
                inbound_instruction=InboundInstruction(
                    source="cli",
                    content="How should our approval model work?",
                ),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        processed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )

        assert processed is not None
        self.assertEqual(len(adapter.requests), 1)
        system_messages = [
            message
            for message in adapter.requests[0].messages
            if message.role is LlmMessageRole.SYSTEM
        ]
        memory_lookup_message = next(
            message for message in system_messages
            if "Durable memory is available for this agent." in str(message.content)
        )
        recalled_memory_message = next(
            message for message in system_messages
            if "# Recalled Memory" in str(message.content)
        )
        self.assertIn("Durable memory is available for this agent.", str(memory_lookup_message.content))
        self.assertIn("# Recalled Memory", str(recalled_memory_message.content))
        self.assertIn("Approval model", str(recalled_memory_message.content))
        self.assertIn(
            "effect-based approvals",
            str(recalled_memory_message.content).lower(),
        )
        system_block_kinds = [
            block["kind"] for block in processed.metadata["prompt_report"]["system_blocks"]
        ]
        self.assertEqual(
            system_block_kinds,
            [
                "agent_instruction",
                "runtime_context",
                "flow_prompt",
                "project_context",
                "memory_lookup_guidance",
                "recalled_memory",
            ],
        )

    def test_process_next_queued_run_uses_memory_lookup_guidance_without_auto_recall_on_normal_turn(
        self,
    ) -> None:
        memory_candidate = self.container.memory_service.create_candidate(
            CreateMemoryCandidateInput(
                agent_id="assistant",
                title="Approval model",
                content="Use effect-based approvals as the default human-facing approval unit.",
                summary="Effect-based approvals are the default approval unit.",
                tags=("approval", "design"),
            ),
        )
        self.container.memory_service.approve_candidate(
            ApproveMemoryCandidateInput(candidate_id=memory_candidate.id),
        )

        adapter = _SequentialTextAdapter("hello from session start", "normal turn answer")
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        first_run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-memory-normal-turn-initial",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=first_run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=first_run.id),
        )
        self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-memory-normal-turn-followup",
                inbound_instruction=InboundInstruction(
                    source="cli",
                    content="How should our approval model work?",
                ),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        processed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )

        assert processed is not None
        self.assertEqual(processed.metadata["prompt_mode"], "normal_turn")
        self.assertEqual(
            [block["kind"] for block in processed.metadata["prompt_report"]["system_blocks"]],
            [
                "agent_instruction",
                "runtime_context",
                "project_context",
                "memory_lookup_guidance",
            ],
        )

    def test_process_next_queued_run_can_search_and_get_memory_then_continue(
        self,
    ) -> None:
        workspace_dir = tempfile.TemporaryDirectory()
        self.addCleanup(workspace_dir.cleanup)
        self._register_agent_and_llm(
            runtime_preferences=AgentRuntimePreferences(workspace=workspace_dir.name),
        )
        memory_candidate = self.container.memory_service.create_candidate(
            CreateMemoryCandidateInput(
                agent_id="assistant",
                title="Approval model",
                content="Use effect-based approvals as the default human-facing approval unit.",
                summary="Effect-based approvals are the default approval unit.",
                tags=("approval", "design"),
            ),
        )
        memory_entry = self.container.memory_service.approve_candidate(
            ApproveMemoryCandidateInput(candidate_id=memory_candidate.id),
        )

        adapter = _MemorySearchAndGetAdapter(entry_id=memory_entry.id)
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-memory-search-get",
                inbound_instruction=InboundInstruction(
                    source="cli",
                    content="Remind me how our approval model should work.",
                ),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        completed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(completed)
        assert completed is not None
        self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
        assert completed.result_payload is not None
        self.assertEqual(completed.result_payload["output_text"], "memory-guided answer")
        self.assertEqual(len(adapter.requests), 3)

        search_tool_messages = [
            message
            for message in adapter.requests[1].messages
            if message.role is LlmMessageRole.TOOL and message.name == "memory_search"
        ]
        self.assertEqual(len(search_tool_messages), 1)
        self.assertIn(
            "# Memory Search Results",
            str(search_tool_messages[0].content),
        )
        self.assertIn(memory_entry.id, str(search_tool_messages[0].content))
        self.assertIn("- citation: memory/", str(search_tool_messages[0].content))
        self.assertIn("- snippet:", str(search_tool_messages[0].content))

        get_tool_messages = [
            message
            for message in adapter.requests[2].messages
            if message.role is LlmMessageRole.TOOL and message.name == "memory_get"
        ]
        self.assertEqual(len(get_tool_messages), 1)
        self.assertIn(
            "# Memory Entry",
            str(get_tool_messages[0].content),
        )
        self.assertIn("Citation: memory/", str(get_tool_messages[0].content))
        self.assertIn(
            "effect-based approvals",
            str(get_tool_messages[0].content).lower(),
        )

        session_messages = self.container.session_service.list_messages(
            ListSessionMessagesInput(
                session_key="agent:assistant:main",
                active_session_only=True,
            ),
        )
        memory_results = [
            message
            for message in session_messages
            if message.source_kind == "tool_run"
            and message.metadata.get("tool_name") in {"memory_search", "memory_get"}
        ]
        self.assertEqual(len(memory_results), 2)
        self.assertEqual(memory_results[0].metadata["tool_name"], "memory_search")
        self.assertEqual(memory_results[1].metadata["tool_name"], "memory_get")

    def test_process_next_queued_run_includes_session_start_flow_prompt(self) -> None:
        adapter = _StaticTextAdapter(text="hello from new session")
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-session-start-flow-prompt",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        processed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
        self.assertEqual(processed.metadata["prompt_mode"], "session_start")
        session_start_system_messages = [
            message
            for message in adapter.requests[0].messages
            if message.role is LlmMessageRole.SYSTEM
        ]
        self.assertTrue(
            any(
                "# Session Start" in str(message.content)
                and "new active session" in str(message.content)
                for message in session_start_system_messages
            ),
        )

    def test_process_next_queued_run_includes_compaction_flow_prompt(self) -> None:
        adapter = _StaticTextAdapter(text="compacted summary")
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-compaction-flow-prompt",
                inbound_instruction=InboundInstruction(
                    source="cli",
                    content="compact the current session",
                ),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        with self.container.uow_factory() as uow:
            current = uow.orchestration_runs.get(run.id)
            assert current is not None
            current.metadata["prompt_flow_hint"] = {
                "mode": "compaction",
                "reason": "context budget exceeded",
                "preserve": "open tasks, approvals, and user preferences",
            }
            uow.orchestration_runs.add(current)
            uow.commit()
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        processed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
        self.assertEqual(processed.metadata["prompt_mode"], "compaction")
        compaction_system_messages = [
            message
            for message in adapter.requests[0].messages
            if message.role is LlmMessageRole.SYSTEM
        ]
        self.assertTrue(
            any(
                "# Compaction" in str(message.content)
                and "compacting the current session context" in str(message.content)
                and "Preserve explicitly: open tasks, approvals, and user preferences"
                in str(message.content)
                for message in compaction_system_messages
            ),
        )

    def test_request_heartbeat_processes_with_heartbeat_flow_prompt(self) -> None:
        adapter = _SequentialTextAdapter("initial answer", "HEARTBEAT_OK")
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        initial = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-initial-for-heartbeat",
                inbound_instruction=InboundInstruction(source="cli", content="first task"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=initial.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=initial.id),
        )
        self.container.orchestration_service.process_next_queued_run(worker_id="worker-1")

        heartbeat = self.container.orchestration_service.request_heartbeat(
            RequestHeartbeatInput(
                anchor_run_id=initial.id,
                reason="scheduled_check",
            ),
        )
        self.assertEqual(heartbeat.inbound_instruction.source, "heartbeat")
        self.assertEqual(heartbeat.metadata["prompt_flow_hint"]["mode"], "heartbeat")
        self.assertEqual(heartbeat.metadata["heartbeat_request"]["basis"], "manual")

        processed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
        self.assertEqual(processed.metadata["prompt_mode"], "heartbeat")
        heartbeat_system_messages = [
            message
            for message in adapter.requests[-1].messages
            if message.role is LlmMessageRole.SYSTEM
        ]
        self.assertTrue(
            any(
                "# Heartbeat" in str(message.content)
                and "lightweight heartbeat check" in str(message.content)
                and "Default idle reply: HEARTBEAT_OK" in str(message.content)
                for message in heartbeat_system_messages
            ),
        )
        self.assertEqual(
            [schema.name for schema in adapter.requests[-1].tool_schemas],
            [],
        )
        self.assertNotIn("memory_candidate_count", processed.metadata)

    def test_heartbeat_prompt_mode_policy_hides_memory_tools_when_auth_is_enabled(
        self,
    ) -> None:
        harness = SqliteTestHarness()
        settings = replace(load_settings(), authorization_enabled=True)
        container = harness.build_container(settings=settings)
        self.addCleanup(container.close)
        self.addCleanup(harness.close)

        adapter = _SequentialTextAdapter("initial answer", "HEARTBEAT_OK")
        container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        container.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="openai.gpt-5.4-mini",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
            ),
        )
        workspace_dir = tempfile.TemporaryDirectory()
        self.addCleanup(workspace_dir.cleanup)
        container.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="assistant",
                name="Assistant",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Be helpful and concise.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(
                    default_llm_id="openai.gpt-5.4-mini",
                ),
                runtime_preferences=AgentRuntimePreferences(
                    workspace=workspace_dir.name,
                ),
            ),
        )
        memory_candidate = container.memory_service.create_candidate(
            CreateMemoryCandidateInput(
                agent_id="assistant",
                title="Approval model",
                content="Use effect-based approvals as the default human-facing approval unit.",
                summary="Effect-based approvals are the default approval unit.",
            ),
        )
        container.memory_service.approve_candidate(
            ApproveMemoryCandidateInput(candidate_id=memory_candidate.id),
        )

        initial = container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-auth-heartbeat-initial",
                inbound_instruction=InboundInstruction(source="cli", content="first task"),
            ),
        )
        container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=initial.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=initial.id),
        )
        container.orchestration_service.process_next_queued_run(worker_id="worker-1")

        heartbeat = container.orchestration_service.request_heartbeat(
            RequestHeartbeatInput(
                anchor_run_id=initial.id,
                reason="scheduled_check",
            ),
        )
        processed = container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(heartbeat.metadata["prompt_flow_hint"]["mode"], "heartbeat")
        self.assertEqual(processed.metadata["prompt_mode"], "heartbeat")
        self.assertEqual(
            [schema.name for schema in adapter.requests[-1].tool_schemas],
            [],
        )

    def test_request_memory_flush_records_durable_memory_without_transcript_reply(
        self,
    ) -> None:
        adapter = _SequentialTextAdapter(
            "initial answer",
            "# Durable Memory\n\nKeep effect approvals as the default path for risky actions.",
        )
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        workspace_dir = tempfile.TemporaryDirectory()
        self.addCleanup(workspace_dir.cleanup)
        self._register_agent_and_llm(
            runtime_preferences=AgentRuntimePreferences(workspace=workspace_dir.name),
        )

        initial = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-initial-for-memory-flush",
                inbound_instruction=InboundInstruction(source="cli", content="first task"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=initial.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=initial.id),
        )
        initial_completed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )
        assert initial_completed is not None

        session_key = str(initial_completed.metadata["session_key"])
        messages_before = self.container.session_service.list_messages(
            ListSessionMessagesInput(
                session_key=session_key,
                active_session_only=True,
            ),
        )
        entries_before = self.container.memory_service.list_entries(
            ListMemoryEntriesInput(agent_id="assistant"),
        )

        flush = self.container.orchestration_service.request_memory_flush(
            RequestMemoryFlushInput(
                anchor_run_id=initial.id,
                reason="manual memory flush",
            ),
        )
        self.assertEqual(flush.inbound_instruction.source, "memory_flush")
        self.assertEqual(flush.metadata["prompt_flow_hint"]["mode"], "memory_flush")
        self.assertEqual(flush.metadata["memory_flush_request"]["basis"], "manual")

        flushed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )
        self.assertIsNotNone(flushed)
        assert flushed is not None
        self.assertEqual(flushed.status, OrchestrationRunStatus.COMPLETED)
        self.assertEqual(flushed.metadata["prompt_mode"], "memory_flush")
        self.assertNotIn("assistant_message_id", flushed.result_payload or {})
        self.assertEqual(flushed.metadata["memory_flush_result"]["skipped"], False)
        self.assertEqual(
            flushed.metadata["memory_flush_result"]["title"],
            "Durable Memory",
        )
        self.assertEqual(
            [schema.name for schema in adapter.requests[-1].tool_schemas],
            [],
        )
        self.assertNotIn("memory_candidate_count", flushed.metadata)

        messages_after = self.container.session_service.list_messages(
            ListSessionMessagesInput(
                session_key=session_key,
                active_session_only=True,
            ),
        )
        self.assertEqual([item.id for item in messages_after], [item.id for item in messages_before])

        memory_entries = self.container.memory_service.list_entries(
            ListMemoryEntriesInput(agent_id="assistant"),
        )
        self.assertEqual(len(memory_entries), len(entries_before) + 1)
        flushed_entry = next(
            entry for entry in memory_entries if entry.run_id == flushed.id
        )
        self.assertEqual(flushed_entry.metadata["kind"], "memory_flush")

    def test_memory_flush_skip_token_does_not_record_durable_memory(self) -> None:
        adapter = _SequentialTextAdapter("initial answer", "NO_MEMORY_FLUSH")
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        workspace_dir = tempfile.TemporaryDirectory()
        self.addCleanup(workspace_dir.cleanup)
        self._register_agent_and_llm(
            runtime_preferences=AgentRuntimePreferences(workspace=workspace_dir.name),
        )

        initial = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-initial-for-memory-flush-skip",
                inbound_instruction=InboundInstruction(source="cli", content="first task"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=initial.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=initial.id),
        )
        self.container.orchestration_service.process_next_queued_run(worker_id="worker-1")

        self.container.orchestration_service.request_memory_flush(
            RequestMemoryFlushInput(anchor_run_id=initial.id),
        )
        entries_before = self.container.memory_service.list_entries(
            ListMemoryEntriesInput(agent_id="assistant"),
        )
        flushed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )

        assert flushed is not None
        self.assertEqual(flushed.metadata["memory_flush_result"]["skipped"], True)
        self.assertEqual(
            flushed.metadata["memory_flush_result"]["reason"],
            "no_memory_flush",
        )
        self.assertEqual(
            len(
                self.container.memory_service.list_entries(
                    ListMemoryEntriesInput(agent_id="assistant"),
                ),
            ),
            len(entries_before),
        )

    def test_request_due_heartbeats_enqueues_idle_session_once(self) -> None:
        adapter = _SequentialTextAdapter("initial answer", "HEARTBEAT_OK")
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        initial = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-initial-for-due-heartbeat",
                inbound_instruction=InboundInstruction(source="cli", content="first task"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=initial.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=initial.id),
        )
        self.container.orchestration_service.process_next_queued_run(worker_id="worker-1")

        with self.container.session_service.uow_factory() as uow:
            session = uow.sessions.get("agent:assistant:main")
            assert session is not None
            session.updated_at = datetime.now(timezone.utc) - timedelta(minutes=10)
            uow.sessions.add(session)
            uow.commit()

        requested = self.container.orchestration_service.request_due_heartbeats(
            RequestDueHeartbeatsInput(
                idle_seconds=60,
                limit=5,
            ),
        )
        self.assertEqual(len(requested), 1)
        self.assertEqual(requested[0].metadata["prompt_flow_hint"]["mode"], "heartbeat")
        self.assertEqual(requested[0].metadata["heartbeat_request"]["basis"], "idle_session")
        self.assertEqual(
            requested[0].metadata["heartbeat_request"]["details"]["idle_seconds"],
            60,
        )

        requested_again = self.container.orchestration_service.request_due_heartbeats(
            RequestDueHeartbeatsInput(
                idle_seconds=60,
                limit=5,
            ),
        )
        self.assertEqual(requested_again, [])

    def test_request_compaction_archives_prior_messages_and_future_prompt_uses_summary(self) -> None:
        adapter = _SequentialTextAdapter(
            "initial answer",
            "compacted summary",
            "follow-up answer",
        )
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        initial = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-initial-for-compaction",
                inbound_instruction=InboundInstruction(source="cli", content="first task"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=initial.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=initial.id),
        )
        initial_completed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )
        assert initial_completed is not None

        compaction = self.container.orchestration_service.request_compaction(
            RequestCompactionInput(
                anchor_run_id=initial.id,
                reason="manual compaction",
                preserve="open tasks and constraints",
            ),
        )
        compaction_completed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(compaction_completed)
        assert compaction_completed is not None
        self.assertEqual(compaction_completed.metadata["prompt_mode"], "compaction")
        self.assertGreaterEqual(
            compaction_completed.metadata["compaction_result"]["archived_message_count"],
            2,
        )

        session_messages = self.container.session_service.list_messages(
            ListSessionMessagesInput(
                session_key="agent:assistant:main",
                active_session_only=True,
            ),
        )
        archived_messages = [
            message for message in session_messages if message.visibility.value == "archived"
        ]
        visible_messages = [
            message for message in session_messages if message.visibility.value != "archived"
        ]
        self.assertGreaterEqual(len(archived_messages), 2)
        self.assertEqual(
            [message.content for message in visible_messages if message.role == "assistant"][-1],
            "compacted summary",
        )

        followup = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-followup-after-compaction",
                inbound_instruction=InboundInstruction(source="cli", content="what next?"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=followup.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=followup.id),
        )
        self.container.orchestration_service.process_next_queued_run(worker_id="worker-1")

        followup_request = adapter.requests[-1]
        transcript_contents = [
            str(message.content)
            for message in followup_request.messages
            if message.role in {LlmMessageRole.USER, LlmMessageRole.ASSISTANT}
        ]
        self.assertIn("compacted summary", transcript_contents)
        self.assertIn("what next?", transcript_contents)
        self.assertNotIn("first task", transcript_contents)
        self.assertNotIn("initial answer", transcript_contents)
        self.assertEqual(adapter.requests[1].tool_schemas, ())

    def test_completed_normal_turn_auto_requests_compaction_when_transcript_budget_is_exceeded(
        self,
    ) -> None:
        custom_harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
            orchestration_auto_compaction_enabled=True,
            orchestration_auto_compaction_transcript_chars=20,
            orchestration_auto_compaction_transcript_tokens=5,
        )
        custom_harness.initialize_schema(settings=settings)
        container = custom_harness.build_container(settings=settings)
        try:
            adapter = _SequentialTextAdapter(
                "hello start",
                (
                    "This is a long follow-up answer that should exceed the transcript "
                    "budget and automatically queue a compaction run."
                ),
                "compacted summary",
            )
            container.llm_adapter_registry.register(
                LlmApiFamily.OPENAI_RESPONSES,
                adapter,
            )
            container.llm_service.register_profile(
                RegisterLlmProfileInput(
                    id="openai.gpt-5.4-mini",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4-mini",
                ),
            )
            container.agent_service.register_profile(
                RegisterAgentProfileInput(
                    id="assistant",
                    name="Assistant",
                    instruction_policy=AgentInstructionPolicy(
                        system_prompt="Be helpful and concise.",
                    ),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.gpt-5.4-mini",
                    ),
                ),
            )

            initial = container.orchestration_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-auto-compaction-initial",
                    inbound_instruction=InboundInstruction(source="cli", content="hello"),
                ),
            )
            container.orchestration_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=initial.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        llm_id="openai.gpt-5.4-mini",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.orchestration_service.enqueue(
                EnqueueOrchestrationRunInput(run_id=initial.id),
            )
            container.orchestration_service.process_next_queued_run(worker_id="worker-1")

            followup = container.orchestration_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-auto-compaction-followup",
                    inbound_instruction=InboundInstruction(
                        source="cli",
                        content="Please continue with more detail.",
                    ),
                ),
            )
            container.orchestration_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=followup.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        llm_id="openai.gpt-5.4-mini",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.orchestration_service.enqueue(
                EnqueueOrchestrationRunInput(run_id=followup.id),
            )

            completed = container.orchestration_service.process_next_queued_run(
                worker_id="worker-1",
            )
            self.assertIsNotNone(completed)
            assert completed is not None
            self.assertEqual(completed.metadata["prompt_mode"], "normal_turn")

            queued_runs = container.orchestration_service.list_runs(
                status=OrchestrationRunStatus.QUEUED,
            )
            compaction_runs = [
                run
                for run in queued_runs
                if run.inbound_instruction.source == "compaction"
            ]
            self.assertEqual(len(compaction_runs), 1)
            compaction_run = compaction_runs[0]
            self.assertEqual(
                compaction_run.metadata["prompt_flow_hint"]["mode"],
                "compaction",
            )
            self.assertEqual(
                compaction_run.metadata["compaction_request"]["basis"],
                "transcript_budget",
            )
            self.assertEqual(
                compaction_run.metadata["compaction_request"]["details"]["transcript_char_threshold"],
                20,
            )

            session = container.session_service.get_session("agent:assistant:main")
            self.assertEqual(
                session.metadata["compaction"]["pending_run_id"],
                compaction_run.id,
            )
            self.assertEqual(
                session.metadata["compaction"]["trigger_basis"],
                "transcript_budget",
            )

            compacted = container.orchestration_service.process_next_queued_run(
                worker_id="worker-1",
            )
            self.assertIsNotNone(compacted)
            assert compacted is not None
            self.assertEqual(compacted.metadata["prompt_mode"], "compaction")

            refreshed_session = container.session_service.get_session("agent:assistant:main")
            self.assertEqual(
                refreshed_session.metadata["compaction"]["run_id"],
                compacted.id,
            )
            self.assertNotIn(
                "pending_run_id",
                refreshed_session.metadata["compaction"],
            )
        finally:
            custom_harness.close()

    def test_completed_normal_turn_auto_requests_compaction_when_prompt_budget_is_exceeded(
        self,
    ) -> None:
        custom_harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
            orchestration_auto_compaction_enabled=True,
            orchestration_auto_compaction_transcript_chars=999_999,
            orchestration_auto_compaction_transcript_tokens=999_999,
            orchestration_auto_compaction_reserve_tokens=200,
            orchestration_auto_compaction_soft_threshold_tokens=100,
        )
        custom_harness.initialize_schema(settings=settings)
        container = custom_harness.build_container(settings=settings)
        try:
            adapter = _StaticTextAdapter(text="short reply")
            container.llm_adapter_registry.register(
                LlmApiFamily.OPENAI_RESPONSES,
                adapter,
            )
            container.llm_service.register_profile(
                RegisterLlmProfileInput(
                    id="openai.gpt-5.4-mini",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4-mini",
                    context_window_tokens=1_000,
                ),
            )
            container.agent_service.register_profile(
                RegisterAgentProfileInput(
                    id="assistant",
                    name="Assistant",
                    instruction_policy=AgentInstructionPolicy(
                        system_prompt="Be helpful and concise.",
                    ),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.gpt-5.4-mini",
                    ),
                ),
            )

            initial = container.orchestration_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-auto-prompt-threshold-initial",
                    inbound_instruction=InboundInstruction(
                        source="cli",
                        content="X" * 3_200,
                    ),
                ),
            )
            container.orchestration_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=initial.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        llm_id="openai.gpt-5.4-mini",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.orchestration_service.enqueue(
                EnqueueOrchestrationRunInput(run_id=initial.id),
            )
            container.orchestration_service.process_next_queued_run(worker_id="worker-1")

            followup = container.orchestration_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-auto-prompt-threshold-followup",
                    inbound_instruction=InboundInstruction(
                        source="cli",
                        content="continue",
                    ),
                ),
            )
            container.orchestration_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=followup.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        llm_id="openai.gpt-5.4-mini",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.orchestration_service.enqueue(
                EnqueueOrchestrationRunInput(run_id=followup.id),
            )

            completed = container.orchestration_service.process_next_queued_run(
                worker_id="worker-1",
            )
            self.assertIsNotNone(completed)
            assert completed is not None
            self.assertGreaterEqual(
                completed.metadata["prompt_report"]["estimated_total_tokens"],
                700,
            )

            queued_runs = container.orchestration_service.list_runs(
                status=OrchestrationRunStatus.QUEUED,
            )
            compaction_runs = [
                run
                for run in queued_runs
                if run.inbound_instruction.source == "compaction"
            ]
            self.assertEqual(len(compaction_runs), 1)
            self.assertIn(
                "auto_compaction_prompt_budget_exceeded",
                compaction_runs[0].metadata["prompt_flow_hint"].get("reason", ""),
            )
            self.assertEqual(
                compaction_runs[0].metadata["compaction_request"]["basis"],
                "prompt_budget",
            )
            self.assertEqual(
                compaction_runs[0].metadata["compaction_request"]["details"]["prompt_threshold_tokens"],
                700,
            )
            session = container.session_service.get_session("agent:assistant:main")
            self.assertEqual(
                session.metadata["compaction"]["trigger_basis"],
                "prompt_budget",
            )
        finally:
            custom_harness.close()

    def test_process_next_queued_run_injects_available_skills_catalog(self) -> None:
        adapter = _StaticTextAdapter(text="hello with skill catalog")
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / ".crxzipple" / "skills" / "repo-review").mkdir(
                parents=True,
            )
            (workspace / ".crxzipple" / "skills" / "repo-review" / "SKILL.md").write_text(
                "# Repo Review\n\nUse this skill when reviewing repository changes.\n",
                encoding="utf-8",
            )
            self._register_agent_and_llm(
                runtime_preferences=AgentRuntimePreferences(workspace=str(workspace)),
            )

            with patch(
                "crxzipple.modules.orchestration.application.skills_context.DEFAULT_GLOBAL_SKILLS_DIR",
                root / "global",
            ), patch(
                "crxzipple.modules.orchestration.application.skills_context.DEFAULT_SYSTEM_SKILLS_DIR",
                root / "system",
            ):
                run = self.container.orchestration_service.accept(
                    AcceptOrchestrationRunInput(
                        run_id="run-skill-catalog",
                        inbound_instruction=InboundInstruction(source="cli", content="hello"),
                    ),
                )
                self.container.orchestration_service.prepare_session_run(
                    PrepareSessionRunInput(
                        run_id=run.id,
                        context=SessionRouteContext(
                            agent_id="assistant",
                            llm_id="openai.gpt-5.4-mini",
                            channel="webchat",
                            direct_scope=DirectSessionScope.MAIN,
                        ),
                    ),
                )
                self.container.orchestration_service.enqueue(
                    EnqueueOrchestrationRunInput(run_id=run.id),
                )

                processed = self.container.orchestration_service.process_next_queued_run(
                    worker_id="worker-1",
                )

            self.assertIsNotNone(processed)
            assert processed is not None
            self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
            system_messages = [
                message
                for message in adapter.requests[0].messages
                if message.role is LlmMessageRole.SYSTEM
            ]
            self.assertTrue(
                any(
                    "# Available Skills" in str(message.content)
                    and "repo-review" in str(message.content)
                    and "SKILL.md" in str(message.content)
                    for message in system_messages
                ),
            )
            self.assertIn(
                "skills_catalog",
                [
                    block["kind"]
                    for block in processed.metadata["prompt_report"]["system_blocks"]
                ],
            )

    def test_process_next_queued_run_can_open_skill_and_continue(self) -> None:
        adapter = _SkillLoadingAdapter()
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / ".crxzipple" / "skills" / "repo-review").mkdir(
                parents=True,
            )
            (workspace / ".crxzipple" / "skills" / "repo-review" / "SKILL.md").write_text(
                "# Repo Review\n\nReview changes carefully and cite concrete findings.\n",
                encoding="utf-8",
            )
            self._register_agent_and_llm(
                runtime_preferences=AgentRuntimePreferences(workspace=str(workspace)),
            )

            run = self.container.orchestration_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-open-skill",
                    inbound_instruction=InboundInstruction(source="cli", content="review the repo"),
                ),
            )
            self.container.orchestration_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        llm_id="openai.gpt-5.4-mini",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            self.container.orchestration_service.enqueue(
                EnqueueOrchestrationRunInput(run_id=run.id),
            )

            completed = self.container.orchestration_service.process_next_queued_run(
                worker_id="worker-1",
            )

            self.assertIsNotNone(completed)
            assert completed is not None
            self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
            assert completed.result_payload is not None
            self.assertEqual(completed.result_payload["output_text"], "used repo-review skill")
            self.assertEqual(len(adapter.requests), 2)
            skill_tool_messages = [
                message
                for message in adapter.requests[1].messages
                if message.role is LlmMessageRole.TOOL and message.name == "open_skill"
            ]
            self.assertEqual(len(skill_tool_messages), 1)
            self.assertIn(
                "# Skill: repo-review",
                str(skill_tool_messages[0].content),
            )
            self.assertIn(
                "Review changes carefully and cite concrete findings.",
                str(skill_tool_messages[0].content),
            )
            session_messages = self.container.session_service.list_messages(
                ListSessionMessagesInput(
                    session_key="agent:assistant:main",
                    active_session_only=True,
                ),
            )
            skill_results = [
                message
                for message in session_messages
                if message.source_kind == "skill_request"
            ]
            self.assertEqual(len(skill_results), 1)
            self.assertEqual(skill_results[0].metadata["tool_name"], "open_skill")
            self.assertEqual(skill_results[0].metadata["skill_name"], "repo-review")

    def test_process_next_queued_run_prefers_active_instance_binding_over_legacy_session_llm(
        self,
    ) -> None:
        adapter = _StaticTextAdapter(text="binding-aware llm")
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-binding-llm",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        prepared = self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        assert prepared.active_session_id is not None
        with self.container.uow_factory() as uow:
            session = uow.sessions.get("agent:assistant:main")
            assert session is not None
            session.llm_id = "legacy-stale-llm"
            session.metadata["runtime_binding"] = {
                "agent_id": "assistant",
                "llm_id": "legacy-stale-llm",
            }
            uow.sessions.add(session)
            instance = uow.session_instances.get(prepared.active_session_id)
            assert instance is not None
            instance.metadata["runtime_binding"] = {
                "agent_id": "assistant",
                "llm_id": "openai.gpt-5.4-mini",
            }
            instance.metadata["agent_id"] = "assistant"
            instance.metadata["llm_id"] = "openai.gpt-5.4-mini"
            uow.session_instances.add(instance)
            uow.commit()

        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )
        processed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
        assert processed.result_payload is not None
        self.assertEqual(processed.result_payload["llm_id"], "openai.gpt-5.4-mini")
        self.assertEqual(processed.result_payload["output_text"], "binding-aware llm")

    def test_process_next_queued_run_completes_inline_tool_loop(self) -> None:
        adapter = _InlineToolLoopAdapter()
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()
        tool = self.container.tool_service.register(
            RegisterToolInput(
                id="echo",
                name="Echo",
                description="Returns the input payload for local inline execution tests.",
                supported_modes=(ToolMode.INLINE,),
                runtime_key="echo",
            ),
        )

        async def echo(arguments: dict[str, object]) -> dict[str, object]:
            return {"echo": arguments.get("message")}

        self.container.local_tool_catalog.register(tool, echo)

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-process-inline-tool",
                inbound_instruction=InboundInstruction(source="cli", content="search"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        processed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
        self.assertEqual(processed.stage, OrchestrationRunStage.COMPLETED)
        self.assertEqual(processed.current_step, 2)
        assert processed.result_payload is not None
        self.assertEqual(processed.result_payload["output_text"], "tool loop complete")
        self.assertEqual(processed.result_payload["llm_id"], "openai.gpt-5.4-mini")
        self.assertEqual(len(adapter.requests), 2)
        self.assertEqual([schema.name for schema in adapter.requests[0].tool_schemas], ["echo"])
        self.assertEqual(
            [message.role for message in adapter.requests[1].messages[:2]],
            [
                LlmMessageRole.SYSTEM,
                LlmMessageRole.SYSTEM,
            ],
        )
        self.assertEqual(
            [message.role for message in adapter.requests[1].messages[-3:]],
            [
                LlmMessageRole.USER,
                LlmMessageRole.ASSISTANT,
                LlmMessageRole.TOOL,
            ],
        )
        self.assertEqual(adapter.requests[1].messages[-2].tool_call_id, "call-echo-1")
        self.assertEqual(adapter.requests[1].messages[-1].tool_call_id, "call-echo-1")
        self.assertEqual(adapter.requests[1].messages[-1].name, "echo")

        session_messages = self.container.session_service.list_messages(
            ListSessionMessagesInput(
                session_key="agent:assistant:main",
                active_session_only=True,
            ),
        )
        self.assertEqual(
            [message.role for message in session_messages],
            ["user", "assistant", "tool", "assistant"],
        )
        self.assertEqual(session_messages[1].metadata["tool_call_id"], "call-echo-1")
        self.assertEqual(session_messages[2].metadata["tool_call_id"], "call-echo-1")

    def test_process_next_queued_run_waits_when_tool_is_background(self) -> None:
        custom_harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            authorization_enabled=True,
            authorization_policy_paths=(
                str(
                    Path(__file__).resolve().parents[2]
                    / "config"
                    / "authorization_policies"
                    / "default.yaml"
                ),
            ),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        custom_harness.initialize_schema(settings=settings)
        container = custom_harness.build_container(settings=settings)
        try:
            container.llm_adapter_registry.register(
                LlmApiFamily.OPENAI_RESPONSES,
                _BackgroundToolAdapter(),
            )
            container.llm_service.register_profile(
                RegisterLlmProfileInput(
                    id="openai.gpt-5.4-mini",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4-mini",
                ),
            )
            container.agent_service.register_profile(
                RegisterAgentProfileInput(
                    id="assistant",
                    name="Assistant",
                    instruction_policy=AgentInstructionPolicy(
                        system_prompt="Be helpful and concise.",
                    ),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.gpt-5.4-mini",
                    ),
                ),
            )

            tool = container.tool_service.register(
                RegisterToolInput(
                    id="background_echo",
                    name="Background Echo",
                    description="Only runs in the background.",
                    supported_modes=(ToolMode.BACKGROUND,),
                    runtime_key="background_echo",
                ),
            )

            async def background_echo(arguments: dict[str, object]) -> dict[str, object]:
                return {"message": arguments.get("message")}

            container.local_tool_catalog.register(tool, background_echo)
            container.authorization_service.grant_agent_effect_access(
                agent_id="assistant",
                effect_id="background_execution",
            )

            run = container.orchestration_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-process-tool",
                    inbound_instruction=InboundInstruction(source="cli", content="search"),
                ),
            )
            container.orchestration_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        llm_id="openai.gpt-5.4-mini",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.orchestration_service.enqueue(
                EnqueueOrchestrationRunInput(run_id=run.id),
            )

            processed = container.orchestration_service.process_next_queued_run(
                worker_id="worker-1",
            )

            self.assertIsNotNone(processed)
            assert processed is not None
            self.assertEqual(processed.status, OrchestrationRunStatus.WAITING)
            self.assertEqual(processed.stage, OrchestrationRunStage.WAITING_ON_TOOL)
            self.assertEqual(processed.current_step, 1)
            self.assertEqual(processed.waiting_reason, "tool_background_wait")
            self.assertEqual(len(processed.pending_tool_run_ids), 1)

            tool_run = container.tool_service.get_tool_run(
                processed.pending_tool_run_ids[0],
            )
            self.assertEqual(tool_run.status, ToolRunStatus.QUEUED)

            session_messages = container.session_service.list_messages(
                ListSessionMessagesInput(
                    session_key="agent:assistant:main",
                    active_session_only=True,
                ),
            )
            self.assertEqual([message.role for message in session_messages], ["user", "assistant"])
            self.assertEqual(session_messages[1].metadata["tool_call_id"], "call-bg-1")
        finally:
            custom_harness.close()

    def test_background_tool_completion_event_resumes_run_and_allows_next_turn(self) -> None:
        custom_harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            authorization_enabled=True,
            authorization_policy_paths=(
                str(
                    Path(__file__).resolve().parents[2]
                    / "config"
                    / "authorization_policies"
                    / "default.yaml"
                ),
            ),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        custom_harness.initialize_schema(settings=settings)
        container = custom_harness.build_container(settings=settings)
        try:
            adapter = _BackgroundResumeAdapter()
            container.llm_adapter_registry.register(
                LlmApiFamily.OPENAI_RESPONSES,
                adapter,
            )
            container.llm_service.register_profile(
                RegisterLlmProfileInput(
                    id="openai.gpt-5.4-mini",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4-mini",
                ),
            )
            container.agent_service.register_profile(
                RegisterAgentProfileInput(
                    id="assistant",
                    name="Assistant",
                    instruction_policy=AgentInstructionPolicy(
                        system_prompt="Be helpful and concise.",
                    ),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.gpt-5.4-mini",
                    ),
                ),
            )

            tool = container.tool_service.register(
                RegisterToolInput(
                    id="background_echo",
                    name="Background Echo",
                    description="Only runs in the background.",
                    supported_modes=(ToolMode.BACKGROUND,),
                    runtime_key="background_echo",
                ),
            )

            async def background_echo(arguments: dict[str, object]) -> dict[str, object]:
                return {"message": arguments.get("message")}

            container.local_tool_catalog.register(tool, background_echo)
            container.authorization_service.grant_agent_effect_access(
                agent_id="assistant",
                effect_id="background_execution",
            )

            run = container.orchestration_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-process-background-resume",
                    inbound_instruction=InboundInstruction(source="cli", content="search"),
                ),
            )
            container.orchestration_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        llm_id="openai.gpt-5.4-mini",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.orchestration_service.enqueue(
                EnqueueOrchestrationRunInput(run_id=run.id),
            )

            waiting = container.orchestration_service.process_next_queued_run(
                worker_id="worker-1",
            )
            assert waiting is not None
            self.assertEqual(waiting.status, OrchestrationRunStatus.WAITING)
            self.assertEqual(len(waiting.pending_tool_run_ids), 1)
            background_tool_run_id = waiting.pending_tool_run_ids[0]

            finished_tool_run = container.tool_service.process_next_queued_run(
                worker_id="tool-worker-1",
            )
            self.assertIsNotNone(finished_tool_run)
            assert finished_tool_run is not None
            self.assertEqual(finished_tool_run.id, background_tool_run_id)
            self.assertEqual(finished_tool_run.status, ToolRunStatus.SUCCEEDED)

            resumed = container.orchestration_service.get_run(run.id)
            self.assertEqual(resumed.status, OrchestrationRunStatus.QUEUED)
            self.assertEqual(resumed.stage, OrchestrationRunStage.QUEUED)
            self.assertEqual(resumed.pending_tool_run_ids, ())
            self.assertEqual(resumed.waiting_reason, None)
            self.assertEqual(
                resumed.queue_policy,
                OrchestrationQueuePolicy.RESUME_FIRST,
            )

            session_messages = container.session_service.list_messages(
                ListSessionMessagesInput(
                    session_key="agent:assistant:main",
                    active_session_only=True,
                ),
            )
            self.assertEqual(
                [message.role for message in session_messages],
                ["user", "assistant", "tool"],
            )
            self.assertEqual(session_messages[2].source_id, background_tool_run_id)
            self.assertEqual(session_messages[2].metadata["tool_call_id"], "call-bg-1")

            completed = container.orchestration_service.process_next_queued_run(
                worker_id="worker-1",
            )
            self.assertIsNotNone(completed)
            assert completed is not None
            self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
            self.assertEqual(completed.stage, OrchestrationRunStage.COMPLETED)
            self.assertEqual(completed.current_step, 2)
            assert completed.result_payload is not None
            self.assertEqual(
                completed.result_payload["output_text"],
                "background loop complete",
            )
            self.assertEqual(len(adapter.requests), 2)
            self.assertEqual(
                [message.role for message in adapter.requests[1].messages[:2]],
                [
                    LlmMessageRole.SYSTEM,
                    LlmMessageRole.SYSTEM,
                ],
            )
            self.assertEqual(
                [message.role for message in adapter.requests[1].messages[-3:]],
                [
                    LlmMessageRole.USER,
                    LlmMessageRole.ASSISTANT,
                    LlmMessageRole.TOOL,
                ],
            )
            self.assertEqual(completed.metadata["prompt_mode"], "recovery_resume")
            recovery_system_messages = [
                message
                for message in adapter.requests[1].messages
                if message.role is LlmMessageRole.SYSTEM
            ]
            self.assertTrue(
                any(
                    "# Recovery Update" in str(message.content)
                    and "resuming after background work completed" in str(message.content)
                    for message in recovery_system_messages
                ),
            )
            self.assertFalse(
                any(
                    "Durable memory is available for this agent." in str(message.content)
                    for message in recovery_system_messages
                ),
            )
            self.assertFalse(
                any("# Recalled Memory" in str(message.content) for message in recovery_system_messages),
            )
        finally:
            custom_harness.close()

    def test_background_tool_call_can_wait_for_approval_then_transition_to_tool_wait(self) -> None:
        custom_harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            authorization_enabled=True,
            authorization_policy_paths=(
                str(
                    Path(__file__).resolve().parents[2]
                    / "config"
                    / "authorization_policies"
                    / "default.yaml"
                ),
            ),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        custom_harness.initialize_schema(settings=settings)
        container = custom_harness.build_container(settings=settings)
        try:
            adapter = _BackgroundApprovalAdapter()
            container.llm_adapter_registry.register(
                LlmApiFamily.OPENAI_RESPONSES,
                adapter,
            )
            container.llm_service.register_profile(
                RegisterLlmProfileInput(
                    id="openai.gpt-5.4-mini",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4-mini",
                ),
            )
            container.agent_service.register_profile(
                RegisterAgentProfileInput(
                    id="assistant",
                    name="Assistant",
                    instruction_policy=AgentInstructionPolicy(
                        system_prompt="Be helpful and concise.",
                    ),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.gpt-5.4-mini",
                    ),
                ),
            )

            tool = container.tool_service.register(
                RegisterToolInput(
                    id="background_echo",
                    name="Background Echo",
                    description="Only runs in the background.",
                    supported_modes=(ToolMode.BACKGROUND,),
                    runtime_key="background_echo",
                ),
            )

            async def background_echo(arguments: dict[str, object]) -> dict[str, object]:
                return {"message": arguments.get("message")}

            container.local_tool_catalog.register(tool, background_echo)

            run = container.orchestration_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-background-approval",
                    inbound_instruction=InboundInstruction(source="cli", content="search"),
                ),
            )
            container.orchestration_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        llm_id="openai.gpt-5.4-mini",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.orchestration_service.enqueue(
                EnqueueOrchestrationRunInput(run_id=run.id),
            )

            waiting_for_approval = container.orchestration_service.process_next_queued_run(
                worker_id="worker-1",
            )
            self.assertIsNotNone(waiting_for_approval)
            assert waiting_for_approval is not None
            self.assertEqual(
                waiting_for_approval.stage,
                OrchestrationRunStage.WAITING_FOR_CONFIRMATION,
            )
            pending_request = waiting_for_approval.pending_approval_request()
            self.assertIsNotNone(pending_request)
            assert pending_request is not None
            self.assertEqual(pending_request.effect_id, "background_execution")
            self.assertEqual(pending_request.tool_name, "background_echo")

            waiting_on_tool = container.orchestration_service.resolve_approval_request(
                ResolveApprovalRequestInput(
                    run_id=run.id,
                    request_id=pending_request.request_id,
                    decision=ApprovalDecision.ALLOW_ONCE,
                ),
            )
            self.assertEqual(waiting_on_tool.status, OrchestrationRunStatus.WAITING)
            self.assertEqual(waiting_on_tool.stage, OrchestrationRunStage.WAITING_ON_TOOL)
            self.assertEqual(waiting_on_tool.waiting_reason, "tool_background_wait")
            self.assertEqual(len(waiting_on_tool.pending_tool_run_ids), 1)

            finished_tool_run = container.tool_service.process_next_queued_run(
                worker_id="tool-worker-1",
            )
            self.assertIsNotNone(finished_tool_run)
            assert finished_tool_run is not None
            self.assertEqual(finished_tool_run.status, ToolRunStatus.SUCCEEDED)

            resumed = container.orchestration_service.get_run(run.id)
            self.assertEqual(resumed.status, OrchestrationRunStatus.QUEUED)
            self.assertEqual(resumed.stage, OrchestrationRunStage.QUEUED)

            completed = container.orchestration_service.process_next_queued_run(
                worker_id="worker-1",
            )
            self.assertIsNotNone(completed)
            assert completed is not None
            self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
            self.assertEqual(
                completed.result_payload["output_text"],
                "background approval flow complete",
            )
        finally:
            custom_harness.close()

    def test_approval_replay_fails_if_stored_target_is_no_longer_supported(self) -> None:
        custom_harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            authorization_enabled=True,
            authorization_policy_paths=(
                str(
                    Path(__file__).resolve().parents[2]
                    / "config"
                    / "authorization_policies"
                    / "default.yaml"
                ),
            ),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        custom_harness.initialize_schema(settings=settings)
        container = custom_harness.build_container(settings=settings)
        try:
            adapter = _BackgroundApprovalAdapter()
            container.llm_adapter_registry.register(
                LlmApiFamily.OPENAI_RESPONSES,
                adapter,
            )
            container.llm_service.register_profile(
                RegisterLlmProfileInput(
                    id="openai.gpt-5.4-mini",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4-mini",
                ),
            )
            container.agent_service.register_profile(
                RegisterAgentProfileInput(
                    id="assistant",
                    name="Assistant",
                    instruction_policy=AgentInstructionPolicy(
                        system_prompt="Be helpful and concise.",
                    ),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.gpt-5.4-mini",
                    ),
                ),
            )

            tool = container.tool_service.register(
                RegisterToolInput(
                    id="background_echo",
                    name="Background Echo",
                    description="Only runs in the background.",
                    supported_modes=(ToolMode.BACKGROUND,),
                    runtime_key="background_echo",
                ),
            )

            async def background_echo(arguments: dict[str, object]) -> dict[str, object]:
                return {"message": arguments.get("message")}

            container.local_tool_catalog.register(tool, background_echo)

            run = container.orchestration_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-background-approval-target-mismatch",
                    inbound_instruction=InboundInstruction(source="cli", content="search"),
                ),
            )
            container.orchestration_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        llm_id="openai.gpt-5.4-mini",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.orchestration_service.enqueue(
                EnqueueOrchestrationRunInput(run_id=run.id),
            )

            waiting_for_approval = container.orchestration_service.process_next_queued_run(
                worker_id="worker-1",
            )
            self.assertIsNotNone(waiting_for_approval)
            assert waiting_for_approval is not None
            pending_request = waiting_for_approval.pending_approval_request()
            self.assertIsNotNone(pending_request)
            assert pending_request is not None
            self.assertEqual(pending_request.tool_name, "background_echo")
            self.assertEqual(pending_request.execution_mode, ToolMode.BACKGROUND.value)

            with container.tool_service.uow_factory() as uow:
                persisted = uow.tools.get("background_echo")
                assert persisted is not None
                uow.tools.add(
                    replace(
                        persisted,
                        execution_support=ToolExecutionSupport(
                            supported_modes=(ToolMode.INLINE,),
                            supported_strategies=persisted.execution_support.supported_strategies,
                            supported_environments=persisted.execution_support.supported_environments,
                        ),
                    ),
                )
                uow.commit()

            with self.assertRaises(OrchestrationValidationError) as exc_info:
                container.orchestration_service.resolve_approval_request(
                    ResolveApprovalRequestInput(
                        run_id=run.id,
                        request_id=pending_request.request_id,
                        decision=ApprovalDecision.ALLOW_ONCE,
                    ),
                )
            self.assertIn(
                "Approved tool replay target is no longer supported",
                str(exc_info.exception),
            )
        finally:
            custom_harness.close()

    def test_recover_abandoned_runs_recovers_tool_wait_when_wait_mapping_is_lost(self) -> None:
        custom_harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            authorization_enabled=True,
            authorization_policy_paths=(
                str(
                    Path(__file__).resolve().parents[2]
                    / "config"
                    / "authorization_policies"
                    / "default.yaml"
                ),
            ),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        custom_harness.initialize_schema(settings=settings)
        container = custom_harness.build_container(settings=settings)
        try:
            adapter = _BackgroundApprovalAdapter()
            container.llm_adapter_registry.register(
                LlmApiFamily.OPENAI_RESPONSES,
                adapter,
            )
            container.llm_service.register_profile(
                RegisterLlmProfileInput(
                    id="openai.gpt-5.4-mini",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4-mini",
                ),
            )
            container.agent_service.register_profile(
                RegisterAgentProfileInput(
                    id="assistant",
                    name="Assistant",
                    instruction_policy=AgentInstructionPolicy(
                        system_prompt="Be helpful and concise.",
                    ),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.gpt-5.4-mini",
                    ),
                ),
            )

            tool = container.tool_service.register(
                RegisterToolInput(
                    id="background_echo",
                    name="Background Echo",
                    description="Only runs in the background.",
                    supported_modes=(ToolMode.BACKGROUND,),
                    runtime_key="background_echo",
                ),
            )

            async def background_echo(arguments: dict[str, object]) -> dict[str, object]:
                return {"message": arguments.get("message")}

            container.local_tool_catalog.register(tool, background_echo)

            run = container.orchestration_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-background-tool-wait-recovery",
                    inbound_instruction=InboundInstruction(source="cli", content="search"),
                ),
            )
            container.orchestration_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        llm_id="openai.gpt-5.4-mini",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.orchestration_service.enqueue(
                EnqueueOrchestrationRunInput(run_id=run.id),
            )

            waiting_for_approval = container.orchestration_service.process_next_queued_run(
                worker_id="worker-1",
            )
            assert waiting_for_approval is not None
            pending_request = waiting_for_approval.pending_approval_request()
            assert pending_request is not None

            waiting_on_tool = container.orchestration_service.resolve_approval_request(
                ResolveApprovalRequestInput(
                    run_id=run.id,
                    request_id=pending_request.request_id,
                    decision=ApprovalDecision.ALLOW_ONCE,
                ),
            )
            self.assertEqual(waiting_on_tool.stage, OrchestrationRunStage.WAITING_ON_TOOL)

            with container.orchestration_service.uow_factory() as uow:
                uow.orchestration_waits.delete_for_run(run.id)
                uow.commit()

            finished_tool_run = container.tool_service.process_next_queued_run(
                worker_id="tool-worker-1",
            )
            self.assertIsNotNone(finished_tool_run)
            assert finished_tool_run is not None
            self.assertEqual(finished_tool_run.status, ToolRunStatus.SUCCEEDED)

            recovered = container.orchestration_service.recover_abandoned_runs()
            self.assertTrue(any(item.id == run.id for item in recovered))

            resumed = container.orchestration_service.get_run(run.id)
            self.assertEqual(resumed.status, OrchestrationRunStatus.QUEUED)
            self.assertEqual(resumed.stage, OrchestrationRunStage.QUEUED)

            completed = container.orchestration_service.process_next_queued_run(
                worker_id="worker-1",
            )
            self.assertIsNotNone(completed)
            assert completed is not None
            self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
            self.assertEqual(
                completed.result_payload["output_text"],
                "background approval flow complete",
            )
        finally:
            custom_harness.close()

    def test_process_next_queued_run_fails_when_llm_requests_unknown_tool(self) -> None:
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            _ToolCallAdapter(),
        )
        self._register_agent_and_llm()

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-process-tool",
                inbound_instruction=InboundInstruction(source="cli", content="search"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        processed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.FAILED)
        self.assertEqual(processed.stage, OrchestrationRunStage.FAILED)
        self.assertEqual(processed.current_step, 1)
        assert processed.error is not None
        self.assertEqual(processed.error.code, "engine_failed")
        self.assertIn("search_docs", processed.error.message)

        session_messages = self.container.session_service.list_messages(
            ListSessionMessagesInput(
                session_key="agent:assistant:main",
                active_session_only=True,
            ),
        )
        self.assertEqual(
            [message.role for message in session_messages],
            ["user", "assistant"],
        )

    def test_cancel_run_keeps_it_out_of_queue(self) -> None:
        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-cancel",
                inbound_instruction=InboundInstruction(source="http", content="stop"),
            ),
        )
        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=run.id,
                agent_id="writer",
                bulk_key="conversation:cancel",
                lane_key="bulk:conversation:cancel",
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        cancelled = self.container.orchestration_service.cancel_run(
            run.id,
            reason="user_cancelled",
        )
        claimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )

        self.assertEqual(cancelled.status, OrchestrationRunStatus.CANCELLED)
        self.assertEqual(cancelled.stage, OrchestrationRunStage.CANCELLED)
        self.assertIsNone(claimed)

    def test_llm_adapter_failure_is_surface_in_orchestration_error(self) -> None:
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            _FailingAdapter(),
        )
        self._register_agent_and_llm()

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-llm-failure",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        processed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.FAILED)
        self.assertEqual(processed.stage, OrchestrationRunStage.FAILED)
        assert processed.error is not None
        self.assertEqual(processed.error.code, "engine_failed")
        self.assertIn("adapter_error", processed.error.message)
        self.assertIn("sample adapter failure", processed.error.message)


if __name__ == "__main__":
    unittest.main()
