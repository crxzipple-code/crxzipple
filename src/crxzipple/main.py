from __future__ import annotations

import sys


def main() -> None:
    if _dispatch_fast_path(sys.argv):
        return
    from crxzipple.interfaces.cli.main import main as cli_main

    cli_main()


def _dispatch_fast_path(argv: list[str]) -> bool:
    if len(argv) < 2:
        return False
    command = argv[1]
    if command != "orchestration":
        return False
    _run_orchestration_cli(argv[2:])
    return True


def _run_orchestration_cli(args: list[str]) -> None:
    import typer
    from sqlalchemy.exc import OperationalError, ProgrammingError

    from crxzipple.core.config import load_settings
    from crxzipple.core.logger import configure_logging, get_logger
    from crxzipple.modules.authorization.domain import AuthorizationDeniedError
    from crxzipple.modules.orchestration.interfaces.cli import (
        build_cli as build_orchestration_cli,
    )

    settings = load_settings()
    configure_logging(settings)
    get_logger(__name__).debug(
        "cli fast-path initialized",
        extra={"environment": settings.environment, "command": "orchestration"},
    )
    try:
        build_orchestration_cli()(args=args, standalone_mode=False)
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


if __name__ == "__main__":
    main()
