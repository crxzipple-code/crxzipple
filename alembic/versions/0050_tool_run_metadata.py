"""persist tool run submission metadata

Revision ID: 0050_tool_run_metadata
Revises: 0049_remove_codex_auth_json_setup_sessions
Create Date: 2026-05-14 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0050_tool_run_metadata"
down_revision = "0049_remove_codex_auth_json_setup_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("tool_runs")}
    if "metadata_payload" in columns:
        return
    op.add_column(
        "tool_runs",
        sa.Column(
            "metadata_payload",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("tool_runs")}
    if "metadata_payload" not in columns:
        return
    with op.batch_alter_table("tool_runs") as batch_op:
        batch_op.drop_column("metadata_payload")
