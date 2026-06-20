from __future__ import annotations

from datetime import datetime

from crxzipple.modules.orchestration.domain.entities import OrchestrationRun
from crxzipple.modules.orchestration.domain.value_objects import (
    OrchestrationRunStage,
    OrchestrationRunStatus,
    utcnow,
)


class InMemoryOrchestrationRunRepository:
    def __init__(self) -> None:
        self._items: dict[str, OrchestrationRun] = {}

    def add(self, run: OrchestrationRun) -> None:
        self._items[run.id] = run

    def get(self, run_id: str) -> OrchestrationRun | None:
        return self._items.get(run_id)

    def list(
        self,
        *,
        status: OrchestrationRunStatus | None = None,
        session_key: str | None = None,
    ) -> list[OrchestrationRun]:
        items = list(self._items.values())
        if status is not None:
            items = [item for item in items if item.status is status]
        normalized_session_key = (session_key or "").strip()
        if normalized_session_key:
            items = [
                item
                for item in items
                if (item.session_key or "").strip() == normalized_session_key
            ]
        return sorted(items, key=lambda item: (item.created_at, item.id), reverse=True)

    def find_next_assigned(
        self,
        *,
        worker_id: str,
        exclude_run_ids: tuple[str, ...] = (),
    ) -> OrchestrationRun | None:
        normalized_worker_id = worker_id.strip()
        if not normalized_worker_id:
            return None
        excluded = set(exclude_run_ids)
        assigned = [
            item
            for item in self._items.values()
            if item.status is OrchestrationRunStatus.RUNNING
            and item.worker_id == normalized_worker_id
            and item.id not in excluded
        ]
        assigned.sort(
            key=lambda item: (
                item.started_at or item.updated_at,
                item.updated_at,
                item.id,
            ),
        )
        return assigned[0] if assigned else None

    def claim_queued_for_assignment(
        self,
        *,
        run_id: str,
        worker_id: str,
        claimed_at: datetime | None = None,
    ) -> OrchestrationRun | None:
        run = self._items.get(run_id)
        if run is None:
            return None
        if run.status is not OrchestrationRunStatus.QUEUED:
            return None
        if run.lane_key is not None:
            lane_is_active = any(
                item.id != run.id
                and item.lane_lock_key == run.lane_key
                and item.status
                in {
                    OrchestrationRunStatus.RUNNING,
                    OrchestrationRunStatus.WAITING,
                }
                for item in self._items.values()
            )
            if lane_is_active:
                return None
        normalized_worker_id = worker_id.strip()
        if not normalized_worker_id:
            return None
        timestamp = claimed_at or utcnow()
        run.status = OrchestrationRunStatus.RUNNING
        run.stage = OrchestrationRunStage.RUNNING
        run.worker_id = normalized_worker_id
        run.lane_lock_key = run.lane_key
        run.started_at = timestamp
        run.updated_at = timestamp
        return run


class InMemoryOrchestrationRunWaitRepository:
    def __init__(self) -> None:
        self._by_run: dict[str, tuple[str, ...]] = {}

    def replace_tool_waits(self, run_id: str, tool_run_ids: tuple[str, ...]) -> None:
        self._by_run[run_id] = tuple(dict.fromkeys(tool_run_ids))

    def delete_for_run(self, run_id: str) -> None:
        self._by_run.pop(run_id, None)

    def list_run_ids_for_tool_run(self, tool_run_id: str) -> list[str]:
        return sorted(
            run_id
            for run_id, waits in self._by_run.items()
            if tool_run_id in waits
        )
