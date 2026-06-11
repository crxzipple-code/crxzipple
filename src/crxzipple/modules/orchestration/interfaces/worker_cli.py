from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from contextlib import contextmanager
import os
import re
import signal
import socket
import threading
from threading import Event as StopEvent
import time
from typing import ContextManager, Iterator
from uuid import uuid4

import typer

from crxzipple.core.config import load_settings
from crxzipple.core.logger import configure_logging
from crxzipple.interfaces.cli.crxzipple import guard_runtime_database
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.interfaces.runtime_container import (
    AppContainer,
    AppKey,
    AssemblyTarget,
    runtime_container as managed_runtime_container,
)
from crxzipple.modules.agent.application import RegisterAgentProfileInput
from crxzipple.modules.agent.domain import AgentLlmRoutingPolicy, AgentNotFoundError
from crxzipple.modules.llm.application import (
    LlmAdapterRequest,
    LlmAdapterResponse,
    RegisterLlmProfileInput,
)
from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmCapability,
    LlmModelFamily,
    LlmProviderKind,
    LlmResult,
    ToolCallIntent,
)
from crxzipple.modules.orchestration.application import (
    RequestDueHeartbeatsInput,
    ResumeOrchestrationRunInput,
)
from crxzipple.modules.orchestration.application.ports import (
    OrchestrationExecutorControlPort,
    OrchestrationRunQueryPort,
    OrchestrationSchedulerRuntimePort,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationExecutorLeaseStatus,
    OrchestrationQueuePolicy,
    OrchestrationRunStatus,
    OrchestrationRunNotFoundError,
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.interfaces.dto import (
    OrchestrationExecutorLeaseDTO,
    OrchestrationRunDTO,
)
from crxzipple.modules.orchestration.interfaces.shared import (
    build_submit_turn_input,
    parse_json_object,
    parse_queue_policy,
    parse_run_stage,
)
from crxzipple.modules.tool.domain import (
    ToolCatalogSourceKind,
    ToolDefinitionOrigin,
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolExecutionSupport,
    ToolFunction,
    ToolFunctionRuntimeKind,
    ToolFunctionStatus,
    ToolKind,
    ToolMode,
    ToolRunResult,
    ToolSource,
)


def _resolve_worker_id(worker_id: str | None) -> str:
    if worker_id is not None and worker_id.strip():
        return worker_id.strip()
    return f"{socket.gethostname()}-{os.getpid()}-{uuid4().hex[:8]}"


def _exit_error(exc: Exception) -> None:
    typer.secho(str(exc), err=True, fg=typer.colors.RED)
    raise typer.Exit(code=1) from None


def _bad_parameter(message: str) -> typer.BadParameter:
    return typer.BadParameter(message)


def _parse_json_option(raw: str | None, *, option_name: str) -> dict[str, object]:
    return parse_json_object(
        raw,
        option_name=option_name,
        error_factory=_bad_parameter,
    )


def _parse_executor_lease_status(
    raw: str | None,
    *,
    option_name: str,
) -> OrchestrationExecutorLeaseStatus | None:
    if raw is None or not raw.strip():
        return None
    try:
        return OrchestrationExecutorLeaseStatus(raw.strip())
    except ValueError as exc:
        valid = ", ".join(item.value for item in OrchestrationExecutorLeaseStatus)
        raise _bad_parameter(f"{option_name} must be one of: {valid}.") from exc


@contextmanager
def _runtime_container(
    target: AssemblyTarget,
    *,
    enable_memory_watchers: bool | None = None,
) -> Iterator[AppContainer]:
    settings = load_settings()
    configure_logging(settings)
    with managed_runtime_container(
        settings,
        target=target,
        enable_memory_watchers=enable_memory_watchers,
    ) as container:
        yield container


def _executor_container() -> ContextManager[AppContainer]:
    return _runtime_container(AssemblyTarget.ORCHESTRATION_EXECUTOR)


def _scheduler_container() -> ContextManager[AppContainer]:
    return _runtime_container(AssemblyTarget.ORCHESTRATION_SCHEDULER)


def _admin_container() -> ContextManager[AppContainer]:
    return _runtime_container(
        AssemblyTarget.CLI_ADMIN,
        enable_memory_watchers=False,
    )


@contextmanager
def _linked_runtime_containers() -> Iterator[tuple[AppContainer, AppContainer]]:
    with (
        _runtime_container(
            AssemblyTarget.ORCHESTRATION_SCHEDULER,
            enable_memory_watchers=False,
        ) as scheduler_container,
        _runtime_container(
            AssemblyTarget.ORCHESTRATION_EXECUTOR,
            enable_memory_watchers=False,
        ) as executor_container,
    ):
        yield scheduler_container, executor_container


def _executor_port(container: AppContainer) -> OrchestrationExecutorControlPort:
    return container.require(AppKey.ORCHESTRATION_EXECUTOR_SERVICE)


def _scheduler_port(container: AppContainer) -> OrchestrationSchedulerRuntimePort:
    return container.require(AppKey.ORCHESTRATION_SCHEDULER_SERVICE)


def _run_query_port(container: AppContainer) -> OrchestrationRunQueryPort:
    return container.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE)


def _echo_run_or_idle(
    run,
    *,
    worker_id: str,
) -> None:
    if run is None:
        echo_data({"status": "idle", "worker_id": worker_id})
        return
    echo_data(OrchestrationRunDTO.from_entity(run))


def _executor_runtime_metrics_payload(
    leases,
) -> dict[str, object]:
    lease_payloads: list[dict[str, object]] = []
    total_capacity = 0
    total_inflight = 0
    capacity_executor_count = 0
    online_executor_count = 0
    for lease in leases:
        status_value = getattr(lease.status, "value", str(lease.status))
        is_expired = False
        lease_is_expired = getattr(lease, "is_expired", None)
        if callable(lease_is_expired):
            is_expired = bool(lease_is_expired())
        effective_status_value = status_value
        lease_effective_status = getattr(lease, "effective_status", None)
        if callable(lease_effective_status):
            effective_status = lease_effective_status()
            effective_status_value = getattr(
                effective_status,
                "value",
                str(effective_status),
            )
        elif is_expired:
            effective_status_value = OrchestrationExecutorLeaseStatus.OFFLINE.value
        counts_toward_capacity = (
            effective_status_value == OrchestrationExecutorLeaseStatus.ONLINE.value
        )
        if counts_toward_capacity:
            online_executor_count += 1
            capacity_executor_count += 1
            total_capacity += lease.max_inflight_assignments
            total_inflight += lease.inflight_assignment_count
        metadata = dict(lease.metadata)
        available_assignment_slots = (
            max(
                lease.max_inflight_assignments
                - lease.inflight_assignment_count,
                0,
            )
            if counts_toward_capacity
            else 0
        )
        lease_payloads.append(
            {
                "worker_id": lease.worker_id,
                "status": status_value,
                "effective_status": effective_status_value,
                "max_inflight_assignments": lease.max_inflight_assignments,
                "inflight_assignment_count": lease.inflight_assignment_count,
                "available_assignment_slots": available_assignment_slots,
                "counts_toward_capacity": counts_toward_capacity,
                "expired": is_expired,
                "runtime_state": metadata.get("runtime_state") or {},
                "runtime_metrics": metadata.get("runtime_metrics") or {},
            },
        )
    return {
        "executor_count": len(lease_payloads),
        "online_executor_count": online_executor_count,
        "capacity_executor_count": capacity_executor_count,
        "total_max_inflight_assignments": total_capacity,
        "total_inflight_assignment_count": total_inflight,
        "total_available_assignment_slots": max(total_capacity - total_inflight, 0),
        "leases": lease_payloads,
    }


def _build_app(help_text: str) -> typer.Typer:
    return typer.Typer(help=help_text, no_args_is_help=True)


def _resolve_max_concurrent_assignments(
    container: object,
    explicit_value: int | None,
) -> int:
    if explicit_value is not None:
        return max(int(explicit_value), 1)
    runtime_bootstrap_config = container.require(AppKey.RUNTIME_BOOTSTRAP_CONFIG)
    configured_value = getattr(
        runtime_bootstrap_config,
        "orchestration_executor_max_concurrent_assignments",
        4,
    )
    return max(int(configured_value), 1)


def _execute_executor_loop(
    *,
    poll_interval_seconds: float,
    max_runs: int | None,
    max_idle_cycles: int | None,
    worker_id: str | None,
    max_concurrent_assignments: int | None = None,
) -> None:
    guard_runtime_database(load_settings(), runtime_name="orchestration executor")
    resolved_worker_id = _resolve_worker_id(worker_id)
    with _executor_container() as container:
        resolved_max_concurrent_assignments = _resolve_max_concurrent_assignments(
            container,
            max_concurrent_assignments,
        )
        stop_event = StopEvent()
        previous_sigint = signal.getsignal(signal.SIGINT)
        previous_sigterm = signal.getsignal(signal.SIGTERM)

        def _request_stop(signum, frame) -> None:  # noqa: ANN001
            stop_event.set()

        signal.signal(signal.SIGINT, _request_stop)
        signal.signal(signal.SIGTERM, _request_stop)
        executor_service = _executor_port(container)
        try:
            executor_service.run_until_stopped(
                worker_id=resolved_worker_id,
                poll_interval_seconds=poll_interval_seconds,
                max_runs=max_runs,
                max_idle_cycles=max_idle_cycles,
                stop_event=stop_event,
                max_concurrent_assignments=resolved_max_concurrent_assignments,
            )
        except (OrchestrationValidationError, OrchestrationRunNotFoundError) as exc:
            _exit_error(exc)
        finally:
            try:
                executor_service.heartbeat_executor(
                    worker_id=resolved_worker_id,
                    max_inflight_assignments=resolved_max_concurrent_assignments,
                    inflight_assignment_count=0,
                    draining=True,
                    metadata={
                        "runtime_state": {
                            "worker_id": resolved_worker_id,
                            "active_run_ids": [],
                            "active_assignment_count": 0,
                            "max_concurrent_assignments": (
                                resolved_max_concurrent_assignments
                            ),
                        },
                        "runtime_metrics": executor_service.runtime_metrics_snapshot(),
                    },
                )
            finally:
                signal.signal(signal.SIGINT, previous_sigint)
                signal.signal(signal.SIGTERM, previous_sigterm)


