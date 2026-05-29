"""Skills module app assembly."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from crxzipple.app.keys import AppKey
from crxzipple.app.plan import ActivationTask, ApplicationFactory
from crxzipple.app.integration.skill_prompt_resolution import (
    SkillAccessServiceAdapter,
    SkillAuthorizationServiceAdapter,
    SkillToolSourceQueryAdapter,
)
from crxzipple.modules.events import EventsApplicationService
from crxzipple.modules.skills import FilesystemSkillRepository, SkillManager
from crxzipple.modules.skills.application import (
    SkillPromptResolver,
    skill_event_from_payload,
)
from crxzipple.modules.skills.domain import SkillSourceStatus, SkillSourceType
from crxzipple.modules.skills.infrastructure import (
    FilesystemSkillSourceRoot,
    SqlAlchemySkillOwnerCatalogRepository,
)

SkillRepositoryFactory = Callable[[], Any]


def skills_factories(
    *,
    repository_factory: SkillRepositoryFactory | None = None,
) -> tuple[ApplicationFactory, ...]:
    """Build Skills module-local catalog/read/installation service."""

    factory = repository_factory or FilesystemSkillRepository
    return (
        ApplicationFactory(
            key="skills.manager",
            provides=(AppKey.SKILL_MANAGER,),
            build=lambda ctx: _build_skill_manager(ctx, factory),
        ),
    )


def skills_activation_tasks() -> tuple[ActivationTask, ...]:
    return (
        ActivationTask(
            key="skills.bind_runtime_readiness",
            requires=(
                AppKey.SKILL_MANAGER,
                AppKey.TOOL_SOURCE_QUERY_SERVICE,
            ),
            run=_bind_runtime_readiness,
        ),
    )


def _build_skill_manager(
    ctx,
    repository_factory: SkillRepositoryFactory,
):
    events_service = (
        ctx.require(AppKey.EVENTS_SERVICE) if ctx.has(AppKey.EVENTS_SERVICE) else None
    )
    owner_catalog_repository = (
        SqlAlchemySkillOwnerCatalogRepository(
            ctx.require(AppKey.DATABASE_SESSION_FACTORY),
        )
        if ctx.has(AppKey.DATABASE_SESSION_FACTORY)
        else None
    )
    return SkillManager(
        repository=_build_skill_repository(
            repository_factory,
            owner_catalog_repository,
        ),
        owner_catalog_repository=owner_catalog_repository,
        event_emitter=build_skill_event_emitter(events_service),
        prompt_resolver=_build_skill_prompt_resolver(ctx),
    )


def _build_skill_prompt_resolver(ctx) -> SkillPromptResolver:
    return SkillPromptResolver(
        access_port=(
            SkillAccessServiceAdapter(ctx.require(AppKey.ACCESS_SERVICE))
            if ctx.has(AppKey.ACCESS_SERVICE)
            else None
        ),
        authorization_port=(
            SkillAuthorizationServiceAdapter(ctx.require(AppKey.AUTHORIZATION_SERVICE))
            if ctx.has(AppKey.AUTHORIZATION_SERVICE)
            else None
        ),
    )


def _bind_runtime_readiness(ctx) -> None:
    skill_manager = ctx.require(AppKey.SKILL_MANAGER)
    skill_manager.configure_runtime_readiness(
        tool_readiness_port=SkillToolSourceQueryAdapter(
            ctx.require(AppKey.TOOL_SOURCE_QUERY_SERVICE),
        ),
    )


def _build_skill_repository(
    repository_factory: SkillRepositoryFactory,
    owner_catalog_repository: SqlAlchemySkillOwnerCatalogRepository | None,
):
    if repository_factory is FilesystemSkillRepository:
        return FilesystemSkillRepository(
            source_provider=_build_filesystem_source_provider(
                owner_catalog_repository,
            ),
        )
    return repository_factory()


def _build_filesystem_source_provider(
    owner_catalog_repository: SqlAlchemySkillOwnerCatalogRepository | None,
):
    if owner_catalog_repository is None:
        return None

    def provide() -> tuple[FilesystemSkillSourceRoot, ...]:
        sources: list[FilesystemSkillSourceRoot] = []
        for source in owner_catalog_repository.list_sources():
            if source.source_id in {"workspace", "global", "system"}:
                continue
            if source.status is SkillSourceStatus.DELETED:
                continue
            if not source.enabled:
                continue
            if source.source_type not in (
                SkillSourceType.MANAGED,
                SkillSourceType.EXTERNAL,
            ):
                continue
            sources.append(
                FilesystemSkillSourceRoot(
                    source_id=source.source_id,
                    root_path=source.root_uri,
                ),
            )
        return tuple(sources)

    return provide


def build_skill_event_emitter(events_service: EventsApplicationService | None):
    if not isinstance(events_service, EventsApplicationService):
        return None

    def emit(event_name: str, payload: dict[str, object]) -> None:
        events_service.publish(skill_event_from_payload(event_name, payload))

    return emit


__all__ = [
    "build_skill_event_emitter",
    "skills_activation_tasks",
    "skills_factories",
]
