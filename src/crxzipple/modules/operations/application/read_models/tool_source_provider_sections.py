from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.tool_source_common import (
    columns,
)
from crxzipple.modules.operations.application.read_models.tool_source_provider_backend_rows import (
    provider_backend_rows,
)
from crxzipple.modules.tool.domain import ToolRun


def provider_backend_health_section(
    provider_backends: tuple[Any, ...],
    *,
    runs: list[ToolRun],
    readiness_by_backend_id: Mapping[str, dict[str, Any]],
    now: datetime,
) -> OperationsTableSectionModel:
    rows = provider_backend_rows(
        provider_backends,
        runs=runs,
        readiness_by_backend_id=readiness_by_backend_id,
        now=now,
    )
    return OperationsTableSectionModel(
        id="provider_backend_health",
        title="Provider Backend Health",
        columns=columns(
            ("backend", "Backend"),
            ("capability", "Capability"),
            ("credential", "Credential"),
            ("readiness", "Readiness"),
            ("calls_24h", "Calls 24h"),
            ("failures_24h", "Failures 24h"),
            ("runtime", "Runtime"),
            ("status", "Status"),
        ),
        rows=rows,
        total=len(rows),
        empty_state="No provider backends are registered.",
    )
