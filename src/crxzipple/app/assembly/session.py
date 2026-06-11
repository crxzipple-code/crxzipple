"""Session module app assembly."""

from __future__ import annotations

from crxzipple.app.keys import AppKey
from crxzipple.app.plan import ApplicationFactory
from crxzipple.modules.agent.domain import AgentNotFoundError
from crxzipple.modules.session.application import (
    SessionApplicationService,
    SessionResolutionService,
)


def session_factories() -> tuple[ApplicationFactory, ...]:
    """Build Session module-local application services."""

    return (
        ApplicationFactory(
            key="session.services",
            provides=(AppKey.SESSION_SERVICE, AppKey.SESSION_RESOLUTION_SERVICE),
            requires=(AppKey.UNIT_OF_WORK_FACTORY, AppKey.AGENT_SERVICE),
            build=_build_session_services,
        ),
    )


def _build_session_services(ctx):
    agent_service = ctx.require(AppKey.AGENT_SERVICE)

    def _default_workspace_for_agent(agent_id: str) -> str | None:
        try:
            profile = agent_service.get_profile(agent_id)
        except AgentNotFoundError:
            return None
        return (
            profile.runtime_preferences.workspace
            or profile.runtime_preferences.workdir
        )

    service = SessionApplicationService(
        ctx.require(AppKey.UNIT_OF_WORK_FACTORY),
        workspace_defaults_resolver=_default_workspace_for_agent,
    )
    return {
        AppKey.SESSION_SERVICE: service,
        AppKey.SESSION_RESOLUTION_SERVICE: SessionResolutionService(service),
    }


__all__ = ["session_factories"]
