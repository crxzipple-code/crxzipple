"""create memory spaces table

Revision ID: 0057_memory_spaces
Revises: 0056_skill_authoring_audit
Create Date: 2026-05-22 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0057_memory_spaces"
down_revision = "0056_skill_authoring_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    created = False
    if not inspector.has_table("memory_spaces"):
        op.create_table(
            "memory_spaces",
            sa.Column("scope_ref", sa.String(length=255), primary_key=True),
            sa.Column("owner_kind", sa.String(length=60), nullable=False),
            sa.Column("owner_id", sa.String(length=255), nullable=False),
            sa.Column("engine_id", sa.String(length=120), nullable=False),
            sa.Column("storage_root", sa.String(length=1000), nullable=False),
            sa.Column("retrieval_backend", sa.String(length=60), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("metadata_payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        created = True

    _ensure_index(
        inspector,
        "memory_spaces",
        "ix_memory_spaces_owner_kind",
        ["owner_kind"],
        created=created,
    )
    _ensure_index(
        inspector,
        "memory_spaces",
        "ix_memory_spaces_owner_id",
        ["owner_id"],
        created=created,
    )
    _ensure_index(
        inspector,
        "memory_spaces",
        "ix_memory_spaces_engine_id",
        ["engine_id"],
        created=created,
    )
    _ensure_index(
        inspector,
        "memory_spaces",
        "ix_memory_spaces_status",
        ["status"],
        created=created,
    )
    _ensure_index(
        inspector,
        "memory_spaces",
        "ix_memory_spaces_updated_at",
        ["updated_at"],
        created=created,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("memory_spaces"):
        for index_name in (
            "ix_memory_spaces_updated_at",
            "ix_memory_spaces_status",
            "ix_memory_spaces_engine_id",
            "ix_memory_spaces_owner_id",
            "ix_memory_spaces_owner_kind",
        ):
            _drop_index_if_exists(inspector, "memory_spaces", index_name)
        op.drop_table("memory_spaces")


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
