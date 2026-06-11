"""create event outbox records table

Revision ID: 0067_event_outbox
Revises: 0066_drop_orchestration_scheduler_signals
Create Date: 2026-06-02 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0067_event_outbox"
down_revision = "0066_drop_orchestration_scheduler_signals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "event_outbox_records",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("topic", sa.String(length=255), nullable=False),
        sa.Column("event_name", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("event_payload", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("publisher_id", sa.String(length=100), nullable=True),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_event_outbox_records_topic", "event_outbox_records", ["topic"])
    op.create_index(
        "ix_event_outbox_records_event_name",
        "event_outbox_records",
        ["event_name"],
    )
    op.create_index(
        "ix_event_outbox_records_status",
        "event_outbox_records",
        ["status"],
    )
    op.create_index(
        "ix_event_outbox_records_available_at",
        "event_outbox_records",
        ["available_at"],
    )
    op.create_index(
        "ix_event_outbox_records_publisher_id",
        "event_outbox_records",
        ["publisher_id"],
    )
    op.create_index(
        "ix_event_outbox_records_claim_expires_at",
        "event_outbox_records",
        ["claim_expires_at"],
    )
    op.create_index(
        "ix_event_outbox_records_delivered_at",
        "event_outbox_records",
        ["delivered_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_event_outbox_records_delivered_at", table_name="event_outbox_records")
    op.drop_index("ix_event_outbox_records_claim_expires_at", table_name="event_outbox_records")
    op.drop_index("ix_event_outbox_records_publisher_id", table_name="event_outbox_records")
    op.drop_index("ix_event_outbox_records_available_at", table_name="event_outbox_records")
    op.drop_index("ix_event_outbox_records_status", table_name="event_outbox_records")
    op.drop_index("ix_event_outbox_records_event_name", table_name="event_outbox_records")
    op.drop_index("ix_event_outbox_records_topic", table_name="event_outbox_records")
    op.drop_table("event_outbox_records")
