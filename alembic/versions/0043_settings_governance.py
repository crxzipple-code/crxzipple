"""settings governance persistence

Revision ID: 0043_settings_governance
Revises: 0042_access_governance_persistence
Create Date: 2026-05-07 09:45:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0043_settings_governance"
down_revision = "0042_access_governance_persistence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("settings_resources"):
        op.create_table(
            "settings_resources",
            sa.Column("resource_id", sa.String(length=160), nullable=False),
            sa.Column("resource_kind", sa.String(length=80), nullable=False),
            sa.Column("display_name", sa.String(length=240), nullable=True),
            sa.Column("governance_scope", sa.String(length=120), nullable=False),
            sa.Column("config_contract", sa.JSON(), nullable=False),
            sa.Column("contract_version", sa.String(length=80), nullable=True),
            sa.Column("storage_key", sa.String(length=320), nullable=False),
            sa.Column("consumer_modules", sa.JSON(), nullable=False),
            sa.Column("resolution_policy", sa.JSON(), nullable=False),
            sa.Column(
                "supports_create",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "supports_update",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "supports_delete",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "supports_enable",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "supports_disable",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "supports_import",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "supports_export",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column("validation_policy", sa.JSON(), nullable=False),
            sa.Column("dry_run_policy", sa.JSON(), nullable=False),
            sa.Column(
                "audit_required",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column("secret_policy", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("latest_version_number", sa.Integer(), nullable=True),
            sa.Column("published_version_id", sa.String(length=160), nullable=True),
            sa.Column("published_version_number", sa.Integer(), nullable=True),
            sa.Column("degraded_reason", sa.String(length=1000), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("resource_id", name="pk_settings_resources"),
        )
        _create_indexes(
            "settings_resources",
            (
                ("ix_settings_resources_resource_kind", ["resource_kind"]),
                ("ix_settings_resources_governance_scope", ["governance_scope"]),
                ("ix_settings_resources_storage_key", ["storage_key"]),
                ("ix_settings_resources_status", ["status"]),
                ("ix_settings_resources_published_version_id", ["published_version_id"]),
                ("ix_settings_resources_updated_at", ["updated_at"]),
            ),
        )

    if not inspector.has_table("settings_resource_versions"):
        op.create_table(
            "settings_resource_versions",
            sa.Column("version_id", sa.String(length=160), nullable=False),
            sa.Column("resource_id", sa.String(length=160), nullable=False),
            sa.Column("resource_kind", sa.String(length=80), nullable=False),
            sa.Column("version_number", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("source_kind", sa.String(length=80), nullable=False),
            sa.Column("source_ref", sa.String(length=500), nullable=True),
            sa.Column("source_metadata", sa.JSON(), nullable=False),
            sa.Column("contract_version", sa.String(length=80), nullable=True),
            sa.Column("redaction_policy", sa.JSON(), nullable=False),
            sa.Column("validation_result_id", sa.String(length=160), nullable=True),
            sa.Column("created_by", sa.String(length=200), nullable=True),
            sa.Column("reason", sa.String(length=1000), nullable=True),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint(
                "version_id",
                name="pk_settings_resource_versions",
            ),
            sa.UniqueConstraint(
                "resource_id",
                "version_number",
                name="uq_settings_resource_versions_resource_version",
            ),
        )
        _create_indexes(
            "settings_resource_versions",
            (
                ("ix_settings_resource_versions_resource_id", ["resource_id"]),
                ("ix_settings_resource_versions_resource_kind", ["resource_kind"]),
                ("ix_settings_resource_versions_status", ["status"]),
                ("ix_settings_resource_versions_source_kind", ["source_kind"]),
                (
                    "ix_settings_resource_versions_validation_result_id",
                    ["validation_result_id"],
                ),
                ("ix_settings_resource_versions_published_at", ["published_at"]),
                ("ix_settings_resource_versions_created_at", ["created_at"]),
            ),
        )

    if not inspector.has_table("settings_effective_snapshots"):
        op.create_table(
            "settings_effective_snapshots",
            sa.Column("snapshot_id", sa.String(length=160), nullable=False),
            sa.Column("resource_id", sa.String(length=160), nullable=False),
            sa.Column("resource_kind", sa.String(length=80), nullable=False),
            sa.Column("scope_key", sa.String(length=200), nullable=False),
            sa.Column("version_id", sa.String(length=160), nullable=True),
            sa.Column("version_number", sa.Integer(), nullable=True),
            sa.Column("effective_payload", sa.JSON(), nullable=False),
            sa.Column("resolution_trace", sa.JSON(), nullable=False),
            sa.Column("sources", sa.JSON(), nullable=False),
            sa.Column("overrides_applied", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column(
                "is_current",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint(
                "snapshot_id",
                name="pk_settings_effective_snapshots",
            ),
        )
        _create_indexes(
            "settings_effective_snapshots",
            (
                ("ix_settings_effective_snapshots_resource_id", ["resource_id"]),
                ("ix_settings_effective_snapshots_resource_kind", ["resource_kind"]),
                ("ix_settings_effective_snapshots_scope_key", ["scope_key"]),
                ("ix_settings_effective_snapshots_version_id", ["version_id"]),
                ("ix_settings_effective_snapshots_status", ["status"]),
                ("ix_settings_effective_snapshots_generated_at", ["generated_at"]),
                ("ix_settings_effective_snapshots_updated_at", ["updated_at"]),
                (
                    "ix_settings_effective_snapshots_resource_scope_current",
                    ["resource_id", "scope_key", "is_current"],
                ),
            ),
        )

    if not inspector.has_table("settings_overrides"):
        op.create_table(
            "settings_overrides",
            sa.Column("override_id", sa.String(length=160), nullable=False),
            sa.Column("resource_id", sa.String(length=160), nullable=False),
            sa.Column("resource_kind", sa.String(length=80), nullable=False),
            sa.Column("override_kind", sa.String(length=80), nullable=False),
            sa.Column("scope_key", sa.String(length=200), nullable=False),
            sa.Column(
                "priority",
                sa.Integer(),
                nullable=False,
                server_default="100",
            ),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("override_payload", sa.JSON(), nullable=False),
            sa.Column("source_kind", sa.String(length=80), nullable=False),
            sa.Column("source_ref", sa.String(length=500), nullable=True),
            sa.Column("reason", sa.String(length=1000), nullable=True),
            sa.Column("actor", sa.String(length=200), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("redaction_policy", sa.JSON(), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("override_id", name="pk_settings_overrides"),
        )
        _create_indexes(
            "settings_overrides",
            (
                ("ix_settings_overrides_resource_id", ["resource_id"]),
                ("ix_settings_overrides_resource_kind", ["resource_kind"]),
                ("ix_settings_overrides_override_kind", ["override_kind"]),
                ("ix_settings_overrides_scope_key", ["scope_key"]),
                ("ix_settings_overrides_status", ["status"]),
                ("ix_settings_overrides_source_kind", ["source_kind"]),
                ("ix_settings_overrides_actor", ["actor"]),
                ("ix_settings_overrides_expires_at", ["expires_at"]),
                ("ix_settings_overrides_updated_at", ["updated_at"]),
            ),
        )

    if not inspector.has_table("settings_validation_results"):
        op.create_table(
            "settings_validation_results",
            sa.Column("validation_id", sa.String(length=160), nullable=False),
            sa.Column("resource_id", sa.String(length=160), nullable=False),
            sa.Column("resource_kind", sa.String(length=80), nullable=False),
            sa.Column("version_id", sa.String(length=160), nullable=True),
            sa.Column("audit_id", sa.String(length=160), nullable=True),
            sa.Column("validator", sa.String(length=160), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("valid", sa.Boolean(), nullable=False),
            sa.Column("issues", sa.JSON(), nullable=False),
            sa.Column("checked_payload_digest", sa.String(length=160), nullable=True),
            sa.Column("redaction_policy", sa.JSON(), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint(
                "validation_id",
                name="pk_settings_validation_results",
            ),
        )
        _create_indexes(
            "settings_validation_results",
            (
                ("ix_settings_validation_results_resource_id", ["resource_id"]),
                ("ix_settings_validation_results_resource_kind", ["resource_kind"]),
                ("ix_settings_validation_results_version_id", ["version_id"]),
                ("ix_settings_validation_results_audit_id", ["audit_id"]),
                ("ix_settings_validation_results_validator", ["validator"]),
                ("ix_settings_validation_results_status", ["status"]),
                ("ix_settings_validation_results_valid", ["valid"]),
                ("ix_settings_validation_results_created_at", ["created_at"]),
            ),
        )

    if not inspector.has_table("settings_action_audits"):
        op.create_table(
            "settings_action_audits",
            sa.Column("audit_id", sa.String(length=160), nullable=False),
            sa.Column("action_id", sa.String(length=160), nullable=True),
            sa.Column("action_type", sa.String(length=120), nullable=False),
            sa.Column("target_type", sa.String(length=120), nullable=False),
            sa.Column("target_id", sa.String(length=200), nullable=True),
            sa.Column("resource_id", sa.String(length=160), nullable=True),
            sa.Column("resource_kind", sa.String(length=80), nullable=True),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("actor", sa.String(length=200), nullable=True),
            sa.Column("source", sa.String(length=120), nullable=False),
            sa.Column("reason", sa.String(length=1000), nullable=False),
            sa.Column("risk", sa.String(length=40), nullable=False),
            sa.Column(
                "confirmation",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column(
                "risk_acknowledged",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column("request_metadata", sa.JSON(), nullable=False),
            sa.Column("result", sa.JSON(), nullable=True),
            sa.Column("error", sa.JSON(), nullable=True),
            sa.Column("redaction_policy", sa.JSON(), nullable=False),
            sa.Column("trace_context", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("audit_id", name="pk_settings_action_audits"),
        )
        _create_indexes(
            "settings_action_audits",
            (
                ("ix_settings_action_audits_action_id", ["action_id"]),
                ("ix_settings_action_audits_action_type", ["action_type"]),
                ("ix_settings_action_audits_target_type", ["target_type"]),
                ("ix_settings_action_audits_target_id", ["target_id"]),
                ("ix_settings_action_audits_resource_id", ["resource_id"]),
                ("ix_settings_action_audits_resource_kind", ["resource_kind"]),
                ("ix_settings_action_audits_status", ["status"]),
                ("ix_settings_action_audits_actor", ["actor"]),
                ("ix_settings_action_audits_source", ["source"]),
                ("ix_settings_action_audits_risk", ["risk"]),
                ("ix_settings_action_audits_created_at", ["created_at"]),
                ("ix_settings_action_audits_updated_at", ["updated_at"]),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table_name, index_names in (
        (
            "settings_action_audits",
            (
                "ix_settings_action_audits_updated_at",
                "ix_settings_action_audits_created_at",
                "ix_settings_action_audits_risk",
                "ix_settings_action_audits_source",
                "ix_settings_action_audits_actor",
                "ix_settings_action_audits_status",
                "ix_settings_action_audits_resource_kind",
                "ix_settings_action_audits_resource_id",
                "ix_settings_action_audits_target_id",
                "ix_settings_action_audits_target_type",
                "ix_settings_action_audits_action_type",
                "ix_settings_action_audits_action_id",
            ),
        ),
        (
            "settings_validation_results",
            (
                "ix_settings_validation_results_created_at",
                "ix_settings_validation_results_valid",
                "ix_settings_validation_results_status",
                "ix_settings_validation_results_validator",
                "ix_settings_validation_results_audit_id",
                "ix_settings_validation_results_version_id",
                "ix_settings_validation_results_resource_kind",
                "ix_settings_validation_results_resource_id",
            ),
        ),
        (
            "settings_overrides",
            (
                "ix_settings_overrides_updated_at",
                "ix_settings_overrides_expires_at",
                "ix_settings_overrides_actor",
                "ix_settings_overrides_source_kind",
                "ix_settings_overrides_status",
                "ix_settings_overrides_scope_key",
                "ix_settings_overrides_override_kind",
                "ix_settings_overrides_resource_kind",
                "ix_settings_overrides_resource_id",
            ),
        ),
        (
            "settings_effective_snapshots",
            (
                "ix_settings_effective_snapshots_resource_scope_current",
                "ix_settings_effective_snapshots_updated_at",
                "ix_settings_effective_snapshots_generated_at",
                "ix_settings_effective_snapshots_status",
                "ix_settings_effective_snapshots_version_id",
                "ix_settings_effective_snapshots_scope_key",
                "ix_settings_effective_snapshots_resource_kind",
                "ix_settings_effective_snapshots_resource_id",
            ),
        ),
        (
            "settings_resource_versions",
            (
                "ix_settings_resource_versions_created_at",
                "ix_settings_resource_versions_published_at",
                "ix_settings_resource_versions_validation_result_id",
                "ix_settings_resource_versions_source_kind",
                "ix_settings_resource_versions_status",
                "ix_settings_resource_versions_resource_kind",
                "ix_settings_resource_versions_resource_id",
            ),
        ),
        (
            "settings_resources",
            (
                "ix_settings_resources_updated_at",
                "ix_settings_resources_published_version_id",
                "ix_settings_resources_status",
                "ix_settings_resources_storage_key",
                "ix_settings_resources_governance_scope",
                "ix_settings_resources_resource_kind",
            ),
        ),
    ):
        if not inspector.has_table(table_name):
            continue
        with op.batch_alter_table(table_name) as batch_op:
            for index_name in index_names:
                batch_op.drop_index(index_name)
        op.drop_table(table_name)


def _create_indexes(
    table_name: str,
    indexes: tuple[tuple[str, list[str]], ...],
) -> None:
    for index_name, columns in indexes:
        op.create_index(index_name, table_name, columns)
