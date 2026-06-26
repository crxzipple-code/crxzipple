from __future__ import annotations

import typer

from crxzipple.interfaces.cli.context import AppKey, ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.agent.domain.exceptions import (
    AgentAlreadyExistsError,
    AgentNotFoundError,
    AgentValidationError,
)
from crxzipple.modules.agent.interfaces.cli_payloads import (
    register_profile_input,
    update_profile_input,
)
from crxzipple.modules.agent.interfaces.cli_profile_state_commands import (
    register_profile_state_commands,
)
from crxzipple.modules.agent.interfaces.cli_profile_sync_commands import (
    register_profile_sync_command,
)
from crxzipple.modules.agent.interfaces.dto import AgentProfileDTO


def register_profile_commands(app: typer.Typer) -> None:
    @app.command("register-profile")
    def register_profile(
        ctx: typer.Context,
        agent_id: str = typer.Argument(..., help="Agent profile identifier."),
        name: str = typer.Argument(..., help="Agent profile display name."),
        default_llm_id: str = typer.Argument(..., help="Default LLM profile id."),
        fallback_llm_id: list[str] = typer.Option(
            None,
            "--fallback-llm",
            help="Fallback LLM profile ids.",
        ),
        image_llm_id: str | None = typer.Option(
            None,
            help="Optional image-capable LLM profile id.",
        ),
        document_llm_id: str | None = typer.Option(
            None,
            help="Optional document-capable LLM profile id.",
        ),
        system_prompt: str = typer.Option("", help="System prompt for this profile."),
        response_style: str | None = typer.Option(
            None,
            help="Optional response style hint.",
        ),
        thinking_default: str | None = typer.Option(
            None,
            help="Optional thinking style hint.",
        ),
        stream_by_default: bool = typer.Option(
            False,
            "--stream-by-default/--no-stream-by-default",
            help="Whether streaming should be enabled by default.",
        ),
        timeout_seconds: int = typer.Option(120, help="Execution timeout in seconds."),
        max_turns: int = typer.Option(99, help="Maximum turn budget."),
        home_dir: str | None = typer.Option(
            None,
            help="Optional agent home directory for AGENT.md/SOUL.md/USER.md.",
        ),
        workdir: str | None = typer.Option(
            None,
            help="Optional default working directory for agent tasks.",
        ),
        workspace: str | None = typer.Option(
            None,
            help="Legacy alias for setting both home_dir and workdir together.",
        ),
        sandbox_mode: str | None = typer.Option(
            None,
            help="Optional runtime sandbox mode preference.",
        ),
        memory_scope_ref: str | None = typer.Option(
            None,
            help="Optional memory scope reference for this agent.",
        ),
        memory_enabled: bool = typer.Option(
            True,
            "--memory-enabled/--memory-disabled",
            help="Whether memory is enabled for this agent.",
        ),
        memory_access: str = typer.Option(
            "read_write",
            help="Memory access mode: read or read_write.",
        ),
        display_name: str | None = typer.Option(
            None,
            help="Optional identity display name.",
        ),
        theme: str | None = typer.Option(None, help="Optional identity theme."),
        emoji: str | None = typer.Option(None, help="Optional identity emoji."),
        avatar: str | None = typer.Option(None, help="Optional identity avatar."),
        enabled: bool = typer.Option(True, "--enabled/--disabled"),
        reason: str | None = typer.Option(
            None,
            "--reason",
            help="Optional reason for the profile change.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        del reason
        try:
            profile = container.require(AppKey.AGENT_SERVICE).register_profile(
                register_profile_input(
                    agent_id=agent_id,
                    name=name,
                    enabled=enabled,
                    default_llm_id=default_llm_id,
                    fallback_llm_id=fallback_llm_id,
                    image_llm_id=image_llm_id,
                    document_llm_id=document_llm_id,
                    system_prompt=system_prompt,
                    response_style=response_style,
                    thinking_default=thinking_default,
                    stream_by_default=stream_by_default,
                    timeout_seconds=timeout_seconds,
                    max_turns=max_turns,
                    home_dir=home_dir,
                    workdir=workdir,
                    workspace=workspace,
                    sandbox_mode=sandbox_mode,
                    memory_scope_ref=memory_scope_ref,
                    memory_enabled=memory_enabled,
                    memory_access=memory_access,
                    display_name=display_name,
                    theme=theme,
                    emoji=emoji,
                    avatar=avatar,
                ),
            )
        except (AgentAlreadyExistsError, AgentValidationError) as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data(AgentProfileDTO.from_entity(profile))

    @app.command("update-profile")
    def update_profile(
        ctx: typer.Context,
        agent_id: str = typer.Argument(..., help="Agent profile identifier."),
        name: str | None = typer.Option(None, help="New agent profile display name."),
        default_llm_id: str | None = typer.Option(
            None,
            help="New default LLM profile id.",
        ),
        memory_scope_ref: str | None = typer.Option(
            None,
            help="New memory scope reference.",
        ),
        memory_enabled: bool | None = typer.Option(
            None,
            "--memory-enabled/--memory-disabled",
            help="Override whether memory is enabled.",
        ),
        memory_access: str | None = typer.Option(
            None,
            help="Override memory access mode: read or read_write.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        current_memory = None
        if (
            memory_scope_ref is not None
            or memory_enabled is not None
            or memory_access is not None
        ):
            current_memory = container.require(AppKey.AGENT_SERVICE).get_profile(
                agent_id,
            ).memory
        try:
            profile = container.require(AppKey.AGENT_SERVICE).update_profile(
                update_profile_input(
                    agent_id=agent_id,
                    name=name,
                    default_llm_id=default_llm_id,
                    memory_scope_ref=memory_scope_ref,
                    memory_enabled=memory_enabled,
                    memory_access=memory_access,
                    current_memory=current_memory,
                ),
            )
        except (AgentNotFoundError, AgentValidationError, ValueError) as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data(AgentProfileDTO.from_entity(profile))

    register_profile_sync_command(app)

    @app.command("list")
    def list_profiles(ctx: typer.Context) -> None:
        container = ensure_container(ctx)
        echo_data(
            [
                AgentProfileDTO.from_entity(profile)
                for profile in container.require(AppKey.AGENT_SERVICE).list_profiles()
            ],
        )

    @app.command("get")
    def get_profile(
        ctx: typer.Context,
        agent_id: str = typer.Argument(..., help="Agent profile identifier."),
    ) -> None:
        container = ensure_container(ctx)
        echo_data(
            AgentProfileDTO.from_entity(
                container.require(AppKey.AGENT_SERVICE).get_profile(agent_id),
            ),
        )

    register_profile_state_commands(app)


__all__ = ["register_profile_commands"]
