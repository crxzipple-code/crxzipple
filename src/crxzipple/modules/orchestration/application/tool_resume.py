from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from crxzipple.core.logger import get_logger
from crxzipple.modules.orchestration.application.engine import OrchestrationEngine
from crxzipple.modules.orchestration.domain import (
    OrchestrationRun,
    OrchestrationRunStatus,
    OrchestrationRunWaitRepository,
    OrchestrationQueuePolicy,
)
from crxzipple.modules.tool.domain import ToolRunStatus


logger = get_logger(__name__)


class WaitLookupUnitOfWork(Protocol):
    orchestration_waits: OrchestrationRunWaitRepository

    def __enter__(self) -> "WaitLookupUnitOfWork":
        ...

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        ...


@dataclass(slots=True)
class OrchestrationToolResumeCoordinator:
    uow_factory: Callable[[], WaitLookupUnitOfWork]
    engine: OrchestrationEngine
    get_run: Callable[[str], OrchestrationRun]
    resume_run: Callable[[str, OrchestrationQueuePolicy, str], OrchestrationRun]

    def handle_terminal_tool_run(self, tool_run_id: str) -> list[OrchestrationRun]:
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
            if not all(tool_run.is_terminal() for tool_run in pending_tool_runs):
                continue
            self.engine.append_completed_background_tool_results(
                run,
                tool_runs=pending_tool_runs,
            )
            resumed_runs.append(
                self.resume_run(
                    run.id,
                    OrchestrationQueuePolicy.RESUME_FIRST,
                    self._resume_reason_from_tool_runs(pending_tool_runs),
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