def _execute_executor_probe(
    *,
    poll_interval_seconds: float,
    max_runs: int | None,
    max_idle_cycles: int | None,
    worker_id: str | None,
    max_concurrent_assignments: int | None = None,
) -> None:
    resolved_worker_id = _resolve_worker_id(worker_id)
    with _executor_container() as container:
        resolved_max_concurrent_assignments = _resolve_max_concurrent_assignments(
            container,
            max_concurrent_assignments,
        )
        try:
            executor_service = _executor_port(container)
            processed_runs = executor_service.run_until_stopped(
                worker_id=resolved_worker_id,
                poll_interval_seconds=poll_interval_seconds,
                max_runs=max_runs,
                max_idle_cycles=max_idle_cycles,
                max_concurrent_assignments=resolved_max_concurrent_assignments,
            )
            runtime_metrics_snapshot = getattr(
                executor_service,
                "runtime_metrics_snapshot",
                lambda: {},
            )
            echo_data(
                {
                    "worker_id": resolved_worker_id,
                    "processed_runs": processed_runs,
                    "max_concurrent_assignments": resolved_max_concurrent_assignments,
                    "runtime_metrics": runtime_metrics_snapshot(),
                },
            )
        except (OrchestrationValidationError, OrchestrationRunNotFoundError) as exc:
            _exit_error(exc)


def _benchmark_run_content(
    content: str,
    *,
    index: int,
    run_count: int,
    run_id: str,
) -> str:
    if run_count <= 1:
        return content
    return (
        f"{content}\n\n"
        f"[benchmark_run index={index + 1} total={run_count} run_id={run_id}]"
    )


_ORCHESTRATION_RUNTIME_SERVICE_KEYS = (
    "worker:orchestration-scheduler",
    "worker:orchestration",
)

_BENCHMARK_TERMINAL_STATUS_VALUES = {
    OrchestrationRunStatus.COMPLETED.value,
    OrchestrationRunStatus.FAILED.value,
    OrchestrationRunStatus.CANCELLED.value,
}
_BENCHMARK_RUN_ID_PATTERN = re.compile(
    r"\[benchmark_run[^\]]*\brun_id=(?P<run_id>[^\]\s]+)",
)


def _run_status_value(run) -> str:  # noqa: ANN001
    status = getattr(run, "status", None)
    return str(getattr(status, "value", status))


def _create_benchmark_runs(
    scheduler_service,  # noqa: ANN001
    *,
    agent_id: str,
    llm_id: str | None,
    content: str,
    run_count: int,
    benchmark_id: str,
    source: str,
    channel: str | None,
    chat_type: str,
    main_key: str,
    unique_lanes: bool,
    queue_policy_value: OrchestrationQueuePolicy,
    priority: int,
    max_steps: int,
) -> list[str]:
    run_ids: list[str] = []
    for index in range(run_count):
        run_id = f"{benchmark_id}-{index + 1:04d}"
        lane_main_key = f"{main_key}-{index + 1:04d}" if unique_lanes else main_key
        benchmark_metadata = {
            "benchmark_id": benchmark_id,
            "benchmark_index": index + 1,
            "benchmark_run_count": run_count,
        }
        queued = scheduler_service.submit_turn(
            build_submit_turn_input(
                source=source,
                content=_benchmark_run_content(
                    content,
                    index=index,
                    run_count=run_count,
                    run_id=run_id,
                ),
                inbound_metadata=benchmark_metadata,
                agent_id=agent_id,
                llm_id=llm_id,
                run_id=run_id,
                queue_policy=queue_policy_value,
                priority=priority,
                max_steps=max_steps,
                metadata=benchmark_metadata,
                channel=channel,
                chat_type=chat_type,
                main_key=lane_main_key,
                session_metadata=benchmark_metadata,
            ),
            inline_worker_id=f"benchmark-intake:{run_id}",
        )
        run_ids.append(queued.id)
    return run_ids


def _summarize_benchmark_runs(
    run_query,  # noqa: ANN001
    *,
    run_ids: list[str],
) -> tuple[dict[str, int], list[str]]:
    status_counts: dict[str, int] = {}
    assigned_run_ids: list[str] = []
    if run_query is None:
        return status_counts, assigned_run_ids
    for run_id in run_ids:
        run = run_query.get_run(run_id)
        status_value = _run_status_value(run)
        status_counts[status_value] = status_counts.get(status_value, 0) + 1
        worker_id_value = str(getattr(run, "worker_id", "") or "").strip()
        if worker_id_value or status_value not in {
            OrchestrationRunStatus.ACCEPTED.value,
            OrchestrationRunStatus.QUEUED.value,
        }:
            assigned_run_ids.append(run_id)
    return status_counts, assigned_run_ids


def _daemon_runtime_service_snapshots(
    container: AppContainer,
    *,
    service_keys: tuple[str, ...] = _ORCHESTRATION_RUNTIME_SERVICE_KEYS,
) -> list[dict[str, object]]:
    daemon_manager = container.require(AppKey.DAEMON_MANAGER)
    snapshots: list[dict[str, object]] = []
    for service_key in service_keys:
        instances = daemon_manager.list_instances(
            service_key=service_key,
            refresh=True,
        )
        instance_payloads = []
        ready_count = 0
        for instance in instances:
            status = str(getattr(instance, "status", "") or "")
            if status == "ready":
                ready_count += 1
            instance_payloads.append(
                {
                    "id": getattr(instance, "id", None),
                    "status": status,
                    "worker_id": getattr(instance, "worker_id", None),
                    "pid": getattr(instance, "pid", None),
                },
            )
        snapshots.append(
            {
                "service_key": service_key,
                "ready_instance_count": ready_count,
                "instances": instance_payloads,
            },
        )
    return snapshots


def _wait_for_benchmark_runs(
    run_query,  # noqa: ANN001
    *,
    run_ids: list[str],
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> tuple[dict[str, int], list[str], bool]:
    deadline = time.monotonic() + max(float(timeout_seconds), 0.0)
    status_counts: dict[str, int] = {}
    assigned_run_ids: list[str] = []
    while True:
        status_counts, assigned_run_ids = _summarize_benchmark_runs(
            run_query,
            run_ids=run_ids,
        )
        terminal_count = sum(
            count
            for status, count in status_counts.items()
            if status in _BENCHMARK_TERMINAL_STATUS_VALUES
        )
        if terminal_count >= len(run_ids):
            return status_counts, assigned_run_ids, True
        if time.monotonic() >= deadline:
            return status_counts, assigned_run_ids, False
        time.sleep(max(float(poll_interval_seconds), 0.01))


class _ToolIoBenchmarkStats:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.started_tool_calls = 0
        self.completed_tool_calls = 0
        self.active_tool_calls = 0
        self.max_active_tool_calls = 0
        self.started_llm_invocations = 0
        self.completed_llm_invocations = 0

    def record_llm_started(self) -> None:
        with self._lock:
            self.started_llm_invocations += 1

    def record_llm_completed(self) -> None:
        with self._lock:
            self.completed_llm_invocations += 1

    def record_tool_started(self) -> None:
        with self._lock:
            self.started_tool_calls += 1
            self.active_tool_calls += 1
            self.max_active_tool_calls = max(
                self.max_active_tool_calls,
                self.active_tool_calls,
            )

    def record_tool_completed(self) -> None:
        with self._lock:
            self.completed_tool_calls += 1
            self.active_tool_calls = max(self.active_tool_calls - 1, 0)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "started_tool_calls": self.started_tool_calls,
                "completed_tool_calls": self.completed_tool_calls,
                "active_tool_calls": self.active_tool_calls,
                "max_active_tool_calls": self.max_active_tool_calls,
                "started_llm_invocations": self.started_llm_invocations,
                "completed_llm_invocations": self.completed_llm_invocations,
            }


