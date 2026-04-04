"""drop legacy tool definitions table

Revision ID: 0028_drop_tool_definitions_table
Revises: 0027_tool_run_invocation_context
Create Date: 2026-03-29 15:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0028_drop_tool_definitions_table"
down_revision = "0027_tool_run_invocation_context"
branch_labels = None
depends_on = None


_BATCH_NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    _drop_tool_runs_tool_fk(inspector)

    if inspector.has_table("tools"):
        op.drop_table("tools")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("tools"):
        op.create_table(
            "tools",
            sa.Column("id", sa.String(length=100), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column(
                "kind",
                sa.String(length=50),
                nullable=False,
                server_default="function",
            ),
            sa.Column(
                "parameters",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
            sa.Column(
                "tags",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
            sa.Column(
                "required_effect_ids",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
            sa.Column(
                "requires_confirmation",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "mutates_state",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "timeout_seconds",
                sa.Integer(),
                nullable=False,
                server_default="30",
            ),
            sa.Column(
                "supported_modes",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
            sa.Column(
                "supported_strategies",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
            sa.Column(
                "supported_environments",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
            sa.Column(
                "source_kind",
                sa.String(length=50),
                nullable=False,
                server_default="manual",
            ),
            sa.Column("runtime_key", sa.String(length=255), nullable=True),
            sa.Column(
                "enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("1"),
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    if inspector.has_table("tool_runs"):
        bind.execute(
            sa.text(
                """
                INSERT INTO tools (
                    id,
                    name,
                    description,
                    kind,
                    parameters,
                    tags,
                    required_effect_ids,
                    requires_confirmation,
                    mutates_state,
                    timeout_seconds,
                    supported_modes,
                    supported_strategies,
                    supported_environments,
                    source_kind,
                    runtime_key,
                    enabled
                )
                SELECT
                    tool_id,
                    tool_id,
                    '',
                    'function',
                    '[]',
                    '[]',
                    '[]',
                    0,
                    0,
                    30,
                    '[]',
                    '[]',
                    '[]',
                    'manual',
                    NULL,
                    1
                FROM (
                    SELECT DISTINCT tool_id
                    FROM tool_runs
                ) AS distinct_tool_ids
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM tools
                    WHERE tools.id = distinct_tool_ids.tool_id
                )
                """,
            ),
        )
        with op.batch_alter_table(
            "tool_runs",
            recreate="always",
            naming_convention=_BATCH_NAMING_CONVENTION,
        ) as batch_op:
            batch_op.create_foreign_key(
                "fk_tool_runs_tool_id_tools",
                "tools",
                ["tool_id"],
                ["id"],
            )


def _drop_tool_runs_tool_fk(inspector: sa.Inspector) -> None:
    if not inspector.has_table("tool_runs"):
        return

    constraint_name: str | None = None
    for foreign_key in inspector.get_foreign_keys("tool_runs"):
        if foreign_key.get("referred_table") != "tools":
            continue
        constrained_columns = tuple(foreign_key.get("constrained_columns") or ())
        if constrained_columns != ("tool_id",):
            continue
        constraint_name = foreign_key.get("name") or "fk_tool_runs_tool_id_tools"
        break

    if constraint_name is None:
        return

    with op.batch_alter_table(
        "tool_runs",
        recreate="always",
        naming_convention=_BATCH_NAMING_CONVENTION,
    ) as batch_op:
        batch_op.drop_constraint(constraint_name, type_="foreignkey")
