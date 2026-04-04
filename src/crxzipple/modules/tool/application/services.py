from __future__ import annotations

import asyncio
import base64
import binascii
from contextlib import contextmanager
from dataclasses import dataclass, field
import json
import threading
from typing import Any, Callable, Protocol
from uuid import uuid4

from crxzipple.core.logger import get_logger
from crxzipple.modules.artifacts.application.services import ArtifactApplicationService
from crxzipple.modules.tool.application.discovery import (
    ToolDiscoveryGateway,
    ToolDiscoveryProviderDescriptor,
)
from crxzipple.modules.tool.application.ports import ToolRunDispatchPort
from crxzipple.modules.tool.application.specifications import ToolSpec
from crxzipple.modules.tool.domain.entities import Tool, ToolRun
from crxzipple.modules.tool.domain.exceptions import (
    ToolAlreadyExistsError,
    ToolDiscoveryProviderNotFoundError,
    ToolExecutionNotAllowedError,
    ToolExecutionNotSupportedError,
    ToolNotFoundError,
    ToolRunNotFoundError,
    ToolValidationError,
)
from crxzipple.modules.tool.domain.repositories import ToolRunRepository
from crxzipple.modules.tool.domain.value_objects import (
    ToolEnvironment,
    ToolExecutionContext,
    ToolExecutionPolicy,
    ToolRunResult,
    ToolExecutionStrategy,
    ToolExecutionSupport,
    ToolExecutionTarget,
    ToolKind,
    ToolMode,
    ToolParameter,
    ToolRunStatus,
    ToolSourceKind,
)
from crxzipple.shared.content_blocks import (
    FILE_BLOCK_TYPE,
    IMAGE_BLOCK_TYPE,
    file_ref_content_block,
    image_ref_content_block,
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
    execution_context: ToolExecutionContext | None = None


class ToolUnitOfWork(Protocol):
    dispatch_tasks: DispatchTaskRepository
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
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        ...

class ToolApplicationService:
    DEFAULT_DETAILS_MAX_CHARS = 131_072

    def __init__(
        self,
        uow_factory: Callable[[], ToolUnitOfWork],
        runtime_gateway: ToolRuntimeGateway,
        discovery_gateway: ToolDiscoveryGateway | None = None,
        dispatch_port: ToolRunDispatchPort | None = None,
        artifact_service: ArtifactApplicationService | None = None,
        default_max_attempts: int = 3,
        worker_lease_seconds: int = 30,
        worker_heartbeat_seconds: float = 5.0,
        details_max_chars: int = DEFAULT_DETAILS_MAX_CHARS,
    ) -> None:
        self.uow_factory = uow_factory
        self.runtime_gateway = runtime_gateway
        self.discovery_gateway = discovery_gateway
        if dispatch_port is None:
            raise RuntimeError("Tool dispatch port is not configured.")
        self.dispatch_port = dispatch_port
        self.artifact_service = artifact_service
        self.default_max_attempts = default_max_attempts
        self.worker_lease_seconds = worker_lease_seconds
        self.worker_heartbeat_seconds = worker_heartbeat_seconds
        self.details_max_chars = max(int(details_max_chars), 1)
        self._manual_tools: dict[str, Tool] = {}

    def register(self, data: RegisterToolInput) -> Tool:
        if data.id in self._manual_tools:
            raise ToolAlreadyExistsError(
                f"Tool '{data.id}' already exists.",
            )
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
        self._manual_tools[tool.id] = tool
        with self.uow_factory() as uow:
            uow.collect(tool)
            uow.commit()
        return tool

    def list_discovery_providers(self) -> list[ToolDiscoveryProviderDescriptor]:
        if self.discovery_gateway is None:
            return []
        return self.discovery_gateway.list_providers()

    def discover_tools(self, *, provider_name: str | None = None) -> list[Tool]:
        specs = self._discover_specs(provider_name=provider_name)
        runtime_tools = self._runtime_local_tool_map()
        discovered: dict[str, Tool] = {}
        for spec in specs:
            discovered.setdefault(
                spec.id,
                runtime_tools.get(spec.id) or self._build_tool_from_spec(spec),
            )
        return [discovered[tool_id] for tool_id in sorted(discovered)]

    def discover_local_tools(self) -> list[Tool]:
        if self.discovery_gateway is None:
            return []
        discovered: dict[str, Tool] = {}
        for provider in self.discovery_gateway.list_providers():
            if provider.source_kind is not ToolSourceKind.LOCAL_DISCOVERY:
                continue
            for tool in self.discover_tools(provider_name=provider.name):
                discovered.setdefault(tool.id, tool)
        return [discovered[tool_id] for tool_id in sorted(discovered)]

    def set_availability(self, data: SetToolAvailabilityInput) -> Tool:
        if self._runtime_system_tool(data.id) is not None:
            raise ToolValidationError(
                f"Tool '{data.id}' is file-backed and cannot be enabled or disabled through the service.",
            )
        tool = self._manual_tools.get(data.id)
        if tool is None:
            raise ToolValidationError(
                f"Tool '{data.id}' is not a process-local manual tool. File-backed tools should be changed at the source manifest/provider.",
            )
        with self.uow_factory() as uow:
            changed = tool.enable() if data.enabled else tool.disable()
            if changed:
                uow.collect(tool)
                uow.commit()
            return tool

    def list_tools(self) -> list[Tool]:
        resolved = self._resolved_tool_map()
        return [resolved[tool_id] for tool_id in sorted(resolved)]

    def list_enabled_tools(self) -> list[Tool]:
        resolved = self._resolved_tool_map()
        return [
            resolved[tool_id]
            for tool_id in sorted(resolved)
            if resolved[tool_id].enabled
        ]

    def ensure_local_system_tools_registered(self) -> tuple[Tool, ...]:
        return tuple(self._runtime_system_tool_map().values())

    def get_tool(self, tool_id: str) -> Tool:
        tool = self._resolve_tool(tool_id)
        if tool is None:
            raise ToolNotFoundError(f"Tool '{tool_id}' was not found.")
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
        recovered_ids = self.dispatch_port.recover_abandoned_run_ids(
            reason=DISPATCH_LEASE_EXPIRED_REASON,
        )
        if not recovered_ids:
            return []
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
            claim = self.dispatch_port.claim_next_queued(
                uow.dispatch_tasks,
                uow,
                worker_id=worker_id,
                lease_seconds=self.worker_lease_seconds,
            )
            if claim is None:
                return None
            run = uow.tool_runs.get(claim.run_id)
            if run is None:
                raise ToolRunNotFoundError(f"Tool run '{claim.run_id}' was not found.")
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
            self.dispatch_port.heartbeat(
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
                    self.dispatch_port.cancel(uow.dispatch_tasks, uow, run)
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
        tool = self.get_tool(data.tool_id)
        if not tool.enabled:
            raise ToolExecutionNotAllowedError(
                f"Tool '{tool.id}' is disabled and cannot be executed.",
            )
        if not tool.supports(target):
            raise ToolExecutionNotSupportedError(
                f"Tool '{tool.id}' does not support {target.mode.value}/{target.strategy.value}/{target.environment.value}.",
            )
        with self.uow_factory() as uow:
            run = ToolRun.create(
                run_id=data.run_id or uuid4().hex,
                tool_id=tool.id,
                input_payload=dict(data.arguments),
                invocation_context_payload=(
                    data.execution_context.to_payload()
                    if data.execution_context is not None
                    else None
                ),
                target=target,
                max_attempts=self.default_max_attempts,
            )
            if target.mode is ToolMode.BACKGROUND:
                run.queue()
                self.dispatch_port.enqueue(uow.dispatch_tasks, uow, run)
            uow.tool_runs.add(run)
            uow.collect(run)
            uow.commit()

        if target.mode is ToolMode.INLINE:
            return await self._perform_run(
                run.id,
                execution_context=data.execution_context,
            )

        if target.mode is ToolMode.BACKGROUND:
            return run

        return self._fail_run(
            run.id,
            "Only local async execution is implemented for inline/background modes in the current skeleton.",
        )

    def execute_background_run(self, run_id: str) -> ToolRun:
        return asyncio.run(self._perform_run(run_id))

    async def _perform_run(
        self,
        run_id: str,
        *,
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRun:
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

            tool = self._resolve_tool(run.tool_id)
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
            resolved_execution_context = (
                execution_context
                if execution_context is not None
                else run.invocation_context
            )

        try:
            output = await self._execute_with_heartbeat(
                tool,
                arguments,
                run_id=run.id,
                target=run.target,
                worker_id=worker_id,
                execution_context=resolved_execution_context,
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
                self.dispatch_port.cancel(uow.dispatch_tasks, uow, succeeded_run)
            else:
                succeeded_run.succeed(output)
                self.dispatch_port.complete(uow.dispatch_tasks, uow, succeeded_run)
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
        execution_context: ToolExecutionContext | None,
    ) -> ToolRunResult:
        if target.mode is not ToolMode.BACKGROUND or worker_id is None:
            result = await self.runtime_gateway.execute(
                tool,
                target,
                arguments,
                execution_context=execution_context,
            )
        else:
            with self._heartbeat_while_processing(run_id=run_id, worker_id=worker_id):
                result = await self.runtime_gateway.execute(
                    tool,
                    target,
                    arguments,
                    execution_context=execution_context,
                )
        if not isinstance(result, ToolRunResult):
            raise ToolValidationError(
                f"Tool runtime '{tool.resolved_runtime_key()}' must return ToolRunResult.",
            )
        result = self._externalize_inline_attachments(result)
        self._validate_result_details(result)
        return result

    def _externalize_inline_attachments(
        self,
        result: ToolRunResult,
    ) -> ToolRunResult:
        if self.artifact_service is None or not result.blocks:
            return result
        transformed_blocks: list[dict[str, Any]] = []
        changed = False
        for block in result.blocks:
            block_type = str(block.get("type") or "").strip()
            if block_type == IMAGE_BLOCK_TYPE:
                transformed_blocks.append(self._externalize_image_block(block))
                changed = True
                continue
            if block_type == FILE_BLOCK_TYPE:
                transformed_blocks.append(self._externalize_file_block(block))
                changed = True
                continue
            transformed_blocks.append(dict(block))
        if not changed:
            return result
        return ToolRunResult(
            content=transformed_blocks,
            details=result.details,
            metadata=result.metadata,
        )

    def _externalize_image_block(self, block: dict[str, Any]) -> dict[str, Any]:
        data = block.get("data")
        mime_type = block.get("mime_type")
        if not isinstance(data, str) or not isinstance(mime_type, str):
            return dict(block)
        decoded = _decode_tool_attachment_bytes(data)
        if decoded is None:
            return dict(block)
        name = block.get("name")
        artifact = self.artifact_service.create_artifact(
            data=decoded,
            mime_type=mime_type,
            name=name if isinstance(name, str) and name.strip() else None,
            metadata={"source": "tool.inline_image"},
        )
        return image_ref_content_block(
            artifact_id=artifact.id,
            mime_type=artifact.mime_type,
            name=artifact.name,
        )

    def _externalize_file_block(self, block: dict[str, Any]) -> dict[str, Any]:
        data = block.get("data")
        mime_type = block.get("mime_type")
        if not isinstance(data, str) or not isinstance(mime_type, str):
            return dict(block)
        decoded = _decode_tool_attachment_bytes(data)
        if decoded is None:
            return dict(block)
        name = block.get("name")
        artifact = self.artifact_service.create_artifact(
            data=decoded,
            mime_type=mime_type,
            name=name if isinstance(name, str) and name.strip() else None,
            metadata={"source": "tool.inline_file"},
        )
        return file_ref_content_block(
            artifact_id=artifact.id,
            mime_type=artifact.mime_type,
            name=artifact.name,
        )

    def _validate_result_details(self, result: ToolRunResult) -> None:
        if result.details is None:
            return
        try:
            serialized = json.dumps(
                result.details,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        except TypeError as exc:
            raise ToolValidationError(
                "Tool run result details must be JSON-serializable.",
            ) from exc
        if len(serialized) > self.details_max_chars:
            raise ToolValidationError(
                "Tool run result details exceed the allowed size budget "
                f"({self.details_max_chars} chars).",
            )

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
                self.dispatch_port.cancel(uow.dispatch_tasks, uow, run)
            elif run.can_retry():
                run.requeue(reason)
            else:
                run.fail(self._retry_exhausted_reason(reason))
                self.dispatch_port.fail(uow.dispatch_tasks, uow, run)
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
                self.dispatch_port.cancel(uow.dispatch_tasks, uow, failed_run)
            elif (
                failed_run.target.mode is ToolMode.BACKGROUND
                and failed_run.can_retry()
            ):
                failed_run.requeue(message)
                self.dispatch_port.requeue(
                    uow.dispatch_tasks,
                    uow,
                    failed_run,
                    reason=message,
                )
            else:
                failed_run.fail(message)
                if failed_run.target.mode is ToolMode.BACKGROUND:
                    self.dispatch_port.fail(uow.dispatch_tasks, uow, failed_run)
            uow.tool_runs.add(failed_run)
            uow.collect(failed_run)
            uow.commit()
            return failed_run

    def _runtime_system_tool_map(self) -> dict[str, Tool]:
        return {
            tool.id: tool
            for tool in self.runtime_gateway.list_local_tools()
            if SYSTEM_MANAGED_TOOL_TAG in tool.tags
        }

    def _runtime_local_tool_map(self) -> dict[str, Tool]:
        self._refresh_local_extension_discovery()
        return {
            tool.id: tool
            for tool in self.runtime_gateway.list_local_tools()
        }

    def _runtime_system_tool(self, tool_id: str) -> Tool | None:
        return self._runtime_system_tool_map().get(tool_id)

    def _resolved_tool_map(self) -> dict[str, Tool]:
        runtime_tools = self._runtime_local_tool_map()
        resolved: dict[str, Tool] = dict(runtime_tools)
        for spec in self._discover_specs(provider_name=None):
            resolved.setdefault(spec.id, runtime_tools.get(spec.id) or self._build_tool_from_spec(spec))
        for tool_id, tool in self._manual_tools.items():
            resolved[tool_id] = tool
        return resolved

    def _resolve_tool(self, tool_id: str) -> Tool | None:
        manual_tool = self._manual_tools.get(tool_id)
        if manual_tool is not None:
            return manual_tool
        runtime_tool = self._runtime_local_tool_map().get(tool_id)
        if runtime_tool is not None:
            return runtime_tool
        for spec in self._discover_specs(provider_name=None):
            if spec.id == tool_id:
                return self._build_tool_from_spec(spec)
        return None

    def _discover_specs(
        self,
        *,
        provider_name: str | None,
    ) -> list[ToolSpec]:
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
        return self.discovery_gateway.discover(provider_name=provider_name)

    def _refresh_local_extension_discovery(self) -> None:
        if self.discovery_gateway is None:
            return
        provider_names = {
            provider.name for provider in self.discovery_gateway.list_providers()
        }
        if "local_filesystem" in provider_names:
            self.discovery_gateway.discover(provider_name="local_filesystem")

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


def _decode_tool_attachment_bytes(data: str) -> bytes | None:
    try:
        return base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        return None
