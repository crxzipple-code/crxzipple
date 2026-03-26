"""add authorization temporary grants

Revision ID: 0025_authorization_temporary_grants
Revises: 0024_llm_context_window_tokens
Create Date: 2026-03-25 10:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0025_authorization_temporary_grants"
down_revision = "0024_llm_context_window_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "authorization_temporary_grants",
        sa.Column("id", sa.String(length=160), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("run_id", sa.String(length=100), nullable=True),
        sa.Column("session_key", sa.String(length=255), nullable=True),
        sa.Column("agent_id", sa.String(length=100), nullable=True),
        sa.Column("approval_request_id", sa.String(length=160), nullable=True),
        sa.Column("effect_ids_payload", sa.JSON(), nullable=False),
        sa.Column("tool_ids_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_authorization_temporary_grants_scope",
        "authorization_temporary_grants",
        ["scope"],
        unique=False,
    )
    op.create_index(
        "ix_authorization_temporary_grants_run_id",
        "authorization_temporary_grants",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_authorization_temporary_grants_session_key",
        "authorization_temporary_grants",
        ["session_key"],
        unique=False,
    )
    op.create_index(
        "ix_authorization_temporary_grants_agent_id",
        "authorization_temporary_grants",
        ["agent_id"],
        unique=False,
    )
    op.create_index(
        "ix_authorization_temporary_grants_approval_request_id",
        "authorization_temporary_grants",
        ["approval_request_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_authorization_temporary_grants_approval_request_id",
        table_name="authorization_temporary_grants",
    )
    op.drop_index(
        "ix_authorization_temporary_grants_agent_id",
        table_name="authorization_temporary_grants",
    )
    op.drop_index(
        "ix_authorization_temporary_grants_session_key",
        table_name="authorization_temporary_grants",
    )
    op.drop_index(
        "ix_authorization_temporary_grants_run_id",
        table_name="authorization_temporary_grants",
    )
    op.drop_index(
        "ix_authorization_temporary_grants_scope",
        table_name="authorization_temporary_grants",
    )
    op.drop_table("authorization_temporary_grants")
