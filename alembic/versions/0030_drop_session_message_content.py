"""drop session message content

Revision ID: 0030_drop_session_message_content
Revises: 0029_drop_orchestration_bulk_key
Create Date: 2026-04-02 15:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0030_drop_session_message_content"
down_revision = "0029_drop_orchestration_bulk_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("session_messages"):
        return
    columns = {column["name"] for column in inspector.get_columns("session_messages")}
    if "content" not in columns:
        return

    with op.batch_alter_table("session_messages") as batch_op:
        batch_op.drop_column("content")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("session_messages"):
        return
    columns = {column["name"] for column in inspector.get_columns("session_messages")}
    if "content" in columns:
        return

    with op.batch_alter_table("session_messages") as batch_op:
        batch_op.add_column(
            sa.Column(
                "content",
                sa.Text(),
                nullable=False,
                server_default="",
            ),
        )
