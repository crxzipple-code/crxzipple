from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from crxzipple.core.db import Base


class SkillSourceModel(Base):
    __tablename__ = "skill_sources"

    source_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    source_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    root_uri: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    sync_status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    scope: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    priority: Mapped[int] = mapped_column(Integer(), nullable=False, default=100)
    enabled: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    readonly: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    metadata_payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class SkillPackageIndexModel(Base):
    __tablename__ = "skill_packages"
    __table_args__ = (
        UniqueConstraint("source_id", "name", name="uq_skill_packages_source_name"),
        UniqueConstraint(
            "source_id", "skill_id", name="uq_skill_packages_source_skill"
        ),
    )

    package_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    skill_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    root_uri: Mapped[str] = mapped_column(String(1000), nullable=False)
    manifest_uri: Mapped[str] = mapped_column(String(1000), nullable=False)
    instructions_uri: Mapped[str] = mapped_column(String(1000), nullable=False)
    version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    requirements_payload: Mapped[dict[str, object]] = mapped_column(
        JSON(), nullable=False
    )
    capability_requirements_payload: Mapped[dict[str, object]] = mapped_column(
        JSON(),
        nullable=False,
    )
    metadata_payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    indexed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class SkillEnablementPolicyModel(Base):
    __tablename__ = "skill_enablement_policies"

    policy_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    target_kind: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    target_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    trusted: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    runtime_visibility: Mapped[str] = mapped_column(
        String(60), nullable=False, index=True
    )
    priority: Mapped[int] = mapped_column(Integer(), nullable=False, default=100)
    reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    metadata_payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class SkillReadinessSnapshotModel(Base):
    __tablename__ = "skill_readiness"

    skill_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    source_id: Mapped[str | None] = mapped_column(
        String(120), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    checks_payload: Mapped[list[dict[str, object]]] = mapped_column(
        JSON(), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    metadata_payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class SkillInstallationModel(Base):
    __tablename__ = "skill_installations"

    installation_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source_id: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
        index=True,
    )
    skill_id: Mapped[str | None] = mapped_column(
        String(160),
        nullable=True,
        index=True,
    )
    skill_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    source_uri: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    target_uri: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    metadata_payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )


class SkillAuthoringDraftModel(Base):
    __tablename__ = "skill_authoring_drafts"

    draft_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    intent: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    skill_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    target_source_id: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
        index=True,
    )
    target_scope: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    workspace_dir: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    base_fingerprint: Mapped[str | None] = mapped_column(String(160), nullable=True)
    manifest_payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    instructions_body: Mapped[str] = mapped_column(Text(), nullable=False)
    support_files_payload: Mapped[list[dict[str, object]]] = mapped_column(
        JSON(),
        nullable=False,
    )
    requirements_payload: Mapped[dict[str, object]] = mapped_column(
        JSON(),
        nullable=False,
    )
    validation_payload: Mapped[dict[str, object] | None] = mapped_column(
        JSON(),
        nullable=True,
    )
    diff_payload: Mapped[dict[str, object] | None] = mapped_column(
        JSON(),
        nullable=True,
    )
    created_by_run_id: Mapped[str | None] = mapped_column(
        String(160),
        nullable=True,
        index=True,
    )
    created_by_turn_id: Mapped[str | None] = mapped_column(
        String(160),
        nullable=True,
    )
    actor: Mapped[str | None] = mapped_column(String(160), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
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
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )


class SkillAuthoringAuditModel(Base):
    __tablename__ = "skill_authoring_audit"

    audit_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    draft_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    actor: Mapped[str | None] = mapped_column(String(160), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    before_payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    after_payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    metadata_payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
