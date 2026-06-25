from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
    OperationsChartSectionModel,
    OperationsKeyValueItemModel,
    OperationsKeyValueSectionModel,
    OperationsModuleRoleModel,
    OperationsTabModel,
    OperationsTableSectionModel,
    RuntimeActionModel,
)


@dataclass(frozen=True, slots=True)
class ChannelsOperationsQuery:
    status: str = "all"
    channel_type: str = "all"
    search: str = ""
    limit: int = 80
    offset: int = 0


@dataclass(frozen=True, slots=True)
class ChannelRuntimeDetailModel:
    runtime_id: str
    title: str
    status: str
    tone: str
    summary: tuple[OperationsKeyValueItemModel, ...]
    capabilities: OperationsKeyValueSectionModel
    account_bindings: OperationsTableSectionModel
    connection_bindings: OperationsTableSectionModel
    events: OperationsTableSectionModel
    dead_letters: OperationsTableSectionModel
    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ChannelRecordDetailModel:
    record_id: str
    title: str
    status: str
    tone: str
    summary: tuple[OperationsKeyValueItemModel, ...]
    payload: dict[str, Any]
    trace: dict[str, Any]
    related: OperationsTableSectionModel


@dataclass(frozen=True, slots=True)
class ChannelInteractionDetailModel:
    interaction_id: str
    title: str
    status: str
    tone: str
    summary: tuple[OperationsKeyValueItemModel, ...]
    routing: OperationsKeyValueSectionModel
    reply_address: OperationsKeyValueSectionModel
    metadata: OperationsKeyValueSectionModel
    events: OperationsTableSectionModel
    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ChannelsOperationsPage:
    module: str
    title: str
    subtitle: str
    health: str
    updated_at: str
    auto_refresh: bool
    role: OperationsModuleRoleModel
    metrics: tuple[MetricCardModel, ...]
    tabs: tuple[OperationsTabModel, ...]
    active_tab: str
    actions: tuple[RuntimeActionModel, ...]
    channel_status: OperationsTableSectionModel
    message_flow: OperationsChartSectionModel
    delivery_trend: OperationsChartSectionModel
    top_channels: OperationsChartSectionModel
    dead_letter_queue: OperationsTableSectionModel
    recent_messages: OperationsTableSectionModel
    interactions: OperationsTableSectionModel
    failures_by_category: OperationsChartSectionModel
    channel_bindings: OperationsTableSectionModel
    connection_bindings: OperationsTableSectionModel
    channel_profiles: OperationsTableSectionModel
    channel_events: OperationsTableSectionModel
    contracts: OperationsTableSectionModel
    runtime_details: tuple[ChannelRuntimeDetailModel, ...]
    record_details: tuple[ChannelRecordDetailModel, ...]
    interaction_details: tuple[ChannelInteractionDetailModel, ...]


@dataclass(frozen=True, slots=True)
class ChannelEventRecord:
    id: str
    cursor: str
    topic: str
    event_name: str
    kind: str
    status: str
    occurred_at: datetime
    channel_type: str | None = None
    runtime_id: str | None = None
    channel_account_id: str | None = None
    connection_id: str | None = None
    conversation_id: str | None = None
    run_id: str | None = None
    trace_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    trace: dict[str, Any] = field(default_factory=dict)
