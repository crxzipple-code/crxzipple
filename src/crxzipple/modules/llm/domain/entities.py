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
    LlmContinuationSignal,
    LlmModelFamily,
    LlmProviderKind,
    LlmResponseItem,
    LlmResult,
    LlmSourceKind,
    ToolSchema,
    utcnow,
)

from crxzipple.shared.domain import AggregateRoot


_forbidden_credential_binding_prefixes = ("env:", "file:")
_forbidden_credential_binding_ids = {"codex_auth_json", "codex-cli", "auth_ref"}
_forbidden_credential_binding_id_prefixes = ("codex_auth_json:", "auth_ref:")


@dataclass(kw_only=True)
class LlmProfile(AggregateRoot[str]):
    provider: LlmProviderKind
    api_family: LlmApiFamily
    model_name: str
    context_window_tokens: int | None = None
    model_family: LlmModelFamily = LlmModelFamily.GENERAL
    capabilities: tuple[LlmCapability, ...] = field(default_factory=tuple)
    default_params: LlmDefaults = field(default_factory=LlmDefaults)
    base_url: str | None = None
    credential_binding_id: str | None = None
    timeout_seconds: int = 60
    max_concurrency: int | None = None
    concurrency_key: str | None = None
    source_kind: LlmSourceKind = LlmSourceKind.MANUAL
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.model_name.strip():
            raise LlmValidationError("LLM model_name cannot be empty.")
        if self.timeout_seconds <= 0:
            raise LlmValidationError("LLM timeout_seconds must be greater than zero.")
        if self.context_window_tokens is not None and self.context_window_tokens <= 0:
            raise LlmValidationError(
                "LLM context_window_tokens must be greater than zero when provided.",
            )
        if self.max_concurrency is not None and self.max_concurrency <= 0:
            raise LlmValidationError(
                "LLM max_concurrency must be greater than zero when provided.",
            )
        if self.concurrency_key is not None:
            self.concurrency_key = self.concurrency_key.strip() or None
        if self.credential_binding_id is not None:
            self.credential_binding_id = self.credential_binding_id.strip() or None
        if self.credential_binding_id is not None and _looks_like_credential_source(
            self.credential_binding_id,
        ):
            raise LlmValidationError(
                "LLM credential_binding_id must reference an Access credential binding id.",
            )
        self.capabilities = tuple(dict.fromkeys(self.capabilities))


def _looks_like_credential_source(value: str) -> bool:
    normalized = value.strip()
    return (
        normalized.startswith(_forbidden_credential_binding_prefixes)
        or normalized in _forbidden_credential_binding_ids
        or normalized.startswith(_forbidden_credential_binding_id_prefixes)
    )


@dataclass(kw_only=True)
class LlmInvocation(AggregateRoot[str]):
    llm_id: str
    messages: tuple[LlmMessage, ...]
    tool_schemas: tuple[ToolSchema, ...] = field(default_factory=tuple)
    response_format: dict[str, object] | None = None
    request_overrides: dict[str, object] = field(default_factory=dict)
    request_metadata: dict[str, object] = field(default_factory=dict)
    status: LlmInvocationStatus = LlmInvocationStatus.CREATED
    result: LlmResult | None = None
    response_items: tuple[LlmResponseItem, ...] = field(default_factory=tuple)
    continuation: LlmContinuationSignal | None = None
    error: LlmErrorPayload | None = None
    provider_request_id: str | None = None
    provider_request_payload_preview: dict[str, object] = field(default_factory=dict)
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
        self.response_items = tuple(self.response_items)
        self.request_overrides = dict(self.request_overrides)
        self.request_metadata = dict(self.request_metadata)
        self.provider_request_payload_preview = dict(
            self.provider_request_payload_preview,
        )
        if self.response_format is not None:
            self.response_format = dict(self.response_format)

    def record_provider_request_payload_preview(
        self,
        preview: dict[str, object],
    ) -> None:
        self.provider_request_payload_preview = dict(preview)

    def start(self) -> None:
        self.status = LlmInvocationStatus.RUNNING
        self.started_at = utcnow()
        self.completed_at = None
        self.error = None

    def succeed(
        self,
        result: LlmResult,
        *,
        response_items: tuple[LlmResponseItem, ...] = (),
        continuation: LlmContinuationSignal | None = None,
        provider_request_id: str | None = None,
    ) -> None:
        self.status = LlmInvocationStatus.SUCCEEDED
        self.result = result
        self.response_items = tuple(response_items)
        self.continuation = continuation
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
