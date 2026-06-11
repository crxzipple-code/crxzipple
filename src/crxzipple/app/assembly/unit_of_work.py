"""Unit of work app assembly."""

from __future__ import annotations

from crxzipple.app.keys import AppKey
from crxzipple.app.plan import ApplicationFactory
from crxzipple.shared.infrastructure import SqlAlchemyUnitOfWork


def unit_of_work_factories() -> tuple[ApplicationFactory, ...]:
    """Build the SQLAlchemy unit-of-work factory used by module applications."""

    return (
        ApplicationFactory(
            key="database.unit_of_work_factory",
            provides=(AppKey.UNIT_OF_WORK_FACTORY,),
            requires=(AppKey.DATABASE_SESSION_FACTORY,),
            build=_build_unit_of_work_factory,
        ),
    )


def _build_unit_of_work_factory(ctx):
    session_factory = ctx.require(AppKey.DATABASE_SESSION_FACTORY)
    return lambda: SqlAlchemyUnitOfWork(session_factory)


__all__ = ["unit_of_work_factories"]
