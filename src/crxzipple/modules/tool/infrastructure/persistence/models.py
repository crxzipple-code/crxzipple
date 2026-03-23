from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from crxzipple.core.db import Base


class ToolModel(Base):
    __tablename__ = "tools"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text(), nullable=False)
    kind: Mapped[str] = mapped_column(String(50), nullable=False, default="function")
    parameters: Mapped[list[dict[str, object]]] = mapped_column(
        JSON(),
        nullable=False,
        default=list,
    )
    tags: Mapped[list[str]] = mapped_column(JSON(), nullable=False, default=list)
    requires_confirmation: Mapped[bool] = mapped_column(nullable=False, default=False)
    mutates_state: Mapped[bool] = mapped_column(nullable=False, default=False)
    timeout_seconds: Mapped[int] = mapped_column(
        Integer(),
        nullable=False,
        default=30,
    )
    supported_modes: Mapped[list[str]] = mapped_column(JSON(), nullable=False, default=list)
    supported_strategies: Mapped[list[str]] = mapped_column(
        JSON(),
        nullable=False,
        default=list,
    )
    supported_environments: Mapped[list[str]] = mapped_column(
        JSON(),
        nullable=False,
        default=list,
    )
    source_kind: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")
    runtime_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)


class ToolRunModel(Base):
    __tablename__ = "tool_runs"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    tool_id: Mapped[str] = mapped_column(
        ForeignKey("tools.id"),
        nullable=False,
        index=True,
    )
    mode: Mapped[str] = mapped_column(String(50), nullable=False)
    strategy: Mapped[str] = mapped_column(String(50), nullable=False)
    environment: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    input_payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    output_payload: Mapped[object | None] = mapped_column(JSON(), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    attempt_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer(), nullable=False, default=3)
    worker_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
