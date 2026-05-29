"""create memory policies table

Revision ID: 0058_memory_policies
Revises: 0057_memory_spaces
Create Date: 2026-05-22 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0058_memory_policies"
down_revision = "0057_memory_spaces"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    created = False
    if not inspector.has_table("memory_policies"):
        op.create_table(
            "memory_policies",
            sa.Column("policy_id", sa.String(length=255), primary_key=True),
            sa.Column("target_kind", sa.String(length=60), nullable=False),
            sa.Column("target_id", sa.String(length=255), nullable=True),
            sa.Column("recall_enabled", sa.Boolean(), nullable=False),
            sa.Column("remember_enabled", sa.Boolean(), nullable=False),
            sa.Column("max_recall_items", sa.Integer(), nullable=False),
            sa.Column("retention", sa.String(length=80), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("metadata_payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        created = True

    _ensure_index(
        inspector,
        "memory_policies",
        "ix_memory_policies_target_kind",
        ["target_kind"],
        created=created,
    )
    _ensure_index(
        inspector,
        "memory_policies",
        "ix_memory_policies_target_id",
        ["target_id"],
        created=created,
    )
    _ensure_index(
        inspector,
        "memory_policies",
        "ix_memory_policies_status",
        ["status"],
        created=created,
    )
    _ensure_index(
        inspector,
        "memory_policies",
        "ix_memory_policies_updated_at",
        ["updated_at"],
        created=created,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("memory_policies"):
        for index_name in (
            "ix_memory_policies_updated_at",
            "ix_memory_policies_status",
            "ix_memory_policies_target_id",
            "ix_memory_policies_target_kind",
        ):
            _drop_index_if_exists(inspector, "memory_policies", index_name)
        op.drop_table("memory_policies")


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
