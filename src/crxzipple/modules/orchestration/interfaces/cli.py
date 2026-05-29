from __future__ import annotations

import typer

from crxzipple.interfaces.cli.context import AppKey, ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.orchestration.application.ports import (
    OrchestrationInspectionPort,
    OrchestrationRunQueryPort,
    OrchestrationSubmissionPort,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationQueuePolicy,
    OrchestrationRunNotFoundError,
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.interfaces.dto import (
    OrchestrationRunDTO,
    PromptSurfacePreviewDTO,
)
from crxzipple.modules.orchestration.interfaces.shared import (
    build_reset_policy,
    build_submit_turn_input,
    parse_direct_scope,
    parse_json_object,
    parse_queue_policy,
    parse_run_status,
)
from crxzipple.modules.session.domain import DirectSessionScope


def _bad_parameter(message: str) -> typer.BadParameter:
    return typer.BadParameter(message)


def _parse_json_option(raw: str | None, *, option_name: str) -> dict[str, object]:
    return parse_json_object(
        raw,
        option_name=option_name,
        error_factory=_bad_parameter,
    )


def _exit_not_found(exc: OrchestrationRunNotFoundError) -> None:
    typer.secho(str(exc), err=True, fg=typer.colors.RED)
    raise typer.Exit(code=1) from None


def _inspection_port(container) -> OrchestrationInspectionPort:  # noqa: ANN001
    return container.require(AppKey.ORCHESTRATION_INSPECTION_SERVICE)


def _run_query_port(container) -> OrchestrationRunQueryPort:  # noqa: ANN001
    return container.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE)


def _scheduler_port(container) -> OrchestrationSubmissionPort:  # noqa: ANN001
    return container.require(AppKey.ORCHESTRATION_SUBMISSION_SERVICE)


