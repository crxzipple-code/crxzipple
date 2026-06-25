from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.ports_tooling import (
    OperationsToolQueryPort,
)
from crxzipple.modules.operations.application.read_models.tool_page_catalog_sections import (
    tool_catalog_sections,
)
from crxzipple.modules.operations.application.read_models.tool_page_detail_sections import (
    tool_detail_sections,
)
from crxzipple.modules.operations.application.read_models.tool_page_execution_sections import (
    tool_execution_sections,
)
from crxzipple.modules.operations.application.read_models.tool_page_facts import (
    ToolPageFacts,
)
from crxzipple.modules.operations.application.read_models.tool_worker_sections import workers_section
from crxzipple.modules.operations.application.read_models.tool_worker_pool_sections import worker_pool_section


def tool_page_sections(
    *,
    facts: ToolPageFacts,
    tool_service: OperationsToolQueryPort,
    access_service: Any | None,
    artifact_service: Any | None,
    runtime_metrics: Any | None,
    runtime_registry: Any | None,
) -> dict[str, Any]:
    concurrency_policy = tool_service.concurrency_policy
    return {
        **tool_execution_sections(
            facts=facts,
            concurrency_policy=concurrency_policy,
            artifact_service=artifact_service,
            runtime_metrics=runtime_metrics,
            runtime_registry=runtime_registry,
        ),
        **tool_catalog_sections(
            facts=facts,
            tool_service=tool_service,
            access_service=access_service,
        ),
        "worker_pool": worker_pool_section(
            facts.workers,
            active_runs=facts.active_runs,
            now=facts.now,
        ),
        "workers": workers_section(
            facts.workers,
            active_runs=facts.active_runs,
            runs=facts.runs,
            assignment_by_run=facts.assignment_by_run,
            now=facts.now,
        ),
        **tool_detail_sections(
            facts=facts,
            artifact_service=artifact_service,
        ),
    }
