"""persist access consumer slot credential bindings

Revision ID: 0046_access_consumer_slot_bindings
Revises: 0045_llm_access_credential_binding_refs
Create Date: 2026-05-11 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0046_access_consumer_slot_bindings"
down_revision = "0045_llm_access_credential_binding_refs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("access_consumer_bindings"):
        return

    columns = {column["name"] for column in inspector.get_columns("access_consumer_bindings")}
    if "credential_bindings" in columns:
        return

    with op.batch_alter_table("access_consumer_bindings") as batch_op:
        batch_op.add_column(
            sa.Column("credential_bindings", sa.JSON(), nullable=True),
        )
    bind.execute(
        sa.text(
            """
            UPDATE access_consumer_bindings
            SET credential_bindings = '{}'
            WHERE credential_bindings IS NULL
            """,
        ),
    )
    with op.batch_alter_table("access_consumer_bindings") as batch_op:
        batch_op.alter_column(
            "credential_bindings",
            existing_type=sa.JSON(),
            nullable=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("access_consumer_bindings"):
        return

    columns = {column["name"] for column in inspector.get_columns("access_consumer_bindings")}
    if "credential_bindings" not in columns:
        return

    with op.batch_alter_table("access_consumer_bindings") as batch_op:
        batch_op.drop_column("credential_bindings")
