from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from crxzipple.modules.artifacts.application.services import ArtifactApplicationService
from crxzipple.modules.dispatch.domain import DispatchTaskRepository
from crxzipple.modules.tool.application.discovery import ToolDiscoveryGateway
from crxzipple.modules.tool.application.ports import ToolRunDispatchPort
from crxzipple.modules.tool.application.specifications import ToolSpec
from crxzipple.modules.tool.domain.entities import Tool
from crxzipple.modules.tool.domain.value_objects import (
    ToolEnvironment,
    ToolExecutionContext,
    ToolExecutionPolicy,
    ToolExecutionStrategy,
    ToolExecutionSupport,
    ToolExecutionTarget,
    ToolKind,
    ToolMode,
    ToolParameter,
    ToolRunResult,
    ToolSourceKind,
)
from crxzipple.shared.domain.aggregates import AggregateRoot
from crxzipple.shared.runtime_metrics import RuntimeMetricsRegistry

DISPATCH_LEASE_EXPIRED_REASON = "Worker lease expired before completion."
DISPATCH_LEASE_EXHAUSTED_REASON = "Worker lease expired and retry budget exhausted."
SYSTEM_MANAGED_TOOL_TAG = "system-managed"


@dataclass(frozen=True, slots=True)
class RegisterToolParameterInput:
    name: str
    data_type: str
    description: str = ""
    required: bool = True


@dataclass(frozen=True, slots=True)
class RegisterToolInput:
    id: str
    name: str
    description: str
    kind: ToolKind = ToolKind.FUNCTION
    parameters: tuple[RegisterToolParameterInput, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)
    required_effect_ids: tuple[str, ...] = field(default_factory=tuple)
    access_requirements: tuple[str, ...] = field(default_factory=tuple)
    access_requirement_sets: tuple[tuple[str, ...], ...] = field(default_factory=tuple)
    timeout_seconds: int = 30
    requires_confirmation: bool = False
    mutates_state: bool = False
    supported_modes: tuple[ToolMode, ...] = (ToolMode.INLINE,)
    supported_strategies: tuple[ToolExecutionStrategy, ...] = (
        ToolExecutionStrategy.ASYNC,
    )
    supported_environments: tuple[ToolEnvironment, ...] = (ToolEnvironment.LOCAL,)
    source_kind: ToolSourceKind = ToolSourceKind.MANUAL
    runtime_key: str | None = None
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class SetToolAvailabilityInput:
    id: str
    enabled: bool


@dataclass(frozen=True, slots=True)
class ExecuteToolInput:
    tool_id: str
    arguments: dict[str, Any] = field(default_factory=dict)
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


@dataclass(frozen=True, slots=True)
class PreparedToolRunCompletion:
    run_id: str
    output: ToolRunResult | None = None
    error_message: str | None = None


class ToolUnitOfWork(Protocol):
    dispatch_tasks: DispatchTaskRepository
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
    def list_local_tools(self) -> list[Tool]:
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
    discovery_gateway: ToolDiscoveryGateway | None
    dispatch_port: ToolRunDispatchPort
    artifact_service: ArtifactApplicationService | None
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
    def discovery_gateway(self) -> ToolDiscoveryGateway | None:
        return self.deps.discovery_gateway

    @property
    def dispatch_port(self) -> ToolRunDispatchPort:
        return self.deps.dispatch_port

    @property
    def artifact_service(self) -> ArtifactApplicationService | None:
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


def build_tool_from_registration(data: RegisterToolInput) -> Tool:
    return Tool(
        id=data.id,
        name=data.name,
        description=data.description,
        kind=data.kind,
        parameters=tuple(
            ToolParameter(
                name=parameter.name,
                data_type=parameter.data_type,
                description=parameter.description,
                required=parameter.required,
            )
            for parameter in data.parameters
        ),
        tags=data.tags,
        required_effect_ids=data.required_effect_ids,
        access_requirements=data.access_requirements,
        access_requirement_sets=data.access_requirement_sets,
        execution_policy=ToolExecutionPolicy(
            timeout_seconds=data.timeout_seconds,
            requires_confirmation=data.requires_confirmation,
            mutates_state=data.mutates_state,
        ),
        execution_support=ToolExecutionSupport(
            supported_modes=data.supported_modes,
            supported_strategies=data.supported_strategies,
            supported_environments=data.supported_environments,
        ),
        source_kind=data.source_kind,
        runtime_key=data.runtime_key,
        enabled=data.enabled,
    )


def build_tool_from_spec(spec: ToolSpec) -> Tool:
    return Tool(
        id=spec.id,
        name=spec.name,
        description=spec.description,
        kind=spec.kind,
        parameters=spec.parameters,
        tags=spec.tags,
        required_effect_ids=spec.required_effect_ids,
        access_requirements=spec.access_requirements,
        access_requirement_sets=spec.access_requirement_sets,
        execution_policy=spec.execution_policy,
        execution_support=spec.execution_support,
        source_kind=spec.source_kind,
        runtime_key=spec.runtime_key,
        enabled=spec.enabled,
    )


def decode_tool_attachment_bytes(data: str) -> bytes | None:
    try:
        return base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        return None
