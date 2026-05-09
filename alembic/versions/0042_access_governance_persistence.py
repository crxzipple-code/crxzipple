"""access governance persistence

Revision ID: 0042_access_governance_persistence
Revises: 0041_create_operations_action_audits
Create Date: 2026-05-06 20:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0042_access_governance_persistence"
down_revision = "0041_create_operations_action_audits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("access_assets"):
        op.create_table(
            "access_assets",
            sa.Column("asset_id", sa.String(length=120), nullable=False),
            sa.Column("asset_kind", sa.String(length=80), nullable=False),
            sa.Column("display_name", sa.String(length=200), nullable=False),
            sa.Column("governance_scope", sa.String(length=120), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("secret_policy", sa.JSON(), nullable=False),
            sa.Column("storage_key", sa.String(length=240), nullable=True),
            sa.Column("consumer_modules", sa.JSON(), nullable=False),
            sa.Column("readiness_policy", sa.JSON(), nullable=False),
            sa.Column("authorization_policy_id", sa.String(length=120), nullable=True),
            sa.Column("rotation_policy", sa.JSON(), nullable=False),
            sa.Column(
                "audit_required",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column("export_policy", sa.JSON(), nullable=False),
            sa.Column("degraded_reason", sa.String(length=1000), nullable=True),
            sa.Column("redaction_policy", sa.JSON(), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("asset_id", name="pk_access_assets"),
        )
        _create_indexes(
            "access_assets",
            (
                ("ix_access_assets_asset_kind", ["asset_kind"]),
                ("ix_access_assets_governance_scope", ["governance_scope"]),
                ("ix_access_assets_status", ["status"]),
                ("ix_access_assets_storage_key", ["storage_key"]),
                ("ix_access_assets_authorization_policy_id", ["authorization_policy_id"]),
                ("ix_access_assets_updated_at", ["updated_at"]),
            ),
        )

    if not inspector.has_table("access_credential_bindings"):
        op.create_table(
            "access_credential_bindings",
            sa.Column("binding_id", sa.String(length=160), nullable=False),
            sa.Column("asset_id", sa.String(length=120), nullable=True),
            sa.Column("binding_kind", sa.String(length=80), nullable=False),
            sa.Column("source_kind", sa.String(length=80), nullable=False),
            sa.Column("source_ref", sa.String(length=500), nullable=False),
            sa.Column("masked_preview", sa.String(length=240), nullable=True),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("redaction_policy", sa.JSON(), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint(
                "binding_id",
                name="pk_access_credential_bindings",
            ),
        )
        _create_indexes(
            "access_credential_bindings",
            (
                ("ix_access_credential_bindings_asset_id", ["asset_id"]),
                ("ix_access_credential_bindings_binding_kind", ["binding_kind"]),
                ("ix_access_credential_bindings_source_kind", ["source_kind"]),
                ("ix_access_credential_bindings_status", ["status"]),
                ("ix_access_credential_bindings_updated_at", ["updated_at"]),
            ),
        )

    if not inspector.has_table("access_consumer_bindings"):
        op.create_table(
            "access_consumer_bindings",
            sa.Column("binding_id", sa.String(length=180), nullable=False),
            sa.Column("consumer_module", sa.String(length=120), nullable=False),
            sa.Column("consumer_kind", sa.String(length=120), nullable=False),
            sa.Column("consumer_id", sa.String(length=240), nullable=False),
            sa.Column("display_name", sa.String(length=240), nullable=True),
            sa.Column(
                "enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column("asset_id", sa.String(length=120), nullable=True),
            sa.Column("credential_binding_id", sa.String(length=160), nullable=True),
            sa.Column("requirement_sets", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("redaction_policy", sa.JSON(), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint(
                "binding_id",
                name="pk_access_consumer_bindings",
            ),
        )
        _create_indexes(
            "access_consumer_bindings",
            (
                ("ix_access_consumer_bindings_consumer_module", ["consumer_module"]),
                ("ix_access_consumer_bindings_consumer_kind", ["consumer_kind"]),
                ("ix_access_consumer_bindings_consumer_id", ["consumer_id"]),
                ("ix_access_consumer_bindings_asset_id", ["asset_id"]),
                (
                    "ix_access_consumer_bindings_credential_binding_id",
                    ["credential_binding_id"],
                ),
                ("ix_access_consumer_bindings_status", ["status"]),
                ("ix_access_consumer_bindings_updated_at", ["updated_at"]),
            ),
        )

    if not inspector.has_table("access_secret_bindings"):
        op.create_table(
            "access_secret_bindings",
            sa.Column("binding_id", sa.String(length=160), nullable=False),
            sa.Column("credential_binding_id", sa.String(length=160), nullable=True),
            sa.Column("storage_key", sa.String(length=240), nullable=False),
            sa.Column("source_kind", sa.String(length=80), nullable=False),
            sa.Column("source_ref", sa.String(length=500), nullable=True),
            sa.Column("masked_preview", sa.String(length=240), nullable=True),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("redaction_policy", sa.JSON(), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("binding_id", name="pk_access_secret_bindings"),
        )
        _create_indexes(
            "access_secret_bindings",
            (
                ("ix_access_secret_bindings_credential_binding_id", ["credential_binding_id"]),
                ("ix_access_secret_bindings_storage_key", ["storage_key"]),
                ("ix_access_secret_bindings_source_kind", ["source_kind"]),
                ("ix_access_secret_bindings_status", ["status"]),
                ("ix_access_secret_bindings_updated_at", ["updated_at"]),
            ),
        )

    if not inspector.has_table("access_connection_profiles"):
        op.create_table(
            "access_connection_profiles",
            sa.Column("profile_id", sa.String(length=160), nullable=False),
            sa.Column("asset_id", sa.String(length=120), nullable=True),
            sa.Column("provider", sa.String(length=120), nullable=False),
            sa.Column("profile_kind", sa.String(length=80), nullable=False),
            sa.Column("endpoint_ref", sa.String(length=500), nullable=True),
            sa.Column("credential_binding_id", sa.String(length=160), nullable=True),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("redaction_policy", sa.JSON(), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("profile_id", name="pk_access_connection_profiles"),
        )
        _create_indexes(
            "access_connection_profiles",
            (
                ("ix_access_connection_profiles_asset_id", ["asset_id"]),
                ("ix_access_connection_profiles_provider", ["provider"]),
                ("ix_access_connection_profiles_profile_kind", ["profile_kind"]),
                ("ix_access_connection_profiles_credential_binding_id", ["credential_binding_id"]),
                ("ix_access_connection_profiles_status", ["status"]),
                ("ix_access_connection_profiles_updated_at", ["updated_at"]),
            ),
        )

    if not inspector.has_table("access_setup_sessions"):
        op.create_table(
            "access_setup_sessions",
            sa.Column("session_id", sa.String(length=160), nullable=False),
            sa.Column("target_kind", sa.String(length=80), nullable=False),
            sa.Column("target_id", sa.String(length=200), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("flow_kind", sa.String(length=80), nullable=False),
            sa.Column("requested_by", sa.String(length=200), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("redaction_policy", sa.JSON(), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("session_id", name="pk_access_setup_sessions"),
        )
        _create_indexes(
            "access_setup_sessions",
            (
                ("ix_access_setup_sessions_target_kind", ["target_kind"]),
                ("ix_access_setup_sessions_target_id", ["target_id"]),
                ("ix_access_setup_sessions_status", ["status"]),
                ("ix_access_setup_sessions_flow_kind", ["flow_kind"]),
                ("ix_access_setup_sessions_expires_at", ["expires_at"]),
                ("ix_access_setup_sessions_updated_at", ["updated_at"]),
            ),
        )

    if not inspector.has_table("access_readiness_snapshots"):
        op.create_table(
            "access_readiness_snapshots",
            sa.Column("snapshot_id", sa.String(length=160), nullable=False),
            sa.Column("target_kind", sa.String(length=80), nullable=False),
            sa.Column("target_id", sa.String(length=200), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("ready", sa.Boolean(), nullable=False),
            sa.Column("reason", sa.String(length=1000), nullable=True),
            sa.Column("checks", sa.JSON(), nullable=False),
            sa.Column("redaction_policy", sa.JSON(), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint(
                "snapshot_id",
                name="pk_access_readiness_snapshots",
            ),
        )
        _create_indexes(
            "access_readiness_snapshots",
            (
                ("ix_access_readiness_snapshots_target_kind", ["target_kind"]),
                ("ix_access_readiness_snapshots_target_id", ["target_id"]),
                ("ix_access_readiness_snapshots_status", ["status"]),
                ("ix_access_readiness_snapshots_ready", ["ready"]),
                ("ix_access_readiness_snapshots_created_at", ["created_at"]),
            ),
        )

    if not inspector.has_table("access_action_audits"):
        op.create_table(
            "access_action_audits",
            sa.Column("audit_id", sa.String(length=160), nullable=False),
            sa.Column("action_type", sa.String(length=120), nullable=False),
            sa.Column("target_type", sa.String(length=120), nullable=False),
            sa.Column("target_id", sa.String(length=200), nullable=True),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("operator", sa.String(length=200), nullable=True),
            sa.Column("source", sa.String(length=120), nullable=False),
            sa.Column("reason", sa.String(length=1000), nullable=False),
            sa.Column("request_metadata", sa.JSON(), nullable=False),
            sa.Column("result", sa.JSON(), nullable=True),
            sa.Column("error", sa.JSON(), nullable=True),
            sa.Column("redaction_policy", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("audit_id", name="pk_access_action_audits"),
        )
        _create_indexes(
            "access_action_audits",
            (
                ("ix_access_action_audits_action_type", ["action_type"]),
                ("ix_access_action_audits_target_type", ["target_type"]),
                ("ix_access_action_audits_target_id", ["target_id"]),
                ("ix_access_action_audits_status", ["status"]),
                ("ix_access_action_audits_source", ["source"]),
                ("ix_access_action_audits_created_at", ["created_at"]),
                ("ix_access_action_audits_updated_at", ["updated_at"]),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table_name, index_names in (
        (
            "access_action_audits",
            (
                "ix_access_action_audits_updated_at",
                "ix_access_action_audits_created_at",
                "ix_access_action_audits_source",
                "ix_access_action_audits_status",
                "ix_access_action_audits_target_id",
                "ix_access_action_audits_target_type",
                "ix_access_action_audits_action_type",
            ),
        ),
        (
            "access_readiness_snapshots",
            (
                "ix_access_readiness_snapshots_created_at",
                "ix_access_readiness_snapshots_ready",
                "ix_access_readiness_snapshots_status",
                "ix_access_readiness_snapshots_target_id",
                "ix_access_readiness_snapshots_target_kind",
            ),
        ),
        (
            "access_setup_sessions",
            (
                "ix_access_setup_sessions_updated_at",
                "ix_access_setup_sessions_expires_at",
                "ix_access_setup_sessions_flow_kind",
                "ix_access_setup_sessions_status",
                "ix_access_setup_sessions_target_id",
                "ix_access_setup_sessions_target_kind",
            ),
        ),
        (
            "access_connection_profiles",
            (
                "ix_access_connection_profiles_updated_at",
                "ix_access_connection_profiles_status",
                "ix_access_connection_profiles_credential_binding_id",
                "ix_access_connection_profiles_profile_kind",
                "ix_access_connection_profiles_provider",
                "ix_access_connection_profiles_asset_id",
            ),
        ),
        (
            "access_secret_bindings",
            (
                "ix_access_secret_bindings_updated_at",
                "ix_access_secret_bindings_status",
                "ix_access_secret_bindings_source_kind",
                "ix_access_secret_bindings_storage_key",
                "ix_access_secret_bindings_credential_binding_id",
            ),
        ),
        (
            "access_consumer_bindings",
            (
                "ix_access_consumer_bindings_updated_at",
                "ix_access_consumer_bindings_status",
                "ix_access_consumer_bindings_credential_binding_id",
                "ix_access_consumer_bindings_asset_id",
                "ix_access_consumer_bindings_consumer_id",
                "ix_access_consumer_bindings_consumer_kind",
                "ix_access_consumer_bindings_consumer_module",
            ),
        ),
        (
            "access_credential_bindings",
            (
                "ix_access_credential_bindings_updated_at",
                "ix_access_credential_bindings_status",
                "ix_access_credential_bindings_source_kind",
                "ix_access_credential_bindings_binding_kind",
                "ix_access_credential_bindings_asset_id",
            ),
        ),
        (
            "access_assets",
            (
                "ix_access_assets_updated_at",
                "ix_access_assets_authorization_policy_id",
                "ix_access_assets_storage_key",
                "ix_access_assets_status",
                "ix_access_assets_governance_scope",
                "ix_access_assets_asset_kind",
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
