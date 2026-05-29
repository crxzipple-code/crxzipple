"""cleanup legacy browser tool sources

Revision ID: 0061_cleanup_legacy_browser_tool_sources
Revises: 0060_operations_observation_store
Create Date: 2026-05-25 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0061_cleanup_legacy_browser_tool_sources"
down_revision = "0060_operations_observation_store"
branch_labels = None
depends_on = None


_LEGACY_BROWSER_PACKAGE_SOURCE_ID = "bundled.local_package.browser"
_LEGACY_BROWSER_MCP_SOURCE_PATTERN = "configured.mcp.browser_%"
_LEGACY_BROWSER_MCP_FUNCTION_PATTERN = "mcp.browser_%"
_LEGACY_BROWSER_PACKAGE_FUNCTION_IDS = (
    "browser_profile",
    "browser_control",
    "browser_snapshot",
    "browser_action",
)
_LEGACY_PROJECTION_MARKERS = (
    "configured.mcp.browser_",
    "mcp:browser:",
    "mcp.browser_",
    _LEGACY_BROWSER_PACKAGE_SOURCE_ID,
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    _delete_legacy_tool_provider_backends(inspector)
    _delete_legacy_tool_discovery_runs(inspector)
    _delete_legacy_tool_functions(inspector)
    _delete_legacy_tool_sources(inspector)
    _delete_stale_operations_projections(inspector)


def downgrade() -> None:
    # This migration removes retired catalog/projection records. Recreating them
    # would reintroduce a superseded Browser MCP/source model.
    return


def _delete_legacy_tool_provider_backends(inspector: sa.Inspector) -> None:
    if not inspector.has_table("tool_provider_backends"):
        return
    table = sa.table(
        "tool_provider_backends",
        sa.column("source_id", sa.String()),
    )
    op.execute(sa.delete(table).where(_legacy_source_id_predicate(table.c.source_id)))


def _delete_legacy_tool_discovery_runs(inspector: sa.Inspector) -> None:
    if not inspector.has_table("tool_source_discovery_runs"):
        return
    table = sa.table(
        "tool_source_discovery_runs",
        sa.column("source_id", sa.String()),
    )
    op.execute(sa.delete(table).where(_legacy_source_id_predicate(table.c.source_id)))


def _delete_legacy_tool_functions(inspector: sa.Inspector) -> None:
    if not inspector.has_table("tool_functions"):
        return
    table = sa.table(
        "tool_functions",
        sa.column("function_id", sa.String()),
        sa.column("source_id", sa.String()),
    )
    op.execute(
        sa.delete(table).where(
            sa.or_(
                _legacy_source_id_predicate(table.c.source_id),
                table.c.function_id.like(_LEGACY_BROWSER_MCP_FUNCTION_PATTERN),
                table.c.function_id.in_(_LEGACY_BROWSER_PACKAGE_FUNCTION_IDS),
            ),
        ),
    )


def _delete_legacy_tool_sources(inspector: sa.Inspector) -> None:
    if not inspector.has_table("tool_sources"):
        return
    table = sa.table(
        "tool_sources",
        sa.column("source_id", sa.String()),
    )
    op.execute(sa.delete(table).where(_legacy_source_id_predicate(table.c.source_id)))


def _delete_stale_operations_projections(inspector: sa.Inspector) -> None:
    if not inspector.has_table("operations_projections"):
        return
    table = sa.table(
        "operations_projections",
        sa.column("module", sa.String()),
        sa.column("payload", sa.JSON()),
    )
    payload_text = sa.cast(table.c.payload, sa.Text())
    marker_predicate = sa.or_(
        *(payload_text.like(f"%{marker}%") for marker in _LEGACY_PROJECTION_MARKERS),
    )
    op.execute(
        sa.delete(table).where(
            table.c.module.in_(("tool", "browser", "daemon")),
            marker_predicate,
        ),
    )


def _legacy_source_id_predicate(column: sa.ColumnElement[str]) -> sa.ColumnElement[bool]:
    return sa.or_(
        column == _LEGACY_BROWSER_PACKAGE_SOURCE_ID,
        column.like(_LEGACY_BROWSER_MCP_SOURCE_PATTERN),
    )
