"""Database and base settings assembly factories."""

from __future__ import annotations

from dataclasses import replace

from crxzipple.app.keys import AppKey
from crxzipple.app.plan import ApplicationFactory
from crxzipple.core.config import Settings, load_settings
from crxzipple.core.db import build_engine, build_session_factory


def database_factories() -> tuple[ApplicationFactory, ...]:
    """Build base settings, database engine and session factory."""

    return (
        ApplicationFactory(
            key="core.settings",
            provides=(AppKey.CORE_SETTINGS,),
            build=_build_settings,
        ),
        ApplicationFactory(
            key="database.engine",
            provides=(AppKey.DATABASE_ENGINE,),
            requires=(AppKey.CORE_SETTINGS,),
            build=lambda ctx: build_engine(ctx.require(AppKey.CORE_SETTINGS)),
        ),
        ApplicationFactory(
            key="database.session_factory",
            provides=(AppKey.DATABASE_SESSION_FACTORY,),
            requires=(AppKey.DATABASE_ENGINE,),
            build=lambda ctx: build_session_factory(ctx.require(AppKey.DATABASE_ENGINE)),
        ),
    )


def _build_settings(_ctx) -> Settings:
    return load_settings()


def settings_with_database_url(settings: Settings, database_url: str) -> Settings:
    """Return settings with an app-assembly supplied database URL."""

    return replace(settings, database_url=database_url)


__all__ = ["database_factories", "settings_with_database_url"]
