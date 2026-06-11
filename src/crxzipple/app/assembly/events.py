"""Events module app assembly."""

from __future__ import annotations

from typing import Any

from crxzipple.app.keys import AppKey
from crxzipple.app.plan import ApplicationFactory, AssemblyTarget
from crxzipple.core.config import Settings
from crxzipple.modules.browser.application.event_contracts import (
    browser_event_definitions,
    browser_event_surfaces,
)
from crxzipple.modules.channels.application.event_contracts import (
    channel_event_definitions,
    channel_event_route_contracts,
    channel_event_surfaces,
    channel_event_topic_contracts,
)
from crxzipple.modules.access.application.event_contracts import (
    access_event_definitions,
    access_event_surfaces,
)
from crxzipple.modules.dispatch.application import dispatch_event_observers
from crxzipple.modules.dispatch.application.event_contracts import (
    dispatch_event_definitions,
    dispatch_event_surfaces,
    dispatch_event_topic_contracts,
)
from crxzipple.modules.events import (
    EventContractRegistry,
    EventsApplicationService,
    FileBackedEventsBackend,
    RedisEventsBackend,
    events_event_definitions,
    events_event_surfaces,
    events_event_topic_contracts,
)
from crxzipple.modules.events.infrastructure.outbox_publisher import (
    EventOutboxPublisherService,
)
from crxzipple.modules.memory.application.event_contracts import (
    memory_event_definitions,
    memory_event_surfaces,
)
from crxzipple.modules.operations.application.event_contracts import (
    operations_event_definitions,
    operations_event_surfaces,
)
from crxzipple.modules.orchestration.application import (
    orchestration_event_definitions,
    orchestration_event_observers,
    orchestration_event_surfaces,
)
from crxzipple.modules.orchestration.application.event_contracts import (
    orchestration_event_topic_contracts,
)
from crxzipple.modules.skills.application.event_contracts import (
    skill_event_definitions,
    skill_event_surfaces,
)
from crxzipple.shared import EventDefinitionRegistry
from crxzipple.shared.infrastructure import EventsBackedEventBus


def events_factories() -> tuple[ApplicationFactory, ...]:
    """Build event backend, service, bus and registries."""

    return (
        ApplicationFactory(
            key="events.service",
            provides=(
                AppKey.EVENTS_BACKEND,
                AppKey.EVENTS_SERVICE,
                AppKey.EVENTS_BUS,
            ),
            requires=(AppKey.CORE_SETTINGS,),
            build=_build_events_service,
        ),
        ApplicationFactory(
            key="events.registries",
            provides=(
                AppKey.EVENT_CONTRACT_REGISTRY,
                AppKey.EVENT_DEFINITION_REGISTRY,
            ),
            build=lambda _ctx: {
                AppKey.EVENT_CONTRACT_REGISTRY: build_event_contract_registry(),
                AppKey.EVENT_DEFINITION_REGISTRY: build_event_definition_registry(),
            },
        ),
        ApplicationFactory(
            key="events.outbox_publisher",
            provides=(AppKey.EVENT_OUTBOX_PUBLISHER_SERVICE,),
            requires=(AppKey.DATABASE_SESSION_FACTORY, AppKey.EVENTS_BUS),
            build=lambda ctx: EventOutboxPublisherService(
                session_factory=ctx.require(AppKey.DATABASE_SESSION_FACTORY),
                event_bus=ctx.require(AppKey.EVENTS_BUS),
            ),
            targets=(AssemblyTarget.EVENT_OUTBOX_PUBLISHER, AssemblyTarget.TEST),
        ),
    )


def _build_events_service(ctx) -> dict[str, Any]:
    settings = ctx.require(AppKey.CORE_SETTINGS)
    backend = build_events_backend(settings)
    service = EventsApplicationService(backend)
    return {
        AppKey.EVENTS_BACKEND: backend,
        AppKey.EVENTS_SERVICE: service,
        AppKey.EVENTS_BUS: EventsBackedEventBus(service),
    }


def build_events_backend(settings: Settings):
    if settings.events_backend == "redis":
        return RedisEventsBackend(
            settings.events_redis_url,
            key_prefix=settings.events_redis_key_prefix,
            block_ms=settings.events_redis_block_ms,
            dedupe_ttl_seconds=settings.events_redis_dedupe_ttl_seconds,
        )
    return FileBackedEventsBackend(
        settings.events_state_dir,
        sync_writes=settings.events_file_sync_writes,
    )


def build_event_contract_registry() -> EventContractRegistry:
    registry = EventContractRegistry()
    registry.register_topics(events_event_topic_contracts())
    registry.register_topics(orchestration_event_topic_contracts())
    registry.register_topics(dispatch_event_topic_contracts())
    registry.register_topics(channel_event_topic_contracts())
    registry.register_routes(channel_event_route_contracts())
    return registry


def build_event_definition_registry() -> EventDefinitionRegistry:
    registry = EventDefinitionRegistry()
    registry.register_many(events_event_definitions())
    registry.register_surfaces(events_event_surfaces())
    registry.register_many(dispatch_event_definitions())
    registry.register_surfaces(dispatch_event_surfaces())
    registry.register_observers(dispatch_event_observers())
    registry.register_many(orchestration_event_definitions())
    registry.register_surfaces(orchestration_event_surfaces())
    registry.register_observers(orchestration_event_observers())
    registry.register_many(memory_event_definitions())
    registry.register_surfaces(memory_event_surfaces())
    registry.register_many(access_event_definitions())
    registry.register_surfaces(access_event_surfaces())
    registry.register_many(skill_event_definitions())
    registry.register_surfaces(skill_event_surfaces())
    registry.register_many(browser_event_definitions())
    registry.register_surfaces(browser_event_surfaces())
    registry.register_many(channel_event_definitions())
    registry.register_surfaces(channel_event_surfaces())
    registry.register_many(operations_event_definitions())
    registry.register_surfaces(operations_event_surfaces())
    return registry


__all__ = [
    "build_event_contract_registry",
    "build_event_definition_registry",
    "build_events_backend",
    "events_factories",
]
