from __future__ import annotations

import typer

from crxzipple.interfaces.cli.context import AppKey, ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.agent.interfaces.cli_payloads import profile_settings_to_input
from crxzipple.modules.agent.interfaces.dto import AgentProfileDTO


def register_profile_sync_command(app: typer.Typer) -> None:
    @app.command("sync-profiles")
    def sync_profiles(
        ctx: typer.Context,
        profile: list[str] = typer.Option(
            None,
            "--profile",
            help="Optional configured profile id to sync.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        selected_ids = set(profile or [])
        configured_profiles = tuple(
            item
            for item in container.require(AppKey.CORE_SETTINGS).agent_profiles
            if not selected_ids or item.id in selected_ids
        )
        synced = container.require(AppKey.AGENT_SERVICE).sync_profiles(
            tuple(profile_settings_to_input(item) for item in configured_profiles),
        )
        echo_data([AgentProfileDTO.from_entity(item) for item in synced])


__all__ = ["register_profile_sync_command"]
