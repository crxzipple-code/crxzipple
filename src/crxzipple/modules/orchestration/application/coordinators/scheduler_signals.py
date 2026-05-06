from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from crxzipple.modules.orchestration.domain import (
    OrchestrationSchedulerSignal,
    OrchestrationSchedulerSignalKind,
    OrchestrationSchedulerSignalRepository,
)
from crxzipple.shared.domain.aggregates import AggregateRoot


class SchedulerSignalCoordinatorUnitOfWork(Protocol):
    orchestration_scheduler_signals: OrchestrationSchedulerSignalRepository

    def __enter__(self) -> "SchedulerSignalCoordinatorUnitOfWork":
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        ...

    def collect(self, aggregate: AggregateRoot[Any]) -> None:
        ...

    def commit(self) -> None:
        ...


@dataclass(slots=True)
class RunSchedulerSignalCoordinator:
    uow_factory: Callable[[], SchedulerSignalCoordinatorUnitOfWork]

    def queue_tool_terminal_signal(self, *, tool_run_id: str) -> OrchestrationSchedulerSignal:
        signal_id = f"tool-terminal:{tool_run_id.strip()}"
        return self._queue_signal(
            signal_id=signal_id,
            signal_kind=OrchestrationSchedulerSignalKind.TOOL_TERMINAL,
            signal_payload={"tool_run_id": tool_run_id.strip()},
        )

    def queue_sessions_spawn_followup_signal(
        self,
        *,
        child_run_id: str,
    ) -> OrchestrationSchedulerSignal:
        signal_id = f"sessions-spawn-followup:{child_run_id.strip()}"
        return self._queue_signal(
            signal_id=signal_id,
            signal_kind=OrchestrationSchedulerSignalKind.SESSIONS_SPAWN_FOLLOWUP,
            signal_payload={"child_run_id": child_run_id.strip()},
        )

    def claim_next_signal(
        self,
        *,
        worker_id: str,
    ) -> OrchestrationSchedulerSignal | None:
        with self.uow_factory() as uow:
            signal = uow.orchestration_scheduler_signals.claim_next(
                worker_id=worker_id,
            )
            if signal is None:
                return None
            uow.collect(signal)
            uow.commit()
            return signal

    def complete_signal(self, signal_id: str) -> OrchestrationSchedulerSignal | None:
        with self.uow_factory() as uow:
            signal = uow.orchestration_scheduler_signals.get(signal_id)
            if signal is None:
                return None
            signal.complete()
            uow.orchestration_scheduler_signals.add(signal)
            uow.collect(signal)
            uow.commit()
            return signal

    def fail_signal(
        self,
        signal_id: str,
        *,
        message: str,
        code: str = "scheduler_signal_failed",
        details: dict[str, object] | None = None,
    ) -> OrchestrationSchedulerSignal | None:
        with self.uow_factory() as uow:
            signal = uow.orchestration_scheduler_signals.get(signal_id)
            if signal is None:
                return None
            signal.fail(
                message=message,
                code=code,
                details=details or {},
            )
            uow.orchestration_scheduler_signals.add(signal)
            uow.collect(signal)
            uow.commit()
            return signal

    def _queue_signal(
        self,
        *,
        signal_id: str,
        signal_kind: OrchestrationSchedulerSignalKind,
        signal_payload: dict[str, object],
    ) -> OrchestrationSchedulerSignal:
        try:
            return self._queue_signal_once(
                signal_id=signal_id,
                signal_kind=signal_kind,
                signal_payload=signal_payload,
            )
        except Exception:
            existing = self._get_equivalent_signal(
                signal_id=signal_id,
                signal_kind=signal_kind,
                signal_payload=signal_payload,
            )
            if existing is not None:
                return existing
            raise

    def _queue_signal_once(
        self,
        *,
        signal_id: str,
        signal_kind: OrchestrationSchedulerSignalKind,
        signal_payload: dict[str, object],
    ) -> OrchestrationSchedulerSignal:
        with self.uow_factory() as uow:
            existing = uow.orchestration_scheduler_signals.get(signal_id)
            if existing is not None:
                return existing
            signal = OrchestrationSchedulerSignal.queue(
                signal_id=signal_id,
                signal_kind=signal_kind,
                signal_payload=signal_payload,
            )
            uow.orchestration_scheduler_signals.add(signal)
            uow.collect(signal)
            uow.commit()
            return signal

    def _get_equivalent_signal(
        self,
        *,
        signal_id: str,
        signal_kind: OrchestrationSchedulerSignalKind,
        signal_payload: dict[str, object],
    ) -> OrchestrationSchedulerSignal | None:
        with self.uow_factory() as uow:
            existing = uow.orchestration_scheduler_signals.get(signal_id)
        if existing is None:
            return None
        if existing.signal_kind is not signal_kind:
            return None
        if existing.signal_payload != signal_payload:
            return None
        return existing
