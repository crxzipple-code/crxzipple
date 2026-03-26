from __future__ import annotations

import typer

from crxzipple.core.config import AgentProfileSettings
from crxzipple.interfaces.cli.context import ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.agent.application import (
    ExportAgentHomeInput,
    MigrateAgentHomeInput,
    RegisterAgentProfileInput,
    SyncAgentHomeInput,
)
from crxzipple.modules.agent.domain.value_objects import (
    AgentExecutionPolicy,
    AgentIdentity,
    AgentInstructionPolicy,
    AgentLlmRoutingPolicy,
    AgentRuntimePreferences,
    AgentToolPreferences,
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
        tool_preferences=AgentToolPreferences.from_payload(profile.tool_preferences),
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
        home_dir: str | None = typer.Option(
            None,
            help="Optional agent home directory for AGENT.md/SOUL.md/USER.md/MEMORY.md.",
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
        display_name: str | None = typer.Option(
            None,
            help="Optional identity display name.",
        ),
        theme: str | None = typer.Option(None, help="Optional identity theme."),
        emoji: str | None = typer.Option(None, help="Optional identity emoji."),
        avatar: str | None = typer.Option(None, help="Optional identity avatar."),
        enabled: bool = typer.Option(True, "--enabled/--disabled"),
        requested_effect: list[str] = typer.Option(
            None,
            "--requested-effect",
            help="Effect id this agent prefers to use when available.",
        ),
        requested_tool: list[str] = typer.Option(
            None,
            "--requested-tool",
            help="Tool id this agent prefers to use when available.",
        ),
        preferred_tool_tag: list[str] = typer.Option(
            None,
            "--preferred-tool-tag",
            help="Tool tag this agent prefers when multiple tools fit.",
        ),
        prefers_background_tools: bool = typer.Option(
            True,
            "--prefers-background-tools/--no-prefers-background-tools",
            help="Whether this agent prefers background-capable tools.",
        ),
        prefers_mutating_tools: bool = typer.Option(
            True,
            "--prefers-mutating-tools/--no-prefers-mutating-tools",
            help="Whether this agent prefers mutating tools when available.",
        ),
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
                    home_dir=home_dir,
                    workdir=workdir,
                    workspace=workspace,
                    sandbox_mode=sandbox_mode,
                ),
                tool_preferences=AgentToolPreferences(
                    requested_effect_ids=tuple(requested_effect or ()),
                    requested_tool_ids=tuple(requested_tool or ()),
                    preferred_tags=tuple(preferred_tool_tag or ()),
                    prefers_background_tools=prefers_background_tools,
                    prefers_mutating_tools=prefers_mutating_tools,
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
        result = container.agent_service.migrate_profile_home(
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
        result = container.agent_service.sync_profile_home(
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
        result = container.agent_service.export_profile_home(
            ExportAgentHomeInput(id=agent_id, home_dir=home_dir),
        )
        echo_data(
            {
                "home_dir": result.home_dir,
                "path": result.path,
                "profile": AgentProfileDTO.from_entity(result.profile),
            },
        )

    return app
