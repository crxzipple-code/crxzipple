from __future__ import annotations

from crxzipple.modules.operations.application.read_models.models import (
    RuntimeActionModel,
)


def tool_actions() -> tuple[RuntimeActionModel, ...]:
    return (
        RuntimeActionModel(
            id="open_tool",
            label="Open Tool",
            owner="tool",
            kind="navigation",
            method="GET",
            endpoint="/operations/tool?tool_id={tool_id}",
        ),
        RuntimeActionModel(
            id="open_trace",
            label="Open Trace",
            owner="events",
            kind="navigation",
            method="GET",
            endpoint="/workbench/traces/{trace_id}",
        ),
        RuntimeActionModel(
            id="cancel_tool_run",
            label="Cancel Tool Run",
            owner="tool",
            risk="controlled",
            requires_confirmation=True,
            audit_event="tool.run.cancel",
            method="POST",
            endpoint="/operations/tool/runs/{run_id}/cancel",
        ),
        RuntimeActionModel(
            id="retry_tool_run",
            label="Retry Tool Run",
            owner="tool",
            risk="controlled",
            requires_confirmation=True,
            audit_event="tool.run.retry",
            method="POST",
            endpoint="/operations/tool/runs/{run_id}/retry",
        ),
        RuntimeActionModel(
            id="prune_expired_workers",
            label="Prune Expired Workers",
            owner="tool",
            risk="controlled",
            requires_confirmation=True,
            audit_event="tool.workers.prune_expired",
            method="POST",
            endpoint="/operations/tool/workers/prune-expired",
        ),
        RuntimeActionModel(
            id="open_access",
            label="Open Access",
            owner="access",
            kind="navigation",
            method="GET",
            endpoint="/operations/access",
        ),
    )
