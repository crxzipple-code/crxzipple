from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from crxzipple.core.db import Base


class SessionModel(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    active_session_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    agent_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    channel: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    chat_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    origin_payload: Mapped[dict[str, object]] = mapped_column(
        JSON(),
        nullable=False,
        default=dict,
    )
    delivery_payload: Mapped[dict[str, object]] = mapped_column(
        JSON(),
        nullable=False,
        default=dict,
    )
    metadata_payload: Mapped[dict[str, object]] = mapped_column(
        JSON(),
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_reset_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SessionMessageModel(Base):
    __tablename__ = "session_messages"
    __table_args__ = (
        Index(
            "ix_session_messages_session_sequence",
            "session_key",
            "session_id",
            "sequence_no",
        ),
        Index(
            "ix_session_messages_session_source",
            "session_key",
            "session_id",
            "source_kind",
            "source_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    session_key: Mapped[str] = mapped_column(
        ForeignKey("sessions.id"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    sequence_no: Mapped[int] = mapped_column(Integer(), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    kind: Mapped[str] = mapped_column(String(50), nullable=False, default="message")
    content_payload: Mapped[dict[str, object]] = mapped_column(
        JSON(),
        nullable=False,
        default=dict,
    )
    source_kind: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    visibility: Mapped[str] = mapped_column(String(50), nullable=False, default="default")
    metadata_payload: Mapped[dict[str, object]] = mapped_column(
        JSON(),
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SessionInstanceModel(Base):
    __tablename__ = "session_instances"
    __table_args__ = (
        Index(
            "ix_session_instances_session_sequence",
            "session_key",
            "sequence_no",
        ),
    )

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    session_key: Mapped[str] = mapped_column(
        ForeignKey("sessions.id"),
        nullable=False,
        index=True,
    )
    sequence_no: Mapped[int] = mapped_column(Integer(), nullable=False)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    reset_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    metadata_payload: Mapped[dict[str, object]] = mapped_column(
        JSON(),
        nullable=False,
        default=dict,
    )
