"""drop legacy agent profiles table

Revision ID: 0026_drop_agent_profiles_table
Revises: 0025_authorization_temporary_grants
Create Date: 2026-03-25 11:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0026_drop_agent_profiles_table"
down_revision = "0025_authorization_temporary_grants"
branch_labels = None
depends_on = None


_BATCH_NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    _drop_sessions_agent_fk(bind, inspector)

    if inspector.has_table("agents"):
        op.drop_table("agents")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("agents"):
        op.create_table(
            "agents",
            sa.Column("id", sa.String(length=100), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
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
            sa.Column(
                "tool_preferences_payload",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    if inspector.has_table("sessions"):
        bind.execute(
            sa.text(
                """
                UPDATE sessions
                SET agent_id = NULL
                WHERE agent_id IS NOT NULL
                """,
            ),
        )
        if bind.dialect.name == "postgresql":
            op.create_foreign_key(
                "fk_sessions_agent_id_agents",
                "sessions",
                "agents",
                ["agent_id"],
                ["id"],
            )
        else:
            with op.batch_alter_table(
                "sessions",
                recreate="always",
                naming_convention=_BATCH_NAMING_CONVENTION,
            ) as batch_op:
                batch_op.create_foreign_key(
                    "fk_sessions_agent_id_agents",
                    "agents",
                    ["agent_id"],
                    ["id"],
                )


def _drop_sessions_agent_fk(bind: sa.Connection, inspector: sa.Inspector) -> None:
    if not inspector.has_table("sessions"):
        return

    constraint_name: str | None = None
    for foreign_key in inspector.get_foreign_keys("sessions"):
        if foreign_key.get("referred_table") != "agents":
            continue
        constrained_columns = tuple(foreign_key.get("constrained_columns") or ())
        if constrained_columns != ("agent_id",):
            continue
        constraint_name = foreign_key.get("name") or "fk_sessions_agent_id_agents"
        break

    if constraint_name is None:
        return

    if bind.dialect.name == "postgresql":
        op.drop_constraint(constraint_name, "sessions", type_="foreignkey")
    else:
        with op.batch_alter_table(
            "sessions",
            recreate="always",
            naming_convention=_BATCH_NAMING_CONVENTION,
        ) as batch_op:
            batch_op.drop_constraint(constraint_name, type_="foreignkey")


def _bool_default(bind: sa.Connection, value: bool) -> sa.TextClause:
    if bind.dialect.name == "postgresql":
        return sa.text("true" if value else "false")
    return sa.text("1" if value else "0")
