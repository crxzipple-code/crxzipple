from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.memory.domain.exceptions import (
    MemoryCandidateAlreadyReviewedError,
    MemoryValidationError,
)
from crxzipple.modules.memory.domain.value_objects import MemoryCandidateStatus
from crxzipple.shared.domain import AggregateRoot
from crxzipple.shared.domain.events import DomainEvent


@dataclass(kw_only=True)
class MemoryEntry(AggregateRoot[str]):
    agent_id: str
    title: str
    content: str
    summary: str = ""
    session_key: str | None = None
    run_id: str | None = None
    source_candidate_id: str | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        self.agent_id = self.agent_id.strip()
        self.title = self.title.strip()
        self.content = self.content.strip()
        self.summary = self.summary.strip()
        self.tags = tuple(
            dict.fromkeys(
                tag.strip().lower()
                for tag in self.tags
                if tag is not None and tag.strip()
            ),
        )
        self.metadata = dict(self.metadata)
        if not self.agent_id:
            raise MemoryValidationError("Memory entry agent_id cannot be empty.")
        if not self.title:
            raise MemoryValidationError("Memory entry title cannot be empty.")
        if not self.content:
            raise MemoryValidationError("Memory entry content cannot be empty.")
        if self.updated_at < self.created_at:
            self.updated_at = self.created_at

    @classmethod
    def create(
        cls,
        *,
        entry_id: str,
        agent_id: str,
        title: str,
        content: str,
        summary: str = "",
        session_key: str | None = None,
        run_id: str | None = None,
        source_candidate_id: str | None = None,
        tags: tuple[str, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> "MemoryEntry":
        now = datetime.now(timezone.utc)
        entry = cls(
            id=entry_id,
            agent_id=agent_id,
            title=title,
            content=content,
            summary=summary,
            session_key=session_key,
            run_id=run_id,
            source_candidate_id=source_candidate_id,
            tags=tags,
            metadata=metadata or {},
            created_at=now,
            updated_at=now,
        )
        entry.record_event(
            DomainEvent(
                name="memory.entry.created",
                payload={
                    "entry_id": entry.id,
                    "agent_id": entry.agent_id,
                    "source_candidate_id": entry.source_candidate_id,
                },
            ),
        )
        return entry


@dataclass(kw_only=True)
class MemoryCandidate(AggregateRoot[str]):
    agent_id: str
    title: str
    content: str
    summary: str = ""
    session_key: str | None = None
    run_id: str | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    status: MemoryCandidateStatus = MemoryCandidateStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reviewed_at: datetime | None = None
    review_reason: str | None = None
    approved_entry_id: str | None = None

    def __post_init__(self) -> None:
        self.agent_id = self.agent_id.strip()
        self.title = self.title.strip()
        self.content = self.content.strip()
        self.summary = self.summary.strip()
        self.tags = tuple(
            dict.fromkeys(
                tag.strip().lower()
                for tag in self.tags
                if tag is not None and tag.strip()
            ),
        )
        self.metadata = dict(self.metadata)
        self.review_reason = (
            self.review_reason.strip() if self.review_reason is not None else None
        )
        if not self.agent_id:
            raise MemoryValidationError("Memory candidate agent_id cannot be empty.")
        if not self.title:
            raise MemoryValidationError("Memory candidate title cannot be empty.")
        if not self.content:
            raise MemoryValidationError("Memory candidate content cannot be empty.")

    @classmethod
    def create(
        cls,
        *,
        candidate_id: str,
        agent_id: str,
        title: str,
        content: str,
        summary: str = "",
        session_key: str | None = None,
        run_id: str | None = None,
        tags: tuple[str, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> "MemoryCandidate":
        candidate = cls(
            id=candidate_id,
            agent_id=agent_id,
            title=title,
            content=content,
            summary=summary,
            session_key=session_key,
            run_id=run_id,
            tags=tags,
            metadata=metadata or {},
        )
        candidate.record_event(
            DomainEvent(
                name="memory.candidate.created",
                payload={
                    "candidate_id": candidate.id,
                    "agent_id": candidate.agent_id,
                },
            ),
        )
        return candidate

    def approve(self, *, entry_id: str) -> MemoryEntry:
        if self.status is not MemoryCandidateStatus.PENDING:
            raise MemoryCandidateAlreadyReviewedError(
                f"Memory candidate '{self.id}' has already been reviewed.",
            )

        entry = MemoryEntry.create(
            entry_id=entry_id,
            agent_id=self.agent_id,
            title=self.title,
            content=self.content,
            summary=self.summary,
            session_key=self.session_key,
            run_id=self.run_id,
            source_candidate_id=self.id,
            tags=self.tags,
            metadata=self.metadata,
        )
        self.status = MemoryCandidateStatus.APPROVED
        self.reviewed_at = entry.created_at
        self.review_reason = None
        self.approved_entry_id = entry.id
        self.record_event(
            DomainEvent(
                name="memory.candidate.approved",
                payload={
                    "candidate_id": self.id,
                    "entry_id": entry.id,
                    "agent_id": self.agent_id,
                },
            ),
        )
        return entry

    def record(self, *, entry_id: str) -> None:
        if self.status is not MemoryCandidateStatus.PENDING:
            raise MemoryCandidateAlreadyReviewedError(
                f"Memory candidate '{self.id}' has already been reviewed.",
            )
        self.approved_entry_id = entry_id
        self.record_event(
            DomainEvent(
                name="memory.candidate.recorded",
                payload={
                    "candidate_id": self.id,
                    "entry_id": entry_id,
                    "agent_id": self.agent_id,
                },
            ),
        )

    def mark_approved(self) -> None:
        if self.status is not MemoryCandidateStatus.PENDING:
            raise MemoryCandidateAlreadyReviewedError(
                f"Memory candidate '{self.id}' has already been reviewed.",
            )
        self.status = MemoryCandidateStatus.APPROVED
        self.reviewed_at = datetime.now(timezone.utc)
        self.review_reason = None
        self.record_event(
            DomainEvent(
                name="memory.candidate.approved",
                payload={
                    "candidate_id": self.id,
                    "entry_id": self.approved_entry_id,
                    "agent_id": self.agent_id,
                },
            ),
        )

    def reject(self, *, reason: str) -> None:
        if self.status is not MemoryCandidateStatus.PENDING:
            raise MemoryCandidateAlreadyReviewedError(
                f"Memory candidate '{self.id}' has already been reviewed.",
            )
        normalized_reason = reason.strip() or "rejected"
        self.status = MemoryCandidateStatus.REJECTED
        self.reviewed_at = datetime.now(timezone.utc)
        self.review_reason = normalized_reason
        self.approved_entry_id = None
        self.record_event(
            DomainEvent(
                name="memory.candidate.rejected",
                payload={
                    "candidate_id": self.id,
                    "agent_id": self.agent_id,
                    "reason": normalized_reason,
                },
            ),
        )
