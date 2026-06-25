from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class OperationsActionDependencies:
    events_service: Any
    channel_runtime_manager: Any
    daemon_manager: Any | None = None
    tool_service: Any | None = None
    llm_service: Any | None = None
    skill_manager: Any | None = None
    access_service: Any | None = None
    access_inventory_collector: Any | None = None
    webhook_channel_runtime_service: Any | None = None
    memory_runtime_service: Any | None = None
    orchestration_resume_service: Any | None = None
    orchestration_cancellation_service: Any | None = None


def required_dependency(value: Any, label: str) -> Any:
    if value is None:
        raise RuntimeError(f"Operations action dependency is not configured: {label}.")
    return value
