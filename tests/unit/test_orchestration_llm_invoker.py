from __future__ import annotations

from types import SimpleNamespace

from crxzipple.modules.llm.application import LlmStreamEvent
from crxzipple.modules.llm.domain import LlmProviderContinuation
from crxzipple.modules.orchestration.application.engine_llm_invoker import (
    OrchestrationEngineLlmInvoker,
)


class _CapturingLlmPort:
    def __init__(self) -> None:
        self.last_stream_input = None

    def stream_invoke(self, data):  # noqa: ANN001
        self.last_stream_input = data
        yield LlmStreamEvent(
            type="invocation_started",
            sequence=1,
            invocation_id="llm-invocation-1",
            data={"status": "running"},
        )

    def get_invocation(self, invocation_id: str):  # noqa: ANN201
        return SimpleNamespace(id=invocation_id)


def test_llm_invoker_passes_provider_continuation_to_stream_input() -> None:
    port = _CapturingLlmPort()
    invoker = OrchestrationEngineLlmInvoker(llm_port=port)
    continuation = LlmProviderContinuation(
        mode="provider_native",
        previous_response_id="resp_previous",
        previous_invocation_id="llm-previous",
        provider_family="openai_codex_responses",
    )

    invocation = invoker.invoke(
        llm_id="openai_codex.gpt-5.5",
        messages=(),
        tool_schemas=(),
        continuation=continuation,
    )

    assert invocation.id == "llm-invocation-1"
    assert port.last_stream_input is not None
    assert port.last_stream_input.continuation == continuation
