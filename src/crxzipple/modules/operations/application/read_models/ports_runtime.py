from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from crxzipple.modules.operations.application.ports import (
    OperationsEventPublishPort as OperationsEventPublishPort,
    OperationsEventStreamPort as OperationsEventStreamPort,
)


class OperationsRuntimeBootstrapConfigPort(Protocol):
    orchestration_run_lease_seconds: float
    orchestration_run_heartbeat_seconds: float
    orchestration_executor_max_concurrent_assignments: int
    orchestration_auto_compaction_enabled: bool
    orchestration_auto_compaction_reserve_tokens: int
    orchestration_auto_compaction_soft_threshold_tokens: int
    tool_run_max_attempts: int
    tool_run_lease_seconds: int
    tool_run_heartbeat_seconds: float
    tool_worker_max_in_flight: int
    tool_worker_default_run_concurrency: int
    tool_worker_image_run_concurrency: int
    tool_worker_shared_state_run_concurrency: int
    tool_remote_default_max_concurrency: int


class OperationsObservationReadPort(Protocol):
    def get_module_observation(self, module: str) -> Any | None: ...

    def snapshot(self) -> Any: ...

    def list_event_buckets(
        self,
        *,
        module: str | None = None,
        event_name: str | None = None,
        since: Any | None = None,
        limit: int = 500,
    ) -> tuple[Mapping[str, Any], ...]: ...


class OperationsEventContractRegistryPort(Protocol):
    def to_payload(self) -> dict[str, Any]: ...

    def list_topic_contracts(self) -> tuple[Any, ...]: ...

    def list_route_contracts(self) -> tuple[Any, ...]: ...


class OperationsEventDefinitionRegistryPort(Protocol):
    def to_payload(self) -> dict[str, Any]: ...

    def list_definitions(self) -> tuple[Any, ...]: ...

    def list_surfaces(self) -> tuple[Any, ...]: ...

    def list_observers(self) -> tuple[Any, ...]: ...


class OperationsRuntimeMetricsPort(Protocol):
    def snapshot(self) -> Mapping[str, Any]: ...


class OperationsObserverRuntimePort(Protocol):
    @property
    def subscriptions(self) -> tuple[Any, ...]: ...

    def snapshot(self) -> Any: ...
