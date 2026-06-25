from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    OperationsModuleOverview,
)
from crxzipple.modules.operations.application.read_models.ports_tooling import (
    OperationsToolQueryPort,
)
from crxzipple.modules.operations.application.read_models.tool_metrics import (
    tool_health,
    tool_metric_cards,
)
from crxzipple.modules.operations.application.read_models.tool_overview_actions import (
    tool_actions,
)
from crxzipple.modules.operations.application.read_models.tool_overview_rows import (
    queue_rows,
    risk_rows,
    worker_rows,
)
from crxzipple.modules.operations.application.read_models.tool_page_facts import (
    OPERATIONS_TOOL_RUN_QUERY_LIMIT,
)
from crxzipple.modules.operations.application.read_models.tool_page_helpers import (
    latest_assignment_by_run,
)
from crxzipple.modules.tool.domain import ToolRunStatus
from crxzipple.shared.time import format_datetime_utc


def tool_operations_overview(
    *,
    tool_service: OperationsToolQueryPort,
    runtime_bootstrap_config: Any | None = None,
) -> OperationsModuleOverview:
    now = datetime.now(timezone.utc)
    tools = tool_service.list_tools()
    runs = tool_service.list_tool_runs(limit=OPERATIONS_TOOL_RUN_QUERY_LIMIT)
    workers = tool_service.list_tool_workers()
    assignments = tool_service.list_tool_run_assignments()
    assignment_by_run = latest_assignment_by_run(assignments)
    active_runs = [run for run in runs if not run.is_terminal()]
    failed_runs = [
        run
        for run in runs
        if run.status in {ToolRunStatus.FAILED, ToolRunStatus.TIMED_OUT}
    ]
    health = tool_health(
        tools=tools,
        active_runs=active_runs,
        failed_runs=failed_runs,
    )

    return OperationsModuleOverview(
        module="tool",
        title="Tool",
        subtitle="监控工具目录、执行队列、失败运行、授权与确认风险。",
        health=health,
        updated_at=format_datetime_utc(now),
        metrics=tool_metric_cards(
            tools=tools,
            runs=runs,
            active_runs=active_runs,
            failed_runs=failed_runs,
            health=health,
            workers=workers,
            runtime_bootstrap_config=runtime_bootstrap_config,
            now=now,
        ),
        queue=queue_rows(
            active_runs,
            assignment_by_run=assignment_by_run,
            now=now,
        ),
        lane_locks=risk_rows(tools),
        executor=worker_rows(workers, active_runs=active_runs),
        actions=tool_actions(),
    )
