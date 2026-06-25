from __future__ import annotations

from pydantic import BaseModel

from crxzipple.modules.operations.application.read_models import (
    ChannelsOperationsPage,
)
from crxzipple.modules.operations.interfaces.http_models_channel_details import (
    ChannelInteractionDetailResponse,
    ChannelRecordDetailResponse,
    ChannelRuntimeDetailResponse,
)
from crxzipple.modules.operations.interfaces.http_models_core import (
    MetricCardResponse,
    OperationsChartSectionResponse,
    OperationsModuleRoleResponse,
    OperationsProjectionFreshnessResponse,
    OperationsTabResponse,
    OperationsTableSectionResponse,
    RuntimeActionResponse,
)


class ChannelsOperationsResponse(BaseModel):
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
    channel_status: OperationsTableSectionResponse
    message_flow: OperationsChartSectionResponse
    delivery_trend: OperationsChartSectionResponse
    top_channels: OperationsChartSectionResponse
    dead_letter_queue: OperationsTableSectionResponse
    recent_messages: OperationsTableSectionResponse
    interactions: OperationsTableSectionResponse
    failures_by_category: OperationsChartSectionResponse
    channel_bindings: OperationsTableSectionResponse
    connection_bindings: OperationsTableSectionResponse
    channel_profiles: OperationsTableSectionResponse
    channel_events: OperationsTableSectionResponse
    contracts: OperationsTableSectionResponse
    runtime_details: list[ChannelRuntimeDetailResponse]
    record_details: list[ChannelRecordDetailResponse]
    interaction_details: list[ChannelInteractionDetailResponse]
    projection_freshness: OperationsProjectionFreshnessResponse | None = None

    @classmethod
    def from_view(
        cls,
        view: ChannelsOperationsPage,
    ) -> "ChannelsOperationsResponse":
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
            channel_status=OperationsTableSectionResponse.from_value(
                view.channel_status,
            ),
            message_flow=OperationsChartSectionResponse.from_value(
                view.message_flow,
            ),
            delivery_trend=OperationsChartSectionResponse.from_value(
                view.delivery_trend,
            ),
            top_channels=OperationsChartSectionResponse.from_value(
                view.top_channels,
            ),
            dead_letter_queue=OperationsTableSectionResponse.from_value(
                view.dead_letter_queue,
            ),
            recent_messages=OperationsTableSectionResponse.from_value(
                view.recent_messages,
            ),
            interactions=OperationsTableSectionResponse.from_value(
                view.interactions,
            ),
            failures_by_category=OperationsChartSectionResponse.from_value(
                view.failures_by_category,
            ),
            channel_bindings=OperationsTableSectionResponse.from_value(
                view.channel_bindings,
            ),
            connection_bindings=OperationsTableSectionResponse.from_value(
                view.connection_bindings,
            ),
            channel_profiles=OperationsTableSectionResponse.from_value(
                view.channel_profiles,
            ),
            channel_events=OperationsTableSectionResponse.from_value(
                view.channel_events,
            ),
            contracts=OperationsTableSectionResponse.from_value(view.contracts),
            runtime_details=[
                ChannelRuntimeDetailResponse.from_value(item)
                for item in view.runtime_details
            ],
            record_details=[
                ChannelRecordDetailResponse.from_value(item)
                for item in view.record_details
            ],
            interaction_details=[
                ChannelInteractionDetailResponse.from_value(item)
                for item in view.interaction_details
            ],
        )
