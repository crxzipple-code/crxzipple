"""persist tool run invocation context

Revision ID: 0027_tool_run_invocation_context
Revises: 0026_drop_agent_profiles_table
Create Date: 2026-03-28 15:40:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0027_tool_run_invocation_context"
down_revision = "0026_drop_agent_profiles_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("tool_runs")}
    if "invocation_context_payload" not in columns:
        op.add_column(
            "tool_runs",
            sa.Column("invocation_context_payload", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("tool_runs")}
    if "invocation_context_payload" in columns:
        with op.batch_alter_table("tool_runs") as batch_op:
            batch_op.drop_column("invocation_context_payload")
