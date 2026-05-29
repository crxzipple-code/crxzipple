"""llm profiles reference access credential bindings

Revision ID: 0045_llm_access_credential_binding_refs
Revises: 0044_authorization_owned_persistence
Create Date: 2026-05-10 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0045_llm_access_credential_binding_refs"
down_revision = "0044_authorization_owned_persistence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("llm_profiles"):
        return

    columns = {column["name"] for column in inspector.get_columns("llm_profiles")}
    if "credential_binding" in columns and "credential_binding_id" not in columns:
        with op.batch_alter_table("llm_profiles") as batch_op:
            batch_op.alter_column(
                "credential_binding",
                new_column_name="credential_binding_id",
                existing_type=sa.String(length=255),
                existing_nullable=True,
            )
    elif "credential_binding_id" not in columns:
        op.add_column(
            "llm_profiles",
            sa.Column("credential_binding_id", sa.String(length=255), nullable=True),
        )
    elif "credential_binding" in columns:
        with op.batch_alter_table("llm_profiles") as batch_op:
            batch_op.drop_column("credential_binding")

    _normalize_default_binding_ids(bind)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("llm_profiles"):
        return

    columns = {column["name"] for column in inspector.get_columns("llm_profiles")}
    if "credential_binding_id" in columns and "credential_binding" not in columns:
        with op.batch_alter_table("llm_profiles") as batch_op:
            batch_op.alter_column(
                "credential_binding_id",
                new_column_name="credential_binding",
                existing_type=sa.String(length=255),
                existing_nullable=True,
            )


def _normalize_default_binding_ids(bind: sa.engine.Connection) -> None:
    bind.execute(
        sa.text(
            """
            UPDATE llm_profiles
            SET credential_binding_id = NULL
            WHERE credential_binding_id = 'EMPTY'
            """,
        ),
    )
    bind.execute(
        sa.text(
            """
            UPDATE llm_profiles
            SET credential_binding_id = 'openai-api-key'
            WHERE credential_binding_id = 'env:OPENAI_API_KEY'
            """,
        ),
    )
    bind.execute(
        sa.text(
            """
            UPDATE llm_profiles
            SET credential_binding_id = 'codex-auth-json'
            WHERE credential_binding_id IN (
                'codex_auth_json',
                'codex-auth-json',
                'codex-cli',
                'codex_auth_json:'
            )
            """,
        ),
    )
