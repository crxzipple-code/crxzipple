from __future__ import annotations

from sqlalchemy import Engine, create_engine
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
        # File-based SQLite is a local-dev default here, so a null pool keeps
        # connections short-lived and avoids stale handles across CLI/tests.
        engine_kwargs["poolclass"] = NullPool

    return create_engine(
        settings.database_url,
        connect_args=connect_args,
        **engine_kwargs,
    )


def build_session_factory(engine: Engine) -> SessionFactory:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def import_models() -> None:
    from crxzipple.modules.dispatch.infrastructure.persistence import (
        models as _dispatch_models,
    )
    from crxzipple.modules.agent.infrastructure.persistence import models as _agent_models
    from crxzipple.modules.llm.infrastructure.persistence import models as _llm_models
    from crxzipple.modules.orchestration.infrastructure.persistence import (
        models as _orchestration_models,
    )
    from crxzipple.modules.session.infrastructure.persistence import (
        models as _session_models,
    )
    from crxzipple.modules.tool.infrastructure.persistence import models as _tool_models

    _ = (
        _dispatch_models,
        _agent_models,
        _llm_models,
        _orchestration_models,
        _session_models,
        _tool_models,
    )


def create_schema(engine: Engine) -> None:
    import_models()
    Base.metadata.create_all(engine)
