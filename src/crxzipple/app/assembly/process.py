"""Process module app assembly."""

from __future__ import annotations

from crxzipple.app.keys import AppKey
from crxzipple.app.plan import ApplicationFactory
from crxzipple.core.config import Settings
from crxzipple.modules.process import (
    FilesystemProcessSessionRepository,
    ProcessApplicationService,
    ProcessSupervisor,
    derive_process_store_root,
)


def process_factories() -> tuple[ApplicationFactory, ...]:
    """Build Process module-local application services."""

    return (
        ApplicationFactory(
            key="process.service",
            provides=(AppKey.PROCESS_SERVICE,),
            requires=(AppKey.CORE_SETTINGS,),
            build=_build_process_service,
        ),
    )


def _build_process_service(ctx) -> ProcessApplicationService:
    settings = ctx.require(AppKey.CORE_SETTINGS)
    return build_process_service(settings)


def build_process_service(settings: Settings) -> ProcessApplicationService:
    repository = FilesystemProcessSessionRepository(
        derive_process_store_root(settings.database_url),
    )
    return ProcessApplicationService(
        repository=repository,
        supervisor=ProcessSupervisor(repository),
    )


__all__ = ["build_process_service", "process_factories"]
