from __future__ import annotations

import asyncio
from uuid import uuid4

from crxzipple.modules.llm.application.adapters import (
    LlmAdapterRequest,
    LlmAdapterResponse,
)
from crxzipple.modules.llm.application.concurrency import LlmConcurrencyLimiter
from crxzipple.modules.llm.application.llm_adapter_request_builder import (
    LlmAdapterRequestBuilder,
)
from crxzipple.modules.llm.application.llm_invocation_events import (
    invocation_started_event_payload,
)
from crxzipple.modules.llm.application.llm_invocation_terminal_events import (
    result_summary_from_adapter_response,
)
from crxzipple.modules.llm.application.llm_invocation_inputs import (
    InvokeLlmInput,
    runtime_invocation_references,
)
from crxzipple.modules.llm.application.llm_invocation_service import (
    LlmInvocationService,
)
from crxzipple.modules.llm.application.provider_request_preview_recorder import (
    ProviderRequestPreviewRecorder,
)
from crxzipple.modules.llm.domain.entities import LlmInvocation, LlmProfile
from crxzipple.modules.llm.domain.exceptions import LlmAdapterNotConfiguredError
from crxzipple.modules.llm.domain import LlmErrorPayload
from crxzipple.shared.domain.events import Event


class LlmInvocationRunner:
    def __init__(
        self,
        *,
        invocation_service: LlmInvocationService,
        adapter_request_builder: LlmAdapterRequestBuilder,
        provider_request_preview_recorder: ProviderRequestPreviewRecorder,
        concurrency_limiter: LlmConcurrencyLimiter,
    ) -> None:
        self._invocation_service = invocation_service
        self._adapter_request_builder = adapter_request_builder
        self._provider_request_preview_recorder = provider_request_preview_recorder
        self._concurrency_limiter = concurrency_limiter

    def invoke(
        self,
        *,
        profile: LlmProfile,
        adapter: object,
        data: InvokeLlmInput,
    ) -> LlmInvocation:
        invocation = self._started_invocation(profile, data)
        self._invocation_service.store_started_invocation(invocation)

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
            with self._concurrency_limiter.limit(profile):
                response = self._invoke_adapter(adapter, profile, request)
        except Exception as exc:
            return self._invocation_service.fail_invocation(
                invocation.id,
                LlmErrorPayload(
                    message=str(exc) or type(exc).__name__,
                    code="adapter_error",
                ),
            )

        return self._complete_invocation(invocation.id, response)

    async def invoke_async(
        self,
        *,
        profile: LlmProfile,
        adapter: object,
        data: InvokeLlmInput,
    ) -> LlmInvocation:
        invocation = self._started_invocation(profile, data)
        await asyncio.to_thread(
            self._invocation_service.store_started_invocation,
            invocation,
        )

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
            async with self._concurrency_limiter.limit_async(profile):
                response = await self._invoke_adapter_async(adapter, profile, request)
        except Exception as exc:
            return await asyncio.to_thread(
                self._invocation_service.fail_invocation,
                invocation.id,
                LlmErrorPayload(
                    message=str(exc) or type(exc).__name__,
                    code="adapter_error",
                ),
            )

        return await asyncio.to_thread(
            self._complete_invocation,
            invocation.id,
            response,
        )

    def test_profile(
        self,
        *,
        profile: LlmProfile,
        adapter: object,
        data: InvokeLlmInput,
    ) -> LlmInvocation:
        invocation = self._started_invocation(
            profile,
            data,
            record_started_event=False,
        )

        try:
            request = self._build_request(profile, invocation, data)
            self._provider_request_preview_recorder.record_for_invocation(
                invocation,
                adapter=adapter,
                profile=profile,
                request=request,
            )
            with self._concurrency_limiter.limit(profile):
                response = self._invoke_adapter(adapter, profile, request)
        except Exception as exc:
            invocation.fail(
                LlmErrorPayload(
                    message=str(exc) or type(exc).__name__,
                    code="adapter_error",
                ),
            )
            return invocation

        invocation.succeed(
            result_summary_from_adapter_response(response),
            response_items=response.response_items,
            continuation=response.continuation,
            provider_request_id=response.provider_request_id,
        )
        return invocation

    def _started_invocation(
        self,
        profile: LlmProfile,
        data: InvokeLlmInput,
        *,
        record_started_event: bool = True,
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
        if record_started_event:
            invocation.record_event(
                Event(
                    name="llm.invocation_started",
                    payload=invocation_started_event_payload(
                        invocation,
                        profile,
                        streaming=False,
                    ),
                ),
            )
        return invocation

    def _build_request(
        self,
        profile: LlmProfile,
        invocation: LlmInvocation,
        data: InvokeLlmInput,
    ) -> LlmAdapterRequest:
        return self._adapter_request_builder.build(
            profile,
            invocation,
            continuation=data.continuation,
            runtime_context=data.runtime_context,
            runtime_route=data.runtime_route,
            runtime_policy=data.runtime_policy,
        )

    def _complete_invocation(
        self,
        invocation_id: str,
        response: LlmAdapterResponse,
    ) -> LlmInvocation:
        return self._invocation_service.complete_invocation(
            invocation_id,
            result_summary_from_adapter_response(response),
            response_items=response.response_items,
            continuation=response.continuation,
            provider_request_id=response.provider_request_id,
            streaming=False,
        )

    @staticmethod
    def _invoke_adapter(
        adapter: object,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> LlmAdapterResponse:
        invoke = getattr(adapter, "invoke", None)
        if callable(invoke):
            return invoke(profile, request)
        raise LlmAdapterNotConfiguredError(
            f"No llm adapter is configured for api family '{profile.api_family.value}'.",
        )

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
