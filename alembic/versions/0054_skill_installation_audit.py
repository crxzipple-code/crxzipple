"""create skill installation audit table

Revision ID: 0054_skill_installation_audit
Revises: 0053_skill_owner_catalog
Create Date: 2026-05-21 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0054_skill_installation_audit"
down_revision = "0053_skill_owner_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    created = False
    if not inspector.has_table("skill_installations"):
        op.create_table(
            "skill_installations",
            sa.Column("installation_id", sa.String(length=160), primary_key=True),
            sa.Column("action", sa.String(length=80), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("source_id", sa.String(length=120), nullable=True),
            sa.Column("skill_id", sa.String(length=160), nullable=True),
            sa.Column("skill_name", sa.String(length=255), nullable=True),
            sa.Column("source_uri", sa.String(length=1000), nullable=True),
            sa.Column("target_uri", sa.String(length=1000), nullable=True),
            sa.Column("actor_id", sa.String(length=160), nullable=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("metadata_payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        created = True

    _ensure_index(inspector, "skill_installations", "ix_skill_installations_action", ["action"], created=created)
    _ensure_index(inspector, "skill_installations", "ix_skill_installations_status", ["status"], created=created)
    _ensure_index(inspector, "skill_installations", "ix_skill_installations_source_id", ["source_id"], created=created)
    _ensure_index(inspector, "skill_installations", "ix_skill_installations_skill_id", ["skill_id"], created=created)
    _ensure_index(inspector, "skill_installations", "ix_skill_installations_skill_name", ["skill_name"], created=created)
    _ensure_index(inspector, "skill_installations", "ix_skill_installations_created_at", ["created_at"], created=created)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("skill_installations"):
        _drop_index_if_exists(
            inspector,
            "skill_installations",
            "ix_skill_installations_created_at",
        )
        _drop_index_if_exists(
            inspector,
            "skill_installations",
            "ix_skill_installations_skill_name",
        )
        _drop_index_if_exists(
            inspector,
            "skill_installations",
            "ix_skill_installations_skill_id",
        )
        _drop_index_if_exists(
            inspector,
            "skill_installations",
            "ix_skill_installations_source_id",
        )
        _drop_index_if_exists(
            inspector,
            "skill_installations",
            "ix_skill_installations_status",
        )
        _drop_index_if_exists(
            inspector,
            "skill_installations",
            "ix_skill_installations_action",
        )
        op.drop_table("skill_installations")


def _ensure_index(
    inspector: sa.Inspector,
    table_name: str,
    index_name: str,
    columns: list[str],
    *,
    created: bool = False,
) -> None:
    _ = created
    existing = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name not in existing:
        op.create_index(index_name, table_name, columns)


def _drop_index_if_exists(
    inspector: sa.Inspector,
    table_name: str,
    index_name: str,
) -> None:
    existing = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name in existing:
        op.drop_index(index_name, table_name=table_name)
