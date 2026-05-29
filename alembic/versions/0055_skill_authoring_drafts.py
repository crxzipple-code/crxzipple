"""create skill authoring draft table

Revision ID: 0055_skill_authoring_drafts
Revises: 0054_skill_installation_audit
Create Date: 2026-05-21 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0055_skill_authoring_drafts"
down_revision = "0054_skill_installation_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    created = False
    if not inspector.has_table("skill_authoring_drafts"):
        op.create_table(
            "skill_authoring_drafts",
            sa.Column("draft_id", sa.String(length=160), primary_key=True),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("intent", sa.String(length=50), nullable=False),
            sa.Column("skill_name", sa.String(length=255), nullable=False),
            sa.Column("target_source_id", sa.String(length=120), nullable=True),
            sa.Column("target_scope", sa.String(length=50), nullable=False),
            sa.Column("workspace_dir", sa.String(length=1000), nullable=True),
            sa.Column("base_fingerprint", sa.String(length=160), nullable=True),
            sa.Column("manifest_payload", sa.JSON(), nullable=False),
            sa.Column("instructions_body", sa.Text(), nullable=False),
            sa.Column("support_files_payload", sa.JSON(), nullable=False),
            sa.Column("requirements_payload", sa.JSON(), nullable=False),
            sa.Column("validation_payload", sa.JSON(), nullable=True),
            sa.Column("diff_payload", sa.JSON(), nullable=True),
            sa.Column("created_by_run_id", sa.String(length=160), nullable=True),
            sa.Column("created_by_turn_id", sa.String(length=160), nullable=True),
            sa.Column("actor", sa.String(length=160), nullable=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        )
        created = True

    _ensure_index(
        inspector,
        "skill_authoring_drafts",
        "ix_skill_authoring_drafts_status",
        ["status"],
        created=created,
    )
    _ensure_index(
        inspector,
        "skill_authoring_drafts",
        "ix_skill_authoring_drafts_intent",
        ["intent"],
        created=created,
    )
    _ensure_index(
        inspector,
        "skill_authoring_drafts",
        "ix_skill_authoring_drafts_skill_name",
        ["skill_name"],
        created=created,
    )
    _ensure_index(
        inspector,
        "skill_authoring_drafts",
        "ix_skill_authoring_drafts_target_source_id",
        ["target_source_id"],
        created=created,
    )
    _ensure_index(
        inspector,
        "skill_authoring_drafts",
        "ix_skill_authoring_drafts_target_scope",
        ["target_scope"],
        created=created,
    )
    _ensure_index(
        inspector,
        "skill_authoring_drafts",
        "ix_skill_authoring_drafts_created_by_run_id",
        ["created_by_run_id"],
        created=created,
    )
    _ensure_index(
        inspector,
        "skill_authoring_drafts",
        "ix_skill_authoring_drafts_created_at",
        ["created_at"],
        created=created,
    )
    _ensure_index(
        inspector,
        "skill_authoring_drafts",
        "ix_skill_authoring_drafts_updated_at",
        ["updated_at"],
        created=created,
    )
    _ensure_index(
        inspector,
        "skill_authoring_drafts",
        "ix_skill_authoring_drafts_expires_at",
        ["expires_at"],
        created=created,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("skill_authoring_drafts"):
        for index_name in (
            "ix_skill_authoring_drafts_expires_at",
            "ix_skill_authoring_drafts_updated_at",
            "ix_skill_authoring_drafts_created_at",
            "ix_skill_authoring_drafts_created_by_run_id",
            "ix_skill_authoring_drafts_target_scope",
            "ix_skill_authoring_drafts_target_source_id",
            "ix_skill_authoring_drafts_skill_name",
            "ix_skill_authoring_drafts_intent",
            "ix_skill_authoring_drafts_status",
        ):
            _drop_index_if_exists(inspector, "skill_authoring_drafts", index_name)
        op.drop_table("skill_authoring_drafts")


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
