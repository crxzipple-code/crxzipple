from __future__ import annotations

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.modules.access.interfaces.inventory import collect_access_inventory
from crxzipple.modules.operations.application.action_dependencies import (
    OperationsActionDependencies,
)
from crxzipple.modules.operations.application.actions import OperationsActionService


def operations_action_service(container: AppContainer) -> OperationsActionService:
    return OperationsActionService(
        deps=OperationsActionDependencies(
            events_service=container.require(AppKey.EVENTS_SERVICE),
            channel_runtime_manager=container.require(AppKey.CHANNEL_RUNTIME_MANAGER),
            daemon_manager=container.require(AppKey.DAEMON_MANAGER),
            tool_service=container.require(AppKey.TOOL_RUN_CONTROL_SERVICE),
            llm_service=container.require(AppKey.LLM_SERVICE),
            skill_manager=container.require(AppKey.SKILL_MANAGER),
            access_service=container.require(AppKey.ACCESS_SERVICE),
            access_inventory_collector=lambda **kwargs: collect_access_inventory(
                container,
                **kwargs,
            ),
            webhook_channel_runtime_service=container.require(
                AppKey.WEBHOOK_CHANNEL_RUNTIME_SERVICE
            ),
            memory_runtime_service=container.require(AppKey.MEMORY_RUNTIME_SERVICE),
            orchestration_resume_service=container.require(
                AppKey.ORCHESTRATION_SCHEDULER_MAINTENANCE_SERVICE,
            ),
            orchestration_cancellation_service=container.require(
                AppKey.ORCHESTRATION_CANCELLATION_SERVICE
            ),
        ),
    )
