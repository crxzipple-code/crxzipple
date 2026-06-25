from __future__ import annotations

from crxzipple.modules.llm.domain import LlmInvocation
from crxzipple.modules.operations.application.read_models.llm_provider_render_labels import (
    provider_request_render_report_label,
    provider_request_render_strategy_label,
    provider_request_renderer_label,
    provider_tool_mapping_label,
)
from crxzipple.modules.operations.application.read_models.llm_provider_request_labels import (
    provider_continuation_fallback_label,
    provider_request_continuation_label,
    provider_request_input_delta_label,
    provider_request_input_items_label,
    provider_request_options_label,
    provider_request_tool_count_label,
    provider_request_transport_label,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
)


def provider_request_context_items(
    invocation: LlmInvocation,
) -> tuple[OperationsKeyValueItemModel, ...]:
    return (
        OperationsKeyValueItemModel(
            "Provider Continuation",
            provider_request_continuation_label(invocation),
        ),
        OperationsKeyValueItemModel(
            "Provider Transport",
            provider_request_transport_label(invocation),
        ),
        OperationsKeyValueItemModel(
            "Provider Renderer",
            provider_request_renderer_label(invocation),
        ),
        OperationsKeyValueItemModel(
            "Provider Render Strategy",
            provider_request_render_strategy_label(invocation),
        ),
        OperationsKeyValueItemModel(
            "Provider Render Report",
            provider_request_render_report_label(invocation),
        ),
        OperationsKeyValueItemModel(
            "Provider Tool Mapping",
            provider_tool_mapping_label(invocation),
        ),
        OperationsKeyValueItemModel(
            "Provider Input Delta",
            provider_request_input_delta_label(invocation),
        ),
        OperationsKeyValueItemModel(
            "Provider Continuation Fallback",
            provider_continuation_fallback_label(invocation),
        ),
        OperationsKeyValueItemModel(
            "Provider Input Items",
            provider_request_input_items_label(invocation),
        ),
        OperationsKeyValueItemModel(
            "Provider Tool Count",
            provider_request_tool_count_label(invocation),
        ),
        OperationsKeyValueItemModel(
            "Provider Options",
            provider_request_options_label(invocation),
        ),
    )
