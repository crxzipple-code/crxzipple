from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from datetime import timedelta, timezone, datetime
from enum import StrEnum
from types import MethodType
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
    LlmMessagePhase,
    LlmMessageRole,
    LlmProviderKind,
    LlmResponseItem,
    LlmResponseItemKind,
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
    AppendSessionItemInput,
    ListSessionItemsInput,
)
from crxzipple.modules.session.domain import (
    DirectSessionScope,
    SessionItem,
    SessionItemKind,
    SessionItemPhase,
    SessionItemVisibility,
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
    ToolRunResult,
    ToolRunStatus,
)
from tests.unit.support import (
    SqliteTestHarness,
    publish_outbox_events,
    published_event_bus_events,
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
    session_id: str | None = None
    source_kind: str | None = None
    source_id: str | None = None


def _append_session_item_fixture(
    session_service: object,
    data: AppendSessionItemFixtureInput,
) -> SessionItem:
    return session_service.append_item(
        AppendSessionItemInput(
            session_key=data.session_key,
            session_id=data.session_id,
            role=data.role,
            kind=_session_item_kind_from_item_fixture(data),
            phase=(
                SessionItemPhase.COMMENTARY
                if data.role == "assistant"
                else SessionItemPhase.UNKNOWN
            ),
            visibility=SessionItemVisibility(
                model_visible=True,
                user_visible=data.role in {"assistant", "user"},
                chat_visible=data.role in {"assistant", "user"},
                trace_visible=True,
            ),
            content_payload=dict(data.content_payload),
            source_module="session",
            source_kind=data.source_kind,
            source_id=data.source_id,
            call_id=_item_fixture_tool_call_id(data),
            tool_name=_item_fixture_tool_name(data),
            metadata=dict(data.metadata),
        ),
    )


def _session_item_kind_from_item_fixture(
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


def _item_fixture_tool_call_id(data: AppendSessionItemFixtureInput) -> str | None:
    return (
        _optional_text_for_fixture(data.metadata.get("tool_call_id"))
        or _optional_text_for_fixture(data.content_payload.get("call_id"))
        or _optional_text_for_fixture(data.content_payload.get("tool_call_id"))
    )


def _item_fixture_tool_name(data: AppendSessionItemFixtureInput) -> str | None:
    return (
        _optional_text_for_fixture(data.metadata.get("tool_name"))
        or _optional_text_for_fixture(data.content_payload.get("name"))
        or _optional_text_for_fixture(data.content_payload.get("tool_name"))
    )


def _optional_text_for_fixture(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None
from tests.unit.skill_test_support import write_skill_package as _write_skill_package
from tests.unit.tool_catalog_seed import seed_catalog_tool


class _StaticTextAdapter:
    def __init__(self, *, text: str) -> None:
        self.text = text
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        return _adapter_response_from_result(request, LlmResult(text=self.text))


class _SequentialTextAdapter:
    def __init__(self, *texts: str) -> None:
        self._texts = list(texts)
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        text = self._texts.pop(0) if self._texts else ""
        return _adapter_response_from_result(request, LlmResult(text=text))


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
        return _adapter_response_from_result(request, result)


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
        return _adapter_response_from_result(request, result)


def _adapter_response_from_result(
    request: LlmAdapterRequest,
    result: LlmResult,
) -> LlmAdapterResponse:
    return LlmAdapterResponse(
        result=result,
        response_items=_response_items_from_result(request, result),
    )


def _response_items_from_result(
    request: LlmAdapterRequest,
    result: LlmResult,
) -> tuple[LlmResponseItem, ...]:
    items: list[LlmResponseItem] = []
    if result.text is not None and result.text.strip():
        items.append(
            LlmResponseItem(
                id=f"{request.invocation_id}:item:assistant:{len(items) + 1}",
                invocation_id=request.invocation_id,
                sequence_no=len(items) + 1,
                kind=LlmResponseItemKind.ASSISTANT_MESSAGE,
                role=LlmMessageRole.ASSISTANT,
                phase=(
                    LlmMessagePhase.COMMENTARY
                    if result.tool_calls
                    else LlmMessagePhase.FINAL_ANSWER
                ),
                content_payload={"text": result.text},
                provider_item_type="message",
                model_visible=True,
                user_visible=not bool(result.tool_calls),
            ),
        )
    for tool_call in result.tool_calls:
        items.append(
            LlmResponseItem(
                id=f"{request.invocation_id}:item:tool_call:{tool_call.id}",
                invocation_id=request.invocation_id,
                sequence_no=len(items) + 1,
                kind=LlmResponseItemKind.TOOL_CALL,
                role=LlmMessageRole.ASSISTANT,
                phase=LlmMessagePhase.COMMENTARY,
                content_payload={
                    "call_id": tool_call.id,
                    "tool_name": tool_call.name,
                    "arguments": dict(tool_call.arguments),
                },
                provider_item_id=f"provider-{tool_call.id}",
                provider_item_type="function_call",
                call_id=tool_call.id,
                tool_name=tool_call.name,
                model_visible=True,
                user_visible=False,
            ),
        )
    return tuple(items)


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
        return _adapter_response_from_result(
            request,
            LlmResult(
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


def _has_tool_message(request: LlmAdapterRequest, name: str) -> bool:
    return any(
        message.role is LlmMessageRole.TOOL and message.name == name
        for message in request.messages
    )


def _has_tool_call_message(request: LlmAdapterRequest, name: str) -> bool:
    return any(
        message.role is LlmMessageRole.ASSISTANT
        and isinstance(message.content, dict)
        and message.content.get("type") == "function_call"
        and message.content.get("name") == name
        for message in request.messages
    )


def _expand_tool_bundle_call(*, call_id: str, source_id: str) -> ToolCallIntent:
    return ToolCallIntent(
        id=call_id,
        name="context_tree.expand",
        arguments={"node_id": f"tools.bundle.{source_id}"},
    )


def _enable_tool_schema_call(*, call_id: str, tool_id: str) -> ToolCallIntent:
    return ToolCallIntent(
        id=call_id,
        name="context_tree.enable_tool_schema",
        arguments={"node_id": f"tools.tool.{tool_id}"},
    )


def _tool_schema_activation_response(
    request: LlmAdapterRequest,
    *,
    source_id: str,
    tool_id: str,
    expand_call_id: str,
    enable_call_id: str,
) -> LlmAdapterResponse | None:
    if not _has_tool_message(request, "context_tree.expand"):
        return _adapter_response_from_result(
            request,
            LlmResult(
                tool_calls=(
                    _expand_tool_bundle_call(
                        call_id=expand_call_id,
                        source_id=source_id,
                    ),
                ),
            ),
        )
    if not any(schema.name == tool_id for schema in request.tool_schemas):
        return _adapter_response_from_result(
            request,
            LlmResult(
                tool_calls=(
                    _enable_tool_schema_call(
                        call_id=enable_call_id,
                        tool_id=tool_id,
                    ),
                ),
            ),
        )
    return None


class _InlineToolLoopAdapter:
    def __init__(self) -> None:
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        request_index = len(self.requests) - 1
        if request_index == 0:
            return _adapter_response_from_result(
                request,
                LlmResult(
                    tool_calls=(
                        _expand_tool_bundle_call(
                            call_id="call-expand-echo",
                            source_id="test.local_package.echo",
                        ),
                    ),
                ),
            )
        if request_index == 1:
            return _adapter_response_from_result(
                request,
                LlmResult(
                    tool_calls=(
                        _enable_tool_schema_call(
                            call_id="call-enable-echo",
                            tool_id="echo",
                        ),
                    ),
                ),
            )
        if request_index == 2:
            return _adapter_response_from_result(
                request,
                LlmResult(
                    tool_calls=(
                        ToolCallIntent(
                            id="call-echo-1",
                            name="echo",
                            arguments={"message": "hello from tool"},
                        ),
                    ),
                ),
            )
        return _adapter_response_from_result(
            request,
            LlmResult(text="tool loop complete"),
        )


class _BackgroundToolAdapter:
    def __init__(self) -> None:
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        activation = _tool_schema_activation_response(
            request,
            source_id="test.local_package.background_echo",
            tool_id="background_echo",
            expand_call_id="call-expand-background",
            enable_call_id="call-enable-background",
        )
        if activation is not None:
            return activation
        if _has_tool_call_message(request, "background_echo"):
            return _adapter_response_from_result(
                request,
                LlmResult(text="background already requested"),
            )
        return _adapter_response_from_result(
            request,
            LlmResult(
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
        activation = _tool_schema_activation_response(
            request,
            source_id="test.local_package.background_echo",
            tool_id="background_echo",
            expand_call_id="call-expand-background",
            enable_call_id="call-enable-background",
        )
        if activation is not None:
            return activation
        if not _has_tool_call_message(request, "background_echo"):
            return _adapter_response_from_result(
                request,
                LlmResult(
                    tool_calls=(
                        ToolCallIntent(
                            id="call-bg-1",
                            name="background_echo",
                            arguments={"message": "background hello"},
                        ),
                    ),
                ),
            )
        return _adapter_response_from_result(
            request,
            LlmResult(text="background loop complete"),
        )


class _BackgroundApprovalAdapter:
    def __init__(self) -> None:
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        activation = _tool_schema_activation_response(
            request,
            source_id="test.local_package.background_echo",
            tool_id="background_echo",
            expand_call_id="call-expand-background-approval",
            enable_call_id="call-enable-background-approval",
        )
        if activation is not None:
            return activation
        if not _has_tool_call_message(request, "background_echo"):
            return _adapter_response_from_result(
                request,
                LlmResult(
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
        activation = _tool_schema_activation_response(
            request,
            source_id="test.local_package.echo",
            tool_id="echo",
            expand_call_id="call-expand-echo",
            enable_call_id="call-enable-echo",
        )
        if activation is not None:
            return activation
        if not _has_tool_call_message(request, "echo"):
            return _adapter_response_from_result(
                request,
                LlmResult(
                    tool_calls=(
                        ToolCallIntent(
                            id="call-echo-1",
                            name="echo",
                            arguments={"message": "hello after approval"},
                        ),
                    ),
                ),
            )
        if not _has_tool_message(request, "echo"):
            raise AssertionError("approval replay should provide an echo tool result")
        return _adapter_response_from_result(
            request,
            LlmResult(text="approval flow complete"),
        )


class _MultiToolApprovalAdapter:
    def __init__(self) -> None:
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        activation = _tool_schema_activation_response(
            request,
            source_id="test.local_package.echo",
            tool_id="echo",
            expand_call_id="call-expand-echo",
            enable_call_id="call-enable-echo",
        )
        if activation is not None:
            return activation
        if not _has_tool_call_message(request, "echo"):
            return _adapter_response_from_result(
                request,
                LlmResult(
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
        return _adapter_response_from_result(
            request,
            LlmResult(text="multi approval flow complete"),
        )


class _EffectApprovalOrVisibleAdapter:
    def __init__(self) -> None:
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        activation = _tool_schema_activation_response(
            request,
            source_id="test.local_package.echo",
            tool_id="echo",
            expand_call_id="call-expand-echo",
            enable_call_id="call-enable-echo",
        )
        if activation is not None:
            return activation
        if not _has_tool_call_message(request, "echo"):
            return _adapter_response_from_result(
                request,
                LlmResult(
                    tool_calls=(
                        ToolCallIntent(
                            id="call-echo-1",
                            name="echo",
                            arguments={"message": "hello after approval"},
                        ),
                    ),
                ),
            )
        if not _has_tool_message(request, "echo"):
            return _adapter_response_from_result(
                request,
                LlmResult(
                    tool_calls=(
                        ToolCallIntent(
                            id="call-echo-2",
                            name="echo",
                            arguments={"message": "hello after approval"},
                        ),
                    ),
                ),
            )
        return _adapter_response_from_result(
            request,
            LlmResult(text="approval flow complete"),
        )


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
        activation = _tool_schema_activation_response(
            request,
            source_id="test.local_package.echo",
            tool_id="echo",
            expand_call_id="call-expand-echo",
            enable_call_id="call-enable-echo",
        )
        if activation is not None:
            return activation
        return _adapter_response_from_result(
            request,
            LlmResult(
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
        if not _has_tool_message(request, "context_tree.expand"):
            return _adapter_response_from_result(
                request,
                LlmResult(
                    tool_calls=(
                        ToolCallIntent(
                            id="call-expand-skills",
                            name="context_tree.expand",
                            arguments={"node_id": "skills.available"},
                        ),
                        _expand_tool_bundle_call(
                            call_id="call-expand-skill-tools",
                            source_id="bundled.local_package.skills",
                        ),
                    ),
                ),
            )
        if not _has_tool_message(request, "context_tree.enable_tool_schema"):
            return _adapter_response_from_result(
                request,
                LlmResult(
                    tool_calls=(
                        _enable_tool_schema_call(
                            call_id="call-enable-skill-read",
                            tool_id="skill_read",
                        ),
                    ),
                ),
            )
        if not _has_tool_message(request, "skill_read"):
            return _adapter_response_from_result(
                request,
                LlmResult(
                    tool_calls=(
                        ToolCallIntent(
                            id="call-skill-1",
                            name="skill_read",
                            arguments={"skill": "repo-review"},
                        ),
                    ),
                ),
            )
        return _adapter_response_from_result(
            request,
            LlmResult(text="used repo-review skill"),
        )


class _SkillReadAndEchoAdapter:
    def __init__(self) -> None:
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        if not _has_tool_message(request, "context_tree.expand"):
            return _adapter_response_from_result(
                request,
                LlmResult(
                    tool_calls=(
                        ToolCallIntent(
                            id="call-expand-skills",
                            name="context_tree.expand",
                            arguments={"node_id": "skills.available"},
                        ),
                        _expand_tool_bundle_call(
                            call_id="call-expand-skill-tools",
                            source_id="bundled.local_package.skills",
                        ),
                        _expand_tool_bundle_call(
                            call_id="call-expand-echo",
                            source_id="test.local_package.echo",
                        ),
                    ),
                ),
            )
        if not _has_tool_message(request, "context_tree.enable_tool_schema"):
            return _adapter_response_from_result(
                request,
                LlmResult(
                    tool_calls=(
                        _enable_tool_schema_call(
                            call_id="call-enable-skill-read",
                            tool_id="skill_read",
                        ),
                        _enable_tool_schema_call(
                            call_id="call-enable-echo",
                            tool_id="echo",
                        ),
                    ),
                ),
            )
        if not _has_tool_message(request, "skill_read"):
            return _adapter_response_from_result(
                request,
                LlmResult(
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
        return _adapter_response_from_result(
            request,
            LlmResult(text="used skill guidance without mode switch"),
        )


class _MultiSkillReadAdapter:
    def __init__(self) -> None:
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        if not _has_tool_message(request, "context_tree.expand"):
            return _adapter_response_from_result(
                request,
                LlmResult(
                    tool_calls=(
                        ToolCallIntent(
                            id="call-expand-skills",
                            name="context_tree.expand",
                            arguments={"node_id": "skills.available"},
                        ),
                        _expand_tool_bundle_call(
                            call_id="call-expand-skill-tools",
                            source_id="bundled.local_package.skills",
                        ),
                    ),
                ),
            )
        if not _has_tool_message(request, "context_tree.enable_tool_schema"):
            return _adapter_response_from_result(
                request,
                LlmResult(
                    tool_calls=(
                        _enable_tool_schema_call(
                            call_id="call-enable-skill-read",
                            tool_id="skill_read",
                        ),
                    ),
                ),
            )
        if not _has_tool_message(request, "skill_read"):
            return _adapter_response_from_result(
                request,
                LlmResult(
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
        return _adapter_response_from_result(
            request,
            LlmResult(text="compared multiple skills before deciding"),
        )


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
        if not _has_tool_message(request, "context_tree.expand"):
            return _adapter_response_from_result(
                request,
                LlmResult(
                    tool_calls=(
                        _expand_tool_bundle_call(
                            call_id="call-expand-memory-tools",
                            source_id="bundled.local_package.memory",
                        ),
                    ),
                ),
            )
        if not _has_tool_message(request, "context_tree.enable_tool_schema"):
            return _adapter_response_from_result(
                request,
                LlmResult(
                    tool_calls=(
                        _enable_tool_schema_call(
                            call_id="call-enable-memory-search",
                            tool_id="memory_search",
                        ),
                        _enable_tool_schema_call(
                            call_id="call-enable-memory-read",
                            tool_id="memory_read",
                        ),
                    ),
                ),
            )
        if not search_messages:
            return _adapter_response_from_result(
                request,
                LlmResult(
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
            return _adapter_response_from_result(
                request,
                LlmResult(
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
        return _adapter_response_from_result(
            request,
            LlmResult(text="memory-guided answer"),
        )


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
        return _adapter_response_from_result(request, LlmResult(text=self.text))


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


def execution_tool_run_ids_for_run(container, run_id: str) -> list[str]:
    query = container.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE)
    tool_run_ids: list[str] = []
    for chain in query.list_execution_chains(run_id):
        for step in query.list_execution_steps(chain.id):
            for item in query.list_execution_step_items(step.id):
                owner = item.owner
                if owner is None or owner.owner_kind != "tool_run":
                    continue
                if owner.owner_id not in tool_run_ids:
                    tool_run_ids.append(owner.owner_id)
    return tool_run_ids



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
        self.session_service.append_item_fixture = MethodType(
            lambda service, data: _append_session_item_fixture(service, data),
            self.session_service,
        )
        self.settings_action_service = self.container.require(
            AppKey.SETTINGS_ACTION_SERVICE,
        )
        self.skill_manager = self.container.require(AppKey.SKILL_MANAGER)
        self.tool_service = self.container.require(AppKey.TOOL_SERVICE)
        self.uow_factory = self.container.require(AppKey.UNIT_OF_WORK_FACTORY)

    def seed_tool(self, **kwargs):
        return seed_catalog_tool(self.container, **kwargs)

    def publish_outbox_events(self) -> int:
        return publish_outbox_events(self.container)

    def published_event_bus_events(self) -> tuple[object, ...]:
        return published_event_bus_events(self.container)

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
