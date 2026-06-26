from __future__ import annotations

import typer

from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.orchestration.domain import (
    OrchestrationRunNotFoundError,
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.interfaces.dto import (
    OrchestrationExecutorLeaseDTO,
    OrchestrationRunDTO,
)
from crxzipple.modules.orchestration.interfaces.worker_cli_executor_benchmarks import (
    register_executor_benchmark_commands,
)
from crxzipple.modules.orchestration.interfaces.shared import parse_run_stage
from crxzipple.modules.orchestration.interfaces.worker_cli_common import (
    _bad_parameter,
    _echo_run_or_idle,
    _execute_executor_loop,
    _execute_executor_probe,
    _executor_container,
    _executor_port,
    _executor_runtime_metrics_payload,
    _exit_error,
    _parse_executor_lease_status,
    _parse_json_option,
    _resolve_worker_id,
)


def register_executor_commands(
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

    register_executor_benchmark_commands(app)

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