class _SyntheticToolIoLlmAdapter:
    def __init__(
        self,
        *,
        tool_name: str,
        tool_calls_per_run: int,
        tool_sleep_seconds: float,
        llm_latency_seconds: float,
        stats: _ToolIoBenchmarkStats,
    ) -> None:
        self.tool_name = tool_name
        self.tool_calls_per_run = max(tool_calls_per_run, 1)
        self.tool_sleep_seconds = max(tool_sleep_seconds, 0.0)
        self.llm_latency_seconds = max(llm_latency_seconds, 0.0)
        self.stats = stats
        self._lock = threading.Lock()
        self._sequence = 0

    def invoke(self, _profile, request: LlmAdapterRequest) -> LlmAdapterResponse:  # noqa: ANN001
        return asyncio.run(self.invoke_async(_profile, request))

    async def invoke_async(
        self,
        _profile,  # noqa: ANN001
        request: LlmAdapterRequest,
    ) -> LlmAdapterResponse:
        self.stats.record_llm_started()
        try:
            if self.llm_latency_seconds > 0:
                await asyncio.sleep(self.llm_latency_seconds)
            benchmark_run_id = self._latest_benchmark_run_id(request)
            if self._has_current_tool_result_message(request, benchmark_run_id):
                return LlmAdapterResponse(
                    result=LlmResult(
                        text="synthetic tool io benchmark complete",
                        finish_reason="stop",
                    ),
                )
            with self._lock:
                self._sequence += 1
                sequence = self._sequence
            call_prefix = f"tool-io-{benchmark_run_id or sequence}"
            return LlmAdapterResponse(
                result=LlmResult(
                    tool_calls=tuple(
                        ToolCallIntent(
                            id=f"{call_prefix}-{index + 1}",
                            name=self.tool_name,
                            arguments={
                                "call_index": index + 1,
                                "sleep_seconds": self.tool_sleep_seconds,
                            },
                        )
                        for index in range(self.tool_calls_per_run)
                    ),
                    finish_reason="tool_calls",
                ),
            )
        finally:
            self.stats.record_llm_completed()

    @staticmethod
    def _has_current_tool_result_message(
        request: LlmAdapterRequest,
        benchmark_run_id: str | None,
    ) -> bool:
        expected_prefix = (
            f"tool-io-{benchmark_run_id}-" if benchmark_run_id is not None else None
        )
        for message in request.messages:
            role = getattr(message, "role", None)
            if str(getattr(role, "value", role)) != "tool":
                continue
            if expected_prefix is None:
                return True
            tool_call_id = getattr(message, "tool_call_id", None)
            if isinstance(tool_call_id, str) and tool_call_id.startswith(
                expected_prefix,
            ):
                return True
        return False

    @staticmethod
    def _latest_benchmark_run_id(request: LlmAdapterRequest) -> str | None:
        for message in reversed(request.messages):
            role = getattr(message, "role", None)
            if str(getattr(role, "value", role)) != "user":
                continue
            match = _BENCHMARK_RUN_ID_PATTERN.search(
                _SyntheticToolIoLlmAdapter._content_text(
                    getattr(message, "content", ""),
                ),
            )
            if match is not None:
                return match.group("run_id")
        return None

    @staticmethod
    def _content_text(content: object) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, dict):
            return "\n".join(
                _SyntheticToolIoLlmAdapter._content_text(value)
                for value in content.values()
            )
        if isinstance(content, (list, tuple)):
            return "\n".join(
                _SyntheticToolIoLlmAdapter._content_text(item)
                for item in content
            )
        return str(content)


def _ensure_benchmark_agent(
    container: AppContainer,
    *,
    agent_id: str,
    llm_id: str,
) -> None:
    agent_service = container.require(AppKey.AGENT_SERVICE)
    try:
        agent_service.get_profile(agent_id)
        return
    except AgentNotFoundError:
        pass
    agent_service.register_profile(
        RegisterAgentProfileInput(
            id=agent_id,
            name=f"Benchmark Tool IO {agent_id}",
            llm_routing_policy=AgentLlmRoutingPolicy(default_llm_id=llm_id),
        ),
    )


def _register_tool_io_benchmark_runtime(
    container: AppContainer,
    *,
    benchmark_id: str,
    agent_id: str,
    tool_calls_per_run: int,
    tool_sleep_seconds: float,
    llm_latency_seconds: float,
) -> tuple[str, str, _ToolIoBenchmarkStats]:
    stats = _ToolIoBenchmarkStats()
    synthetic_llm_id = f"benchmark.tool_io.{uuid4().hex[:12]}"
    synthetic_tool_id = f"benchmark_tool_io_sleep_{uuid4().hex[:12]}"
    adapter = _SyntheticToolIoLlmAdapter(
        tool_name=synthetic_tool_id,
        tool_calls_per_run=tool_calls_per_run,
        tool_sleep_seconds=tool_sleep_seconds,
        llm_latency_seconds=llm_latency_seconds,
        stats=stats,
    )
    container.require(AppKey.LLM_ADAPTER_REGISTRY).register(
        LlmApiFamily.OLLAMA_NATIVE,
        adapter,
    )
    container.require(AppKey.LLM_SERVICE).register_profile(
        RegisterLlmProfileInput(
            id=synthetic_llm_id,
            provider=LlmProviderKind.OLLAMA,
            api_family=LlmApiFamily.OLLAMA_NATIVE,
            model_name="synthetic-tool-io",
            model_family=LlmModelFamily.GENERAL,
            capabilities=(LlmCapability.TOOL_CALLING,),
            timeout_seconds=30,
        ),
    )
    source_id = f"benchmark.tool_io.{uuid4().hex[:12]}"
    with container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
        source = ToolSource(
            id=source_id,
            display_name="Synthetic Tool IO Benchmark",
            kind=ToolCatalogSourceKind.LOCAL_PACKAGE,
            description="Temporary benchmark source for orchestration tool IO tests.",
            config={"namespace": "benchmark.tool_io"},
        )
        function = ToolFunction(
            id=synthetic_tool_id,
            source_id=source_id,
            stable_key=f"{source_id}.{synthetic_tool_id}",
            name=synthetic_tool_id,
            display_name="Synthetic Tool IO Sleep",
            description="Sleeps asynchronously to benchmark inline tool IO concurrency.",
            input_schema={
                "type": "object",
                "properties": {
                    "call_index": {"type": "integer"},
                    "sleep_seconds": {"type": "number"},
                },
            },
            runtime_kind=ToolFunctionRuntimeKind.LOCAL,
            handler_ref={"ref": synthetic_tool_id},
            required_effect_ids=("local_tool_access",),
            execution_support=ToolExecutionSupport(
                supported_modes=(ToolMode.INLINE,),
                supported_strategies=(ToolExecutionStrategy.ASYNC,),
                supported_environments=(ToolEnvironment.LOCAL,),
            ),
            metadata={
                "tool_kind": ToolKind.FUNCTION.value,
                "definition_origin": ToolDefinitionOrigin.LOCAL_DISCOVERY.value,
                "runtime_key": synthetic_tool_id,
                "execution_support": {
                    "supported_modes": (ToolMode.INLINE.value,),
                    "supported_strategies": (ToolExecutionStrategy.ASYNC.value,),
                    "supported_environments": (ToolEnvironment.LOCAL.value,),
                },
            },
            status=ToolFunctionStatus.ACTIVE,
        )
        uow.tool_sources.upsert(source)
        uow.tool_functions.upsert(function)
        uow.commit()
    tool = container.require(AppKey.TOOL_SERVICE).get_tool(
        synthetic_tool_id,
    )

    async def _sleep_tool(arguments: dict[str, object]) -> ToolRunResult:
        stats.record_tool_started()
        started_at = time.perf_counter()
        try:
            sleep_seconds = float(arguments.get("sleep_seconds") or tool_sleep_seconds)
            await asyncio.sleep(max(sleep_seconds, 0.0))
            elapsed_seconds = time.perf_counter() - started_at
            return ToolRunResult.text(
                "synthetic tool io slept",
                details={
                    "call_index": arguments.get("call_index"),
                    "sleep_seconds": sleep_seconds,
                    "elapsed_seconds": round(elapsed_seconds, 6),
                },
            )
        finally:
            stats.record_tool_completed()

    container.require(AppKey.TOOL_LOCAL_RUNTIME_REGISTRY).register(tool, _sleep_tool)
    _ensure_benchmark_agent(container, agent_id=agent_id, llm_id=synthetic_llm_id)
    return synthetic_llm_id, synthetic_tool_id, stats


