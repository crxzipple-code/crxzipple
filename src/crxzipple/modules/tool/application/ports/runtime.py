from __future__ import annotations

from threading import Event as ThreadEvent
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from crxzipple.modules.events import EventsApplicationService
    from crxzipple.modules.tool.application.dispatch_events import ToolRuntimeEventService
    from crxzipple.modules.tool.domain import ToolRun


class ToolSchedulerRuntimePort(Protocol):
    def recover_abandoned_runs(self) -> "list[ToolRun]":
        ...

    def assign_next_available(self, *, worker_id: str | None = None) -> "ToolRun | None":
        ...

    def run_until_stopped(
        self,
        *,
        poll_interval_seconds: float,
        max_runs: int | None = None,
        max_idle_cycles: int | None = None,
        stop_event: ThreadEvent | None = None,
        events_service: "EventsApplicationService | None" = None,
    ) -> int:
        ...


class ToolWorkerRuntimePort(Protocol):
    def register_worker(
        self,
        *,
        worker_id: str,
        max_in_flight: int = 1,
        capabilities_payload: dict[str, Any] | None = None,
    ) -> object:
        ...

    def mark_worker_stale(self, *, worker_id: str) -> object | None:
        ...

    def process_next_assigned_run(self, *, worker_id: str) -> "ToolRun | None":
        ...

    def heartbeat_run(self, run_id: str, *, worker_id: str) -> "ToolRun":
        ...

    def cancel_tool_run(self, run_id: str) -> "ToolRun":
        ...

    def run_until_stopped(
        self,
        *,
        worker_id: str,
        poll_interval_seconds: float,
        max_runs: int | None = None,
        max_idle_cycles: int | None = None,
        stop_event: ThreadEvent | None = None,
        events_service: "EventsApplicationService | None" = None,
        runtime_event_service: "ToolRuntimeEventService | None" = None,
        max_in_flight: int = 1,
    ) -> int:
        ...
