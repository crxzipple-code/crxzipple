"""orchestration wait mappings

Revision ID: 0015_orchestration_wait_mappings
Revises: 0014_session_binding_columns_nullable
Create Date: 2026-03-23 16:30:00
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "0015_orchestration_wait_mappings"
down_revision = "0014_session_binding_columns_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orchestration_run_waits",
        sa.Column("run_id", sa.String(length=100), nullable=False),
        sa.Column("tool_run_id", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["orchestration_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("run_id", "tool_run_id"),
    )
    op.create_index(
        "ix_orchestration_run_waits_tool_run_id",
        "orchestration_run_waits",
        ["tool_run_id"],
        unique=False,
    )

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT id, pending_tool_run_ids
            FROM orchestration_runs
            WHERE status = 'waiting'
            """,
        ),
    ).all()
    now = datetime.now(timezone.utc)
    for row in rows:
        for tool_run_id in _decode_pending_tool_run_ids(row.pending_tool_run_ids):
            bind.execute(
                sa.text(
                    """
                    INSERT INTO orchestration_run_waits (run_id, tool_run_id, created_at)
                    VALUES (:run_id, :tool_run_id, :created_at)
                    """,
                ),
                {
                    "run_id": row.id,
                    "tool_run_id": tool_run_id,
                    "created_at": now,
                },
            )


def downgrade() -> None:
    op.drop_index(
        "ix_orchestration_run_waits_tool_run_id",
        table_name="orchestration_run_waits",
    )
    op.drop_table("orchestration_run_waits")


def _decode_pending_tool_run_ids(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        items = value
    elif isinstance(value, str) and value.strip():
        decoded = json.loads(value)
        items = decoded if isinstance(decoded, list) else []
    else:
        items = []
    return tuple(
        item.strip()
        for item in items
        if isinstance(item, str) and item.strip()
    )
