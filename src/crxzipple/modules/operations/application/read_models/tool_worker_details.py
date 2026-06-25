from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
    OperationsKeyValueSectionModel,
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.tool_worker_detail_sections import (
    tool_worker_capabilities_section,
)
from crxzipple.modules.operations.application.read_models.tool_worker_detail_summary import (
    tool_worker_detail_summary,
)
from crxzipple.modules.operations.application.read_models.tool_worker_runtime_sections import (
    tool_worker_runtimes_section,
)
from crxzipple.modules.operations.application.read_models.tool_lifecycle_event_rows import (
    tool_worker_events_section,
)
from crxzipple.modules.operations.application.read_models.tool_worker_provider_limits import (
    tool_worker_provider_limits_section,
)
from crxzipple.modules.operations.application.read_models.tool_run_detail_payloads import (
    json_safe_payload,
)
from crxzipple.modules.operations.application.read_models.tool_worker_projection import (
    worker_registration_bucket,
    worker_registration_status,
)
from crxzipple.modules.tool.domain import ToolRun, ToolWorkerRegistration


@dataclass(frozen=True, slots=True)
class ToolWorkerDetailModel:
    worker_id: str
    title: str
    status: str
    tone: str
    summary: tuple[OperationsKeyValueItemModel, ...]
    capabilities: OperationsKeyValueSectionModel
    runtimes: OperationsTableSectionModel
    provider_limits: OperationsTableSectionModel
    events: OperationsTableSectionModel
    raw_payload: Any


def tool_worker_details(
    workers: list[ToolWorkerRegistration],
    *,
    active_runs: list[ToolRun],
    observed_events: tuple[OperationsObservedEvent, ...],
    now: datetime,
) -> tuple[ToolWorkerDetailModel, ...]:
    active_runs_by_worker: dict[str, list[ToolRun]] = {}
    for run in active_runs:
        if run.worker_id:
            active_runs_by_worker.setdefault(run.worker_id, []).append(run)

    events_by_worker: dict[str, list[OperationsObservedEvent]] = {}
    for event in observed_events:
        worker_id = _optional_str(event.payload.get("worker_id"))
        if worker_id is None and event.event_name.startswith("tool.worker."):
            worker_id = event.entity_id
        if worker_id:
            events_by_worker.setdefault(worker_id, []).append(event)

    return tuple(
        _tool_worker_detail(
            worker,
            active_runs=active_runs_by_worker.get(worker.id, []),
            events=events_by_worker.get(worker.id, []),
            now=now,
        )
        for worker in sorted(workers, key=lambda item: item.id)[:50]
    )


def _tool_worker_detail(
    worker: ToolWorkerRegistration,
    *,
    active_runs: list[ToolRun],
    events: list[OperationsObservedEvent],
    now: datetime,
) -> ToolWorkerDetailModel:
    bucket = worker_registration_bucket(worker, now=now)
    status, tone = worker_registration_status(bucket)
    return ToolWorkerDetailModel(
        worker_id=worker.id,
        title=worker.id,
        status=status,
        tone=tone,
        summary=tool_worker_detail_summary(
            worker,
            status=status,
            active_runs=active_runs,
            now=now,
        ),
        capabilities=tool_worker_capabilities_section(worker),
        runtimes=tool_worker_runtimes_section(worker),
        provider_limits=tool_worker_provider_limits_section(worker),
        events=tool_worker_events_section(events),
        raw_payload=json_safe_payload(worker.capabilities_payload),
    )

def _optional_str(value: object | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None
