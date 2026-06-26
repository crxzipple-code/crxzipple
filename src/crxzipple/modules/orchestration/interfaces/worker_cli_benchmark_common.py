from __future__ import annotations

import time

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.modules.orchestration.domain import (
    OrchestrationQueuePolicy,
    OrchestrationRunStatus,
)
from crxzipple.modules.orchestration.interfaces.shared import build_submit_turn_input


ORCHESTRATION_RUNTIME_SERVICE_KEYS = (
    "worker:orchestration-scheduler",
    "worker:orchestration",
)

BENCHMARK_TERMINAL_STATUS_VALUES = {
    OrchestrationRunStatus.COMPLETED.value,
    OrchestrationRunStatus.FAILED.value,
    OrchestrationRunStatus.CANCELLED.value,
}


def benchmark_run_content(
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


def run_status_value(run) -> str:  # noqa: ANN001
    status = getattr(run, "status", None)
    return str(getattr(status, "value", status))


def create_benchmark_runs(
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
                content=benchmark_run_content(
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


def summarize_benchmark_runs(
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
        status_value = run_status_value(run)
        status_counts[status_value] = status_counts.get(status_value, 0) + 1
        worker_id_value = str(getattr(run, "worker_id", "") or "").strip()
        if worker_id_value or status_value not in {
            OrchestrationRunStatus.ACCEPTED.value,
            OrchestrationRunStatus.QUEUED.value,
        }:
            assigned_run_ids.append(run_id)
    return status_counts, assigned_run_ids


def daemon_runtime_service_snapshots(
    container: AppContainer,
    *,
    service_keys: tuple[str, ...] = ORCHESTRATION_RUNTIME_SERVICE_KEYS,
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


def wait_for_benchmark_runs(
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
        status_counts, assigned_run_ids = summarize_benchmark_runs(
            run_query,
            run_ids=run_ids,
        )
        terminal_count = sum(
            count
            for status, count in status_counts.items()
            if status in BENCHMARK_TERMINAL_STATUS_VALUES
        )
        if terminal_count >= len(run_ids):
            return status_counts, assigned_run_ids, True
        if time.monotonic() >= deadline:
            return status_counts, assigned_run_ids, False
        time.sleep(max(float(poll_interval_seconds), 0.01))
