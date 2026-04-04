from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from crxzipple.shared.domain import AggregateRoot
from crxzipple.shared.domain.events import DomainEvent

from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.domain.value_objects import (
    ToolEnvironment,
    ToolExecutionContext,
    ToolExecutionPolicy,
    ToolRunError,
    ToolRunResult,
    ToolExecutionSupport,
    ToolExecutionTarget,
    ToolExecutionStrategy,
    ToolKind,
    ToolMode,
    ToolParameter,
    ToolRunStatus,
    ToolSourceKind,
)
from crxzipple.shared.content_blocks import describe_content_for_text_fallback


@dataclass(kw_only=True)
class Tool(AggregateRoot[str]):
    name: str
    description: str
    kind: ToolKind = ToolKind.FUNCTION
    parameters: tuple[ToolParameter, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)
    required_effect_ids: tuple[str, ...] = field(default_factory=tuple)
    execution_policy: ToolExecutionPolicy = field(default_factory=ToolExecutionPolicy)
    execution_support: ToolExecutionSupport = field(
        default_factory=ToolExecutionSupport,
    )
    source_kind: ToolSourceKind = ToolSourceKind.MANUAL
    runtime_key: str | None = None
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ToolValidationError("Tool name cannot be empty.")
        if not self.description.strip():
            raise ToolValidationError("Tool description cannot be empty.")

        parameter_names = [parameter.name for parameter in self.parameters]
        if len(parameter_names) != len(set(parameter_names)):
            raise ToolValidationError("Tool parameter names must be unique.")

        self.tags = tuple(
            dict.fromkeys(
                tag.strip().lower()
                for tag in self.tags
                if tag is not None and tag.strip()
            ),
        )
        self.required_effect_ids = tuple(
            dict.fromkeys(
                effect_id.strip()
                for effect_id in self.required_effect_ids
                if effect_id is not None and effect_id.strip()
            ),
        )
        self.parameters = tuple(self.parameters)

    def supports(self, target: ToolExecutionTarget) -> bool:
        return self.execution_support.supports(target)

    def resolved_runtime_key(self) -> str:
        return self.runtime_key or self.id

    def enable(self) -> bool:
        if self.enabled:
            return False
        self.enabled = True
        self.record_event(
            DomainEvent(
                name="tool.enabled",
                payload={"tool_id": self.id, "tool_name": self.name},
            ),
        )
        return True

    def disable(self) -> bool:
        if not self.enabled:
            return False
        self.enabled = False
        self.record_event(
            DomainEvent(
                name="tool.disabled",
                payload={"tool_id": self.id, "tool_name": self.name},
            ),
        )
        return True


