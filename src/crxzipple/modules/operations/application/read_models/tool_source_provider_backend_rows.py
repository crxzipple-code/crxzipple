from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Mapping

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
)
from crxzipple.modules.operations.application.read_models.presenters import (
    title_label,
)
from crxzipple.modules.operations.application.read_models.tool_source_provider_backend_labels import (
    provider_backend_credential_label,
    provider_backend_readiness_label,
    provider_backend_runtime_label,
    provider_backend_status_label,
    provider_backend_tone,
)
from crxzipple.modules.operations.application.read_models.tool_source_common import (
    record_text,
    record_value,
)
from crxzipple.modules.tool.domain import ToolRun, ToolRunStatus


def provider_backend_rows(
    provider_backends: tuple[Any, ...],
    *,
    runs: list[ToolRun],
    readiness_by_backend_id: Mapping[str, dict[str, Any]],
    now: datetime,
) -> tuple[OperationsTableRowModel, ...]:
    run_counts = _provider_backend_run_counts(runs, now=now)
    rows: list[OperationsTableRowModel] = []
    for backend in provider_backends:
        backend_id = record_text(backend, "backend_id")
        if not backend_id:
            continue
        rows.append(
            _provider_backend_row(
                backend,
                backend_id=backend_id,
                run_counts=run_counts.get(backend_id, {}),
                readiness=readiness_by_backend_id.get(backend_id),
            ),
        )
    return tuple(rows)


def _provider_backend_row(
    backend: Any,
    *,
    backend_id: str,
    run_counts: Mapping[str, int],
    readiness: Mapping[str, Any] | None,
) -> OperationsTableRowModel:
    return OperationsTableRowModel(
        id=backend_id,
        cells={
            "backend": record_text(backend, "display_name") or backend_id,
            "capability": title_label(record_value(backend, "capability")),
            "credential": provider_backend_credential_label(backend),
            "readiness": provider_backend_readiness_label(readiness),
            "calls_24h": str(run_counts.get("calls_24h", 0)),
            "failures_24h": str(run_counts.get("failures_24h", 0)),
            "runtime": provider_backend_runtime_label(backend),
            "status": provider_backend_status_label(backend),
        },
        status=record_value(backend, "status") or "unknown",
        tone=provider_backend_tone(backend, readiness),
    )


def _provider_backend_run_counts(
    runs: list[ToolRun],
    *,
    now: datetime,
) -> dict[str, dict[str, int]]:
    cutoff = now - timedelta(hours=24)
    counts: dict[str, dict[str, int]] = {}
    for run in runs:
        backend_id = _run_provider_backend_id(run)
        if backend_id is None:
            continue
        created_at = _run_created_at(run)
        if created_at is None or created_at < cutoff:
            continue
        bucket = counts.setdefault(
            backend_id,
            {"calls_24h": 0, "failures_24h": 0},
        )
        bucket["calls_24h"] += 1
        if run.status in {ToolRunStatus.FAILED, ToolRunStatus.TIMED_OUT}:
            bucket["failures_24h"] += 1
    return counts


def _run_provider_backend_id(run: ToolRun) -> str | None:
    value = run.metadata.get("provider_backend")
    if not isinstance(value, Mapping):
        return None
    backend_id = str(value.get("backend_id") or "").strip()
    return backend_id or None


def _run_created_at(run: ToolRun) -> datetime | None:
    created_at = getattr(run, "created_at", None)
    return created_at if isinstance(created_at, datetime) else None
