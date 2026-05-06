"""create operations projections

Revision ID: 0040_create_operations_projections
Revises: 0039_create_tool_runtime_tracking
Create Date: 2026-05-06 09:55:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0040_create_operations_projections"
down_revision = "0039_create_tool_runtime_tracking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("operations_projections"):
        return

    op.create_table(
        "operations_projections",
        sa.Column("module", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column(
            "query_key",
            sa.String(length=160),
            nullable=False,
            server_default="default",
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint(
            "module",
            "kind",
            "query_key",
            name="pk_operations_projections",
        ),
    )
    op.create_index(
        "ix_operations_projections_module",
        "operations_projections",
        ["module"],
    )
    op.create_index(
        "ix_operations_projections_updated_at",
        "operations_projections",
        ["updated_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("operations_projections"):
        return

    with op.batch_alter_table("operations_projections") as batch_op:
        batch_op.drop_index("ix_operations_projections_updated_at")
        batch_op.drop_index("ix_operations_projections_module")
    op.drop_table("operations_projections")
