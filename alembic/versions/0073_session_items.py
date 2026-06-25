"""session items

Revision ID: 0073_session_items
Revises: 0072_llm_response_items
Create Date: 2026-06-11 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0073_session_items"
down_revision = "0072_llm_response_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "session_items",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("session_key", sa.String(length=255), nullable=False),
        sa.Column("session_id", sa.String(length=100), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=100), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=True),
        sa.Column("phase", sa.String(length=100), nullable=False),
        sa.Column("content_payload", sa.JSON(), nullable=False),
        sa.Column("model_visible", sa.Boolean(), nullable=False),
        sa.Column("user_visible", sa.Boolean(), nullable=False),
        sa.Column("chat_visible", sa.Boolean(), nullable=False),
        sa.Column("trace_visible", sa.Boolean(), nullable=False),
        sa.Column("source_module", sa.String(length=100), nullable=True),
        sa.Column("source_kind", sa.String(length=100), nullable=True),
        sa.Column("source_id", sa.String(length=255), nullable=True),
        sa.Column("provider_item_id", sa.String(length=255), nullable=True),
        sa.Column("provider_item_type", sa.String(length=255), nullable=True),
        sa.Column("call_id", sa.String(length=255), nullable=True),
        sa.Column("tool_name", sa.String(length=255), nullable=True),
        sa.Column("metadata_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_key"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_session_items_session_sequence",
        "session_items",
        ["session_key", "session_id", "sequence_no"],
        unique=True,
    )
    op.create_index(
        "ix_session_items_source",
        "session_items",
        ["source_module", "source_kind", "source_id"],
        unique=False,
    )
    op.create_index(
        "ix_session_items_call_id",
        "session_items",
        ["call_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_session_items_session_id"),
        "session_items",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_session_items_session_key"),
        "session_items",
        ["session_key"],
        unique=False,
    )
    bind = op.get_bind()
    if sa.inspect(bind).has_table("session_messages"):
        op.drop_table("session_messages")


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("session_messages"):
        op.create_table(
            "session_messages",
            sa.Column("id", sa.String(length=100), nullable=False),
            sa.Column("session_key", sa.String(length=255), nullable=False),
            sa.Column("session_id", sa.String(length=100), nullable=False),
            sa.Column("role", sa.String(length=50), nullable=False),
            sa.Column("metadata_payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("sequence_no", sa.Integer(), nullable=False),
            sa.Column("kind", sa.String(length=50), nullable=False),
            sa.Column("content_payload", sa.JSON(), nullable=False),
            sa.Column("source_kind", sa.String(length=50), nullable=True),
            sa.Column("source_id", sa.String(length=100), nullable=True),
            sa.Column("visibility", sa.String(length=50), nullable=False),
            sa.ForeignKeyConstraint(["session_key"], ["sessions.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_session_messages_session_key",
            "session_messages",
            ["session_key"],
        )
        op.create_index(
            "ix_session_messages_session_id",
            "session_messages",
            ["session_id"],
        )
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
    op.drop_index(op.f("ix_session_items_session_key"), table_name="session_items")
    op.drop_index(op.f("ix_session_items_session_id"), table_name="session_items")
    op.drop_index("ix_session_items_call_id", table_name="session_items")
    op.drop_index("ix_session_items_source", table_name="session_items")
    op.drop_index("ix_session_items_session_sequence", table_name="session_items")
    op.drop_table("session_items")
