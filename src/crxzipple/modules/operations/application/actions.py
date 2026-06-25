from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.operations.application.action_dependencies import (
    OperationsActionDependencies,
)
from crxzipple.modules.operations.application.action_channel_runtimes import (
    DEFAULT_STALE_CHANNEL_RUNTIME_AFTER_SECONDS,
    prune_stale_channel_runtimes as _prune_stale_channel_runtimes,
)
from crxzipple.modules.operations.application.action_event_subscriptions import (
    DEFAULT_STUCK_SUBSCRIPTION_AFTER_SECONDS,
    advance_event_subscriptions_to_head as _advance_event_subscriptions_to_head,
)
from crxzipple.modules.operations.application.action_results import (
    ChannelRuntimePruneResult,
    EventSubscriptionAdvanceResult,
)
from crxzipple.modules.operations.application import (
    action_orchestration_controls as _orchestration_controls,
    action_resource_controls as _resource_controls,
    action_runtime_controls as _runtime_controls,
)


@dataclass(slots=True)
class OperationsActionService:
    deps: OperationsActionDependencies

    def advance_event_subscriptions_to_head(
        self,
        *,
        subscription_id: str | None = None,
        source_topic: str | None = None,
        status: str = "stuck",
        observer_only: bool = False,
        stuck_after_seconds: float = DEFAULT_STUCK_SUBSCRIPTION_AFTER_SECONDS,
        dry_run: bool = False,
        reason: str | None = None,
    ) -> EventSubscriptionAdvanceResult:
        return _advance_event_subscriptions_to_head(
            self.deps.events_service,
            subscription_id=subscription_id,
            source_topic=source_topic,
            status=status,
            observer_only=observer_only,
            stuck_after_seconds=stuck_after_seconds,
            dry_run=dry_run,
            reason=reason,
        )

    def prune_stale_channel_runtimes(
        self,
        *,
        runtime_id: str | None = None,
        channel_type: str | None = None,
        stale_after_seconds: float = DEFAULT_STALE_CHANNEL_RUNTIME_AFTER_SECONDS,
        dry_run: bool = False,
        reason: str | None = None,
    ) -> ChannelRuntimePruneResult:
        return _prune_stale_channel_runtimes(
            self.deps.channel_runtime_manager,
            runtime_id=runtime_id,
            channel_type=channel_type,
            stale_after_seconds=stale_after_seconds,
            dry_run=dry_run,
            reason=reason,
        )

    def run_daemon_service_action(
        self,
        *,
        service_key: str,
        action: str,
        reason: str,
    ) -> tuple[Any, ...]:
        del reason
        return _runtime_controls.run_daemon_service_action(
            self.deps.daemon_manager,
            service_key=service_key,
            action=action,
        )

    def cancel_tool_run(self, *, run_id: str, reason: str | None = None) -> Any:
        del reason
        return _runtime_controls.cancel_tool_run(
            self.deps.tool_service,
            run_id=run_id,
        )

    async def retry_tool_run(self, *, run_id: str, reason: str | None = None) -> Any:
        del reason
        return await _runtime_controls.retry_tool_run(
            self.deps.tool_service,
            run_id=run_id,
        )

    def warmup_llm_profile(self, *, llm_id: str, reason: str | None = None) -> Any:
        del reason
        return _runtime_controls.warmup_llm_profile(
            self.deps.llm_service,
            llm_id=llm_id,
        )

    def prune_expired_tool_workers(
        self,
        *,
        retention_seconds: int = 3600,
        reason: str | None = None,
    ) -> dict[str, Any]:
        del reason
        return _runtime_controls.prune_expired_tool_workers(
            self.deps.tool_service,
            retention_seconds=retention_seconds,
        )

    def replay_channel_dead_letter(
        self,
        *,
        channel_type: str,
        runtime_id: str | None = None,
        cursor: str | None = None,
        event_id: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        del reason
        return _runtime_controls.replay_channel_dead_letter(
            self.deps.webhook_channel_runtime_service,
            channel_type=channel_type,
            runtime_id=runtime_id,
            cursor=cursor,
            event_id=event_id,
        )

    def validate_skill_package(self, *, path: str, reason: str | None = None) -> Any:
        del reason
        return _resource_controls.validate_skill_package(
            self.deps.skill_manager,
            path=path,
        )

    def install_global_skill(self, *, source_dir: str, reason: str | None = None) -> Any:
        del reason
        return _resource_controls.install_global_skill(
            self.deps.skill_manager,
            source_dir=source_dir,
        )

    def sync_skills(
        self,
        *,
        workspace_dir: str | None = None,
        source_id: str | None = None,
        surface: str = "interactive",
        reason: str | None = None,
    ) -> Any:
        del reason
        return _resource_controls.sync_skills(
            self.deps.skill_manager,
            workspace_dir=workspace_dir,
            source_id=source_id,
            surface=surface,
        )

    def collect_access_inventory(
        self,
        *,
        workspace_dir: str | None = None,
        include_ready: bool = True,
        include_disabled: bool = False,
    ) -> dict[str, Any]:
        return _resource_controls.collect_access_inventory(
            self.deps.access_inventory_collector,
            workspace_dir=workspace_dir,
            include_ready=include_ready,
            include_disabled=include_disabled,
        )

    def check_access_readiness(
        self,
        *,
        requirements: list[str],
        credential_bindings: list[str],
        workspace_dir: str | None = None,
        allow_literal_credentials: bool = False,
    ) -> list[tuple[str, Any]]:
        return _resource_controls.check_access_readiness(
            self.deps.access_service,
            requirements=requirements,
            credential_bindings=credential_bindings,
            workspace_dir=workspace_dir,
            allow_literal_credentials=allow_literal_credentials,
        )

    def begin_access_setup(
        self,
        *,
        target: str,
        workspace_dir: str | None = None,
    ) -> Any:
        return _resource_controls.begin_access_setup(
            self.deps.access_service,
            target=target,
            workspace_dir=workspace_dir,
        )

    def write_long_term_memory(
        self,
        *,
        agent_id: str,
        content: str,
        reason: str | None = None,
    ) -> Any:
        return _resource_controls.write_long_term_memory(
            self.deps.memory_runtime_service,
            agent_id=agent_id,
            content=content,
            reason=reason,
        )

    def cancel_orchestration_run(
        self,
        *,
        run_id: str,
        reason: str | None = None,
    ) -> Any:
        return _orchestration_controls.cancel_orchestration_run(
            self.deps.orchestration_cancellation_service,
            run_id=run_id,
            reason=reason,
        )

    def resume_orchestration_run(
        self,
        *,
        run_id: str,
        reason: str | None = None,
    ) -> Any:
        return _orchestration_controls.resume_orchestration_run(
            self.deps.orchestration_resume_service,
            run_id=run_id,
            reason=reason,
        )
