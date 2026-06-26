from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import shutil

import typer

from crxzipple.interfaces.cli.context import AppKey, ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.process import ProcessNotFoundError, ProcessValidationError
from crxzipple.modules.process.interfaces.cli_payloads import (
    cleanup_to_payload,
    matches_filters,
    output_to_payload,
    session_to_payload,
)


MAX_PROCESS_COMMAND_CHARS = 8_000


def _resolve_shell_executable() -> str:
    preferred = os.environ.get("SHELL", "").strip()
    if preferred:
        preferred_name = Path(preferred).name.lower()
        if preferred_name in {"sh", "bash", "zsh"}:
            resolved = shutil.which(preferred)
            if resolved:
                return resolved
    fallback = shutil.which("/bin/sh") or shutil.which("sh")
    if fallback:
        return fallback
    raise typer.BadParameter("No POSIX shell is available for process start.")


def _resolve_working_directory(working_directory: str) -> str:
    try:
        resolved = Path(working_directory).expanduser().resolve(strict=True)
    except OSError as exc:
        raise typer.BadParameter(
            f"Working directory '{working_directory}' could not be resolved.",
        ) from exc
    if not resolved.is_dir():
        raise typer.BadParameter(
            f"Working directory '{working_directory}' is not a readable directory.",
        )
    return str(resolved)


def _normalize_command(command: str) -> str:
    normalized = command.strip()
    if not normalized:
        raise typer.BadParameter("command must be a non-empty string.")
    if len(normalized) > MAX_PROCESS_COMMAND_CHARS:
        raise typer.BadParameter(
            f"command is too long; maximum length is {MAX_PROCESS_COMMAND_CHARS} characters.",
        )
    return normalized


def _exit_not_found(message: str) -> None:
    typer.secho(message, err=True, fg=typer.colors.RED)
    raise typer.Exit(code=1) from None


def build_cli() -> typer.Typer:
    app = typer.Typer(help="Manage background processes.", no_args_is_help=True)

    @app.command("start")
    def start_process(
        ctx: typer.Context,
        command: str = typer.Argument(..., help="Shell command to run."),
        working_directory: str = typer.Option(
            ...,
            "--working-directory",
            help="Directory to use as the process working directory.",
        ),
        session_key: str | None = typer.Option(
            None,
            "--session-key",
            help="Optional session key to attach to the process session.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        session = container.require(AppKey.PROCESS_SERVICE).start_command(
            command=_normalize_command(command),
            shell=_resolve_shell_executable(),
            working_directory=_resolve_working_directory(working_directory),
            session_key=session_key.strip() or None if session_key is not None else None,
        )
        echo_data(session_to_payload(session))

    @app.command("list")
    def list_processes(
        ctx: typer.Context,
        session_key: str | None = typer.Option(
            None,
            "--session-key",
            help="Optional session key filter.",
        ),
        working_directory: str | None = typer.Option(
            None,
            "--working-directory",
            help="Optional working directory filter.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        normalized_working_directory = (
            _resolve_working_directory(working_directory)
            if working_directory is not None
            else None
        )
        sessions = [
            session_to_payload(session)
            for session in container.require(
                AppKey.PROCESS_SERVICE,
            ).list_sessions_metadata()
            if matches_filters(
                session,
                session_key=session_key,
                working_directory=normalized_working_directory,
            )
        ]
        echo_data(sessions)

    @app.command("get")
    def get_process(
        ctx: typer.Context,
        process_id: str = typer.Argument(..., help="Process identifier."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            session = container.require(AppKey.PROCESS_SERVICE).get_session(process_id=process_id)
        except ProcessNotFoundError as exc:
            _exit_not_found(str(exc))
        echo_data(session_to_payload(session))

    @app.command("output")
    def get_process_output(
        ctx: typer.Context,
        process_id: str = typer.Argument(..., help="Process identifier."),
        stdout_offset: int = typer.Option(0, min=0, help="Stdout offset."),
        stderr_offset: int = typer.Option(0, min=0, help="Stderr offset."),
        limit: int = typer.Option(4000, min=1, max=20000, help="Maximum characters."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            output = container.require(AppKey.PROCESS_SERVICE).read_output(
                process_id=process_id,
                stdout_offset=stdout_offset,
                stderr_offset=stderr_offset,
                limit=limit,
            )
        except ProcessNotFoundError as exc:
            _exit_not_found(str(exc))
        echo_data(output_to_payload(output))

    @app.command("terminate")
    def terminate_process(
        ctx: typer.Context,
        process_id: str = typer.Argument(..., help="Process identifier."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            container.require(AppKey.PROCESS_SERVICE).get_session(process_id=process_id)
        except ProcessNotFoundError as exc:
            _exit_not_found(str(exc))
        session = container.require(AppKey.PROCESS_SERVICE).terminate_session(process_id=process_id)
        echo_data(session_to_payload(session))

    @app.command("remove")
    def remove_process(
        ctx: typer.Context,
        process_id: str = typer.Argument(..., help="Process identifier."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            session = container.require(AppKey.PROCESS_SERVICE).get_session(process_id=process_id)
        except ProcessNotFoundError as exc:
            _exit_not_found(str(exc))
        try:
            container.require(AppKey.PROCESS_SERVICE).remove_session(process_id=process_id)
        except ProcessValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data(
            {
                "removed": True,
                "process_id": process_id,
                "status": session.status.value,
            },
        )

    @app.command("cleanup")
    def cleanup_processes(
        ctx: typer.Context,
        older_than_days: int | None = typer.Option(
            None,
            "--older-than-days",
            min=0,
            help="Remove terminal process sessions older than this many days.",
        ),
        max_terminal_sessions: int | None = typer.Option(
            None,
            "--max-terminal-sessions",
            min=0,
            help="Keep at most this many newest terminal process sessions.",
        ),
        max_terminal_bytes: int | None = typer.Option(
            None,
            "--max-terminal-bytes",
            min=0,
            help="Keep terminal process session files under this byte budget.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=older_than_days)
            if older_than_days is not None
            else None
        )
        try:
            result = container.require(AppKey.PROCESS_SERVICE).cleanup_sessions(
                ended_before=cutoff,
                max_terminal_sessions=max_terminal_sessions,
                max_terminal_bytes=max_terminal_bytes,
            )
        except ProcessValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data(cleanup_to_payload(result))

    return app
