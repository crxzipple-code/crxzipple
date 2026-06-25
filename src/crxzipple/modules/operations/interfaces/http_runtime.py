from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.modules.operations.interfaces.http_models import (
    OperationsRuntimeStatusItemResponse,
    OperationsRuntimeStatusResponse,
)


def _runtime_status(container: AppContainer) -> OperationsRuntimeStatusResponse:
    database, migration = _database_runtime_status(container)
    events = _events_runtime_status(container)
    return OperationsRuntimeStatusResponse(
        updated_at=datetime.now(timezone.utc).isoformat(),
        checks=[database, events, migration],
    )


def _database_runtime_status(
    container: AppContainer,
) -> tuple[OperationsRuntimeStatusItemResponse, OperationsRuntimeStatusItemResponse]:
    settings = container.require(AppKey.CORE_SETTINGS)
    url = settings.database_url
    database_value = _database_label(url)
    database_details = _safe_url(url)
    migration_value = "unknown"
    migration_status = "unknown"
    migration_tone = "warning"
    try:
        with container.require(AppKey.DATABASE_ENGINE).connect() as connection:
            dialect = connection.dialect.name
            driver = connection.dialect.driver
            connection.execute(text("select 1"))
            try:
                version = connection.execute(
                    text("select version_num from alembic_version"),
                ).scalar_one_or_none()
            except SQLAlchemyError:
                version = None
            migration_value = str(version or "uninitialized")
            migration_status = "current" if version else "uninitialized"
            migration_tone = "success" if version else "warning"
    except SQLAlchemyError as exc:
        return (
            OperationsRuntimeStatusItemResponse(
                id="database",
                label="Database",
                value=database_value,
                status="unreachable",
                tone="danger",
                details=f"{database_details}; {exc}",
            ),
            OperationsRuntimeStatusItemResponse(
                id="migration",
                label="Migration",
                value="unknown",
                status="unknown",
                tone="danger",
                details="Database is unreachable.",
            ),
        )

    if url.startswith("sqlite"):
        database_status = "sqlite"
        database_tone = "warning"
    else:
        database_status = "connected"
        database_tone = "success"
    return (
        OperationsRuntimeStatusItemResponse(
            id="database",
            label="Database",
            value=database_value,
            status=database_status,
            tone=database_tone,
            details=f"{database_details}; dialect={dialect}; driver={driver}",
        ),
        OperationsRuntimeStatusItemResponse(
            id="migration",
            label="Migration",
            value=migration_value,
            status=migration_status,
            tone=migration_tone,
            details="alembic_version",
        ),
    )


def _events_runtime_status(
    container: AppContainer,
) -> OperationsRuntimeStatusItemResponse:
    settings = container.require(AppKey.CORE_SETTINGS)
    if settings.events_backend != "redis":
        return OperationsRuntimeStatusItemResponse(
            id="events",
            label="Events",
            value=settings.events_backend,
            status="file",
            tone="warning",
            details=settings.events_state_dir,
        )
    url = settings.events_redis_url or ""
    try:
        from redis import Redis
        from redis.exceptions import RedisError

        client = Redis.from_url(url, decode_responses=True)
        client.ping()
    except (ImportError, RedisError, ValueError) as exc:
        return OperationsRuntimeStatusItemResponse(
            id="events",
            label="Events",
            value="redis",
            status="unreachable",
            tone="danger",
            details=f"{_safe_url(url)}; {exc}",
        )
    return OperationsRuntimeStatusItemResponse(
        id="events",
        label="Events",
        value="redis",
        status="connected",
        tone="success",
        details=f"{_safe_url(url)}; prefix={settings.events_redis_key_prefix}",
    )


def _database_label(database_url: str) -> str:
    if database_url.startswith("postgresql"):
        return "PostgreSQL"
    if database_url.startswith("sqlite"):
        return "SQLite"
    try:
        return make_url(database_url).get_backend_name()
    except Exception:
        return database_url.split(":", 1)[0] or "unknown"


def _safe_url(url: str) -> str:
    if not url:
        return "-"
    try:
        return make_url(url).render_as_string(hide_password=True)
    except Exception:
        return url
