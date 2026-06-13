"""llm response items and events

Revision ID: 0072_llm_response_items
Revises: 0071_delete_configured_browser_tool_source
Create Date: 2026-06-11 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0072_llm_response_items"
down_revision = "0071_delete_configured_browser_tool_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "llm_invocations",
        sa.Column("continuation_payload", sa.JSON(), nullable=True),
    )
    op.create_table(
        "llm_invocation_response_items",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("invocation_id", sa.String(length=100), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=100), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=True),
        sa.Column("phase", sa.String(length=100), nullable=False),
        sa.Column("content_payload", sa.JSON(), nullable=False),
        sa.Column("provider_payload", sa.JSON(), nullable=False),
        sa.Column("provider_item_id", sa.String(length=255), nullable=True),
        sa.Column("provider_item_type", sa.String(length=255), nullable=True),
        sa.Column("call_id", sa.String(length=255), nullable=True),
        sa.Column("tool_name", sa.String(length=255), nullable=True),
        sa.Column("model_visible", sa.Boolean(), nullable=False),
        sa.Column("user_visible", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["invocation_id"],
            ["llm_invocations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_llm_invocation_response_items_invocation_id"),
        "llm_invocation_response_items",
        ["invocation_id"],
        unique=False,
    )
    op.create_table(
        "llm_invocation_response_events",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("invocation_id", sa.String(length=100), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=100), nullable=False),
        sa.Column("item_id", sa.String(length=100), nullable=True),
        sa.Column("delta_payload", sa.JSON(), nullable=False),
        sa.Column("provider_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["invocation_id"],
            ["llm_invocations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_llm_invocation_response_events_invocation_id"),
        "llm_invocation_response_events",
        ["invocation_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_llm_invocation_response_events_invocation_id"),
        table_name="llm_invocation_response_events",
    )
    op.drop_table("llm_invocation_response_events")
    op.drop_index(
        op.f("ix_llm_invocation_response_items_invocation_id"),
        table_name="llm_invocation_response_items",
    )
    op.drop_table("llm_invocation_response_items")
    op.drop_column("llm_invocations", "continuation_payload")