def _execute_tool_io_benchmark(
    *,
    agent_id: str,
    run_count: int,
    tool_calls_per_run: int,
    tool_sleep_seconds: float,
    llm_latency_seconds: float,
    run_id_prefix: str | None,
    source: str,
    channel: str | None,
    chat_type: str,
    main_key: str,
    unique_lanes: bool,
    queue_policy: str | None,
    priority: int,
    max_steps: int,
    worker_id: str | None,
    scheduler_worker_id: str | None,
    max_concurrent_assignments: int,
    poll_interval_seconds: float,
    scheduler_poll_interval_seconds: float,
    max_idle_cycles: int | None,
    allow_shared_executors: bool,
) -> None:
    resolved_worker_id = _resolve_worker_id(worker_id)
    resolved_scheduler_worker_id = _resolve_worker_id(scheduler_worker_id)
    benchmark_id = (
        run_id_prefix.strip()
        if run_id_prefix is not None and run_id_prefix.strip()
        else f"tool-io-bench-{uuid4().hex[:8]}"
    )
    queue_policy_value = parse_queue_policy(
        queue_policy,
        option_name="--queue-policy",
        error_factory=_bad_parameter,
    ) or OrchestrationQueuePolicy.FIFO
    effective_max_concurrent_assignments = (
        max_concurrent_assignments if unique_lanes else 1
    )

    with _linked_runtime_containers() as (scheduler_container, executor_container):
        try:
            scheduler_service = _scheduler_port(scheduler_container)
            executor_service = _executor_port(executor_container)
            run_query = _run_query_port(executor_container)
            list_runs = getattr(run_query, "list_runs", None)
            if not allow_shared_executors and callable(list_runs):
                queued_runs = list_runs(status=OrchestrationRunStatus.QUEUED)
                queued_run_ids = [str(run.id) for run in queued_runs]
                if queued_run_ids:
                    preview = ", ".join(queued_run_ids[:5])
                    suffix = "" if len(queued_run_ids) <= 5 else ", ..."
                    raise OrchestrationValidationError(
                        "Tool IO benchmark found existing queued orchestration "
                        f"runs before creating benchmark runs: {preview}{suffix}. "
                        "Clear the queue before running an isolated benchmark.",
                    )
            other_online_executor_ids: list[str] = []
            list_executor_leases = getattr(
                executor_service,
                "list_executor_leases",
                None,
            )
            if callable(list_executor_leases):
                for lease in list_executor_leases(
                    status=OrchestrationExecutorLeaseStatus.ONLINE,
                ):
                    if lease.worker_id == resolved_worker_id:
                        continue
                    is_expired = getattr(lease, "is_expired", None)
                    if callable(is_expired) and is_expired():
                        continue
                    other_online_executor_ids.append(lease.worker_id)
            if other_online_executor_ids and not allow_shared_executors:
                raise OrchestrationValidationError(
                    "Tool IO benchmark requires an exclusive executor lease by "
                    "default because the synthetic LLM/tool runtime is local to "
                    "this process. Stop other orchestration executors or drain "
                    "them before running this benchmark.",
                )

            synthetic_llm_id, synthetic_tool_id, stats = (
                _register_tool_io_benchmark_runtime(
                    executor_container,
                    benchmark_id=benchmark_id,
                    agent_id=agent_id,
                    tool_calls_per_run=tool_calls_per_run,
                    tool_sleep_seconds=tool_sleep_seconds,
                    llm_latency_seconds=llm_latency_seconds,
                )
            )
            executor_service.heartbeat_executor(
                worker_id=resolved_worker_id,
                max_inflight_assignments=effective_max_concurrent_assignments,
                inflight_assignment_count=0,
                metadata={
                    "benchmark_id": benchmark_id,
                    "benchmark_kind": "tool_io",
                    "runtime_state": {
                        "worker_id": resolved_worker_id,
                        "active_run_ids": [],
                        "active_assignment_count": 0,
                        "max_concurrent_assignments": max_concurrent_assignments,
                        "effective_max_concurrent_assignments": (
                            effective_max_concurrent_assignments
                        ),
                    },
                },
            )

            run_ids = _create_benchmark_runs(
                scheduler_service,
                agent_id=agent_id,
                llm_id=synthetic_llm_id,
                content=(
                    "Run the synthetic benchmark tool calls, then summarize completion."
                ),
                run_count=run_count,
                benchmark_id=benchmark_id,
                source=source,
                channel=channel,
                chat_type=chat_type,
                main_key=f"{main_key}-{benchmark_id}",
                unique_lanes=unique_lanes,
                queue_policy_value=queue_policy_value,
                priority=priority,
                max_steps=max_steps,
            )

            started_at = time.perf_counter()
            scheduler_stop = StopEvent()
            with ThreadPoolExecutor(max_workers=2) as runtime_pool:
                scheduler_future = runtime_pool.submit(
                    scheduler_service.run_until_stopped,
                    worker_id=resolved_scheduler_worker_id,
                    poll_interval_seconds=scheduler_poll_interval_seconds,
                    max_runs=run_count,
                    max_idle_cycles=None,
                    stop_event=scheduler_stop,
                )
                executor_future = runtime_pool.submit(
                    executor_service.run_until_stopped,
                    worker_id=resolved_worker_id,
                    poll_interval_seconds=poll_interval_seconds,
                    max_runs=run_count,
                    max_idle_cycles=max_idle_cycles,
                    max_concurrent_assignments=effective_max_concurrent_assignments,
                )
                processed_runs = executor_future.result()
                try:
                    scheduler_processed_items = scheduler_future.result(
                        timeout=max(scheduler_poll_interval_seconds * 2, 0.1),
                    )
                except FuturesTimeoutError:
                    scheduler_stop.set()
                    scheduler_processed_items = scheduler_future.result()
            elapsed_seconds = time.perf_counter() - started_at

            runtime_metrics_snapshot = getattr(
                executor_service,
                "runtime_metrics_snapshot",
                lambda: {},
            )
            status_counts, assigned_run_ids = _summarize_benchmark_runs(
                run_query,
                run_ids=run_ids,
            )
            expected_tool_call_count = run_count * tool_calls_per_run
            stats_snapshot = stats.snapshot()
            completed_tool_calls = stats_snapshot["completed_tool_calls"]
            echo_data(
                {
                    "benchmark_id": benchmark_id,
                    "runtime_mode": "linked_scheduler_executor_synthetic_tool_io",
                    "created_run_count": len(run_ids),
                    "assigned_run_count": len(assigned_run_ids),
                    "scheduler_processed_items": scheduler_processed_items,
                    "processed_runs": processed_runs,
                    "elapsed_seconds": round(elapsed_seconds, 6),
                    "runs_per_second": (
                        round(processed_runs / elapsed_seconds, 6)
                        if elapsed_seconds > 0
                        else None
                    ),
                    "tool_calls_per_run": tool_calls_per_run,
                    "expected_tool_call_count": expected_tool_call_count,
                    "completed_tool_call_count": completed_tool_calls,
                    "tool_calls_per_second": (
                        round(completed_tool_calls / elapsed_seconds, 6)
                        if elapsed_seconds > 0
                        else None
                    ),
                    "max_active_tool_calls": stats_snapshot["max_active_tool_calls"],
                    "tool_sleep_seconds": tool_sleep_seconds,
                    "llm_latency_seconds": llm_latency_seconds,
                    "queue_policy": queue_policy_value.value,
                    "lane_mode": "unique" if unique_lanes else "single",
                    "synthetic": {
                        "llm_id": synthetic_llm_id,
                        "tool_id": synthetic_tool_id,
                    },
                    "executor": {
                        "worker_id": resolved_worker_id,
                        "max_concurrent_assignments": (
                            effective_max_concurrent_assignments
                        ),
                        "configured_max_concurrent_assignments": (
                            max_concurrent_assignments
                        ),
                        "poll_interval_seconds": poll_interval_seconds,
                    },
                    "scheduler": {
                        "worker_id": resolved_scheduler_worker_id,
                        "poll_interval_seconds": scheduler_poll_interval_seconds,
                    },
                    "other_online_executor_ids": other_online_executor_ids,
                    "status_counts": status_counts,
                    "run_ids": run_ids,
                    "assigned_run_ids": assigned_run_ids,
                    "stats": stats_snapshot,
                    "runtime_metrics": runtime_metrics_snapshot(),
                },
            )
        except (
            OrchestrationValidationError,
            OrchestrationRunNotFoundError,
            typer.BadParameter,
        ) as exc:
            _exit_error(exc)


