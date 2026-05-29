"""Runtime assembly plans for application entrypoints."""

from __future__ import annotations

from crxzipple.app.assembly.access import access_factories
from crxzipple.app.assembly.agent import agent_activation_tasks, agent_factories
from crxzipple.app.assembly.artifacts import artifact_factories
from crxzipple.app.assembly.authorization import authorization_factories
from crxzipple.app.assembly.browser import browser_factories
from crxzipple.app.assembly.channels import (
    channel_control_factories,
    channel_factories,
)
from crxzipple.app.assembly.channel_runtime import (
    channel_runtime_activation_tasks,
    channel_runtime_factories,
)
from crxzipple.app.assembly.daemon import (
    daemon_activation_tasks,
    daemon_factories,
    daemon_manager_factories,
)
from crxzipple.app.assembly.database import database_factories
from crxzipple.app.assembly.dispatch import dispatch_factories
from crxzipple.app.assembly.event_runtime import event_runtime_factories
from crxzipple.app.assembly.events import events_factories
from crxzipple.app.assembly.lifecycle import runtime_lifecycle_factories
from crxzipple.app.assembly.llm import llm_factories
from crxzipple.app.assembly.memory import (
    memory_context_factories,
    memory_factories,
)
from crxzipple.app.assembly.mobile import mobile_factories
from crxzipple.app.assembly.ocr import ocr_factories
from crxzipple.app.assembly.operations import operations_factories
from crxzipple.app.assembly.orchestration import orchestration_factories
from crxzipple.app.assembly.process import process_factories
from crxzipple.app.assembly.runtime_defaults import runtime_defaults_factories
from crxzipple.app.assembly.session import session_factories
from crxzipple.app.assembly.session_runtime import session_runtime_factories
from crxzipple.app.assembly.settings import settings_factories
from crxzipple.app.assembly.skills import skills_activation_tasks, skills_factories
from crxzipple.app.assembly.tool import (
    TOOL_ORCHESTRATION_QUEUE_SERVICE_TARGETS,
    TOOL_QUEUE_SERVICE_TARGETS,
    tool_activation_tasks,
    tool_browser_activation_tasks,
    tool_core_factories,
    tool_execution_factories,
    tool_queue_factories,
)
from crxzipple.app.assembly.unit_of_work import unit_of_work_factories
from crxzipple.app.plan import ActivationTask, ApplicationFactory, AssemblyPlan


def runtime_module_local_factories(
    *,
    enable_memory_watchers: bool = False,
) -> tuple[ApplicationFactory, ...]:
    """Build ordinary module applications before cross-module composition."""

    return (
        database_factories()
        + settings_factories()
        + runtime_defaults_factories()
        + events_factories()
        + unit_of_work_factories()
        + access_factories()
        + authorization_factories()
        + agent_factories()
        + llm_factories()
        + session_factories()
        + dispatch_factories()
        + daemon_factories()
        + process_factories()
        + daemon_manager_factories()
        + artifact_factories()
        + skills_factories()
        + memory_factories(enable_watchers=enable_memory_watchers)
        + browser_factories()
        + ocr_factories()
        + mobile_factories()
        + channel_factories()
        + channel_control_factories()
        + tool_core_factories()
    )


def runtime_integration_factories() -> tuple[ApplicationFactory, ...]:
    """Build app-level compositions that span multiple modules."""

    return (
        memory_context_factories()
        + tool_queue_factories(targets=TOOL_QUEUE_SERVICE_TARGETS)
        + tool_queue_factories(
            targets=TOOL_ORCHESTRATION_QUEUE_SERVICE_TARGETS,
            provide_orchestration_port=True,
        )
        + tool_execution_factories()
        + orchestration_factories()
        + session_runtime_factories()
        + channel_runtime_factories()
        + operations_factories()
        + event_runtime_factories()
        + runtime_lifecycle_factories()
    )


def runtime_activation_tasks() -> tuple[ActivationTask, ...]:
    """Run idempotent app activation after the registry is fully built."""

    return (
        agent_activation_tasks()
        + skills_activation_tasks()
        + daemon_activation_tasks()
        + tool_activation_tasks()
        + tool_browser_activation_tasks()
        + channel_runtime_activation_tasks()
    )


def runtime_plan(
    *,
    enable_memory_watchers: bool = False,
) -> AssemblyPlan:
    """Return the full runtime assembly plan used by app entrypoints."""

    return AssemblyPlan(
        module_local_factories=runtime_module_local_factories(
            enable_memory_watchers=enable_memory_watchers,
        ),
        integration_factories=runtime_integration_factories(),
        activation_tasks=runtime_activation_tasks(),
        metadata={"kind": "runtime"},
    )


__all__ = [
    "runtime_activation_tasks",
    "runtime_integration_factories",
    "runtime_module_local_factories",
    "runtime_plan",
]
