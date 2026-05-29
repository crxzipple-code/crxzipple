from __future__ import annotations

import typer

from crxzipple.interfaces.cli.context import AppKey, ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.access.interfaces.inventory import collect_access_inventory
from crxzipple.modules.access.interfaces.presenters import (
    present_readiness,
    present_setup_flow,
)


def build_cli() -> typer.Typer:
    app = typer.Typer(
        help="Inspect external access readiness and setup flows.",
        no_args_is_help=True,
    )

    @app.command("check")
    def check_access(
        ctx: typer.Context,
        target: str = typer.Argument(
            ...,
            help="Access requirement or credential binding to check.",
        ),
        as_credential_binding: bool = typer.Option(
            False,
            "--credential-binding",
            help="Treat target as a raw credential binding instead of a requirement.",
        ),
        workspace_dir: str | None = typer.Option(
            None,
            help="Workspace for relative credential files.",
        ),
        allow_literal: bool = typer.Option(
            False,
            help="Allow literal credential values when checking a credential binding.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        if as_credential_binding:
            readiness = container.require(AppKey.ACCESS_SERVICE).check_credential_binding(
                target,
                workspace_dir=workspace_dir,
                allow_literal=allow_literal,
            )
            echo_data(present_readiness(readiness, target_type="credential_binding"))
            return
        readiness = container.require(AppKey.ACCESS_SERVICE).check_requirement(
            target,
            workspace_dir=workspace_dir,
        )
        echo_data(present_readiness(readiness, target_type="requirement"))

    @app.command("inventory")
    def access_inventory(
        ctx: typer.Context,
        workspace_dir: str | None = typer.Option(
            None,
            help="Workspace for relative credential files.",
        ),
        include_ready: bool = typer.Option(
            False,
            help="Include targets whose access is already ready.",
        ),
        include_disabled: bool = typer.Option(
            False,
            help="Include disabled model/tool/channel assets.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        echo_data(
            collect_access_inventory(
                container,
                workspace_dir=workspace_dir,
                include_ready=include_ready,
                include_disabled=include_disabled,
            ),
        )

    @app.command("setup")
    def begin_setup(
        ctx: typer.Context,
        target: str = typer.Argument(
            ...,
            help="Access requirement or credential binding to prepare.",
        ),
        workspace_dir: str | None = typer.Option(
            None,
            help="Workspace for relative credential files.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        flow = container.require(AppKey.ACCESS_SERVICE).begin_setup(
            target,
            workspace_dir=workspace_dir,
        )
        echo_data(present_setup_flow(flow))

    return app
