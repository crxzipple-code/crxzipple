from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, text
from sqlalchemy.orm import Mapped, mapped_column

from crxzipple.core.db import Base


class OrchestrationRunModel(Base):
    __tablename__ = "orchestration_runs"
    __table_args__ = (
        Index(
            "uq_orchestration_runs_active_lane",
            "lane_lock_key",
            unique=True,
            sqlite_where=text(
                "lane_lock_key IS NOT NULL AND status IN ('running', 'waiting')",
            ),
            postgresql_where=text(
                "lane_lock_key IS NOT NULL AND status IN ('running', 'waiting')",
            ),
        ),
    )

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
    lane_lock_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
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
    reply_target_payload: Mapped[dict[str, object] | None] = mapped_column(
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


class OrchestrationIngressRequestModel(Base):
    __tablename__ = "orchestration_ingress_requests"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("orchestration_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(50), nullable=False, default="routed_turn")
    route_context_payload: Mapped[dict[str, object]] = mapped_column(
        JSON(),
        nullable=False,
        default=dict,
    )
    bound_session_payload: Mapped[dict[str, object]] = mapped_column(
        JSON(),
        nullable=False,
        default=dict,
    )
    requested_llm_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ensure_session: Mapped[bool] = mapped_column(nullable=False, default=True)
    touch_activity: Mapped[bool] = mapped_column(nullable=False, default=True)
    reset_policy_payload: Mapped[dict[str, object]] = mapped_column(
        JSON(),
        nullable=False,
        default=dict,
    )
    prepare_metadata_payload: Mapped[dict[str, object]] = mapped_column(
        JSON(),
        nullable=False,
        default=dict,
    )
    queue_policy: Mapped[str] = mapped_column(String(50), nullable=False, default="fifo")
    priority: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    error_payload: Mapped[dict[str, object] | None] = mapped_column(JSON(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OrchestrationSchedulerSignalModel(Base):
    __tablename__ = "orchestration_scheduler_signals"

    id: Mapped[str] = mapped_column(String(150), primary_key=True)
    signal_kind: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    signal_payload: Mapped[dict[str, object]] = mapped_column(
        JSON(),
        nullable=False,
        default=dict,
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    worker_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    error_payload: Mapped[dict[str, object] | None] = mapped_column(JSON(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OrchestrationExecutorLeaseModel(Base):
    __tablename__ = "orchestration_executor_leases"

    worker_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    max_inflight_assignments: Mapped[int] = mapped_column(
        Integer(),
        nullable=False,
        default=1,
    )
    inflight_assignment_count: Mapped[int] = mapped_column(
        Integer(),
        nullable=False,
        default=0,
    )
    metadata_payload: Mapped[dict[str, object]] = mapped_column(
        JSON(),
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
