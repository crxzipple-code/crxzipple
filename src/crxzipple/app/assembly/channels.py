"""Channels module app assembly."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.app.keys import AppKey
from crxzipple.app.plan import ApplicationFactory, AssemblyTarget
from crxzipple.core.config import Settings
from crxzipple.modules.channels import (
    ChannelControlService,
    ChannelInteractionRegistry,
    ChannelInteractionService,
    ChannelProfileApplicationService,
    ChannelRuntimeManager,
    ChannelRuntimePlanner,
    ChannelRuntimeRegistry,
    ChannelStateRoot,
    ChannelSystemConfig,
    FileBackedChannelInteractionRegistryStore,
    FileBackedChannelRuntimeRegistryStore,
    FileBackedChannelSystemConfigStore,
    bootstrap_channel_state_root,
)


@dataclass(slots=True)
class ChannelInfrastructure:
    system_config: ChannelSystemConfig
    system_config_store: FileBackedChannelSystemConfigStore
    interaction_registry_store: FileBackedChannelInteractionRegistryStore
    runtime_registry_store: FileBackedChannelRuntimeRegistryStore
    state_root: ChannelStateRoot
    interaction_service: ChannelInteractionService
    profile_service: ChannelProfileApplicationService
    runtime_planner: ChannelRuntimePlanner
    runtime_manager: ChannelRuntimeManager


def channel_factories() -> tuple[ApplicationFactory, ...]:
    """Build channel profile/config and runtime registry applications."""

    return (
        ApplicationFactory(
            key="channels.infrastructure",
            provides=(
                AppKey.CHANNEL_INFRASTRUCTURE,
                AppKey.CHANNEL_PROFILE_SERVICE,
                AppKey.CHANNEL_RUNTIME_MANAGER,
            ),
            requires=(AppKey.CORE_SETTINGS,),
            build=_build_channel_infrastructure,
        ),
    )


def channel_control_factories() -> tuple[ApplicationFactory, ...]:
    """Build channel control integration with Daemon service specs."""

    return (
        ApplicationFactory(
            key="channels.control_service",
            provides=(AppKey.CHANNEL_CONTROL_SERVICE,),
            requires=(AppKey.CHANNEL_INFRASTRUCTURE, AppKey.DAEMON_SERVICE),
            build=_build_channel_control_service,
            targets=(
                AssemblyTarget.API,
                AssemblyTarget.CLI_ADMIN,
                AssemblyTarget.DAEMON_SUPERVISOR,
                AssemblyTarget.TEST,
            ),
        ),
    )


def _build_channel_infrastructure(ctx) -> ChannelInfrastructure:
    settings = ctx.require(AppKey.CORE_SETTINGS)
    infrastructure = build_channel_infrastructure(
        settings,
        channel_profiles=settings.channel_profiles,
    )
    return {
        AppKey.CHANNEL_INFRASTRUCTURE: infrastructure,
        AppKey.CHANNEL_PROFILE_SERVICE: infrastructure.profile_service,
        AppKey.CHANNEL_RUNTIME_MANAGER: infrastructure.runtime_manager,
    }


def _build_channel_control_service(ctx) -> ChannelControlService:
    infrastructure = ctx.require(AppKey.CHANNEL_INFRASTRUCTURE)
    return ChannelControlService(
        profile_service=infrastructure.profile_service,
        planner=infrastructure.runtime_planner,
        daemon_service=ctx.require(AppKey.DAEMON_SERVICE),
    )


def build_channel_infrastructure(
    settings: Settings,
    *,
    channel_profiles: tuple[Any, ...],
) -> ChannelInfrastructure:
    bootstrap_config = ChannelSystemConfig(profiles=channel_profiles)
    bootstrap_interactions = ChannelInteractionRegistry()
    bootstrap_registry = ChannelRuntimeRegistry()
    state_root = bootstrap_channel_state_root(
        settings.channels_state_dir,
        system_config=bootstrap_config,
        interaction_registry=bootstrap_interactions,
        runtime_registry=bootstrap_registry,
    )
    system_config_store = FileBackedChannelSystemConfigStore(
        state_root.root_dir,
        bootstrap_config=bootstrap_config,
    )
    interaction_registry_store = FileBackedChannelInteractionRegistryStore(
        state_root.root_dir,
        bootstrap_registry=bootstrap_interactions,
    )
    runtime_registry_store = FileBackedChannelRuntimeRegistryStore(
        state_root.root_dir,
        bootstrap_registry=bootstrap_registry,
    )
    interaction_service = ChannelInteractionService(
        registry_store=interaction_registry_store,
    )
    profile_service = ChannelProfileApplicationService(
        system_config_store=system_config_store,
    )
    for profile in channel_profiles:
        profile_service.upsert_profile(profile)
    runtime_planner = ChannelRuntimePlanner()
    runtime_manager = ChannelRuntimeManager(
        registry_store=runtime_registry_store,
    )
    return ChannelInfrastructure(
        system_config=profile_service.get_system_config(),
        system_config_store=system_config_store,
        interaction_registry_store=interaction_registry_store,
        runtime_registry_store=runtime_registry_store,
        state_root=state_root,
        interaction_service=interaction_service,
        profile_service=profile_service,
        runtime_planner=runtime_planner,
        runtime_manager=runtime_manager,
    )


__all__ = [
    "ChannelInfrastructure",
    "build_channel_infrastructure",
    "channel_control_factories",
    "channel_factories",
]
