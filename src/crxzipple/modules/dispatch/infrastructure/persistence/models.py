from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from crxzipple.core.db import Base


class DispatchTaskModel(Base):
    __tablename__ = "dispatch_tasks"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    owner_kind: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    owner_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    lane_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    policy: Mapped[str] = mapped_column(String(50), nullable=False, default="fifo")
    priority: Mapped[int] = mapped_column(Integer(), nullable=False, default=100)
    payload_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_payload: Mapped[dict[str, object]] = mapped_column(
        JSON(),
        nullable=False,
        default=dict,
    )
    waiting_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_payload: Mapped[dict[str, object] | None] = mapped_column(JSON(), nullable=True)
    claimed_by: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    claim_token: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
