from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from crxzipple.modules.tool.domain.entity_normalization import normalize_optional_text
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.domain.value_objects import (
    ToolExecutionContext,
    ToolExecutionTarget,
    ToolRunError,
    ToolRunResult,
    ToolRunStatus,
)
from crxzipple.shared.content_blocks import describe_content_for_text_fallback
from crxzipple.shared.domain import AggregateRoot
from crxzipple.shared.domain.events import Event

DEFAULT_TOOL_RUN_ERROR_MESSAGE = "Tool run failed without an error message."
TOOL_RESULT_ENVELOPE_METADATA_KEY = "tool_result_envelope"
TOOL_RESULT_ENVELOPE_SCHEMA_VERSION = "2026-06-14.tool_result_envelope.v1"


def _normalize_tool_run_error(error: str | ToolRunError) -> ToolRunError:
    if isinstance(error, ToolRunError):
        return error
    normalized = str(error).strip()
    return ToolRunError(message=normalized or DEFAULT_TOOL_RUN_ERROR_MESSAGE)


def _tool_result_envelope_payload(result: ToolRunResult) -> dict[str, Any] | None:
    envelope = result.metadata.get(TOOL_RESULT_ENVELOPE_METADATA_KEY)
    if isinstance(envelope, dict):
        return dict(envelope)
    return None


def _normalized_tool_result_envelope_payload(
    result: ToolRunResult,
    *,
    tool_run_id: str,
    call_id: str | None,
    fallback_tool_name: str,
) -> dict[str, Any] | None:
    payload = _tool_result_envelope_payload(result)
    if payload is None:
        return None
    payload.setdefault("schema_version", TOOL_RESULT_ENVELOPE_SCHEMA_VERSION)
    payload["tool_run_id"] = tool_run_id
    if call_id is not None:
        payload["call_id"] = call_id
    else:
        payload.pop("call_id", None)
    if not isinstance(payload.get("tool_name"), str) or not str(
        payload.get("tool_name"),
    ).strip():
        payload["tool_name"] = fallback_tool_name
    return payload


