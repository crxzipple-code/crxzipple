from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from crxzipple.core.db import Base


class SettingsResourceModel(Base):
    __tablename__ = "settings_resources"

    resource_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    resource_kind: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    governance_scope: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    config_contract: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    contract_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    storage_key: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    consumer_modules: Mapped[list[str]] = mapped_column(JSON(), nullable=False)
    resolution_policy: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    supports_create: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    supports_update: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    supports_delete: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    supports_enable: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    supports_disable: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    supports_import: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    supports_export: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    validation_policy: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    dry_run_policy: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    audit_required: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    secret_policy: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    latest_version_number: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    published_version_id: Mapped[str | None] = mapped_column(
        String(160),
        nullable=True,
        index=True,
    )
    published_version_number: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    degraded_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    metadata_: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSON(),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )


class SettingsResourceVersionModel(Base):
    __tablename__ = "settings_resource_versions"
    __table_args__ = (
        UniqueConstraint(
            "resource_id",
            "version_number",
            name="uq_settings_resource_versions_resource_version",
        ),
    )

    version_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    resource_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    resource_kind: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer(), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_metadata: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    contract_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    redaction_policy: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    validation_result_id: Mapped[str | None] = mapped_column(
        String(160),
        nullable=True,
        index=True,
    )
    created_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    metadata_: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSON(),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SettingsEffectiveSnapshotModel(Base):
    __tablename__ = "settings_effective_snapshots"
    __table_args__ = (
        Index(
            "ix_settings_effective_snapshots_resource_scope_current",
            "resource_id",
            "scope_key",
            "is_current",
        ),
    )

    snapshot_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    resource_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    resource_kind: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    scope_key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    version_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    version_number: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    effective_payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    resolution_trace: Mapped[list[dict[str, object]]] = mapped_column(
        JSON(),
        nullable=False,
    )
    sources: Mapped[list[dict[str, object]]] = mapped_column(JSON(), nullable=False)
    overrides_applied: Mapped[list[dict[str, object]]] = mapped_column(
        JSON(),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    metadata_: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSON(),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )


class SettingsOverrideModel(Base):
    __tablename__ = "settings_overrides"

    override_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    resource_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    resource_kind: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    override_kind: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    scope_key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    priority: Mapped[int] = mapped_column(Integer(), nullable=False, default=100)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    override_payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    actor: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    redaction_policy: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    metadata_: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSON(),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )


class SettingsValidationResultModel(Base):
    __tablename__ = "settings_validation_results"

    validation_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    resource_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    resource_kind: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    version_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    audit_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    validator: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    valid: Mapped[bool] = mapped_column(Boolean(), nullable=False, index=True)
    issues: Mapped[list[dict[str, object]]] = mapped_column(JSON(), nullable=False)
    checked_payload_digest: Mapped[str | None] = mapped_column(String(160), nullable=True)
    redaction_policy: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    metadata_: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSON(),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )


class SettingsActionAuditModel(Base):
    __tablename__ = "settings_action_audits"

    audit_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    action_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    action_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    target_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    resource_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    resource_kind: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    actor: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    risk: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    confirmation: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    risk_acknowledged: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        default=False,
    )
    request_metadata: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    result: Mapped[dict[str, object] | None] = mapped_column(JSON(), nullable=True)
    error: Mapped[dict[str, object] | None] = mapped_column(JSON(), nullable=True)
    redaction_policy: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    trace_context: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
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
