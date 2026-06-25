from __future__ import annotations

from typing import Any, Protocol


class OperationsMemoryQueryPort(Protocol):
    def agent_scope_inventory(
        self,
        agent_id: str,
        *,
        file_limit: int = 240,
    ) -> Any: ...

    def search_agent(
        self,
        agent_id: str,
        *,
        query: str,
        limit: int = 20,
    ) -> tuple[Any, ...]: ...

    def get_agent_excerpt(
        self,
        agent_id: str,
        *,
        path: str,
        start_line: int | None = None,
        line_count: int | None = None,
    ) -> Any | None: ...

    def get_agent_long_term_excerpt(self, agent_id: str) -> Any | None: ...


class OperationsMemoryWatchRegistryPort(Protocol):
    def snapshot_metrics(self) -> Any: ...


class OperationsContextWorkspacePort(Protocol):
    def list_workspaces(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[Any, ...]: ...


class OperationsContextTreePort(Protocol):
    def list_tree(self, session_key: str) -> Any: ...


class OperationsContextObservationSnapshotPort(Protocol):
    def list_recent_snapshots(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[Any, ...]: ...


class OperationsContextSliceBuilderPort(Protocol):
    def build_slice(self, **kwargs: Any) -> Any: ...


class OperationsSkillCatalogPort(Protocol):
    def list_available(
        self,
        *,
        workspace_dir: str | None = None,
        surface: str | None = None,
    ) -> tuple[Any, ...]: ...
