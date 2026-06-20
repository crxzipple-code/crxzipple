from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field

from crxzipple.modules.llm.application import (
    InvokeLlmInput,
    StreamLlmInput,
    profile_supports_provider_continuation,
)
from crxzipple.modules.llm.application.runtime_request import RuntimeLlmRequest
from crxzipple.modules.llm.domain import (
    LlmAdapterNotConfiguredError,
    LlmProviderContinuation,
)
from crxzipple.modules.orchestration.application.ports import LlmPort
from crxzipple.modules.orchestration.domain import OrchestrationValidationError
from crxzipple.shared.runtime_metrics import (
    RuntimeMetricsRegistry,
    get_runtime_metrics_registry,
)


@dataclass(slots=True)
class OrchestrationEngineLlmInvoker:
    llm_port: LlmPort
    metrics: RuntimeMetricsRegistry = field(
        default_factory=get_runtime_metrics_registry,
    )

    def invoke(
        self,
        *,
        request_envelope: RuntimeLlmRequest,
        response_format: dict[str, object] | None = None,
        continuation: LlmProviderContinuation | None = None,
        on_llm_stream_update: Callable[[str, str, str | None], None] | None = None,
    ):
        labels = {"llm_id": request_envelope.llm_id}
        with self.metrics.active("orchestration.llm.active", labels=labels):
            with self.metrics.timed("orchestration.llm.invoke_seconds", labels=labels):
                try:
                    events = self.llm_port.stream_invoke(
                        StreamLlmInput.from_runtime_request(
                            request_envelope,
                            response_format=response_format,
                            continuation=continuation,
                        ),
                    )
                except LlmAdapterNotConfiguredError:
                    return self.llm_port.invoke(
                        InvokeLlmInput.from_runtime_request(
                            request_envelope,
                            response_format=response_format,
                            continuation=continuation,
                        ),
                    )

                invocation_id: str | None = None
                streamed_text = ""
                for event in events:
                    if event.invocation_id:
                        invocation_id = event.invocation_id
                    if event.type == "invocation_started":
                        if invocation_id is not None and on_llm_stream_update is not None:
                            on_llm_stream_update(invocation_id, "", "")
                        continue
                    if event.type == "text_delta":
                        delta = event.data.get("text")
                        if delta is not None:
                            text_delta = str(delta)
                            streamed_text += text_delta
                            if invocation_id is not None and on_llm_stream_update is not None:
                                on_llm_stream_update(invocation_id, streamed_text, text_delta)
                        continue
                    if event.type == "failed":
                        error_payload = event.data.get("error")
                        if isinstance(error_payload, dict):
                            message = str(error_payload.get("message") or "LLM stream failed.")
                            code = str(error_payload.get("code") or "stream_failed")
                            raise OrchestrationValidationError(
                                f"LLM invocation failed [{code}]: {message}",
                            )
                        raise OrchestrationValidationError("LLM invocation failed [stream_failed].")

                if invocation_id is None:
                    raise OrchestrationValidationError(
                        "Streaming llm invocation ended before an invocation id was produced.",
                    )
                return self.llm_port.get_invocation(invocation_id)

    async def invoke_async(
        self,
        *,
        request_envelope: RuntimeLlmRequest,
        response_format: dict[str, object] | None = None,
        continuation: LlmProviderContinuation | None = None,
        on_llm_stream_update: Callable[[str, str, str | None], None] | None = None,
    ):
        labels = {"llm_id": request_envelope.llm_id}
        with self.metrics.active("orchestration.llm.active", labels=labels):
            with self.metrics.timed("orchestration.llm.invoke_seconds", labels=labels):
                try:
                    events = self.llm_port.stream_invoke_async(
                        StreamLlmInput.from_runtime_request(
                            request_envelope,
                            response_format=response_format,
                            continuation=continuation,
                        ),
                    )
                except LlmAdapterNotConfiguredError:
                    return await self.llm_port.invoke_async(
                        InvokeLlmInput.from_runtime_request(
                            request_envelope,
                            response_format=response_format,
                            continuation=continuation,
                        ),
                    )

                invocation_id: str | None = None
                streamed_text = ""
                try:
                    async for event in events:
                        if event.invocation_id:
                            invocation_id = event.invocation_id
                        if event.type == "invocation_started":
                            if invocation_id is not None and on_llm_stream_update is not None:
                                on_llm_stream_update(invocation_id, "", "")
                            continue
                        if event.type == "text_delta":
                            delta = event.data.get("text")
                            if delta is not None:
                                text_delta = str(delta)
                                streamed_text += text_delta
                                if invocation_id is not None and on_llm_stream_update is not None:
                                    on_llm_stream_update(invocation_id, streamed_text, text_delta)
                            continue
                        if event.type == "failed":
                            error_payload = event.data.get("error")
                            if isinstance(error_payload, dict):
                                message = str(error_payload.get("message") or "LLM stream failed.")
                                code = str(error_payload.get("code") or "stream_failed")
                                raise OrchestrationValidationError(
                                    f"LLM invocation failed [{code}]: {message}",
                                )
                            raise OrchestrationValidationError("LLM invocation failed [stream_failed].")
                except LlmAdapterNotConfiguredError:
                    return await self.llm_port.invoke_async(
                        InvokeLlmInput.from_runtime_request(
                            request_envelope,
                            response_format=response_format,
                            continuation=continuation,
                        ),
                    )

                if invocation_id is None:
                    raise OrchestrationValidationError(
                        "Streaming llm invocation ended before an invocation id was produced.",
                    )
                return await asyncio.to_thread(
                    self.llm_port.get_invocation,
                    invocation_id,
                )

    def provider_continuation(
        self,
        *,
        request_envelope: RuntimeLlmRequest,
        continuation: LlmProviderContinuation | None,
    ) -> LlmProviderContinuation | None:
        if continuation is None:
            return None
        if not self._supports_provider_continuation(
            request_envelope=request_envelope,
            continuation=continuation,
        ):
            return None
        return continuation

    def _supports_provider_continuation(
        self,
        *,
        request_envelope: RuntimeLlmRequest,
        continuation: LlmProviderContinuation,
    ) -> bool:
        profile = self.llm_port.get_profile(request_envelope.llm_id)
        return profile_supports_provider_continuation(
            profile=profile,
            continuation=continuation,
            provider_options=request_envelope.provider_options,
        )
