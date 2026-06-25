from __future__ import annotations

from contextlib import contextmanager
import os
import signal
import socket
from threading import Event as StopEvent
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
from crxzipple.modules.orchestration.application.ports import (
    OrchestrationExecutorControlPort,
    OrchestrationRunQueryPort,
    OrchestrationSchedulerRuntimePort,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationExecutorLeaseStatus,
    OrchestrationRunNotFoundError,
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.interfaces.dto import OrchestrationRunDTO
from crxzipple.modules.orchestration.interfaces.shared import (
    parse_json_object,
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


