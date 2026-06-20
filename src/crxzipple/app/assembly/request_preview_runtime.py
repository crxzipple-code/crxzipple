"""Read-only runtime assembly for LLM request preview entrypoints."""

from __future__ import annotations

from typing import Any

from crxzipple.app.assembly.access import access_factories
from crxzipple.app.assembly.agent import agent_factories
from crxzipple.app.assembly.artifacts import artifact_factories
from crxzipple.app.assembly.authorization import authorization_factories
from crxzipple.app.assembly.context_workspace import (
    context_workspace_factories,
    context_workspace_integration_factories,
)
from crxzipple.app.assembly.database import database_factories
from crxzipple.app.assembly.dispatch import dispatch_factories
from crxzipple.app.assembly.llm import llm_factories
from crxzipple.app.assembly.memory import memory_context_factories, memory_factories
from crxzipple.app.assembly.orchestration import orchestration_factories
from crxzipple.app.assembly.runtime_defaults import runtime_defaults_factories
from crxzipple.app.assembly.session import session_factories
from crxzipple.app.assembly.settings import settings_factories
from crxzipple.app.assembly.skills import skills_factories
from crxzipple.app.assembly.tool import tool_request_preview_factories
from crxzipple.app.assembly.unit_of_work import unit_of_work_factories
from crxzipple.app.keys import AppKey
from crxzipple.app.plan import ApplicationFactory, AssemblyPlan
from crxzipple.modules.events import EventsApplicationService, FileBackedEventsBackend
from crxzipple.shared.infrastructure import EventsBackedEventBus


def request_preview_runtime_module_local_factories() -> tuple[ApplicationFactory, ...]:
    """Build owner/query services required to render a provider request."""

    return (
        database_factories()
        + settings_factories(seed_core_resources=False)
        + runtime_defaults_factories()
        + _request_preview_events_factories()
        + unit_of_work_factories()
        + access_factories(ensure_default_oauth_provider=False)
        + authorization_factories()
        + agent_factories()
        + llm_factories()
        + session_factories()
        + context_workspace_factories()
        + dispatch_factories()
        + artifact_factories()
        + skills_factories(persist_runtime_request_readiness=False)
        + memory_factories(enable_watchers=False)
        + tool_request_preview_factories()
    )


def request_preview_runtime_integration_factories() -> tuple[ApplicationFactory, ...]:
    """Build cross-module ports used by orchestration request preview."""

    return (
        memory_context_factories(create_missing_spaces=False)
        + orchestration_factories()
        + context_workspace_integration_factories()
    )


def request_preview_runtime_plan() -> AssemblyPlan:
    """Return the minimal read-only assembly plan for request preview."""

    return AssemblyPlan(
        module_local_factories=request_preview_runtime_module_local_factories(),
        integration_factories=request_preview_runtime_integration_factories(),
        activation_tasks=(),
        metadata={"kind": "request_preview_runtime"},
    )


def _request_preview_events_factories() -> tuple[ApplicationFactory, ...]:
    return (
        ApplicationFactory(
            key="events.preview_service",
            provides=(
                AppKey.EVENTS_BACKEND,
                AppKey.EVENTS_SERVICE,
                AppKey.EVENTS_BUS,
            ),
            requires=(AppKey.CORE_SETTINGS,),
            build=_build_request_preview_events_service,
        ),
    )


def _build_request_preview_events_service(ctx) -> dict[str, Any]:
    settings = ctx.require(AppKey.CORE_SETTINGS)
    backend = FileBackedEventsBackend(
        settings.events_state_dir,
        sync_writes=settings.events_file_sync_writes,
    )
    service = EventsApplicationService(backend)
    return {
        AppKey.EVENTS_BACKEND: backend,
        AppKey.EVENTS_SERVICE: service,
        AppKey.EVENTS_BUS: EventsBackedEventBus(service),
    }


__all__ = [
    "request_preview_runtime_integration_factories",
    "request_preview_runtime_module_local_factories",
    "request_preview_runtime_plan",
]
