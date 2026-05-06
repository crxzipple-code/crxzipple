"""rename reply payload columns

Revision ID: 0032_rename_reply_payload_columns
Revises: 0031_drop_session_llm_id
Create Date: 2026-04-17 14:35:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0032_rename_reply_payload_columns"
down_revision = "0031_drop_session_llm_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("sessions"):
        session_columns = {
            column["name"]
            for column in inspector.get_columns("sessions")
        }
        if (
            "delivery_payload" in session_columns
            and "reply_payload" not in session_columns
        ):
            if bind.dialect.name == "postgresql":
                op.alter_column(
                    "sessions",
                    "delivery_payload",
                    new_column_name="reply_payload",
                    existing_type=sa.JSON(),
                    existing_nullable=False,
                )
            else:
                with op.batch_alter_table("sessions", recreate="always") as batch_op:
                    batch_op.alter_column(
                        "delivery_payload",
                        new_column_name="reply_payload",
                        existing_type=sa.JSON(),
                        existing_nullable=False,
                    )

    inspector = sa.inspect(bind)
    if inspector.has_table("orchestration_runs"):
        orchestration_columns = {
            column["name"]
            for column in inspector.get_columns("orchestration_runs")
        }
        if (
            "delivery_target_payload" in orchestration_columns
            and "reply_target_payload" not in orchestration_columns
        ):
            if bind.dialect.name == "postgresql":
                op.alter_column(
                    "orchestration_runs",
                    "delivery_target_payload",
                    new_column_name="reply_target_payload",
                    existing_type=sa.JSON(),
                    existing_nullable=True,
                )
            else:
                with op.batch_alter_table(
                    "orchestration_runs",
                    recreate="always",
                ) as batch_op:
                    batch_op.alter_column(
                        "delivery_target_payload",
                        new_column_name="reply_target_payload",
                        existing_type=sa.JSON(),
                        existing_nullable=True,
                    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("sessions"):
        session_columns = {
            column["name"]
            for column in inspector.get_columns("sessions")
        }
        if (
            "reply_payload" in session_columns
            and "delivery_payload" not in session_columns
        ):
            if bind.dialect.name == "postgresql":
                op.alter_column(
                    "sessions",
                    "reply_payload",
                    new_column_name="delivery_payload",
                    existing_type=sa.JSON(),
                    existing_nullable=False,
                )
            else:
                with op.batch_alter_table("sessions", recreate="always") as batch_op:
                    batch_op.alter_column(
                        "reply_payload",
                        new_column_name="delivery_payload",
                        existing_type=sa.JSON(),
                        existing_nullable=False,
                    )

    inspector = sa.inspect(bind)
    if inspector.has_table("orchestration_runs"):
        orchestration_columns = {
            column["name"]
            for column in inspector.get_columns("orchestration_runs")
        }
        if (
            "reply_target_payload" in orchestration_columns
            and "delivery_target_payload" not in orchestration_columns
        ):
            if bind.dialect.name == "postgresql":
                op.alter_column(
                    "orchestration_runs",
                    "reply_target_payload",
                    new_column_name="delivery_target_payload",
                    existing_type=sa.JSON(),
                    existing_nullable=True,
                )
            else:
                with op.batch_alter_table(
                    "orchestration_runs",
                    recreate="always",
                ) as batch_op:
                    batch_op.alter_column(
                        "reply_target_payload",
                        new_column_name="delivery_target_payload",
                        existing_type=sa.JSON(),
                        existing_nullable=True,
                    )
