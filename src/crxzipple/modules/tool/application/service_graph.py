from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.tool.application.catalog_service import ToolCatalogService
from crxzipple.modules.tool.application.concurrency import ToolRunConcurrencyPolicy
from crxzipple.modules.tool.application.scheduler_service import (
    ToolBackgroundSchedulerService,
)
from crxzipple.modules.tool.application.service_support import ToolServiceDependencies
from crxzipple.modules.tool.application.services import ToolApplicationService
from crxzipple.modules.tool.application.submission_service import ToolSubmissionService
from crxzipple.modules.tool.application.worker_service import ToolWorkerService


@dataclass(slots=True)
class ToolServiceGraph:
    deps: ToolServiceDependencies
    catalog_service: ToolCatalogService
    scheduler_service: ToolBackgroundSchedulerService
    worker_service: ToolWorkerService
    submission_service: ToolSubmissionService
    application_service: ToolApplicationService


def build_tool_service_graph(deps: ToolServiceDependencies) -> ToolServiceGraph:
    catalog_service = ToolCatalogService(deps)
    concurrency_policy = ToolRunConcurrencyPolicy(
        default_max_in_flight=deps.worker_default_run_concurrency,
        image_max_in_flight=deps.worker_image_run_concurrency,
        shared_state_max_in_flight=deps.worker_shared_state_run_concurrency,
    )
    scheduler_service = ToolBackgroundSchedulerService(
        deps,
        catalog_service=catalog_service,
        concurrency_policy=concurrency_policy,
    )
    worker_service = ToolWorkerService(
        deps,
        catalog_service=catalog_service,
        concurrency_policy=concurrency_policy,
    )
    submission_service = ToolSubmissionService(
        deps,
        catalog_service=catalog_service,
        worker_service=worker_service,
    )
    application_service = ToolApplicationService(
        catalog_service=catalog_service,
        worker_service=worker_service,
        submission_service=submission_service,
    )
    return ToolServiceGraph(
        deps=deps,
        catalog_service=catalog_service,
        scheduler_service=scheduler_service,
        worker_service=worker_service,
        submission_service=submission_service,
        application_service=application_service,
    )
