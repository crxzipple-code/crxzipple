from __future__ import annotations

from contextlib import contextmanager
import os
import socket
from typing import Iterator
from uuid import uuid4

import typer

from crxzipple.bootstrap import AppContainer, build_container
from crxzipple.core.config import load_settings
from crxzipple.core.logger import configure_logging
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.orchestration.application import (
    AdvanceOrchestrationRunInput,
    CompleteOrchestrationRunInput,
    FailOrchestrationRunInput,
    ResumeOrchestrationRunInput,
    WaitOnToolInput,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationRunNotFoundError,
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.interfaces.dto import OrchestrationRunDTO
from crxzipple.modules.orchestration.interfaces.shared import (
    parse_json_object,
    parse_queue_policy,
    parse_run_stage,
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


@contextmanager
def _worker_container() -> Iterator[AppContainer]:
    settings = load_settings()
    configure_logging(settings)
    container = build_container(settings=settings)
    try:
        yield container
    finally:
        container.close()


def _echo_run_or_idle(
    run,
    *,
    worker_id: str,
) -> None:
    if run is None:
        echo_data({"status": "idle", "worker_id": worker_id})
        return
    echo_data(OrchestrationRunDTO.from_entity(run))


def build_cli() -> typer.Typer:
    app = typer.Typer(
        help="Operate orchestration runs as a worker.",
        no_args_is_help=True,
    )

    @app.command("claim-next")
    def claim_next(
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Stable orchestration worker identifier.",
        ),
    ) -> None:
        resolved_worker_id = _resolve_worker_id(worker_id)
        with _worker_container() as container:
            run = container.orchestration_service.claim_next_queued_run(
                worker_id=resolved_worker_id,
            )
            _echo_run_or_idle(run, worker_id=resolved_worker_id)

    @app.command("process-next")
    def process_next(
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Stable orchestration worker identifier.",
        ),
    ) -> None:
        resolved_worker_id = _resolve_worker_id(worker_id)
        with _worker_container() as container:
            try:
                run = container.orchestration_service.process_next_queued_run(
                    worker_id=resolved_worker_id,
                )
                _echo_run_or_idle(run, worker_id=resolved_worker_id)
            except (OrchestrationValidationError, OrchestrationRunNotFoundError) as exc:
                _exit_error(exc)

    @app.command("heartbeat")
    def heartbeat(
        run_id: str = typer.Argument(..., help="Orchestration run identifier."),
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Stable orchestration worker identifier.",
        ),
    ) -> None:
        with _worker_container() as container:
            try:
                run = container.orchestration_service.heartbeat_run(
                    run_id,
                    worker_id=_resolve_worker_id(worker_id),
                )
                echo_data(OrchestrationRunDTO.from_entity(run))
            except (OrchestrationValidationError, OrchestrationRunNotFoundError) as exc:
                _exit_error(exc)

    @app.command("recover-abandoned")
    def recover_abandoned() -> None:
        with _worker_container() as container:
            try:
                runs = container.orchestration_service.recover_abandoned_runs()
                echo_data([OrchestrationRunDTO.from_entity(run) for run in runs])
            except OrchestrationValidationError as exc:
                _exit_error(exc)

    @app.command("advance")
    def advance(
        run_id: str = typer.Argument(..., help="Orchestration run identifier."),
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Stable orchestration worker identifier.",
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
        with _worker_container() as container:
            try:
                run = container.orchestration_service.advance_run(
                    AdvanceOrchestrationRunInput(
                        run_id=run_id,
                        worker_id=_resolve_worker_id(worker_id),
                        stage=parse_run_stage(
                            stage,
                            option_name="--stage",
                            error_factory=_bad_parameter,
                        ),
                        step_increment=step_increment,
                        metadata=_parse_json_option(metadata, option_name="--metadata"),
                    ),
                )
                echo_data(OrchestrationRunDTO.from_entity(run))
            except (OrchestrationValidationError, OrchestrationRunNotFoundError) as exc:
                _exit_error(exc)

    @app.command("wait-tool")
    def wait_tool(
        run_id: str = typer.Argument(..., help="Orchestration run identifier."),
        tool_run_id: list[str] = typer.Argument(
            ...,
            help="One or more pending tool run identifiers.",
        ),
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Stable orchestration worker identifier.",
        ),
        reason: str | None = typer.Option(None, help="Optional waiting reason."),
    ) -> None:
        with _worker_container() as container:
            try:
                run = container.orchestration_service.wait_on_tool(
                    WaitOnToolInput(
                        run_id=run_id,
                        worker_id=_resolve_worker_id(worker_id),
                        pending_tool_run_ids=tuple(tool_run_id),
                        reason=reason,
                    ),
                )
                echo_data(OrchestrationRunDTO.from_entity(run))
            except (OrchestrationValidationError, OrchestrationRunNotFoundError) as exc:
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
        with _worker_container() as container:
            try:
                run = container.orchestration_service.resume_run(
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

    @app.command("complete")
    def complete(
        run_id: str = typer.Argument(..., help="Orchestration run identifier."),
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Stable orchestration worker identifier.",
        ),
        result: str | None = typer.Option(
            None,
            help="Optional result payload JSON object.",
        ),
    ) -> None:
        with _worker_container() as container:
            try:
                run = container.orchestration_service.complete_run(
                    CompleteOrchestrationRunInput(
                        run_id=run_id,
                        worker_id=_resolve_worker_id(worker_id),
                        result_payload=_parse_json_option(result, option_name="--result"),
                    ),
                )
                echo_data(OrchestrationRunDTO.from_entity(run))
            except (OrchestrationValidationError, OrchestrationRunNotFoundError) as exc:
                _exit_error(exc)

    @app.command("fail")
    def fail(
        run_id: str = typer.Argument(..., help="Orchestration run identifier."),
        message: str = typer.Argument(..., help="Failure message."),
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Optional orchestration worker identifier.",
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
        with _worker_container() as container:
            try:
                run = container.orchestration_service.fail_run(
                    FailOrchestrationRunInput(
                        run_id=run_id,
                        message=message,
                        code=code,
                        details=_parse_json_option(details, option_name="--details"),
                        worker_id=(
                            _resolve_worker_id(worker_id)
                            if worker_id is not None
                            else None
                        ),
                    ),
                )
                echo_data(OrchestrationRunDTO.from_entity(run))
            except (OrchestrationValidationError, OrchestrationRunNotFoundError) as exc:
                _exit_error(exc)

    return app


app = build_cli()


def main() -> None:
    app()
