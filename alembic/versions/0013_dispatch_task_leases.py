"""dispatch task leases

Revision ID: 0013_dispatch_task_leases
Revises: 0012_dispatch_tasks
Create Date: 2026-03-23 14:40:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0013_dispatch_task_leases"
down_revision = "0012_dispatch_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dispatch_tasks",
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "dispatch_tasks",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_dispatch_tasks_lease_expires_at"),
        "dispatch_tasks",
        ["lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_dispatch_tasks_lease_expires_at"), table_name="dispatch_tasks")
    op.drop_column("dispatch_tasks", "lease_expires_at")
    op.drop_column("dispatch_tasks", "heartbeat_at")
