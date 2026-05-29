from __future__ import annotations

from typing import Protocol

from crxzipple.modules.tool.domain.entities import (
    ToolFunction,
    ToolProviderBackend,
    ToolRun,
    ToolRunAssignment,
    ToolSource,
    ToolWorkerRegistration,
)
from crxzipple.modules.tool.domain.value_objects import (
    ToolCatalogSourceKind,
    ToolFunctionStatus,
    ToolProviderBackendStatus,
    ToolProviderCapability,
    ToolSourceStatus,
)


class ToolSourceRepository(Protocol):
    def upsert(self, source: ToolSource) -> None:
        ...

    def get(self, source_id: str) -> ToolSource | None:
        ...

    def list(
        self,
        *,
        kind: ToolCatalogSourceKind | str | None = None,
        status: ToolSourceStatus | str | None = None,
    ) -> list[ToolSource]:
        ...


class ToolFunctionRepository(Protocol):
    def upsert(self, function: ToolFunction) -> None:
        ...

    def get(self, function_id: str) -> ToolFunction | None:
        ...

    def get_by_stable_key(self, stable_key: str) -> ToolFunction | None:
        ...

    def list(
        self,
        *,
        source_id: str | None = None,
        status: ToolFunctionStatus | str | None = None,
    ) -> list[ToolFunction]:
        ...


class ToolProviderBackendRepository(Protocol):
    def upsert(self, backend: ToolProviderBackend) -> None:
        ...

    def get(self, backend_id: str) -> ToolProviderBackend | None:
        ...

    def list(
        self,
        *,
        source_id: str | None = None,
        capability: ToolProviderCapability | str | None = None,
        status: ToolProviderBackendStatus | str | None = None,
    ) -> list[ToolProviderBackend]:
        ...


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