def _execute_executor_runtime_benchmark(
    *,
    agent_id: str,
    llm_id: str | None,
    content: str,
    run_count: int,
    run_id_prefix: str | None,
    source: str,
    channel: str | None,
    chat_type: str,
    main_key: str,
    unique_lanes: bool,
    queue_policy: str | None,
    priority: int,
    max_steps: int,
    worker_id: str | None,
    scheduler_worker_id: str | None,
    max_concurrent_assignments: int,
    poll_interval_seconds: float,
    scheduler_poll_interval_seconds: float,
    max_idle_cycles: int | None,
    allow_shared_executors: bool,
) -> None:
    resolved_worker_id = _resolve_worker_id(worker_id)
    resolved_scheduler_worker_id = _resolve_worker_id(scheduler_worker_id)
    benchmark_id = (
        run_id_prefix.strip()
        if run_id_prefix is not None and run_id_prefix.strip()
        else f"bench-{uuid4().hex[:8]}"
    )
    queue_policy_value = parse_queue_policy(
        queue_policy,
        option_name="--queue-policy",
        error_factory=_bad_parameter,
    ) or OrchestrationQueuePolicy.FIFO

    with _linked_runtime_containers() as (scheduler_container, executor_container):
        try:
            scheduler_service = _scheduler_port(scheduler_container)
            executor_service = _executor_port(executor_container)
            run_query = _run_query_port(executor_container)
            list_runs = getattr(run_query, "list_runs", None)
            if not allow_shared_executors and callable(list_runs):
                queued_runs = list_runs(status=OrchestrationRunStatus.QUEUED)
                queued_run_ids = [str(run.id) for run in queued_runs]
                if queued_run_ids:
                    preview = ", ".join(queued_run_ids[:5])
                    suffix = "" if len(queued_run_ids) <= 5 else ", ..."
                    raise OrchestrationValidationError(
                        "Benchmark runtime found existing queued orchestration "
                        f"runs before creating benchmark runs: {preview}{suffix}. "
                        "Clear the queue or pass --allow-shared-executors to run "
                        "a non-isolated benchmark.",
                    )
            run_ids = _create_benchmark_runs(
                scheduler_service,
                agent_id=agent_id,
                llm_id=llm_id,
                content=content,
                run_count=run_count,
                benchmark_id=benchmark_id,
                source=source,
                channel=channel,
                chat_type=chat_type,
                main_key=main_key,
                unique_lanes=unique_lanes,
                queue_policy_value=queue_policy_value,
                priority=priority,
                max_steps=max_steps,
            )

            executor_service.heartbeat_executor(
                worker_id=resolved_worker_id,
                max_inflight_assignments=max_concurrent_assignments,
                inflight_assignment_count=0,
                metadata={
                    "benchmark_id": benchmark_id,
                    "runtime_state": {
                        "worker_id": resolved_worker_id,
                        "active_run_ids": [],
                        "active_assignment_count": 0,
                        "max_concurrent_assignments": max_concurrent_assignments,
                    },
                },
            )
            other_online_executor_ids: list[str] = []
            list_executor_leases = getattr(
                executor_service,
                "list_executor_leases",
                None,
            )
            if callable(list_executor_leases):
                for lease in list_executor_leases(
                    status=OrchestrationExecutorLeaseStatus.ONLINE,
                ):
                    if lease.worker_id == resolved_worker_id:
                        continue
                    is_expired = getattr(lease, "is_expired", None)
                    if callable(is_expired) and is_expired():
                        continue
                    other_online_executor_ids.append(lease.worker_id)
            if other_online_executor_ids and not allow_shared_executors:
                raise OrchestrationValidationError(
                    "Benchmark runtime requires an exclusive executor lease by "
                    "default so scheduler assignments stay repeatable. Stop other "
                    "orchestration executors or pass --allow-shared-executors.",
                )

            started_at = time.perf_counter()
            scheduler_stop = StopEvent()
            with ThreadPoolExecutor(max_workers=2) as runtime_pool:
                scheduler_future = runtime_pool.submit(
                    scheduler_service.run_until_stopped,
                    worker_id=resolved_scheduler_worker_id,
                    poll_interval_seconds=scheduler_poll_interval_seconds,
                    max_runs=run_count,
                    max_idle_cycles=None,
                    stop_event=scheduler_stop,
                )
                executor_future = runtime_pool.submit(
                    executor_service.run_until_stopped,
                    worker_id=resolved_worker_id,
                    poll_interval_seconds=poll_interval_seconds,
                    max_runs=run_count,
                    max_idle_cycles=max_idle_cycles,
                    max_concurrent_assignments=max_concurrent_assignments,
                )
                processed_runs = executor_future.result()
                try:
                    scheduler_processed_items = scheduler_future.result(
                        timeout=max(scheduler_poll_interval_seconds * 2, 0.1),
                    )
                except FuturesTimeoutError:
                    scheduler_stop.set()
                    scheduler_processed_items = scheduler_future.result()
            elapsed_seconds = time.perf_counter() - started_at

            runtime_metrics_snapshot = getattr(
                executor_service,
                "runtime_metrics_snapshot",
                lambda: {},
            )
            status_counts, assigned_run_ids = _summarize_benchmark_runs(
                run_query,
                run_ids=run_ids,
            )
            if run_query is None:
                assigned_run_ids = run_ids[:scheduler_processed_items]

            assignment_waves = (
                (scheduler_processed_items + max_concurrent_assignments - 1)
                // max_concurrent_assignments
            )

            echo_data(
                {
                    "benchmark_id": benchmark_id,
                    "created_run_count": len(run_ids),
                    "assigned_run_count": len(assigned_run_ids),
                    "assignment_waves": assignment_waves,
                    "scheduler_processed_items": scheduler_processed_items,
                    "runtime_mode": "linked_scheduler_executor",
                    "processed_runs": processed_runs,
                    "elapsed_seconds": round(elapsed_seconds, 6),
                    "runs_per_second": (
                        round(processed_runs / elapsed_seconds, 6)
                        if elapsed_seconds > 0
                        else None
                    ),
                    "queue_policy": queue_policy_value.value,
                    "lane_mode": "unique" if unique_lanes else "single",
                    "executor": {
                        "worker_id": resolved_worker_id,
                        "max_concurrent_assignments": max_concurrent_assignments,
                        "poll_interval_seconds": poll_interval_seconds,
                    },
                    "scheduler": {
                        "worker_id": resolved_scheduler_worker_id,
                        "poll_interval_seconds": scheduler_poll_interval_seconds,
                    },
                    "other_online_executor_ids": other_online_executor_ids,
                    "status_counts": status_counts,
                    "run_ids": run_ids,
                    "assigned_run_ids": assigned_run_ids,
                    "runtime_metrics": runtime_metrics_snapshot(),
                },
            )
        except (
            OrchestrationValidationError,
            OrchestrationRunNotFoundError,
            typer.BadParameter,
        ) as exc:
            _exit_error(exc)


def _execute_daemon_runtime_benchmark(
    *,
    agent_id: str,
    llm_id: str | None,
    content: str,
    run_count: int,
    run_id_prefix: str | None,
    source: str,
    channel: str | None,
    chat_type: str,
    main_key: str,
    unique_lanes: bool,
    queue_policy: str | None,
    priority: int,
    max_steps: int,
    timeout_seconds: float,
    poll_interval_seconds: float,
    require_ready_daemons: bool,
    allow_shared_runtime: bool,
) -> None:
    benchmark_id = (
        run_id_prefix.strip()
        if run_id_prefix is not None and run_id_prefix.strip()
        else f"daemon-bench-{uuid4().hex[:8]}"
    )
    queue_policy_value = parse_queue_policy(
        queue_policy,
        option_name="--queue-policy",
        error_factory=_bad_parameter,
    ) or OrchestrationQueuePolicy.FIFO

    with _admin_container() as container:
        try:
            scheduler_service = _scheduler_port(container)
            run_query = _run_query_port(container)
            if run_query is None:
                raise OrchestrationValidationError(
                    "Daemon runtime benchmark requires orchestration_run_query_service.",
                )
            list_runs = getattr(run_query, "list_runs", None)
            if not allow_shared_runtime and callable(list_runs):
                queued_runs = list_runs(status=OrchestrationRunStatus.QUEUED)
                queued_run_ids = [str(run.id) for run in queued_runs]
                if queued_run_ids:
                    preview = ", ".join(queued_run_ids[:5])
                    suffix = "" if len(queued_run_ids) <= 5 else ", ..."
                    raise OrchestrationValidationError(
                        "Daemon runtime benchmark found existing queued orchestration "
                        f"runs before creating benchmark runs: {preview}{suffix}. "
                        "Clear the queue or pass --allow-shared-runtime to run "
                        "a non-isolated benchmark.",
                    )

            daemon_services = _daemon_runtime_service_snapshots(container)
            missing_ready = [
                str(item["service_key"])
                for item in daemon_services
                if int(item["ready_instance_count"]) <= 0
            ]
            if require_ready_daemons and missing_ready:
                raise OrchestrationValidationError(
                    "Daemon runtime benchmark requires ready orchestration runtime "
                    f"services: {', '.join(missing_ready)}. Start them with "
                    "`daemon run --service-set orchestration-runtime --no-include-eager`.",
                )

            run_ids = _create_benchmark_runs(
                scheduler_service,
                agent_id=agent_id,
                llm_id=llm_id,
                content=content,
                run_count=run_count,
                benchmark_id=benchmark_id,
                source=source,
                channel=channel,
                chat_type=chat_type,
                main_key=main_key,
                unique_lanes=unique_lanes,
                queue_policy_value=queue_policy_value,
                priority=priority,
                max_steps=max_steps,
            )

            started_at = time.perf_counter()
            status_counts, assigned_run_ids, completed_before_timeout = (
                _wait_for_benchmark_runs(
                    run_query,
                    run_ids=run_ids,
                    timeout_seconds=timeout_seconds,
                    poll_interval_seconds=poll_interval_seconds,
                )
            )
            elapsed_seconds = time.perf_counter() - started_at
            processed_runs = status_counts.get(OrchestrationRunStatus.COMPLETED.value, 0)

            echo_data(
                {
                    "benchmark_id": benchmark_id,
                    "created_run_count": len(run_ids),
                    "assigned_run_count": len(assigned_run_ids),
                    "processed_runs": processed_runs,
                    "completed_before_timeout": completed_before_timeout,
                    "runtime_mode": "daemon_scheduler_executor",
                    "elapsed_seconds": round(elapsed_seconds, 6),
                    "runs_per_second": (
                        round(processed_runs / elapsed_seconds, 6)
                        if elapsed_seconds > 0
                        else None
                    ),
                    "queue_policy": queue_policy_value.value,
                    "lane_mode": "unique" if unique_lanes else "single",
                    "daemon_services": daemon_services,
                    "status_counts": status_counts,
                    "run_ids": run_ids,
                    "assigned_run_ids": assigned_run_ids,
                },
            )
        except (
            OrchestrationValidationError,
            OrchestrationRunNotFoundError,
            typer.BadParameter,
        ) as exc:
            _exit_error(exc)


def _execute_scheduler_loop(
    *,
    poll_interval_seconds: float,
    max_runs: int | None,
    max_idle_cycles: int | None,
    worker_id: str | None,
) -> None:
    guard_runtime_database(load_settings(), runtime_name="orchestration scheduler")
    resolved_worker_id = _resolve_worker_id(worker_id)
    with _scheduler_container() as container:
        try:
            scheduler_service = _scheduler_port(container)
            scheduler_service.run_until_stopped(
                worker_id=resolved_worker_id,
                poll_interval_seconds=poll_interval_seconds,
                max_runs=max_runs,
                max_idle_cycles=max_idle_cycles,
            )
        except (OrchestrationValidationError, OrchestrationRunNotFoundError) as exc:
            _exit_error(exc)


