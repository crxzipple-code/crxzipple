from __future__ import annotations

import typer

from crxzipple.interfaces.cli.context import AppKey, ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.agent.application.home_models import (
    ExportAgentHomeInput,
    MigrateAgentHomeInput,
    SyncAgentHomeInput,
)
from crxzipple.modules.agent.interfaces.dto import AgentProfileDTO


def register_home_commands(app: typer.Typer) -> None:
    @app.command("migrate-home")
    def migrate_home(
        ctx: typer.Context,
        agent_id: str = typer.Argument(..., help="Agent profile identifier."),
        home_dir: str = typer.Argument(..., help="Target agent home directory."),
        workdir: str | None = typer.Option(
            None,
            help="Optional workdir to keep after moving agent-home files.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        result = container.require(AppKey.AGENT_SERVICE).migrate_profile_home(
            MigrateAgentHomeInput(
                id=agent_id,
                home_dir=home_dir,
                workdir=workdir,
            ),
        )
        echo_data(
            {
                "source_dir": result.source_dir,
                "home_dir": result.profile.runtime_preferences.resolved_home_dir,
                "workdir": result.profile.runtime_preferences.resolved_workdir,
                "copied_paths": list(result.copied_paths),
                "skipped_paths": list(result.skipped_paths),
                "profile": AgentProfileDTO.from_entity(result.profile),
            },
        )

    @app.command("sync-home")
    def sync_home(
        ctx: typer.Context,
        agent_id: str = typer.Argument(..., help="Agent profile identifier."),
        home_dir: str | None = typer.Option(
            None,
            help="Optional agent home directory override. Defaults to the profile home_dir.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        result = container.require(AppKey.AGENT_SERVICE).sync_profile_home(
            SyncAgentHomeInput(id=agent_id, home_dir=home_dir),
        )
        echo_data(
            {
                "home_dir": result.home_dir,
                "path": result.path,
                "profile": AgentProfileDTO.from_entity(result.profile),
            },
        )

    @app.command("export-home")
    def export_home(
        ctx: typer.Context,
        agent_id: str = typer.Argument(..., help="Agent profile identifier."),
        home_dir: str | None = typer.Option(
            None,
            help="Optional agent home directory override. Defaults to the profile home_dir.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        result = container.require(AppKey.AGENT_SERVICE).export_profile_home(
            ExportAgentHomeInput(id=agent_id, home_dir=home_dir),
        )
        echo_data(
            {
                "home_dir": result.home_dir,
                "path": result.path,
                "profile": AgentProfileDTO.from_entity(result.profile),
            },
        )


__all__ = ["register_home_commands"]
