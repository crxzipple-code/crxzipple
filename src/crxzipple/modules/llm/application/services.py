from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from typing import Any, Callable, Protocol

from crxzipple.modules.llm.application.adapters import (
    LlmAdapterGateway,
)
from crxzipple.modules.llm.application.concurrency import LlmConcurrencyLimiter
from crxzipple.modules.llm.application.llm_adapter_request_builder import (
    LlmAdapterRequestBuilder,
)
from crxzipple.modules.llm.application.llm_invocation_inputs import (
    InvokeLlmInput,
    StreamLlmInput,
    WarmupLlmProfileInput,
    WarmupLlmProfileResult,
)
from crxzipple.modules.llm.application.llm_invocation_runner import (
    LlmInvocationRunner,
)
from crxzipple.modules.llm.application.llm_streaming_invocation_runner import (
    LlmStreamingInvocationRunner,
)
from crxzipple.modules.llm.application.llm_invocation_events import (
    invocation_provider_request_prepared_event_payload,
)
from crxzipple.modules.llm.application.llm_invocation_terminal_events import (
    invocation_failed_event_payload,
    invocation_succeeded_event_payload,
)
from crxzipple.modules.llm.application.llm_profile_service import (
    LlmProfileService,
)
from crxzipple.modules.llm.application.llm_profile_warmup import (
    LlmProfileWarmupService,
)
from crxzipple.modules.llm.application.llm_profile_config import RegisterLlmProfileInput
from crxzipple.modules.llm.application.llm_invocation_service import (
    LlmInvocationService,
)
from crxzipple.modules.llm.application.llm_streaming_completion_recorder import (
    LlmStreamingCompletionRecorder,
)
from crxzipple.modules.llm.application.llm_streaming_event_recorder import (
    LlmStreamingEventRecorder,
)
from crxzipple.modules.llm.application.provider_request_preview_recorder import (
    ProviderRequestPreviewRecorder,
)
from crxzipple.modules.llm.application.streaming import LlmStreamEvent
from crxzipple.modules.llm.domain.entities import LlmInvocation, LlmProfile
from crxzipple.modules.llm.domain.exceptions import (
    LlmAdapterNotConfiguredError,
)
from crxzipple.modules.llm.domain.repositories import (
    LlmInvocationRepository,
    LlmProfileRepository,
)
from crxzipple.modules.llm.domain import (
    LlmResponseEventRetentionPolicy,
    LlmResponseEvent,
    LlmResponseItem,
)
from crxzipple.shared.domain.aggregates import AggregateRoot
from crxzipple.shared.access import (
    CredentialProvider,
)

