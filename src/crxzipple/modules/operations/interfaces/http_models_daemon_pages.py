from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from crxzipple.modules.operations.application.read_models import (
    DaemonOperationsPage,
)
from crxzipple.modules.operations.interfaces.http_models_core import (
    MetricCardResponse,
    OperationsChartSectionResponse,
    OperationsKeyValueSectionResponse,
    OperationsModuleRoleResponse,
    OperationsProjectionFreshnessResponse,
    OperationsTabResponse,
    OperationsTableSectionResponse,
    RuntimeActionResponse,
)
from crxzipple.modules.operations.interfaces.http_models_daemon_details import (
    DaemonInstanceDetailResponse,
    DaemonLeaseDetailResponse,
    DaemonProcessDetailResponse,
)


class DaemonOperationsResponse(BaseModel):
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
    service_sets: OperationsTableSectionResponse
    services: OperationsTableSectionResponse
    instances: OperationsTableSectionResponse
    leases: OperationsTableSectionResponse
    processes: OperationsTableSectionResponse
    process_health: OperationsChartSectionResponse
    restart_summary: OperationsChartSectionResponse
    lease_health: OperationsChartSectionResponse
    dependency_health: OperationsTableSectionResponse
    drain_overview: OperationsKeyValueSectionResponse
    daemon_events: OperationsTableSectionResponse
    quick_actions: list[RuntimeActionResponse]
    links_to_operations: list[dict[str, Any]]
    instance_details: list[DaemonInstanceDetailResponse]
    lease_details: list[DaemonLeaseDetailResponse]
    process_details: list[DaemonProcessDetailResponse]
    projection_freshness: OperationsProjectionFreshnessResponse | None = None

    @classmethod
    def from_view(
        cls,
        view: DaemonOperationsPage,
    ) -> "DaemonOperationsResponse":
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
            service_sets=OperationsTableSectionResponse.from_value(
                view.service_sets,
            ),
            services=OperationsTableSectionResponse.from_value(view.services),
            instances=OperationsTableSectionResponse.from_value(view.instances),
            leases=OperationsTableSectionResponse.from_value(view.leases),
            processes=OperationsTableSectionResponse.from_value(view.processes),
            process_health=OperationsChartSectionResponse.from_value(
                view.process_health,
            ),
            restart_summary=OperationsChartSectionResponse.from_value(
                view.restart_summary,
            ),
            lease_health=OperationsChartSectionResponse.from_value(view.lease_health),
            dependency_health=OperationsTableSectionResponse.from_value(
                view.dependency_health,
            ),
            drain_overview=OperationsKeyValueSectionResponse.from_value(
                view.drain_overview,
            ),
            daemon_events=OperationsTableSectionResponse.from_value(
                view.daemon_events,
            ),
            quick_actions=[
                RuntimeActionResponse.from_value(item) for item in view.quick_actions
            ],
            links_to_operations=[dict(item) for item in view.links_to_operations],
            instance_details=[
                DaemonInstanceDetailResponse.from_value(item)
                for item in view.instance_details
            ],
            lease_details=[
                DaemonLeaseDetailResponse.from_value(item)
                for item in view.lease_details
            ],
            process_details=[
                DaemonProcessDetailResponse.from_value(item)
                for item in view.process_details
            ],
        )
