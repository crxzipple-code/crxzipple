from __future__ import annotations

import typer

from .cli_action_commands import register_action_commands
from .cli_allocation_commands import register_allocation_commands
from .cli_host_commands import register_host_commands
from .cli_pool_commands import register_pool_commands
from .cli_profile_commands import register_profile_commands


def build_cli() -> typer.Typer:
    app = typer.Typer(
        help="Control browser profiles and page actions.", no_args_is_help=True
    )
    profile_app = typer.Typer(help="Manage browser profiles.", no_args_is_help=True)
    pool_app = typer.Typer(help="Manage browser profile pools.", no_args_is_help=True)
    allocation_app = typer.Typer(
        help="Manage browser profile allocations.", no_args_is_help=True
    )
    host_app = typer.Typer(
        help="Run managed browser host processes.", no_args_is_help=True
    )

    register_profile_commands(app, profile_app)
    register_pool_commands(pool_app)
    register_allocation_commands(allocation_app)
    register_host_commands(host_app)
    register_action_commands(app)

    app.add_typer(profile_app, name="profile")
    app.add_typer(pool_app, name="pool")
    app.add_typer(allocation_app, name="allocation")
    app.add_typer(host_app, name="host")

    return app
