"""add llm invocation request metadata

Revision ID: 0069_llm_invocation_request_metadata
Revises: 0068_orchestration_run_wait_state_fields
Create Date: 2026-06-05 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0069_llm_invocation_request_metadata"
down_revision = "0068_orchestration_run_wait_state_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    op.add_column(
        "llm_invocations",
        sa.Column(
            "request_metadata",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    if bind.dialect.name == "sqlite":
        return
    op.alter_column("llm_invocations", "request_metadata", server_default=None)


def downgrade() -> None:
    op.drop_column("llm_invocations", "request_metadata")
