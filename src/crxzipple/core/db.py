from __future__ import annotations

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from crxzipple.core.config import Settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


SessionFactory = sessionmaker[Session]


def build_engine(settings: Settings) -> Engine:
    connect_args: dict[str, object] = {}
    engine_kwargs: dict[str, object] = {}
    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        connect_args["timeout"] = 30.0
        # File-based SQLite is a local-dev default here, so a null pool keeps
        # connections short-lived and avoids stale handles across CLI/tests.
        engine_kwargs["poolclass"] = NullPool

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

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA busy_timeout=30000")
            if file_backed:
                cursor.execute("PRAGMA journal_mode=WAL")
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


def build_session_factory(engine: Engine) -> SessionFactory:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def import_models() -> None:
    from crxzipple.modules.dispatch.infrastructure.persistence import (
        models as _dispatch_models,
    )
    from crxzipple.modules.authorization.infrastructure.persistence import (
        models as _authorization_models,
    )
    from crxzipple.modules.llm.infrastructure.persistence import models as _llm_models
    from crxzipple.modules.orchestration.infrastructure.persistence import (
        models as _orchestration_models,
    )
    from crxzipple.modules.operations.infrastructure.persistence import (
        models as _operations_models,
    )
    from crxzipple.modules.session.infrastructure.persistence import (
        models as _session_models,
    )
    from crxzipple.modules.tool.infrastructure.persistence import models as _tool_models

    _ = (
        _dispatch_models,
        _authorization_models,
        _llm_models,
        _orchestration_models,
        _operations_models,
        _session_models,
        _tool_models,
    )


def create_schema(engine: Engine) -> None:
    import_models()
    Base.metadata.create_all(engine)
