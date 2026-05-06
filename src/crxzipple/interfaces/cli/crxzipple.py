from __future__ import annotations

import typer
import uvicorn

from crxzipple.core.config import (
    RuntimeDatabaseGuardError,
    load_settings,
    require_runtime_database,
)
from crxzipple.interfaces.cli.context import ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.orchestration.application.turn_submission import (
    AwaitTurnTimeoutError,
    build_turn_options,
    extract_output_text,
    resolve_profile,
    submit_and_wait_for_turn,
)
from crxzipple.core.logger import get_logger
from crxzipple.bootstrap import AppContainer
from crxzipple.modules.orchestration.domain import (
    OrchestrationQueuePolicy,
    OrchestrationRun,
    OrchestrationRunStatus,
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.interfaces.dto import OrchestrationRunDTO
from crxzipple.modules.session.domain import DirectSessionScope

logger = get_logger(__name__)

_ACTIVE_DAEMON_STATUSES = frozenset({"starting", "ready", "degraded"})


def guard_runtime_database(settings, *, runtime_name: str) -> None:  # noqa: ANN001
    try:
        require_runtime_database(settings, runtime_name=runtime_name)
    except RuntimeDatabaseGuardError as exc:
        typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from None


def _require_orchestration_runtime(container: AppContainer) -> None:
    service_keys = container.daemon_manager.resolve_reconcile_service_keys(
        service_set_keys=("orchestration-runtime",),
        include_eager=False,
    )
    unavailable: list[str] = []
    for service_key in service_keys:
        instances = container.daemon_manager.healthcheck_service(service_key)
        if any(instance.status in _ACTIVE_DAEMON_STATUSES for instance in instances):
            continue
        unavailable.append(service_key)
    if not unavailable:
        return
    missing = ", ".join(unavailable)
    raise RuntimeError(
        "Orchestration runtime is not running for this CLI turn. "
        f"Unavailable services: {missing}. "
        "Start it first with `python -m crxzipple.main daemon run --service-set orchestration-runtime`.",
    )


def _echo_completed_run(run: OrchestrationRun, *, json_output: bool) -> None:
    if json_output:
        echo_data(OrchestrationRunDTO.from_entity(run))
        if run.status is not OrchestrationRunStatus.COMPLETED:
            raise typer.Exit(code=1) from None
        return

    if run.status is not OrchestrationRunStatus.COMPLETED:
        message = (
            run.error.message
            if run.error is not None
            else f"Run ended with status {run.status.value}."
        )
        typer.secho(message, err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from None

    output_text = extract_output_text(run)
    if output_text is not None:
        typer.echo(output_text)
        return
    echo_data(OrchestrationRunDTO.from_entity(run))


def ask(
    ctx: typer.Context,
    content: str = typer.Argument(..., help="Message to send to crxzipple."),
    agent_id: str | None = typer.Option(
        None,
        "--agent",
        help="Target agent profile id. If omitted, the only enabled profile is used.",
    ),
    llm_id: str | None = typer.Option(
        None,
        help="Optional LLM profile override. Defaults to the agent profile default.",
    ),
    channel: str = typer.Option(
        "crxzipple",
        help="Conversation channel label used for routing.",
    ),
    chat_type: str = typer.Option("direct", help="Chat type for routing."),
    peer_id: str | None = typer.Option(None, help="Optional peer identifier."),
    conversation_id: str | None = typer.Option(
        None,
        help="Optional group or channel conversation identifier.",
    ),
    thread_id: str | None = typer.Option(None, help="Optional thread identifier."),
    account_id: str | None = typer.Option(None, help="Optional account identifier."),
    main_key: str = typer.Option("main", help="Stable main-session suffix."),
    direct_scope: str = typer.Option(
        DirectSessionScope.MAIN.value,
        help="Direct message routing scope.",
    ),
    source: str = typer.Option("cli", help="Inbound source label."),
    queue_policy: str = typer.Option(
        OrchestrationQueuePolicy.JUMP_QUEUE.value,
        help="Queue ordering policy for this turn.",
    ),
    priority: int = typer.Option(100, min=0, help="Queue priority."),
    max_steps: int | None = typer.Option(
        None,
        min=1,
        help="Optional max step override. Defaults to the agent profile setting.",
    ),
    wait_timeout_seconds: int = typer.Option(
        300,
        min=1,
        help="How long to wait for this turn to finish before exiting.",
    ),
    poll_interval_seconds: float = typer.Option(
        0.05,
        min=0.01,
        help="Observe interval while waiting for orchestration runtime updates.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Print the full orchestration run payload instead of only the reply text.",
    ),
) -> None:
    container = ensure_container(ctx)
    profile, error = resolve_profile(container.agent_service, agent_id=agent_id)
    if profile is None:
        typer.secho(error or "Unable to resolve agent profile.", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from None
    options = build_turn_options(
        profile=profile,
        llm_id=llm_id,
        channel=channel,
        chat_type=chat_type,
        peer_id=peer_id,
        conversation_id=conversation_id,
        thread_id=thread_id,
        account_id=account_id,
        main_key=main_key,
        direct_scope=direct_scope,
        source=source,
        queue_policy=queue_policy,
        priority=priority,
        max_steps=max_steps,
        wait_timeout_seconds=wait_timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )
    try:
        _require_orchestration_runtime(container)
        run = submit_and_wait_for_turn(
            container.orchestration_scheduler_service,
            container.orchestration_run_query_service,
            container.events_service,
            content=content,
            options=options,
        )
    except OrchestrationValidationError as exc:
        typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from None
    except AwaitTurnTimeoutError as exc:
        typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from None
    except RuntimeError as exc:
        typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from None
    _echo_completed_run(run, json_output=json_output)


def chat(
    ctx: typer.Context,
    agent_id: str | None = typer.Option(
        None,
        "--agent",
        help="Target agent profile id. If omitted, the only enabled profile is used.",
    ),
    llm_id: str | None = typer.Option(
        None,
        help="Optional LLM profile override. Defaults to the agent profile default.",
    ),
    channel: str = typer.Option(
        "crxzipple",
        help="Conversation channel label used for routing.",
    ),
    chat_type: str = typer.Option("direct", help="Chat type for routing."),
    peer_id: str | None = typer.Option(None, help="Optional peer identifier."),
    conversation_id: str | None = typer.Option(
        None,
        help="Optional group or channel conversation identifier.",
    ),
    thread_id: str | None = typer.Option(None, help="Optional thread identifier."),
    account_id: str | None = typer.Option(None, help="Optional account identifier."),
    main_key: str = typer.Option("main", help="Stable main-session suffix."),
    direct_scope: str = typer.Option(
        DirectSessionScope.MAIN.value,
        help="Direct message routing scope.",
    ),
    source: str = typer.Option("cli", help="Inbound source label."),
    queue_policy: str = typer.Option(
        OrchestrationQueuePolicy.JUMP_QUEUE.value,
        help="Queue ordering policy for each turn.",
    ),
    priority: int = typer.Option(100, min=0, help="Queue priority."),
    max_steps: int | None = typer.Option(
        None,
        min=1,
        help="Optional max step override. Defaults to the agent profile setting.",
    ),
    wait_timeout_seconds: int = typer.Option(
        300,
        min=1,
        help="How long to wait for each turn to finish before exiting.",
    ),
    poll_interval_seconds: float = typer.Option(
        0.05,
        min=0.01,
        help="Observe interval while waiting for orchestration runtime updates.",
    ),
) -> None:
    container = ensure_container(ctx)
    profile, error = resolve_profile(container.agent_service, agent_id=agent_id)
    if profile is None:
        typer.secho(error or "Unable to resolve agent profile.", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from None
    options = build_turn_options(
        profile=profile,
        llm_id=llm_id,
        channel=channel,
        chat_type=chat_type,
        peer_id=peer_id,
        conversation_id=conversation_id,
        thread_id=thread_id,
        account_id=account_id,
        main_key=main_key,
        direct_scope=direct_scope,
        source=source,
        queue_policy=queue_policy,
        priority=priority,
        max_steps=max_steps,
        wait_timeout_seconds=wait_timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )

    try:
        _require_orchestration_runtime(container)
    except RuntimeError as exc:
        typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from None

    typer.echo(f"Chatting with {profile.id}. Type /exit to quit.")
    while True:
        try:
            content = typer.prompt(f"{profile.id}>").strip()
        except (EOFError, typer.Abort, KeyboardInterrupt):
            typer.echo("")
            break

        if not content:
            continue
        if content in {"/exit", "/quit"}:
            break

        try:
            run = submit_and_wait_for_turn(
                container.orchestration_scheduler_service,
                container.orchestration_run_query_service,
                container.events_service,
                content=content,
                options=options,
            )
        except OrchestrationValidationError as exc:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
            continue
        except AwaitTurnTimeoutError as exc:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
            continue
        _echo_completed_run(run, json_output=False)


def serve(
    ctx: typer.Context,
    host: str = typer.Option("127.0.0.1", help="HTTP bind host."),
    port: int = typer.Option(8000, min=1, max=65535, help="HTTP bind port."),
) -> None:
    guard_runtime_database(load_settings(), runtime_name="HTTP API")
    from crxzipple.interfaces.http.app import create_app

    container = ensure_container(ctx)
    http_app = create_app(
        settings=container.settings,
        container=container,
        manage_container_lifecycle=False,
    )
    server = uvicorn.Server(
        uvicorn.Config(
            http_app,
            host=host,
            port=port,
            log_level="info",
        ),
    )

    logger.info(
        "starting crxzipple serve",
        extra={
            "host": host,
            "port": port,
            "mode": "api-only",
        },
    )
    server.run()
