"""agent tool policy

Revision ID: 0017_agent_tool_policy
Revises: 0016_session_hot_path_indexes
Create Date: 2026-03-24 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0017_agent_tool_policy"
down_revision = "0016_session_hot_path_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "tool_policy_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("agents", "tool_policy_payload")
