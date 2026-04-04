from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from crxzipple.core.db import Base


class OrchestrationRunModel(Base):
    __tablename__ = "orchestration_runs"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    active_session_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
    agent_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    lane_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    queue_policy: Mapped[str] = mapped_column(String(50), nullable=False, default="fifo")
    priority: Mapped[int] = mapped_column(Integer(), nullable=False, default=100)
    current_step: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    max_steps: Mapped[int] = mapped_column(Integer(), nullable=False, default=99)
    pending_tool_run_ids: Mapped[list[str]] = mapped_column(
        JSON(),
        nullable=False,
        default=list,
    )
    waiting_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    inbound_instruction_payload: Mapped[dict[str, object]] = mapped_column(
        JSON(),
        nullable=False,
        default=dict,
    )
    delivery_target_payload: Mapped[dict[str, object] | None] = mapped_column(
        JSON(),
        nullable=True,
    )
    result_payload: Mapped[dict[str, object] | None] = mapped_column(JSON(), nullable=True)
    error_payload: Mapped[dict[str, object] | None] = mapped_column(JSON(), nullable=True)
    metadata_payload: Mapped[dict[str, object]] = mapped_column(
        JSON(),
        nullable=False,
        default=dict,
    )
    worker_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class OrchestrationRunWaitModel(Base):
    __tablename__ = "orchestration_run_waits"

    run_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("orchestration_runs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tool_run_id: Mapped[str] = mapped_column(String(100), primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
