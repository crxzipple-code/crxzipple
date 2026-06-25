"""Execution-chain domain entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    ExecutionChainStatus,
    ExecutionOwnerReference,
    ExecutionStepItemKind,
    ExecutionStepItemStatus,
    ExecutionStepKind,
    ExecutionStepStatus,
    OrchestrationErrorPayload,
    utcnow,
)
from crxzipple.shared.domain import AggregateRoot

from .entity_payloads import (
    _normalized_optional_text,
    _normalized_payload,
)

@dataclass(kw_only=True)
class ExecutionChain(AggregateRoot[str]):
    turn_id: str
    status: ExecutionChainStatus = ExecutionChainStatus.CREATED
    active_step_id: str | None = None
    step_count: int = 0
    error_payload: OrchestrationErrorPayload | None = None
    created_at: datetime = field(default_factory=utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise OrchestrationValidationError("Execution chain id cannot be empty.")
        if not self.turn_id.strip():
            raise OrchestrationValidationError("Execution chain turn_id cannot be empty.")
        if not isinstance(self.status, ExecutionChainStatus):
            self.status = ExecutionChainStatus(str(self.status))
        self.active_step_id = _normalized_optional_text(self.active_step_id)
        if self.step_count < 0:
            raise OrchestrationValidationError(
                "Execution chain step_count cannot be negative.",
            )

    @classmethod
    def create(cls, *, chain_id: str, turn_id: str) -> "ExecutionChain":
        return cls(id=chain_id, turn_id=turn_id)

    def start(self, *, active_step_id: str | None = None) -> None:
        timestamp = utcnow()
        self.status = ExecutionChainStatus.RUNNING
        self.active_step_id = _normalized_optional_text(active_step_id)
        self.started_at = self.started_at or timestamp
        self.updated_at = timestamp

    def set_active_step(self, step_id: str | None) -> None:
        self.active_step_id = _normalized_optional_text(step_id)
        self.updated_at = utcnow()

    def increment_step_count(self) -> None:
        self.step_count += 1
        self.updated_at = utcnow()

    def wait(self, *, active_step_id: str | None = None) -> None:
        self.status = ExecutionChainStatus.WAITING
        if active_step_id is not None:
            self.active_step_id = _normalized_optional_text(active_step_id)
        self.updated_at = utcnow()

    def complete(self) -> None:
        timestamp = utcnow()
        self.status = ExecutionChainStatus.COMPLETED
        self.active_step_id = None
        self.completed_at = timestamp
        self.updated_at = timestamp
        self.error_payload = None

    def fail(
        self,
        *,
        message: str,
        code: str = "execution_chain_failed",
        details: dict[str, object] | None = None,
    ) -> None:
        timestamp = utcnow()
        self.status = ExecutionChainStatus.FAILED
        self.completed_at = timestamp
        self.updated_at = timestamp
        self.error_payload = OrchestrationErrorPayload(
            message=message,
            code=code,
            details=details or {},
        )

    def cancel(self) -> None:
        timestamp = utcnow()
        self.status = ExecutionChainStatus.CANCELLED
        self.active_step_id = None
        self.completed_at = timestamp
        self.updated_at = timestamp

@dataclass(kw_only=True)
class ExecutionStep(AggregateRoot[str]):
    chain_id: str
    turn_id: str
    step_index: int
    kind: ExecutionStepKind
    status: ExecutionStepStatus = ExecutionStepStatus.CREATED
    dispatch_task_id: str | None = None
    owner: ExecutionOwnerReference | None = None
    correlation_key: str | None = None
    error_payload: OrchestrationErrorPayload | None = None
    created_at: datetime = field(default_factory=utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise OrchestrationValidationError("Execution step id cannot be empty.")
        if not self.chain_id.strip():
            raise OrchestrationValidationError("Execution step chain_id cannot be empty.")
        if not self.turn_id.strip():
            raise OrchestrationValidationError("Execution step turn_id cannot be empty.")
        if self.step_index < 0:
            raise OrchestrationValidationError(
                "Execution step step_index cannot be negative.",
            )
        if not isinstance(self.kind, ExecutionStepKind):
            self.kind = ExecutionStepKind(str(self.kind))
        if not isinstance(self.status, ExecutionStepStatus):
            self.status = ExecutionStepStatus(str(self.status))
        self.dispatch_task_id = _normalized_optional_text(self.dispatch_task_id)
        self.correlation_key = _normalized_optional_text(self.correlation_key)

    @classmethod
    def create(
        cls,
        *,
        step_id: str,
        chain_id: str,
        turn_id: str,
        step_index: int,
        kind: ExecutionStepKind,
        correlation_key: str | None = None,
    ) -> "ExecutionStep":
        return cls(
            id=step_id,
            chain_id=chain_id,
            turn_id=turn_id,
            step_index=step_index,
            kind=kind,
            correlation_key=correlation_key,
        )

    def assign_dispatch_task(self, dispatch_task_id: str | None) -> None:
        self.dispatch_task_id = _normalized_optional_text(dispatch_task_id)
        self.updated_at = utcnow()

    def link_owner(self, owner: ExecutionOwnerReference | None) -> None:
        self.owner = owner
        self.updated_at = utcnow()

    def start(self) -> None:
        timestamp = utcnow()
        self.status = ExecutionStepStatus.RUNNING
        self.started_at = self.started_at or timestamp
        self.updated_at = timestamp

    def wait(self) -> None:
        self.status = ExecutionStepStatus.WAITING
        self.updated_at = utcnow()

    def complete(self) -> None:
        timestamp = utcnow()
        self.status = ExecutionStepStatus.COMPLETED
        self.completed_at = timestamp
        self.updated_at = timestamp
        self.error_payload = None

    def fail(
        self,
        *,
        message: str,
        code: str = "execution_step_failed",
        details: dict[str, object] | None = None,
    ) -> None:
        timestamp = utcnow()
        self.status = ExecutionStepStatus.FAILED
        self.completed_at = timestamp
        self.updated_at = timestamp
        self.error_payload = OrchestrationErrorPayload(
            message=message,
            code=code,
            details=details or {},
        )

    def cancel(self) -> None:
        timestamp = utcnow()
        self.status = ExecutionStepStatus.CANCELLED
        self.completed_at = timestamp
        self.updated_at = timestamp

@dataclass(kw_only=True)
class ExecutionStepItem(AggregateRoot[str]):
    step_id: str
    chain_id: str
    turn_id: str
    item_index: int
    kind: ExecutionStepItemKind
    status: ExecutionStepItemStatus = ExecutionStepItemStatus.CREATED
    owner: ExecutionOwnerReference | None = None
    correlation_key: str | None = None
    source_event_id: str | None = None
    payload_ref: dict[str, object] | None = None
    summary_payload: dict[str, object] | None = None
    error_payload: OrchestrationErrorPayload | None = None
    created_at: datetime = field(default_factory=utcnow)
    completed_at: datetime | None = None
    updated_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise OrchestrationValidationError("Execution step item id cannot be empty.")
        if not self.step_id.strip():
            raise OrchestrationValidationError(
                "Execution step item step_id cannot be empty.",
            )
        if not self.chain_id.strip():
            raise OrchestrationValidationError(
                "Execution step item chain_id cannot be empty.",
            )
        if not self.turn_id.strip():
            raise OrchestrationValidationError(
                "Execution step item turn_id cannot be empty.",
            )
        if self.item_index < 0:
            raise OrchestrationValidationError(
                "Execution step item item_index cannot be negative.",
            )
        if not isinstance(self.kind, ExecutionStepItemKind):
            self.kind = ExecutionStepItemKind(str(self.kind))
        if not isinstance(self.status, ExecutionStepItemStatus):
            self.status = ExecutionStepItemStatus(str(self.status))
        self.correlation_key = _normalized_optional_text(self.correlation_key)
        self.source_event_id = _normalized_optional_text(self.source_event_id)
        self.payload_ref = _normalized_payload(self.payload_ref)
        self.summary_payload = _normalized_payload(self.summary_payload)

    @classmethod
    def create(
        cls,
        *,
        item_id: str,
        step_id: str,
        chain_id: str,
        turn_id: str,
        item_index: int,
        kind: ExecutionStepItemKind,
        owner: ExecutionOwnerReference | None = None,
        correlation_key: str | None = None,
    ) -> "ExecutionStepItem":
        return cls(
            id=item_id,
            step_id=step_id,
            chain_id=chain_id,
            turn_id=turn_id,
            item_index=item_index,
            kind=kind,
            owner=owner,
            correlation_key=correlation_key,
        )

    def link_owner(self, owner: ExecutionOwnerReference | None) -> None:
        self.owner = owner
        self.updated_at = utcnow()

    def start(self) -> None:
        self.status = ExecutionStepItemStatus.RUNNING
        self.updated_at = utcnow()

    def wait(self) -> None:
        self.status = ExecutionStepItemStatus.WAITING
        self.updated_at = utcnow()

    def complete(self, *, summary_payload: dict[str, object] | None = None) -> None:
        timestamp = utcnow()
        self.status = ExecutionStepItemStatus.COMPLETED
        if summary_payload is not None:
            self.summary_payload = dict(summary_payload)
        self.completed_at = timestamp
        self.updated_at = timestamp
        self.error_payload = None

    def fail(
        self,
        *,
        message: str,
        code: str = "execution_step_item_failed",
        details: dict[str, object] | None = None,
    ) -> None:
        timestamp = utcnow()
        self.status = ExecutionStepItemStatus.FAILED
        self.completed_at = timestamp
        self.updated_at = timestamp
        self.error_payload = OrchestrationErrorPayload(
            message=message,
            code=code,
            details=details or {},
        )

    def mark_late_observed(self) -> None:
        timestamp = utcnow()
        self.status = ExecutionStepItemStatus.LATE_OBSERVED
        self.completed_at = self.completed_at or timestamp
        self.updated_at = timestamp

    def mark_late_ignored(self) -> None:
        timestamp = utcnow()
        self.status = ExecutionStepItemStatus.LATE_IGNORED
        self.completed_at = self.completed_at or timestamp
        self.updated_at = timestamp
