"""create skill authoring audit table

Revision ID: 0056_skill_authoring_audit
Revises: 0055_skill_authoring_drafts
Create Date: 2026-05-21 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0056_skill_authoring_audit"
down_revision = "0055_skill_authoring_drafts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    created = False
    if not inspector.has_table("skill_authoring_audit"):
        op.create_table(
            "skill_authoring_audit",
            sa.Column("audit_id", sa.String(length=160), primary_key=True),
            sa.Column("draft_id", sa.String(length=160), nullable=False),
            sa.Column("action", sa.String(length=80), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("actor", sa.String(length=160), nullable=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("before_payload", sa.JSON(), nullable=False),
            sa.Column("after_payload", sa.JSON(), nullable=False),
            sa.Column("metadata_payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        created = True

    _ensure_index(
        inspector,
        "skill_authoring_audit",
        "ix_skill_authoring_audit_draft_id",
        ["draft_id"],
        created=created,
    )
    _ensure_index(
        inspector,
        "skill_authoring_audit",
        "ix_skill_authoring_audit_action",
        ["action"],
        created=created,
    )
    _ensure_index(
        inspector,
        "skill_authoring_audit",
        "ix_skill_authoring_audit_status",
        ["status"],
        created=created,
    )
    _ensure_index(
        inspector,
        "skill_authoring_audit",
        "ix_skill_authoring_audit_created_at",
        ["created_at"],
        created=created,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("skill_authoring_audit"):
        for index_name in (
            "ix_skill_authoring_audit_created_at",
            "ix_skill_authoring_audit_status",
            "ix_skill_authoring_audit_action",
            "ix_skill_authoring_audit_draft_id",
        ):
            _drop_index_if_exists(inspector, "skill_authoring_audit", index_name)
        op.drop_table("skill_authoring_audit")


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
