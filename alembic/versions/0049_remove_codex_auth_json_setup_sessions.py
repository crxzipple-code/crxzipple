"""remove deprecated codex auth json setup sessions

Revision ID: 0049_remove_codex_auth_json_setup_sessions
Revises: 0048_remove_codex_auth_json_access_asset
Create Date: 2026-05-12 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0049_remove_codex_auth_json_setup_sessions"
down_revision = "0048_remove_codex_auth_json_access_asset"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("access_setup_sessions"):
        return
    bind.execute(
        sa.text(
            """
            DELETE FROM access_setup_sessions
            WHERE target_id = 'codex-auth-json'
               OR target_kind = 'codex_auth_json'
            """,
        ),
    )


def downgrade() -> None:
    # Deprecated Codex CLI/auth.json setup sessions are intentionally not restored.
    return None
