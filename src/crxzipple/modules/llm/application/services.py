from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol
from uuid import uuid4

from crxzipple.modules.llm.application.adapters import (
    LlmAdapterGateway,
    LlmAdapterRequest,
)
from crxzipple.modules.llm.application.streaming import LlmStreamEvent
from crxzipple.modules.llm.domain.entities import LlmInvocation, LlmProfile
from crxzipple.modules.llm.domain.exceptions import (
    LlmAdapterNotConfiguredError,
    LlmAlreadyExistsError,
    LlmInvocationNotAllowedError,
    LlmInvocationNotFoundError,
    LlmNotFoundError,
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
from crxzipple.shared.domain.events import DomainEvent


@dataclass(frozen=True, slots=True)
class RegisterLlmProfileInput:
    id: str
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


@dataclass(frozen=True, slots=True)
class InvokeLlmInput:
    llm_id: str
    messages: tuple[LlmMessage, ...]
    tool_schemas: tuple[ToolSchema, ...] = field(default_factory=tuple)
    response_format: dict[str, Any] | None = None
    overrides: dict[str, Any] = field(default_factory=dict)
    invocation_id: str | None = None


@dataclass(frozen=True, slots=True)
class StreamLlmInput:
    llm_id: str
    messages: tuple[LlmMessage, ...]
    tool_schemas: tuple[ToolSchema, ...] = field(default_factory=tuple)
    response_format: dict[str, Any] | None = None
    overrides: dict[str, Any] = field(default_factory=dict)
    invocation_id: str | None = None


class LlmUnitOfWork(Protocol):
    llm_profiles: LlmProfileRepository
    llm_invocations: LlmInvocationRepository

    def __enter__(self) -> "LlmUnitOfWork":
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        ...

    def collect(self, aggregate: AggregateRoot[Any]) -> None:
        ...

    def commit(self) -> None:
        ...

    def rollback(self) -> None:
        ...


class LlmApplicationService:
    def __init__(
        self,
        uow_factory: Callable[[], LlmUnitOfWork],
        adapter_gateway: LlmAdapterGateway,
    ) -> None:
        self.uow_factory = uow_factory
        self.adapter_gateway = adapter_gateway

    def register_profile(self, data: RegisterLlmProfileInput) -> LlmProfile:
        with self.uow_factory() as uow:
            if uow.llm_profiles.get(data.id) is not None:
                raise LlmAlreadyExistsError(f"LLM profile '{data.id}' already exists.")

            profile = LlmProfile(
                id=data.id,
                provider=data.provider,
                api_family=data.api_family,
                model_name=data.model_name,
                model_family=data.model_family,
                capabilities=data.capabilities,
                default_params=data.default_params,
                base_url=data.base_url,
                credential_binding=data.credential_binding,
                timeout_seconds=data.timeout_seconds,
                source_kind=data.source_kind,
                enabled=data.enabled,
            )
            profile.record_event(
                DomainEvent(
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

    def get_profile(self, llm_id: str) -> LlmProfile:
        with self.uow_factory() as uow:
            profile = uow.llm_profiles.get(llm_id)
            if profile is None:
                raise LlmNotFoundError(f"LLM profile '{llm_id}' was not found.")
            return profile

    def list_profiles(self) -> list[LlmProfile]:
        with self.uow_factory() as uow:
            return uow.llm_profiles.list()

    def sync_profiles(
        self,
        profiles: tuple[RegisterLlmProfileInput, ...],
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
                profile.record_event(
                    DomainEvent(
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
        )
        invocation.start()
        invocation.record_event(
            DomainEvent(
                name="llm.invocation_started",
                payload={
                    "invocation_id": invocation.id,
                    "llm_id": invocation.llm_id,
                    "api_family": profile.api_family.value,
                },
            ),
        )

        with self.uow_factory() as uow:
            uow.llm_invocations.add(invocation)
            uow.collect(invocation)
            uow.commit()

        request = LlmAdapterRequest(
            messages=invocation.messages,
            tool_schemas=invocation.tool_schemas,
            response_format=invocation.response_format,
            overrides=invocation.request_overrides,
        )

        try:
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
                DomainEvent(
                    name="llm.invocation_succeeded",
                    payload={
                        "invocation_id": stored.id,
                        "llm_id": stored.llm_id,
                    },
                ),
            )
            uow.llm_invocations.add(stored)
            uow.collect(stored)
            uow.commit()
            return stored

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
        )
        invocation.start()
        invocation.record_event(
            DomainEvent(
                name="llm.invocation_started",
                payload={
                    "invocation_id": invocation.id,
                    "llm_id": invocation.llm_id,
                    "api_family": profile.api_family.value,
                    "streaming": True,
                },
            ),
        )

        with self.uow_factory() as uow:
            uow.llm_invocations.add(invocation)
            uow.collect(invocation)
            uow.commit()

        request = LlmAdapterRequest(
            messages=invocation.messages,
            tool_schemas=invocation.tool_schemas,
            response_format=invocation.response_format,
            overrides=invocation.request_overrides,
        )

        def _generator() -> Iterator[LlmStreamEvent]:
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
                        provider_request_id = normalized_event.data.get("provider_request_id")
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
                failed = self._fail_invocation(
                    invocation.id,
                    LlmErrorPayload(
                        message=str(exc) or type(exc).__name__,
                        code="adapter_error",
                    ),
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

    def get_invocation(self, invocation_id: str) -> LlmInvocation:
        with self.uow_factory() as uow:
            invocation = uow.llm_invocations.get(invocation_id)
            if invocation is None:
                raise LlmInvocationNotFoundError(
                    f"LLM invocation '{invocation_id}' was not found.",
                )
            return invocation

    def list_invocations(self, *, llm_id: str | None = None) -> list[LlmInvocation]:
        with self.uow_factory() as uow:
            return uow.llm_invocations.list(llm_id=llm_id)

    def _fail_invocation(
        self,
        invocation_id: str,
        error: LlmErrorPayload,
    ) -> LlmInvocation:
        with self.uow_factory() as uow:
            stored = uow.llm_invocations.get(invocation_id)
            if stored is None:
                raise LlmInvocationNotFoundError(
                    f"LLM invocation '{invocation_id}' was not found.",
                )
            stored.fail(error)
            stored.record_event(
                DomainEvent(
                    name="llm.invocation_failed",
                    payload={
                        "invocation_id": stored.id,
                        "llm_id": stored.llm_id,
                        "error_code": error.code,
                    },
                ),
            )
            uow.llm_invocations.add(stored)
            uow.collect(stored)
            uow.commit()
            return stored

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
            stored.record_event(
                DomainEvent(
                    name="llm.invocation_succeeded",
                    payload={
                        "invocation_id": stored.id,
                        "llm_id": stored.llm_id,
                        "streaming": True,
                    },
                ),
            )
            uow.llm_invocations.add(stored)
            uow.collect(stored)
            uow.commit()
            return stored

    @staticmethod
    def _build_profile(data: RegisterLlmProfileInput) -> LlmProfile:
        return LlmProfile(
            id=data.id,
            provider=data.provider,
            api_family=data.api_family,
            model_name=data.model_name,
            model_family=data.model_family,
            capabilities=data.capabilities,
            default_params=data.default_params,
            base_url=data.base_url,
            credential_binding=data.credential_binding,
            timeout_seconds=data.timeout_seconds,
            source_kind=data.source_kind,
            enabled=data.enabled,
        )
