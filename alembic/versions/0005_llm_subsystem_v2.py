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

    with op.batch_alter_table("llm_profiles", recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column(
                "api_family",
                sa.String(length=100),
                nullable=False,
                server_default="openai_responses",
            ),
        )
        batch_op.add_column(
            sa.Column(
                "model_family",
                sa.String(length=100),
                nullable=False,
                server_default="general",
            ),
        )
        batch_op.add_column(
            sa.Column(
                "capabilities",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
        )
        batch_op.add_column(
            sa.Column(
                "default_params",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
        )
        batch_op.add_column(
            sa.Column("base_url", sa.String(length=500), nullable=True),
        )
        batch_op.add_column(
            sa.Column("credential_binding", sa.String(length=255), nullable=True),
        )
        batch_op.add_column(
            sa.Column(
                "timeout_seconds",
                sa.Integer(),
                nullable=False,
                server_default="60",
            ),
        )
        batch_op.add_column(
            sa.Column(
                "source_kind",
                sa.String(length=100),
                nullable=False,
                server_default="manual",
            ),
        )

    existing_profiles = bind.execute(
        sa.text("SELECT id, temperature FROM llm_profiles"),
    ).fetchall()
    for row in existing_profiles:
        default_params = json.dumps({"temperature": row.temperature})
        bind.execute(
            sa.text(
                "UPDATE llm_profiles SET default_params = :default_params WHERE id = :id",
            ),
            {"id": row.id, "default_params": default_params},
        )

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

    with op.batch_alter_table("llm_profiles", recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column(
                "temperature",
                sa.Float(),
                nullable=False,
                server_default="0.0",
            ),
        )

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

    with op.batch_alter_table("llm_profiles", recreate="always") as batch_op:
        batch_op.drop_column("source_kind")
        batch_op.drop_column("timeout_seconds")
        batch_op.drop_column("credential_binding")
        batch_op.drop_column("base_url")
        batch_op.drop_column("default_params")
        batch_op.drop_column("capabilities")
        batch_op.drop_column("model_family")
        batch_op.drop_column("api_family")

    op.rename_table("llm_profiles", "llms")