def _register_executor_commands(
    app: typer.Typer,
) -> None:
    @app.command("process-next-assigned-assignment")
    def process_next_assigned_assignment(
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Stable orchestration executor identifier.",
        ),
    ) -> None:
        resolved_worker_id = _resolve_worker_id(worker_id)
        with _executor_container() as container:
            try:
                executor_service = _executor_port(container)
                run = executor_service.process_next_assigned_assignment(
                    worker_id=resolved_worker_id,
                )
                _echo_run_or_idle(run, worker_id=resolved_worker_id)
            except (OrchestrationValidationError, OrchestrationRunNotFoundError) as exc:
                _exit_error(exc)

    @app.command("admit-assignment")
    def admit_assignment(
        run_id: str,
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Stable orchestration executor identifier.",
        ),
    ) -> None:
        resolved_worker_id = _resolve_worker_id(worker_id)
        with _executor_container() as container:
            try:
                executor_service = _executor_port(container)
                run = executor_service.admit_assignment(
                    run_id=run_id,
                    worker_id=resolved_worker_id,
                )
                echo_data(OrchestrationRunDTO.from_entity(run))
            except (OrchestrationValidationError, OrchestrationRunNotFoundError) as exc:
                _exit_error(exc)

    @app.command("process-assignment-inline")
    def process_assignment_inline(
        run_id: str,
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Stable orchestration executor identifier.",
        ),
    ) -> None:
        resolved_worker_id = _resolve_worker_id(worker_id)
        with _executor_container() as container:
            try:
                executor_service = _executor_port(container)
                run = executor_service.process_assignment_inline(
                    run_id=run_id,
                    worker_id=resolved_worker_id,
                )
                echo_data(OrchestrationRunDTO.from_entity(run))
            except (OrchestrationValidationError, OrchestrationRunNotFoundError) as exc:
                _exit_error(exc)

    @app.command("run-executor")
    def run_executor(
        poll_interval_seconds: float = typer.Option(
            0.5,
            "--poll-interval-seconds",
            min=0.05,
            help="Idle wait time between queue polls.",
        ),
        max_runs: int | None = typer.Option(
            None,
            "--max-runs",
            min=1,
            help="Optional maximum number of runs to process before exiting.",
        ),
        max_idle_cycles: int | None = typer.Option(
            None,
            "--max-idle-cycles",
            min=1,
            help="Optional maximum consecutive idle polls before exiting.",
        ),
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Stable orchestration executor identifier.",
        ),
        max_concurrent_assignments: int | None = typer.Option(
            None,
            "--max-concurrent-assignments",
            "--max-inflight-assignments",
            min=1,
            help=(
                "Maximum assigned runs this executor advances concurrently. "
                "Defaults to Settings runtime defaults."
            ),
        ),
    ) -> None:
        _execute_executor_loop(
            poll_interval_seconds=poll_interval_seconds,
            max_runs=max_runs,
            max_idle_cycles=max_idle_cycles,
            worker_id=worker_id,
            max_concurrent_assignments=max_concurrent_assignments,
        )

    @app.command("probe-runtime")
    def probe_runtime(
        poll_interval_seconds: float = typer.Option(
            0.5,
            "--poll-interval-seconds",
            min=0.05,
            help="Idle wait time between queue polls.",
        ),
        max_runs: int | None = typer.Option(
            None,
            "--max-runs",
            min=1,
            help="Optional maximum number of runs to process before exiting.",
        ),
        max_idle_cycles: int | None = typer.Option(
            1,
            "--max-idle-cycles",
            min=1,
            help="Optional maximum consecutive idle polls before exiting.",
        ),
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Stable orchestration executor identifier.",
        ),
        max_concurrent_assignments: int | None = typer.Option(
            None,
            "--max-concurrent-assignments",
            "--max-inflight-assignments",
            min=1,
            help=(
                "Maximum assigned runs this executor advances concurrently. "
                "Defaults to Settings runtime defaults."
            ),
        ),
    ) -> None:
        _execute_executor_probe(
            poll_interval_seconds=poll_interval_seconds,
            max_runs=max_runs,
            max_idle_cycles=max_idle_cycles,
            worker_id=worker_id,
            max_concurrent_assignments=max_concurrent_assignments,
        )

    @app.command("benchmark-runtime")
    def benchmark_runtime(
        agent_id: str = typer.Argument(..., help="Agent profile identifier."),
        llm_id: str = typer.Argument(..., help="LLM profile identifier."),
        content: str = typer.Argument(..., help="Prompt content for each benchmark run."),
        run_count: int = typer.Option(
            8,
            "--run-count",
            min=1,
            help="Number of orchestration runs to create and process.",
        ),
        run_id_prefix: str | None = typer.Option(
            None,
            "--run-id-prefix",
            help="Optional deterministic run id prefix.",
        ),
        source: str = typer.Option(
            "cli",
            "--source",
            help="Inbound instruction source.",
        ),
        channel: str | None = typer.Option(
            "benchmark",
            "--channel",
            help="Session route channel.",
        ),
        chat_type: str = typer.Option(
            "direct",
            "--chat-type",
            help="Session route chat type.",
        ),
        main_key: str = typer.Option(
            "benchmark",
            "--main-key",
            help="Base session main key used for benchmark lane construction.",
        ),
        unique_lanes: bool = typer.Option(
            True,
            "--unique-lanes/--same-lane",
            help="Use one session lane per run, or force all runs through one lane.",
        ),
        queue_policy: str | None = typer.Option(
            None,
            "--queue-policy",
            help="Queue policy for created runs.",
        ),
        priority: int = typer.Option(
            100,
            "--priority",
            min=0,
            help="Run priority.",
        ),
        max_steps: int = typer.Option(
            99,
            "--max-steps",
            min=1,
            help="Maximum orchestration steps per run.",
        ),
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Stable orchestration executor identifier.",
        ),
        scheduler_worker_id: str | None = typer.Option(
            None,
            "--scheduler-worker-id",
            help="Stable orchestration scheduler identifier.",
        ),
        max_concurrent_assignments: int = typer.Option(
            4,
            "--max-concurrent-assignments",
            "--max-inflight-assignments",
            min=1,
            help="Maximum assigned runs this executor advances concurrently.",
        ),
        poll_interval_seconds: float = typer.Option(
            0.05,
            "--poll-interval-seconds",
            min=0.01,
            help="Executor idle wait time between queue polls.",
        ),
        scheduler_poll_interval_seconds: float = typer.Option(
            0.05,
            "--scheduler-poll-interval-seconds",
            min=0.01,
            help="Scheduler assignment wait time between polls.",
        ),
        max_idle_cycles: int | None = typer.Option(
            20,
            "--max-idle-cycles",
            min=1,
            help="Executor idle cycle limit before exiting.",
        ),
        allow_shared_executors: bool = typer.Option(
            False,
            "--allow-shared-executors/--require-exclusive-executor",
            help="Allow scheduler assignments to be spread across online executors.",
        ),
    ) -> None:
        _execute_executor_runtime_benchmark(
            agent_id=agent_id,
            llm_id=llm_id,
            content=content,
            run_count=run_count,
            run_id_prefix=run_id_prefix,
            source=source,
            channel=channel,
            chat_type=chat_type,
            main_key=main_key,
            unique_lanes=unique_lanes,
            queue_policy=queue_policy,
            priority=priority,
            max_steps=max_steps,
            worker_id=worker_id,
            scheduler_worker_id=scheduler_worker_id,
            max_concurrent_assignments=max_concurrent_assignments,
            poll_interval_seconds=poll_interval_seconds,
            scheduler_poll_interval_seconds=scheduler_poll_interval_seconds,
            max_idle_cycles=max_idle_cycles,
            allow_shared_executors=allow_shared_executors,
        )

    @app.command("benchmark-tool-io")
    def benchmark_tool_io(
        agent_id: str = typer.Option(
            "assistant",
            "--agent-id",
            help="Agent profile identifier to use, created if missing.",
        ),
        run_count: int = typer.Option(
            4,
            "--run-count",
            min=1,
            help="Number of orchestration runs to create and process.",
        ),
        tool_calls_per_run: int = typer.Option(
            2,
            "--tool-calls-per-run",
            min=1,
            help="Synthetic inline IO tool calls emitted by each run's first LLM step.",
        ),
        tool_sleep_seconds: float = typer.Option(
            0.2,
            "--tool-sleep-seconds",
            min=0.0,
            help="Async sleep duration for each synthetic tool call.",
        ),
        llm_latency_seconds: float = typer.Option(
            0.0,
            "--llm-latency-seconds",
            min=0.0,
            help="Optional synthetic LLM latency per invocation.",
        ),
        run_id_prefix: str | None = typer.Option(
            None,
            "--run-id-prefix",
            help="Optional deterministic run id prefix.",
        ),
        source: str = typer.Option(
            "benchmark",
            "--source",
            help="Inbound instruction source.",
        ),
        channel: str | None = typer.Option(
            "benchmark",
            "--channel",
            help="Session route channel.",
        ),
        chat_type: str = typer.Option(
            "direct",
            "--chat-type",
            help="Session route chat type.",
        ),
        main_key: str = typer.Option(
            "tool-io-benchmark",
            "--main-key",
            help="Base session main key used for benchmark lane construction.",
        ),
        unique_lanes: bool = typer.Option(
            True,
            "--unique-lanes/--same-lane",
            help="Use one session lane per run, or force all runs through one lane.",
        ),
        queue_policy: str | None = typer.Option(
            None,
            "--queue-policy",
            help="Queue policy for created runs.",
        ),
        priority: int = typer.Option(
            100,
            "--priority",
            min=0,
            help="Run priority.",
        ),
        max_steps: int = typer.Option(
            8,
            "--max-steps",
            min=2,
            help="Maximum orchestration steps per run.",
        ),
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Stable orchestration executor identifier.",
        ),
        scheduler_worker_id: str | None = typer.Option(
            None,
            "--scheduler-worker-id",
            help="Stable orchestration scheduler identifier.",
        ),
        max_concurrent_assignments: int = typer.Option(
            4,
            "--max-concurrent-assignments",
            "--max-inflight-assignments",
            min=1,
            help="Maximum assigned runs this executor advances concurrently.",
        ),
        poll_interval_seconds: float = typer.Option(
            0.02,
            "--poll-interval-seconds",
            min=0.01,
            help="Executor idle wait time between queue polls.",
        ),
        scheduler_poll_interval_seconds: float = typer.Option(
            0.02,
            "--scheduler-poll-interval-seconds",
            min=0.01,
            help="Scheduler assignment wait time between polls.",
        ),
        max_idle_cycles: int | None = typer.Option(
            20,
            "--max-idle-cycles",
            min=1,
            help="Executor idle cycle limit before exiting.",
        ),
        allow_shared_executors: bool = typer.Option(
            False,
            "--allow-shared-executors/--require-exclusive-executor",
            help=(
                "Allow other online executors. Unsafe for this synthetic benchmark "
                "because the synthetic runtime exists only in this process."
            ),
        ),
    ) -> None:
        _execute_tool_io_benchmark(
            agent_id=agent_id,
            run_count=run_count,
            tool_calls_per_run=tool_calls_per_run,
            tool_sleep_seconds=tool_sleep_seconds,
            llm_latency_seconds=llm_latency_seconds,
            run_id_prefix=run_id_prefix,
            source=source,
            channel=channel,
            chat_type=chat_type,
            main_key=main_key,
            unique_lanes=unique_lanes,
            queue_policy=queue_policy,
            priority=priority,
            max_steps=max_steps,
            worker_id=worker_id,
            scheduler_worker_id=scheduler_worker_id,
            max_concurrent_assignments=max_concurrent_assignments,
            poll_interval_seconds=poll_interval_seconds,
            scheduler_poll_interval_seconds=scheduler_poll_interval_seconds,
            max_idle_cycles=max_idle_cycles,
            allow_shared_executors=allow_shared_executors,
        )

    @app.command("benchmark-daemon-runtime")
    def benchmark_daemon_runtime(
        agent_id: str = typer.Argument(..., help="Agent profile identifier."),
        llm_id: str = typer.Argument(..., help="LLM profile identifier."),
        content: str = typer.Argument(..., help="Prompt content for each benchmark run."),
        run_count: int = typer.Option(
            8,
            "--run-count",
            min=1,
            help="Number of orchestration runs to create and wait for.",
        ),
        run_id_prefix: str | None = typer.Option(
            None,
            "--run-id-prefix",
            help="Optional deterministic run id prefix.",
        ),
        source: str = typer.Option(
            "cli",
            "--source",
            help="Inbound instruction source.",
        ),
        channel: str | None = typer.Option(
            "daemon-benchmark",
            "--channel",
            help="Session route channel.",
        ),
        chat_type: str = typer.Option(
            "direct",
            "--chat-type",
            help="Session route chat type.",
        ),
        main_key: str = typer.Option(
            "daemon-benchmark",
            "--main-key",
            help="Base session main key used for benchmark lane construction.",
        ),
        unique_lanes: bool = typer.Option(
            True,
            "--unique-lanes/--same-lane",
            help="Use one session lane per run, or force all runs through one lane.",
        ),
        queue_policy: str | None = typer.Option(
            None,
            "--queue-policy",
            help="Queue policy for created runs.",
        ),
        priority: int = typer.Option(
            100,
            "--priority",
            min=0,
            help="Run priority.",
        ),
        max_steps: int = typer.Option(
            99,
            "--max-steps",
            min=1,
            help="Maximum orchestration steps per run.",
        ),
        timeout_seconds: float = typer.Option(
            120.0,
            "--timeout-seconds",
            min=0.1,
            help="Maximum time to wait for daemon-processed runs to reach terminal state.",
        ),
        poll_interval_seconds: float = typer.Option(
            0.25,
            "--poll-interval-seconds",
            min=0.01,
            help="Run status polling interval while daemon runtimes process work.",
        ),
        require_ready_daemons: bool = typer.Option(
            True,
            "--require-ready-daemons/--allow-missing-daemons",
            help="Require scheduler and executor daemon services to be ready before creating runs.",
        ),
        allow_shared_runtime: bool = typer.Option(
            False,
            "--allow-shared-runtime/--require-isolated-queue",
            help="Allow benchmark runs to share the orchestration queue with existing queued runs.",
        ),
    ) -> None:
        _execute_daemon_runtime_benchmark(
            agent_id=agent_id,
            llm_id=llm_id,
            content=content,
            run_count=run_count,
            run_id_prefix=run_id_prefix,
            source=source,
            channel=channel,
            chat_type=chat_type,
            main_key=main_key,
            unique_lanes=unique_lanes,
            queue_policy=queue_policy,
            priority=priority,
            max_steps=max_steps,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            require_ready_daemons=require_ready_daemons,
            allow_shared_runtime=allow_shared_runtime,
        )

    @app.command("heartbeat-executor")
    def heartbeat_executor(
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Stable orchestration executor identifier.",
        ),
        max_inflight_assignments: int = typer.Option(
            1,
            "--max-inflight-assignments",
            min=1,
            help="Maximum assignments this executor can advance concurrently.",
        ),
        inflight_assignment_count: int | None = typer.Option(
            None,
            "--inflight-assignment-count",
            min=0,
            help=(
                "Optional scheduler-owned inflight override. Omit during normal "
                "heartbeats so assignment claims own this counter."
            ),
        ),
        draining: bool = typer.Option(
            False,
            "--draining/--online",
            help="Report whether this executor should stop receiving new work.",
        ),
        metadata: str | None = typer.Option(
            None,
            help="Optional executor lease metadata JSON object.",
        ),
    ) -> None:
        resolved_worker_id = _resolve_worker_id(worker_id)
        with _executor_container() as container:
            try:
                executor_service = _executor_port(container)
                lease = executor_service.heartbeat_executor(
                    worker_id=resolved_worker_id,
                    max_inflight_assignments=max_inflight_assignments,
                    inflight_assignment_count=inflight_assignment_count,
                    draining=draining,
                    metadata=_parse_json_option(metadata, option_name="--metadata"),
                )
                echo_data(OrchestrationExecutorLeaseDTO.from_entity(lease))
            except OrchestrationValidationError as exc:
                _exit_error(exc)

    @app.command("list-executor-leases")
    def list_executor_leases(
        status: str | None = typer.Option(
            None,
            "--status",
            help="Optional executor lease status filter.",
        ),
    ) -> None:
        with _executor_container() as container:
            try:
                executor_service = _executor_port(container)
                leases = executor_service.list_executor_leases(
                    status=_parse_executor_lease_status(
                        status,
                        option_name="--status",
                    ),
                )
                echo_data(
                    [
                        OrchestrationExecutorLeaseDTO.from_entity(lease)
                        for lease in leases
                    ],
                )
            except OrchestrationValidationError as exc:
                _exit_error(exc)

    @app.command("runtime-metrics")
    def runtime_metrics(
        status: str | None = typer.Option(
            None,
            "--status",
            help="Optional executor lease status filter.",
        ),
    ) -> None:
        with _executor_container() as container:
            try:
                executor_service = _executor_port(container)
                leases = executor_service.list_executor_leases(
                    status=_parse_executor_lease_status(
                        status,
                        option_name="--status",
                    ),
                )
                echo_data(_executor_runtime_metrics_payload(leases))
            except OrchestrationValidationError as exc:
                _exit_error(exc)

    @app.command("heartbeat-assignment")
    def heartbeat_assignment(
        run_id: str = typer.Argument(..., help="Orchestration run identifier."),
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Stable orchestration executor identifier.",
        ),
    ) -> None:
        with _executor_container() as container:
            try:
                executor_service = _executor_port(container)
                run = executor_service.heartbeat_assignment(
                    run_id=run_id,
                    worker_id=_resolve_worker_id(worker_id),
                )
                echo_data(OrchestrationRunDTO.from_entity(run))
            except (OrchestrationValidationError, OrchestrationRunNotFoundError) as exc:
                _exit_error(exc)

    @app.command("advance-assignment")
    def advance_assignment(
        run_id: str = typer.Argument(..., help="Orchestration run identifier."),
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Stable orchestration executor identifier.",
        ),
        stage: str = typer.Option(..., help="Target run stage."),
        step_increment: int = typer.Option(
            0,
            "--step-increment",
            min=0,
            help="Optional step counter increment.",
        ),
        metadata: str | None = typer.Option(
            None,
            help="Optional metadata JSON object merged into the run.",
        ),
    ) -> None:
        with _executor_container() as container:
            try:
                executor_service = _executor_port(container)
                run = executor_service.advance_assignment(
                    run_id=run_id,
                    worker_id=_resolve_worker_id(worker_id),
                    stage=parse_run_stage(
                        stage,
                        option_name="--stage",
                        error_factory=_bad_parameter,
                    ),
                    step_increment=step_increment,
                    metadata=_parse_json_option(metadata, option_name="--metadata"),
                )
                echo_data(OrchestrationRunDTO.from_entity(run))
            except (OrchestrationValidationError, OrchestrationRunNotFoundError) as exc:
                _exit_error(exc)

    @app.command("wait-assignment-on-tool")
    def wait_assignment_on_tool(
        run_id: str = typer.Argument(..., help="Orchestration run identifier."),
        tool_run_id: list[str] = typer.Argument(
            ...,
            help="One or more pending tool run identifiers.",
        ),
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Stable orchestration executor identifier.",
        ),
        reason: str | None = typer.Option(None, help="Optional waiting reason."),
    ) -> None:
        with _executor_container() as container:
            try:
                executor_service = _executor_port(container)
                run = executor_service.wait_assignment_on_tool(
                    run_id=run_id,
                    worker_id=_resolve_worker_id(worker_id),
                    pending_tool_run_ids=tuple(tool_run_id),
                    reason=reason,
                )
                echo_data(OrchestrationRunDTO.from_entity(run))
            except (OrchestrationValidationError, OrchestrationRunNotFoundError) as exc:
                _exit_error(exc)

    @app.command("complete-assignment")
    def complete_assignment(
        run_id: str = typer.Argument(..., help="Orchestration run identifier."),
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Stable orchestration executor identifier.",
        ),
        result: str | None = typer.Option(
            None,
            help="Optional result payload JSON object.",
        ),
    ) -> None:
        with _executor_container() as container:
            try:
                executor_service = _executor_port(container)
                run = executor_service.complete_assignment(
                    run_id=run_id,
                    worker_id=_resolve_worker_id(worker_id),
                    result_payload=_parse_json_option(result, option_name="--result"),
                )
                echo_data(OrchestrationRunDTO.from_entity(run))
            except (OrchestrationValidationError, OrchestrationRunNotFoundError) as exc:
                _exit_error(exc)

    @app.command("fail-assignment")
    def fail_assignment(
        run_id: str = typer.Argument(..., help="Orchestration run identifier."),
        message: str = typer.Argument(..., help="Failure message."),
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Optional orchestration executor identifier.",
        ),
        code: str = typer.Option(
            "orchestration_failed",
            help="Failure code.",
        ),
        details: str | None = typer.Option(
            None,
            help="Optional failure details JSON object.",
        ),
    ) -> None:
        with _executor_container() as container:
            try:
                executor_service = _executor_port(container)
                run = executor_service.fail_assignment(
                    run_id=run_id,
                    message=message,
                    code=code,
                    details=_parse_json_option(details, option_name="--details"),
                    worker_id=(
                        _resolve_worker_id(worker_id)
                        if worker_id is not None
                        else None
                    ),
                )
                echo_data(OrchestrationRunDTO.from_entity(run))
            except (OrchestrationValidationError, OrchestrationRunNotFoundError) as exc:
                _exit_error(exc)

