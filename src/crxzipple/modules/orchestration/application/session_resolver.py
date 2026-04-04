from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from crxzipple.modules.orchestration.application.router import (
    OrchestrationRouter,
    SessionRoutingDecision,
)
from crxzipple.modules.session.application import (
    RoutedSessionResult,
    SessionApplicationService,
    SyncRoutedSessionInput,
)
from crxzipple.modules.session.domain.entities import Session, SessionInstance
from crxzipple.modules.session.domain.value_objects import (
    SessionResetPolicy,
    SessionRouteContext,
)


@dataclass(frozen=True, slots=True)
class ResolveSessionBundleInput:
    context: SessionRouteContext
    ensure: bool = False
    touch_activity: bool = True
    reset_policy: SessionResetPolicy | None = None
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class SessionBundle:
    routing: SessionRoutingDecision
    resolution: RoutedSessionResult
    session: Session | None = None
    active_instance: SessionInstance | None = None


class SessionResolver:
    def __init__(
        self,
        session_service: SessionApplicationService,
        router: OrchestrationRouter | None = None,
    ) -> None:
        self.session_service = session_service
        self.router = router or OrchestrationRouter()

    def resolve(self, data: ResolveSessionBundleInput) -> SessionBundle:
        routing = self.router.route_session(data.context)
        resolved = self.session_service.sync_routed_session(
            SyncRoutedSessionInput(
                key_resolution=routing.key_resolution,
                agent_id=data.context.agent_id,
                status=data.context.status,
                origin=routing.origin,
                delivery=routing.delivery,
                metadata=data.context.metadata,
                ensure=data.ensure,
                touch_activity=data.touch_activity,
                reset_policy=data.reset_policy,
                now=data.now,
            ),
        )
        return SessionBundle(
            routing=routing,
            resolution=resolved,
            session=resolved.session,
            active_instance=resolved.active_instance,
        )
