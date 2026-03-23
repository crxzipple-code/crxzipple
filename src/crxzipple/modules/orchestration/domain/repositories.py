from __future__ import annotations

from typing import Protocol

from crxzipple.modules.orchestration.domain.entities import OrchestrationRun
from crxzipple.modules.orchestration.domain.value_objects import OrchestrationRunStatus


class OrchestrationRunRepository(Protocol):
    def add(self, run: OrchestrationRun) -> None:
        ...

    def get(self, run_id: str) -> OrchestrationRun | None:
        ...

    def list(
        self,
        *,
        status: OrchestrationRunStatus | None = None,
    ) -> list[OrchestrationRun]:
        ...


class OrchestrationRunWaitRepository(Protocol):
    def replace_tool_waits(self, run_id: str, tool_run_ids: tuple[str, ...]) -> None:
        ...

    def delete_for_run(self, run_id: str) -> None:
        ...

    def list_run_ids_for_tool_run(self, tool_run_id: str) -> list[str]:
        ...
