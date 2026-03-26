"""add llm context window tokens

Revision ID: 0024_llm_context_window_tokens
Revises: 0023_memory_domain
Create Date: 2026-03-25 00:45:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0024_llm_context_window_tokens"
down_revision = "0023_memory_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "llm_profiles",
        sa.Column("context_window_tokens", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("llm_profiles", "context_window_tokens")
