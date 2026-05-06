"""session binding columns nullable

Revision ID: 0014_session_binding_columns_nullable
Revises: 0013_dispatch_task_leases
Create Date: 2026-03-23 13:30:00
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "0014_session_binding_columns_nullable"
down_revision = "0013_dispatch_task_leases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        op.alter_column(
            "sessions",
            "agent_id",
            existing_type=sa.String(length=100),
            nullable=True,
        )
        op.alter_column(
            "sessions",
            "llm_id",
            existing_type=sa.String(length=100),
            nullable=True,
        )
    else:
        with op.batch_alter_table("sessions", recreate="always") as batch_op:
            batch_op.alter_column(
                "agent_id",
                existing_type=sa.String(length=100),
                nullable=True,
            )
            batch_op.alter_column(
                "llm_id",
                existing_type=sa.String(length=100),
                nullable=True,
            )

    rows = bind.execute(
        sa.text(
            """
            SELECT id, agent_id, llm_id, metadata_payload
            FROM sessions
            """,
        ),
    ).all()

    for row in rows:
        metadata = _decode_json_payload(row.metadata_payload)
        runtime_binding = metadata.get("runtime_binding")
        if not isinstance(runtime_binding, dict):
            runtime_binding = {}
        changed = False
        if runtime_binding.get("agent_id") is None and row.agent_id is not None:
            runtime_binding["agent_id"] = row.agent_id
            changed = True
        if runtime_binding.get("llm_id") is None and row.llm_id is not None:
            runtime_binding["llm_id"] = row.llm_id
            changed = True
        if changed:
            metadata["runtime_binding"] = runtime_binding
            bind.execute(
                _metadata_update_stmt(bind),
                {
                    "id": row.id,
                    "metadata_payload": json.dumps(metadata),
                },
            )


def downgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT id, agent_id, llm_id, metadata_payload
            FROM sessions
            """,
        ),
    ).all()

    for row in rows:
        metadata = _decode_json_payload(row.metadata_payload)
        runtime_binding = metadata.get("runtime_binding")
        if not isinstance(runtime_binding, dict):
            runtime_binding = {}
        agent_id = row.agent_id or runtime_binding.get("agent_id")
        llm_id = row.llm_id or runtime_binding.get("llm_id")
        if agent_id is None or llm_id is None:
            raise RuntimeError(
                "Cannot downgrade 0014_session_binding_columns_nullable because "
                f"session '{row.id}' is missing agent_id or llm_id compatibility values.",
            )
        bind.execute(
            sa.text(
                """
                UPDATE sessions
                SET agent_id = :agent_id,
                    llm_id = :llm_id
                WHERE id = :id
                """,
            ),
            {
                "id": row.id,
                "agent_id": agent_id,
                "llm_id": llm_id,
            },
        )

    if bind.dialect.name == "postgresql":
        op.alter_column(
            "sessions",
            "agent_id",
            existing_type=sa.String(length=100),
            nullable=False,
        )
        op.alter_column(
            "sessions",
            "llm_id",
            existing_type=sa.String(length=100),
            nullable=False,
        )
    else:
        with op.batch_alter_table("sessions", recreate="always") as batch_op:
            batch_op.alter_column(
                "agent_id",
                existing_type=sa.String(length=100),
                nullable=False,
            )
            batch_op.alter_column(
                "llm_id",
                existing_type=sa.String(length=100),
                nullable=False,
            )


def _decode_json_payload(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        decoded = json.loads(value)
        if isinstance(decoded, dict):
            return dict(decoded)
    return {}


def _metadata_update_stmt(bind: sa.Connection) -> sa.TextClause:
    if bind.dialect.name == "postgresql":
        return sa.text(
            """
            UPDATE sessions
            SET metadata_payload = CAST(:metadata_payload AS JSON)
            WHERE id = :id
            """,
        )
    return sa.text(
        """
        UPDATE sessions
        SET metadata_payload = :metadata_payload
        WHERE id = :id
        """,
    )
