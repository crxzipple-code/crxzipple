"""add memory domain tables

Revision ID: 0023_memory_domain
Revises: 0022_agent_tool_preferences_cleanup
Create Date: 2026-03-24 23:55:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0023_memory_domain"
down_revision = "0022_agent_tool_preferences_cleanup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memory_candidates",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("agent_id", sa.String(length=100), nullable=False),
        sa.Column("session_key", sa.String(length=255), nullable=True),
        sa.Column("run_id", sa.String(length=100), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("tags_payload", sa.JSON(), nullable=False),
        sa.Column("metadata_payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column("approved_entry_id", sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_memory_candidates_agent_id",
        "memory_candidates",
        ["agent_id"],
        unique=False,
    )
    op.create_index(
        "ix_memory_candidates_session_key",
        "memory_candidates",
        ["session_key"],
        unique=False,
    )
    op.create_index(
        "ix_memory_candidates_run_id",
        "memory_candidates",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_memory_candidates_status",
        "memory_candidates",
        ["status"],
        unique=False,
    )

    op.create_table(
        "memory_entries",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("agent_id", sa.String(length=100), nullable=False),
        sa.Column("session_key", sa.String(length=255), nullable=True),
        sa.Column("run_id", sa.String(length=100), nullable=True),
        sa.Column("source_candidate_id", sa.String(length=100), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("tags_payload", sa.JSON(), nullable=False),
        sa.Column("metadata_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_candidate_id"],
            ["memory_candidates.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_memory_entries_agent_id",
        "memory_entries",
        ["agent_id"],
        unique=False,
    )
    op.create_index(
        "ix_memory_entries_session_key",
        "memory_entries",
        ["session_key"],
        unique=False,
    )
    op.create_index(
        "ix_memory_entries_run_id",
        "memory_entries",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_memory_entries_source_candidate_id",
        "memory_entries",
        ["source_candidate_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_memory_entries_source_candidate_id", table_name="memory_entries")
    op.drop_index("ix_memory_entries_run_id", table_name="memory_entries")
    op.drop_index("ix_memory_entries_session_key", table_name="memory_entries")
    op.drop_index("ix_memory_entries_agent_id", table_name="memory_entries")
    op.drop_table("memory_entries")

    op.drop_index("ix_memory_candidates_status", table_name="memory_candidates")
    op.drop_index("ix_memory_candidates_run_id", table_name="memory_candidates")
    op.drop_index("ix_memory_candidates_session_key", table_name="memory_candidates")
    op.drop_index("ix_memory_candidates_agent_id", table_name="memory_candidates")
    op.drop_table("memory_candidates")
