"""add llm profile concurrency limits

Revision ID: 0036_llm_profile_concurrency_limits
Revises: 0035_create_orchestration_executor_leases
Create Date: 2026-04-21 00:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0036_llm_profile_concurrency_limits"
down_revision = "0035_create_orchestration_executor_leases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("llm_profiles")}

    if "max_concurrency" not in columns:
        op.add_column(
            "llm_profiles",
            sa.Column("max_concurrency", sa.Integer(), nullable=True),
        )
    if "concurrency_key" not in columns:
        op.add_column(
            "llm_profiles",
            sa.Column("concurrency_key", sa.String(length=255), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("llm_profiles")}

    if "concurrency_key" in columns:
        op.drop_column("llm_profiles", "concurrency_key")
    if "max_concurrency" in columns:
        op.drop_column("llm_profiles", "max_concurrency")
