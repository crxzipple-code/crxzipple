"""session hot path indexes

Revision ID: 0016_session_hot_path_indexes
Revises: 0015_orchestration_wait_mappings
Create Date: 2026-03-23 17:15:00
"""

from __future__ import annotations

from alembic import op


revision = "0016_session_hot_path_indexes"
down_revision = "0015_orchestration_wait_mappings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_session_messages_session_sequence",
        "session_messages",
        ["session_key", "session_id", "sequence_no"],
        unique=False,
    )
    op.create_index(
        "ix_session_messages_session_source",
        "session_messages",
        ["session_key", "session_id", "source_kind", "source_id"],
        unique=False,
    )
    op.create_index(
        "ix_session_instances_session_sequence",
        "session_instances",
        ["session_key", "sequence_no"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_session_instances_session_sequence",
        table_name="session_instances",
    )
    op.drop_index(
        "ix_session_messages_session_source",
        table_name="session_messages",
    )
    op.drop_index(
        "ix_session_messages_session_sequence",
        table_name="session_messages",
    )
