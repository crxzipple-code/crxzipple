from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import dataclass, field
import threading
from typing import Any, Callable, Protocol
from uuid import uuid4

from crxzipple.core.logger import get_logger
from crxzipple.modules.dispatch.application import (
    DispatchApplicationService,
    RecoverAbandonedDispatchTasksInput,
)
from crxzipple.modules.tool.application.discovery import (
    ToolDiscoveryGateway,
    ToolDiscoveryProviderDescriptor,
)
from crxzipple.modules.tool.application.dispatch_bridge import ToolDispatchBridge
from crxzipple.modules.tool.application.specifications import ToolSpec
from crxzipple.modules.tool.domain.entities import Tool, ToolRun
from crxzipple.modules.tool.domain.exceptions import (
    ToolAlreadyExistsError,
    ToolDiscoveryProviderNotFoundError,
    ToolExecutionNotAllowedError,
    ToolExecutionNotSupportedError,
    ToolNotFoundError,
    ToolRunNotFoundError,
)
from crxzipple.modules.tool.domain.repositories import ToolRepository, ToolRunRepository
from crxzipple.modules.tool.domain.value_objects import (
    ToolEnvironment,
    ToolExecutionPolicy,
    ToolExecutionStrategy,
    ToolExecutionSupport,
    ToolExecutionTarget,
    ToolKind,
    ToolMode,
    ToolParameter,
    ToolRunStatus,
    ToolSourceKind,
)
from crxzipple.shared.domain.aggregates import AggregateRoot
from crxzipple.shared.domain.events import DomainEvent
from crxzipple.modules.dispatch.domain import DispatchTaskRepository

logger = get_logger(__name__)
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


class ToolUnitOfWork(Protocol):
    dispatch_tasks: DispatchTaskRepository
    tools: ToolRepository
    tool_runs: ToolRunRepository

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
    ) -> Any:
        ...

