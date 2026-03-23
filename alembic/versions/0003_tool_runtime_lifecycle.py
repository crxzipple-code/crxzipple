"""tool runtime lifecycle

Revision ID: 0003_tool_runtime_lifecycle
Revises: 0002_tool_definition_contract
Create Date: 2026-03-22 02:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_tool_runtime_lifecycle"
down_revision = "0002_tool_definition_contract"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tools",
        sa.Column(
            "supported_modes",
            sa.JSON(),
            nullable=False,
            server_default='["inline"]',
        ),
    )
    op.add_column(
        "tools",
        sa.Column(
            "supported_strategies",
            sa.JSON(),
            nullable=False,
            server_default='["async"]',
        ),
    )
    op.add_column(
        "tools",
        sa.Column(
            "supported_environments",
            sa.JSON(),
            nullable=False,
            server_default='["local"]',
        ),
    )
    op.add_column(
        "tools",
        sa.Column(
            "source_kind",
            sa.String(length=50),
            nullable=False,
            server_default="manual",
        ),
    )
    op.add_column(
        "tools",
        sa.Column("runtime_key", sa.String(length=255), nullable=True),
    )

    op.create_table(
        "tool_runs",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("tool_id", sa.String(length=100), nullable=False),
        sa.Column("mode", sa.String(length=50), nullable=False),
        sa.Column("strategy", sa.String(length=50), nullable=False),
        sa.Column("environment", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("input_payload", sa.JSON(), nullable=False),
        sa.Column("output_payload", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tool_id"], ["tools.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tool_runs_tool_id", "tool_runs", ["tool_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_tool_runs_tool_id", table_name="tool_runs")
    op.drop_table("tool_runs")
    op.drop_column("tools", "runtime_key")
    op.drop_column("tools", "source_kind")
    op.drop_column("tools", "supported_environments")
    op.drop_column("tools", "supported_strategies")
    op.drop_column("tools", "supported_modes")
