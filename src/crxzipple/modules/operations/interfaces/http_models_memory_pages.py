from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from crxzipple.modules.operations.application.read_models import (
    MemoryFileDetailModel,
    MemoryOperationsPage,
)
from crxzipple.modules.operations.interfaces.http_models_core import (
    MetricCardResponse,
    OperationsChartSectionResponse,
    OperationsKeyValueItemResponse,
    OperationsModuleRoleResponse,
    OperationsProjectionFreshnessResponse,
    OperationsTabResponse,
    OperationsTableSectionResponse,
    RuntimeActionResponse,
)


class MemoryFileDetailResponse(BaseModel):
    file_id: str
    title: str
    status: str
    tone: str
    summary: list[OperationsKeyValueItemResponse]
    excerpt: str
    related: OperationsTableSectionResponse
    raw_payload: Any

    @classmethod
    def from_value(
        cls,
        value: MemoryFileDetailModel,
    ) -> "MemoryFileDetailResponse":
        return cls(
            file_id=value.file_id,
            title=value.title,
            status=value.status,
            tone=value.tone,
            summary=[
                OperationsKeyValueItemResponse.from_value(item)
                for item in value.summary
            ],
            excerpt=value.excerpt,
            related=OperationsTableSectionResponse.from_value(value.related),
            raw_payload=value.raw_payload,
        )


class MemoryOperationsResponse(BaseModel):
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
    memory_stores: OperationsTableSectionResponse
    context_resolution: OperationsTableSectionResponse
    index_health: OperationsChartSectionResponse
    index_jobs: OperationsTableSectionResponse
    index_sync_activity: OperationsTableSectionResponse
    retrieval_performance: OperationsChartSectionResponse
    retrieval_trace: OperationsTableSectionResponse
    write_flush: OperationsTableSectionResponse
    memory_usage: OperationsTableSectionResponse
    recent_retrieval_logs: OperationsTableSectionResponse
    source_scan_status: OperationsTableSectionResponse
    source_files: OperationsTableSectionResponse
    file_details: list[MemoryFileDetailResponse]
    projection_freshness: OperationsProjectionFreshnessResponse | None = None

    @classmethod
    def from_view(
        cls,
        view: MemoryOperationsPage,
    ) -> "MemoryOperationsResponse":
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
            memory_stores=OperationsTableSectionResponse.from_value(
                view.memory_stores,
            ),
            context_resolution=OperationsTableSectionResponse.from_value(
                view.context_resolution,
            ),
            index_health=OperationsChartSectionResponse.from_value(
                view.index_health,
            ),
            index_jobs=OperationsTableSectionResponse.from_value(view.index_jobs),
            index_sync_activity=OperationsTableSectionResponse.from_value(
                view.index_sync_activity,
            ),
            retrieval_performance=OperationsChartSectionResponse.from_value(
                view.retrieval_performance,
            ),
            retrieval_trace=OperationsTableSectionResponse.from_value(
                view.retrieval_trace,
            ),
            write_flush=OperationsTableSectionResponse.from_value(view.write_flush),
            memory_usage=OperationsTableSectionResponse.from_value(
                view.memory_usage,
            ),
            recent_retrieval_logs=OperationsTableSectionResponse.from_value(
                view.recent_retrieval_logs,
            ),
            source_scan_status=OperationsTableSectionResponse.from_value(
                view.source_scan_status,
            ),
            source_files=OperationsTableSectionResponse.from_value(view.source_files),
            file_details=[
                MemoryFileDetailResponse.from_value(item) for item in view.file_details
            ],
        )
