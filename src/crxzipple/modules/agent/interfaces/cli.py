from __future__ import annotations

import typer

from crxzipple.core.config import AgentProfileSettings
from crxzipple.interfaces.cli.context import ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.agent.application import RegisterAgentProfileInput
from crxzipple.modules.agent.domain.value_objects import (
    AgentExecutionPolicy,
    AgentIdentity,
    AgentInstructionPolicy,
    AgentLlmRoutingPolicy,
    AgentRuntimePreferences,
)
from crxzipple.modules.agent.interfaces.dto import AgentProfileDTO


def _profile_settings_to_input(profile: AgentProfileSettings) -> RegisterAgentProfileInput:
    return RegisterAgentProfileInput(
        id=profile.id,
        name=profile.name,
        description=profile.description,
        enabled=profile.enabled,
        identity=AgentIdentity.from_payload(profile.identity),
        instruction_policy=AgentInstructionPolicy.from_payload(
            profile.instruction_policy,
        ),
        llm_routing_policy=AgentLlmRoutingPolicy.from_payload(
            profile.llm_routing_policy,
        ),
        execution_policy=AgentExecutionPolicy.from_payload(profile.execution_policy),
        runtime_preferences=AgentRuntimePreferences.from_payload(
            profile.runtime_preferences,
        ),
    )


def build_cli() -> typer.Typer:
    app = typer.Typer(help="Manage agent profiles.", no_args_is_help=True)

    @app.command("register-profile")
    def register_profile(
        ctx: typer.Context,
        agent_id: str = typer.Argument(..., help="Agent profile identifier."),
        name: str = typer.Argument(..., help="Agent profile display name."),
        default_llm_id: str = typer.Argument(..., help="Default LLM profile id."),
        description: str = typer.Option("", help="Optional agent description."),
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
        max_turns: int = typer.Option(12, help="Maximum turn budget."),
        workspace: str | None = typer.Option(
            None,
            help="Optional preferred workspace path.",
        ),
        sandbox_mode: str | None = typer.Option(
            None,
            help="Optional runtime sandbox mode preference.",
        ),
        display_name: str | None = typer.Option(
            None,
            help="Optional identity display name.",
        ),
        theme: str | None = typer.Option(None, help="Optional identity theme."),
        emoji: str | None = typer.Option(None, help="Optional identity emoji."),
        avatar: str | None = typer.Option(None, help="Optional identity avatar."),
        enabled: bool = typer.Option(True, "--enabled/--disabled"),
    ) -> None:
        container = ensure_container(ctx)
        profile = container.agent_service.register_profile(
            RegisterAgentProfileInput(
                id=agent_id,
                name=name,
                description=description,
                enabled=enabled,
                identity=AgentIdentity(
                    display_name=display_name,
                    theme=theme,
                    emoji=emoji,
                    avatar=avatar,
                ),
                instruction_policy=AgentInstructionPolicy(
                    system_prompt=system_prompt,
                    response_style=response_style,
                    thinking_default=thinking_default,
                    stream_by_default=stream_by_default,
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(
                    default_llm_id=default_llm_id,
                    fallback_llm_ids=tuple(fallback_llm_id or ()),
                    image_llm_id=image_llm_id,
                    document_llm_id=document_llm_id,
                ),
                execution_policy=AgentExecutionPolicy(
                    timeout_seconds=timeout_seconds,
                    max_turns=max_turns,
                ),
                runtime_preferences=AgentRuntimePreferences(
                    workspace=workspace,
                    sandbox_mode=sandbox_mode,
                ),
            ),
        )
        echo_data(AgentProfileDTO.from_entity(profile))

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
            for item in container.settings.agent_profiles
            if not selected_ids or item.id in selected_ids
        )
        synced = container.agent_service.sync_profiles(
            tuple(_profile_settings_to_input(item) for item in configured_profiles),
        )
        echo_data([AgentProfileDTO.from_entity(item) for item in synced])

    @app.command("list")
    def list_profiles(ctx: typer.Context) -> None:
        container = ensure_container(ctx)
        echo_data(
            [
                AgentProfileDTO.from_entity(profile)
                for profile in container.agent_service.list_profiles()
            ],
        )

    @app.command("get")
    def get_profile(
        ctx: typer.Context,
        agent_id: str = typer.Argument(..., help="Agent profile identifier."),
    ) -> None:
        container = ensure_container(ctx)
        echo_data(
            AgentProfileDTO.from_entity(container.agent_service.get_profile(agent_id)),
        )

    @app.command("enable")
    def enable_profile(
        ctx: typer.Context,
        agent_id: str = typer.Argument(..., help="Agent profile identifier."),
    ) -> None:
        container = ensure_container(ctx)
        echo_data(
            AgentProfileDTO.from_entity(container.agent_service.enable_profile(agent_id)),
        )

    @app.command("disable")
    def disable_profile(
        ctx: typer.Context,
        agent_id: str = typer.Argument(..., help="Agent profile identifier."),
    ) -> None:
        container = ensure_container(ctx)
        echo_data(
            AgentProfileDTO.from_entity(container.agent_service.disable_profile(agent_id)),
        )

    return app
