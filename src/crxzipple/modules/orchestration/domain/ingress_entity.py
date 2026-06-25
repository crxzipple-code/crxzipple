"""Orchestration ingress request aggregate."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    OrchestrationBoundSessionTarget,
    OrchestrationErrorPayload,
    OrchestrationIngressRequestKind,
    OrchestrationIngressStatus,
    OrchestrationQueuePolicy,
    utcnow,
)
from crxzipple.shared.domain import AggregateRoot
from crxzipple.shared.domain.events import Event

from .entity_payloads import _optional_payload_text

@dataclass(kw_only=True)
class OrchestrationIngressRequest(AggregateRoot[str]):
    run_id: str
    kind: OrchestrationIngressRequestKind = OrchestrationIngressRequestKind.ROUTED_TURN
    route_context_payload: dict[str, object] = field(default_factory=dict)
    bound_session_payload: dict[str, object] = field(default_factory=dict)
    requested_llm_id: str | None = None
    ensure_session: bool = True
    touch_activity: bool = True
    reset_policy_payload: dict[str, object] = field(default_factory=dict)
    prepare_metadata: dict[str, object] = field(default_factory=dict)
    queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.FIFO
    priority: int | None = None
    status: OrchestrationIngressStatus = OrchestrationIngressStatus.QUEUED
    worker_id: str | None = None
    error: OrchestrationErrorPayload | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    claimed_at: datetime | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise OrchestrationValidationError(
                "Orchestration ingress request id cannot be empty.",
            )
        if not self.run_id.strip():
            raise OrchestrationValidationError(
                "Orchestration ingress request run_id cannot be empty.",
            )
        if not isinstance(self.kind, OrchestrationIngressRequestKind):
            self.kind = OrchestrationIngressRequestKind(str(self.kind))
        if not isinstance(self.queue_policy, OrchestrationQueuePolicy):
            self.queue_policy = OrchestrationQueuePolicy(str(self.queue_policy))
        if self.priority is not None and self.priority < 0:
            raise OrchestrationValidationError(
                "Orchestration ingress request priority cannot be negative.",
            )
        if not isinstance(self.status, OrchestrationIngressStatus):
            self.status = OrchestrationIngressStatus(str(self.status))
        self.route_context_payload = dict(self.route_context_payload)
        self.bound_session_payload = dict(self.bound_session_payload)
        self.reset_policy_payload = dict(self.reset_policy_payload)
        self.prepare_metadata = dict(self.prepare_metadata)
        if self.requested_llm_id is not None:
            self.requested_llm_id = self.requested_llm_id.strip() or None
        if self.worker_id is not None:
            self.worker_id = self.worker_id.strip() or None
        self._validate_target_payload()

    @classmethod
    def queue_turn(
        cls,
        *,
        request_id: str,
        run_id: str,
        route_context_payload: dict[str, object],
        requested_llm_id: str | None = None,
        ensure_session: bool = True,
        touch_activity: bool = True,
        reset_policy_payload: dict[str, object] | None = None,
        prepare_metadata: dict[str, object] | None = None,
        queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.FIFO,
        priority: int | None = None,
    ) -> "OrchestrationIngressRequest":
        request = cls(
            id=request_id,
            run_id=run_id,
            kind=OrchestrationIngressRequestKind.ROUTED_TURN,
            route_context_payload=route_context_payload,
            requested_llm_id=requested_llm_id,
            ensure_session=ensure_session,
            touch_activity=touch_activity,
            reset_policy_payload=reset_policy_payload or {},
            prepare_metadata=prepare_metadata or {},
            queue_policy=queue_policy,
            priority=priority,
        )
        request.record_event(
            Event(
                name="orchestration.ingress.requested",
                payload={
                    "request_id": request.id,
                    "run_id": request.run_id,
                    "kind": request.kind.value,
                    "status": request.status.value,
                    "source": _optional_payload_text(
                        request.route_context_payload.get("surface"),
                    )
                    or _optional_payload_text(
                        request.route_context_payload.get("channel"),
                    ),
                    "target_lane": _optional_payload_text(
                        request.route_context_payload.get("main_key"),
                    ),
                    "priority": request.priority,
                    "queue_policy": request.queue_policy.value,
                    "requested_llm_id": request.requested_llm_id,
                },
            ),
        )
        return request

    @classmethod
    def queue_bound_turn(
        cls,
        *,
        request_id: str,
        run_id: str,
        bound_session_target: OrchestrationBoundSessionTarget,
        requested_llm_id: str | None = None,
        prepare_metadata: dict[str, object] | None = None,
        queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.FIFO,
        priority: int | None = None,
    ) -> "OrchestrationIngressRequest":
        request = cls(
            id=request_id,
            run_id=run_id,
            kind=OrchestrationIngressRequestKind.BOUND_TURN,
            bound_session_payload=bound_session_target.to_payload(),
            requested_llm_id=requested_llm_id,
            ensure_session=False,
            touch_activity=False,
            prepare_metadata=prepare_metadata or {},
            queue_policy=queue_policy,
            priority=priority,
        )
        request.record_event(
            Event(
                name="orchestration.ingress.requested",
                payload={
                    "request_id": request.id,
                    "run_id": request.run_id,
                    "kind": request.kind.value,
                    "status": request.status.value,
                    "source": "bound_turn",
                    "target_lane": bound_session_target.lane_key
                    or bound_session_target.session_key,
                    "priority": request.priority,
                    "queue_policy": request.queue_policy.value,
                    "requested_llm_id": request.requested_llm_id,
                },
            ),
        )
        return request

    def claim(self, *, worker_id: str, claimed_at: datetime | None = None) -> None:
        normalized_worker_id = worker_id.strip()
        if not normalized_worker_id:
            raise OrchestrationValidationError(
                "Orchestration ingress worker_id cannot be empty.",
            )
        timestamp = claimed_at or utcnow()
        self.status = OrchestrationIngressStatus.PROCESSING
        self.worker_id = normalized_worker_id
        self.claimed_at = timestamp
        self.updated_at = timestamp
        self.record_event(
            Event(
                name="orchestration.ingress.claimed",
                payload={
                    "request_id": self.id,
                    "run_id": self.run_id,
                    "kind": self.kind.value,
                    "status": self.status.value,
                    "worker_id": self.worker_id,
                },
            ),
        )

    def complete(self, *, completed_at: datetime | None = None) -> None:
        timestamp = completed_at or utcnow()
        self.status = OrchestrationIngressStatus.COMPLETED
        self.error = None
        self.completed_at = timestamp
        self.updated_at = timestamp
        self.record_event(
            Event(
                name="orchestration.ingress.completed",
                payload={
                    "request_id": self.id,
                    "run_id": self.run_id,
                    "kind": self.kind.value,
                    "status": self.status.value,
                },
            ),
        )

    def fail(
        self,
        *,
        message: str,
        code: str = "ingress_failed",
        details: dict[str, object] | None = None,
        failed_at: datetime | None = None,
    ) -> None:
        timestamp = failed_at or utcnow()
        self.status = OrchestrationIngressStatus.FAILED
        self.error = OrchestrationErrorPayload(
            message=message,
            code=code,
            details=details or {},
        )
        self.completed_at = timestamp
        self.updated_at = timestamp
        self.record_event(
            Event(
                name="orchestration.ingress.failed",
                payload={
                    "request_id": self.id,
                    "run_id": self.run_id,
                    "kind": self.kind.value,
                    "status": self.status.value,
                    "code": code,
                    "message": message,
                    "details": dict(self.error.details),
                },
            ),
        )

    @property
    def bound_session_target(self) -> OrchestrationBoundSessionTarget | None:
        return OrchestrationBoundSessionTarget.from_payload(self.bound_session_payload)

    def _validate_target_payload(self) -> None:
        if self.kind is OrchestrationIngressRequestKind.ROUTED_TURN:
            if not self.route_context_payload:
                raise OrchestrationValidationError(
                    "Routed orchestration ingress request requires route_context_payload.",
                )
            if self.bound_session_payload:
                raise OrchestrationValidationError(
                    "Routed orchestration ingress request cannot include bound_session_payload.",
                )
            return
        if self.kind is OrchestrationIngressRequestKind.BOUND_TURN:
            if self.route_context_payload:
                raise OrchestrationValidationError(
                    "Bound orchestration ingress request cannot include route_context_payload.",
                )
            if self.bound_session_target is None:
                raise OrchestrationValidationError(
                    "Bound orchestration ingress request requires bound_session_payload.",
                )
            return
        raise OrchestrationValidationError(
            f"Unsupported orchestration ingress request kind '{self.kind.value}'.",
        )
