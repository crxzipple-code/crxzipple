from __future__ import annotations

import typer

from crxzipple.core.config import load_settings
from crxzipple.interfaces.cli.crxzipple import guard_runtime_database
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.orchestration.application import (
    RequestDueHeartbeatsInput,
    ResumeOrchestrationRunInput,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationRunNotFoundError,
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.interfaces.dto import (
    OrchestrationExecutorLeaseDTO,
    OrchestrationRunDTO,
)
from crxzipple.modules.orchestration.interfaces.shared import parse_queue_policy
from crxzipple.modules.orchestration.interfaces.worker_cli_common import (
    _bad_parameter,
    _echo_run_or_idle,
    _exit_error,
    _resolve_worker_id,
    _scheduler_container,
    _scheduler_port,
)


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


def register_scheduler_commands(app: typer.Typer) -> None:
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


