"""drop orchestration bulk key

Revision ID: 0029_drop_orchestration_bulk_key
Revises: 0028_drop_tool_definitions_table
Create Date: 2026-03-29 20:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0029_drop_orchestration_bulk_key"
down_revision = "0028_drop_tool_definitions_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("orchestration_runs"):
        return
    columns = {column["name"] for column in inspector.get_columns("orchestration_runs")}
    if "bulk_key" not in columns:
        return

    index_names = {index["name"] for index in inspector.get_indexes("orchestration_runs")}
    with op.batch_alter_table("orchestration_runs") as batch_op:
        if op.f("ix_orchestration_runs_bulk_key") in index_names:
            batch_op.drop_index(op.f("ix_orchestration_runs_bulk_key"))
        batch_op.drop_column("bulk_key")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("orchestration_runs"):
        return
    columns = {column["name"] for column in inspector.get_columns("orchestration_runs")}
    if "bulk_key" in columns:
        return

    with op.batch_alter_table("orchestration_runs") as batch_op:
        batch_op.add_column(sa.Column("bulk_key", sa.String(length=255), nullable=True))
        batch_op.create_index(
            op.f("ix_orchestration_runs_bulk_key"),
            ["bulk_key"],
            unique=False,
        )
