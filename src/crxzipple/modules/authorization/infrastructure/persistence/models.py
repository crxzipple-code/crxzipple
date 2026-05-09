from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from crxzipple.core.db import Base


class AuthorizationPolicyModel(Base):
    __tablename__ = "authorization_policies"

    policy_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    effect: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    actions_payload: Mapped[list[str]] = mapped_column(JSON(), nullable=False)
    subject_type: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
        index=True,
    )
    subject_id: Mapped[str | None] = mapped_column(
        String(240),
        nullable=True,
        index=True,
    )
    subject_match_payload: Mapped[dict[str, object]] = mapped_column(
        JSON(),
        nullable=False,
    )
    resource_kind: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
        index=True,
    )
    resource_id: Mapped[str | None] = mapped_column(
        String(240),
        nullable=True,
        index=True,
    )
    resource_match_payload: Mapped[dict[str, object]] = mapped_column(
        JSON(),
        nullable=False,
    )
    context_match_payload: Mapped[dict[str, object]] = mapped_column(
        JSON(),
        nullable=False,
    )
    condition_payload: Mapped[dict[str, object] | None] = mapped_column(
        JSON(),
        nullable=True,
    )
    obligations_payload: Mapped[list[object]] = mapped_column(JSON(), nullable=False)
    priority: Mapped[int] = mapped_column(Integer(), nullable=False, default=0, index=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        default=True,
        index=True,
    )
    source_kind: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default="imported",
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TemporaryAuthorizationGrantModel(Base):
    __tablename__ = "authorization_temporary_grants"

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    run_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    session_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    approval_request_id: Mapped[str | None] = mapped_column(
        String(160),
        nullable=True,
        index=True,
    )
    effect_ids_payload: Mapped[list[str]] = mapped_column(
        JSON(),
        nullable=False,
        default=list,
    )
    tool_ids_payload: Mapped[list[str]] = mapped_column(
        JSON(),
        nullable=False,
        default=list,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuthorizationAuditModel(Base):
    __tablename__ = "authorization_action_audits"

    audit_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    actor_type: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
        index=True,
    )
    actor_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    target_policy_id: Mapped[str | None] = mapped_column(
        String(160),
        nullable=True,
        index=True,
    )
    reason: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    before_payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    after_payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    decision_payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    metadata_payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
