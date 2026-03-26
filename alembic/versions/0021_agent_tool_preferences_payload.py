"""rename agent tool policy payload column

Revision ID: 0021_agent_tool_preferences_payload
Revises: 0020_effect_request_terminology
Create Date: 2026-03-24 20:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0021_agent_tool_preferences_payload"
down_revision = "0020_effect_request_terminology"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("agents") as batch_op:
        batch_op.alter_column(
            "tool_policy_payload",
            new_column_name="tool_preferences_payload",
            existing_type=sa.JSON(),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("agents") as batch_op:
        batch_op.alter_column(
            "tool_preferences_payload",
            new_column_name="tool_policy_payload",
            existing_type=sa.JSON(),
            existing_nullable=False,
        )
