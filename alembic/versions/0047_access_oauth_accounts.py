"""persist access oauth providers and accounts

Revision ID: 0047_access_oauth_accounts
Revises: 0046_access_consumer_slot_bindings
Create Date: 2026-05-11 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0047_access_oauth_accounts"
down_revision = "0046_access_consumer_slot_bindings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("access_oauth_providers"):
        op.create_table(
            "access_oauth_providers",
            sa.Column("provider_id", sa.String(length=160), primary_key=True),
            sa.Column("display_name", sa.String(length=240), nullable=False),
            sa.Column("provider_kind", sa.String(length=80), nullable=False),
            sa.Column("authorization_url", sa.String(length=1000), nullable=True),
            sa.Column("token_url", sa.String(length=1000), nullable=True),
            sa.Column("revocation_url", sa.String(length=1000), nullable=True),
            sa.Column("device_code_url", sa.String(length=1000), nullable=True),
            sa.Column("default_scopes", sa.JSON(), nullable=False),
            sa.Column("client_id", sa.String(length=300), nullable=True),
            sa.Column(
                "client_credential_binding_id",
                sa.String(length=160),
                nullable=True,
            ),
            sa.Column("callback_url", sa.String(length=1000), nullable=True),
            sa.Column("callback_mode", sa.String(length=80), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("redaction_policy", sa.JSON(), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_access_oauth_providers_provider_kind",
            "access_oauth_providers",
            ["provider_kind"],
        )
        op.create_index(
            "ix_access_oauth_providers_callback_mode",
            "access_oauth_providers",
            ["callback_mode"],
        )
        op.create_index(
            "ix_access_oauth_providers_status",
            "access_oauth_providers",
            ["status"],
        )
        op.create_index(
            "ix_access_oauth_providers_client_credential_binding_id",
            "access_oauth_providers",
            ["client_credential_binding_id"],
        )
        op.create_index(
            "ix_access_oauth_providers_updated_at",
            "access_oauth_providers",
            ["updated_at"],
        )

    if not inspector.has_table("access_oauth_accounts"):
        op.create_table(
            "access_oauth_accounts",
            sa.Column("account_id", sa.String(length=180), primary_key=True),
            sa.Column("provider_id", sa.String(length=160), nullable=False),
            sa.Column("credential_binding_id", sa.String(length=160), nullable=True),
            sa.Column("display_name", sa.String(length=240), nullable=True),
            sa.Column("subject", sa.String(length=300), nullable=True),
            sa.Column("granted_scopes", sa.JSON(), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("refresh_ready", sa.Boolean(), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("storage_key", sa.String(length=500), nullable=True),
            sa.Column("masked_preview", sa.String(length=240), nullable=True),
            sa.Column("redaction_policy", sa.JSON(), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_access_oauth_accounts_provider_id",
            "access_oauth_accounts",
            ["provider_id"],
        )
        op.create_index(
            "ix_access_oauth_accounts_credential_binding_id",
            "access_oauth_accounts",
            ["credential_binding_id"],
        )
        op.create_index(
            "ix_access_oauth_accounts_subject",
            "access_oauth_accounts",
            ["subject"],
        )
        op.create_index(
            "ix_access_oauth_accounts_expires_at",
            "access_oauth_accounts",
            ["expires_at"],
        )
        op.create_index(
            "ix_access_oauth_accounts_status",
            "access_oauth_accounts",
            ["status"],
        )
        op.create_index(
            "ix_access_oauth_accounts_storage_key",
            "access_oauth_accounts",
            ["storage_key"],
        )
        op.create_index(
            "ix_access_oauth_accounts_updated_at",
            "access_oauth_accounts",
            ["updated_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("access_oauth_accounts"):
        op.drop_table("access_oauth_accounts")
    if inspector.has_table("access_oauth_providers"):
        op.drop_table("access_oauth_providers")