@dataclass(kw_only=True)
class ToolRun(AggregateRoot[str]):
    tool_id: str
    target: ToolExecutionTarget
    call_id: str | None = None
    tool_surface_id: str | None = None
    function_id: str | None = None
    function_revision: int | None = None
    source_id: str | None = None
    source_revision: int | None = None
    schema_hash: str | None = None
    status: ToolRunStatus = ToolRunStatus.CREATED
    input_payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    invocation_context_payload: dict[str, Any] | None = None
    result_payload: Any | None = None
    result_envelope_payload: dict[str, Any] | None = None
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
        self.metadata = dict(self.metadata)
        self.call_id = normalize_optional_text(self.call_id)
        self.tool_surface_id = normalize_optional_text(self.tool_surface_id)
        self.function_id = normalize_optional_text(self.function_id)
        self.source_id = normalize_optional_text(self.source_id)
        self.schema_hash = normalize_optional_text(self.schema_hash)
        if self.function_revision is not None and self.function_revision < 1:
            raise ToolValidationError("Tool run function_revision must be at least 1.")
        if self.source_revision is not None and self.source_revision < 1:
            raise ToolValidationError("Tool run source_revision must be at least 1.")
        self.invocation_context_payload = (
            dict(self.invocation_context_payload)
            if self.invocation_context_payload is not None
            else None
        )
        self.result_envelope_payload = (
            dict(self.result_envelope_payload)
            if isinstance(self.result_envelope_payload, dict)
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
        if not self.error_payload.strip():
            return ToolRunError(message=DEFAULT_TOOL_RUN_ERROR_MESSAGE)
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
        metadata: dict[str, Any] | None = None,
        invocation_context_payload: dict[str, Any] | None = None,
        target: ToolExecutionTarget,
        call_id: str | None = None,
        tool_surface_id: str | None = None,
        function_id: str | None = None,
        function_revision: int | None = None,
        source_id: str | None = None,
        source_revision: int | None = None,
        schema_hash: str | None = None,
        max_attempts: int = 3,
    ) -> ToolRun:
        run = cls(
            id=run_id,
            tool_id=tool_id,
            call_id=call_id,
            tool_surface_id=tool_surface_id,
            function_id=function_id,
            function_revision=function_revision,
            source_id=source_id,
            source_revision=source_revision,
            schema_hash=schema_hash,
            input_payload=input_payload,
            metadata=metadata or {},
            invocation_context_payload=invocation_context_payload,
            target=target,
            max_attempts=max_attempts,
        )
        run.record_event(
            Event(
                name="tool.run.created",
                payload={
                    "run_id": run.id,
                    "tool_id": run.tool_id,
                    "call_id": run.call_id,
                    "tool_surface_id": run.tool_surface_id,
                    "function_id": run.function_id,
                    "function_revision": run.function_revision,
                    "source_id": run.source_id,
                    "source_revision": run.source_revision,
                    "schema_hash": run.schema_hash,
                    "mode": run.target.mode.value,
                    "strategy": run.target.strategy.value,
                    "environment": run.target.environment.value,
                    "metadata": dict(run.metadata),
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
        self.result_envelope_payload = None
        self.error_payload = None
        self.record_event(
            Event(
                name="tool.run.queued",
                payload={
                    "run_id": self.id,
                    "tool_id": self.tool_id,
                    "call_id": self.call_id,
                    "tool_surface_id": self.tool_surface_id,
                    "function_id": self.function_id,
                    "source_id": self.source_id,
                },
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
        self.result_envelope_payload = None
        self.error_payload = None
        self.record_event(
            Event(
                name="tool.run.dispatching",
                payload={
                    "run_id": self.id,
                    "tool_id": self.tool_id,
                    "call_id": self.call_id,
                    "tool_surface_id": self.tool_surface_id,
                    "function_id": self.function_id,
                    "source_id": self.source_id,
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
        self.result_envelope_payload = None
        self.record_event(
            Event(
                name="tool.run.started",
                payload={
                    "run_id": self.id,
                    "tool_id": self.tool_id,
                    "call_id": self.call_id,
                    "tool_surface_id": self.tool_surface_id,
                    "function_id": self.function_id,
                    "source_id": self.source_id,
                },
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
        self.record_event(
            Event(
                name="tool.run.heartbeated",
                payload={
                    "run_id": self.id,
                    "tool_id": self.tool_id,
                    "worker_id": self.worker_id,
                    "status": self.status.value,
                    "attempt_count": self.attempt_count,
                    "heartbeat_at": self.heartbeat_at.isoformat(),
                    "lease_expires_at": self.lease_expires_at.isoformat(),
                },
            ),
        )

    def succeed(self, output_payload: ToolRunResult) -> None:
        self.status = ToolRunStatus.SUCCEEDED
        self.result_payload = output_payload.to_payload()
        self.result_envelope_payload = _normalized_tool_result_envelope_payload(
            output_payload,
            tool_run_id=self.id,
            call_id=self.call_id,
            fallback_tool_name=self.tool_id,
        )
        self.error_payload = None
        self.completed_at = datetime.now(timezone.utc)
        self.heartbeat_at = self.completed_at
        self.lease_expires_at = None
        self.record_event(
            Event(
                name="tool.run.succeeded",
                payload=self._terminal_event_payload(),
            ),
        )

    def fail(self, error_message: str | ToolRunError) -> None:
        self.status = ToolRunStatus.FAILED
        normalized_error = _normalize_tool_run_error(error_message)
        self.error_payload = normalized_error.to_storage()
        self.result_payload = None
        self.result_envelope_payload = None
        self.completed_at = datetime.now(timezone.utc)
        self.heartbeat_at = self.completed_at
        self.lease_expires_at = None
        self.record_event(
            Event(
                name="tool.run.failed",
                payload={
                    **self._terminal_event_payload(),
                    "error_message": normalized_error.message,
                },
            ),
        )

    def requeue(self, reason: str | ToolRunError) -> None:
        self.status = ToolRunStatus.QUEUED
        normalized_error = _normalize_tool_run_error(reason)
        self.error_payload = normalized_error.to_storage()
        self.result_payload = None
        self.result_envelope_payload = None
        self.started_at = None
        self.completed_at = None
        self.worker_id = None
        self.heartbeat_at = None
        self.lease_expires_at = None
        self.cancel_requested_at = None
        self.record_event(
            Event(
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
            Event(
                name="tool.run.cancel_requested",
                payload={"run_id": self.id, "tool_id": self.tool_id},
            ),
        )

    def cancel(self) -> None:
        self.status = ToolRunStatus.CANCELLED
        self.result_payload = None
        self.result_envelope_payload = None
        self.completed_at = datetime.now(timezone.utc)
        self.heartbeat_at = self.completed_at
        self.lease_expires_at = None
        self.record_event(
            Event(
                name="tool.run.cancelled",
                payload=self._terminal_event_payload(),
            ),
        )

    def timeout(self) -> None:
        self.status = ToolRunStatus.TIMED_OUT
        self.result_payload = None
        self.result_envelope_payload = None
        self.completed_at = datetime.now(timezone.utc)
        self.heartbeat_at = self.completed_at
        self.lease_expires_at = None
        self.record_event(
            Event(
                name="tool.run.timed_out",
                payload=self._terminal_event_payload(),
            ),
        )

    def is_terminal(self) -> bool:
        return self.status in {
            ToolRunStatus.SUCCEEDED,
            ToolRunStatus.FAILED,
            ToolRunStatus.CANCELLED,
            ToolRunStatus.TIMED_OUT,
        }

    def _terminal_event_payload(self) -> dict[str, object]:
        return {
            "run_id": self.id,
            "tool_id": self.tool_id,
            "call_id": self.call_id,
            "tool_surface_id": self.tool_surface_id,
            "function_id": self.function_id,
            "function_revision": self.function_revision,
            "source_id": self.source_id,
            "source_revision": self.source_revision,
            "schema_hash": self.schema_hash,
            "mode": self.target.mode.value,
            "strategy": self.target.strategy.value,
            "environment": self.target.environment.value,
        }

    def can_retry(self) -> bool:
        return self.attempt_count < self.max_attempts
