"""llm provider request preview

Revision ID: 0077_llm_provider_request_preview
Revises: 0076_tool_surface_snapshots
Create Date: 2026-06-14 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0077_llm_provider_request_preview"
down_revision = "0076_tool_surface_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "llm_invocations",
        sa.Column(
            "provider_request_payload_preview",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.alter_column(
        "llm_invocations",
        "provider_request_payload_preview",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("llm_invocations", "provider_request_payload_preview")
