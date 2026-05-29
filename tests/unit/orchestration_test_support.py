from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import timedelta, timezone, datetime
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from crxzipple.core.config import load_settings
from crxzipple.interfaces.runtime_container import AppKey
from crxzipple.modules.access.application.repositories import (
    AccessCredentialBindingRecord,
)
from crxzipple.modules.agent.application import (
    RegisterAgentProfileInput,
    UpdateAgentProfileInput,
)
from crxzipple.modules.authorization.domain import AuthorizationEffect, AuthorizationPolicy
from crxzipple.modules.dispatch.application import (
    CreateDispatchTaskInput,
    EnqueueDispatchTaskInput,
    RecoverAbandonedDispatchTasksInput,
)
from crxzipple.modules.agent.domain import (
    AgentInstructionPolicy,
    AgentLlmRoutingPolicy,
    AgentMemoryBinding,
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
from crxzipple.modules.orchestration.application import (
    AdvanceAssignmentInput,
    RequestCompactionInput,
    RequestDueHeartbeatsInput,
    RequestHeartbeatInput,
    RequestMemoryFlushInput,
    ResolveApprovalRequestInput,
    WaitAssignmentOnToolInput,
)
from crxzipple.modules.orchestration.application.commands import (
    CompleteAssignmentInput,
    FailAssignmentInput,
    ResumeOrchestrationRunInput,
)
from crxzipple.modules.orchestration.application.intake_commands import (
    AcceptOrchestrationRunInput,
    EnqueueOrchestrationRunInput,
    PrepareSessionRunInput,
    RouteOrchestrationRunInput,
)
from crxzipple.modules.orchestration.domain import (
    ApprovalDecision,
    InboundInstruction,
    OrchestrationQueuePolicy,
    OrchestrationRunStage,
    OrchestrationRunStatus,
    OrchestrationValidationError,
    ReplyTarget,
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
from crxzipple.modules.tool.application import ExecuteToolInput
from crxzipple.modules.tool.domain import (
    Tool,
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolExecutionSupport,
    ToolKind,
    ToolMode,
    ToolParameter,
    ToolRunStatus,
)
from tests.unit.support import SqliteTestHarness
from tests.unit.skill_test_support import write_skill_package as _write_skill_package
from tests.unit.tool_catalog_seed import seed_catalog_tool


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


class _SequentialResultAdapter:
    def __init__(self, *results: LlmResult | str) -> None:
        self._results = list(results)
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        raw = self._results.pop(0) if self._results else ""
        if isinstance(raw, LlmResult):
            result = raw
        else:
            result = LlmResult(text=raw)
        return LlmAdapterResponse(result=result)


class _SequentialFailureAdapter:
    def __init__(self, *results: LlmResult | str | Exception) -> None:
        self._results = list(results)
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        raw = self._results.pop(0) if self._results else ""
        if isinstance(raw, Exception):
            raise raw
        if isinstance(raw, LlmResult):
            result = raw
        else:
            result = LlmResult(text=raw)
        return LlmAdapterResponse(result=result)


def _memory_flush_skip_result() -> LlmResult:
    return LlmResult(
        tool_calls=(
            ToolCallIntent(
                id="call-memory-flush-skip-1",
                name="memory_flush_skip",
                arguments={},
            ),
        ),
    )


def _memory_flush_tool_schema_names(request: LlmAdapterRequest) -> list[str]:
    return sorted(schema.name for schema in request.tool_schemas)


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


class _SkillReadingAdapter:
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
            if message.name == "skill_read"
        ]
        if not skill_messages:
            return LlmAdapterResponse(
                result=LlmResult(
                    tool_calls=(
                        ToolCallIntent(
                            id="call-skill-1",
                            name="skill_read",
                            arguments={"skill": "repo-review"},
                        ),
                    ),
                ),
            )
        return LlmAdapterResponse(result=LlmResult(text="used repo-review skill"))


class _SkillReadAndEchoAdapter:
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
                            id="call-skill-1",
                            name="skill_read",
                            arguments={"skill": "repo-review"},
                        ),
                        ToolCallIntent(
                            id="call-echo-1",
                            name="echo",
                            arguments={"message": "hello after reading"},
                        ),
                    ),
                ),
            )
        return LlmAdapterResponse(result=LlmResult(text="used skill guidance without mode switch"))


