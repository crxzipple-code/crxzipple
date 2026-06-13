from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from crxzipple.core.logger import get_logger
from crxzipple.modules.orchestration.application.engine import OrchestrationEngine
from crxzipple.modules.orchestration.application.event_contracts import (
    ORCHESTRATION_ORPHAN_TOOL_RESULT_OBSERVED_EVENT,
)
from crxzipple.modules.orchestration.application.execution_chain_lifecycle import (
    mark_tool_run_step_item_terminal,
    materialize_tool_result_session_item_items,
)
from crxzipple.modules.orchestration.application.ports.context import (
    EventPublishPort,
)
from crxzipple.modules.orchestration.domain import (
    ExecutionChainRepository,
    ExecutionStepItemRepository,
    ExecutionStepRepository,
    OrchestrationRun,
    OrchestrationRunStatus,
    OrchestrationRunWaitRepository,
    OrchestrationQueuePolicy,
)
from crxzipple.modules.tool.domain import ToolRunStatus
from crxzipple.shared.domain.aggregates import AggregateRoot
from crxzipple.shared.domain.events import Event


logger = get_logger(__name__)


class WaitLookupUnitOfWork(Protocol):
    execution_chains: ExecutionChainRepository
    execution_steps: ExecutionStepRepository
    execution_step_items: ExecutionStepItemRepository
    orchestration_waits: OrchestrationRunWaitRepository

    def __enter__(self) -> "WaitLookupUnitOfWork":
        ...

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        ...

    def collect(self, aggregate: AggregateRoot[object]) -> None:
        ...

    def commit(self) -> None:
        ...


class ResumeToolRunCallback(Protocol):
    def __call__(
        self,
        run_id: str,
        queue_policy: OrchestrationQueuePolicy,
        reason: str,
        *,
        metadata: dict[str, object] | None = None,
    ) -> OrchestrationRun:
        ...


@dataclass(slots=True)
class OrchestrationToolResumeCoordinator:
    uow_factory: Callable[[], WaitLookupUnitOfWork]
    engine: OrchestrationEngine
    get_run: Callable[[str], OrchestrationRun]
    resume_run: ResumeToolRunCallback
    events_service: EventPublishPort | None = None

    def handle_terminal_tool_run(self, tool_run_id: str) -> list[OrchestrationRun]:
        try:
            terminal_tool_run = self.engine.tool_execution_port.get_tool_run(
                tool_run_id,
            )
        except Exception:
            terminal_tool_run = None
        if terminal_tool_run is not None and terminal_tool_run.is_terminal():
            self._mark_terminal_tool_runs((terminal_tool_run,))
        with self.uow_factory() as uow:
            run_ids = uow.orchestration_waits.list_run_ids_for_tool_run(tool_run_id)
        if not run_ids:
            return []
        resumed_runs: list[OrchestrationRun] = []
        for run_id in run_ids:
            run = self.get_run(run_id)
            if run.status is not OrchestrationRunStatus.WAITING:
                continue
            pending_tool_runs = tuple(
                self.engine.tool_execution_port.get_tool_run(pending_run_id)
                for pending_run_id in run.pending_tool_run_ids
            )
            self._mark_terminal_tool_runs(
                tuple(tool_run for tool_run in pending_tool_runs if tool_run.is_terminal()),
            )
            if not all(tool_run.is_terminal() for tool_run in pending_tool_runs):
                continue
            item_ids = self.engine.append_completed_background_tool_results(
                run,
                tool_runs=pending_tool_runs,
            )
            self._materialize_tool_result_items(
                run=run,
                tool_runs=pending_tool_runs,
                item_ids=item_ids,
            )
            evidence_frontier = _evidence_frontier_for_tool_runs(
                self.engine,
                run=run,
                tool_runs=pending_tool_runs,
            )
            resumed_runs.append(
                self.resume_run(
                    run.id,
                    OrchestrationQueuePolicy.RESUME_FIRST,
                    self._resume_reason_from_tool_runs(pending_tool_runs),
                    metadata=(
                        {"evidence_frontier": [dict(item) for item in evidence_frontier]}
                        if evidence_frontier
                        else None
                    ),
                ),
            )
        return resumed_runs

    def reconcile_tool_waits(self, tool_run_ids: tuple[str, ...]) -> None:
        for tool_run_id in tool_run_ids:
            try:
                self.handle_terminal_tool_run(tool_run_id)
            except Exception:
                logger.exception(
                    "failed to reconcile orchestration wait after persisting mapping",
                    extra={"tool_run_id": tool_run_id},
                )

    @staticmethod
    def _resume_reason_from_tool_runs(tool_runs: tuple[object, ...]) -> str:
        for tool_run in tool_runs:
            status = getattr(tool_run, "status", None)
            if status is ToolRunStatus.FAILED:
                return "tool_failed_results_ready"
            if status in {
                ToolRunStatus.CANCELLED,
                ToolRunStatus.TIMED_OUT,
            }:
                return "tool_terminal_results_ready"
        return "tool_results_ready"

    def _mark_terminal_tool_runs(self, tool_runs: tuple[object, ...]) -> None:
        if not tool_runs:
            return
        orphaned_tool_runs: list[object] = []
        with self.uow_factory() as uow:
            for tool_run in tool_runs:
                tool_run_id = getattr(tool_run, "id", None)
                status = getattr(tool_run, "status", None)
                if not isinstance(tool_run_id, str):
                    continue
                observed = mark_tool_run_step_item_terminal(
                    uow,
                    tool_run_id=tool_run_id,
                    status=_enum_value(status),
                    summary_payload=_tool_run_terminal_summary(tool_run),
                    error_message=getattr(tool_run, "error_message", None),
                )
                if observed is None and _is_orchestration_owned_tool_run(tool_run):
                    orphaned_tool_runs.append(tool_run)
            uow.commit()
        for tool_run in orphaned_tool_runs:
            self._publish_orphan_tool_result(tool_run)

    def _publish_orphan_tool_result(self, tool_run: object) -> None:
        if self.events_service is None:
            return
        tool_run_id = getattr(tool_run, "id", None)
        if not isinstance(tool_run_id, str) or not tool_run_id.strip():
            return
        payload = _orphan_tool_result_payload(tool_run)
        try:
            self.events_service.publish(
                Event(
                    name=ORCHESTRATION_ORPHAN_TOOL_RESULT_OBSERVED_EVENT,
                    payload=payload,
                    kind="fact",
                    ordering_key=tool_run_id,
                    dedupe_key=(
                        f"{ORCHESTRATION_ORPHAN_TOOL_RESULT_OBSERVED_EVENT}:"
                        f"{tool_run_id}:{payload.get('tool_status')}"
                    ),
                ),
            )
        except Exception:
            logger.exception(
                "failed to publish orphan orchestration tool result observation",
                extra={"tool_run_id": tool_run_id},
            )

    def _materialize_tool_result_items(
        self,
        *,
        run: OrchestrationRun,
        tool_runs: tuple[object, ...],
        item_ids: tuple[str, ...],
    ) -> None:
        links = tuple(
            (tool_run_id, item_id)
            for tool_run, item_id in zip(tool_runs, item_ids, strict=False)
            for tool_run_id in (getattr(tool_run, "id", None),)
            if isinstance(tool_run_id, str)
        )
        if not links:
            return
        with self.uow_factory() as uow:
            materialize_tool_result_session_item_items(
                uow,
                run=run,
                tool_result_item_links=links,
            )
            uow.commit()


