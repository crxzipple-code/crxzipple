from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from crxzipple.modules.operations.application.read_models import (
    EventsEventDetailModel,
    EventsOperationsPage,
)
from crxzipple.modules.operations.interfaces.http_models_core import (
    MetricCardResponse,
    OperationsChartSectionResponse,
    OperationsKeyValueItemResponse,
    OperationsKeyValueSectionResponse,
    OperationsModuleRoleResponse,
    OperationsProjectionFreshnessResponse,
    OperationsTabResponse,
    OperationsTableSectionResponse,
    RuntimeActionResponse,
)


class EventsEventDetailResponse(BaseModel):
    event_id: str
    title: str
    status: str
    tone: str
    summary: list[OperationsKeyValueItemResponse]
    payload: Any
    trace: Any
    contracts: OperationsTableSectionResponse
    subscriptions: OperationsTableSectionResponse

    @classmethod
    def from_value(
        cls,
        value: EventsEventDetailModel,
    ) -> "EventsEventDetailResponse":
        return cls(
            event_id=value.event_id,
            title=value.title,
            status=value.status,
            tone=value.tone,
            summary=[
                OperationsKeyValueItemResponse.from_value(item)
                for item in value.summary
            ],
            payload=value.payload,
            trace=value.trace,
            contracts=OperationsTableSectionResponse.from_value(value.contracts),
            subscriptions=OperationsTableSectionResponse.from_value(
                value.subscriptions,
            ),
        )


class EventsOperationsResponse(BaseModel):
    module: str
    title: str
    subtitle: str
    health: str
    updated_at: str
    auto_refresh: bool
    role: OperationsModuleRoleResponse
    metrics: list[MetricCardResponse]
    tabs: list[OperationsTabResponse]
    active_tab: str
    actions: list[RuntimeActionResponse]
    events_over_time: OperationsChartSectionResponse
    events_by_surface: OperationsChartSectionResponse
    owners_by_volume: OperationsTableSectionResponse
    contract_compatibility: OperationsKeyValueSectionResponse
    recent_events: OperationsTableSectionResponse
    consumer_health: OperationsTableSectionResponse
    observer_health: OperationsTableSectionResponse
    observer_lag: OperationsTableSectionResponse
    topics: OperationsTableSectionResponse
    subscriptions: OperationsTableSectionResponse
    observer_coverage: OperationsTableSectionResponse
    dead_letters: OperationsTableSectionResponse
    contracts: OperationsTableSectionResponse
    routes: OperationsTableSectionResponse
    event_details: list[EventsEventDetailResponse]
    projection_freshness: OperationsProjectionFreshnessResponse | None = None

    @classmethod
    def from_view(
        cls,
        view: EventsOperationsPage,
    ) -> "EventsOperationsResponse":
        return cls(
            module=view.module,
            title=view.title,
            subtitle=view.subtitle,
            health=view.health,
            updated_at=view.updated_at,
            auto_refresh=view.auto_refresh,
            role=OperationsModuleRoleResponse.from_value(view.role),
            metrics=[MetricCardResponse.from_value(item) for item in view.metrics],
            tabs=[OperationsTabResponse.from_value(item) for item in view.tabs],
            active_tab=view.active_tab,
            actions=[RuntimeActionResponse.from_value(item) for item in view.actions],
            events_over_time=OperationsChartSectionResponse.from_value(
                view.events_over_time,
            ),
            events_by_surface=OperationsChartSectionResponse.from_value(
                view.events_by_surface,
            ),
            owners_by_volume=OperationsTableSectionResponse.from_value(
                view.owners_by_volume,
            ),
            contract_compatibility=OperationsKeyValueSectionResponse.from_value(
                view.contract_compatibility,
            ),
            recent_events=OperationsTableSectionResponse.from_value(
                view.recent_events,
            ),
            consumer_health=OperationsTableSectionResponse.from_value(
                view.consumer_health,
            ),
            observer_health=OperationsTableSectionResponse.from_value(
                view.observer_health,
            ),
            observer_lag=OperationsTableSectionResponse.from_value(
                view.observer_lag,
            ),
            topics=OperationsTableSectionResponse.from_value(view.topics),
            subscriptions=OperationsTableSectionResponse.from_value(
                view.subscriptions,
            ),
            observer_coverage=OperationsTableSectionResponse.from_value(
                view.observer_coverage,
            ),
            dead_letters=OperationsTableSectionResponse.from_value(
                view.dead_letters,
            ),
            contracts=OperationsTableSectionResponse.from_value(view.contracts),
            routes=OperationsTableSectionResponse.from_value(view.routes),
            event_details=[
                EventsEventDetailResponse.from_value(item)
                for item in view.event_details
            ],
        )