def build_cli() -> typer.Typer:
    app = typer.Typer(help="Manage orchestration runs.", no_args_is_help=True)

    @app.command("intake")
    def intake_run(
        ctx: typer.Context,
        agent_id: str = typer.Argument(..., help="Target agent identifier."),
        llm_id: str = typer.Argument(..., help="Target LLM identifier."),
        content: str | None = typer.Argument(None, help="Optional inbound content."),
        source: str = typer.Option("cli", help="Inbound source label."),
        run_id: str | None = typer.Option(None, help="Optional orchestration run id."),
        channel: str | None = typer.Option(None, help="Optional channel identifier."),
        chat_type: str = typer.Option("direct", help="Chat type for routing."),
        peer_id: str | None = typer.Option(None, help="Optional peer identifier."),
        conversation_id: str | None = typer.Option(
            None,
            help="Optional group or channel conversation identifier.",
        ),
        thread_id: str | None = typer.Option(None, help="Optional thread identifier."),
        account_id: str | None = typer.Option(None, help="Optional account identifier."),
        label: str | None = typer.Option(None, help="Optional origin label."),
        surface: str | None = typer.Option(None, help="Optional origin surface."),
        main_key: str = typer.Option("main", help="Stable main-session suffix."),
        direct_scope: str = typer.Option(
            DirectSessionScope.MAIN.value,
            help="Direct message routing scope.",
        ),
        session_status: str = typer.Option("active", help="Session status."),
        queue_policy: str = typer.Option(
            OrchestrationQueuePolicy.FIFO.value,
            help="Queue ordering policy for this run.",
        ),
        priority: int = typer.Option(100, min=0, help="Queue priority."),
        max_steps: int = typer.Option(99, min=1, help="Maximum step budget."),
        enqueue: bool = typer.Option(
            False,
            "--enqueue/--no-enqueue",
            help="Immediately place the prepared run onto the queue.",
        ),
        touch_activity: bool = typer.Option(
            True,
            "--touch-activity/--no-touch-activity",
            help="Refresh session activity timestamps while ensuring.",
        ),
        idle_minutes: int | None = typer.Option(
            None,
            min=1,
            help="Reset the active session after this many idle minutes.",
        ),
        daily_reset_hour_utc: int | None = typer.Option(
            None,
            min=0,
            max=23,
            help="Reset the active session at this UTC hour each day.",
        ),
        inbound_metadata: str | None = typer.Option(
            None,
            help="Optional inbound instruction metadata JSON object.",
        ),
        session_metadata: str | None = typer.Option(
            None,
            help="Optional session route metadata JSON object.",
        ),
        run_metadata: str | None = typer.Option(
            None,
            help="Optional orchestration run metadata JSON object.",
        ),
        reply_interface: str | None = typer.Option(
            None,
            help="Optional reply interface name.",
        ),
        reply_address: str | None = typer.Option(
            None,
            help="Optional reply target address.",
        ),
        reply_to: str | None = typer.Option(
            None,
            help="Optional reply-to token.",
        ),
        reply_metadata: str | None = typer.Option(
            None,
            help="Optional reply metadata JSON object.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        scheduler_service = _scheduler_port(container)
        try:
            queue_policy_value = parse_queue_policy(
                queue_policy,
                option_name="--queue-policy",
                error_factory=_bad_parameter,
            )
            run_metadata_payload = _parse_json_option(
                run_metadata,
                option_name="--run-metadata",
            )
            run = scheduler_service.submit_turn(
                build_submit_turn_input(
                    source=source,
                    content=content,
                    agent_id=agent_id,
                    llm_id=llm_id,
                    inbound_metadata=_parse_json_option(
                        inbound_metadata,
                        option_name="--inbound-metadata",
                    ),
                    reply_interface=reply_interface,
                    reply_address=reply_address,
                    reply_to=reply_to,
                    reply_metadata=_parse_json_option(
                        reply_metadata,
                        option_name="--reply-metadata",
                    ),
                    run_id=run_id,
                    queue_policy=queue_policy_value or OrchestrationQueuePolicy.FIFO,
                    priority=priority,
                    max_steps=max_steps,
                    channel=channel,
                    chat_type=chat_type,
                    peer_id=peer_id,
                    conversation_id=conversation_id,
                    thread_id=thread_id,
                    account_id=account_id,
                    label=label,
                    surface=surface,
                    main_key=main_key,
                    direct_scope=parse_direct_scope(
                        direct_scope,
                        option_name="--direct-scope",
                        error_factory=_bad_parameter,
                    ),
                    status=session_status,
                    session_metadata=_parse_json_option(
                        session_metadata,
                        option_name="--session-metadata",
                    ),
                    touch_activity=touch_activity,
                    reset_policy=build_reset_policy(
                        idle_minutes=idle_minutes,
                        daily_reset_hour_utc=daily_reset_hour_utc,
                    ),
                    metadata=run_metadata_payload,
                ),
                inline_worker_id=(
                    f"cli-intake:{run_id or agent_id}"
                    if enqueue
                    else None
                ),
            )
        except OrchestrationValidationError as exc:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
            raise typer.Exit(code=1) from None
        echo_data(OrchestrationRunDTO.from_entity(run))

    @app.command("get")
    def get_run(
        ctx: typer.Context,
        run_id: str = typer.Argument(..., help="Orchestration run identifier."),
    ) -> None:
        container = ensure_container(ctx)
        run_query = _run_query_port(container)
        try:
            run = run_query.get_run(run_id)
        except OrchestrationRunNotFoundError as exc:
            _exit_not_found(exc)
        echo_data(OrchestrationRunDTO.from_entity(run))

    @app.command("prompt-preview")
    def prompt_preview(
        ctx: typer.Context,
        run_id: str = typer.Argument(..., help="Orchestration run identifier."),
    ) -> None:
        container = ensure_container(ctx)
        inspection_service = _inspection_port(container)
        try:
            preview = inspection_service.preview_prompt(run_id)
        except OrchestrationRunNotFoundError as exc:
            _exit_not_found(exc)
        except OrchestrationValidationError as exc:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
            raise typer.Exit(code=1) from None
        echo_data(
            PromptSurfacePreviewDTO.from_value(
                run_id=run_id,
                preview=preview,
            ),
        )

    @app.command("list")
    def list_runs(
        ctx: typer.Context,
        status: str | None = typer.Option(
            None,
            help="Optional run status filter.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        run_query = _run_query_port(container)
        echo_data(
            [
                OrchestrationRunDTO.from_entity(run)
                for run in run_query.list_runs(
                    status=parse_run_status(
                        status,
                        option_name="--status",
                        error_factory=_bad_parameter,
                    ),
                )
            ],
        )

    return app
