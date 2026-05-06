from __future__ import annotations

from typing import Protocol

from crxzipple.modules.tool.domain.entities import (
    ToolRun,
    ToolRunAssignment,
    ToolWorkerRegistration,
)


class ToolRunRepository(Protocol):
    def add(self, tool_run: ToolRun) -> None:
        ...

    def add_new(self, tool_run: ToolRun) -> None:
        ...

    def add_many_new(self, tool_runs: tuple[ToolRun, ...]) -> None:
        ...

    def get(self, run_id: str) -> ToolRun | None:
        ...

    def get_many(self, run_ids: tuple[str, ...]) -> dict[str, ToolRun]:
        ...

    def list(self) -> list[ToolRun]:
        ...

    def list_for_tool(self, tool_id: str) -> list[ToolRun]:
        ...


class ToolRunAssignmentRepository(Protocol):
    def add(self, assignment: ToolRunAssignment) -> None:
        ...

    def add_new(self, assignment: ToolRunAssignment) -> None:
        ...

    def get(self, assignment_id: str) -> ToolRunAssignment | None:
        ...

    def get_latest_for_run(self, run_id: str) -> ToolRunAssignment | None:
        ...

    def get_latest_for_run_and_worker(
        self,
        run_id: str,
        worker_id: str,
    ) -> ToolRunAssignment | None:
        ...

    def list_for_run(self, run_id: str) -> list[ToolRunAssignment]:
        ...

    def get_next_for_worker(self, worker_id: str) -> ToolRunAssignment | None:
        ...

    def list_for_worker(self, worker_id: str) -> list[ToolRunAssignment]:
        ...

    def list(self) -> list[ToolRunAssignment]:
        ...


class ToolWorkerRepository(Protocol):
    def add(self, worker: ToolWorkerRegistration) -> None:
        ...

    def add_new(self, worker: ToolWorkerRegistration) -> None:
        ...

    def get(self, worker_id: str) -> ToolWorkerRegistration | None:
        ...

    def list(self) -> list[ToolWorkerRegistration]:
        ...

    def delete(self, worker_id: str) -> None:
        ...
