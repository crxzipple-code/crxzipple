from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from crxzipple.modules.operations.application.read_models import (
    ChannelInteractionDetailModel,
    ChannelRecordDetailModel,
    ChannelRuntimeDetailModel,
)
from crxzipple.modules.operations.interfaces.http_models_core import (
    OperationsKeyValueItemResponse,
    OperationsKeyValueSectionResponse,
    OperationsTableSectionResponse,
)


class ChannelRuntimeDetailResponse(BaseModel):
    runtime_id: str
    title: str
    status: str
    tone: str
    summary: list[OperationsKeyValueItemResponse]
    capabilities: OperationsKeyValueSectionResponse
    account_bindings: OperationsTableSectionResponse
    connection_bindings: OperationsTableSectionResponse
    events: OperationsTableSectionResponse
    dead_letters: OperationsTableSectionResponse
    raw_payload: Any

    @classmethod
    def from_value(
        cls,
        value: ChannelRuntimeDetailModel,
    ) -> "ChannelRuntimeDetailResponse":
        return cls(
            runtime_id=value.runtime_id,
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
            account_bindings=OperationsTableSectionResponse.from_value(
                value.account_bindings,
            ),
            connection_bindings=OperationsTableSectionResponse.from_value(
                value.connection_bindings,
            ),
            events=OperationsTableSectionResponse.from_value(value.events),
            dead_letters=OperationsTableSectionResponse.from_value(value.dead_letters),
            raw_payload=value.raw_payload,
        )


class ChannelRecordDetailResponse(BaseModel):
    record_id: str
    title: str
    status: str
    tone: str
    summary: list[OperationsKeyValueItemResponse]
    payload: Any
    trace: Any
    related: OperationsTableSectionResponse

    @classmethod
    def from_value(
        cls,
        value: ChannelRecordDetailModel,
    ) -> "ChannelRecordDetailResponse":
        return cls(
            record_id=value.record_id,
            title=value.title,
            status=value.status,
            tone=value.tone,
            summary=[
                OperationsKeyValueItemResponse.from_value(item)
                for item in value.summary
            ],
            payload=value.payload,
            trace=value.trace,
            related=OperationsTableSectionResponse.from_value(value.related),
        )


class ChannelInteractionDetailResponse(BaseModel):
    interaction_id: str
    title: str
    status: str
    tone: str
    summary: list[OperationsKeyValueItemResponse]
    routing: OperationsKeyValueSectionResponse
    reply_address: OperationsKeyValueSectionResponse
    metadata: OperationsKeyValueSectionResponse
    events: OperationsTableSectionResponse
    raw_payload: Any

    @classmethod
    def from_value(
        cls,
        value: ChannelInteractionDetailModel,
    ) -> "ChannelInteractionDetailResponse":
        return cls(
            interaction_id=value.interaction_id,
            title=value.title,
            status=value.status,
            tone=value.tone,
            summary=[
                OperationsKeyValueItemResponse.from_value(item)
                for item in value.summary
            ],
            routing=OperationsKeyValueSectionResponse.from_value(value.routing),
            reply_address=OperationsKeyValueSectionResponse.from_value(
                value.reply_address,
            ),
            metadata=OperationsKeyValueSectionResponse.from_value(value.metadata),
            events=OperationsTableSectionResponse.from_value(value.events),
            raw_payload=value.raw_payload,
        )
