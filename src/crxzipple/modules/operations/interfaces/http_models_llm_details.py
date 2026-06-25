from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from crxzipple.modules.operations.application.read_models import (
    LlmInvocationDetailModel,
)
from crxzipple.modules.operations.interfaces.http_models_core import (
    OperationsKeyValueItemResponse,
    OperationsKeyValueSectionResponse,
    OperationsTableSectionResponse,
)


class LlmInvocationDetailResponse(BaseModel):
    invocation_id: str
    title: str
    status: str
    tone: str
    summary: list[OperationsKeyValueItemResponse]
    request_context: list[OperationsKeyValueItemResponse]
    runtime_observations: OperationsKeyValueSectionResponse
    runtime_request_summary: dict[str, Any]
    request_payload: Any
    provider_render_report: dict[str, Any]
    provider_wire_preview: dict[str, Any]
    provider_context_mapping: OperationsTableSectionResponse
    result_payload: Any
    result_summary: str
    error: str
    resolver: OperationsKeyValueSectionResponse
    error_facts: OperationsKeyValueSectionResponse
    policy_trace: OperationsTableSectionResponse
    response_items: OperationsTableSectionResponse
    response_runtime_mapping: OperationsTableSectionResponse
    response_events: OperationsTableSectionResponse
    events: OperationsTableSectionResponse

    @classmethod
    def from_value(
        cls,
        value: LlmInvocationDetailModel,
    ) -> "LlmInvocationDetailResponse":
        return cls(
            invocation_id=value.invocation_id,
            title=value.title,
            status=value.status,
            tone=value.tone,
            summary=[
                OperationsKeyValueItemResponse.from_value(item)
                for item in value.summary
            ],
            request_context=[
                OperationsKeyValueItemResponse.from_value(item)
                for item in value.request_context
            ],
            runtime_observations=OperationsKeyValueSectionResponse.from_value(
                value.runtime_observations,
            ),
            runtime_request_summary=dict(value.runtime_request_summary),
            request_payload=value.request_payload,
            provider_render_report=value.provider_render_report,
            provider_wire_preview=value.provider_wire_preview,
            provider_context_mapping=OperationsTableSectionResponse.from_value(
                value.provider_context_mapping,
            ),
            result_payload=value.result_payload,
            result_summary=value.result_summary,
            error=value.error,
            resolver=OperationsKeyValueSectionResponse.from_value(value.resolver),
            error_facts=OperationsKeyValueSectionResponse.from_value(
                value.error_facts,
            ),
            policy_trace=OperationsTableSectionResponse.from_value(
                value.policy_trace,
            ),
            response_items=OperationsTableSectionResponse.from_value(
                value.response_items,
            ),
            response_runtime_mapping=OperationsTableSectionResponse.from_value(
                value.response_runtime_mapping,
            ),
            response_events=OperationsTableSectionResponse.from_value(
                value.response_events,
            ),
            events=OperationsTableSectionResponse.from_value(value.events),
        )
