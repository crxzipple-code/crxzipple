from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol
from uuid import uuid4

from crxzipple.modules.llm.application.adapters import (
    LlmAdapterGateway,
    LlmAdapterRequest,
    LlmAdapterResponse,
)
from crxzipple.modules.llm.application.concurrency import LlmConcurrencyLimiter
from crxzipple.modules.llm.application.streaming import LlmStreamEvent
from crxzipple.modules.llm.domain.entities import LlmInvocation, LlmProfile
from crxzipple.modules.llm.domain.exceptions import (
    LlmAdapterNotConfiguredError,
    LlmAlreadyExistsError,
    LlmInvocationNotAllowedError,
    LlmInvocationNotFoundError,
    LlmNotFoundError,
    LlmValidationError,
)
from crxzipple.modules.llm.domain.repositories import (
    LlmInvocationRepository,
    LlmProfileRepository,
)
from crxzipple.modules.llm.domain.value_objects import (
    LlmApiFamily,
    LlmCapability,
    LlmDefaults,
    LlmErrorPayload,
    LlmMessage,
    LlmModelFamily,
    LlmProviderKind,
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
    tool_schemas: tuple[ToolSchema, ...] = field(default_factory=tuple)
    response_format: dict[str, Any] | None = None
    overrides: dict[str, Any] = field(default_factory=dict)
    request_metadata: dict[str, Any] = field(default_factory=dict)
    invocation_id: str | None = None


@dataclass(frozen=True, slots=True)
class StreamLlmInput:
    llm_id: str
    messages: tuple[LlmMessage, ...]
    tool_schemas: tuple[ToolSchema, ...] = field(default_factory=tuple)
    response_format: dict[str, Any] | None = None
    overrides: dict[str, Any] = field(default_factory=dict)
    request_metadata: dict[str, Any] = field(default_factory=dict)
    invocation_id: str | None = None


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
        capabilities=_capabilities_from_config_value(
            _config_value(config, "capabilities", ()),
        ),
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
            tool_schemas=data.tool_schemas,
            response_format=data.response_format,
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
            request = self._build_adapter_request(profile, invocation)
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
                response.result,
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
            tool_schemas=data.tool_schemas,
            response_format=data.response_format,
            request_overrides=data.overrides,
            request_metadata=data.request_metadata,
        )
        invocation.start()

        try:
            request = self._build_adapter_request(profile, invocation)
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
            response.result,
            provider_request_id=response.provider_request_id,
        )
        return invocation

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
            tool_schemas=data.tool_schemas,
            response_format=data.response_format,
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
            request = self._build_adapter_request(profile, invocation)
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
            response.result,
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
            tool_schemas=data.tool_schemas,
            response_format=data.response_format,
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
                sequence += 1

                try:
                    request = self._build_adapter_request(profile, invocation)
                    for event in stream_invoke(profile, request):
                        normalized_event = LlmStreamEvent(
                            type=event.type,
                            sequence=sequence,
                            invocation_id=invocation.id,
                            data=dict(event.data),
                        )
                        sequence += 1

                        if normalized_event.type == "completed":
                            result_payload = normalized_event.data.get("result")
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
            tool_schemas=data.tool_schemas,
            response_format=data.response_format,
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
            sequence += 1

            try:
                request = self._build_adapter_request(profile, invocation)
                async for event in stream(request):
                    normalized_event = LlmStreamEvent(
                        type=event.type,
                        sequence=sequence,
                        invocation_id=invocation.id,
                        data=dict(event.data),
                    )
                    sequence += 1

                    if normalized_event.type == "completed":
                        result_payload = normalized_event.data.get("result")
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

    def get_invocation(self, invocation_id: str) -> LlmInvocation:
        with self.uow_factory() as uow:
            invocation = uow.llm_invocations.get(invocation_id)
            if invocation is None:
                raise LlmInvocationNotFoundError(
                    f"LLM invocation '{invocation_id}' was not found.",
                )
            return invocation

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
        provider_request_id: str | None = None,
    ) -> LlmInvocation:
        with self.uow_factory() as uow:
            stored = uow.llm_invocations.get(invocation_id)
            if stored is None:
                raise LlmInvocationNotFoundError(
                    f"LLM invocation '{invocation_id}' was not found.",
                )
            stored.succeed(result, provider_request_id=provider_request_id)
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
        provider_request_id: str | None = None,
    ) -> LlmInvocation:
        with self.uow_factory() as uow:
            stored = uow.llm_invocations.get(invocation_id)
            if stored is None:
                raise LlmInvocationNotFoundError(
                    f"LLM invocation '{invocation_id}' was not found.",
                )
            stored.succeed(result, provider_request_id=provider_request_id)
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
    ) -> LlmAdapterRequest:
        return LlmAdapterRequest(
            messages=invocation.messages,
            tool_schemas=invocation.tool_schemas,
            response_format=invocation.response_format,
            overrides=invocation.request_overrides,
            resolved_credential=self._resolve_profile_credential(profile),
        )

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
        "tool_schema_count": len(invocation.tool_schemas),
        "response_format_configured": invocation.response_format is not None,
        "request_metadata": dict(invocation.request_metadata),
    }


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
