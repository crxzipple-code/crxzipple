from __future__ import annotations

import typer

from crxzipple.core.config import AgentProfileSettings
from crxzipple.interfaces.cli.context import AppKey, ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.agent.application import (
    ExportAgentHomeInput,
    MigrateAgentHomeInput,
    RegisterAgentProfileInput,
    SyncAgentHomeInput,
    UpdateAgentProfileInput,
)
from crxzipple.modules.agent.domain.exceptions import (
    AgentAlreadyExistsError,
    AgentNotFoundError,
    AgentValidationError,
)
from crxzipple.modules.agent.domain.value_objects import (
    AgentExecutionPolicy,
    AgentIdentity,
    AgentInstructionPolicy,
    AgentLlmRoutingPolicy,
    AgentMemoryBinding,
    AgentRuntimePreferences,
)
from crxzipple.modules.agent.interfaces.dto import AgentProfileDTO


def build_cli() -> typer.Typer:
    app = typer.Typer(help="Manage agent profiles.", no_args_is_help=True)

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
                RegisterAgentProfileInput(
                    id=agent_id,
                    name=name,
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
                    memory=AgentMemoryBinding(
                        enabled=memory_enabled,
                        scope_ref=memory_scope_ref,
                        access=memory_access,
                    ),
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
        updates: dict[str, object] = {}
        if name is not None:
            updates["name"] = name
        if default_llm_id is not None:
            updates["llm_routing_policy"] = AgentLlmRoutingPolicy(
                default_llm_id=default_llm_id,
            )
        if (
            memory_scope_ref is not None
            or memory_enabled is not None
            or memory_access is not None
        ):
            current = container.require(AppKey.AGENT_SERVICE).get_profile(agent_id)
            updates["memory"] = AgentMemoryBinding(
                enabled=(
                    memory_enabled
                    if memory_enabled is not None
                    else current.memory.enabled
                ),
                scope_ref=(
                    memory_scope_ref
                    if memory_scope_ref is not None
                    else current.memory.scope_ref
                ),
                access=memory_access or current.memory.access,
            )
        try:
            profile = container.require(AppKey.AGENT_SERVICE).update_profile(
                UpdateAgentProfileInput(id=agent_id, **updates),
            )
        except (AgentNotFoundError, AgentValidationError) as exc:
            raise typer.BadParameter(str(exc)) from exc
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
            for item in container.require(AppKey.CORE_SETTINGS).agent_profiles
            if not selected_ids or item.id in selected_ids
        )
        synced = container.require(AppKey.AGENT_SERVICE).sync_profiles(
            tuple(_profile_settings_to_input(item) for item in configured_profiles),
        )
        echo_data([AgentProfileDTO.from_entity(item) for item in synced])

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
            AgentProfileDTO.from_entity(container.require(AppKey.AGENT_SERVICE).get_profile(agent_id)),
        )

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
        echo_data(
            AgentProfileDTO.from_entity(profile),
        )

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
        echo_data(
            AgentProfileDTO.from_entity(profile),
        )

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

    return app


def _profile_settings_to_input(profile: AgentProfileSettings) -> RegisterAgentProfileInput:
    return RegisterAgentProfileInput(
        id=profile.id,
        name=profile.name,
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
        memory=AgentMemoryBinding.from_payload(profile.memory),
    )
