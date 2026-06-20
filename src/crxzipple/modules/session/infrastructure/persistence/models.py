from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String
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
    reply_payload: Mapped[dict[str, object]] = mapped_column(
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


class SessionItemModel(Base):
    __tablename__ = "session_items"
    __table_args__ = (
        Index(
            "ix_session_items_session_sequence",
            "session_key",
            "session_id",
            "sequence_no",
        ),
        Index(
            "ix_session_items_source",
            "source_module",
            "source_kind",
            "source_id",
        ),
        Index("ix_session_items_call_id", "call_id"),
    )

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    session_key: Mapped[str] = mapped_column(
        ForeignKey("sessions.id"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    sequence_no: Mapped[int] = mapped_column(Integer(), nullable=False)
    kind: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    phase: Mapped[str] = mapped_column(String(100), nullable=False, default="unknown")
    content_payload: Mapped[dict[str, object]] = mapped_column(
        JSON(),
        nullable=False,
        default=dict,
    )
    source_module: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_kind: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_item_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_item_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    call_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_visible: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    user_visible: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    chat_visible: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    trace_visible: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
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
