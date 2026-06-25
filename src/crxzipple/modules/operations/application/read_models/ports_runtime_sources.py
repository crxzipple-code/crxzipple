from __future__ import annotations

from typing import Any, Protocol


class OperationsBrowserProfilePort(Protocol):
    def list_profiles(self) -> tuple[Any, ...]: ...

    def list_pools(self) -> tuple[Any, ...]: ...

    def list_allocations(self) -> tuple[Any, ...]: ...


class OperationsChannelProfilePort(Protocol):
    def list_profiles(self) -> tuple[Any, ...]: ...


class OperationsChannelRuntimePort(Protocol):
    def list_runtimes(self, *, channel_type: str | None = None) -> tuple[Any, ...]: ...

    def list_account_bindings(
        self,
        *,
        runtime_id: str | None = None,
    ) -> tuple[Any, ...]: ...

    def list_connection_bindings(
        self,
        *,
        runtime_id: str | None = None,
    ) -> tuple[Any, ...]: ...


class OperationsChannelInteractionPort(Protocol):
    def list_interactions(self) -> tuple[Any, ...]: ...


class OperationsDaemonRegistryPort(Protocol):
    def list_service_specs(self) -> tuple[Any, ...]: ...

    def list_service_sets(self) -> tuple[Any, ...]: ...

    def list_leases(self, *, service_key: str | None = None) -> tuple[Any, ...]: ...


class OperationsDaemonManagerPort(Protocol):
    def list_instances(self, *, refresh: bool = False) -> tuple[Any, ...]: ...


class OperationsProcessQueryPort(Protocol):
    def list_sessions_metadata(self) -> tuple[Any, ...]: ...

    def list_sessions(self) -> tuple[Any, ...]: ...

    def get_session(self, session_id: str) -> Any | None: ...

    def read_output(self, session_id: str, *, tail: int | None = None) -> str: ...
