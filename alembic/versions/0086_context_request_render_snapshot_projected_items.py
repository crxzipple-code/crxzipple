"""add projected input items to context request snapshots

Revision ID: 0086_context_request_render_snapshot_projected_items
Revises: 0085_context_request_render_snapshots
Create Date: 2026-06-19
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0086_context_request_render_snapshot_projected_items"
down_revision = "0085_context_request_render_snapshots"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in set(inspector.get_table_names()):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    table_name = "context_request_render_snapshots"
    columns = _columns(table_name)
    if not columns or "projected_input_items" in columns:
        return
    op.add_column(
        table_name,
        sa.Column(
            "projected_input_items",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    op.alter_column(table_name, "projected_input_items", server_default=None)


def downgrade() -> None:
    table_name = "context_request_render_snapshots"
    if "projected_input_items" in _columns(table_name):
        op.drop_column(table_name, "projected_input_items")