def _evidence_frontier_for_tool_runs(
    engine: OrchestrationEngine,
    *,
    run: OrchestrationRun,
    tool_runs: tuple[object, ...],
) -> tuple[dict[str, object], ...]:
    builder = getattr(engine, "evidence_frontier_for_tool_runs", None)
    if not callable(builder):
        return ()
    result = builder(run, tool_runs=tool_runs)
    if not isinstance(result, list | tuple):
        return ()
    return tuple(dict(item) for item in result if isinstance(item, dict))


def _tool_run_terminal_summary(tool_run: object) -> dict[str, object]:
    target = getattr(tool_run, "target", None)
    completed_at = getattr(tool_run, "completed_at", None)
    payload: dict[str, object] = {
        "tool_id": getattr(tool_run, "tool_id", None),
        "function_id": getattr(tool_run, "function_id", None),
        "source_id": getattr(tool_run, "source_id", None),
        "mode": _enum_value(getattr(target, "mode", None)),
        "strategy": _enum_value(getattr(target, "strategy", None)),
        "environment": _enum_value(getattr(target, "environment", None)),
    }
    if completed_at is not None and hasattr(completed_at, "isoformat"):
        payload["completed_at"] = completed_at.isoformat()
    return {key: value for key, value in payload.items() if value is not None}


def _orphan_tool_result_payload(tool_run: object) -> dict[str, object]:
    tool_run_id = getattr(tool_run, "id", None)
    metadata = _tool_run_metadata(tool_run)
    orchestration_run_id = _optional_text(metadata.get("orchestration_run_id"))
    tool_status = _enum_value(getattr(tool_run, "status", None))
    payload: dict[str, object] = {
        "event_name": ORCHESTRATION_ORPHAN_TOOL_RESULT_OBSERVED_EVENT,
        "level": "warning",
        "status": "orphaned",
        "reason": "execution_step_item_not_found",
        "tool_run_id": tool_run_id,
        "run_id": orchestration_run_id,
        "orchestration_run_id": orchestration_run_id,
        "tool_status": tool_status,
        "error_message": getattr(tool_run, "error_message", None),
        "summary": "Terminal orchestration tool result could not be merged into the execution chain.",
        "display_label": "Orphan Tool Result",
        "display_summary": (
            "Terminal tool run has no execution step item; execution chain was not advanced."
        ),
        "display_tone": "warning",
        "entity_type": "tool_run",
        "entity_id": tool_run_id,
        **_tool_run_terminal_summary(tool_run),
    }
    return {key: value for key, value in payload.items() if value is not None}


def _is_orchestration_owned_tool_run(tool_run: object) -> bool:
    metadata = _tool_run_metadata(tool_run)
    source = _optional_text(metadata.get("source"))
    if source == "orchestration":
        return True
    return _optional_text(metadata.get("orchestration_run_id")) is not None


def _tool_run_metadata(tool_run: object) -> dict[str, object]:
    metadata = getattr(tool_run, "metadata", None)
    return dict(metadata) if isinstance(metadata, dict) else {}


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _enum_value(value: object) -> str:
    raw_value = getattr(value, "value", value)
    return raw_value if isinstance(raw_value, str) else str(raw_value)
