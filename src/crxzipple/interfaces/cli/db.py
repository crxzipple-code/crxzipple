from __future__ import annotations

import io
import os
from pathlib import Path
from typing import TextIO

from alembic import command
from alembic.config import Config
import typer

from crxzipple.core.config import load_settings


PROJECT_ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_INI_PATH = PROJECT_ROOT / "alembic.ini"
ALEMBIC_SCRIPT_PATH = PROJECT_ROOT / "alembic"
SRC_PATH = PROJECT_ROOT / "src"


def resolve_alembic_ini_path() -> Path:
    return Path(os.getenv("APP_ALEMBIC_INI_PATH", str(ALEMBIC_INI_PATH)))


def resolve_alembic_script_path() -> Path:
    return Path(
        os.getenv("APP_ALEMBIC_SCRIPT_LOCATION", str(ALEMBIC_SCRIPT_PATH)),
    )


def resolve_src_path() -> Path:
    return Path(os.getenv("APP_ALEMBIC_SRC_PATH", str(SRC_PATH)))


def build_alembic_config(*, stdout: TextIO | None = None) -> Config:
    settings = load_settings()
    config = Config(str(resolve_alembic_ini_path()), stdout=stdout)
    config.set_main_option("sqlalchemy.url", settings.database_url)
    config.set_main_option("script_location", str(resolve_alembic_script_path()))
    config.set_main_option("prepend_sys_path", str(resolve_src_path()))
    return config


def echo_revision_script_path(script: object) -> None:
    if script is None:
        return

    if isinstance(script, list):
        for item in script:
            typer.echo(item.path)
        return

    typer.echo(script.path)


def build_cli() -> typer.Typer:
    app = typer.Typer(help="Manage database migrations.", no_args_is_help=True)

    @app.command("upgrade")
    def upgrade(revision: str = typer.Argument("head", help="Target revision.")) -> None:
        command.upgrade(build_alembic_config(), revision)

    @app.command("downgrade")
    def downgrade(
        revision: str = typer.Argument("base", help="Target revision."),
    ) -> None:
        command.downgrade(build_alembic_config(), revision)

    @app.command("stamp")
    def stamp(revision: str = typer.Argument("head", help="Revision to mark.")) -> None:
        command.stamp(build_alembic_config(), revision)

    @app.command("revision")
    def revision(
        message: str = typer.Argument(..., help="Revision message."),
        autogenerate: bool = typer.Option(
            False,
            "--autogenerate/--empty",
            help="Compare metadata to the database before creating the revision.",
        ),
    ) -> None:
        script = command.revision(
            build_alembic_config(),
            message=message,
            autogenerate=autogenerate,
        )
        echo_revision_script_path(script)

    @app.command("revision-empty")
    def revision_empty(
        message: str = typer.Argument(..., help="Revision message."),
    ) -> None:
        script = command.revision(
            build_alembic_config(),
            message=message,
            autogenerate=False,
        )
        echo_revision_script_path(script)

    @app.command("current")
    def current(
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output."),
    ) -> None:
        output = io.StringIO()
        command.current(build_alembic_config(stdout=output), verbose=verbose)
        typer.echo(output.getvalue().rstrip())

    @app.command("history")
    def history(
        revision_range: str | None = typer.Argument(
            None,
            help="Optional revision range, e.g. base:head.",
        ),
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output."),
    ) -> None:
        output = io.StringIO()
        command.history(
            build_alembic_config(stdout=output),
            rev_range=revision_range,
            verbose=verbose,
        )
        typer.echo(output.getvalue().rstrip())

    return app
