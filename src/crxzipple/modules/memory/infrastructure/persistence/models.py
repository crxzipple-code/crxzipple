from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from crxzipple.core.db import Base


class MemoryCandidateModel(Base):
    __tablename__ = "memory_candidates"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    session_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    run_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text(), nullable=False)
    summary: Mapped[str] = mapped_column(Text(), nullable=False, default="")
    tags_payload: Mapped[list[str]] = mapped_column(JSON(), nullable=False, default=list)
    metadata_payload: Mapped[dict[str, object]] = mapped_column(
        JSON(),
        nullable=False,
        default=dict,
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    review_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    approved_entry_id: Mapped[str | None] = mapped_column(String(100), nullable=True)


class MemoryEntryModel(Base):
    __tablename__ = "memory_entries"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    session_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    run_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    source_candidate_id: Mapped[str | None] = mapped_column(
        ForeignKey("memory_candidates.id"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text(), nullable=False)
    summary: Mapped[str] = mapped_column(Text(), nullable=False, default="")
    tags_payload: Mapped[list[str]] = mapped_column(JSON(), nullable=False, default=list)
    metadata_payload: Mapped[dict[str, object]] = mapped_column(
        JSON(),
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
