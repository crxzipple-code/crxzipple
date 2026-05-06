from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from crxzipple.modules.orchestration.domain.value_objects import (
    InboundInstruction,
    OrchestrationQueuePolicy,
    ReplyTarget,
)
from crxzipple.modules.session.domain import (
    SessionResetPolicy,
    SessionRouteContext,
)


@dataclass(frozen=True, slots=True)
class AcceptOrchestrationRunInput:
    inbound_instruction: InboundInstruction
    reply_target: ReplyTarget | None = None
    run_id: str | None = None
    queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.FIFO
    priority: int = 100
    max_steps: int = 99
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RouteOrchestrationRunInput:
    run_id: str
    agent_id: str
    session_key: str | None = None
    lane_key: str | None = None
    priority: int | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BindSessionInput:
    run_id: str
    active_session_id: str


@dataclass(frozen=True, slots=True)
class EnqueueOrchestrationRunInput:
    run_id: str
    lane_key: str | None = None
    queue_policy: OrchestrationQueuePolicy | None = None
    priority: int | None = None


@dataclass(frozen=True, slots=True)
class PrepareSessionRunInput:
    run_id: str
    context: SessionRouteContext
    requested_llm_id: str | None = None
    ensure: bool = True
    touch_activity: bool = True
    reset_policy: SessionResetPolicy | None = None
    priority: int | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    now: datetime | None = None
