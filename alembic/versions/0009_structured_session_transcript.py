"""structured session transcript

Revision ID: 0009_structured_session_transcript
Revises: 0008_session_instance_lifecycle
Create Date: 2026-03-23 00:25:00
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "0009_structured_session_transcript"
down_revision = "0008_session_instance_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("session_messages") as batch_op:
        batch_op.add_column(
            sa.Column(
                "sequence_no",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("1"),
            ),
        )
        batch_op.add_column(
            sa.Column(
                "kind",
                sa.String(length=50),
                nullable=False,
                server_default=sa.text("'message'"),
            ),
        )
        batch_op.add_column(
            sa.Column(
                "content_payload",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
        )
        batch_op.add_column(
            sa.Column("source_kind", sa.String(length=50), nullable=True),
        )
        batch_op.add_column(
            sa.Column("source_id", sa.String(length=100), nullable=True),
        )
        batch_op.add_column(
            sa.Column(
                "visibility",
                sa.String(length=50),
                nullable=False,
                server_default=sa.text("'default'"),
            ),
        )

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT id, session_id, role, content
            FROM session_messages
            ORDER BY session_id, created_at, id
            """,
        ),
    ).mappings()

    sequence_by_session_id: dict[str, int] = {}
    for row in rows:
        session_id = row["session_id"]
        next_sequence = sequence_by_session_id.get(session_id, 0) + 1
        sequence_by_session_id[session_id] = next_sequence
        bind.execute(
            sa.text(
                """
                UPDATE session_messages
                SET sequence_no = :sequence_no,
                    kind = :kind,
                    content_payload = :content_payload,
                    visibility = :visibility
                WHERE id = :id
                """,
            ),
            {
                "id": row["id"],
                "sequence_no": next_sequence,
                "kind": "tool_result" if row["role"] == "tool" else "message",
                "content_payload": json.dumps({"text": row["content"]}),
                "visibility": "default",
            },
        )


def downgrade() -> None:
    with op.batch_alter_table("session_messages") as batch_op:
        batch_op.drop_column("visibility")
        batch_op.drop_column("source_id")
        batch_op.drop_column("source_kind")
        batch_op.drop_column("content_payload")
        batch_op.drop_column("kind")
        batch_op.drop_column("sequence_no")
