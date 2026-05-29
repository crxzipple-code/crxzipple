"""create skill owner catalog tables

Revision ID: 0053_skill_owner_catalog
Revises: 0052_tool_source_discovery_runs
Create Date: 2026-05-20 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0053_skill_owner_catalog"
down_revision = "0052_tool_source_discovery_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    created_sources = False
    if not inspector.has_table("skill_sources"):
        op.create_table(
            "skill_sources",
            sa.Column("source_id", sa.String(length=120), primary_key=True),
            sa.Column("source_type", sa.String(length=60), nullable=False),
            sa.Column("root_uri", sa.String(length=1000), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("sync_status", sa.String(length=50), nullable=False),
            sa.Column("scope", sa.String(length=120), nullable=True),
            sa.Column("priority", sa.Integer(), nullable=False),
            sa.Column(
                "enabled",
                sa.Boolean(),
                nullable=False,
                server_default=_bool_default(bind, True),
            ),
            sa.Column(
                "readonly",
                sa.Boolean(),
                nullable=False,
                server_default=_bool_default(bind, False),
            ),
            sa.Column("metadata_payload", sa.JSON(), nullable=False),
            sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        created_sources = True
    _ensure_index(
        inspector,
        "skill_sources",
        "ix_skill_sources_source_type",
        ["source_type"],
        created=created_sources,
    )
    _ensure_index(
        inspector,
        "skill_sources",
        "ix_skill_sources_status",
        ["status"],
        created=created_sources,
    )
    _ensure_index(
        inspector,
        "skill_sources",
        "ix_skill_sources_sync_status",
        ["sync_status"],
        created=created_sources,
    )
    _ensure_index(
        inspector,
        "skill_sources",
        "ix_skill_sources_scope",
        ["scope"],
        created=created_sources,
    )

    created_packages = False
    if not inspector.has_table("skill_packages"):
        op.create_table(
            "skill_packages",
            sa.Column("package_id", sa.String(length=160), primary_key=True),
            sa.Column("skill_id", sa.String(length=160), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("source_id", sa.String(length=120), nullable=False),
            sa.Column("root_uri", sa.String(length=1000), nullable=False),
            sa.Column("manifest_uri", sa.String(length=1000), nullable=False),
            sa.Column("instructions_uri", sa.String(length=1000), nullable=False),
            sa.Column("version", sa.String(length=120), nullable=True),
            sa.Column("fingerprint", sa.String(length=160), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("requirements_payload", sa.JSON(), nullable=False),
            sa.Column("capability_requirements_payload", sa.JSON(), nullable=False),
            sa.Column("metadata_payload", sa.JSON(), nullable=False),
            sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "source_id", "name", name="uq_skill_packages_source_name"
            ),
            sa.UniqueConstraint(
                "source_id", "skill_id", name="uq_skill_packages_source_skill"
            ),
        )
        created_packages = True
    _ensure_index(
        inspector,
        "skill_packages",
        "ix_skill_packages_skill_id",
        ["skill_id"],
        created=created_packages,
    )
    _ensure_index(
        inspector,
        "skill_packages",
        "ix_skill_packages_name",
        ["name"],
        created=created_packages,
    )
    _ensure_index(
        inspector,
        "skill_packages",
        "ix_skill_packages_source_id",
        ["source_id"],
        created=created_packages,
    )
    _ensure_index(
        inspector,
        "skill_packages",
        "ix_skill_packages_fingerprint",
        ["fingerprint"],
        created=created_packages,
    )
    _ensure_index(
        inspector,
        "skill_packages",
        "ix_skill_packages_status",
        ["status"],
        created=created_packages,
    )

    created_policies = False
    if not inspector.has_table("skill_enablement_policies"):
        op.create_table(
            "skill_enablement_policies",
            sa.Column("policy_id", sa.String(length=160), primary_key=True),
            sa.Column("target_kind", sa.String(length=60), nullable=False),
            sa.Column("target_id", sa.String(length=255), nullable=True),
            sa.Column(
                "enabled",
                sa.Boolean(),
                nullable=False,
                server_default=_bool_default(bind, True),
            ),
            sa.Column(
                "trusted",
                sa.Boolean(),
                nullable=False,
                server_default=_bool_default(bind, False),
            ),
            sa.Column("runtime_visibility", sa.String(length=60), nullable=False),
            sa.Column("priority", sa.Integer(), nullable=False),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("metadata_payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        created_policies = True
    _ensure_index(
        inspector,
        "skill_enablement_policies",
        "ix_skill_enablement_policies_target_kind",
        ["target_kind"],
        created=created_policies,
    )
    _ensure_index(
        inspector,
        "skill_enablement_policies",
        "ix_skill_enablement_policies_target_id",
        ["target_id"],
        created=created_policies,
    )
    _ensure_index(
        inspector,
        "skill_enablement_policies",
        "ix_skill_enablement_policies_runtime_visibility",
        ["runtime_visibility"],
        created=created_policies,
    )

    created_readiness = False
    if not inspector.has_table("skill_readiness"):
        op.create_table(
            "skill_readiness",
            sa.Column("skill_id", sa.String(length=160), primary_key=True),
            sa.Column("source_id", sa.String(length=120), nullable=True),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("checks_payload", sa.JSON(), nullable=False),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("metadata_payload", sa.JSON(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        created_readiness = True
    _ensure_index(
        inspector,
        "skill_readiness",
        "ix_skill_readiness_source_id",
        ["source_id"],
        created=created_readiness,
    )
    _ensure_index(
        inspector,
        "skill_readiness",
        "ix_skill_readiness_status",
        ["status"],
        created=created_readiness,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("skill_readiness"):
        _drop_index_if_exists(inspector, "skill_readiness", "ix_skill_readiness_status")
        _drop_index_if_exists(
            inspector, "skill_readiness", "ix_skill_readiness_source_id"
        )
        op.drop_table("skill_readiness")

    if inspector.has_table("skill_enablement_policies"):
        _drop_index_if_exists(
            inspector,
            "skill_enablement_policies",
            "ix_skill_enablement_policies_runtime_visibility",
        )
        _drop_index_if_exists(
            inspector,
            "skill_enablement_policies",
            "ix_skill_enablement_policies_target_id",
        )
        _drop_index_if_exists(
            inspector,
            "skill_enablement_policies",
            "ix_skill_enablement_policies_target_kind",
        )
        op.drop_table("skill_enablement_policies")

    if inspector.has_table("skill_packages"):
        _drop_index_if_exists(inspector, "skill_packages", "ix_skill_packages_status")
        _drop_index_if_exists(
            inspector, "skill_packages", "ix_skill_packages_fingerprint"
        )
        _drop_index_if_exists(
            inspector, "skill_packages", "ix_skill_packages_source_id"
        )
        _drop_index_if_exists(inspector, "skill_packages", "ix_skill_packages_name")
        _drop_index_if_exists(inspector, "skill_packages", "ix_skill_packages_skill_id")
        op.drop_table("skill_packages")

    if inspector.has_table("skill_sources"):
        _drop_index_if_exists(inspector, "skill_sources", "ix_skill_sources_scope")
        _drop_index_if_exists(
            inspector, "skill_sources", "ix_skill_sources_sync_status"
        )
        _drop_index_if_exists(inspector, "skill_sources", "ix_skill_sources_status")
        _drop_index_if_exists(
            inspector, "skill_sources", "ix_skill_sources_source_type"
        )
        op.drop_table("skill_sources")


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


def _bool_default(bind: sa.engine.Connection, value: bool) -> sa.TextClause:
    if bind.dialect.name == "postgresql":
        return sa.text("true" if value else "false")
    return sa.text("1" if value else "0")
