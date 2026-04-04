"""drop session llm id

Revision ID: 0031_drop_session_llm_id
Revises: 0030_drop_session_message_content
Create Date: 2026-04-02 16:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0031_drop_session_llm_id"
down_revision = "0030_drop_session_message_content"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("_alembic_tmp_sessions"):
        op.drop_table("_alembic_tmp_sessions")
        inspector = sa.inspect(bind)

    if not inspector.has_table("sessions"):
        return
    columns = {column["name"] for column in inspector.get_columns("sessions")}
    if "llm_id" not in columns:
        return
    indexes = {index["name"] for index in inspector.get_indexes("sessions")}
    if "ix_sessions_llm_id" in indexes:
        op.drop_index("ix_sessions_llm_id", table_name="sessions")

    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_column("llm_id")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("sessions"):
        return
    columns = {column["name"] for column in inspector.get_columns("sessions")}
    if "llm_id" in columns:
        return

    with op.batch_alter_table("sessions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "llm_id",
                sa.String(length=255),
                nullable=True,
            ),
        )
    op.create_index("ix_sessions_llm_id", "sessions", ["llm_id"], unique=False)
