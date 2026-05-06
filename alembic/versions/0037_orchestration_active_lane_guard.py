"""add orchestration active lane guard

Revision ID: 0037_orchestration_active_lane_guard
Revises: 0036_llm_profile_concurrency_limits
Create Date: 2026-04-21 01:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0037_orchestration_active_lane_guard"
down_revision = "0036_llm_profile_concurrency_limits"
branch_labels = None
depends_on = None


INDEX_NAME = "uq_orchestration_runs_active_lane"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("orchestration_runs"):
        return
    columns = {
        column["name"]
        for column in inspector.get_columns("orchestration_runs")
    }
    indexes = {
        index["name"]
        for index in inspector.get_indexes("orchestration_runs")
    }
    if "lane_lock_key" not in columns:
        op.add_column(
            "orchestration_runs",
            sa.Column("lane_lock_key", sa.String(length=255), nullable=True),
        )
    if "ix_orchestration_runs_lane_lock_key" not in indexes:
        op.create_index(
            "ix_orchestration_runs_lane_lock_key",
            "orchestration_runs",
            ["lane_lock_key"],
        )
    op.execute(
        "UPDATE orchestration_runs "
        "SET lane_lock_key = lane_key "
        "WHERE lane_key IS NOT NULL "
        "AND status IN ('running', 'waiting') "
        "AND lane_lock_key IS NULL",
    )
    if INDEX_NAME in indexes:
        return
    active_lane_where = sa.text(
        "lane_lock_key IS NOT NULL AND status IN ('running', 'waiting')",
    )
    op.create_index(
        INDEX_NAME,
        "orchestration_runs",
        ["lane_lock_key"],
        unique=True,
        sqlite_where=active_lane_where,
        postgresql_where=active_lane_where,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("orchestration_runs"):
        return
    indexes = {
        index["name"]
        for index in inspector.get_indexes("orchestration_runs")
    }
    if INDEX_NAME in indexes:
        op.drop_index(INDEX_NAME, table_name="orchestration_runs")
    if "ix_orchestration_runs_lane_lock_key" in indexes:
        op.drop_index(
            "ix_orchestration_runs_lane_lock_key",
            table_name="orchestration_runs",
        )
    columns = {
        column["name"]
        for column in inspector.get_columns("orchestration_runs")
    }
    if "lane_lock_key" in columns:
        op.drop_column("orchestration_runs", "lane_lock_key")
