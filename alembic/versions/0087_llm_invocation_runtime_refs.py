"""add runtime references to llm invocations

Revision ID: 0087_llm_invocation_runtime_refs
Revises: 0086_context_request_render_snapshot_projected_items
Create Date: 2026-06-23
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0087_llm_invocation_runtime_refs"
down_revision = "0086_context_request_render_snapshot_projected_items"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in set(inspector.get_table_names()):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in set(inspector.get_table_names()):
        return set()
    return {index["name"] for index in inspector.get_indexes(table_name)}


def _add_column_if_missing(
    table_name: str,
    columns: set[str],
    name: str,
    length: int,
) -> None:
    if name not in columns:
        op.add_column(table_name, sa.Column(name, sa.String(length), nullable=True))


def _create_index_if_missing(table_name: str, indexes: set[str], name: str) -> None:
    index_name = f"ix_{table_name}_{name}"
    if index_name not in indexes:
        op.create_index(index_name, table_name, [name])


def upgrade() -> None:
    table_name = "llm_invocations"
    columns = _columns(table_name)
    if not columns:
        return
    _add_column_if_missing(table_name, columns, "run_id", 160)
    _add_column_if_missing(table_name, columns, "agent_id", 160)
    _add_column_if_missing(table_name, columns, "session_key", 240)
    _add_column_if_missing(table_name, columns, "active_session_id", 160)
    indexes = _indexes(table_name)
    _create_index_if_missing(table_name, indexes, "run_id")
    _create_index_if_missing(table_name, indexes, "agent_id")
    _create_index_if_missing(table_name, indexes, "session_key")
    _create_index_if_missing(table_name, indexes, "active_session_id")


def downgrade() -> None:
    table_name = "llm_invocations"
    columns = _columns(table_name)
    indexes = _indexes(table_name)
    for name in ("active_session_id", "session_key", "agent_id", "run_id"):
        index_name = f"ix_{table_name}_{name}"
        if index_name in indexes:
            op.drop_index(index_name, table_name=table_name)
        if name in columns:
            op.drop_column(table_name, name)
