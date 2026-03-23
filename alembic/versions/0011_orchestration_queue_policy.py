"""orchestration queue policy

Revision ID: 0011_orchestration_queue_policy
Revises: 0010_orchestration_runs
Create Date: 2026-03-23 03:35:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0011_orchestration_queue_policy"
down_revision = "0010_orchestration_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orchestration_runs",
        sa.Column(
            "queue_policy",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'fifo'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("orchestration_runs", "queue_policy")
