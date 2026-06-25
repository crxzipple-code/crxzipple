from __future__ import annotations

from crxzipple.modules.tool.domain import ToolRunAssignmentStatus
from crxzipple.modules.tool.domain.entities import (
    ToolRun,
    ToolRunAssignment,
    ToolWorkerRegistration,
)


class InMemoryToolRunRepository:
    def __init__(self) -> None:
        self._items: dict[str, ToolRun] = {}

    def add(self, tool_run: ToolRun) -> None:
        self._items[tool_run.id] = tool_run

    def add_new(self, tool_run: ToolRun) -> None:
        self.add(tool_run)

    def add_many_new(self, tool_runs: tuple[ToolRun, ...]) -> None:
        for tool_run in tool_runs:
            self.add_new(tool_run)

    def get(self, run_id: str) -> ToolRun | None:
        return self._items.get(run_id)

    def get_many(self, run_ids: tuple[str, ...]) -> dict[str, ToolRun]:
        return {
            run_id: tool_run
            for run_id in run_ids
            if (tool_run := self._items.get(run_id)) is not None
        }

    def list(self, *, limit: int | None = None) -> list[ToolRun]:
        items = sorted(
            self._items.values(),
            key=lambda run: run.created_at,
            reverse=True,
        )
        if limit is not None:
            return items[:limit]
        return items

    def list_for_tool(self, tool_id: str, *, limit: int | None = None) -> list[ToolRun]:
        items = [
            run
            for run in self.list(limit=None)
            if run.tool_id == tool_id
        ]
        if limit is not None:
            return items[:limit]
        return items

    def list_for_orchestration_runs(self, run_ids: tuple[str, ...]) -> list[ToolRun]:
        normalized_ids = {run_id for run_id in run_ids if run_id.strip()}
        if not normalized_ids:
            return []
        return [
            run
            for run in self._items.values()
            if str(run.metadata.get("orchestration_run_id", "")).strip()
            in normalized_ids
        ]


class InMemoryToolRunAssignmentRepository:
    def __init__(self) -> None:
        self._items: dict[str, ToolRunAssignment] = {}

    def add(self, assignment: ToolRunAssignment) -> None:
        self._items[assignment.id] = assignment

    def add_new(self, assignment: ToolRunAssignment) -> None:
        self.add(assignment)

    def get(self, assignment_id: str) -> ToolRunAssignment | None:
        return self._items.get(assignment_id)

    def get_latest_for_run(self, run_id: str) -> ToolRunAssignment | None:
        assignments = self.list_for_run(run_id)
        if not assignments:
            return None
        return assignments[0]

    def get_latest_for_run_and_worker(
        self,
        run_id: str,
        worker_id: str,
    ) -> ToolRunAssignment | None:
        for assignment in self.list_for_run(run_id):
            if assignment.worker_id == worker_id:
                return assignment
        return None

    def list_for_run(self, run_id: str) -> list[ToolRunAssignment]:
        return sorted(
            [
                assignment
                for assignment in self._items.values()
                if assignment.run_id == run_id
            ],
            key=lambda assignment: assignment.assigned_at,
            reverse=True,
        )

    def get_next_for_worker(self, worker_id: str) -> ToolRunAssignment | None:
        assignments = [
            assignment
            for assignment in self._items.values()
            if assignment.worker_id == worker_id
            and assignment.status in {
                ToolRunAssignmentStatus.ASSIGNED,
                ToolRunAssignmentStatus.RUNNING,
            }
        ]
        if not assignments:
            return None
        assignments.sort(key=lambda assignment: assignment.assigned_at)
        return assignments[0]

    def list_for_worker(self, worker_id: str) -> list[ToolRunAssignment]:
        return sorted(
            [
                assignment
                for assignment in self._items.values()
                if assignment.worker_id == worker_id
            ],
            key=lambda assignment: assignment.assigned_at,
            reverse=True,
        )

    def list(self) -> list[ToolRunAssignment]:
        return sorted(
            list(self._items.values()),
            key=lambda assignment: assignment.assigned_at,
            reverse=True,
        )


class InMemoryToolWorkerRepository:
    def __init__(self) -> None:
        self._items: dict[str, ToolWorkerRegistration] = {}

    def add(self, worker: ToolWorkerRegistration) -> None:
        self._items[worker.id] = worker

    def add_new(self, worker: ToolWorkerRegistration) -> None:
        self.add(worker)

    def get(self, worker_id: str) -> ToolWorkerRegistration | None:
        return self._items.get(worker_id)

    def list(self) -> list[ToolWorkerRegistration]:
        return list(self._items.values())

    def delete(self, worker_id: str) -> None:
        self._items.pop(worker_id, None)
