from __future__ import annotations

import typer
from sqlalchemy.exc import OperationalError, ProgrammingError

from crxzipple.core.config import load_settings
from crxzipple.core.logger import configure_logging, get_logger
from crxzipple.interfaces.cli.crxzipple import ask as ask_command
from crxzipple.interfaces.cli.crxzipple import chat as chat_command
from crxzipple.interfaces.cli.crxzipple import serve as serve_command
from crxzipple.interfaces.cli.db import build_cli as build_db_cli
from crxzipple.modules.agent.interfaces.cli import build_cli as build_agent_cli
from crxzipple.modules.authorization.interfaces.cli import (
    build_cli as build_authorization_cli,
)
from crxzipple.modules.dispatch.interfaces.cli import build_cli as build_dispatch_cli
from crxzipple.modules.authorization.domain import AuthorizationDeniedError
from crxzipple.modules.llm.interfaces.cli import build_cli as build_llm_cli
from crxzipple.modules.orchestration.interfaces.cli import (
    build_cli as build_orchestration_cli,
)
from crxzipple.modules.orchestration.interfaces.worker_cli import (
    build_cli as build_orchestration_worker_cli,
)
from crxzipple.modules.session.interfaces.cli import build_cli as build_session_cli
from crxzipple.modules.tool.interfaces.cli import build_cli as build_tool_cli
from crxzipple.modules.tool.interfaces.worker_cli import build_cli as build_tool_worker_cli

logger = get_logger(__name__)


app = typer.Typer(
    help="Unified CLI entrypoint for crxzipple.",
    no_args_is_help=True,
    rich_markup_mode=None,
)

app.add_typer(build_tool_cli(), name="tool")
app.add_typer(build_tool_worker_cli(), name="tool-worker")
app.add_typer(build_dispatch_cli(), name="dispatch")
app.add_typer(build_orchestration_cli(), name="orchestration")
app.add_typer(build_orchestration_worker_cli(), name="orchestration-worker")
app.add_typer(build_session_cli(), name="session")
app.add_typer(build_llm_cli(), name="llm")
app.add_typer(build_agent_cli(), name="agent")
app.add_typer(build_authorization_cli(), name="auth")
app.add_typer(build_db_cli(), name="db")


@app.callback()
def root() -> None:
    """Top-level command group."""


@app.command()
def about() -> None:
    settings = load_settings()
    typer.echo(f"{settings.app_name} [{settings.environment}]")


app.command("ask")(ask_command)
app.command("chat")(chat_command)
app.command("serve")(serve_command)


def _is_missing_database_schema_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return (
        "no such table" in message
        or "no such column" in message
        or "undefined table" in message
        or "undefined column" in message
        or ("relation" in message and "does not exist" in message)
        or ("table" in message and "does not exist" in message)
        or ("column" in message and "does not exist" in message)
    )


def main() -> None:
    settings = load_settings()
    configure_logging(settings)
    logger.debug(
        "cli entrypoint initialized",
        extra={"environment": settings.environment},
    )
    try:
        app(standalone_mode=False)
    except (OperationalError, ProgrammingError) as exc:
        if not _is_missing_database_schema_error(exc):
            raise
        typer.secho(
            "Database schema is not initialized or is out of date for the current APP_DATABASE_URL. "
            "Run `PYTHONPATH=src python3 -m crxzipple.main db upgrade head` with the same database settings, then retry.",
            err=True,
            fg=typer.colors.RED,
        )
        raise SystemExit(1) from None
    except AuthorizationDeniedError as exc:
        typer.secho(
            f"Authorization denied: {exc}",
            err=True,
            fg=typer.colors.RED,
        )
        raise SystemExit(1) from None
