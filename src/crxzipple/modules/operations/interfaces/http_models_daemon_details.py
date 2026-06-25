from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from crxzipple.modules.operations.application.read_models import (
    DaemonInstanceDetailModel,
    DaemonLeaseDetailModel,
    DaemonProcessDetailModel,
)
from crxzipple.modules.operations.interfaces.http_models_core import (
    OperationsKeyValueItemResponse,
    OperationsKeyValueSectionResponse,
    OperationsTableSectionResponse,
)


class DaemonInstanceDetailResponse(BaseModel):
    instance_id: str
    title: str
    status: str
    tone: str
    summary: list[OperationsKeyValueItemResponse]
    environment: OperationsKeyValueSectionResponse
    service: OperationsKeyValueSectionResponse
    leases: OperationsTableSectionResponse
    events: OperationsTableSectionResponse
    raw_payload: Any

    @classmethod
    def from_value(
        cls,
        value: DaemonInstanceDetailModel,
    ) -> "DaemonInstanceDetailResponse":
        return cls(
            instance_id=value.instance_id,
            title=value.title,
            status=value.status,
            tone=value.tone,
            summary=[
                OperationsKeyValueItemResponse.from_value(item)
                for item in value.summary
            ],
            environment=OperationsKeyValueSectionResponse.from_value(
                value.environment,
            ),
            service=OperationsKeyValueSectionResponse.from_value(value.service),
            leases=OperationsTableSectionResponse.from_value(value.leases),
            events=OperationsTableSectionResponse.from_value(value.events),
            raw_payload=value.raw_payload,
        )


class DaemonLeaseDetailResponse(BaseModel):
    lease_id: str
    title: str
    status: str
    tone: str
    summary: list[OperationsKeyValueItemResponse]
    metadata: OperationsKeyValueSectionResponse
    events: OperationsTableSectionResponse
    raw_payload: Any

    @classmethod
    def from_value(
        cls,
        value: DaemonLeaseDetailModel,
    ) -> "DaemonLeaseDetailResponse":
        return cls(
            lease_id=value.lease_id,
            title=value.title,
            status=value.status,
            tone=value.tone,
            summary=[
                OperationsKeyValueItemResponse.from_value(item)
                for item in value.summary
            ],
            metadata=OperationsKeyValueSectionResponse.from_value(value.metadata),
            events=OperationsTableSectionResponse.from_value(value.events),
            raw_payload=value.raw_payload,
        )


class DaemonProcessDetailResponse(BaseModel):
    process_id: str
    title: str
    status: str
    tone: str
    summary: list[OperationsKeyValueItemResponse]
    metadata: OperationsKeyValueSectionResponse
    output: OperationsTableSectionResponse
    raw_payload: Any

    @classmethod
    def from_value(
        cls,
        value: DaemonProcessDetailModel,
    ) -> "DaemonProcessDetailResponse":
        return cls(
            process_id=value.process_id,
            title=value.title,
            status=value.status,
            tone=value.tone,
            summary=[
                OperationsKeyValueItemResponse.from_value(item)
                for item in value.summary
            ],
            metadata=OperationsKeyValueSectionResponse.from_value(value.metadata),
            output=OperationsTableSectionResponse.from_value(value.output),
            raw_payload=value.raw_payload,
        )
