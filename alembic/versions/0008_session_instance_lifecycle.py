"""session instance lifecycle

Revision ID: 0008_session_instance_lifecycle
Revises: 0007_session_subsystem_v2
Create Date: 2026-03-22 23:55:00
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "0008_session_instance_lifecycle"
down_revision = "0007_session_subsystem_v2"
branch_labels = None
depends_on = None


def _infer_kind(session_key: str, chat_type: str | None) -> str:
    if ":thread:" in session_key:
        return "thread"
    if ":group:" in session_key:
        return "group"
    if ":channel:" in session_key:
        return "channel"
    if ":dm:" in session_key:
        return "direct"
    if chat_type == "thread":
        return "thread"
    if chat_type == "group":
        return "group"
    if chat_type == "channel":
        return "channel"
    return "main"


def upgrade() -> None:
    op.create_table(
        "session_instances",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("session_key", sa.String(length=255), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="active",
        ),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reset_reason", sa.String(length=50), nullable=True),
        sa.Column("metadata_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.ForeignKeyConstraint(["session_key"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_session_instances_session_key",
        "session_instances",
        ["session_key"],
    )

    bind = op.get_bind()
    now = datetime.now(timezone.utc)
    rows = bind.execute(
        sa.text(
            """
            SELECT id, active_session_id, agent_id, llm_id, chat_type, created_at, last_reset_at
            FROM sessions
            """,
        ),
    ).mappings()

    for row in rows:
        opened_at = row["last_reset_at"] or row["created_at"] or now
        bind.execute(
            sa.text(
                """
                INSERT INTO session_instances (
                    id,
                    session_key,
                    sequence_no,
                    kind,
                    status,
                    opened_at,
                    closed_at,
                    reset_reason,
                    metadata_payload
                ) VALUES (
                    :id,
                    :session_key,
                    :sequence_no,
                    :kind,
                    :status,
                    :opened_at,
                    :closed_at,
                    :reset_reason,
                    :metadata_payload
                )
                """,
            ),
            {
                "id": row["active_session_id"],
                "session_key": row["id"],
                "sequence_no": 1,
                "kind": _infer_kind(row["id"], row["chat_type"]),
                "status": "active",
                "opened_at": opened_at,
                "closed_at": None,
                "reset_reason": None,
                "metadata_payload": {
                    "agent_id": row["agent_id"],
                    "llm_id": row["llm_id"],
                },
            },
        )


def downgrade() -> None:
    op.drop_index("ix_session_instances_session_key", table_name="session_instances")
    op.drop_table("session_instances")
