from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator, Mapping
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Callable, Protocol
from uuid import uuid4

from crxzipple.modules.llm.application.adapters import (
    LlmAdapterGateway,
    LlmAdapterRequest,
    LlmAdapterResponse,
)
from crxzipple.modules.llm.application.concurrency import LlmConcurrencyLimiter
from crxzipple.modules.llm.application.runtime_request import (
    RuntimeLlmRequest,
    request_render_snapshot_preview_payload,
    runtime_request_context_from_metadata,
)
from crxzipple.modules.llm.application.streaming import LlmStreamEvent
from crxzipple.modules.llm.domain.entities import LlmInvocation, LlmProfile
from crxzipple.modules.llm.domain.exceptions import (
    LlmAdapterNotConfiguredError,
    LlmAlreadyExistsError,
    LlmInvocationNotAllowedError,
    LlmInvocationNotFoundError,
    LlmNotFoundError,
    LlmResponseItemNotFoundError,
    LlmValidationError,
)
from crxzipple.modules.llm.domain.repositories import (
    LlmInvocationRepository,
    LlmProfileRepository,
)
from crxzipple.modules.llm.domain.value_objects import (
    LlmApiFamily,
    LlmCapability,
    LlmContinuationSignal,
    LlmDefaults,
    LlmErrorPayload,
    LlmInputItem,
    LlmMessage,
    LlmModelFamily,
    LlmProviderKind,
    LlmProviderContinuation,
    LlmResponseEventRetentionPolicy,
    LlmResponseEvent,
    LlmResponseEventType,
    LlmResponseItem,
    LlmResult,
    LlmSourceKind,
    ToolSchema,
)
from crxzipple.shared.domain.aggregates import AggregateRoot
from crxzipple.shared.domain.events import Event
from crxzipple.shared.access import (
    AccessConsumerRef,
    CredentialBindingRef,
    CredentialProvider,
)

_forbidden_credential_binding_prefixes = ("env:", "file:")
_forbidden_credential_binding_ids = {"codex_auth_json", "codex-cli", "auth_ref"}
_forbidden_credential_binding_id_prefixes = ("codex_auth_json:", "auth_ref:")
DEFAULT_RESPONSE_EVENT_RETENTION_POLICY = LlmResponseEventRetentionPolicy(
    full_event_window_seconds=86_400,
    detail_event_limit=100,
    durable_fact="completed_response_items",
    overflow_action="prefer_response_items_and_request_preview",
)


@dataclass(frozen=True, slots=True)
class RegisterLlmProfileInput:
    id: str
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

    @classmethod
    def from_config(
        cls,
        config: LlmProfileImportLike | Mapping[str, Any],
    ) -> "RegisterLlmProfileInput":
        return register_llm_profile_input_from_config(config)


class LlmProfileImportLike(Protocol):
    profile_id: str
    provider: str | LlmProviderKind
    api_family: str | LlmApiFamily
    model_name: str


class CredentialBindingMetadataProvider(Protocol):
    def describe_credential_binding(
        self,
        binding_id: str,
    ) -> Mapping[str, object] | None: ...


@dataclass(frozen=True, slots=True)
class InvokeLlmInput:
    llm_id: str
    messages: tuple[LlmMessage, ...]
    input_items: tuple[LlmInputItem, ...] = field(default_factory=tuple)
    provider_context_messages: tuple[LlmMessage, ...] = field(default_factory=tuple)
    tool_schemas: tuple[ToolSchema, ...] = field(default_factory=tuple)
    response_format: dict[str, Any] | None = None
    request_policy: dict[str, Any] = field(default_factory=dict)
    overrides: dict[str, Any] = field(default_factory=dict)
    request_metadata: dict[str, Any] = field(default_factory=dict)
    runtime_context: dict[str, Any] = field(default_factory=dict)
    runtime_route: dict[str, Any] = field(default_factory=dict)
    runtime_policy: dict[str, Any] = field(default_factory=dict)
    invocation_id: str | None = None
    continuation: LlmProviderContinuation | None = None

    @classmethod
    def from_runtime_request(
        cls,
        request: RuntimeLlmRequest,
        *,
        response_format: dict[str, Any] | None = None,
        overrides: dict[str, Any] | None = None,
        invocation_id: str | None = None,
        continuation: LlmProviderContinuation | None = None,
    ) -> "InvokeLlmInput":
        return cls(
            llm_id=request.llm_id,
            messages=request.messages,
            input_items=request.transcript.items,
            provider_context_messages=request.provider_context_messages,
            tool_schemas=request.tool_schemas,
            response_format=(
                dict(response_format)
                if response_format is not None
                else request.response_format()
            ),
            request_policy=dict(request.transcript.policy),
            overrides=dict(
                overrides if overrides is not None else request.provider_overrides(),
            ),
            request_metadata=request.request_metadata(),
            runtime_context=request.renderer_context().to_payload(),
            runtime_route=request.renderer_route().to_payload(),
            runtime_policy=request.renderer_policy().to_payload(),
            invocation_id=invocation_id,
            continuation=continuation,
        )


@dataclass(frozen=True, slots=True)
class StreamLlmInput:
    llm_id: str
    messages: tuple[LlmMessage, ...]
    input_items: tuple[LlmInputItem, ...] = field(default_factory=tuple)
    provider_context_messages: tuple[LlmMessage, ...] = field(default_factory=tuple)
    tool_schemas: tuple[ToolSchema, ...] = field(default_factory=tuple)
    response_format: dict[str, Any] | None = None
    request_policy: dict[str, Any] = field(default_factory=dict)
    overrides: dict[str, Any] = field(default_factory=dict)
    request_metadata: dict[str, Any] = field(default_factory=dict)
    runtime_context: dict[str, Any] = field(default_factory=dict)
    runtime_route: dict[str, Any] = field(default_factory=dict)
    runtime_policy: dict[str, Any] = field(default_factory=dict)
    invocation_id: str | None = None
    continuation: LlmProviderContinuation | None = None

    @classmethod
    def from_runtime_request(
        cls,
        request: RuntimeLlmRequest,
        *,
        response_format: dict[str, Any] | None = None,
        overrides: dict[str, Any] | None = None,
        invocation_id: str | None = None,
        continuation: LlmProviderContinuation | None = None,
    ) -> "StreamLlmInput":
        return cls(
            llm_id=request.llm_id,
            messages=request.messages,
            input_items=request.transcript.items,
            provider_context_messages=request.provider_context_messages,
            tool_schemas=request.tool_schemas,
            response_format=(
                dict(response_format)
                if response_format is not None
                else request.response_format()
            ),
            request_policy=dict(request.transcript.policy),
            overrides=dict(
                overrides if overrides is not None else request.provider_overrides(),
            ),
            request_metadata=request.request_metadata(),
            runtime_context=request.renderer_context().to_payload(),
            runtime_route=request.renderer_route().to_payload(),
            runtime_policy=request.renderer_policy().to_payload(),
            invocation_id=invocation_id,
            continuation=continuation,
        )


@dataclass(frozen=True, slots=True)
class WarmupLlmProfileInput:
    llm_id: str


@dataclass(frozen=True, slots=True)
class WarmupLlmProfileResult:
    llm_id: str
    status: str
    details: dict[str, Any] = field(default_factory=dict)


def register_llm_profile_input_from_config(
    config: LlmProfileImportLike | Mapping[str, Any],
) -> RegisterLlmProfileInput:
    """Convert an import payload into LLM owner-module input."""

    if any(
        _config_has(config, key)
        for key in ("credential_binding", "credential_binding_ref", "auth_ref")  # forbidden legacy profile key
    ):
        raise ValueError(
            "LLM profile config must use credential_binding_id, not credential_binding.",
        )

    return RegisterLlmProfileInput(
        id=str(_config_value(config, "id", _config_value(config, "profile_id"))),
        provider=_coerce_provider_kind(_config_value(config, "provider")),
        api_family=_coerce_api_family(_config_value(config, "api_family")),
        model_name=str(_config_value(config, "model_name")),
        context_window_tokens=_optional_int_config_value(
            _config_value(config, "context_window_tokens", None),
        ),
        model_family=_coerce_model_family(
            _config_value(config, "model_family", LlmModelFamily.GENERAL),
        ),
        capabilities=_capabilities_for_profile_config(config),
        default_params=_defaults_from_config_value(
            _config_value(config, "default_params", None),
        ),
        base_url=_optional_string_config_value(_config_value(config, "base_url", None)),
        credential_binding_id=_credential_binding_id_from_config_value(
            _config_value(config, "credential_binding_id", None),
        ),
        timeout_seconds=_int_config_value(
            _config_value(config, "timeout_seconds", 60),
            default=60,
        ),
        max_concurrency=_optional_int_config_value(
            _config_value(config, "max_concurrency", None),
        ),
        concurrency_key=_optional_string_config_value(
            _config_value(config, "concurrency_key", None),
        ),
        source_kind=_coerce_source_kind(
            _config_value(config, "source_kind", LlmSourceKind.IMPORTED),
        ),
        enabled=_bool_config_value(_config_value(config, "enabled", True)),
    )


