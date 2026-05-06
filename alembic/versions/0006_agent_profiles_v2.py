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

    if bind.dialect.name == "postgresql":
        _drop_agents_default_llm_fk(inspector)
        for column in _agent_profile_v2_columns(bind):
            op.add_column("agents", column)
        op.drop_column("agents", "default_llm_id")
        op.drop_column("agents", "tool_ids")
    else:
        with op.batch_alter_table("agents", recreate="always") as batch_op:
            for column in _agent_profile_v2_columns(bind):
                batch_op.add_column(column)
            batch_op.drop_column("default_llm_id")
            batch_op.drop_column("tool_ids")

    for row in existing_profiles:
        bind.execute(
            _agent_profile_policy_update_stmt(bind),
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

    old_columns = _legacy_agent_profile_columns()
    if bind.dialect.name == "postgresql":
        for column in old_columns:
            op.add_column("agents", column)
        for column_name in reversed(_agent_profile_v2_column_names()):
            op.drop_column("agents", column_name)
    else:
        with op.batch_alter_table("agents", recreate="always") as batch_op:
            for column in old_columns:
                batch_op.add_column(column)
            for column_name in reversed(_agent_profile_v2_column_names()):
                batch_op.drop_column(column_name)

    for row in existing_profiles:
        payload = row.llm_routing_policy_payload
        if isinstance(payload, str):
            payload = json.loads(payload)
        payload = payload or {}
        bind.execute(
            _legacy_agent_profile_update_stmt(bind),
            {
                "id": row.id,
                "default_llm_id": str(payload.get("default_llm_id", "")),
                "tool_ids": json.dumps([]),
            },
        )

    op.create_index("ix_agents_default_llm_id", "agents", ["default_llm_id"])

    if bind.dialect.name == "sqlite":
        op.execute(sa.text("PRAGMA foreign_keys=ON"))


def _agent_profile_v2_columns(bind: sa.Connection) -> tuple[sa.Column, ...]:
    return (
        sa.Column("description", sa.String(length=500), nullable=False, server_default=""),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=_bool_default(bind, True),
        ),
        sa.Column(
            "identity_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "instruction_policy_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "llm_routing_policy_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "execution_policy_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "runtime_preferences_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def _agent_profile_v2_column_names() -> tuple[str, ...]:
    return tuple(column.name for column in _agent_profile_v2_columns(op.get_bind()))


def _legacy_agent_profile_columns() -> tuple[sa.Column, ...]:
    return (
        sa.Column("default_llm_id", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("tool_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )


def _drop_agents_default_llm_fk(inspector: sa.Inspector) -> None:
    constraint_name: str | None = None
    for foreign_key in inspector.get_foreign_keys("agents"):
        constrained_columns = tuple(foreign_key.get("constrained_columns") or ())
        if constrained_columns != ("default_llm_id",):
            continue
        constraint_name = foreign_key.get("name")
        break
    if constraint_name:
        op.drop_constraint(constraint_name, "agents", type_="foreignkey")


def _bool_default(bind: sa.Connection, value: bool) -> sa.TextClause:
    if bind.dialect.name == "postgresql":
        return sa.text("true" if value else "false")
    return sa.text("1" if value else "0")


def _agent_profile_policy_update_stmt(bind: sa.Connection) -> sa.TextClause:
    if bind.dialect.name == "postgresql":
        return sa.text(
            """
            UPDATE agents
            SET llm_routing_policy_payload = CAST(:payload AS JSON),
                execution_policy_payload = CAST(:execution_policy_payload AS JSON),
                runtime_preferences_payload = CAST(:runtime_preferences_payload AS JSON)
            WHERE id = :id
            """,
        )
    return sa.text(
        """
        UPDATE agents
        SET llm_routing_policy_payload = :payload,
            execution_policy_payload = :execution_policy_payload,
            runtime_preferences_payload = :runtime_preferences_payload
        WHERE id = :id
        """,
    )


def _legacy_agent_profile_update_stmt(bind: sa.Connection) -> sa.TextClause:
    if bind.dialect.name == "postgresql":
        return sa.text(
            """
            UPDATE agents
            SET default_llm_id = :default_llm_id,
                tool_ids = CAST(:tool_ids AS JSON)
            WHERE id = :id
            """,
        )
    return sa.text(
        """
        UPDATE agents
        SET default_llm_id = :default_llm_id,
            tool_ids = :tool_ids
        WHERE id = :id
        """,
    )
