from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from crxzipple.core.config import Settings


ALLOW_SQLITE_RUNTIME_FALLBACK_ENV = "APP_ALLOW_SQLITE_RUNTIME_FALLBACK"
ALLOW_FILE_EVENTS_RUNTIME_FALLBACK_ENV = "APP_ALLOW_FILE_EVENTS_RUNTIME_FALLBACK"
ALLOW_SQLITE_MEMORY_INDEX_RUNTIME_ENV = "APP_ALLOW_SQLITE_MEMORY_INDEX_RUNTIME"


class RuntimeDatabaseGuardError(RuntimeError):
    """Raised when a long-running runtime is pointed at SQLite by default."""


class RuntimeEventsBackendGuardError(RuntimeError):
    """Raised when a shared runtime is pointed at a local events backend."""


class RuntimeMemoryIndexGuardError(RuntimeError):
    """Raised when production runtime has not acknowledged the local memory index."""


def is_sqlite_database_url(database_url: str) -> bool:
    return urlsplit(database_url).scheme.startswith("sqlite")


def require_runtime_database(settings: "Settings", *, runtime_name: str) -> None:
    if not is_sqlite_database_url(settings.database_url):
        return
    if settings.allow_sqlite_runtime_fallback:
        return
    raise RuntimeDatabaseGuardError(
        f"Refusing to start {runtime_name} with SQLite. "
        "Source `scripts/dev/infra-env.sh` or set APP_DATABASE_URL to Postgres. "
        f"For an explicit one-off SQLite fallback, set {ALLOW_SQLITE_RUNTIME_FALLBACK_ENV}=1.",
    )


def require_shared_events_backend(settings: "Settings", *, runtime_name: str) -> None:
    if settings.events_backend == "redis":
        return
    if settings.allow_file_events_runtime_fallback:
        return
    raise RuntimeEventsBackendGuardError(
        f"Refusing to start {runtime_name} with {settings.events_backend!r} "
        "events backend. Shared runtime services require Redis events. "
        "Source `scripts/dev/infra-env.sh` or set APP_EVENTS_BACKEND=redis. "
        "For an explicit one-off file events fallback, set "
        f"{ALLOW_FILE_EVENTS_RUNTIME_FALLBACK_ENV}=1.",
    )


def require_production_memory_index_acknowledgement(
    settings: "Settings",
    *,
    runtime_name: str,
) -> None:
    if settings.environment.strip().lower() not in {"prod", "production"}:
        return
    if settings.allow_sqlite_memory_index_runtime:
        return
    raise RuntimeMemoryIndexGuardError(
        f"Refusing to start {runtime_name} in production without explicit Memory "
        "SQLite index acknowledgement. Current Memory retrieval uses a local "
        "SQLite FTS/vector-cache index under APP_MEMORY_STORAGE_ROOT; confirm this "
        "is the intended production index mode by setting "
        f"{ALLOW_SQLITE_MEMORY_INDEX_RUNTIME_ENV}=1.",
    )
