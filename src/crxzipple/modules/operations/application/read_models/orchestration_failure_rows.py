from __future__ import annotations

from typing import Any

from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
)
from crxzipple.modules.operations.application.read_models.presenters import (
    display_value,
    truncate_text,
)
from crxzipple.modules.operations.application.read_models.routes import (
    workbench_trace_route,
)
from crxzipple.shared.time import format_datetime_utc


def repeated_probe_rows(
    runs: list[OrchestrationRun],
) -> tuple[OperationsTableRowModel, ...]:
    rows: list[OperationsTableRowModel] = []
    for run in runs:
        observation = run.metadata.get("repeated_probe_observation")
        if not isinstance(observation, dict):
            continue
        repeated = observation.get("repeated")
        if not isinstance(repeated, list):
            continue
        for index, item in enumerate(repeated[:5]):
            if not isinstance(item, dict):
                continue
            row = _repeated_probe_row(run, item, index=index)
            if row is not None:
                rows.append(row)
    rows.sort(
        key=lambda row: (
            -_int(row.cells.get("count"), 0),
            row.cells.get("run_id", ""),
            row.cells.get("target", ""),
        ),
    )
    return tuple(rows)


def recent_failure_rows(
    runs: list[OrchestrationRun],
) -> tuple[OperationsTableRowModel, ...]:
    return tuple(
        OperationsTableRowModel(
            id=run.id,
            cells={
                "time": format_datetime_utc(run.completed_at or run.updated_at),
                "run_id": run.id,
                "error": _run_error_code(run),
                "status": run.status.value,
                "module": "Orchestration",
                "details": _run_error_message(run),
                "trace": _trace_id(run),
                "route": _workbench_route(run),
                "trace_route": _trace_route(run),
                "actions": "Open / Trace / Requeue",
            },
            status=run.status.value,
            tone="danger",
        )
        for run in sorted(runs, key=lambda item: item.updated_at, reverse=True)[:20]
    )


def _repeated_probe_row(
    run: OrchestrationRun,
    item: dict[str, Any],
    *,
    index: int,
) -> OperationsTableRowModel | None:
    count = _int(item.get("count"), 0)
    if count < 3:
        return None
    target = _probe_target_label(item)
    return OperationsTableRowModel(
        id=f"{run.id}:{index}:{target}",
        cells={
            "run_id": run.id,
            "tool_id": _display(item.get("tool_id")),
            "kind": _display(item.get("kind")),
            "target": target,
            "count": str(count),
            "first_seen_step": _display(item.get("first_seen_step")),
            "last_seen_step": _display(item.get("last_seen_step")),
            "trace": _trace_id(run),
            "route": _workbench_route(run),
            "trace_route": _trace_route(run),
        },
        status="repeated_probe",
        tone="warning",
    )


def _probe_target_label(item: dict[str, Any]) -> str:
    normalized_url = _optional_metadata_text(item.get("normalized_url"))
    if normalized_url is not None:
        return _truncate(normalized_url, limit=120)
    command_fingerprint = _optional_metadata_text(item.get("command_fingerprint"))
    if command_fingerprint is not None:
        return f"command:{command_fingerprint}"
    argument_fingerprint = _optional_metadata_text(item.get("argument_fingerprint"))
    if argument_fingerprint is not None:
        return f"args:{argument_fingerprint}"
    key = _optional_metadata_text(item.get("key"))
    return _truncate(key or "-", limit=120)


def _optional_metadata_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int(value: object | None, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _trace_id(run: OrchestrationRun) -> str:
    trace_id = run.metadata.get("trace_id")
    if isinstance(trace_id, str) and trace_id.strip():
        return trace_id.strip()
    correlation_id = run.metadata.get("correlation_id")
    if isinstance(correlation_id, str) and correlation_id.strip():
        return correlation_id.strip()
    return run.id


def _trace_route(run: OrchestrationRun) -> str:
    return workbench_trace_route(_trace_id(run))


def _workbench_route(run: OrchestrationRun) -> str:
    return f"/ui/workbench/runs/{run.id}"


def _run_error_code(run: OrchestrationRun) -> str:
    error = run.error
    if error is None:
        return "-"
    code = getattr(error, "code", None)
    return _display(code)


def _run_error_message(run: OrchestrationRun) -> str:
    error = run.error
    if error is None:
        return "-"
    message = getattr(error, "message", None)
    return _truncate(_display(message))


def _display(value: object | None) -> str:
    return display_value(value)


def _truncate(value: str, *, limit: int = 96) -> str:
    return truncate_text(value, limit)
