"""delete configured browser tool source

Revision ID: 0071_delete_configured_browser_tool_source
Revises: 0070_context_snapshot_run_history
Create Date: 2026-06-10 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0071_delete_configured_browser_tool_source"
down_revision = "0070_context_snapshot_run_history"
branch_labels = None
depends_on = None


_OLD_BROWSER_SOURCE_ID = "configured.browser"
_OLD_BROWSER_NODE_PREFIX = "tools.bundle.configured.browser"
_OLD_BROWSER_MARKERS = (
    _OLD_BROWSER_SOURCE_ID,
    _OLD_BROWSER_NODE_PREFIX,
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    _delete_rows_by_source_id(inspector, "tool_provider_backends")
    _delete_rows_by_source_id(inspector, "tool_source_discovery_runs")
    _delete_rows_by_source_id(inspector, "tool_functions")
    _delete_rows_by_source_id(inspector, "tool_sources")
    _delete_stale_context_nodes(inspector)
    _delete_stale_operations_projections(inspector)


def downgrade() -> None:
    # Recreating this source would reintroduce the retired Browser special path.
    return


def _delete_rows_by_source_id(inspector: sa.Inspector, table_name: str) -> None:
    if not inspector.has_table(table_name):
        return
    table = sa.table(table_name, sa.column("source_id", sa.String()))
    op.execute(sa.delete(table).where(table.c.source_id == _OLD_BROWSER_SOURCE_ID))


def _delete_stale_context_nodes(inspector: sa.Inspector) -> None:
    if not inspector.has_table("context_node_states"):
        return
    table = sa.table(
        "context_node_states",
        sa.column("node_id", sa.String()),
        sa.column("owner_ref", sa.JSON()),
        sa.column("metadata", sa.JSON()),
    )
    owner_ref_text = sa.cast(table.c.owner_ref, sa.Text())
    metadata_text = sa.cast(table.c.metadata, sa.Text())
    op.execute(
        sa.delete(table).where(
            sa.or_(
                table.c.node_id == _OLD_BROWSER_NODE_PREFIX,
                table.c.node_id.like(f"{_OLD_BROWSER_NODE_PREFIX}.%"),
                owner_ref_text.like(f"%{_OLD_BROWSER_SOURCE_ID}%"),
                metadata_text.like(f"%{_OLD_BROWSER_SOURCE_ID}%"),
            ),
        ),
    )


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
        *(payload_text.like(f"%{marker}%") for marker in _OLD_BROWSER_MARKERS),
    )
    op.execute(
        sa.delete(table).where(
            table.c.module.in_(("tool", "browser", "daemon", "context_workspace")),
            marker_predicate,
        ),
    )
