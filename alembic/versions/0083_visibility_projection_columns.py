"""align llm and session visibility projection columns

Revision ID: 0083_visibility_projection_columns
Revises: 0082_llm_invocation_provider_context_messages
Create Date: 2026-06-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0083_visibility_projection_columns"
down_revision = "0082_llm_invocation_provider_context_messages"
branch_labels = None
depends_on = None


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    return {column["name"] for column in sa.inspect(bind).get_columns(table_name)}


def _add_bool_column_if_missing(table_name: str, column_name: str, *, default: bool) -> None:
    if column_name in _column_names(table_name):
        return
    op.add_column(
        table_name,
        sa.Column(
            column_name,
            sa.Boolean(),
            nullable=False,
            server_default=sa.true() if default else sa.false(),
        ),
    )
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.alter_column(table_name, column_name, server_default=None)


def upgrade() -> None:
    llm_item_columns = _column_names("llm_invocation_response_items")
    if "provider_replay_candidate" not in llm_item_columns:
        op.add_column(
            "llm_invocation_response_items",
            sa.Column(
                "provider_replay_candidate",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
        )
    if "user_timeline_candidate" not in llm_item_columns:
        op.add_column(
            "llm_invocation_response_items",
            sa.Column(
                "user_timeline_candidate",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        for column_name in ("provider_replay_candidate", "user_timeline_candidate"):
            op.alter_column(
                "llm_invocation_response_items",
                column_name,
                server_default=None,
            )

    _add_bool_column_if_missing("session_items", "model_visible", default=True)
    _add_bool_column_if_missing("session_items", "user_visible", default=True)
    _add_bool_column_if_missing("session_items", "chat_visible", default=True)
    _add_bool_column_if_missing("session_items", "trace_visible", default=True)


def downgrade() -> None:
    for table_name, column_names in (
        (
            "session_items",
            ("trace_visible", "chat_visible", "user_visible", "model_visible"),
        ),
        (
            "llm_invocation_response_items",
            ("user_timeline_candidate", "provider_replay_candidate"),
        ),
    ):
        existing = _column_names(table_name)
        for column_name in column_names:
            if column_name in existing:
                op.drop_column(table_name, column_name)
