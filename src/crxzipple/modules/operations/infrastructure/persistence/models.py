from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from crxzipple.core.db import Base


class OperationsProjectionModel(Base):
    __tablename__ = "operations_projections"

    module: Mapped[str] = mapped_column(String(80), primary_key=True)
    kind: Mapped[str] = mapped_column(String(80), primary_key=True)
    query_key: Mapped[str] = mapped_column(
        String(160),
        primary_key=True,
        default="default",
    )
    version: Mapped[int] = mapped_column(Integer(), nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)


class OperationsObservedEventModel(Base):
    __tablename__ = "operations_observed_events"

    topic: Mapped[str] = mapped_column(String(240), primary_key=True)
    cursor: Mapped[str] = mapped_column(String(160), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    event_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    module: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    owner: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, default="fact")
    level: Mapped[str] = mapped_column(String(40), nullable=False, default="info")
    status: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    run_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    trace_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    source_event_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )


class OperationsModuleObservationModel(Base):
    __tablename__ = "operations_module_observations"

    module: Mapped[str] = mapped_column(String(80), primary_key=True)
    owner: Mapped[str] = mapped_column(String(80), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    event_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    status_counts: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    event_name_counts: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    last_event_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_event_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    last_topic: Mapped[str | None] = mapped_column(String(240), nullable=True)
    last_cursor: Mapped[str | None] = mapped_column(String(160), nullable=True)
    last_event_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )


class OperationsObserverHeartbeatModel(Base):
    __tablename__ = "operations_observer_heartbeats"

    runtime_name: Mapped[str] = mapped_column(String(120), primary_key=True)
    worker_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    processed_events: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    idle_cycles: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    subscription_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    poll_interval_seconds: Mapped[float | None] = mapped_column(Float(), nullable=True)
    limit_per_subscription: Mapped[int | None] = mapped_column(Integer(), nullable=True)


class OperationsEventTimeBucketModel(Base):
    __tablename__ = "operations_event_time_buckets"

    module: Mapped[str] = mapped_column(String(80), primary_key=True)
    event_name: Mapped[str] = mapped_column(String(160), primary_key=True)
    status: Mapped[str] = mapped_column(String(80), primary_key=True)
    bucket_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
    )
    owner: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )


class OperationsActionAuditModel(Base):
    __tablename__ = "operations_action_audits"

    audit_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    action_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    target_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    target: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    dangerous: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    risk: Mapped[str] = mapped_column(String(40), nullable=False, default="normal")
    confirmation: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    risk_acknowledged: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        default=False,
    )
    operator: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source: Mapped[str] = mapped_column(String(120), nullable=False, default="operations")
    metadata_: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSON(),
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    result: Mapped[dict[str, object] | None] = mapped_column(JSON(), nullable=True)
    error: Mapped[dict[str, object] | None] = mapped_column(JSON(), nullable=True)
