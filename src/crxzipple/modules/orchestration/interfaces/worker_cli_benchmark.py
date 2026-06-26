from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from threading import Event as StopEvent
import time
from uuid import uuid4

import typer

from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.orchestration.domain import (
    OrchestrationExecutorLeaseStatus,
    OrchestrationQueuePolicy,
    OrchestrationRunNotFoundError,
    OrchestrationRunStatus,
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.interfaces.shared import (
    parse_queue_policy,
)
from crxzipple.modules.orchestration.interfaces.worker_cli_benchmark_common import (
    create_benchmark_runs,
    daemon_runtime_service_snapshots,
    summarize_benchmark_runs,
    wait_for_benchmark_runs,
)
from crxzipple.modules.orchestration.interfaces.worker_cli_benchmark_synthetic import (
    register_tool_io_benchmark_runtime,
)
from crxzipple.modules.orchestration.interfaces.worker_cli_common import (
    _admin_container,
    _bad_parameter,
    _executor_port,
    _exit_error,
    _linked_runtime_containers,
    _resolve_worker_id,
    _run_query_port,
    _scheduler_container,
    _scheduler_port,
)

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
                register_tool_io_benchmark_runtime(
                    executor_container,
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

            run_ids = create_benchmark_runs(
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
            status_counts, assigned_run_ids = summarize_benchmark_runs(
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
            run_ids = create_benchmark_runs(
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
            status_counts, assigned_run_ids = summarize_benchmark_runs(
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

    with (
        _admin_container() as admin_container,
        _scheduler_container() as scheduler_container,
    ):
        try:
            scheduler_service = _scheduler_port(scheduler_container)
            run_query = _run_query_port(admin_container)
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

            daemon_services = daemon_runtime_service_snapshots(admin_container)
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

            run_ids = create_benchmark_runs(
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
                wait_for_benchmark_runs(
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
