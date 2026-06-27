from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from crxzipple.modules.dispatch.domain import DispatchTaskRepository
from crxzipple.modules.tool.application.ports import (
    ToolAccessReadinessPort,
    ToolArtifactWritePort,
    ToolOrchestrationDispatchPort,
    ToolRuntimeReadinessPort,
)
from crxzipple.modules.tool.domain.entities import Tool
from crxzipple.modules.tool.domain.entities import ToolFunction
from crxzipple.modules.tool.domain.value_objects import (
    ToolEnvironment,
    ToolExecutionContext,
    ToolExecutionStrategy,
    ToolExecutionTarget,
    ToolMode,
    ToolRunError,
    ToolRunResult,
)
from crxzipple.shared.domain.aggregates import AggregateRoot
from crxzipple.shared.runtime_metrics import RuntimeMetricsRegistry


DISPATCH_LEASE_EXPIRED_REASON = "Worker lease expired before completion."
DISPATCH_LEASE_EXHAUSTED_REASON = "Worker lease expired and retry budget exhausted."
SYSTEM_MANAGED_TOOL_TAG = "system-managed"


@dataclass(frozen=True, slots=True)
class ExecuteToolInput:
    tool_id: str
    arguments: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    call_id: str | None = None
    tool_surface_id: str | None = None
    mode: ToolMode = ToolMode.INLINE
    strategy: ToolExecutionStrategy = ToolExecutionStrategy.ASYNC
    environment: ToolEnvironment = ToolEnvironment.LOCAL
    run_id: str | None = None
    execution_context: ToolExecutionContext | None = None


@dataclass(frozen=True, slots=True)
class PreparedToolRunExecution:
    tool: Tool
    arguments: dict[str, Any]
    run_id: str
    target: ToolExecutionTarget
    worker_id: str | None
    execution_context: ToolExecutionContext | None


@dataclass(frozen=True, slots=True)
class PreparedToolRunRequest:
    data: ExecuteToolInput
    tool: Tool
    target: ToolExecutionTarget
    function: ToolFunction
    source_revision: int | None = None
    provider_backend_payload: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class PreparedToolRunCompletion:
    run_id: str
    output: ToolRunResult | None = None
    error_message: str | ToolRunError | None = None


class ToolUnitOfWork(Protocol):
    dispatch_tasks: DispatchTaskRepository
    tool_sources: Any
    tool_functions: Any
    tool_provider_backends: Any
    tool_surfaces: Any
    tool_runs: Any
    tool_run_assignments: Any
    tool_workers: Any

    def __enter__(self) -> "ToolUnitOfWork":
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        ...

    def collect(self, aggregate: AggregateRoot[Any]) -> None:
        ...

    def commit(self) -> None:
        ...

    def rollback(self) -> None:
        ...


class ToolRuntimeGateway(Protocol):
    def list_registered_tools(self) -> list[Tool]:
        ...

    async def execute(
        self,
        tool: Tool,
        target: ToolExecutionTarget,
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        ...


@dataclass(slots=True)
class ToolServiceDependencies:
    uow_factory: Callable[[], ToolUnitOfWork]
    runtime_gateway: ToolRuntimeGateway
    runtime_registry: Any | None
    dispatch_port: ToolOrchestrationDispatchPort
    access_readiness: ToolAccessReadinessPort | None
    runtime_readiness: ToolRuntimeReadinessPort | None
    artifact_service: ToolArtifactWritePort | None
    default_max_attempts: int
    worker_lease_seconds: int
    worker_heartbeat_seconds: float
    details_max_chars: int
    worker_default_run_concurrency: int
    worker_image_run_concurrency: int
    worker_shared_state_run_concurrency: int
    metrics: RuntimeMetricsRegistry


class ToolServiceBase:
    def __init__(self, deps: ToolServiceDependencies) -> None:
        self.deps = deps

    @property
    def uow_factory(self) -> Callable[[], ToolUnitOfWork]:
        return self.deps.uow_factory

    @property
    def runtime_gateway(self) -> ToolRuntimeGateway:
        return self.deps.runtime_gateway

    @property
    def dispatch_port(self) -> ToolOrchestrationDispatchPort:
        return self.deps.dispatch_port

    @property
    def access_readiness(self) -> ToolAccessReadinessPort | None:
        return self.deps.access_readiness

    @property
    def runtime_readiness(self) -> ToolRuntimeReadinessPort | None:
        return self.deps.runtime_readiness

    @property
    def artifact_service(self) -> ToolArtifactWritePort | None:
        return self.deps.artifact_service

    @property
    def default_max_attempts(self) -> int:
        return self.deps.default_max_attempts

    @property
    def worker_lease_seconds(self) -> int:
        return self.deps.worker_lease_seconds

    @property
    def worker_heartbeat_seconds(self) -> float:
        return self.deps.worker_heartbeat_seconds

    @property
    def details_max_chars(self) -> int:
        return self.deps.details_max_chars

    @property
    def metrics(self) -> RuntimeMetricsRegistry:
        return self.deps.metrics


__all__ = [
    "DISPATCH_LEASE_EXHAUSTED_REASON",
    "DISPATCH_LEASE_EXPIRED_REASON",
    "ExecuteToolInput",
    "PreparedToolRunCompletion",
    "PreparedToolRunExecution",
    "PreparedToolRunRequest",
    "SYSTEM_MANAGED_TOOL_TAG",
    "ToolRuntimeGateway",
    "ToolServiceBase",
    "ToolServiceDependencies",
    "ToolUnitOfWork",
]
