from __future__ import annotations

import typer

from crxzipple.modules.agent.interfaces.cli_home_commands import (
    register_home_commands,
)
from crxzipple.modules.agent.interfaces.cli_profile_commands import (
    register_profile_commands,
)


def build_cli() -> typer.Typer:
    app = typer.Typer(help="Manage agent profiles.", no_args_is_help=True)
    register_profile_commands(app)
    register_home_commands(app)
    return app
