"""add orchestration ingress request kinds

Revision ID: 0038_add_orchestration_ingress_request_kinds
Revises: 0037_orchestration_active_lane_guard
Create Date: 2026-04-23 15:40:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0038_add_orchestration_ingress_request_kinds"
down_revision = "0037_orchestration_active_lane_guard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = "orchestration_ingress_requests"
    if not inspector.has_table(table_name):
        return

    column_names = {column["name"] for column in inspector.get_columns(table_name)}
    with op.batch_alter_table(table_name) as batch_op:
        if "kind" not in column_names:
            batch_op.add_column(
                sa.Column(
                    "kind",
                    sa.String(length=50),
                    nullable=False,
                    server_default="routed_turn",
                ),
            )
        if "bound_session_payload" not in column_names:
            batch_op.add_column(
                sa.Column(
                    "bound_session_payload",
                    sa.JSON(),
                    nullable=False,
                    server_default=sa.text("'{}'"),
                ),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = "orchestration_ingress_requests"
    if not inspector.has_table(table_name):
        return

    column_names = {column["name"] for column in inspector.get_columns(table_name)}
    with op.batch_alter_table(table_name) as batch_op:
        if "bound_session_payload" in column_names:
            batch_op.drop_column("bound_session_payload")
        if "kind" in column_names:
            batch_op.drop_column("kind")