class ToolApplicationService:
    def __init__(
        self,
        uow_factory: Callable[[], ToolUnitOfWork],
        runtime_gateway: ToolRuntimeGateway,
        discovery_gateway: ToolDiscoveryGateway | None = None,
        dispatch_bridge: ToolDispatchBridge | None = None,
        dispatch_service: DispatchApplicationService | None = None,
        default_max_attempts: int = 3,
        worker_lease_seconds: int = 30,
        worker_heartbeat_seconds: float = 5.0,
    ) -> None:
        self.uow_factory = uow_factory
        self.runtime_gateway = runtime_gateway
        self.discovery_gateway = discovery_gateway
        self.dispatch_bridge = dispatch_bridge or ToolDispatchBridge()
        self.dispatch_service = dispatch_service
        self.default_max_attempts = default_max_attempts
        self.worker_lease_seconds = worker_lease_seconds
        self.worker_heartbeat_seconds = worker_heartbeat_seconds

    def register(self, data: RegisterToolInput) -> Tool:
        with self.uow_factory() as uow:
            if uow.tools.get(data.id) is not None:
                raise ToolAlreadyExistsError(f"Tool '{data.id}' already exists.")

            tool = self._build_tool(data)
            tool.record_event(
                DomainEvent(
                    name="tool.registered",
                    payload={
                        "tool_id": tool.id,
                        "tool_name": tool.name,
                        "tool_kind": tool.kind.value,
                    },
                ),
            )
            uow.tools.add(tool)
            uow.collect(tool)
            uow.commit()
            return tool

    def list_discovery_providers(self) -> list[ToolDiscoveryProviderDescriptor]:
        if self.discovery_gateway is None:
            return []
        return self.discovery_gateway.list_providers()

    def discover_tools(self, *, provider_name: str | None = None) -> list[Tool]:
        if self.discovery_gateway is None:
            if provider_name is not None:
                raise ToolDiscoveryProviderNotFoundError(
                    f"Tool discovery provider '{provider_name}' is not configured.",
                )
            return []

        provider_names = {
            provider.name for provider in self.discovery_gateway.list_providers()
        }
        if provider_name is not None and provider_name not in provider_names:
            raise ToolDiscoveryProviderNotFoundError(
                f"Tool discovery provider '{provider_name}' was not found.",
            )

        discovered = self.discovery_gateway.discover(provider_name=provider_name)
        registered: list[Tool] = []

        with self.uow_factory() as uow:
            changed = False
            seen_tool_ids: set[str] = set()
            for spec in discovered:
                if spec.id in seen_tool_ids:
                    continue
                seen_tool_ids.add(spec.id)

                existing = uow.tools.get(spec.id)
                if existing is not None:
                    if self._should_refresh_discovered_tool(existing, spec):
                        refreshed = self._build_tool_from_spec(spec)
                        refreshed.record_event(
                            DomainEvent(
                                name="tool.discovered_refreshed",
                                payload={
                                    "tool_id": refreshed.id,
                                    "source_kind": refreshed.source_kind.value,
                                    "provider_name": spec.provider_name,
                                },
                            ),
                        )
                        uow.tools.add(refreshed)
                        uow.collect(refreshed)
                        registered.append(refreshed)
                        changed = True
                    else:
                        registered.append(existing)
                    continue

                tool = self._build_tool_from_spec(spec)
                tool.record_event(
                    DomainEvent(
                        name="tool.discovered",
                        payload={
                            "tool_id": tool.id,
                            "source_kind": tool.source_kind.value,
                            "provider_name": spec.provider_name,
                        },
                    ),
                )
                uow.tools.add(tool)
                uow.collect(tool)
                registered.append(tool)
                changed = True

            if changed:
                uow.commit()

        return registered

    def discover_local_tools(self) -> list[Tool]:
        return self.discover_tools(provider_name="local_builtin")

    def set_availability(self, data: SetToolAvailabilityInput) -> Tool:
        with self.uow_factory() as uow:
            tool = uow.tools.get(data.id)
        if tool is None:
            self.ensure_local_system_tools_registered()
            with self.uow_factory() as uow:
                tool = uow.tools.get(data.id)
                if tool is None:
                    raise ToolNotFoundError(f"Tool '{data.id}' was not found.")
                changed = tool.enable() if data.enabled else tool.disable()
                if changed:
                    uow.tools.add(tool)
                    uow.collect(tool)
                    uow.commit()
                return tool
        with self.uow_factory() as uow:
            tool = uow.tools.get(data.id)
            if tool is None:
                raise ToolNotFoundError(f"Tool '{data.id}' was not found.")
            changed = tool.enable() if data.enabled else tool.disable()
            if changed:
                uow.tools.add(tool)
                uow.collect(tool)
                uow.commit()
            return tool

    def list_tools(self) -> list[Tool]:
        with self.uow_factory() as uow:
            return uow.tools.list()

    def list_enabled_tools(self) -> list[Tool]:
        with self.uow_factory() as uow:
            return uow.tools.list_enabled()

    def ensure_local_system_tools_registered(self) -> tuple[Tool, ...]:
        managed_tools = [
            tool
            for tool in self.runtime_gateway.list_local_tools()
            if SYSTEM_MANAGED_TOOL_TAG in tool.tags
        ]
        if not managed_tools:
            return ()
        registered: list[Tool] = []
        with self.uow_factory() as uow:
            changed = False
            for tool in managed_tools:
                existing = uow.tools.get(tool.id)
                if existing is not None:
                    registered.append(existing)
                    continue
                spec = ToolSpec.from_tool(tool, provider_name="local_system")
                persisted = self._build_tool_from_spec(spec)
                persisted.record_event(
                    DomainEvent(
                        name="tool.system_registered",
                        payload={
                            "tool_id": persisted.id,
                            "source_kind": persisted.source_kind.value,
                        },
                    ),
                )
                uow.tools.add(persisted)
                uow.collect(persisted)
                registered.append(persisted)
                changed = True
            if changed:
                uow.commit()
        return tuple(registered)

    def get_tool(self, tool_id: str) -> Tool:
        with self.uow_factory() as uow:
            tool = uow.tools.get(tool_id)
        if tool is None:
            self.ensure_local_system_tools_registered()
            with self.uow_factory() as uow:
                tool = uow.tools.get(tool_id)
                if tool is None:
                    raise ToolNotFoundError(f"Tool '{tool_id}' was not found.")
                return tool
        return tool

    def get_tool_run(self, run_id: str) -> ToolRun:
        with self.uow_factory() as uow:
            run = uow.tool_runs.get(run_id)
            if run is None:
                raise ToolRunNotFoundError(f"Tool run '{run_id}' was not found.")
            return run

    def list_tool_runs(self, *, tool_id: str | None = None) -> list[ToolRun]:
        with self.uow_factory() as uow:
            if tool_id is None:
                return uow.tool_runs.list()
            return uow.tool_runs.list_for_tool(tool_id)

    def recover_abandoned_runs(self) -> list[ToolRun]:
        if self.dispatch_service is None:
            raise RuntimeError("Tool dispatch_service is not configured.")
        recovered_tasks = self.dispatch_service.recover_abandoned_tasks(
            RecoverAbandonedDispatchTasksInput(
                owner_kind="tool_run",
                reason=DISPATCH_LEASE_EXPIRED_REASON,
            ),
        )
        if not recovered_tasks:
            return []
        recovered_ids = [task.owner_id for task in recovered_tasks]
        with self.uow_factory() as uow:
            recovered_runs = []
            for run_id in recovered_ids:
                run = uow.tool_runs.get(run_id)
                if run is not None:
                    recovered_runs.append(run)
            return recovered_runs

    def claim_next_queued_run(self, *, worker_id: str) -> ToolRun | None:
        self.recover_abandoned_runs()

        with self.uow_factory() as uow:
            task = self.dispatch_bridge.claim_next_queued(
                uow.dispatch_tasks,
                uow,
                worker_id=worker_id,
                lease_seconds=self.worker_lease_seconds,
            )
            if task is None:
                return None
            run = uow.tool_runs.get(task.owner_id)
            if run is None:
                raise ToolRunNotFoundError(f"Tool run '{task.owner_id}' was not found.")
            run.dispatch(
                worker_id=worker_id,
                lease_seconds=self.worker_lease_seconds,
            )

            run.record_event(
                DomainEvent(
                    name="tool.run.dispatching",
                    payload={
                        "run_id": run.id,
                        "tool_id": run.tool_id,
                        "worker_id": worker_id,
                        "attempt_count": run.attempt_count,
                    },
                ),
            )
            uow.tool_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    def process_next_queued_run(self, *, worker_id: str) -> ToolRun | None:
        run = self.claim_next_queued_run(worker_id=worker_id)
        if run is None:
            return None
        return self.execute_background_run(run.id)

    def heartbeat_run(self, run_id: str, *, worker_id: str) -> ToolRun:
        with self.uow_factory() as uow:
            run = uow.tool_runs.get(run_id)
            if run is None:
                raise ToolRunNotFoundError(f"Tool run '{run_id}' was not found.")
            if run.is_terminal():
                return run
            if run.worker_id != worker_id:
                logger.warning(
                    "skipping heartbeat for tool run owned by another worker",
                    extra={
                        "run_id": run.id,
                        "expected_worker_id": worker_id,
                        "actual_worker_id": run.worker_id,
                    },
                )
                return run
            run.heartbeat(lease_seconds=self.worker_lease_seconds)
            self.dispatch_bridge.heartbeat(
                uow.dispatch_tasks,
                uow,
                run,
                worker_id=worker_id,
                lease_seconds=self.worker_lease_seconds,
            )
            uow.tool_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    def cancel_tool_run(self, run_id: str) -> ToolRun:
        with self.uow_factory() as uow:
            run = uow.tool_runs.get(run_id)
            if run is None:
                raise ToolRunNotFoundError(f"Tool run '{run_id}' was not found.")
            if run.is_terminal():
                return run

            if run.status in {
                ToolRunStatus.CREATED,
                ToolRunStatus.QUEUED,
                ToolRunStatus.DISPATCHING,
            }:
                run.request_cancel()
                run.cancel()
                if run.target.mode is ToolMode.BACKGROUND:
                    self.dispatch_bridge.cancel(uow.dispatch_tasks, uow, run)
            elif run.status is ToolRunStatus.RUNNING:
                run.request_cancel()

            uow.tool_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    async def execute(self, data: ExecuteToolInput) -> ToolRun:
        target = ToolExecutionTarget(
            mode=data.mode,
            strategy=data.strategy,
            environment=data.environment,
        )

        with self.uow_factory() as uow:
            tool = uow.tools.get(data.tool_id)
        if tool is None:
            self.ensure_local_system_tools_registered()
            with self.uow_factory() as uow:
                tool = uow.tools.get(data.tool_id)
                if tool is None:
                    raise ToolNotFoundError(f"Tool '{data.tool_id}' was not found.")
                if not tool.enabled:
                    raise ToolExecutionNotAllowedError(
                        f"Tool '{tool.id}' is disabled and cannot be executed.",
                    )
                if not tool.supports(target):
                    raise ToolExecutionNotSupportedError(
                        f"Tool '{tool.id}' does not support {target.mode.value}/{target.strategy.value}/{target.environment.value}.",
                    )

                run = ToolRun.create(
                    run_id=data.run_id or uuid4().hex,
                    tool_id=tool.id,
                    input_payload=dict(data.arguments),
                    target=target,
                    max_attempts=self.default_max_attempts,
                )
                if target.mode is ToolMode.BACKGROUND:
                    run.queue()
                    self.dispatch_bridge.enqueue(uow.dispatch_tasks, uow, run)
                uow.tool_runs.add(run)
                uow.collect(run)
                uow.commit()
        else:
            with self.uow_factory() as uow:
                tool = uow.tools.get(data.tool_id)
                if tool is None:
                    raise ToolNotFoundError(f"Tool '{data.tool_id}' was not found.")
                if not tool.enabled:
                    raise ToolExecutionNotAllowedError(
                        f"Tool '{tool.id}' is disabled and cannot be executed.",
                    )
                if not tool.supports(target):
                    raise ToolExecutionNotSupportedError(
                        f"Tool '{tool.id}' does not support {target.mode.value}/{target.strategy.value}/{target.environment.value}.",
                    )

                run = ToolRun.create(
                    run_id=data.run_id or uuid4().hex,
                    tool_id=tool.id,
                    input_payload=dict(data.arguments),
                    target=target,
                    max_attempts=self.default_max_attempts,
                )
                if target.mode is ToolMode.BACKGROUND:
                    run.queue()
                    self.dispatch_bridge.enqueue(uow.dispatch_tasks, uow, run)
                uow.tool_runs.add(run)
                uow.collect(run)
                uow.commit()

        if target.mode is ToolMode.INLINE:
            return await self._perform_run(run.id)

        if target.mode is ToolMode.BACKGROUND:
            return run

        return self._fail_run(
            run.id,
            "Only local async execution is implemented for inline/background modes in the current skeleton.",
        )

    def execute_background_run(self, run_id: str) -> ToolRun:
        return asyncio.run(self._perform_run(run_id))

    async def _perform_run(self, run_id: str) -> ToolRun:
        with self.uow_factory() as uow:
            run = uow.tool_runs.get(run_id)
            if run is None:
                raise ToolRunNotFoundError(f"Tool run '{run_id}' was not found.")

            if run.is_terminal():
                return run

            if run.status is ToolRunStatus.CANCEL_REQUESTED:
                run.cancel()
                uow.tool_runs.add(run)
                uow.collect(run)
                uow.commit()
                return run

            tool = uow.tools.get(run.tool_id)
            if tool is None:
                raise ToolNotFoundError(f"Tool '{run.tool_id}' was not found.")

            if run.status in {
                ToolRunStatus.CREATED,
                ToolRunStatus.QUEUED,
                ToolRunStatus.DISPATCHING,
            }:
                run.start()
            uow.tool_runs.add(run)
            uow.collect(run)
            uow.commit()
            arguments = dict(run.input_payload)
            worker_id = run.worker_id

        try:
            output = await self._execute_with_heartbeat(
                tool,
                arguments,
                run_id=run.id,
                target=run.target,
                worker_id=worker_id,
            )
        except Exception as exc:
            return self._fail_run(run_id, str(exc))

        with self.uow_factory() as uow:
            succeeded_run = uow.tool_runs.get(run_id)
            if succeeded_run is None:
                raise ToolRunNotFoundError(
                    f"Tool run '{run_id}' was not found after execution success.",
                )
            if succeeded_run.status is ToolRunStatus.CANCEL_REQUESTED:
                succeeded_run.cancel()
                self.dispatch_bridge.cancel(uow.dispatch_tasks, uow, succeeded_run)
            else:
                succeeded_run.succeed(output)
                self.dispatch_bridge.complete(uow.dispatch_tasks, uow, succeeded_run)
            uow.tool_runs.add(succeeded_run)
            uow.collect(succeeded_run)
            uow.commit()
            return succeeded_run

    async def _execute_with_heartbeat(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        *,
        run_id: str,
        target: ToolExecutionTarget,
        worker_id: str | None,
    ) -> Any:
        if target.mode is not ToolMode.BACKGROUND or worker_id is None:
            return await self.runtime_gateway.execute(tool, target, arguments)
        with self._heartbeat_while_processing(run_id=run_id, worker_id=worker_id):
            return await self.runtime_gateway.execute(tool, target, arguments)

    @contextmanager
    def _heartbeat_while_processing(
        self,
        *,
        run_id: str,
        worker_id: str,
    ) -> Any:
        if self.worker_heartbeat_seconds <= 0:
            yield
            return
        stop_event = threading.Event()

        def _run_heartbeat_loop() -> None:
            while not stop_event.wait(self.worker_heartbeat_seconds):
                try:
                    run = self.heartbeat_run(run_id, worker_id=worker_id)
                except Exception:
                    logger.exception(
                        "failed to heartbeat tool run while processing",
                        extra={"run_id": run_id, "worker_id": worker_id},
                    )
                    return
                if run.status not in {
                    ToolRunStatus.DISPATCHING,
                    ToolRunStatus.RUNNING,
                    ToolRunStatus.CANCEL_REQUESTED,
                }:
                    return

        heartbeat_thread = threading.Thread(
            target=_run_heartbeat_loop,
            name=f"tool-heartbeat-{run_id[:8]}",
            daemon=True,
        )
        heartbeat_thread.start()
        try:
            yield
        finally:
            stop_event.set()
            heartbeat_thread.join(timeout=max(self.worker_heartbeat_seconds * 2, 0.2))

    def handle_recovered_dispatch_task(
        self,
        *,
        tool_run_id: str,
        reason: str,
    ) -> ToolRun | None:
        with self.uow_factory() as uow:
            run = uow.tool_runs.get(tool_run_id)
            if run is None:
                return None
            if run.is_terminal() or run.status is ToolRunStatus.QUEUED:
                return run
            if run.status is ToolRunStatus.CANCEL_REQUESTED:
                run.cancel()
                self.dispatch_bridge.cancel(uow.dispatch_tasks, uow, run)
            elif run.can_retry():
                run.requeue(reason)
            else:
                run.fail(self._retry_exhausted_reason(reason))
                self.dispatch_bridge.fail(uow.dispatch_tasks, uow, run)
            uow.tool_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    def _fail_run(self, run_id: str, message: str) -> ToolRun:
        with self.uow_factory() as uow:
            failed_run = uow.tool_runs.get(run_id)
            if failed_run is None:
                raise ToolRunNotFoundError(
                    f"Tool run '{run_id}' was not found after execution failure.",
                )
            if failed_run.status is ToolRunStatus.CANCEL_REQUESTED:
                failed_run.cancel()
                self.dispatch_bridge.cancel(uow.dispatch_tasks, uow, failed_run)
            elif (
                failed_run.target.mode is ToolMode.BACKGROUND
                and failed_run.can_retry()
            ):
                failed_run.requeue(message)
                self.dispatch_bridge.requeue(
                    uow.dispatch_tasks,
                    uow,
                    failed_run,
                    reason=message,
                )
            else:
                failed_run.fail(message)
                if failed_run.target.mode is ToolMode.BACKGROUND:
                    self.dispatch_bridge.fail(uow.dispatch_tasks, uow, failed_run)
            uow.tool_runs.add(failed_run)
            uow.collect(failed_run)
            uow.commit()
            return failed_run

    def _build_tool(self, data: RegisterToolInput) -> Tool:
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

    def _build_tool_from_spec(self, spec: ToolSpec) -> Tool:
        return Tool(
            id=spec.id,
            name=spec.name,
            description=spec.description,
            kind=spec.kind,
            parameters=spec.parameters,
            tags=spec.tags,
            required_effect_ids=spec.required_effect_ids,
            execution_policy=spec.execution_policy,
            execution_support=spec.execution_support,
            source_kind=spec.source_kind,
            runtime_key=spec.runtime_key,
            enabled=spec.enabled,
        )

    @staticmethod
    def _should_refresh_discovered_tool(existing: Tool, spec: ToolSpec) -> bool:
        if existing.source_kind is not spec.source_kind:
            return False
        if existing.source_kind is ToolSourceKind.MANUAL:
            return False
        return (
            existing.name != spec.name
            or existing.description != spec.description
            or existing.kind is not spec.kind
            or existing.parameters != spec.parameters
            or existing.tags != spec.tags
            or existing.required_effect_ids != spec.required_effect_ids
            or existing.execution_policy != spec.execution_policy
            or existing.execution_support != spec.execution_support
            or existing.runtime_key != spec.runtime_key
            or existing.enabled != spec.enabled
        )

    @staticmethod
    def _retry_exhausted_reason(reason: str) -> str:
        normalized = reason.strip()
        if normalized == DISPATCH_LEASE_EXPIRED_REASON:
            return DISPATCH_LEASE_EXHAUSTED_REASON
        return f"{normalized} (retry budget exhausted)"
