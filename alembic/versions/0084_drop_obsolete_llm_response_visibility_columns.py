"""drop obsolete llm response item visibility columns

Revision ID: 0084_drop_obsolete_llm_response_visibility_columns
Revises: 0083_visibility_projection_columns
Create Date: 2026-06-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0084_drop_obsolete_llm_response_visibility_columns"
down_revision = "0083_visibility_projection_columns"
branch_labels = None
depends_on = None


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    return {column["name"] for column in sa.inspect(bind).get_columns(table_name)}


def upgrade() -> None:
    existing = _column_names("llm_invocation_response_items")
    for column_name in ("user_visible", "model_visible"):
        if column_name in existing:
            op.drop_column("llm_invocation_response_items", column_name)


def downgrade() -> None:
    existing = _column_names("llm_invocation_response_items")
    for column_name in ("model_visible", "user_visible"):
        if column_name not in existing:
            op.add_column(
                "llm_invocation_response_items",
                sa.Column(
                    column_name,
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.true(),
                ),
            )
            bind = op.get_bind()
            if bind.dialect.name != "sqlite":
                op.alter_column(
                    "llm_invocation_response_items",
                    column_name,
                    server_default=None,
                )
