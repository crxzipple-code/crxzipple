"""session subsystem v2

Revision ID: 0007_session_subsystem_v2
Revises: 0006_agent_profiles_v2
Create Date: 2026-03-22 23:30:00
"""

from __future__ import annotations

from datetime import datetime, timezone
import json

from alembic import op
import sqlalchemy as sa


revision = "0007_session_subsystem_v2"
down_revision = "0006_agent_profiles_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing_session_ids = [row.id for row in bind.execute(sa.text("SELECT id FROM sessions"))]

    if bind.dialect.name == "postgresql":
        for column in _session_v2_columns():
            op.add_column("sessions", column)
    else:
        with op.batch_alter_table("sessions", recreate="always") as batch_op:
            for column in _session_v2_columns():
                batch_op.add_column(column)

    op.create_index("ix_sessions_active_session_id", "sessions", ["active_session_id"])
    op.create_index("ix_sessions_channel", "sessions", ["channel"])

    now = datetime.now(timezone.utc)
    for session_id in existing_session_ids:
        bind.execute(
            _session_v2_update_stmt(bind),
            {
                "id": session_id,
                "active_session_id": session_id,
                "origin_payload": json.dumps({}),
                "delivery_payload": json.dumps({}),
                "metadata_payload": json.dumps({}),
                "created_at": now,
                "updated_at": now,
                "last_reset_at": now,
            },
        )

    op.create_table(
        "session_messages",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("session_key", sa.String(length=255), nullable=False),
        sa.Column("session_id", sa.String(length=100), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_key"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_session_messages_session_key",
        "session_messages",
        ["session_key"],
    )
    op.create_index(
        "ix_session_messages_session_id",
        "session_messages",
        ["session_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_index("ix_session_messages_session_id", table_name="session_messages")
    op.drop_index("ix_session_messages_session_key", table_name="session_messages")
    op.drop_table("session_messages")
    op.drop_index("ix_sessions_channel", table_name="sessions")
    op.drop_index("ix_sessions_active_session_id", table_name="sessions")

    if bind.dialect.name == "postgresql":
        for column_name in reversed(_session_v2_column_names()):
            op.drop_column("sessions", column_name)
    else:
        with op.batch_alter_table("sessions", recreate="always") as batch_op:
            for column_name in reversed(_session_v2_column_names()):
                batch_op.drop_column(column_name)


def _session_v2_columns() -> tuple[sa.Column, ...]:
    return (
        sa.Column(
            "active_session_id",
            sa.String(length=100),
            nullable=False,
            server_default="bootstrap-session",
        ),
        sa.Column("channel", sa.String(length=100), nullable=True),
        sa.Column("chat_type", sa.String(length=50), nullable=True),
        sa.Column(
            "origin_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "delivery_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "metadata_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("'1970-01-01 00:00:00'"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("'1970-01-01 00:00:00'"),
        ),
        sa.Column(
            "last_reset_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("'1970-01-01 00:00:00'"),
        ),
    )


def _session_v2_column_names() -> tuple[str, ...]:
    return tuple(column.name for column in _session_v2_columns())


def _session_v2_update_stmt(bind: sa.Connection) -> sa.TextClause:
    if bind.dialect.name == "postgresql":
        return sa.text(
            """
            UPDATE sessions
            SET active_session_id = :active_session_id,
                origin_payload = CAST(:origin_payload AS JSON),
                delivery_payload = CAST(:delivery_payload AS JSON),
                metadata_payload = CAST(:metadata_payload AS JSON),
                created_at = :created_at,
                updated_at = :updated_at,
                last_reset_at = :last_reset_at
            WHERE id = :id
            """,
        )
    return sa.text(
        """
        UPDATE sessions
        SET active_session_id = :active_session_id,
            origin_payload = :origin_payload,
            delivery_payload = :delivery_payload,
            metadata_payload = :metadata_payload,
            created_at = :created_at,
            updated_at = :updated_at,
            last_reset_at = :last_reset_at
        WHERE id = :id
        """,
    )
