from __future__ import annotations

from threading import Lock
from urllib.parse import unquote

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from crxzipple.core.config import Settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


SessionFactory = sessionmaker[Session]

_SQLITE_WAL_INITIALIZATION_LOCK = Lock()
_SQLITE_WAL_INITIALIZED_DATABASES: set[str] = set()


def build_engine(settings: Settings) -> Engine:
    connect_args: dict[str, object] = {}
    engine_kwargs: dict[str, object] = {}
    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        connect_args["timeout"] = 30.0
        # Keep SQLite connections pooled. NullPool repeatedly opens/closes file
        # handles and can deadlock under concurrent executor tests on macOS.
        engine_kwargs["pool_pre_ping"] = True

    engine = create_engine(
        settings.database_url,
        connect_args=connect_args,
        **engine_kwargs,
    )
    if settings.database_url.startswith("sqlite"):
        _configure_sqlite_pragmas(engine, settings.database_url)
    return engine


def _configure_sqlite_pragmas(engine: Engine, database_url: str) -> None:
    file_backed = _is_file_backed_sqlite(database_url)
    database_identity = _sqlite_file_identity(database_url) if file_backed else None

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(
        dbapi_connection, _connection_record
    ) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA busy_timeout=30000")
            if file_backed and database_identity is not None:
                _ensure_sqlite_wal_mode(cursor, database_identity)
                cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()


def _is_file_backed_sqlite(database_url: str) -> bool:
    if database_url in {"sqlite://", "sqlite:///:memory:"}:
        return False
    if not database_url.startswith("sqlite:///"):
        return False
    path = database_url.removeprefix("sqlite:///").split("?", 1)[0]
    return bool(path and path != ":memory:")


def _sqlite_file_identity(database_url: str) -> str | None:
    if not _is_file_backed_sqlite(database_url):
        return None
    path = database_url.removeprefix("sqlite:///").split("?", 1)[0]
    if not path or path == ":memory:":
        return None
    return unquote(path)


def _ensure_sqlite_wal_mode(cursor, database_identity: str) -> None:  # noqa: ANN001
    with _SQLITE_WAL_INITIALIZATION_LOCK:
        if database_identity in _SQLITE_WAL_INITIALIZED_DATABASES:
            return
        cursor.execute("PRAGMA journal_mode=WAL")
        _SQLITE_WAL_INITIALIZED_DATABASES.add(database_identity)


def build_session_factory(engine: Engine) -> SessionFactory:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def import_models() -> None:
    from crxzipple.modules.access.infrastructure.persistence import (
        models as _access_models,
    )
    from crxzipple.modules.dispatch.infrastructure.persistence import (
        models as _dispatch_models,
    )
    from crxzipple.modules.authorization.infrastructure.persistence import (
        models as _authorization_models,
    )
    from crxzipple.modules.llm.infrastructure.persistence import models as _llm_models
    from crxzipple.modules.memory.infrastructure.persistence import (
        models as _memory_models,
    )
    from crxzipple.modules.orchestration.infrastructure.persistence import (
        models as _orchestration_models,
    )
    from crxzipple.modules.operations.infrastructure.persistence import (
        models as _operations_models,
    )
    from crxzipple.modules.session.infrastructure.persistence import (
        models as _session_models,
    )
    from crxzipple.modules.settings.infrastructure.persistence import (
        models as _settings_models,
    )
    from crxzipple.modules.skills.infrastructure.persistence import (
        models as _skills_models,
    )
    from crxzipple.modules.tool.infrastructure.persistence import models as _tool_models

    _ = (
        _access_models,
        _dispatch_models,
        _authorization_models,
        _llm_models,
        _memory_models,
        _orchestration_models,
        _operations_models,
        _session_models,
        _settings_models,
        _skills_models,
        _tool_models,
    )


def create_schema(engine: Engine) -> None:
    import_models()
    Base.metadata.create_all(engine)
