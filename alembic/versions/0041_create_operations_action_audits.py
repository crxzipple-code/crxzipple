"""create operations action audits

Revision ID: 0041_create_operations_action_audits
Revises: 0040_create_operations_projections
Create Date: 2026-05-06 18:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0041_create_operations_action_audits"
down_revision = "0040_create_operations_projections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("operations_action_audits"):
        return

    op.create_table(
        "operations_action_audits",
        sa.Column("audit_id", sa.String(length=80), nullable=False),
        sa.Column("action_type", sa.String(length=120), nullable=False),
        sa.Column("target_type", sa.String(length=120), nullable=False),
        sa.Column("target_id", sa.String(length=200), nullable=True),
        sa.Column("target", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=False),
        sa.Column("dangerous", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("risk", sa.String(length=40), nullable=False, server_default="normal"),
        sa.Column("confirmation", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "risk_acknowledged",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("operator", sa.String(length=200), nullable=True),
        sa.Column("source", sa.String(length=120), nullable=False, server_default="operations"),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("audit_id", name="pk_operations_action_audits"),
    )
    op.create_index(
        "ix_operations_action_audits_action_type",
        "operations_action_audits",
        ["action_type"],
    )
    op.create_index(
        "ix_operations_action_audits_created_at",
        "operations_action_audits",
        ["created_at"],
    )
    op.create_index(
        "ix_operations_action_audits_status",
        "operations_action_audits",
        ["status"],
    )
    op.create_index(
        "ix_operations_action_audits_target_id",
        "operations_action_audits",
        ["target_id"],
    )
    op.create_index(
        "ix_operations_action_audits_target_type",
        "operations_action_audits",
        ["target_type"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("operations_action_audits"):
        return

    with op.batch_alter_table("operations_action_audits") as batch_op:
        batch_op.drop_index("ix_operations_action_audits_target_type")
        batch_op.drop_index("ix_operations_action_audits_target_id")
        batch_op.drop_index("ix_operations_action_audits_status")
        batch_op.drop_index("ix_operations_action_audits_created_at")
        batch_op.drop_index("ix_operations_action_audits_action_type")
    op.drop_table("operations_action_audits")