def _register_scheduler_commands(app: typer.Typer) -> None:
    def _process_next_request(
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Stable orchestration scheduler identifier.",
        ),
    ) -> None:
        resolved_worker_id = _resolve_worker_id(worker_id)
        with _scheduler_container() as container:
            try:
                scheduler_service = _scheduler_port(container)
                run = scheduler_service.process_next_request(
                    worker_id=resolved_worker_id,
                )
                _echo_run_or_idle(run, worker_id=resolved_worker_id)
            except (OrchestrationValidationError, OrchestrationRunNotFoundError) as exc:
                _exit_error(exc)

    @app.command("process-next-request")
    def process_next_request(
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Stable orchestration scheduler identifier.",
        ),
    ) -> None:
        _process_next_request(worker_id=worker_id)

    @app.command("process-next-continuation")
    def process_next_continuation(
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Stable orchestration scheduler identifier.",
        ),
    ) -> None:
        resolved_worker_id = _resolve_worker_id(worker_id)
        with _scheduler_container() as container:
            try:
                scheduler_service = _scheduler_port(container)
                continuation = scheduler_service.process_next_continuation(
                    worker_id=resolved_worker_id,
                )
                if continuation is None:
                    echo_data({"status": "idle", "worker_id": resolved_worker_id})
                    return
                echo_data(
                    {
                        "continuation_id": continuation.id,
                        "continuation_kind": continuation.continuation_kind.value,
                        "status": continuation.status.value,
                        "worker_id": resolved_worker_id,
                    },
                )
            except (OrchestrationValidationError, OrchestrationRunNotFoundError) as exc:
                _exit_error(exc)

    @app.command("assign-next-assignment")
    def assign_next_assignment(
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Stable orchestration scheduler identifier.",
        ),
    ) -> None:
        resolved_worker_id = _resolve_worker_id(worker_id)
        with _scheduler_container() as container:
            try:
                scheduler_service = _scheduler_port(container)
                run = scheduler_service.assign_next_assignment()
                _echo_run_or_idle(run, worker_id=resolved_worker_id)
            except (OrchestrationValidationError, OrchestrationRunNotFoundError) as exc:
                _exit_error(exc)

    @app.command("run-scheduler")
    def run_scheduler(
        poll_interval_seconds: float = typer.Option(
            0.5,
            "--poll-interval-seconds",
            min=0.05,
            help="Idle wait time between scheduler work polls.",
        ),
        max_runs: int | None = typer.Option(
            None,
            "--max-runs",
            min=1,
            help="Optional maximum number of scheduler work items to process before exiting.",
        ),
        max_idle_cycles: int | None = typer.Option(
            None,
            "--max-idle-cycles",
            min=1,
            help="Optional maximum consecutive idle polls before exiting.",
        ),
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Stable orchestration scheduler identifier.",
        ),
    ) -> None:
        _execute_scheduler_loop(
            poll_interval_seconds=poll_interval_seconds,
            max_runs=max_runs,
            max_idle_cycles=max_idle_cycles,
            worker_id=worker_id,
        )

    @app.command("request-due-heartbeats")
    def request_due_heartbeats(
        idle_seconds: int = typer.Option(
            ...,
            "--idle-seconds",
            min=1,
            help="Minimum idle age before queuing a heartbeat run.",
        ),
        agent_id: str | None = typer.Option(
            None,
            "--agent-id",
            help="Optional agent filter.",
        ),
        limit: int | None = typer.Option(
            None,
            "--limit",
            min=1,
            help="Optional maximum number of heartbeat runs to queue.",
        ),
        reason: str | None = typer.Option(
            None,
            "--reason",
            help="Optional heartbeat reason.",
        ),
        idle_reply: str = typer.Option(
            "HEARTBEAT_OK",
            "--idle-reply",
            help="Default short reply when nothing actionable is pending.",
        ),
    ) -> None:
        with _scheduler_container() as container:
            try:
                scheduler_service = _scheduler_port(container)
                runs = scheduler_service.request_due_heartbeats(
                    RequestDueHeartbeatsInput(
                        idle_seconds=idle_seconds,
                        agent_id=agent_id,
                        limit=limit,
                        reason=reason,
                        idle_reply=idle_reply,
                    ),
                )
                echo_data([OrchestrationRunDTO.from_entity(run) for run in runs])
            except OrchestrationValidationError as exc:
                _exit_error(exc)

    @app.command("recover-abandoned")
    def recover_abandoned() -> None:
        with _scheduler_container() as container:
            try:
                scheduler_service = _scheduler_port(container)
                runs = scheduler_service.recover_abandoned_runs()
                echo_data([OrchestrationRunDTO.from_entity(run) for run in runs])
            except OrchestrationValidationError as exc:
                _exit_error(exc)

    @app.command("expire-executor-leases")
    def expire_executor_leases() -> None:
        with _scheduler_container() as container:
            try:
                scheduler_service = _scheduler_port(container)
                leases = scheduler_service.expire_executor_leases()
                echo_data(
                    [
                        OrchestrationExecutorLeaseDTO.from_entity(lease)
                        for lease in leases
                    ],
                )
            except OrchestrationValidationError as exc:
                _exit_error(exc)

    @app.command("resume")
    def resume(
        run_id: str = typer.Argument(..., help="Orchestration run identifier."),
        lane_key: str | None = typer.Option(None, help="Optional replacement lane key."),
        queue_policy: str | None = typer.Option(
            None,
            help="Optional replacement queue policy.",
        ),
        priority: int | None = typer.Option(
            None,
            min=0,
            help="Optional replacement priority.",
        ),
        reason: str | None = typer.Option(None, help="Optional resume reason."),
        clear_pending_tool_run_ids: bool = typer.Option(
            True,
            "--clear-pending-tool-runs/--keep-pending-tool-runs",
            help="Whether resuming should clear pending tool run references.",
        ),
    ) -> None:
        with _scheduler_container() as container:
            try:
                scheduler_service = _scheduler_port(container)
                run = scheduler_service.resume_run(
                    ResumeOrchestrationRunInput(
                        run_id=run_id,
                        lane_key=lane_key,
                        queue_policy=parse_queue_policy(
                            queue_policy,
                            option_name="--queue-policy",
                            error_factory=_bad_parameter,
                        ),
                        priority=priority,
                        reason=reason,
                        clear_pending_tool_run_ids=clear_pending_tool_run_ids,
                    ),
                )
                echo_data(OrchestrationRunDTO.from_entity(run))
            except (OrchestrationValidationError, OrchestrationRunNotFoundError) as exc:
                _exit_error(exc)


def build_cli() -> typer.Typer:
    app = _build_app("Operate orchestration scheduler and executor services.")
    _register_executor_commands(app)
    _register_scheduler_commands(app)
    return app


def build_executor_cli() -> typer.Typer:
    app = _build_app("Operate orchestration executor service commands.")
    _register_executor_commands(app)
    return app


def build_scheduler_cli() -> typer.Typer:
    app = _build_app("Operate orchestration scheduler service commands.")
    _register_scheduler_commands(app)
    return app


app = build_cli()


def main() -> None:
    app()
