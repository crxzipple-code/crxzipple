from __future__ import annotations

from crxzipple.modules.llm.domain import LlmInvocation
from crxzipple.modules.operations.application.observation_models import (
    OperationsObservedEvent,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_request_context_provider_items import (
    provider_request_context_items,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_request_context_runtime_items import (
    artifact_request_context_items,
    replay_request_context_items,
    runtime_request_context_items,
    tool_result_request_context_items,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
)


def request_context_items(
    invocation: LlmInvocation,
    *,
    events: tuple[OperationsObservedEvent, ...],
    streaming_ids: set[str],
) -> tuple[OperationsKeyValueItemModel, ...]:
    return (
        *runtime_request_context_items(
            invocation,
            events=events,
            streaming_ids=streaming_ids,
        ),
        *replay_request_context_items(invocation),
        *tool_result_request_context_items(invocation),
        *artifact_request_context_items(invocation),
        *provider_request_context_items(invocation),
    )
