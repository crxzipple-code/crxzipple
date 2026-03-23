from __future__ import annotations

from crxzipple.modules.orchestration.domain.entities import OrchestrationRun
from crxzipple.modules.orchestration.domain.value_objects import OrchestrationRunStatus


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
    ) -> list[OrchestrationRun]:
        items = list(self._items.values())
        if status is not None:
            items = [item for item in items if item.status is status]
        return sorted(items, key=lambda item: (item.created_at, item.id), reverse=True)


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
