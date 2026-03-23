"""agent profiles v2

Revision ID: 0006_agent_profiles_v2
Revises: 0005_llm_subsystem_v2
Create Date: 2026-03-22 22:30:00
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "0006_agent_profiles_v2"
down_revision = "0005_llm_subsystem_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_profiles = bind.execute(
        sa.text("SELECT id, default_llm_id FROM agents"),
    ).fetchall()

    if bind.dialect.name == "sqlite":
        op.execute(sa.text("PRAGMA foreign_keys=OFF"))
        op.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_agents"))

    agent_indexes = {index["name"] for index in inspector.get_indexes("agents")}
    if "ix_agents_default_llm_id" in agent_indexes:
        op.drop_index("ix_agents_default_llm_id", table_name="agents")

    with op.batch_alter_table("agents", recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column("description", sa.String(length=500), nullable=False, server_default=""),
        )
        batch_op.add_column(
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        )
        batch_op.add_column(
            sa.Column(
                "identity_payload",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
        )
        batch_op.add_column(
            sa.Column(
                "instruction_policy_payload",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
        )
        batch_op.add_column(
            sa.Column(
                "llm_routing_policy_payload",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
        )
        batch_op.add_column(
            sa.Column(
                "execution_policy_payload",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
        )
        batch_op.add_column(
            sa.Column(
                "runtime_preferences_payload",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
        )
        batch_op.drop_column("default_llm_id")
        batch_op.drop_column("tool_ids")

    for row in existing_profiles:
        bind.execute(
            sa.text(
                """
                UPDATE agents
                SET llm_routing_policy_payload = :payload,
                    execution_policy_payload = :execution_policy_payload,
                    runtime_preferences_payload = :runtime_preferences_payload
                WHERE id = :id
                """,
            ),
            {
                "id": row.id,
                "payload": json.dumps(
                    {
                        "default_llm_id": row.default_llm_id,
                        "fallback_llm_ids": [],
                    },
                ),
                "execution_policy_payload": json.dumps(
                    {"timeout_seconds": 120, "max_turns": 12},
                ),
                "runtime_preferences_payload": json.dumps({"attrs": {}}),
            },
        )

    if bind.dialect.name == "sqlite":
        op.execute(sa.text("PRAGMA foreign_keys=ON"))


def downgrade() -> None:
    bind = op.get_bind()
    existing_profiles = bind.execute(
        sa.text("SELECT id, llm_routing_policy_payload FROM agents"),
    ).fetchall()

    if bind.dialect.name == "sqlite":
        op.execute(sa.text("PRAGMA foreign_keys=OFF"))
        op.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_agents"))

    with op.batch_alter_table("agents", recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column("default_llm_id", sa.String(length=100), nullable=False, server_default=""),
        )
        batch_op.add_column(
            sa.Column("tool_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        )
        batch_op.drop_column("runtime_preferences_payload")
        batch_op.drop_column("execution_policy_payload")
        batch_op.drop_column("llm_routing_policy_payload")
        batch_op.drop_column("instruction_policy_payload")
        batch_op.drop_column("identity_payload")
        batch_op.drop_column("enabled")
        batch_op.drop_column("description")

    for row in existing_profiles:
        payload = row.llm_routing_policy_payload
        if isinstance(payload, str):
            payload = json.loads(payload)
        payload = payload or {}
        bind.execute(
            sa.text(
                """
                UPDATE agents
                SET default_llm_id = :default_llm_id,
                    tool_ids = :tool_ids
                WHERE id = :id
                """,
            ),
            {
                "id": row.id,
                "default_llm_id": str(payload.get("default_llm_id", "")),
                "tool_ids": json.dumps([]),
            },
        )

    op.create_index("ix_agents_default_llm_id", "agents", ["default_llm_id"])

    if bind.dialect.name == "sqlite":
        op.execute(sa.text("PRAGMA foreign_keys=ON"))
