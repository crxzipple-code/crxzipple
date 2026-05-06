from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, JSON, String
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
