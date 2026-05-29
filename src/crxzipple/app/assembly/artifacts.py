"""Artifacts module app assembly."""

from __future__ import annotations

from crxzipple.app.keys import AppKey
from crxzipple.app.plan import ApplicationFactory
from crxzipple.modules.artifacts import (
    ArtifactApplicationService,
    FilesystemArtifactStore,
)


def artifact_factories() -> tuple[ApplicationFactory, ...]:
    """Build Artifacts module-local application service."""

    return (
        ApplicationFactory(
            key="artifacts.service",
            provides=(AppKey.ARTIFACT_SERVICE,),
            requires=(AppKey.CORE_SETTINGS,),
            build=_build_artifact_service,
        ),
    )


def _build_artifact_service(ctx) -> ArtifactApplicationService:
    settings = ctx.require(AppKey.CORE_SETTINGS)
    return ArtifactApplicationService(
        FilesystemArtifactStore(settings.artifact_store_dir),
        preview_max_dimension=settings.artifact_image_preview_max_dimension,
        llm_max_dimension=settings.artifact_image_llm_max_dimension,
        llm_image_max_bytes=settings.artifact_image_llm_max_bytes,
    )


__all__ = ["artifact_factories"]
