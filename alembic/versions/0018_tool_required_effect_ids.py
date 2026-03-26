"""tool required effect ids

Revision ID: 0018_tool_required_effect_ids
Revises: 0017_agent_tool_policy
Create Date: 2026-03-24 13:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0018_tool_required_effect_ids"
down_revision = "0017_agent_tool_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tools",
        sa.Column(
            "required_effect_ids",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("tools", "required_effect_ids")
