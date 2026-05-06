"""llm subsystem v2

Revision ID: 0005_llm_subsystem_v2
Revises: 0004_tool_run_reliability
Create Date: 2026-03-22 06:00:00
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "0005_llm_subsystem_v2"
down_revision = "0004_tool_run_reliability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    op.rename_table("llms", "llm_profiles")

    if bind.dialect.name == "postgresql":
        for column in _llm_profile_v2_columns():
            op.add_column("llm_profiles", column)
    else:
        with op.batch_alter_table("llm_profiles", recreate="always") as batch_op:
            for column in _llm_profile_v2_columns():
                batch_op.add_column(column)

    existing_profiles = bind.execute(
        sa.text("SELECT id, temperature FROM llm_profiles"),
    ).fetchall()
    for row in existing_profiles:
        default_params = json.dumps({"temperature": row.temperature})
        bind.execute(
            _default_params_update_stmt(bind),
            {"id": row.id, "default_params": default_params},
        )

    if bind.dialect.name == "postgresql":
        op.drop_column("llm_profiles", "temperature")
    else:
        with op.batch_alter_table("llm_profiles", recreate="always") as batch_op:
            batch_op.drop_column("temperature")

    op.create_table(
        "llm_invocations",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("llm_id", sa.String(length=100), nullable=False),
        sa.Column("messages", sa.JSON(), nullable=False),
        sa.Column("tool_schemas", sa.JSON(), nullable=False),
        sa.Column("response_format", sa.JSON(), nullable=True),
        sa.Column("request_overrides", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("result_payload", sa.JSON(), nullable=True),
        sa.Column("error_payload", sa.JSON(), nullable=True),
        sa.Column("provider_request_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["llm_id"], ["llm_profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_llm_invocations_llm_id", "llm_invocations", ["llm_id"])


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_index("ix_llm_invocations_llm_id", table_name="llm_invocations")
    op.drop_table("llm_invocations")

    temperature_column = sa.Column(
        "temperature",
        sa.Float(),
        nullable=False,
        server_default="0.0",
    )
    if bind.dialect.name == "postgresql":
        op.add_column("llm_profiles", temperature_column)
    else:
        with op.batch_alter_table("llm_profiles", recreate="always") as batch_op:
            batch_op.add_column(temperature_column)

    existing_profiles = bind.execute(
        sa.text("SELECT id, default_params FROM llm_profiles"),
    ).fetchall()
    for row in existing_profiles:
        temperature = 0.0
        if row.default_params:
            try:
                payload = (
                    row.default_params
                    if isinstance(row.default_params, dict)
                    else json.loads(row.default_params)
                )
            except (TypeError, json.JSONDecodeError):
                payload = {}
            if isinstance(payload, dict) and payload.get("temperature") is not None:
                temperature = float(payload["temperature"])
        bind.execute(
            sa.text("UPDATE llm_profiles SET temperature = :temperature WHERE id = :id"),
            {"id": row.id, "temperature": temperature},
        )

    if bind.dialect.name == "postgresql":
        for column_name in reversed(_llm_profile_v2_column_names()):
            op.drop_column("llm_profiles", column_name)
    else:
        with op.batch_alter_table("llm_profiles", recreate="always") as batch_op:
            for column_name in reversed(_llm_profile_v2_column_names()):
                batch_op.drop_column(column_name)

    op.rename_table("llm_profiles", "llms")


def _llm_profile_v2_columns() -> tuple[sa.Column, ...]:
    return (
        sa.Column(
            "api_family",
            sa.String(length=100),
            nullable=False,
            server_default="openai_responses",
        ),
        sa.Column(
            "model_family",
            sa.String(length=100),
            nullable=False,
            server_default="general",
        ),
        sa.Column(
            "capabilities",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "default_params",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("base_url", sa.String(length=500), nullable=True),
        sa.Column("credential_binding", sa.String(length=255), nullable=True),
        sa.Column(
            "timeout_seconds",
            sa.Integer(),
            nullable=False,
            server_default="60",
        ),
        sa.Column(
            "source_kind",
            sa.String(length=100),
            nullable=False,
            server_default="manual",
        ),
    )


def _llm_profile_v2_column_names() -> tuple[str, ...]:
    return tuple(column.name for column in _llm_profile_v2_columns())


def _default_params_update_stmt(bind: sa.Connection) -> sa.TextClause:
    if bind.dialect.name == "postgresql":
        return sa.text(
            """
            UPDATE llm_profiles
            SET default_params = CAST(:default_params AS JSON)
            WHERE id = :id
            """,
        )
    return sa.text(
        "UPDATE llm_profiles SET default_params = :default_params WHERE id = :id",
    )
