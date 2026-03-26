from __future__ import annotations

import typer

from crxzipple.interfaces.cli.context import ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.orchestration.application import (
    EnqueueOrchestrationRunInput,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationQueuePolicy,
    OrchestrationRunNotFoundError,
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.interfaces.dto import (
    OrchestrationRunDTO,
    PromptPreviewDTO,
)
from crxzipple.modules.orchestration.interfaces.shared import (
    build_accept_run_input,
    build_prepare_session_run_input,
    build_reset_policy,
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
        max_steps: int = typer.Option(12, min=1, help="Maximum step budget."),
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
        delivery_interface: str | None = typer.Option(
            None,
            help="Optional delivery interface name.",
        ),
        delivery_address: str | None = typer.Option(
            None,
            help="Optional delivery target address.",
        ),
        delivery_reply_to: str | None = typer.Option(
            None,
            help="Optional delivery reply-to token.",
        ),
        delivery_metadata: str | None = typer.Option(
            None,
            help="Optional delivery metadata JSON object.",
        ),
    ) -> None:
        container = ensure_container(ctx)
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
            accepted = container.orchestration_service.accept(
                build_accept_run_input(
                    source=source,
                    content=content,
                    inbound_metadata=_parse_json_option(
                        inbound_metadata,
                        option_name="--inbound-metadata",
                    ),
                    delivery_interface=delivery_interface,
                    delivery_address=delivery_address,
                    delivery_reply_to=delivery_reply_to,
                    delivery_metadata=_parse_json_option(
                        delivery_metadata,
                        option_name="--delivery-metadata",
                    ),
                    run_id=run_id,
                    queue_policy=queue_policy_value or OrchestrationQueuePolicy.FIFO,
                    priority=priority,
                    max_steps=max_steps,
                    metadata=run_metadata_payload,
                ),
            )
            prepared = container.orchestration_service.prepare_session_run(
                build_prepare_session_run_input(
                    run_id=accepted.id,
                    agent_id=agent_id,
                    llm_id=llm_id,
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
                    priority=priority,
                    metadata=run_metadata_payload,
                ),
            )
            run = prepared
            if enqueue:
                run = container.orchestration_service.enqueue(
                    EnqueueOrchestrationRunInput(
                        run_id=prepared.id,
                        queue_policy=queue_policy_value,
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
        try:
            run = container.orchestration_service.get_run(run_id)
        except OrchestrationRunNotFoundError as exc:
            _exit_not_found(exc)
        echo_data(OrchestrationRunDTO.from_entity(run))

    @app.command("prompt-preview")
    def prompt_preview(
        ctx: typer.Context,
        run_id: str = typer.Argument(..., help="Orchestration run identifier."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            preview = container.orchestration_service.preview_prompt(run_id)
        except OrchestrationRunNotFoundError as exc:
            _exit_not_found(exc)
        except OrchestrationValidationError as exc:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
            raise typer.Exit(code=1) from None
        echo_data(
            PromptPreviewDTO.from_value(
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
        echo_data(
            [
                OrchestrationRunDTO.from_entity(run)
                for run in container.orchestration_service.list_runs(
                    status=parse_run_status(
                        status,
                        option_name="--status",
                        error_factory=_bad_parameter,
                    ),
                )
            ],
        )

    return app
