from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from crxzipple.core.db import Base


class EventOutboxRecordModel(Base):
    __tablename__ = "event_outbox_records"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    topic: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    event_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    event_payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    publisher_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    claim_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
