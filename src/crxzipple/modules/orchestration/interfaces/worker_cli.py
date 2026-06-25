from __future__ import annotations

import typer

from crxzipple.modules.orchestration.interfaces.worker_cli_common import _build_app
from crxzipple.modules.orchestration.interfaces.worker_cli_executor import (
    register_executor_commands as _register_executor_commands,
)
from crxzipple.modules.orchestration.interfaces.worker_cli_scheduler import (
    register_scheduler_commands as _register_scheduler_commands,
)


def build_cli() -> typer.Typer:
    app = _build_app("Operate orchestration scheduler and executor services.")
    _register_executor_commands(app)
    _register_scheduler_commands(app)
    return app


def build_executor_cli() -> typer.Typer:
    app = _build_app("Operate orchestration executor service commands.")
    _register_executor_commands(app)
    return app


def build_scheduler_cli() -> typer.Typer:
    app = _build_app("Operate orchestration scheduler service commands.")
    _register_scheduler_commands(app)
    return app


app = build_cli()


def main() -> None:
    app()