DEFAULT_RESPONSE_EVENT_RETENTION_POLICY = LlmResponseEventRetentionPolicy(
    full_event_window_seconds=86_400,
    detail_event_limit=100,
    durable_fact="completed_response_items",
    overflow_action="prefer_response_items_and_request_preview",
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
        self._credential_provider: CredentialProvider | None = None
        self.credential_provider = credential_provider
        self.profile_service = LlmProfileService(
            self.uow_factory,
            credential_provider=self.credential_provider,
        )
        self.invocation_service = LlmInvocationService(
            self.uow_factory,
            response_event_retention_policy=DEFAULT_RESPONSE_EVENT_RETENTION_POLICY,
            succeeded_payload_builder=(
                lambda invocation, profile, streaming: invocation_succeeded_event_payload(
                    invocation,
                    profile,
                    streaming=streaming,
                )
            ),
            failed_payload_builder=(
                lambda invocation, profile, error, streaming: invocation_failed_event_payload(
                    invocation,
                    profile,
                    error=error,
                    streaming=streaming,
                )
            ),
        )
        self.streaming_completion_recorder = LlmStreamingCompletionRecorder(
            self.invocation_service,
        )
        self.streaming_event_recorder = LlmStreamingEventRecorder(
            invocation_service=self.invocation_service,
            streaming_completion_recorder=self.streaming_completion_recorder,
        )
        self.provider_request_preview_recorder = ProviderRequestPreviewRecorder(
            self.uow_factory,
            event_payload_builder=invocation_provider_request_prepared_event_payload,
        )
        self.adapter_request_builder = LlmAdapterRequestBuilder(
            credential_provider=self.credential_provider,
        )
        self.profile_warmup_service = LlmProfileWarmupService(
            self.uow_factory,
            adapter_gateway=self.adapter_gateway,
            adapter_request_builder=self.adapter_request_builder,
        )
        self.invocation_runner = LlmInvocationRunner(
            invocation_service=self.invocation_service,
            adapter_request_builder=self.adapter_request_builder,
            provider_request_preview_recorder=self.provider_request_preview_recorder,
            concurrency_limiter=self.concurrency_limiter,
        )
        self.streaming_invocation_runner = LlmStreamingInvocationRunner(
            invocation_service=self.invocation_service,
            streaming_event_recorder=self.streaming_event_recorder,
            adapter_request_builder=self.adapter_request_builder,
            provider_request_preview_recorder=self.provider_request_preview_recorder,
            concurrency_limiter=self.concurrency_limiter,
        )

    @property
    def credential_provider(self) -> CredentialProvider | None:
        return self._credential_provider

    @credential_provider.setter
    def credential_provider(self, value: CredentialProvider | None) -> None:
        self._credential_provider = value
        if hasattr(self, "profile_service"):
            self.profile_service.credential_provider = value
        if hasattr(self, "adapter_request_builder"):
            self.adapter_request_builder.credential_provider = value

    def register_profile(self, data: RegisterLlmProfileInput) -> LlmProfile:
        return self.profile_service.register_profile(data)

    def upsert_profile(self, data: RegisterLlmProfileInput) -> LlmProfile:
        return self.profile_service.upsert_profile(data)

    def update_profile(self, data: RegisterLlmProfileInput) -> LlmProfile:
        return self.profile_service.update_profile(data)

    def set_profile_enabled(self, llm_id: str, *, enabled: bool) -> LlmProfile:
        return self.profile_service.set_profile_enabled(llm_id, enabled=enabled)

    def delete_profile(self, llm_id: str) -> None:
        self.profile_service.delete_profile(llm_id)

    def get_profile(self, llm_id: str) -> LlmProfile:
        return self.profile_service.get_profile(llm_id)

    def get_profile_optional(self, llm_id: str) -> LlmProfile | None:
        return self.profile_service.get_profile_optional(llm_id)

    def list_profiles(self) -> list[LlmProfile]:
        return self.profile_service.list_profiles()

    def _get_enabled_profile(self, llm_id: str) -> LlmProfile:
        return self.profile_service.get_enabled_profile(llm_id)

    def sync_profiles(
        self,
        profiles: tuple[RegisterLlmProfileInput, ...],
        *,
        emit_events: bool = True,
    ) -> list[LlmProfile]:
        return self.profile_service.sync_profiles(profiles, emit_events=emit_events)

    def invoke(self, data: InvokeLlmInput) -> LlmInvocation:
        profile = self._get_enabled_profile(data.llm_id)
        adapter = self.adapter_gateway.get(profile.api_family)
        if adapter is None:
            raise LlmAdapterNotConfiguredError(
                f"No llm adapter is configured for api family '{profile.api_family.value}'.",
            )

        return self.invocation_runner.invoke(
            profile=profile,
            adapter=adapter,
            data=data,
        )

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

        return self.invocation_runner.test_profile(
            profile=profile,
            adapter=adapter,
            data=data,
        )

    def warmup_profile(
        self,
        data: WarmupLlmProfileInput,
    ) -> WarmupLlmProfileResult:
        return self.profile_warmup_service.warmup_profile(data)

    async def invoke_async(self, data: InvokeLlmInput) -> LlmInvocation:
        profile = await asyncio.to_thread(self._get_enabled_profile, data.llm_id)

        adapter = self.adapter_gateway.get(profile.api_family)
        if adapter is None:
            raise LlmAdapterNotConfiguredError(
                f"No llm adapter is configured for api family '{profile.api_family.value}'.",
            )

        return await self.invocation_runner.invoke_async(
            profile=profile,
            adapter=adapter,
            data=data,
        )

    def stream_invoke(self, data: StreamLlmInput) -> Iterator[LlmStreamEvent]:
        profile = self._get_enabled_profile(data.llm_id)
        adapter = self.adapter_gateway.get(profile.api_family)
        if adapter is None:
            raise LlmAdapterNotConfiguredError(
                f"No llm adapter is configured for api family '{profile.api_family.value}'.",
            )

        return self.streaming_invocation_runner.stream_invoke(
            profile=profile,
            adapter=adapter,
            data=data,
        )

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

        async for event in self.streaming_invocation_runner.stream_invoke_async(
            profile=profile,
            adapter=adapter,
            data=data,
        ):
            yield event

    def get_invocation(self, invocation_id: str) -> LlmInvocation:
        return self.invocation_service.get_invocation(invocation_id)

    def get_response_item(self, item_id: str) -> LlmResponseItem:
        return self.invocation_service.get_response_item(item_id)

    def list_invocations(
        self,
        *,
        llm_id: str | None = None,
        run_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[LlmInvocation]:
        return self.invocation_service.list_invocations(
            llm_id=llm_id,
            run_id=run_id,
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
        return self.invocation_service.list_response_events(
            invocation_id,
            limit=limit,
            after_sequence=after_sequence,
        )

    def response_event_retention_policy(self) -> LlmResponseEventRetentionPolicy:
        return self.invocation_service.response_event_retention_policy()

    def _build_profile(self, data: RegisterLlmProfileInput) -> LlmProfile:
        return self.profile_service.build_profile(data)
