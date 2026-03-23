from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from crxzipple.modules.llm.domain.exceptions import LlmValidationError
from crxzipple.modules.llm.domain.value_objects import (
    LlmApiFamily,
    LlmCapability,
    LlmDefaults,
    LlmErrorPayload,
    LlmInvocationStatus,
    LlmMessage,
    LlmModelFamily,
    LlmProviderKind,
    LlmResult,
    LlmSourceKind,
    ToolSchema,
    utcnow,
)

from crxzipple.shared.domain import AggregateRoot


@dataclass(kw_only=True)
class LlmProfile(AggregateRoot[str]):
    provider: LlmProviderKind
    api_family: LlmApiFamily
    model_name: str
    model_family: LlmModelFamily = LlmModelFamily.GENERAL
    capabilities: tuple[LlmCapability, ...] = field(default_factory=tuple)
    default_params: LlmDefaults = field(default_factory=LlmDefaults)
    base_url: str | None = None
    credential_binding: str | None = None
    timeout_seconds: int = 60
    source_kind: LlmSourceKind = LlmSourceKind.MANUAL
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.model_name.strip():
            raise LlmValidationError("LLM model_name cannot be empty.")
        if self.timeout_seconds <= 0:
            raise LlmValidationError("LLM timeout_seconds must be greater than zero.")
        self.capabilities = tuple(dict.fromkeys(self.capabilities))


@dataclass(kw_only=True)
class LlmInvocation(AggregateRoot[str]):
    llm_id: str
    messages: tuple[LlmMessage, ...]
    tool_schemas: tuple[ToolSchema, ...] = field(default_factory=tuple)
    response_format: dict[str, object] | None = None
    request_overrides: dict[str, object] = field(default_factory=dict)
    status: LlmInvocationStatus = LlmInvocationStatus.CREATED
    result: LlmResult | None = None
    error: LlmErrorPayload | None = None
    provider_request_id: str | None = None
    created_at: datetime = field(default_factory=utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.llm_id.strip():
            raise LlmValidationError("LLM invocation llm_id cannot be empty.")
        if not self.messages:
            raise LlmValidationError("LLM invocation requires at least one message.")
        self.messages = tuple(self.messages)
        self.tool_schemas = tuple(self.tool_schemas)
        self.request_overrides = dict(self.request_overrides)
        if self.response_format is not None:
            self.response_format = dict(self.response_format)

    def start(self) -> None:
        self.status = LlmInvocationStatus.RUNNING
        self.started_at = utcnow()
        self.completed_at = None
        self.error = None

    def succeed(
        self,
        result: LlmResult,
        *,
        provider_request_id: str | None = None,
    ) -> None:
        self.status = LlmInvocationStatus.SUCCEEDED
        self.result = result
        self.error = None
        self.provider_request_id = provider_request_id
        self.completed_at = utcnow()

    def fail(
        self,
        error: LlmErrorPayload,
        *,
        provider_request_id: str | None = None,
    ) -> None:
        self.status = LlmInvocationStatus.FAILED
        self.error = error
        self.provider_request_id = provider_request_id
        self.completed_at = utcnow()
