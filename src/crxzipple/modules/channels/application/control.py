from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.channels.domain import (
    ChannelAccountProfile,
    ChannelProfile,
    ChannelSystemConfig,
)
from crxzipple.modules.daemon.application import DaemonApplicationService
from crxzipple.modules.daemon.domain import DaemonServiceSpec

from .bindings import collect_channel_binding_env_vars
from .services import ChannelProfileApplicationService


def _title_case_channel(value: str) -> str:
    normalized = value.strip().replace("-", " ").replace("_", " ")
    return " ".join(part.capitalize() for part in normalized.split() if part) or "Channel"


def _is_retired_channel_type(channel_type: str) -> bool:
    return channel_type.strip().lower() in {"inbox"}


@dataclass(frozen=True, slots=True)
class ChannelRuntimePlan:
    channel_type: str
    service_key: str
    spec: DaemonServiceSpec


class ChannelRuntimePlanner:
    def build_plan(
        self,
        system_config: ChannelSystemConfig,
    ) -> tuple[ChannelRuntimePlan, ...]:
        plans: list[ChannelRuntimePlan] = []
        for profile in system_config.profiles:
            plan = self._build_profile_plan(profile)
            if plan is not None:
                plans.append(plan)
        return tuple(plans)

    def _build_profile_plan(
        self,
        profile: ChannelProfile,
    ) -> ChannelRuntimePlan | None:
        if not profile.enabled:
            return None
        enabled_accounts = tuple(account for account in profile.accounts if account.enabled)
        if not enabled_accounts:
            return None
        channel_type = profile.channel_type.strip().lower()
        if _is_retired_channel_type(channel_type):
            return None
        service_key = f"channel:{channel_type}"
        env_keys = self._profile_env_keys(profile, enabled_accounts)
        spec = DaemonServiceSpec(
            key=service_key,
            display_name=f"{_title_case_channel(channel_type)} Channel Runtime",
            service_group="channels",
            role="host",
            managed_by="internal",
            transport="process",
            replica_mode="singleton",
            desired_replicas=1,
            start_policy=self._profile_start_policy(profile, enabled_accounts),
            restart_policy="on-failure",
            metadata={
                "module": "channels",
                "managed_module": "channels.control",
                "managed_kind": "channel-runtime",
                "channel_type": channel_type,
                "accounts": [account.account_id for account in enabled_accounts],
                "env_keys": list(env_keys),
                "cli_args": [
                    "channel-runtime",
                    "run",
                    "--channel",
                    channel_type,
                    "--service-key",
                    service_key,
                ],
            },
        )
        return ChannelRuntimePlan(
            channel_type=channel_type,
            service_key=service_key,
            spec=spec,
        )

    def _profile_start_policy(
        self,
        profile: ChannelProfile,
        accounts: tuple[ChannelAccountProfile, ...],
    ) -> str:
        explicit = str(profile.metadata.get("start_policy") or "").strip().lower()
        if explicit in {"eager", "lazy", "attach-only", "ensure"}:
            return explicit
        transport_modes = {account.transport_mode.strip().lower() for account in accounts}
        if transport_modes & {"sse", "ws", "websocket", "poll", "webhook"}:
            return "eager"
        return "lazy"

    def _profile_env_keys(
        self,
        profile: ChannelProfile,
        accounts: tuple[ChannelAccountProfile, ...],
    ) -> tuple[str, ...]:
        resolved: list[str] = []
        for env_name in collect_channel_binding_env_vars(profile.metadata):
            if env_name not in resolved:
                resolved.append(env_name)
        for account in accounts:
            for env_name in collect_channel_binding_env_vars(account.metadata):
                if env_name not in resolved:
                    resolved.append(env_name)
        return tuple(sorted(resolved))


class ChannelControlService:
    def __init__(
        self,
        *,
        profile_service: ChannelProfileApplicationService,
        planner: ChannelRuntimePlanner,
        daemon_service: DaemonApplicationService,
    ) -> None:
        self.profile_service = profile_service
        self.planner = planner
        self.daemon_service = daemon_service

    def planned_runtime_specs(self) -> tuple[DaemonServiceSpec, ...]:
        return tuple(
            plan.spec
            for plan in self.planner.build_plan(self.profile_service.get_system_config())
        )

    def sync_daemon_specs(self) -> tuple[DaemonServiceSpec, ...]:
        planned = self.planned_runtime_specs()
        planned_keys = {spec.key for spec in planned}
        for spec in planned:
            self.daemon_service.register_service_spec(spec)
        self.daemon_service.remove_service_specs(
            lambda spec: (
                str(spec.metadata.get("managed_module") or "").strip().lower()
                == "channels.control"
                and spec.key not in planned_keys
            ),
        )
        return planned