def llm_profile_from_config(
    config: LlmProfileImportLike | Mapping[str, Any],
) -> LlmProfile:
    return llm_profile_from_register_input(
        register_llm_profile_input_from_config(config),
    )


def llm_profile_from_register_input(data: RegisterLlmProfileInput) -> LlmProfile:
    return LlmProfile(
        id=data.id,
        provider=data.provider,
        api_family=data.api_family,
        model_name=data.model_name,
        context_window_tokens=data.context_window_tokens,
        model_family=data.model_family,
        capabilities=data.capabilities,
        default_params=data.default_params,
        base_url=data.base_url,
        credential_binding_id=data.credential_binding_id,
        timeout_seconds=data.timeout_seconds,
        max_concurrency=data.max_concurrency,
        concurrency_key=data.concurrency_key,
        source_kind=data.source_kind,
        enabled=data.enabled,
    )


class LlmUnitOfWork(Protocol):
    llm_profiles: LlmProfileRepository
    llm_invocations: LlmInvocationRepository

    def __enter__(self) -> "LlmUnitOfWork": ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None: ...

    def collect(self, aggregate: AggregateRoot[Any]) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class LlmApplicationService:
    def __init__(
        self,
        uow_factory: Callable[[], LlmUnitOfWork],
        adapter_gateway: LlmAdapterGateway,
        *,
        concurrency_limiter: LlmConcurrencyLimiter | None = None,
        credential_provider: CredentialProvider | None = None,
    ) -> None:
        self.uow_factory = uow_factory
        self.adapter_gateway = adapter_gateway
        self.concurrency_limiter = concurrency_limiter or LlmConcurrencyLimiter()
        self.credential_provider = credential_provider

    def register_profile(self, data: RegisterLlmProfileInput) -> LlmProfile:
        with self.uow_factory() as uow:
            if uow.llm_profiles.get(data.id) is not None:
                raise LlmAlreadyExistsError(f"LLM profile '{data.id}' already exists.")

            profile = self._build_profile(data)
            profile.record_event(
                Event(
                    name="llm.profile_registered",
                    payload={
                        "llm_id": profile.id,
                        "provider": profile.provider.value,
                        "api_family": profile.api_family.value,
                    },
                ),
            )
            uow.llm_profiles.add(profile)
            uow.collect(profile)
            uow.commit()
            return profile

    def upsert_profile(self, data: RegisterLlmProfileInput) -> LlmProfile:
        with self.uow_factory() as uow:
            existing = uow.llm_profiles.get(data.id)
            profile = self._build_profile(data)
            profile.record_event(
                Event(
                    name=(
                        "llm.profile_registered"
                        if existing is None
                        else "llm.profile_updated"
                    ),
                    payload={
                        "llm_id": profile.id,
                        "provider": profile.provider.value,
                        "api_family": profile.api_family.value,
                        "source_kind": profile.source_kind.value,
                    },
                ),
            )
            uow.llm_profiles.add(profile)
            uow.collect(profile)
            uow.commit()
            return profile

    def update_profile(self, data: RegisterLlmProfileInput) -> LlmProfile:
        with self.uow_factory() as uow:
            if uow.llm_profiles.get(data.id) is None:
                raise LlmNotFoundError(f"LLM profile '{data.id}' was not found.")
            profile = self._build_profile(data)
            profile.record_event(
                Event(
                    name="llm.profile_updated",
                    payload={
                        "llm_id": profile.id,
                        "provider": profile.provider.value,
                        "api_family": profile.api_family.value,
                        "source_kind": profile.source_kind.value,
                    },
                ),
            )
            uow.llm_profiles.add(profile)
            uow.collect(profile)
            uow.commit()
            return profile

    def set_profile_enabled(self, llm_id: str, *, enabled: bool) -> LlmProfile:
        with self.uow_factory() as uow:
            existing = uow.llm_profiles.get(llm_id)
            if existing is None:
                raise LlmNotFoundError(f"LLM profile '{llm_id}' was not found.")
            profile = LlmProfile(
                id=existing.id,
                provider=existing.provider,
                api_family=existing.api_family,
                model_name=existing.model_name,
                context_window_tokens=existing.context_window_tokens,
                model_family=existing.model_family,
                capabilities=existing.capabilities,
                default_params=existing.default_params,
                base_url=existing.base_url,
                credential_binding_id=existing.credential_binding_id,
                timeout_seconds=existing.timeout_seconds,
                max_concurrency=existing.max_concurrency,
                concurrency_key=existing.concurrency_key,
                source_kind=existing.source_kind,
                enabled=enabled,
            )
            profile.record_event(
                Event(
                    name=("llm.profile_enabled" if enabled else "llm.profile_disabled"),
                    payload={
                        "llm_id": profile.id,
                        "provider": profile.provider.value,
                        "api_family": profile.api_family.value,
                        "enabled": profile.enabled,
                    },
                ),
            )
            uow.llm_profiles.add(profile)
            uow.collect(profile)
            uow.commit()
            return profile

    def delete_profile(self, llm_id: str) -> None:
        with self.uow_factory() as uow:
            existing = uow.llm_profiles.get(llm_id)
            if existing is None:
                raise LlmNotFoundError(f"LLM profile '{llm_id}' was not found.")
            existing.record_event(
                Event(
                    name="llm.profile_deleted",
                    payload={
                        "llm_id": existing.id,
                        "provider": existing.provider.value,
                        "api_family": existing.api_family.value,
                    },
                ),
            )
            uow.llm_profiles.delete(llm_id)
            uow.collect(existing)
            uow.commit()

    def get_profile(self, llm_id: str) -> LlmProfile:
        with self.uow_factory() as uow:
            profile = uow.llm_profiles.get(llm_id)
            if profile is None:
                raise LlmNotFoundError(f"LLM profile '{llm_id}' was not found.")
            return profile

    def get_profile_optional(self, llm_id: str) -> LlmProfile | None:
        with self.uow_factory() as uow:
            return uow.llm_profiles.get(llm_id)

    def list_profiles(self) -> list[LlmProfile]:
        with self.uow_factory() as uow:
            return uow.llm_profiles.list()

    def _get_enabled_profile(self, llm_id: str) -> LlmProfile:
        with self.uow_factory() as uow:
            profile = uow.llm_profiles.get(llm_id)
            if profile is None:
                raise LlmNotFoundError(f"LLM profile '{llm_id}' was not found.")
            if not profile.enabled:
                raise LlmInvocationNotAllowedError(
                    f"LLM profile '{profile.id}' is disabled.",
                )
            return profile

    def sync_profiles(
        self,
        profiles: tuple[RegisterLlmProfileInput, ...],
        *,
        emit_events: bool = True,
    ) -> list[LlmProfile]:
        if not profiles:
            return []

        synced_profiles: list[LlmProfile] = []
        with self.uow_factory() as uow:
            for data in profiles:
                existing = uow.llm_profiles.get(data.id)
                if (
                    existing is not None
                    and existing.source_kind == LlmSourceKind.MANUAL
                    and data.source_kind != LlmSourceKind.MANUAL
                ):
                    synced_profiles.append(existing)
                    continue

                profile = self._build_profile(data)
                event_name = (
                    "llm.profile_registered"
                    if existing is None
                    else "llm.profile_updated"
                )
                if emit_events:
                    profile.record_event(
                        Event(
                            name=event_name,
                            payload={
                                "llm_id": profile.id,
                                "provider": profile.provider.value,
                                "api_family": profile.api_family.value,
                                "source_kind": profile.source_kind.value,
                            },
                        ),
                    )
                uow.llm_profiles.add(profile)
                uow.collect(profile)
                synced_profiles.append(profile)

            uow.commit()
            return synced_profiles

    def invoke(self, data: InvokeLlmInput) -> LlmInvocation:
        with self.uow_factory() as uow:
            profile = uow.llm_profiles.get(data.llm_id)
            if profile is None:
                raise LlmNotFoundError(f"LLM profile '{data.llm_id}' was not found.")
            if not profile.enabled:
                raise LlmInvocationNotAllowedError(
                    f"LLM profile '{profile.id}' is disabled.",
                )

        adapter = self.adapter_gateway.get(profile.api_family)
        if adapter is None:
            raise LlmAdapterNotConfiguredError(
                f"No llm adapter is configured for api family '{profile.api_family.value}'.",
            )

        invocation = LlmInvocation(
            id=data.invocation_id or uuid4().hex,
            llm_id=profile.id,
            messages=data.messages,
            input_items=data.input_items,
            provider_context_messages=data.provider_context_messages,
            tool_schemas=data.tool_schemas,
            response_format=data.response_format,
            request_policy=data.request_policy,
            request_overrides=data.overrides,
            request_metadata=data.request_metadata,
        )
        invocation.start()
        invocation.record_event(
            Event(
                name="llm.invocation_started",
                payload=_invocation_started_event_payload(
                    invocation,
                    profile,
                    streaming=False,
                ),
            ),
        )

        with self.uow_factory() as uow:
            uow.llm_invocations.add(invocation)
            uow.collect(invocation)
            uow.commit()

        try:
            request = self._build_adapter_request(
                profile,
                invocation,
                continuation=data.continuation,
                runtime_context=data.runtime_context,
                runtime_route=data.runtime_route,
                runtime_policy=data.runtime_policy,
            )
            self._record_provider_request_payload_preview(
                invocation.id,
                self._provider_request_payload_preview(adapter, profile, request),
            )
            with self.concurrency_limiter.limit(profile):
                response = adapter.invoke(profile, request)
        except Exception as exc:
            return self._fail_invocation(
                invocation.id,
                LlmErrorPayload(
                    message=str(exc) or type(exc).__name__,
                    code="adapter_error",
                ),
            )

        with self.uow_factory() as uow:
            stored = uow.llm_invocations.get(invocation.id)
            if stored is None:
                raise LlmInvocationNotFoundError(
                    f"LLM invocation '{invocation.id}' was not found.",
                )
            stored.succeed(
                _result_summary_from_adapter_response(response),
                response_items=response.response_items,
                continuation=response.continuation,
                provider_request_id=response.provider_request_id,
            )
            stored.record_event(
                Event(
                    name="llm.invocation_succeeded",
                    payload=_invocation_succeeded_event_payload(
                        stored,
                        profile,
                        streaming=False,
                    ),
                ),
            )
            uow.llm_invocations.add(stored)
            uow.collect(stored)
            uow.commit()
            return stored

    def test_profile(
        self,
        profile_data: RegisterLlmProfileInput,
        data: InvokeLlmInput,
    ) -> LlmInvocation:
        profile = self._build_profile(profile_data)
        adapter = self.adapter_gateway.get(profile.api_family)
        if adapter is None:
            raise LlmAdapterNotConfiguredError(
                f"No llm adapter is configured for api family '{profile.api_family.value}'.",
            )

        invocation = LlmInvocation(
            id=data.invocation_id or uuid4().hex,
            llm_id=profile.id,
            messages=data.messages,
            input_items=data.input_items,
            provider_context_messages=data.provider_context_messages,
            tool_schemas=data.tool_schemas,
            response_format=data.response_format,
            request_policy=data.request_policy,
            request_overrides=data.overrides,
            request_metadata=data.request_metadata,
        )
        invocation.start()

        try:
            request = self._build_adapter_request(
                profile,
                invocation,
                continuation=data.continuation,
                runtime_context=data.runtime_context,
                runtime_route=data.runtime_route,
                runtime_policy=data.runtime_policy,
            )
            invocation.record_provider_request_payload_preview(
                self._provider_request_payload_preview(adapter, profile, request),
            )
            with self.concurrency_limiter.limit(profile):
                response = adapter.invoke(profile, request)
        except Exception as exc:
            invocation.fail(
                LlmErrorPayload(
                    message=str(exc) or type(exc).__name__,
                    code="adapter_error",
                ),
            )
            return invocation

        invocation.succeed(
            _result_summary_from_adapter_response(response),
            response_items=response.response_items,
            continuation=response.continuation,
            provider_request_id=response.provider_request_id,
        )
        return invocation

    def warmup_profile(
        self,
        data: WarmupLlmProfileInput,
    ) -> WarmupLlmProfileResult:
        with self.uow_factory() as uow:
            profile = uow.llm_profiles.get(data.llm_id)
            if profile is None:
                raise LlmNotFoundError(f"LLM profile '{data.llm_id}' was not found.")
            if not profile.enabled:
                raise LlmInvocationNotAllowedError(
                    f"LLM profile '{profile.id}' is disabled.",
                )

        adapter = self.adapter_gateway.get(profile.api_family)
        if adapter is None:
            self._record_profile_warmup_event(
                profile.id,
                "llm.profile_warmup_failed",
                _profile_warmup_event_payload(
                    profile,
                    status="failed",
                    details={
                        "reason": "adapter_not_configured",
                        "api_family": profile.api_family.value,
                    },
                ),
            )
            raise LlmAdapterNotConfiguredError(
                f"No llm adapter is configured for api family '{profile.api_family.value}'.",
            )
        warmup_websocket = getattr(adapter, "warmup_websocket", None)
        if not callable(warmup_websocket):
            details = {"reason": "adapter_warmup_not_supported"}
            self._record_profile_warmup_event(
                profile.id,
                "llm.profile_warmup_skipped",
                _profile_warmup_event_payload(
                    profile,
                    status="skipped",
                    details=details,
                ),
            )
            return WarmupLlmProfileResult(
                llm_id=profile.id,
                status="skipped",
                details=details,
            )
        try:
            details = warmup_websocket(
                profile,
                resolved_credential=self._resolve_profile_credential(profile),
            )
        except Exception as exc:
            self._record_profile_warmup_event(
                profile.id,
                "llm.profile_warmup_failed",
                _profile_warmup_event_payload(
                    profile,
                    status="failed",
                    details={
                        "reason": str(exc) or type(exc).__name__,
                        "error_type": type(exc).__name__,
                    },
                ),
            )
            raise
        detail_payload = dict(details) if isinstance(details, dict) else {}
        self._record_profile_warmup_event(
            profile.id,
            "llm.profile_warmup_succeeded",
            _profile_warmup_event_payload(
                profile,
                status="warmed",
                details=detail_payload,
            ),
        )
        return WarmupLlmProfileResult(
            llm_id=profile.id,
            status="warmed",
            details=detail_payload,
        )

    async def invoke_async(self, data: InvokeLlmInput) -> LlmInvocation:
        profile = await asyncio.to_thread(self._get_enabled_profile, data.llm_id)

        adapter = self.adapter_gateway.get(profile.api_family)
        if adapter is None:
            raise LlmAdapterNotConfiguredError(
                f"No llm adapter is configured for api family '{profile.api_family.value}'.",
            )

        invocation = LlmInvocation(
            id=data.invocation_id or uuid4().hex,
            llm_id=profile.id,
            messages=data.messages,
            input_items=data.input_items,
            provider_context_messages=data.provider_context_messages,
            tool_schemas=data.tool_schemas,
            response_format=data.response_format,
            request_policy=data.request_policy,
            request_overrides=data.overrides,
            request_metadata=data.request_metadata,
        )
        invocation.start()
        invocation.record_event(
            Event(
                name="llm.invocation_started",
                payload=_invocation_started_event_payload(
                    invocation,
                    profile,
                    streaming=False,
                ),
            ),
        )

        await asyncio.to_thread(self._store_started_invocation, invocation)

        try:
            request = self._build_adapter_request(
                profile,
                invocation,
                continuation=data.continuation,
                runtime_context=data.runtime_context,
                runtime_route=data.runtime_route,
                runtime_policy=data.runtime_policy,
            )
            await asyncio.to_thread(
                self._record_provider_request_payload_preview,
                invocation.id,
                self._provider_request_payload_preview(adapter, profile, request),
            )
            async with self.concurrency_limiter.limit_async(profile):
                response = await self._invoke_adapter_async(adapter, profile, request)
        except Exception as exc:
            return await asyncio.to_thread(
                self._fail_invocation,
                invocation.id,
                LlmErrorPayload(
                    message=str(exc) or type(exc).__name__,
                    code="adapter_error",
                ),
            )

        return await asyncio.to_thread(
            self._complete_invocation,
            invocation.id,
            _result_summary_from_adapter_response(response),
            response_items=response.response_items,
            continuation=response.continuation,
            provider_request_id=response.provider_request_id,
        )

    def stream_invoke(self, data: StreamLlmInput) -> Iterator[LlmStreamEvent]:
        with self.uow_factory() as uow:
            profile = uow.llm_profiles.get(data.llm_id)
            if profile is None:
                raise LlmNotFoundError(f"LLM profile '{data.llm_id}' was not found.")
            if not profile.enabled:
                raise LlmInvocationNotAllowedError(
                    f"LLM profile '{profile.id}' is disabled.",
                )

        adapter = self.adapter_gateway.get(profile.api_family)
        if adapter is None:
            raise LlmAdapterNotConfiguredError(
                f"No llm adapter is configured for api family '{profile.api_family.value}'.",
            )

        stream_invoke = getattr(adapter, "stream_invoke", None)
        if not callable(stream_invoke):
            raise LlmAdapterNotConfiguredError(
                f"No streaming llm adapter is configured for api family '{profile.api_family.value}'.",
            )

        invocation = LlmInvocation(
            id=data.invocation_id or uuid4().hex,
            llm_id=profile.id,
            messages=data.messages,
            input_items=data.input_items,
            provider_context_messages=data.provider_context_messages,
            tool_schemas=data.tool_schemas,
            response_format=data.response_format,
            request_policy=data.request_policy,
            request_overrides=data.overrides,
            request_metadata=data.request_metadata,
        )
        invocation.start()
        invocation.record_event(
            Event(
                name="llm.invocation_started",
                payload=_invocation_started_event_payload(
                    invocation,
                    profile,
                    streaming=True,
                ),
            ),
        )

        with self.uow_factory() as uow:
            uow.llm_invocations.add(invocation)
            uow.collect(invocation)
            uow.commit()

        def _generator() -> Iterator[LlmStreamEvent]:
            with self.concurrency_limiter.limit(profile):
                sequence = 1
                completed = False
                yield LlmStreamEvent(
                    type="invocation_started",
                    sequence=sequence,
                    invocation_id=invocation.id,
                    data={
                        "llm_id": invocation.llm_id,
                        "status": invocation.status.value,
                    },
                )
                self._record_response_event(
                    invocation.id,
                    sequence=sequence,
                    event_type="invocation_started",
                    data={
                        "llm_id": invocation.llm_id,
                        "status": invocation.status.value,
                    },
                )
                sequence += 1

                try:
                    request = self._build_adapter_request(
                        profile,
                        invocation,
                        continuation=data.continuation,
                        runtime_context=data.runtime_context,
                        runtime_route=data.runtime_route,
                        runtime_policy=data.runtime_policy,
                    )
                    self._record_provider_request_payload_preview(
                        invocation.id,
                        self._provider_request_payload_preview(
                            adapter,
                            profile,
                            request,
                        ),
                    )
                    for event in stream_invoke(profile, request):
                        normalized_event = LlmStreamEvent(
                            type=event.type,
                            sequence=sequence,
                            invocation_id=invocation.id,
                            data=dict(event.data),
                        )
                        self._record_response_event(
                            invocation.id,
                            sequence=sequence,
                            event_type=normalized_event.type,
                            data=normalized_event.data,
                        )
                        sequence += 1

                        if normalized_event.type == "completed":
                            result_payload = normalized_event.data.get("result")
                            response_items = _response_items_from_completed_payload(
                                normalized_event.data,
                            )
                            continuation = _continuation_from_completed_payload(
                                normalized_event.data,
                            )
                            provider_request_id = normalized_event.data.get(
                                "provider_request_id",
                            )
                            if not isinstance(result_payload, dict):
                                raise RuntimeError(
                                    "Streaming llm adapter completed without a result payload.",
                                )
                            result = LlmResult.from_payload(result_payload)
                            if result is None:
                                raise RuntimeError(
                                    "Streaming llm adapter completed with an invalid result payload.",
                                )
                            self._complete_stream_invocation(
                                invocation.id,
                                result,
                                response_items=response_items,
                                continuation=continuation,
                                provider_request_id=(
                                    str(provider_request_id)
                                    if provider_request_id is not None
                                    else None
                                ),
                            )
                            completed = True
                        yield normalized_event

                    if not completed:
                        failed = self._fail_invocation(
                            invocation.id,
                            LlmErrorPayload(
                                message="Streaming llm invocation ended before completion.",
                                code="stream_incomplete",
                            ),
                            streaming=True,
                        )
                        yield LlmStreamEvent(
                            type="failed",
                            sequence=sequence,
                            invocation_id=invocation.id,
                            data={
                                "error": (
                                    failed.error.to_payload() if failed.error else {}
                                ),
                            },
                        )
                        self._record_response_event(
                            invocation.id,
                            sequence=sequence,
                            event_type="failed",
                            data={"error": failed.error.to_payload() if failed.error else {}},
                        )
                except Exception as exc:
                    failed = self._fail_invocation(
                        invocation.id,
                        LlmErrorPayload(
                            message=str(exc) or type(exc).__name__,
                            code="adapter_error",
                        ),
                        streaming=True,
                    )
                    yield LlmStreamEvent(
                        type="failed",
                        sequence=sequence,
                        invocation_id=invocation.id,
                        data={
                            "error": failed.error.to_payload() if failed.error else {},
                        },
                    )
                    self._record_response_event(
                        invocation.id,
                        sequence=sequence,
                        event_type="failed",
                        data={"error": failed.error.to_payload() if failed.error else {}},
                    )

        return _generator()

    async def stream_invoke_async(
        self,
        data: StreamLlmInput,
    ) -> AsyncIterator[LlmStreamEvent]:
        profile = await asyncio.to_thread(self._get_enabled_profile, data.llm_id)

        adapter = self.adapter_gateway.get(profile.api_family)
        if adapter is None:
            raise LlmAdapterNotConfiguredError(
                f"No llm adapter is configured for api family '{profile.api_family.value}'.",
            )

        stream = self._stream_adapter_async(adapter, profile)
        if stream is None:
            raise LlmAdapterNotConfiguredError(
                f"No streaming llm adapter is configured for api family '{profile.api_family.value}'.",
            )

        invocation = LlmInvocation(
            id=data.invocation_id or uuid4().hex,
            llm_id=profile.id,
            messages=data.messages,
            input_items=data.input_items,
            provider_context_messages=data.provider_context_messages,
            tool_schemas=data.tool_schemas,
            response_format=data.response_format,
            request_policy=data.request_policy,
            request_overrides=data.overrides,
            request_metadata=data.request_metadata,
        )
        invocation.start()
        invocation.record_event(
            Event(
                name="llm.invocation_started",
                payload=_invocation_started_event_payload(
                    invocation,
                    profile,
                    streaming=True,
                ),
            ),
        )

        await asyncio.to_thread(self._store_started_invocation, invocation)

        async with self.concurrency_limiter.limit_async(profile):
            sequence = 1
            completed = False
            yield LlmStreamEvent(
                type="invocation_started",
                sequence=sequence,
                invocation_id=invocation.id,
                data={
                    "llm_id": invocation.llm_id,
                    "status": invocation.status.value,
                },
            )
            await asyncio.to_thread(
                self._record_response_event,
                invocation.id,
                sequence=sequence,
                event_type="invocation_started",
                data={
                    "llm_id": invocation.llm_id,
                    "status": invocation.status.value,
                },
            )
            sequence += 1

            try:
                request = self._build_adapter_request(
                    profile,
                    invocation,
                    continuation=data.continuation,
                    runtime_context=data.runtime_context,
                    runtime_route=data.runtime_route,
                    runtime_policy=data.runtime_policy,
                )
                await asyncio.to_thread(
                    self._record_provider_request_payload_preview,
                    invocation.id,
                    self._provider_request_payload_preview(adapter, profile, request),
                )
                async for event in stream(request):
                    normalized_event = LlmStreamEvent(
                        type=event.type,
                        sequence=sequence,
                        invocation_id=invocation.id,
                        data=dict(event.data),
                    )
                    await asyncio.to_thread(
                        self._record_response_event,
                        invocation.id,
                        sequence=sequence,
                        event_type=normalized_event.type,
                        data=normalized_event.data,
                    )
                    sequence += 1

                    if normalized_event.type == "completed":
                        result_payload = normalized_event.data.get("result")
                        response_items = _response_items_from_completed_payload(
                            normalized_event.data,
                        )
                        continuation = _continuation_from_completed_payload(
                            normalized_event.data,
                        )
                        provider_request_id = normalized_event.data.get(
                            "provider_request_id",
                        )
                        if not isinstance(result_payload, dict):
                            raise RuntimeError(
                                "Streaming llm adapter completed without a result payload.",
                            )
                        result = LlmResult.from_payload(result_payload)
                        if result is None:
                            raise RuntimeError(
                                "Streaming llm adapter completed with an invalid result payload.",
                            )
                        await asyncio.to_thread(
                            self._complete_stream_invocation,
                            invocation.id,
                            result,
                            response_items=response_items,
                            continuation=continuation,
                            provider_request_id=(
                                str(provider_request_id)
                                if provider_request_id is not None
                                else None
                            ),
                        )
                        completed = True
                    yield normalized_event

                if not completed:
                    failed = await asyncio.to_thread(
                        self._fail_invocation,
                        invocation.id,
                        LlmErrorPayload(
                            message="Streaming llm invocation ended before completion.",
                            code="stream_incomplete",
                        ),
                        streaming=True,
                    )
                    yield LlmStreamEvent(
                        type="failed",
                        sequence=sequence,
                        invocation_id=invocation.id,
                        data={
                            "error": failed.error.to_payload() if failed.error else {},
                        },
                    )
                    await asyncio.to_thread(
                        self._record_response_event,
                        invocation.id,
                        sequence=sequence,
                        event_type="failed",
                        data={"error": failed.error.to_payload() if failed.error else {}},
                    )
            except Exception as exc:
                failed = await asyncio.to_thread(
                    self._fail_invocation,
                    invocation.id,
                    LlmErrorPayload(
                        message=str(exc) or type(exc).__name__,
                        code="adapter_error",
                    ),
                    streaming=True,
                )
                yield LlmStreamEvent(
                    type="failed",
                    sequence=sequence,
                    invocation_id=invocation.id,
                    data={
                        "error": failed.error.to_payload() if failed.error else {},
                    },
                )
                await asyncio.to_thread(
                    self._record_response_event,
                    invocation.id,
                    sequence=sequence,
                    event_type="failed",
                    data={"error": failed.error.to_payload() if failed.error else {}},
                )

    def get_invocation(self, invocation_id: str) -> LlmInvocation:
        with self.uow_factory() as uow:
            invocation = uow.llm_invocations.get(invocation_id)
            if invocation is None:
                raise LlmInvocationNotFoundError(
                    f"LLM invocation '{invocation_id}' was not found.",
                )
            return invocation

    def get_response_item(self, item_id: str) -> LlmResponseItem:
        with self.uow_factory() as uow:
            item = uow.llm_invocations.get_response_item(item_id)
            if item is None:
                raise LlmResponseItemNotFoundError(
                    f"LLM response item '{item_id}' was not found.",
                )
            return item

    def list_invocations(
        self,
        *,
        llm_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[LlmInvocation]:
        with self.uow_factory() as uow:
            return uow.llm_invocations.list(
                llm_id=llm_id,
                limit=limit,
                offset=offset,
            )

    def list_response_events(
        self,
        invocation_id: str,
        *,
        limit: int | None = None,
        after_sequence: int | None = None,
    ) -> list[LlmResponseEvent]:
        with self.uow_factory() as uow:
            if uow.llm_invocations.get(invocation_id) is None:
                raise LlmInvocationNotFoundError(
                    f"LLM invocation '{invocation_id}' was not found.",
                )
            return uow.llm_invocations.list_response_events(
                invocation_id,
                limit=limit,
                after_sequence=after_sequence,
            )

    def response_event_retention_policy(self) -> LlmResponseEventRetentionPolicy:
        return DEFAULT_RESPONSE_EVENT_RETENTION_POLICY

    def _record_response_event(
        self,
        invocation_id: str,
        *,
        sequence: int,
        event_type: str,
        data: Mapping[str, Any],
    ) -> None:
        with self.uow_factory() as uow:
            uow.llm_invocations.add_response_event(
                LlmResponseEvent(
                    id=f"{invocation_id}:event:{sequence}",
                    invocation_id=invocation_id,
                    sequence_no=sequence,
                    type=_coerce_response_event_type(event_type),
                    item_id=(
                        str(data["item_id"])
                        if data.get("item_id") not in {None, ""}
                        else None
                    ),
                    delta_payload=dict(data),
                    provider_payload=dict(data.get("provider_payload", {}))
                    if isinstance(data.get("provider_payload"), dict)
                    else {},
                ),
            )
            uow.commit()

    def _store_started_invocation(self, invocation: LlmInvocation) -> None:
        with self.uow_factory() as uow:
            uow.llm_invocations.add(invocation)
            uow.collect(invocation)
            uow.commit()

    def _complete_invocation(
        self,
        invocation_id: str,
        result: LlmResult,
        *,
        response_items: tuple[LlmResponseItem, ...] = (),
        continuation: LlmContinuationSignal | None = None,
        provider_request_id: str | None = None,
    ) -> LlmInvocation:
        with self.uow_factory() as uow:
            stored = uow.llm_invocations.get(invocation_id)
            if stored is None:
                raise LlmInvocationNotFoundError(
                    f"LLM invocation '{invocation_id}' was not found.",
                )
            result_summary = (
                LlmResult.from_response_items(
                    response_items,
                    usage=result.usage,
                    finish_reason=result.finish_reason,
                    metadata=result.metadata,
                    structured_output=result.structured_output,
                )
                if response_items
                else result
            )
            stored.succeed(
                result_summary,
                response_items=response_items,
                continuation=continuation,
                provider_request_id=provider_request_id,
            )
            profile = uow.llm_profiles.get(stored.llm_id)
            stored.record_event(
                Event(
                    name="llm.invocation_succeeded",
                    payload=_invocation_succeeded_event_payload(
                        stored,
                        profile,
                        streaming=False,
                    ),
                ),
            )
            uow.llm_invocations.add(stored)
            uow.collect(stored)
            uow.commit()
            return stored

    def _fail_invocation(
        self,
        invocation_id: str,
        error: LlmErrorPayload,
        *,
        streaming: bool = False,
    ) -> LlmInvocation:
        with self.uow_factory() as uow:
            stored = uow.llm_invocations.get(invocation_id)
            if stored is None:
                raise LlmInvocationNotFoundError(
                    f"LLM invocation '{invocation_id}' was not found.",
                )
            stored.fail(error)
            profile = uow.llm_profiles.get(stored.llm_id)
            stored.record_event(
                Event(
                    name="llm.invocation_failed",
                    payload=_invocation_failed_event_payload(
                        stored,
                        profile,
                        error=error,
                        streaming=streaming,
                    ),
                ),
            )
            uow.llm_invocations.add(stored)
            uow.collect(stored)
            uow.commit()
            return stored

    async def _invoke_adapter_async(
        self,
        adapter: object,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> LlmAdapterResponse:
        invoke_async = getattr(adapter, "invoke_async", None)
        if callable(invoke_async):
            return await invoke_async(profile, request)
        invoke = getattr(adapter, "invoke", None)
        if callable(invoke):
            return await asyncio.to_thread(invoke, profile, request)
        raise LlmAdapterNotConfiguredError(
            f"No llm adapter is configured for api family '{profile.api_family.value}'.",
        )

    def _stream_adapter_async(
        self,
        adapter: object,
        profile: LlmProfile,
    ):
        stream_invoke_async = getattr(adapter, "stream_invoke_async", None)
        if callable(stream_invoke_async):
            return lambda request: stream_invoke_async(profile, request)
        stream_invoke = getattr(adapter, "stream_invoke", None)
        if callable(stream_invoke):
            return lambda request: self._iterate_sync_stream_async(
                stream_invoke(profile, request),
            )
        return None

    async def _iterate_sync_stream_async(
        self,
        iterator: Iterator[LlmStreamEvent],
    ) -> AsyncIterator[LlmStreamEvent]:
        sentinel = object()

        def _next_event() -> LlmStreamEvent | object:
            try:
                return next(iterator)
            except StopIteration:
                return sentinel

        while True:
            event = await asyncio.to_thread(_next_event)
            if event is sentinel:
                break
            yield event

    def _complete_stream_invocation(
        self,
        invocation_id: str,
        result: LlmResult,
        *,
        response_items: tuple[LlmResponseItem, ...] = (),
        continuation: LlmContinuationSignal | None = None,
        provider_request_id: str | None = None,
    ) -> LlmInvocation:
        with self.uow_factory() as uow:
            stored = uow.llm_invocations.get(invocation_id)
            if stored is None:
                raise LlmInvocationNotFoundError(
                    f"LLM invocation '{invocation_id}' was not found.",
                )
            result_summary = (
                LlmResult.from_response_items(
                    response_items,
                    usage=result.usage,
                    finish_reason=result.finish_reason,
                    metadata=result.metadata,
                    structured_output=result.structured_output,
                )
                if response_items
                else result
            )
            stored.succeed(
                result_summary,
                response_items=response_items,
                continuation=continuation,
                provider_request_id=provider_request_id,
            )
            profile = uow.llm_profiles.get(stored.llm_id)
            stored.record_event(
                Event(
                    name="llm.invocation_succeeded",
                    payload=_invocation_succeeded_event_payload(
                        stored,
                        profile,
                        streaming=True,
                    ),
                ),
            )
            uow.llm_invocations.add(stored)
            uow.collect(stored)
            uow.commit()
            return stored

    def _build_adapter_request(
        self,
        profile: LlmProfile,
        invocation: LlmInvocation,
        *,
        continuation: LlmProviderContinuation | None = None,
        runtime_context: Mapping[str, Any] | None = None,
        runtime_route: Mapping[str, Any] | None = None,
        runtime_policy: Mapping[str, Any] | None = None,
    ) -> LlmAdapterRequest:
        effective_runtime_context = (
            dict(runtime_context)
            if isinstance(runtime_context, Mapping) and runtime_context
            else runtime_request_context_from_metadata(invocation.request_metadata)
        )
        provider_transport = _provider_transport_for_request(
            invocation.request_overrides,
            continuation,
        )
        effective_runtime_route = (
            dict(runtime_route)
            if isinstance(runtime_route, Mapping) and runtime_route
            else _runtime_route_from_invocation(invocation, provider_transport)
        )
        effective_runtime_policy = (
            dict(runtime_policy)
            if isinstance(runtime_policy, Mapping) and runtime_policy
            else _runtime_policy_from_invocation(invocation)
        )
        return LlmAdapterRequest(
            invocation_id=invocation.id,
            messages=invocation.messages,
            input_items=invocation.input_items,
            provider_context_messages=invocation.provider_context_messages,
            tool_schemas=invocation.tool_schemas,
            response_format=invocation.response_format,
            request_policy=invocation.request_policy,
            overrides=invocation.request_overrides,
            request_metadata=invocation.request_metadata,
            runtime_context=effective_runtime_context,
            runtime_route=effective_runtime_route,
            runtime_policy=effective_runtime_policy,
            resolved_credential=self._resolve_profile_credential(profile),
            continuation=continuation,
            provider_transport=provider_transport,
        )

    def _provider_request_payload_preview(
        self,
        adapter: object,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> dict[str, object]:
        preview_request = getattr(adapter, "preview_request", None)
        if callable(preview_request):
            try:
                preview = preview_request(profile, request)
                if isinstance(preview, dict):
                    return dict(preview)
            except Exception as exc:
                return {
                    "preview_source": "provider_adapter",
                    "preview_error": str(exc) or type(exc).__name__,
                    "provider": profile.provider.value,
                    "api_family": profile.api_family.value,
                    "model": profile.model_name,
                }
        return {
            "preview_source": "normalized_fallback",
            "provider": profile.provider.value,
            "api_family": profile.api_family.value,
            "model": profile.model_name,
            "message_count": len(request.messages),
            "message_roles": [message.role.value for message in request.messages],
            "input_item_count": len(request.input_items),
            "input_item_kinds": [item.kind.value for item in request.input_items],
            "tool_count": len(request.tool_schemas),
            "response_format_configured": request.response_format is not None,
            "override_keys": sorted(str(key) for key in request.overrides),
            **_provider_input_preview_from_request_metadata(request.request_metadata),
        }

    def _record_provider_request_payload_preview(
        self,
        invocation_id: str,
        preview: dict[str, object],
    ) -> None:
        with self.uow_factory() as uow:
            stored = uow.llm_invocations.get(invocation_id)
            if stored is None:
                raise LlmInvocationNotFoundError(
                    f"LLM invocation '{invocation_id}' was not found.",
                )
            stored.record_provider_request_payload_preview(preview)
            profile = uow.llm_profiles.get(stored.llm_id)
            stored.record_event(
                Event(
                    name="llm.invocation_provider_request_prepared",
                    payload=_invocation_provider_request_prepared_event_payload(
                        stored,
                        profile,
                    ),
                ),
            )
            uow.llm_invocations.add(stored)
            uow.collect(stored)
            uow.commit()

    def _resolve_profile_credential(self, profile: LlmProfile) -> str | None:
        if self.credential_provider is None:
            return None
        binding_ref = credential_binding_ref_for_profile(profile)
        if binding_ref is None:
            return None
        return self.credential_provider.resolve_credential(
            binding_ref,
            consumer=AccessConsumerRef(
                consumer_id=f"llm.profile:{profile.id}",
                module="llm",
                component="adapter",
                runtime_ref=profile.api_family.value,
                metadata={
                    "provider": profile.provider.value,
                    "model_name": profile.model_name,
                },
            ),
        )

    def _record_profile_warmup_event(
        self,
        llm_id: str,
        event_name: str,
        payload: dict[str, Any],
    ) -> None:
        with self.uow_factory() as uow:
            profile = uow.llm_profiles.get(llm_id)
            if profile is None:
                return
            profile.record_event(Event(name=event_name, payload=payload))
            uow.llm_profiles.add(profile)
            uow.collect(profile)
            uow.commit()

    def _build_profile(self, data: RegisterLlmProfileInput) -> LlmProfile:
        self._validate_credential_binding_compatibility(data)
        return llm_profile_from_register_input(data)

    def _validate_credential_binding_compatibility(
        self,
        data: RegisterLlmProfileInput,
    ) -> None:
        inspector = getattr(self.credential_provider, "describe_credential_binding", None)
        if not callable(inspector):
            return
        expectation = _credential_expectation_for(data.provider, data.api_family)
        binding_id = _optional_string_config_value(data.credential_binding_id)
        if binding_id is None:
            if expectation["required"]:
                raise LlmValidationError(
                    f"LLM profile '{data.id}' requires {expectation['label']} credential binding.",
                )
            return
        metadata = inspector(binding_id)
        if metadata is None:
            raise LlmValidationError(
                f"LLM profile '{data.id}' references unknown Access credential binding '{binding_id}'.",
            )
        if not _credential_binding_matches_expectation(metadata, expectation["kind"]):
            actual = _credential_binding_type_label(metadata)
            raise LlmValidationError(
                f"LLM profile '{data.id}' expects {expectation['label']} credential binding, "
                f"but '{binding_id}' is {actual}.",
            )


def _credential_expectation_for(
    provider: LlmProviderKind,
    api_family: LlmApiFamily,
) -> dict[str, object]:
    if (
        provider is LlmProviderKind.OPENAI_CODEX
        or api_family is LlmApiFamily.OPENAI_CODEX_RESPONSES
    ):
        return {"kind": "oauth2_account", "label": "OAuth account", "required": True}
    if (
        provider in {
            LlmProviderKind.OPENAI,
            LlmProviderKind.ANTHROPIC,
            LlmProviderKind.GOOGLE,
        }
        or api_family
        in {
            LlmApiFamily.OPENAI_RESPONSES,
            LlmApiFamily.ANTHROPIC_MESSAGES,
            LlmApiFamily.GEMINI_GENERATE_CONTENT,
        }
    ):
        return {"kind": "api_key", "label": "API key", "required": True}
    if (
        provider is LlmProviderKind.OPENAI_COMPATIBLE
        or api_family is LlmApiFamily.OPENAI_CHAT_COMPATIBLE
    ):
        return {"kind": "optional_api_key", "label": "API key or none", "required": False}
    if provider is LlmProviderKind.OLLAMA or api_family is LlmApiFamily.OLLAMA_NATIVE:
        return {"kind": "none", "label": "no credential", "required": False}
    return {"kind": "any", "label": "Access credential", "required": False}


def _credential_binding_matches_expectation(
    metadata: Mapping[str, object],
    expectation_kind: object,
) -> bool:
    if expectation_kind == "any":
        return True
    if expectation_kind == "none":
        return False
    if expectation_kind == "oauth2_account":
        return _is_oauth_account_binding(metadata)
    if expectation_kind in {"api_key", "optional_api_key"}:
        return _is_api_key_binding(metadata)
    return True


def _is_api_key_binding(metadata: Mapping[str, object]) -> bool:
    if _is_oauth_account_binding(metadata):
        return False
    kind = _metadata_text(metadata, "binding_kind")
    return kind == "api_key"


def _is_oauth_account_binding(metadata: Mapping[str, object]) -> bool:
    return (
        _metadata_text(metadata, "source_kind") == "oauth_account"
        or _metadata_text(metadata, "binding_kind") == "oauth2_account"
        or _metadata_text(metadata, "binding_kind") == "openid_connect"
    )


def _credential_binding_type_label(metadata: Mapping[str, object]) -> str:
    if _is_oauth_account_binding(metadata):
        return "OAuth account"
    if _is_api_key_binding(metadata):
        return "API key"
    return (
        _metadata_text(metadata, "binding_kind")
        or _metadata_text(metadata, "source_kind")
        or "credential"
    )


def _metadata_text(metadata: Mapping[str, object], key: str) -> str:
    value = metadata.get(key)
    return str(value).strip().lower() if value is not None else ""


def _config_value(config: object, key: str, default: object = None) -> object:
    if isinstance(config, Mapping):
        return config.get(key, default)
    return getattr(config, key, default)


def _config_has(config: object, key: str) -> bool:
    if isinstance(config, Mapping):
        return key in config
    return hasattr(config, key)


def _coerce_provider_kind(value: object) -> LlmProviderKind:
    return value if isinstance(value, LlmProviderKind) else LlmProviderKind(str(value))


def _coerce_api_family(value: object) -> LlmApiFamily:
    return value if isinstance(value, LlmApiFamily) else LlmApiFamily(str(value))


def _coerce_model_family(value: object) -> LlmModelFamily:
    if value is None or (isinstance(value, str) and not value.strip()):
        return LlmModelFamily.GENERAL
    return value if isinstance(value, LlmModelFamily) else LlmModelFamily(str(value))


def _coerce_source_kind(value: object) -> LlmSourceKind:
    if value is None or (isinstance(value, str) and not value.strip()):
        return LlmSourceKind.IMPORTED
    return value if isinstance(value, LlmSourceKind) else LlmSourceKind(str(value))


def _capabilities_from_config_value(value: object) -> tuple[LlmCapability, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, LlmCapability)):
        value = (value,)
    return tuple(
        item if isinstance(item, LlmCapability) else LlmCapability(str(item))
        for item in value
    )


def _provider_transport_for_request(
    overrides: Mapping[str, Any],
    continuation: LlmProviderContinuation | None,
) -> str:
    if continuation is not None and continuation.transport is not None:
        return continuation.transport
    value = overrides.get("provider_transport")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "auto"


def _runtime_route_from_invocation(
    invocation: LlmInvocation,
    provider_transport: str,
) -> dict[str, Any]:
    route: dict[str, Any] = {
        "llm_id": invocation.llm_id,
        "provider_transport": provider_transport or "auto",
    }
    metadata = invocation.request_metadata
    for key in ("session_key", "active_session_id"):
        value = metadata.get(key) if isinstance(metadata, Mapping) else None
        if value not in (None, "", {}, []):
            route[key] = value
    return route


def _runtime_policy_from_invocation(
    invocation: LlmInvocation,
) -> dict[str, Any]:
    policy: dict[str, Any] = {}
    if invocation.request_policy:
        policy["transcript_policy"] = dict(invocation.request_policy)
    reasoning = invocation.request_overrides.get("reasoning")
    if isinstance(reasoning, Mapping) and reasoning:
        policy["reasoning"] = dict(reasoning)
    if invocation.response_format:
        policy["response_format"] = dict(invocation.response_format)
    if invocation.request_overrides:
        policy["provider_option_keys"] = sorted(
            str(key) for key in invocation.request_overrides
        )
    return policy


def _provider_input_preview_from_request_metadata(
    request_metadata: dict[str, Any] | None,
) -> dict[str, object]:
    if not isinstance(request_metadata, dict):
        return {}
    request_render_snapshot = request_metadata.get("request_render_snapshot")
    tool_surface = request_metadata.get("tool_surface")
    preview: dict[str, object] = {}
    if isinstance(request_render_snapshot, dict):
        preview_request_render_snapshot = request_render_snapshot_preview_payload(request_render_snapshot)
        request_render_snapshot_id = _optional_preview_text(
            request_render_snapshot.get("snapshot_id"),
        )
        if request_render_snapshot_id is not None:
            preview["request_render_snapshot_id"] = request_render_snapshot_id
        context_schema = _optional_preview_text(
            request_render_snapshot.get("tree_schema_version"),
        )
        if context_schema is not None:
            preview["request_render_snapshot_schema_version"] = context_schema
        included_node_ids = request_render_snapshot.get("included_node_ids")
        if isinstance(included_node_ids, list | tuple):
            preview["request_render_snapshot_included_node_count"] = len(
                included_node_ids,
            )
        preview["request_render_snapshot_fingerprint"] = _stable_preview_fingerprint(
            preview_request_render_snapshot,
        )
    if isinstance(tool_surface, dict):
        tool_surface_id = _optional_preview_text(tool_surface.get("id"))
        if tool_surface_id is not None:
            preview["tool_surface_id"] = tool_surface_id
        functions = tool_surface.get("functions")
        if isinstance(functions, list | tuple):
            preview["tool_surface_function_count"] = len(functions)
        mirrored_schema_names = tool_surface.get("mirrored_schema_names")
        if isinstance(mirrored_schema_names, list | tuple):
            preview["tool_surface_mirrored_schema_count"] = len(mirrored_schema_names)
        preview["tool_surface_fingerprint"] = _stable_preview_fingerprint(tool_surface)
    for key in (
        "request_render_snapshot_id",
        "tool_surface_snapshot_id",
        "tool_surface_function_count",
        "tool_surface_mirrored_schema_count",
    ):
        value = request_metadata.get(key)
        if key not in preview and value not in (None, "", {}, []):
            preview[key] = value
    return preview


def _stable_preview_fingerprint(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _optional_preview_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _capabilities_for_profile_config(
    config: LlmProfileImportLike | Mapping[str, Any],
) -> tuple[LlmCapability, ...]:
    capabilities = list(
        _capabilities_from_config_value(_config_value(config, "capabilities", ())),
    )
    api_family = _coerce_api_family(_config_value(config, "api_family"))
    if (
        api_family is LlmApiFamily.OPENAI_RESPONSES
        and LlmCapability.PROVIDER_NATIVE_CONTINUATION not in capabilities
    ):
        capabilities.append(LlmCapability.PROVIDER_NATIVE_CONTINUATION)
    if (
        api_family is LlmApiFamily.OPENAI_CODEX_RESPONSES
        and LlmCapability.PROVIDER_WEBSOCKET_TRANSPORT in capabilities
        and LlmCapability.PROVIDER_INCREMENTAL_INPUT in capabilities
        and LlmCapability.PROVIDER_NATIVE_CONTINUATION not in capabilities
    ):
        capabilities.append(LlmCapability.PROVIDER_NATIVE_CONTINUATION)
    return tuple(dict.fromkeys(capabilities))


def _defaults_from_config_value(value: object) -> LlmDefaults:
    if value is None:
        return LlmDefaults()
    if isinstance(value, LlmDefaults):
        return value
    if isinstance(value, Mapping):
        return LlmDefaults.from_payload(dict(value))
    to_payload = getattr(value, "to_payload", None)
    if callable(to_payload):
        payload = to_payload()
        if isinstance(payload, Mapping):
            return LlmDefaults.from_payload(dict(payload))

    payload: dict[str, Any] = {}
    for field_name in (
        "temperature",
        "top_p",
        "max_output_tokens",
        "reasoning_effort",
    ):
        field_value = getattr(value, field_name, None)
        if field_value is not None:
            payload[field_name] = field_value
    extra_body = getattr(value, "extra_body", None)
    if isinstance(extra_body, Mapping):
        payload["extra_body"] = dict(extra_body)
    return LlmDefaults.from_payload(payload)


def _credential_binding_id_from_config_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        binding_id = _optional_string_config_value(value)
        if binding_id is not None and _is_forbidden_credential_binding_id(binding_id):
            raise ValueError(
                "LLM credential_binding_id must reference an Access credential binding id.",
            )
        return binding_id
    raise TypeError("LLM credential_binding_id must be an Access credential binding id string.")


def _is_forbidden_credential_binding_id(value: str) -> bool:
    normalized = value.strip()
    return (
        normalized.startswith(_forbidden_credential_binding_prefixes)
        or normalized in _forbidden_credential_binding_ids
        or normalized.startswith(_forbidden_credential_binding_id_prefixes)
    )


def _optional_string_config_value(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _int_config_value(value: object, *, default: int) -> int:
    if value is None:
        return default
    return int(value)


def _optional_int_config_value(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return int(value)


def _bool_config_value(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def credential_binding_ref_for_profile(
    profile: LlmProfile,
) -> CredentialBindingRef | None:
    binding_id = _optional_string_config_value(profile.credential_binding_id)
    if binding_id is None:
        return None
    return CredentialBindingRef(
        binding_id=binding_id,
        source_type="access_credential_binding",
        source_ref=binding_id,
        metadata={
            "module": "llm",
            "profile_id": profile.id,
            "provider": profile.provider.value,
            "api_family": profile.api_family.value,
        },
    )


def _invocation_started_event_payload(
    invocation: LlmInvocation,
    profile: LlmProfile,
    *,
    streaming: bool,
) -> dict[str, Any]:
    return {
        "invocation_id": invocation.id,
        "llm_id": invocation.llm_id,
        "provider": profile.provider.value,
        "api_family": profile.api_family.value,
        "model_name": profile.model_name,
        "model_family": profile.model_family.value,
        "concurrency_key": profile.concurrency_key or f"profile:{profile.id}",
        "max_concurrency": profile.max_concurrency,
        "timeout_seconds": profile.timeout_seconds,
        "streaming": streaming,
        "message_count": len(invocation.messages),
        "input_item_count": len(invocation.input_items),
        "input_item_kinds": [item.kind.value for item in invocation.input_items],
        "provider_context_message_count": len(invocation.provider_context_messages),
        "provider_context_message_kinds": _provider_context_message_kinds(
            invocation.provider_context_messages,
        ),
        "tool_schema_count": len(invocation.tool_schemas),
        "response_format_configured": invocation.response_format is not None,
        "runtime_request_summary": _runtime_request_summary(invocation),
        "request_metadata": dict(invocation.request_metadata),
    }


def _invocation_provider_request_prepared_event_payload(
    invocation: LlmInvocation,
    profile: LlmProfile | None,
) -> dict[str, Any]:
    preview = dict(invocation.provider_request_payload_preview)
    payload: dict[str, Any] = {
        "invocation_id": invocation.id,
        "llm_id": invocation.llm_id,
        "runtime_request_summary": _runtime_request_summary(invocation),
        "request_metadata": dict(invocation.request_metadata),
        "provider_request_payload_preview": preview,
    }
    transport = preview.get("transport")
    if transport is not None:
        payload["transport"] = transport
    has_previous_response_id = preview.get("has_previous_response_id")
    if isinstance(has_previous_response_id, bool):
        payload["has_previous_response_id"] = has_previous_response_id
    input_delta_mode = preview.get("input_delta_mode")
    if isinstance(input_delta_mode, bool):
        payload["input_delta_mode"] = input_delta_mode
    for key in ("input_baseline_count", "input_delta_count", "tool_count"):
        value = preview.get(key)
        if isinstance(value, int):
            payload[key] = value
    if profile is not None:
        payload.update(
            {
                "provider": profile.provider.value,
                "api_family": profile.api_family.value,
                "model_name": profile.model_name,
                "model_family": profile.model_family.value,
                "concurrency_key": profile.concurrency_key or f"profile:{profile.id}",
            },
        )
    return payload


def _runtime_request_summary(invocation: LlmInvocation) -> dict[str, Any]:
    metadata = dict(invocation.request_metadata)
    summary: dict[str, Any] = {
        "message_count": len(invocation.messages),
        "input_item_count": len(invocation.input_items),
        "input_item_kinds": [item.kind.value for item in invocation.input_items],
        "provider_context_message_count": len(invocation.provider_context_messages),
        "provider_context_message_kinds": _provider_context_message_kinds(
            invocation.provider_context_messages,
        ),
        "tool_schema_count": len(invocation.tool_schemas),
        "response_format_configured": invocation.response_format is not None,
    }
    for key in (
        "request_render_snapshot_id",
        "input_mode",
        "runtime_contract_version",
        "runtime_contract_hash",
        "direct_session_item_count",
        "tool_surface_id",
        "tool_surface_snapshot_id",
        "tool_surface_function_count",
        "tool_surface_mirrored_schema_count",
    ):
        value = metadata.get(key)
        if value not in (None, "", {}, []):
            summary[key] = value
    request_render_snapshot = metadata.get("request_render_snapshot")
    if isinstance(request_render_snapshot, Mapping):
        preview_request_render_snapshot = request_render_snapshot_preview_payload(
            request_render_snapshot,
        )
        if preview_request_render_snapshot:
            summary["request_render_snapshot"] = preview_request_render_snapshot
    tool_surface = metadata.get("tool_surface")
    if isinstance(tool_surface, Mapping):
        tool_summary = _tool_surface_summary(tool_surface)
        if tool_summary:
            summary["tool_surface"] = tool_summary
    return {
        key: value
        for key, value in summary.items()
        if value not in (None, "", {}, [])
    }


def _tool_surface_summary(tool_surface: Mapping[str, object]) -> dict[str, object]:
    summary: dict[str, object] = {}
    surface_id = _optional_preview_text(tool_surface.get("id"))
    if surface_id is not None:
        summary["id"] = surface_id
    functions = tool_surface.get("functions")
    if isinstance(functions, list | tuple):
        summary["function_count"] = len(functions)
    mirrored_schema_names = tool_surface.get("mirrored_schema_names")
    if isinstance(mirrored_schema_names, list | tuple):
        summary["mirrored_schema_count"] = len(mirrored_schema_names)
    blocked_access_count = tool_surface.get("blocked_access_count")
    if isinstance(blocked_access_count, int):
        summary["blocked_access_count"] = blocked_access_count
    return summary


def _provider_context_message_kinds(
    messages: tuple[LlmMessage, ...],
) -> list[str]:
    kinds: list[str] = []
    for message in messages:
        kind = str(message.metadata.get("provider_context_kind", "")).strip()
        if kind and kind not in kinds:
            kinds.append(kind)
    return kinds


def _profile_warmup_event_payload(
    profile: LlmProfile,
    *,
    status: str,
    details: Mapping[str, Any],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "llm_id": profile.id,
        "provider": profile.provider.value,
        "api_family": profile.api_family.value,
        "model_name": profile.model_name,
        "model_family": profile.model_family.value,
        "status": status,
        "details": dict(details),
    }
    transport = details.get("transport")
    if transport is not None:
        payload["transport"] = transport
    endpoint = details.get("endpoint")
    if endpoint is not None:
        payload["endpoint"] = endpoint
    reused_connection = details.get("reused_connection")
    if isinstance(reused_connection, bool):
        payload["reused_connection"] = reused_connection
    reason = details.get("reason")
    if reason is not None:
        payload["reason"] = str(reason)
    return payload


def _invocation_succeeded_event_payload(
    invocation: LlmInvocation,
    profile: LlmProfile | None,
    *,
    streaming: bool,
) -> dict[str, Any]:
    payload = _invocation_terminal_base_payload(
        invocation,
        profile,
        streaming=streaming,
    )
    if invocation.result is not None:
        response_text = invocation.result.text or ""
        payload["finish_reason"] = invocation.result.finish_reason
        payload["text_present"] = bool(response_text.strip())
        payload["text_chars"] = len(response_text)
        payload["tool_call_count"] = len(invocation.result.tool_calls)
        if invocation.result.tool_calls:
            payload["tool_call_names"] = [
                tool_call.name for tool_call in invocation.result.tool_calls
            ]
        if invocation.result.usage is not None:
            payload["usage"] = invocation.result.usage.to_payload()
    return payload


def _result_summary_from_adapter_response(
    response: LlmAdapterResponse,
) -> LlmResult:
    if not response.response_items:
        return response.result
    return LlmResult.from_response_items(
        response.response_items,
        usage=response.result.usage,
        finish_reason=response.result.finish_reason,
        metadata=response.result.metadata,
        structured_output=response.result.structured_output,
    )


def _response_items_from_completed_payload(
    payload: Mapping[str, Any],
) -> tuple[LlmResponseItem, ...]:
    raw_items = payload.get("response_items")
    if not isinstance(raw_items, (list, tuple)):
        return ()
    items: list[LlmResponseItem] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        items.append(LlmResponseItem.from_payload(raw_item))
    return tuple(items)


def _continuation_from_completed_payload(
    payload: Mapping[str, Any],
) -> LlmContinuationSignal | None:
    raw_continuation = payload.get("continuation")
    if not isinstance(raw_continuation, dict):
        return None
    return LlmContinuationSignal.from_payload(raw_continuation)


def _invocation_failed_event_payload(
    invocation: LlmInvocation,
    profile: LlmProfile | None,
    *,
    error: LlmErrorPayload,
    streaming: bool,
) -> dict[str, Any]:
    payload = _invocation_terminal_base_payload(
        invocation,
        profile,
        streaming=streaming,
    )
    payload.update(
        {
            "error_code": error.code,
            "error_family": _llm_error_family(error.code),
            "retryable": _llm_error_retryable(error.code),
            "error_message": error.message,
        },
    )
    if error.details:
        payload["error_details"] = dict(error.details)
    return payload


def _invocation_terminal_base_payload(
    invocation: LlmInvocation,
    profile: LlmProfile | None,
    *,
    streaming: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "invocation_id": invocation.id,
        "llm_id": invocation.llm_id,
        "provider_request_id": invocation.provider_request_id,
        "duration_seconds": _invocation_duration_seconds(invocation),
        "streaming": streaming,
        "request_metadata": dict(invocation.request_metadata),
        "provider_request_payload_preview": dict(
            invocation.provider_request_payload_preview,
        ),
    }
    if profile is not None:
        payload.update(
            {
                "provider": profile.provider.value,
                "api_family": profile.api_family.value,
                "model_name": profile.model_name,
                "model_family": profile.model_family.value,
                "concurrency_key": profile.concurrency_key or f"profile:{profile.id}",
            },
        )
    return payload


def _invocation_duration_seconds(invocation: LlmInvocation) -> float | None:
    if invocation.started_at is None or invocation.completed_at is None:
        return None
    return max((invocation.completed_at - invocation.started_at).total_seconds(), 0.0)


def _coerce_response_event_type(event_type: str) -> LlmResponseEventType:
    try:
        return LlmResponseEventType(event_type)
    except ValueError:
        if event_type == "text_delta":
            return LlmResponseEventType.TEXT_DELTA
        if event_type == "completed":
            return LlmResponseEventType.COMPLETED
        if event_type == "failed":
            return LlmResponseEventType.FAILED
        if event_type == "invocation_started":
            return LlmResponseEventType.INVOCATION_STARTED
        return LlmResponseEventType.ITEM_COMPLETED


def _llm_error_family(error_code: str) -> str:
    text = error_code.lower()
    if any(token in text for token in ("rate", "quota", "429")):
        return "rate_limit"
    if any(token in text for token in ("auth", "access", "credential", "401", "403")):
        return "auth"
    if "timeout" in text:
        return "timeout"
    if any(token in text for token in ("context", "token", "length")):
        return "context_length"
    if any(token in text for token in ("unavailable", "connection", "provider", "503")):
        return "provider_down"
    if any(token in text for token in ("bad_request", "validation", "400")):
        return "bad_request"
    return "adapter_error"


def _llm_error_retryable(error_code: str) -> bool:
    return _llm_error_family(error_code) in {"rate_limit", "timeout", "provider_down"}
