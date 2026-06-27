from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from crxzipple.modules.tool.domain.value_objects import ToolRunAssignmentStatus
from crxzipple.shared.domain import AggregateRoot
from crxzipple.shared.domain.events import Event


@dataclass(kw_only=True)
class ToolRunAssignment(AggregateRoot[str]):
    run_id: str
    tool_id: str
    worker_id: str
    status: ToolRunAssignmentStatus = ToolRunAssignmentStatus.ASSIGNED
    attempt_count: int = 1
    assigned_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    started_at: datetime | None = None
    heartbeat_at: datetime | None = None
    lease_expires_at: datetime | None = None
    completed_at: datetime | None = None
    terminal_reason: str | None = None

    @classmethod
    def create(
        cls,
        *,
        assignment_id: str,
        run_id: str,
        tool_id: str,
        worker_id: str,
        attempt_count: int,
        lease_seconds: int,
    ) -> ToolRunAssignment:
        now = datetime.now(timezone.utc)
        assignment = cls(
            id=assignment_id,
            run_id=run_id,
            tool_id=tool_id,
            worker_id=worker_id,
            attempt_count=attempt_count,
            assigned_at=now,
            heartbeat_at=now,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
        )
        assignment.record_event(
            Event(
                name="tool.assignment.created",
                payload={
                    "assignment_id": assignment.id,
                    "run_id": assignment.run_id,
                    "tool_id": assignment.tool_id,
                    "worker_id": assignment.worker_id,
                    "attempt_count": assignment.attempt_count,
                },
            ),
        )
        return assignment

    def start(self) -> None:
        if self.status is ToolRunAssignmentStatus.RUNNING:
            return
        self.status = ToolRunAssignmentStatus.RUNNING
        self.started_at = datetime.now(timezone.utc)
        self.record_event(
            Event(
                name="tool.assignment.started",
                payload={
                    "assignment_id": self.id,
                    "run_id": self.run_id,
                    "tool_id": self.tool_id,
                    "worker_id": self.worker_id,
                },
            ),
        )

    def heartbeat(self, *, lease_seconds: int) -> None:
        if self.status not in {
            ToolRunAssignmentStatus.ASSIGNED,
            ToolRunAssignmentStatus.RUNNING,
        }:
            return
        now = datetime.now(timezone.utc)
        self.heartbeat_at = now
        self.lease_expires_at = now + timedelta(seconds=lease_seconds)
        self.record_event(
            Event(
                name="tool.assignment.heartbeated",
                payload={
                    "assignment_id": self.id,
                    "run_id": self.run_id,
                    "tool_id": self.tool_id,
                    "worker_id": self.worker_id,
                    "status": self.status.value,
                    "attempt_count": self.attempt_count,
                    "heartbeat_at": self.heartbeat_at.isoformat(),
                    "lease_expires_at": self.lease_expires_at.isoformat(),
                },
            ),
        )

    def succeed(self) -> None:
        self._complete(ToolRunAssignmentStatus.SUCCEEDED)

    def fail(self, reason: str) -> None:
        self._complete(ToolRunAssignmentStatus.FAILED, reason=reason)

    def cancel(self, *, reason: str | None = None) -> None:
        self._complete(ToolRunAssignmentStatus.CANCELLED, reason=reason)

    def expire(self, *, reason: str) -> None:
        self._complete(ToolRunAssignmentStatus.EXPIRED, reason=reason)

    def is_terminal(self) -> bool:
        return self.status in {
            ToolRunAssignmentStatus.SUCCEEDED,
            ToolRunAssignmentStatus.FAILED,
            ToolRunAssignmentStatus.CANCELLED,
            ToolRunAssignmentStatus.EXPIRED,
        }

    def _complete(
        self,
        status: ToolRunAssignmentStatus,
        *,
        reason: str | None = None,
    ) -> None:
        self.status = status
        self.completed_at = datetime.now(timezone.utc)
        self.heartbeat_at = self.completed_at
        self.lease_expires_at = None
        self.terminal_reason = reason
        self.record_event(
            Event(
                name=f"tool.assignment.{status.value}",
                payload={
                    "assignment_id": self.id,
                    "run_id": self.run_id,
                    "tool_id": self.tool_id,
                    "worker_id": self.worker_id,
                    "reason": reason,
                },
            ),
        )
