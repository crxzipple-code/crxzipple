from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
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
    credential_binding: str | None = None
    timeout_seconds: int = 60
    max_concurrency: int | None = None
    concurrency_key: str | None = None
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
        *,
        concurrency_limiter: LlmConcurrencyLimiter | None = None,
    ) -> None:
        self.uow_factory = uow_factory
        self.adapter_gateway = adapter_gateway
        self.concurrency_limiter = concurrency_limiter or LlmConcurrencyLimiter()

    def register_profile(self, data: RegisterLlmProfileInput) -> LlmProfile:
        with self.uow_factory() as uow:
            if uow.llm_profiles.get(data.id) is not None:
                raise LlmAlreadyExistsError(f"LLM profile '{data.id}' already exists.")

            profile = LlmProfile(
                id=data.id,
                provider=data.provider,
                api_family=data.api_family,
                model_name=data.model_name,
                context_window_tokens=data.context_window_tokens,
                model_family=data.model_family,
                capabilities=data.capabilities,
                default_params=data.default_params,
                base_url=data.base_url,
                credential_binding=data.credential_binding,
                timeout_seconds=data.timeout_seconds,
                max_concurrency=data.max_concurrency,
                concurrency_key=data.concurrency_key,
                source_kind=data.source_kind,
                enabled=data.enabled,
            )
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

        request = LlmAdapterRequest(
            messages=invocation.messages,
            tool_schemas=invocation.tool_schemas,
            response_format=invocation.response_format,
            overrides=invocation.request_overrides,
        )

        try:
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

        request = LlmAdapterRequest(
            messages=invocation.messages,
            tool_schemas=invocation.tool_schemas,
            response_format=invocation.response_format,
            overrides=invocation.request_overrides,
        )

        try:
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

        request = LlmAdapterRequest(
            messages=invocation.messages,
            tool_schemas=invocation.tool_schemas,
            response_format=invocation.response_format,
            overrides=invocation.request_overrides,
        )

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
                                "error": failed.error.to_payload()
                                if failed.error
                                else {},
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

        request = LlmAdapterRequest(
            messages=invocation.messages,
            tool_schemas=invocation.tool_schemas,
            response_format=invocation.response_format,
            overrides=invocation.request_overrides,
        )

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

    @staticmethod
    def _build_profile(data: RegisterLlmProfileInput) -> LlmProfile:
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
            credential_binding=data.credential_binding,
            timeout_seconds=data.timeout_seconds,
            max_concurrency=data.max_concurrency,
            concurrency_key=data.concurrency_key,
            source_kind=data.source_kind,
            enabled=data.enabled,
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
        payload["finish_reason"] = invocation.result.finish_reason
        payload["tool_call_count"] = len(invocation.result.tool_calls)
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
