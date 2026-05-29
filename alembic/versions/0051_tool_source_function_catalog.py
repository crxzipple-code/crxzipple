"""create tool source and function catalog tables

Revision ID: 0051_tool_source_function_catalog
Revises: 0050_tool_run_metadata
Create Date: 2026-05-19 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0051_tool_source_function_catalog"
down_revision = "0050_tool_run_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    created_tool_sources = False
    if not inspector.has_table("tool_sources"):
        op.create_table(
            "tool_sources",
            sa.Column("source_id", sa.String(length=100), primary_key=True),
            sa.Column("kind", sa.String(length=50), nullable=False),
            sa.Column("display_name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("config_payload", sa.JSON(), nullable=False),
            sa.Column(
                "credential_requirements_payload",
                sa.JSON(),
                nullable=False,
            ),
            sa.Column("runtime_requirements_payload", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("config_hash", sa.String(length=128), nullable=False),
            sa.Column("last_discovered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_discovery_status", sa.String(length=50), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        created_tool_sources = True
    _ensure_index(
        inspector,
        "tool_sources",
        "ix_tool_sources_kind",
        ["kind"],
        created=created_tool_sources,
    )
    _ensure_index(
        inspector,
        "tool_sources",
        "ix_tool_sources_status",
        ["status"],
        created=created_tool_sources,
    )

    created_tool_functions = False
    if not inspector.has_table("tool_functions"):
        op.create_table(
            "tool_functions",
            sa.Column("function_id", sa.String(length=100), primary_key=True),
            sa.Column("source_id", sa.String(length=100), nullable=False),
            sa.Column("stable_key", sa.String(length=255), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("display_name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("input_schema_payload", sa.JSON(), nullable=False),
            sa.Column("runtime_kind", sa.String(length=50), nullable=False),
            sa.Column("handler_ref_payload", sa.JSON(), nullable=False),
            sa.Column("capability_ids_payload", sa.JSON(), nullable=False),
            sa.Column(
                "credential_requirements_payload",
                sa.JSON(),
                nullable=False,
            ),
            sa.Column("access_requirement_sets_payload", sa.JSON(), nullable=False),
            sa.Column("runtime_requirements_payload", sa.JSON(), nullable=False),
            sa.Column("required_effect_ids_payload", sa.JSON(), nullable=False),
            sa.Column("execution_support_payload", sa.JSON(), nullable=False),
            sa.Column(
                "enabled",
                sa.Boolean(),
                nullable=False,
                server_default=_bool_default(bind, True),
            ),
            sa.Column("trust_policy_payload", sa.JSON(), nullable=False),
            sa.Column("approval_policy_payload", sa.JSON(), nullable=False),
            sa.Column(
                "credential_binding_overrides_payload",
                sa.JSON(),
                nullable=False,
            ),
            sa.Column(
                "required_effect_overrides_payload",
                sa.JSON(),
                nullable=True,
            ),
            sa.Column("metadata_payload", sa.JSON(), nullable=False),
            sa.Column("schema_hash", sa.String(length=128), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("stale_since", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint(
                "stable_key",
                name="uq_tool_functions_stable_key",
            ),
        )
        created_tool_functions = True
    if not created_tool_functions:
        _upgrade_tool_functions(inspector)
    _ensure_index(
        inspector,
        "tool_functions",
        "ix_tool_functions_source_id",
        ["source_id"],
        created=created_tool_functions,
    )
    _ensure_index(
        inspector,
        "tool_functions",
        "ix_tool_functions_name",
        ["name"],
        created=created_tool_functions,
    )
    _ensure_index(
        inspector,
        "tool_functions",
        "ix_tool_functions_runtime_kind",
        ["runtime_kind"],
        created=created_tool_functions,
    )
    _ensure_index(
        inspector,
        "tool_functions",
        "ix_tool_functions_status",
        ["status"],
        created=created_tool_functions,
    )

    created_tool_provider_backends = False
    if not inspector.has_table("tool_provider_backends"):
        op.create_table(
            "tool_provider_backends",
            sa.Column("backend_id", sa.String(length=100), primary_key=True),
            sa.Column("source_id", sa.String(length=100), nullable=False),
            sa.Column("capability", sa.String(length=100), nullable=False),
            sa.Column("display_name", sa.String(length=255), nullable=False),
            sa.Column(
                "credential_requirements_payload",
                sa.JSON(),
                nullable=False,
            ),
            sa.Column("runtime_ref_payload", sa.JSON(), nullable=False),
            sa.Column("priority", sa.Integer(), nullable=False),
            sa.Column(
                "enabled",
                sa.Boolean(),
                nullable=False,
                server_default=_bool_default(bind, True),
            ),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        created_tool_provider_backends = True
    _ensure_index(
        inspector,
        "tool_provider_backends",
        "ix_tool_provider_backends_source_id",
        ["source_id"],
        created=created_tool_provider_backends,
    )
    _ensure_index(
        inspector,
        "tool_provider_backends",
        "ix_tool_provider_backends_capability",
        ["capability"],
        created=created_tool_provider_backends,
    )
    _ensure_index(
        inspector,
        "tool_provider_backends",
        "ix_tool_provider_backends_status",
        ["status"],
        created=created_tool_provider_backends,
    )

    _upgrade_tool_runs(inspector)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("tool_runs"):
        _drop_index_if_exists(inspector, "tool_runs", "ix_tool_runs_source_id")
        _drop_index_if_exists(inspector, "tool_runs", "ix_tool_runs_function_id")
        tool_run_columns = {
            column["name"]
            for column in inspector.get_columns("tool_runs")
        }
        with op.batch_alter_table("tool_runs") as batch_op:
            for column_name in (
                "schema_hash",
                "source_revision",
                "source_id",
                "function_revision",
                "function_id",
            ):
                if column_name in tool_run_columns:
                    batch_op.drop_column(column_name)

    if inspector.has_table("tool_provider_backends"):
        _drop_index_if_exists(
            inspector,
            "tool_provider_backends",
            "ix_tool_provider_backends_status",
        )
        _drop_index_if_exists(
            inspector,
            "tool_provider_backends",
            "ix_tool_provider_backends_capability",
        )
        _drop_index_if_exists(
            inspector,
            "tool_provider_backends",
            "ix_tool_provider_backends_source_id",
        )
        op.drop_table("tool_provider_backends")

    if inspector.has_table("tool_functions"):
        _drop_index_if_exists(
            inspector,
            "tool_functions",
            "ix_tool_functions_status",
        )
        _drop_index_if_exists(
            inspector,
            "tool_functions",
            "ix_tool_functions_runtime_kind",
        )
        _drop_index_if_exists(
            inspector,
            "tool_functions",
            "ix_tool_functions_name",
        )
        _drop_index_if_exists(
            inspector,
            "tool_functions",
            "ix_tool_functions_source_id",
        )
        op.drop_table("tool_functions")

    if inspector.has_table("tool_sources"):
        _drop_index_if_exists(inspector, "tool_sources", "ix_tool_sources_status")
        _drop_index_if_exists(inspector, "tool_sources", "ix_tool_sources_kind")
        op.drop_table("tool_sources")


def _upgrade_tool_runs(inspector: sa.Inspector) -> None:
    if not inspector.has_table("tool_runs"):
        return
    columns = {column["name"] for column in inspector.get_columns("tool_runs")}
    if "function_id" not in columns:
        op.add_column(
            "tool_runs",
            sa.Column("function_id", sa.String(length=100), nullable=True),
        )
    if "function_revision" not in columns:
        op.add_column(
            "tool_runs",
            sa.Column("function_revision", sa.Integer(), nullable=True),
        )
    if "source_id" not in columns:
        op.add_column(
            "tool_runs",
            sa.Column("source_id", sa.String(length=100), nullable=True),
        )
    if "source_revision" not in columns:
        op.add_column(
            "tool_runs",
            sa.Column("source_revision", sa.Integer(), nullable=True),
        )
    if "schema_hash" not in columns:
        op.add_column(
            "tool_runs",
            sa.Column("schema_hash", sa.String(length=128), nullable=True),
        )
    _ensure_index(
        inspector,
        "tool_runs",
        "ix_tool_runs_function_id",
        ["function_id"],
    )
    _ensure_index(
        inspector,
        "tool_runs",
        "ix_tool_runs_source_id",
        ["source_id"],
    )


def _upgrade_tool_functions(inspector: sa.Inspector) -> None:
    if not inspector.has_table("tool_functions"):
        return
    columns = {column["name"] for column in inspector.get_columns("tool_functions")}
    for column_name, column in (
        (
            "access_requirement_sets_payload",
            sa.Column("access_requirement_sets_payload", sa.JSON(), nullable=True),
        ),
        (
            "credential_binding_overrides_payload",
            sa.Column("credential_binding_overrides_payload", sa.JSON(), nullable=True),
        ),
        (
            "required_effect_overrides_payload",
            sa.Column("required_effect_overrides_payload", sa.JSON(), nullable=True),
        ),
        ("metadata_payload", sa.Column("metadata_payload", sa.JSON(), nullable=True)),
        ("last_seen_at", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True)),
        ("stale_since", sa.Column("stale_since", sa.DateTime(timezone=True), nullable=True)),
        (
            "deprecated_at",
            sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
        ),
    ):
        if column_name not in columns:
            op.add_column("tool_functions", column)


def _ensure_index(
    inspector: sa.Inspector,
    table_name: str,
    index_name: str,
    columns: list[str],
    *,
    created: bool = False,
) -> None:
    if created or index_name not in _index_names(inspector, table_name):
        op.create_index(index_name, table_name, columns)


def _drop_index_if_exists(
    inspector: sa.Inspector,
    table_name: str,
    index_name: str,
) -> None:
    if index_name in _index_names(inspector, table_name):
        op.drop_index(index_name, table_name=table_name)


def _index_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {
        str(index["name"])
        for index in inspector.get_indexes(table_name)
        if index.get("name")
    }


def _bool_default(bind: sa.Connection, value: bool) -> sa.TextClause:
    if bind.dialect.name == "sqlite":
        return sa.text("1" if value else "0")
    return sa.text("true" if value else "false")
