"""Dispatch module app assembly."""

from __future__ import annotations

from crxzipple.app.keys import AppKey
from crxzipple.app.plan import ApplicationFactory
from crxzipple.modules.dispatch.application import DispatchApplicationService


def dispatch_factories() -> tuple[ApplicationFactory, ...]:
    """Build Dispatch module-local application services."""

    return (
        ApplicationFactory(
            key="dispatch.service",
            provides=(AppKey.DISPATCH_SERVICE,),
            requires=(AppKey.UNIT_OF_WORK_FACTORY,),
            build=lambda ctx: DispatchApplicationService(
                ctx.require(AppKey.UNIT_OF_WORK_FACTORY),
            ),
        ),
    )


__all__ = ["dispatch_factories"]