class _MultiSkillReadAdapter:
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
                            id="call-skill-1",
                            name="skill_read",
                            arguments={"skill": "repo-review"},
                        ),
                        ToolCallIntent(
                            id="call-skill-2",
                            name="skill_read",
                            arguments={"skill": "memory-recall"},
                        ),
                    ),
                ),
            )
        return LlmAdapterResponse(result=LlmResult(text="compared multiple skills before deciding"))


class _MemorySearchAndReadAdapter:
    def __init__(
        self,
        *,
        path: str,
        start_line: int = 1,
        line_count: int = 12,
    ) -> None:
        self.path = path
        self.start_line = start_line
        self.line_count = line_count
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
        read_messages = [
            message
            for message in tool_messages
            if message.name == "memory_read"
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
        if not read_messages:
            end_line = self.start_line + max(self.line_count, 1) - 1
            return LlmAdapterResponse(
                result=LlmResult(
                    tool_calls=(
                        ToolCallIntent(
                            id="call-read-file-1",
                            name="memory_read",
                            arguments={
                                "citation": (
                                    f"{self.path}:{self.start_line}"
                                    if end_line <= self.start_line
                                    else f"{self.path}:{self.start_line}-{end_line}"
                                ),
                            },
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


class _OverlayAccessConfigView:
    def __init__(
        self,
        records: dict[str, AccessCredentialBindingRecord],
        *,
        fallback: object | None,
    ) -> None:
        self.records = records
        self.fallback = fallback

    def get_credential_binding(
        self,
        binding_id: str,
    ) -> AccessCredentialBindingRecord | object | None:
        normalized = binding_id.strip()
        if normalized in self.records:
            return self.records[normalized]
        get_binding = getattr(self.fallback, "get_credential_binding", None)
        if callable(get_binding):
            return get_binding(normalized)
        return None


def assign_next_orchestration_assignment(
    container,
    *,
    worker_id: str,
    max_inflight_assignments: int = 1,
):
    executor_service = container.require(AppKey.ORCHESTRATION_EXECUTOR_CONTROL_SERVICE)
    scheduler_service = container.require(
        AppKey.ORCHESTRATION_SCHEDULER_MAINTENANCE_SERVICE,
    )
    executor_service.heartbeat_executor(
        worker_id=worker_id,
        max_inflight_assignments=max_inflight_assignments,
    )
    return scheduler_service.assign_next_assignment()


def process_next_orchestration_assignment(
    container,
    *,
    worker_id: str,
    max_inflight_assignments: int = 1,
):
    executor_service = container.require(AppKey.ORCHESTRATION_EXECUTOR_CONTROL_SERVICE)
    scheduler_service = container.require(
        AppKey.ORCHESTRATION_SCHEDULER_MAINTENANCE_SERVICE,
    )
    executor_service.heartbeat_executor(
        worker_id=worker_id,
        max_inflight_assignments=max_inflight_assignments,
    )
    assigned = scheduler_service.assign_next_assignment()
    if assigned is None:
        return executor_service.process_next_assigned_assignment(
            worker_id=worker_id,
        )
    return executor_service.process_assigned_assignment(
        run_id=assigned.id,
        worker_id=worker_id,
    )



class OrchestrationTestCaseBase(unittest.TestCase):
    default_llm_credential_binding_id = "openai-api-key"
    default_llm_credential_env_name = "CRXZIPPLE_TEST_OPENAI_API_KEY"

    def setUp(self) -> None:
        self._previous_openapi_provider_paths = os.environ.get(
            "APP_TOOL_OPENAPI_PROVIDER_PATHS",
        )
        self._previous_default_llm_credential = os.environ.get(
            self.default_llm_credential_env_name,
        )
        self._previous_memory_storage_root = os.environ.get("APP_MEMORY_STORAGE_ROOT")
        os.environ["APP_TOOL_OPENAPI_PROVIDER_PATHS"] = os.pathsep
        os.environ[self.default_llm_credential_env_name] = "test-openai-api-key"
        self._memory_tempdir = tempfile.TemporaryDirectory()
        os.environ["APP_MEMORY_STORAGE_ROOT"] = str(
            Path(self._memory_tempdir.name) / "memory",
        )
        self._skills_tempdir = tempfile.TemporaryDirectory()
        skills_root = Path(self._skills_tempdir.name)
        self._global_skills_patcher = patch(
            "crxzipple.modules.skills.infrastructure.filesystem.repository.DEFAULT_GLOBAL_SKILLS_DIR",
            skills_root / "global",
        )
        self._system_skills_patcher = patch(
            "crxzipple.modules.skills.infrastructure.filesystem.repository.DEFAULT_SYSTEM_SKILLS_DIR",
            skills_root / "system",
        )
        self._global_skills_patcher.start()
        self._system_skills_patcher.start()
        self.harness = SqliteTestHarness()
        self.harness.initialize_schema()
        self.container = self.harness.build_runtime_container()
        self._bind_runtime_services()
        system_skill_dir = skills_root / "system" / "memory-recall"
        _write_skill_package(
            system_skill_dir,
            name="memory-recall",
            description=(
                "Use this skill when earlier decisions, preferences, commitments, "
                "or durable workspace context may affect the current answer."
            ),
            instructions=(
                "# Memory Recall\n\n"
                "Use this skill when earlier decisions, preferences, commitments, "
                "or durable workspace context may affect the current answer.\n"
            ),
            allowed_tools=("memory_search", "memory_read", "memory_write_daily"),
        )

    def _bind_runtime_services(self) -> None:
        self.access_service = self.container.require(AppKey.ACCESS_SERVICE)
        self.agent_service = self.container.require(AppKey.AGENT_SERVICE)
        self.artifact_service = self.container.require(AppKey.ARTIFACT_SERVICE)
        self.authorization_service = self.container.require(
            AppKey.AUTHORIZATION_SERVICE,
        )
        channel_infrastructure = self.container.require(AppKey.CHANNEL_INFRASTRUCTURE)
        self.channel_interaction_service = channel_infrastructure.interaction_service
        self.channel_runtime_manager = self.container.require(
            AppKey.CHANNEL_RUNTIME_MANAGER,
        )
        self.dispatch_service = self.container.require(AppKey.DISPATCH_SERVICE)
        self.event_bus = self.container.require(AppKey.EVENTS_BUS)
        self.events_service = self.container.require(AppKey.EVENTS_SERVICE)
        self.file_memory_service = self.container.require(AppKey.FILE_MEMORY_SERVICE)
        self.llm_adapter_registry = self.container.require(
            AppKey.LLM_ADAPTER_REGISTRY,
        )
        self.llm_service = self.container.require(AppKey.LLM_SERVICE)
        self.local_runtime_registry = self.container.require(AppKey.TOOL_LOCAL_RUNTIME_REGISTRY)
        self.memory_context_resolver = self.container.require(
            AppKey.MEMORY_CONTEXT_RESOLVER,
        )
        self.operations_observer_runtime_event_service = self.container.require(
            AppKey.OPERATIONS_OBSERVER_RUNTIME_EVENT_SERVICE,
        )
        self.orchestration_approval_control_service = self.container.require(
            AppKey.ORCHESTRATION_APPROVAL_CONTROL_SERVICE,
        )
        self.orchestration_cancellation_service = self.container.require(
            AppKey.ORCHESTRATION_CANCELLATION_SERVICE,
        )
        self.orchestration_executor_service = self.container.require(
            AppKey.ORCHESTRATION_EXECUTOR_SERVICE,
        )
        self.orchestration_inspection_service = self.container.require(
            AppKey.ORCHESTRATION_INSPECTION_SERVICE,
        )
        self.orchestration_intake_service = self.container.require(
            AppKey.ORCHESTRATION_INTAKE_SERVICE,
        )
        self.orchestration_run_query_service = self.container.require(
            AppKey.ORCHESTRATION_RUN_QUERY_SERVICE,
        )
        self.orchestration_scheduler_runtime_event_service = self.container.require(
            AppKey.ORCHESTRATION_SCHEDULER_RUNTIME_EVENT_SERVICE,
        )
        self.orchestration_scheduler_service = self.container.require(
            AppKey.ORCHESTRATION_SCHEDULER_SERVICE,
        )
        self.session_resolution_service = self.container.require(
            AppKey.SESSION_RESOLUTION_SERVICE,
        )
        self.session_service = self.container.require(AppKey.SESSION_SERVICE)
        self.settings_action_service = self.container.require(
            AppKey.SETTINGS_ACTION_SERVICE,
        )
        self.skill_manager = self.container.require(AppKey.SKILL_MANAGER)
        self.tool_service = self.container.require(AppKey.TOOL_SERVICE)
        self.uow_factory = self.container.require(AppKey.UNIT_OF_WORK_FACTORY)

    def seed_tool(self, **kwargs):
        return seed_catalog_tool(self.container, **kwargs)

    def tearDown(self) -> None:
        self._system_skills_patcher.stop()
        self._global_skills_patcher.stop()
        self._skills_tempdir.cleanup()
        self._memory_tempdir.cleanup()
        self.harness.close()
        if self._previous_openapi_provider_paths is None:
            os.environ.pop("APP_TOOL_OPENAPI_PROVIDER_PATHS", None)
        else:
            os.environ["APP_TOOL_OPENAPI_PROVIDER_PATHS"] = (
                self._previous_openapi_provider_paths
            )
        if self._previous_default_llm_credential is None:
            os.environ.pop(self.default_llm_credential_env_name, None)
        else:
            os.environ[self.default_llm_credential_env_name] = (
                self._previous_default_llm_credential
            )
        if self._previous_memory_storage_root is None:
            os.environ.pop("APP_MEMORY_STORAGE_ROOT", None)
        else:
            os.environ["APP_MEMORY_STORAGE_ROOT"] = self._previous_memory_storage_root

    def _install_default_llm_access_binding(self, container) -> str:
        access_service = container.require(AppKey.ACCESS_SERVICE)
        existing_view = getattr(access_service, "config_view", None)
        access_service.config_view = _OverlayAccessConfigView(
            {
                self.default_llm_credential_binding_id: AccessCredentialBindingRecord(
                    binding_id=self.default_llm_credential_binding_id,
                    asset_id=None,
                    binding_kind="api_key",
                    source_kind="env",
                    source_ref=self.default_llm_credential_env_name,
                    masked_preview=f"env:{self.default_llm_credential_env_name}",
                    metadata={"test_fixture": "orchestration"},
                ),
            },
            fallback=existing_view,
        )
        return self.default_llm_credential_binding_id

    def _register_agent_and_llm(
        self,
        *,
        llm_id: str = "openai.gpt-5.4-mini",
        context_window_tokens: int | None = None,
        runtime_preferences: AgentRuntimePreferences | None = None,
        memory: AgentMemoryBinding | None = None,
    ) -> None:
        credential_binding_id = self._install_default_llm_access_binding(self.container)
        self.llm_service.sync_profiles(
            (
                RegisterLlmProfileInput(
                    id=llm_id,
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4-mini",
                    context_window_tokens=context_window_tokens,
                    credential_binding_id=credential_binding_id,
                ),
            ),
        )
        self.agent_service.sync_profiles(
            (
                RegisterAgentProfileInput(
                    id="assistant",
                    name="Assistant",
                    instruction_policy=AgentInstructionPolicy(
                        system_prompt="Be helpful and concise.",
                    ),
                    llm_routing_policy=AgentLlmRoutingPolicy(default_llm_id=llm_id),
                    runtime_preferences=runtime_preferences
                    or AgentRuntimePreferences(),
                    memory=memory or AgentMemoryBinding(),
                ),
            ),
        )


__all__ = [name for name in globals() if not name.startswith("__")]