@dataclass(kw_only=True)
class ToolRun(AggregateRoot[str]):
    tool_id: str
    target: ToolExecutionTarget
    status: ToolRunStatus = ToolRunStatus.CREATED
    input_payload: dict[str, Any] = field(default_factory=dict)
    invocation_context_payload: dict[str, Any] | None = None
    result_payload: Any | None = None
    error_payload: str | None = None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    started_at: datetime | None = None
    completed_at: datetime | None = None
    attempt_count: int = 0
    max_attempts: int = 3
    worker_id: str | None = None
    heartbeat_at: datetime | None = None
    lease_expires_at: datetime | None = None
    cancel_requested_at: datetime | None = None

    def __post_init__(self) -> None:
        self.input_payload = dict(self.input_payload)
        self.invocation_context_payload = (
            dict(self.invocation_context_payload)
            if self.invocation_context_payload is not None
            else None
        )
        if self.attempt_count < 0:
            raise ToolValidationError("Tool run attempt_count cannot be negative.")
        if self.max_attempts < 1:
            raise ToolValidationError("Tool run max_attempts must be at least 1.")

    @property
    def result(self) -> ToolRunResult | None:
        if self.result_payload is None:
            return None
        return ToolRunResult.from_payload(self.result_payload)

    @property
    def error(self) -> ToolRunError | None:
        if self.error_payload is None:
            return None
        return ToolRunError.from_storage(self.error_payload)

    @property
    def output_payload(self) -> Any | None:
        result = self.result
        if result is None:
            return None
        if result.details is not None:
            return result.details
        if result.blocks:
            return describe_content_for_text_fallback(result.blocks)
        return None

    @property
    def invocation_context(self) -> ToolExecutionContext | None:
        return ToolExecutionContext.from_payload(self.invocation_context_payload)

    @property
    def error_message(self) -> str | None:
        error = self.error
        if error is None:
            return None
        return error.message

    @property
    def stored_output_payload(self) -> Any | None:
        return self.result_payload

    @property
    def stored_error_payload(self) -> str | None:
        return self.error_payload

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        tool_id: str,
        input_payload: dict[str, Any],
        invocation_context_payload: dict[str, Any] | None = None,
        target: ToolExecutionTarget,
        max_attempts: int = 3,
    ) -> "ToolRun":
        run = cls(
            id=run_id,
            tool_id=tool_id,
            input_payload=input_payload,
            invocation_context_payload=invocation_context_payload,
            target=target,
            max_attempts=max_attempts,
        )
        run.record_event(
            DomainEvent(
                name="tool.run.created",
                payload={
                    "run_id": run.id,
                    "tool_id": run.tool_id,
                    "mode": run.target.mode.value,
                    "strategy": run.target.strategy.value,
                    "environment": run.target.environment.value,
                },
            ),
        )
        return run

    def queue(self) -> None:
        self.status = ToolRunStatus.QUEUED
        self.worker_id = None
        self.heartbeat_at = None
        self.lease_expires_at = None
        self.cancel_requested_at = None
        self.started_at = None
        self.completed_at = None
        self.result_payload = None
        self.error_payload = None
        self.record_event(
            DomainEvent(
                name="tool.run.queued",
                payload={"run_id": self.id, "tool_id": self.tool_id},
            ),
        )

    def dispatch(self, *, worker_id: str, lease_seconds: int) -> None:
        now = datetime.now(timezone.utc)
        self.status = ToolRunStatus.DISPATCHING
        self.attempt_count += 1
        self.worker_id = worker_id
        self.heartbeat_at = now
        self.lease_expires_at = now + timedelta(seconds=lease_seconds)
        self.started_at = None
        self.completed_at = None
        self.result_payload = None
        self.error_payload = None
        self.record_event(
            DomainEvent(
                name="tool.run.dispatching",
                payload={
                    "run_id": self.id,
                    "tool_id": self.tool_id,
                    "worker_id": worker_id,
                    "attempt_count": self.attempt_count,
                },
            ),
        )

    def start(self) -> None:
        self.status = ToolRunStatus.RUNNING
        self.started_at = datetime.now(timezone.utc)
        self.completed_at = None
        self.error_payload = None
        self.result_payload = None
        self.record_event(
            DomainEvent(
                name="tool.run.started",
                payload={"run_id": self.id, "tool_id": self.tool_id},
            ),
        )

    def heartbeat(self, *, lease_seconds: int) -> None:
        if self.status not in {
            ToolRunStatus.DISPATCHING,
            ToolRunStatus.RUNNING,
            ToolRunStatus.CANCEL_REQUESTED,
        }:
            return
        now = datetime.now(timezone.utc)
        self.heartbeat_at = now
        self.lease_expires_at = now + timedelta(seconds=lease_seconds)

    def succeed(self, output_payload: ToolRunResult) -> None:
        self.status = ToolRunStatus.SUCCEEDED
        self.result_payload = output_payload.to_payload()
        self.error_payload = None
        self.completed_at = datetime.now(timezone.utc)
        self.heartbeat_at = self.completed_at
        self.lease_expires_at = None
        self.record_event(
            DomainEvent(
                name="tool.run.succeeded",
                payload={"run_id": self.id, "tool_id": self.tool_id},
            ),
        )

    def fail(self, error_message: str | ToolRunError) -> None:
        self.status = ToolRunStatus.FAILED
        normalized_error = (
            error_message
            if isinstance(error_message, ToolRunError)
            else ToolRunError(message=error_message)
        )
        self.error_payload = normalized_error.to_storage()
        self.result_payload = None
        self.completed_at = datetime.now(timezone.utc)
        self.heartbeat_at = self.completed_at
        self.lease_expires_at = None
        self.record_event(
            DomainEvent(
                name="tool.run.failed",
                payload={
                    "run_id": self.id,
                    "tool_id": self.tool_id,
                    "error_message": normalized_error.message,
                },
            ),
        )

    def requeue(self, reason: str | ToolRunError) -> None:
        self.status = ToolRunStatus.QUEUED
        normalized_error = (
            reason if isinstance(reason, ToolRunError) else ToolRunError(message=reason)
        )
        self.error_payload = normalized_error.to_storage()
        self.result_payload = None
        self.started_at = None
        self.completed_at = None
        self.worker_id = None
        self.heartbeat_at = None
        self.lease_expires_at = None
        self.cancel_requested_at = None
        self.record_event(
            DomainEvent(
                name="tool.run.requeued",
                payload={
                    "run_id": self.id,
                    "tool_id": self.tool_id,
                    "attempt_count": self.attempt_count,
                    "reason": normalized_error.message,
                },
            ),
        )

    def request_cancel(self) -> None:
        self.cancel_requested_at = datetime.now(timezone.utc)
        self.status = ToolRunStatus.CANCEL_REQUESTED
        self.record_event(
            DomainEvent(
                name="tool.run.cancel_requested",
                payload={"run_id": self.id, "tool_id": self.tool_id},
            ),
        )

    def cancel(self) -> None:
        self.status = ToolRunStatus.CANCELLED
        self.completed_at = datetime.now(timezone.utc)
        self.heartbeat_at = self.completed_at
        self.lease_expires_at = None
        self.record_event(
            DomainEvent(
                name="tool.run.cancelled",
                payload={"run_id": self.id, "tool_id": self.tool_id},
            ),
        )

    def timeout(self) -> None:
        self.status = ToolRunStatus.TIMED_OUT
        self.completed_at = datetime.now(timezone.utc)
        self.heartbeat_at = self.completed_at
        self.lease_expires_at = None
        self.record_event(
            DomainEvent(
                name="tool.run.timed_out",
                payload={"run_id": self.id, "tool_id": self.tool_id},
            ),
        )

    def is_terminal(self) -> bool:
        return self.status in {
            ToolRunStatus.SUCCEEDED,
            ToolRunStatus.FAILED,
            ToolRunStatus.CANCELLED,
            ToolRunStatus.TIMED_OUT,
        }

    def can_retry(self) -> bool:
        return self.attempt_count < self.max_attempts


__all__ = [
    "Tool",
    "ToolEnvironment",
    "ToolExecutionPolicy",
    "ToolExecutionSupport",
    "ToolExecutionTarget",
    "ToolExecutionStrategy",
    "ToolKind",
    "ToolMode",
    "ToolParameter",
    "ToolRun",
    "ToolRunStatus",
    "ToolSourceKind",
]
