"""Settings module app assembly."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine

from crxzipple.app.keys import AppKey
from crxzipple.app.plan import ApplicationFactory
from crxzipple.core.db import Base
from crxzipple.modules.settings.application import (
    SettingsEffectiveConfigMaterializer,
    seed_core_settings_resources,
)
from crxzipple.modules.settings.infrastructure.persistence import (
    SettingsActionAuditModel,
    SettingsEffectiveSnapshotModel,
    SettingsOverrideModel,
    SettingsResourceModel,
    SettingsResourceVersionModel,
    SettingsValidationResultModel,
    create_sqlalchemy_settings_services,
)


def settings_factories() -> tuple[ApplicationFactory, ...]:
    """Build Settings module-local services from the database session factory."""

    return (
        ApplicationFactory(
            key="settings.services",
            provides=(
                AppKey.SETTINGS_SERVICES,
                AppKey.SETTINGS_QUERY_SERVICE,
                AppKey.SETTINGS_ACTION_SERVICE,
                AppKey.SETTINGS_RESOLVER,
                AppKey.SETTINGS_MATERIALIZER,
                AppKey.SETTINGS_BOOTSTRAP_RESULT,
            ),
            requires=(
                AppKey.CORE_SETTINGS,
                AppKey.DATABASE_ENGINE,
                AppKey.DATABASE_SESSION_FACTORY,
            ),
            build=_build_settings_services,
        ),
    )


def _build_settings_services(ctx) -> dict[str, Any]:
    settings = ctx.require(AppKey.CORE_SETTINGS)
    engine = ctx.require(AppKey.DATABASE_ENGINE)
    session_factory = ctx.require(AppKey.DATABASE_SESSION_FACTORY)
    _ensure_settings_schema(engine)
    services = create_sqlalchemy_settings_services(session_factory)
    bootstrap_result = seed_core_settings_resources(settings, services=services)
    materializer = SettingsEffectiveConfigMaterializer(
        services.queries,
        environment=settings.environment,
    )
    return {
        AppKey.SETTINGS_SERVICES: services,
        AppKey.SETTINGS_QUERY_SERVICE: services.queries,
        AppKey.SETTINGS_ACTION_SERVICE: services.actions,
        AppKey.SETTINGS_RESOLVER: services.resolver,
        AppKey.SETTINGS_MATERIALIZER: materializer,
        AppKey.SETTINGS_BOOTSTRAP_RESULT: bootstrap_result,
    }


def _ensure_settings_schema(engine: Engine) -> None:
    _ = (
        SettingsActionAuditModel,
        SettingsEffectiveSnapshotModel,
        SettingsOverrideModel,
        SettingsResourceModel,
        SettingsResourceVersionModel,
        SettingsValidationResultModel,
    )
    Base.metadata.create_all(
        engine,
        tables=(
            SettingsResourceModel.__table__,
            SettingsResourceVersionModel.__table__,
            SettingsEffectiveSnapshotModel.__table__,
            SettingsOverrideModel.__table__,
            SettingsValidationResultModel.__table__,
            SettingsActionAuditModel.__table__,
        ),
    )


__all__ = ["settings_factories"]
