from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from crxzipple.core.db import Base


class AccessAssetModel(Base):
    __tablename__ = "access_assets"

    asset_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    asset_kind: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    governance_scope: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    secret_policy: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(240), nullable=True, index=True)
    consumer_modules: Mapped[list[str]] = mapped_column(JSON(), nullable=False)
    readiness_policy: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    rotation_policy: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    audit_required: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    export_policy: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    degraded_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
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


class AccessCredentialBindingModel(Base):
    __tablename__ = "access_credential_bindings"

    binding_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    asset_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    binding_kind: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_kind: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    masked_preview: Mapped[str | None] = mapped_column(String(240), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
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


class AccessConsumerBindingModel(Base):
    __tablename__ = "access_consumer_bindings"

    binding_id: Mapped[str] = mapped_column(String(180), primary_key=True)
    consumer_module: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    consumer_kind: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    consumer_id: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    asset_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    credential_binding_id: Mapped[str | None] = mapped_column(
        String(160),
        nullable=True,
        index=True,
    )
    requirement_sets: Mapped[list[list[str]]] = mapped_column(JSON(), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
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


class AccessSecretBindingModel(Base):
    __tablename__ = "access_secret_bindings"

    binding_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    credential_binding_id: Mapped[str | None] = mapped_column(
        String(160),
        nullable=True,
        index=True,
    )
    storage_key: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    source_kind: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    masked_preview: Mapped[str | None] = mapped_column(String(240), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
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


class AccessConnectionProfileModel(Base):
    __tablename__ = "access_connection_profiles"

    profile_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    asset_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    profile_kind: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    endpoint_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    credential_binding_id: Mapped[str | None] = mapped_column(
        String(160),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
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


class AccessSetupSessionModel(Base):
    __tablename__ = "access_setup_sessions"

    session_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    target_kind: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    flow_kind: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    requested_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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


class AccessReadinessSnapshotModel(Base):
    __tablename__ = "access_readiness_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    target_kind: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    ready: Mapped[bool] = mapped_column(Boolean(), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    checks: Mapped[list[dict[str, object]]] = mapped_column(JSON(), nullable=False)
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


class AccessActionAuditModel(Base):
    __tablename__ = "access_action_audits"

    audit_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    action_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    target_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    operator: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    request_metadata: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    result: Mapped[dict[str, object] | None] = mapped_column(JSON(), nullable=True)
    error: Mapped[dict[str, object] | None] = mapped_column(JSON(), nullable=True)
    redaction_policy: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
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
