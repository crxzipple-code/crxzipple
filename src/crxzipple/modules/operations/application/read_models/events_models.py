from __future__ import annotations

from dataclasses import dataclass
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
class EventsOperationsQuery:
    status: str = "all"
    topic_prefix: str = ""
    search: str = ""
    owner: str = "all"
    limit: int = 80
    offset: int = 0


@dataclass(frozen=True, slots=True)
class EventsEventDetailModel:
    event_id: str
    title: str
    status: str
    tone: str
    summary: tuple[OperationsKeyValueItemModel, ...]
    payload: dict[str, Any]
    trace: dict[str, Any]
    contracts: OperationsTableSectionModel
    subscriptions: OperationsTableSectionModel


@dataclass(frozen=True, slots=True)
class EventsOperationsPage:
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
    events_over_time: OperationsChartSectionModel
    events_by_surface: OperationsChartSectionModel
    owners_by_volume: OperationsTableSectionModel
    contract_compatibility: OperationsKeyValueSectionModel
    recent_events: OperationsTableSectionModel
    consumer_health: OperationsTableSectionModel
    observer_health: OperationsTableSectionModel
    observer_lag: OperationsTableSectionModel
    topics: OperationsTableSectionModel
    subscriptions: OperationsTableSectionModel
    observer_coverage: OperationsTableSectionModel
    dead_letters: OperationsTableSectionModel
    contracts: OperationsTableSectionModel
    routes: OperationsTableSectionModel
    event_details: tuple[EventsEventDetailModel, ...]
