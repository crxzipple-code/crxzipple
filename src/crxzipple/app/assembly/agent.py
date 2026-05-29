"""Agent module app assembly."""

from __future__ import annotations

from crxzipple.app.keys import AppKey
from crxzipple.app.plan import ActivationTask, ApplicationFactory, AssemblyTarget
from crxzipple.modules.agent.application import (
    AgentApplicationService,
    agent_profile_inputs_from_settings,
)
from crxzipple.modules.agent.infrastructure import (
    apply_agent_home_config_payload,
    derive_agent_home_root,
    ensure_agent_home_scaffold,
    list_registered_agent_homes,
    load_agent_home_config,
    migrate_agent_home_contents,
    profile_from_agent_home_config_payload,
    read_agent_home_files,
    register_agent_home,
    resolve_registered_agent_home,
    unregister_agent_home,
    write_agent_home_config,
    write_agent_home_files,
)


def agent_factories() -> tuple[ApplicationFactory, ...]:
    """Build the Agent module application service."""

    return (
        ApplicationFactory(
            key="agent.service",
            provides=(AppKey.AGENT_SERVICE,),
            requires=(AppKey.CORE_SETTINGS, AppKey.UNIT_OF_WORK_FACTORY),
            build=_build_agent_service,
        ),
    )


def agent_activation_tasks() -> tuple[ActivationTask, ...]:
    """Bootstrap configured agent profiles after the service is built."""

    return (
        ActivationTask(
            key="agent.bootstrap_profiles",
            requires=(AppKey.CORE_SETTINGS, AppKey.AGENT_SERVICE),
            run=_bootstrap_agent_profiles,
            targets=(
                AssemblyTarget.API,
                AssemblyTarget.CLI_ADMIN,
                AssemblyTarget.DAEMON_SUPERVISOR,
                AssemblyTarget.TEST,
            ),
        ),
    )


def _build_agent_service(ctx) -> AgentApplicationService:
    settings = ctx.require(AppKey.CORE_SETTINGS)
    uow_factory = ctx.require(AppKey.UNIT_OF_WORK_FACTORY)
    return AgentApplicationService(
        uow_factory,
        agent_home_root=str(derive_agent_home_root(settings.database_url)),
        home_scaffolder=ensure_agent_home_scaffold,
        home_migrator=migrate_agent_home_contents,
        home_config_loader=load_agent_home_config,
        home_config_writer=lambda profile, home_dir: write_agent_home_config(
            profile,
            home_dir=home_dir,
        ),
        home_config_applier=lambda profile, payload, home_dir: (
            apply_agent_home_config_payload(
                profile,
                payload,
                home_dir=home_dir,
            )
        ),
        home_profile_factory=lambda payload, home_dir: (
            profile_from_agent_home_config_payload(payload, home_dir=home_dir)
        ),
        home_registry_lister=lambda root_dir: list_registered_agent_homes(root_dir),
        home_registry_resolver=lambda root_dir, agent_id: resolve_registered_agent_home(
            root_dir,
            agent_id,
        ),
        home_registry_writer=lambda root_dir, agent_id, home_dir: register_agent_home(
            root_dir,
            agent_id=agent_id,
            home_dir=home_dir,
        ),
        home_registry_remover=lambda root_dir, agent_id: unregister_agent_home(
            root_dir,
            agent_id=agent_id,
        ),
        home_file_reader=read_agent_home_files,
        home_file_writer=write_agent_home_files,
    )


def _bootstrap_agent_profiles(ctx) -> None:
    settings = ctx.require(AppKey.CORE_SETTINGS)
    service = ctx.require(AppKey.AGENT_SERVICE)
    profile_inputs = agent_profile_inputs_from_settings(settings.agent_profiles)
    service.sync_profiles(profile_inputs, write_home="if_missing")


__all__ = ["agent_activation_tasks", "agent_factories"]
