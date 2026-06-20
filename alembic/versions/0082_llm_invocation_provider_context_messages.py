"""add llm invocation provider context messages

Revision ID: 0082_llm_invocation_provider_context_messages
Revises: 0081_llm_invocation_request_policy
Create Date: 2026-06-16
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0082_llm_invocation_provider_context_messages"
down_revision = "0081_llm_invocation_request_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    op.add_column(
        "llm_invocations",
        sa.Column(
            "provider_context_messages",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    )
    if bind.dialect.name == "sqlite":
        return
    op.alter_column(
        "llm_invocations",
        "provider_context_messages",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("llm_invocations", "provider_context_messages")
