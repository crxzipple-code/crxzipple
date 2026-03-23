"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-03-22 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llms",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "tools",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "agents",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("default_llm_id", sa.String(length=100), nullable=False),
        sa.Column("tool_ids", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["default_llm_id"], ["llms.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agents_default_llm_id", "agents", ["default_llm_id"])
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("agent_id", sa.String(length=100), nullable=False),
        sa.Column("llm_id", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["llm_id"], ["llms.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sessions_agent_id", "sessions", ["agent_id"])
    op.create_index("ix_sessions_llm_id", "sessions", ["llm_id"])


def downgrade() -> None:
    op.drop_index("ix_sessions_llm_id", table_name="sessions")
    op.drop_index("ix_sessions_agent_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("ix_agents_default_llm_id", table_name="agents")
    op.drop_table("agents")
    op.drop_table("tools")
    op.drop_table("llms")
