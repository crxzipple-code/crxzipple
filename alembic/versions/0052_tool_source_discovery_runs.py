"""persist tool source discovery run history

Revision ID: 0052_tool_source_discovery_runs
Revises: 0051_tool_source_function_catalog
Create Date: 2026-05-19 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0052_tool_source_discovery_runs"
down_revision = "0051_tool_source_function_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    created = False
    if not inspector.has_table("tool_source_discovery_runs"):
        op.create_table(
            "tool_source_discovery_runs",
            sa.Column("discovery_run_id", sa.String(length=100), primary_key=True),
            sa.Column("source_id", sa.String(length=100), nullable=False),
            sa.Column("source_revision", sa.Integer(), nullable=False),
            sa.Column("config_hash", sa.String(length=128), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("function_count", sa.Integer(), nullable=False),
            sa.Column("provider_backend_count", sa.Integer(), nullable=False),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("metadata_payload", sa.JSON(), nullable=False),
        )
        created = True

    _ensure_index(
        inspector,
        "tool_source_discovery_runs",
        "ix_tool_source_discovery_runs_source_id",
        ["source_id"],
        created=created,
    )
    _ensure_index(
        inspector,
        "tool_source_discovery_runs",
        "ix_tool_source_discovery_runs_status",
        ["status"],
        created=created,
    )
    _ensure_index(
        inspector,
        "tool_source_discovery_runs",
        "ix_tool_source_discovery_runs_discovered_at",
        ["discovered_at"],
        created=created,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("tool_source_discovery_runs"):
        return
    _drop_index_if_exists(
        inspector,
        "tool_source_discovery_runs",
        "ix_tool_source_discovery_runs_discovered_at",
    )
    _drop_index_if_exists(
        inspector,
        "tool_source_discovery_runs",
        "ix_tool_source_discovery_runs_status",
    )
    _drop_index_if_exists(
        inspector,
        "tool_source_discovery_runs",
        "ix_tool_source_discovery_runs_source_id",
    )
    op.drop_table("tool_source_discovery_runs")


def _ensure_index(
    inspector: sa.Inspector,
    table_name: str,
    index_name: str,
    columns: list[str],
    *,
    created: bool = False,
) -> None:
    if created:
        return
    existing = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name not in existing:
        op.create_index(index_name, table_name, columns)


def _drop_index_if_exists(
    inspector: sa.Inspector,
    table_name: str,
    index_name: str,
) -> None:
    existing = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name in existing:
        op.drop_index(index_name, table_name=table_name)
