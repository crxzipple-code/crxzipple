"""Cancellation service for orchestration runs and session trees."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from crxzipple.core.logger import get_logger
from crxzipple.modules.orchestration.application.unit_of_work import (
    OrchestrationUnitOfWork,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationRun,
    OrchestrationRunStatus,
)
from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationRunNotFoundError,
    OrchestrationValidationError,
)
from crxzipple.modules.session.application import SessionApplicationService

logger = get_logger(__name__)


@dataclass(slots=True)
class RunCancellationService:
    """Owns run and session-tree cancellation semantics."""

    uow_factory: Callable[[], OrchestrationUnitOfWork]
    session_service: SessionApplicationService | None
    get_run: Callable[[str], OrchestrationRun]
    list_runs: Callable[[], list[OrchestrationRun]]
    cancel_run_record: Callable[..., OrchestrationRun]
    release_executor_assignment: Callable[..., None]
    cancel_tool_run: Callable[[str], object] | None = None

    def cancel_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
    ) -> OrchestrationRun:
        run = self.get_run(run_id)
        release_worker_id = (
            run.worker_id
            if run.status is OrchestrationRunStatus.RUNNING
            else None
        )
        session_key = run.session_key
        if not session_key or self.session_service is None:
            if run.status in {
                OrchestrationRunStatus.COMPLETED,
                OrchestrationRunStatus.FAILED,
                OrchestrationRunStatus.CANCELLED,
            }:
                return run
            cancelled = self.cancel_run_record(run_id, reason=reason)
            if release_worker_id is not None:
                self.release_executor_assignment(worker_id=release_worker_id)
            return cancelled
        summary = self.cancel_session_tree(session_key, reason=reason)
        return self._record_cancel_cascade(run_id, summary=summary)

    def cancel_session_tree(
        self,
        session_key: str,
        *,
        reason: str | None = None,
    ) -> dict[str, object]:
        normalized_session_key = session_key.strip()
        if not normalized_session_key:
            raise OrchestrationValidationError(
                "session_key is required for session-tree cancellation.",
            )
        session_keys = self._collect_session_tree_session_keys(normalized_session_key)
        targeted_session_keys = set(session_keys)
        cancelled_run_ids: list[str] = []
        terminal_run_ids: list[str] = []
        cancelled_tool_run_ids: list[str] = []
        for run in self.list_runs():
            current_session_key = run.session_key or ""
            if current_session_key not in targeted_session_keys:
                continue
            if run.status in {
                OrchestrationRunStatus.COMPLETED,
                OrchestrationRunStatus.FAILED,
                OrchestrationRunStatus.CANCELLED,
            }:
                terminal_run_ids.append(run.id)
                continue
            release_worker_id = (
                run.worker_id
                if run.status is OrchestrationRunStatus.RUNNING
                else None
            )
            cancelled_tool_run_ids.extend(self._cancel_pending_tool_runs(run))
            cancelled = self.cancel_run_record(run.id, reason=reason)
            if release_worker_id is not None:
                self.release_executor_assignment(worker_id=release_worker_id)
            cancelled_run_ids.append(cancelled.id)
        unique_cancelled_tool_run_ids = tuple(dict.fromkeys(cancelled_tool_run_ids))
        return {
            "root_session_key": normalized_session_key,
            "session_keys": list(session_keys),
            "cancelled_run_ids": cancelled_run_ids,
            "terminal_run_ids": terminal_run_ids,
            "cancelled_tool_run_ids": list(unique_cancelled_tool_run_ids),
            "cancelled_run_count": len(cancelled_run_ids),
            "terminal_run_count": len(terminal_run_ids),
            "cancelled_tool_run_count": len(unique_cancelled_tool_run_ids),
            "reason": reason.strip()
            if isinstance(reason, str) and reason.strip()
            else None,
        }

    def _record_cancel_cascade(
        self,
        run_id: str,
        *,
        summary: dict[str, object],
    ) -> OrchestrationRun:
        with self.uow_factory() as uow:
            run = self._get_run(uow, run_id)
            run.metadata["cancel_cascade"] = dict(summary)
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    def _collect_session_tree_session_keys(
        self,
        root_session_key: str,
    ) -> tuple[str, ...]:
        if self.session_service is None:
            return (root_session_key,)
        root_session = self.session_service.get_session(root_session_key)
        binding = root_session.runtime_binding()
        agent_id = binding.agent_id or root_session.agent_id
        sessions = self.session_service.list_sessions(agent_id=agent_id)
        children_by_requester: dict[str, list[str]] = {}
        for session in sessions:
            spawn_payload = session.metadata.get("spawn")
            if not isinstance(spawn_payload, dict):
                continue
            requester_session_key = str(
                spawn_payload.get("requester_session_key", ""),
            ).strip()
            if not requester_session_key:
                continue
            children_by_requester.setdefault(requester_session_key, []).append(
                session.id,
            )
        ordered: list[str] = []
        pending = [root_session_key]
        seen: set[str] = set()
        while pending:
            current = pending.pop(0)
            if current in seen:
                continue
            seen.add(current)
            ordered.append(current)
            pending.extend(children_by_requester.get(current, ()))
        return tuple(ordered)

    def _cancel_pending_tool_runs(self, run: OrchestrationRun) -> list[str]:
        if self.cancel_tool_run is None:
            return []
        cancelled: list[str] = []
        for tool_run_id in run.pending_tool_run_ids:
            try:
                tool_run = self.cancel_tool_run(tool_run_id)
            except Exception:
                logger.exception(
                    "failed to cancel pending tool run during session-tree cancellation",
                    extra={"run_id": run.id, "tool_run_id": tool_run_id},
                )
                continue
            tool_run_id_value = str(getattr(tool_run, "id", "") or "").strip()
            if tool_run_id_value and tool_run_id_value not in cancelled:
                cancelled.append(tool_run_id_value)
        return cancelled

    @staticmethod
    def _get_run(uow: OrchestrationUnitOfWork, run_id: str) -> OrchestrationRun:
        run = uow.orchestration_runs.get(run_id)
        if run is None:
            raise OrchestrationRunNotFoundError(
                f"Orchestration run '{run_id}' was not found.",
            )
        return run
