from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from crxzipple.modules.operations.application.read_models import (
    ToolRunDetailModel,
    ToolWorkerDetailModel,
)
from crxzipple.modules.operations.interfaces.http_models_core import (
    OperationsKeyValueItemResponse,
    OperationsKeyValueSectionResponse,
    OperationsTableSectionResponse,
)


class ToolRunDetailResponse(BaseModel):
    run_id: str
    title: str
    status: str
    tone: str
    summary: list[OperationsKeyValueItemResponse]
    invocation_context: list[OperationsKeyValueItemResponse]
    input_payload: Any
    result_payload: Any
    result_summary: str
    error: str
    error_facts: OperationsKeyValueSectionResponse
    assignments: OperationsTableSectionResponse
    events: OperationsTableSectionResponse
    artifacts: OperationsTableSectionResponse

    @classmethod
    def from_value(cls, value: ToolRunDetailModel) -> "ToolRunDetailResponse":
        return cls(
            run_id=value.run_id,
            title=value.title,
            status=value.status,
            tone=value.tone,
            summary=[
                OperationsKeyValueItemResponse.from_value(item)
                for item in value.summary
            ],
            invocation_context=[
                OperationsKeyValueItemResponse.from_value(item)
                for item in value.invocation_context
            ],
            input_payload=value.input_payload,
            result_payload=value.result_payload,
            result_summary=value.result_summary,
            error=value.error,
            error_facts=OperationsKeyValueSectionResponse.from_value(
                value.error_facts,
            ),
            assignments=OperationsTableSectionResponse.from_value(value.assignments),
            events=OperationsTableSectionResponse.from_value(value.events),
            artifacts=OperationsTableSectionResponse.from_value(value.artifacts),
        )


class ToolWorkerDetailResponse(BaseModel):
    worker_id: str
    title: str
    status: str
    tone: str
    summary: list[OperationsKeyValueItemResponse]
    capabilities: OperationsKeyValueSectionResponse
    runtimes: OperationsTableSectionResponse
    provider_limits: OperationsTableSectionResponse
    events: OperationsTableSectionResponse
    raw_payload: Any

    @classmethod
    def from_value(cls, value: ToolWorkerDetailModel) -> "ToolWorkerDetailResponse":
        return cls(
            worker_id=value.worker_id,
            title=value.title,
            status=value.status,
            tone=value.tone,
            summary=[
                OperationsKeyValueItemResponse.from_value(item)
                for item in value.summary
            ],
            capabilities=OperationsKeyValueSectionResponse.from_value(
                value.capabilities,
            ),
            runtimes=OperationsTableSectionResponse.from_value(value.runtimes),
            provider_limits=OperationsTableSectionResponse.from_value(
                value.provider_limits,
            ),
            events=OperationsTableSectionResponse.from_value(value.events),
            raw_payload=value.raw_payload,
        )
