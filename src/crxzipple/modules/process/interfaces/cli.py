from __future__ import annotations

import os
from pathlib import Path
import shutil

import typer

from crxzipple.interfaces.cli.context import ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.process import ProcessNotFoundError, ProcessValidationError


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


def _session_to_payload(session) -> dict[str, object]:  # noqa: ANN001
    return {
        "id": session.id,
        "command": session.command,
        "shell": session.shell,
        "working_directory": session.working_directory,
        "session_key": session.session_key,
        "metadata": dict(session.metadata),
        "pid": session.pid,
        "status": session.status.value,
        "exit_code": session.exit_code,
        "created_at": session.created_at.isoformat(),
        "started_at": session.started_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "ended_at": session.ended_at.isoformat() if session.ended_at is not None else None,
        "termination_requested_at": (
            session.termination_requested_at.isoformat()
            if session.termination_requested_at is not None
            else None
        ),
    }


def _output_to_payload(output) -> dict[str, object]:  # noqa: ANN001
    return {
        "process_id": output.process_id,
        "status": output.status.value,
        "exit_code": output.exit_code,
        "stdout": output.stdout,
        "stderr": output.stderr,
        "stdout_offset": output.stdout_offset,
        "stderr_offset": output.stderr_offset,
        "next_stdout_offset": output.next_stdout_offset,
        "next_stderr_offset": output.next_stderr_offset,
        "started_at": output.started_at.isoformat(),
        "ended_at": output.ended_at.isoformat() if output.ended_at is not None else None,
    }


def _matches_filters(session, *, session_key: str | None, working_directory: str | None) -> bool:  # noqa: ANN001
    if session_key is not None and session.session_key != session_key:
        return False
    if working_directory is not None and session.working_directory != working_directory:
        return False
    return True


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
        session = container.process_service.start_command(
            command=_normalize_command(command),
            shell=_resolve_shell_executable(),
            working_directory=_resolve_working_directory(working_directory),
            session_key=session_key.strip() or None if session_key is not None else None,
        )
        echo_data(_session_to_payload(session))

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
            _session_to_payload(session)
            for session in container.process_service.list_sessions()
            if _matches_filters(
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
            session = container.process_service.get_session(process_id=process_id)
        except ProcessNotFoundError as exc:
            _exit_not_found(str(exc))
        echo_data(_session_to_payload(session))

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
            container.process_service.get_session(process_id=process_id)
        except ProcessNotFoundError as exc:
            _exit_not_found(str(exc))
        output = container.process_service.read_output(
            process_id=process_id,
            stdout_offset=stdout_offset,
            stderr_offset=stderr_offset,
            limit=limit,
        )
        echo_data(_output_to_payload(output))

    @app.command("terminate")
    def terminate_process(
        ctx: typer.Context,
        process_id: str = typer.Argument(..., help="Process identifier."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            container.process_service.get_session(process_id=process_id)
        except ProcessNotFoundError as exc:
            _exit_not_found(str(exc))
        session = container.process_service.terminate_session(process_id=process_id)
        echo_data(_session_to_payload(session))

    @app.command("remove")
    def remove_process(
        ctx: typer.Context,
        process_id: str = typer.Argument(..., help="Process identifier."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            session = container.process_service.get_session(process_id=process_id)
        except ProcessNotFoundError as exc:
            _exit_not_found(str(exc))
        try:
            container.process_service.remove_session(process_id=process_id)
        except ProcessValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data(
            {
                "removed": True,
                "process_id": process_id,
                "status": session.status.value,
            },
        )

    return app
