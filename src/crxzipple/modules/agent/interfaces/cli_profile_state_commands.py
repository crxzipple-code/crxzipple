from __future__ import annotations

import typer

from crxzipple.interfaces.cli.context import AppKey, ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.agent.domain.exceptions import (
    AgentNotFoundError,
    AgentValidationError,
)
from crxzipple.modules.agent.interfaces.dto import AgentProfileDTO


def register_profile_state_commands(app: typer.Typer) -> None:
    @app.command("enable")
    def enable_profile(
        ctx: typer.Context,
        agent_id: str = typer.Argument(..., help="Agent profile identifier."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            profile = container.require(AppKey.AGENT_SERVICE).enable_profile(agent_id)
        except AgentNotFoundError as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data(AgentProfileDTO.from_entity(profile))

    @app.command("disable")
    def disable_profile(
        ctx: typer.Context,
        agent_id: str = typer.Argument(..., help="Agent profile identifier."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            profile = container.require(AppKey.AGENT_SERVICE).disable_profile(agent_id)
        except AgentNotFoundError as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data(AgentProfileDTO.from_entity(profile))

    @app.command("delete")
    def delete_profile(
        ctx: typer.Context,
        agent_id: str = typer.Argument(..., help="Agent profile identifier."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            container.require(AppKey.AGENT_SERVICE).delete_profile(agent_id)
        except (AgentNotFoundError, AgentValidationError) as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data({"id": agent_id, "deleted": True})


__all__ = ["register_profile_state_commands"]
