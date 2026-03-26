from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from crxzipple.modules.llm.application import InvokeLlmInput, StreamLlmInput
from crxzipple.modules.llm.domain import LlmAdapterNotConfiguredError
from crxzipple.modules.orchestration.application.ports import LlmPort
from crxzipple.modules.orchestration.domain import OrchestrationValidationError


@dataclass(slots=True)
class OrchestrationEngineLlmInvoker:
    llm_port: LlmPort

    def invoke(
        self,
        *,
        llm_id: str,
        messages: tuple,
        tool_schemas: tuple,
        on_llm_stream_update: Callable[[str, str], None] | None = None,
    ):
        try:
            events = self.llm_port.stream_invoke(
                StreamLlmInput(
                    llm_id=llm_id,
                    messages=messages,
                    tool_schemas=tool_schemas,
                ),
            )
        except LlmAdapterNotConfiguredError:
            return self.llm_port.invoke(
                InvokeLlmInput(
                    llm_id=llm_id,
                    messages=messages,
                    tool_schemas=tool_schemas,
                ),
            )

        invocation_id: str | None = None
        streamed_text = ""
        for event in events:
            if event.invocation_id:
                invocation_id = event.invocation_id
            if event.type == "invocation_started":
                if invocation_id is not None and on_llm_stream_update is not None:
                    on_llm_stream_update(invocation_id, "")
                continue
            if event.type == "text_delta":
                delta = event.data.get("text")
                if delta is not None:
                    streamed_text += str(delta)
                    if invocation_id is not None and on_llm_stream_update is not None:
                        on_llm_stream_update(invocation_id, streamed_text)
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
