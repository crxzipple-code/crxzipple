from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from uuid import uuid4

from crxzipple.modules.llm.application.adapters import LlmAdapterRequest
from crxzipple.modules.llm.application.concurrency import LlmConcurrencyLimiter
from crxzipple.modules.llm.application.llm_adapter_request_builder import (
    LlmAdapterRequestBuilder,
)
from crxzipple.modules.llm.application.llm_invocation_events import (
    invocation_started_event_payload,
)
from crxzipple.modules.llm.application.llm_invocation_inputs import (
    StreamLlmInput,
    runtime_invocation_references,
)
from crxzipple.modules.llm.application.llm_invocation_service import (
    LlmInvocationService,
)
from crxzipple.modules.llm.application.llm_streaming_event_recorder import (
    LlmStreamingEventRecorder,
)
from crxzipple.modules.llm.application.provider_request_preview_recorder import (
    ProviderRequestPreviewRecorder,
)
from crxzipple.modules.llm.application.streaming import LlmStreamEvent
from crxzipple.modules.llm.domain.entities import LlmInvocation, LlmProfile
from crxzipple.modules.llm.domain.exceptions import LlmAdapterNotConfiguredError
from crxzipple.shared.domain.events import Event


class LlmStreamingInvocationRunner:
    def __init__(
        self,
        *,
        invocation_service: LlmInvocationService,
        streaming_event_recorder: LlmStreamingEventRecorder,
        adapter_request_builder: LlmAdapterRequestBuilder,
        provider_request_preview_recorder: ProviderRequestPreviewRecorder,
        concurrency_limiter: LlmConcurrencyLimiter,
    ) -> None:
        self._invocation_service = invocation_service
        self._streaming_event_recorder = streaming_event_recorder
        self._adapter_request_builder = adapter_request_builder
        self._provider_request_preview_recorder = provider_request_preview_recorder
        self._concurrency_limiter = concurrency_limiter

    def stream_invoke(
        self,
        *,
        profile: LlmProfile,
        adapter: object,
        data: StreamLlmInput,
    ) -> Iterator[LlmStreamEvent]:
        stream_invoke = getattr(adapter, "stream_invoke", None)
        if not callable(stream_invoke):
            raise LlmAdapterNotConfiguredError(
                f"No streaming llm adapter is configured for api family '{profile.api_family.value}'.",
            )

        invocation = self._started_invocation(profile, data)
        self._invocation_service.store_started_invocation(invocation)

        def _generator() -> Iterator[LlmStreamEvent]:
            with self._concurrency_limiter.limit(profile):
                sequence = 1
                completed = False
                yield self._streaming_event_recorder.started_event(
                    invocation,
                    sequence,
                )
                self._streaming_event_recorder.record_started_event(
                    invocation,
                    sequence=sequence,
                )
                sequence += 1

                try:
                    request = self._build_request(profile, invocation, data)
                    self._provider_request_preview_recorder.record(
                        invocation.id,
                        self._provider_request_preview_recorder.preview(
                            adapter,
                            profile,
                            request,
                        ),
                    )
                    for event in stream_invoke(profile, request):
                        normalized_event = self._streaming_event_recorder.normalized_event(
                            event,
                            sequence=sequence,
                            invocation_id=invocation.id,
                        )
                        self._streaming_event_recorder.record_response_event(
                            invocation.id,
                            sequence=sequence,
                            event_type=normalized_event.type,
                            data=normalized_event.data,
                        )
                        sequence += 1

                        if normalized_event.type == "completed":
                            self._streaming_event_recorder.complete_from_stream_event(
                                invocation.id,
                                normalized_event,
                            )
                            completed = True
                        yield normalized_event

                    if not completed:
                        yield self._streaming_event_recorder.incomplete_stream_failed_event(
                            invocation.id,
                            sequence=sequence,
                        )
                except Exception as exc:
                    yield self._streaming_event_recorder.adapter_failed_event(
                        invocation.id,
                        sequence=sequence,
                        error_message=str(exc) or type(exc).__name__,
                    )

        return _generator()

    async def stream_invoke_async(
        self,
        *,
        profile: LlmProfile,
        adapter: object,
        data: StreamLlmInput,
    ) -> AsyncIterator[LlmStreamEvent]:
        stream = self._stream_adapter_async(adapter, profile)
        if stream is None:
            raise LlmAdapterNotConfiguredError(
                f"No streaming llm adapter is configured for api family '{profile.api_family.value}'.",
            )

        invocation = self._started_invocation(profile, data)
        await asyncio.to_thread(
            self._invocation_service.store_started_invocation,
            invocation,
        )

        async with self._concurrency_limiter.limit_async(profile):
            sequence = 1
            completed = False
            yield self._streaming_event_recorder.started_event(invocation, sequence)
            await asyncio.to_thread(
                self._streaming_event_recorder.record_started_event,
                invocation,
                sequence=sequence,
            )
            sequence += 1

            try:
                request = self._build_request(profile, invocation, data)
                await asyncio.to_thread(
                    self._provider_request_preview_recorder.record,
                    invocation.id,
                    self._provider_request_preview_recorder.preview(
                        adapter,
                        profile,
                        request,
                    ),
                )
                async for event in stream(request):
                    normalized_event = self._streaming_event_recorder.normalized_event(
                        event,
                        sequence=sequence,
                        invocation_id=invocation.id,
                    )
                    await asyncio.to_thread(
                        self._streaming_event_recorder.record_response_event,
                        invocation.id,
                        sequence=sequence,
                        event_type=normalized_event.type,
                        data=normalized_event.data,
                    )
                    sequence += 1

                    if normalized_event.type == "completed":
                        await asyncio.to_thread(
                            self._streaming_event_recorder.complete_from_stream_event,
                            invocation.id,
                            normalized_event,
                        )
                        completed = True
                    yield normalized_event

                if not completed:
                    yield await asyncio.to_thread(
                        self._streaming_event_recorder.incomplete_stream_failed_event,
                        invocation.id,
                        sequence=sequence,
                    )
            except Exception as exc:
                yield await asyncio.to_thread(
                    self._streaming_event_recorder.adapter_failed_event,
                    invocation.id,
                    sequence=sequence,
                    error_message=str(exc) or type(exc).__name__,
                )

    def _started_invocation(
        self,
        profile: LlmProfile,
        data: StreamLlmInput,
    ) -> LlmInvocation:
        refs = runtime_invocation_references(
            request_metadata=data.request_metadata,
            runtime_context=data.runtime_context,
            runtime_route=data.runtime_route,
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
            run_id=refs["run_id"],
            agent_id=refs["agent_id"],
            session_key=refs["session_key"],
            active_session_id=refs["active_session_id"],
        )
        invocation.start()
        invocation.record_event(
            Event(
                name="llm.invocation_started",
                payload=invocation_started_event_payload(
                    invocation,
                    profile,
                    streaming=True,
                ),
            ),
        )
        return invocation

    def _build_request(
        self,
        profile: LlmProfile,
        invocation: LlmInvocation,
        data: StreamLlmInput,
    ) -> LlmAdapterRequest:
        return self._adapter_request_builder.build(
            profile,
            invocation,
            continuation=data.continuation,
            runtime_context=data.runtime_context,
            runtime_route=data.runtime_route,
            runtime_policy=data.runtime_policy,
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
