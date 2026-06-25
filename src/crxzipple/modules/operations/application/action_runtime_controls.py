from __future__ import annotations

from typing import Any

from crxzipple.modules.llm.application import WarmupLlmProfileInput
from crxzipple.modules.operations.application.action_dependencies import (
    required_dependency,
)


def run_daemon_service_action(
    daemon_manager: Any,
    *,
    service_key: str,
    action: str,
) -> tuple[Any, ...]:
    manager = required_dependency(daemon_manager, "daemon manager")
    normalized_action = str(action or "").strip().lower()
    if normalized_action == "ensure":
        return tuple(manager.ensure_service(service_key))
    if normalized_action == "healthcheck":
        return tuple(manager.healthcheck_service(service_key))
    if normalized_action == "reconcile":
        return tuple(manager.reconcile_service(service_key))
    if normalized_action == "stop":
        return tuple(manager.stop_service(service_key))
    raise ValueError(f"Unsupported daemon service action: {action}")


def cancel_tool_run(tool_service: Any, *, run_id: str) -> Any:
    return required_dependency(
        tool_service,
        "tool run control service",
    ).cancel_tool_run(run_id)


async def retry_tool_run(tool_service: Any, *, run_id: str) -> Any:
    return await required_dependency(
        tool_service,
        "tool run control service",
    ).retry_tool_run(run_id)


def warmup_llm_profile(llm_service: Any, *, llm_id: str) -> Any:
    return required_dependency(
        llm_service,
        "llm service",
    ).warmup_profile(WarmupLlmProfileInput(llm_id=llm_id))


def prune_expired_tool_workers(
    tool_service: Any,
    *,
    retention_seconds: int,
) -> dict[str, Any]:
    return dict(
        required_dependency(
            tool_service,
            "tool run control service",
        ).prune_expired_workers(retention_seconds=retention_seconds),
    )


def replay_channel_dead_letter(
    webhook_channel_runtime_service: Any,
    *,
    channel_type: str,
    runtime_id: str | None = None,
    cursor: str | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    if channel_type.strip().lower() != "webhook":
        raise ValueError(
            "Dead-letter replay no longer requeues generic legacy outbound events. "
            "Use the owning channel runtime replay path.",
        )
    return dict(
        required_dependency(
            webhook_channel_runtime_service,
            "webhook channel runtime service",
        ).replay_dead_letter_record(
            runtime_id=runtime_id,
            cursor=cursor,
            event_id=event_id,
        ),
    )
