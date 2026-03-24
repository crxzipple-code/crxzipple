from __future__ import annotations

from threading import Event, Thread

import typer
import uvicorn

from crxzipple.interfaces.cli.context import ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.interfaces.http.app import create_app
from crxzipple.interfaces.turns import (
    ForegroundTurnTimeoutError,
    build_turn_options,
    extract_output_text,
    resolve_profile,
    run_foreground_turn,
)
from crxzipple.interfaces.worker_loops import (
    run_orchestration_worker_loop,
    run_tool_worker_loop,
)
from crxzipple.core.logger import get_logger
from crxzipple.modules.orchestration.domain import (
    OrchestrationQueuePolicy,
    OrchestrationRun,
    OrchestrationRunStatus,
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.interfaces.dto import OrchestrationRunDTO
from crxzipple.modules.session.domain import DirectSessionScope

logger = get_logger(__name__)


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
        help="Polling interval while driving the local worker loop.",
    ),
    worker_id: str = typer.Option(
        "crxzipple-foreground-orch",
        help="Foreground orchestration worker id.",
    ),
    tool_worker_id: str = typer.Option(
        "crxzipple-foreground-tool",
        help="Foreground tool worker id.",
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
        worker_id=worker_id,
        tool_worker_id=tool_worker_id,
    )
    try:
        run = run_foreground_turn(
            container.orchestration_service,
            container.tool_service,
            content=content,
            options=options,
        )
    except OrchestrationValidationError as exc:
        typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from None
    except ForegroundTurnTimeoutError as exc:
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
        help="Polling interval while driving the local worker loop.",
    ),
    worker_id: str = typer.Option(
        "crxzipple-chat-orch",
        help="Foreground orchestration worker id.",
    ),
    tool_worker_id: str = typer.Option(
        "crxzipple-chat-tool",
        help="Foreground tool worker id.",
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
        worker_id=worker_id,
        tool_worker_id=tool_worker_id,
    )

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
            run = run_foreground_turn(
                container.orchestration_service,
                container.tool_service,
                content=content,
                options=options,
            )
        except OrchestrationValidationError as exc:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
            continue
        except ForegroundTurnTimeoutError as exc:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
            continue
        _echo_completed_run(run, json_output=False)


def serve(
    ctx: typer.Context,
    host: str = typer.Option("127.0.0.1", help="HTTP bind host."),
    port: int = typer.Option(8000, min=1, max=65535, help="HTTP bind port."),
    orchestration_worker_id: str = typer.Option(
        "crxzipple-serve-orch",
        help="Worker id for the orchestration queue consumer.",
    ),
    tool_worker_id: str = typer.Option(
        "crxzipple-serve-tool",
        help="Worker id for the tool queue consumer.",
    ),
    orchestration_poll_interval_seconds: float = typer.Option(
        0.5,
        min=0.05,
        help="Idle wait between orchestration queue polls.",
    ),
    tool_poll_interval_seconds: float = typer.Option(
        0.5,
        min=0.05,
        help="Idle wait between tool queue polls.",
    ),
) -> None:
    container = ensure_container(ctx)
    stop_event = Event()
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

    def _run_orchestration() -> None:
        try:
            run_orchestration_worker_loop(
                container.orchestration_service,
                worker_id=orchestration_worker_id,
                poll_interval_seconds=orchestration_poll_interval_seconds,
                stop_event=stop_event,
            )
        except Exception:
            logger.exception("orchestration worker loop crashed")
            stop_event.set()
            server.should_exit = True

    def _run_tool() -> None:
        try:
            run_tool_worker_loop(
                container.tool_service,
                worker_id=tool_worker_id,
                poll_interval_seconds=tool_poll_interval_seconds,
                stop_event=stop_event,
            )
        except Exception:
            logger.exception("tool worker loop crashed")
            stop_event.set()
            server.should_exit = True

    orchestration_thread = Thread(
        target=_run_orchestration,
        name="crxzipple-orchestration-worker",
        daemon=True,
    )
    tool_thread = Thread(
        target=_run_tool,
        name="crxzipple-tool-worker",
        daemon=True,
    )

    logger.info(
        "starting crxzipple serve",
        extra={
            "host": host,
            "port": port,
            "orchestration_worker_id": orchestration_worker_id,
            "tool_worker_id": tool_worker_id,
        },
    )
    orchestration_thread.start()
    tool_thread.start()
    try:
        server.run()
    finally:
        stop_event.set()
        orchestration_thread.join(timeout=1.0)
        tool_thread.join(timeout=1.0)
