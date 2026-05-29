"""drop retired browser local package manifest records

Revision ID: 0062_drop_retired_browser_local_package_manifest
Revises: 0061_cleanup_legacy_browser_tool_sources
Create Date: 2026-05-26 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0062_drop_retired_browser_local_package_manifest"
down_revision = "0061_cleanup_legacy_browser_tool_sources"
branch_labels = None
depends_on = None


_LEGACY_BROWSER_PACKAGE_SOURCE_ID = "bundled.local_package.browser"
_LEGACY_BROWSER_PACKAGE_FUNCTION_IDS = (
    "browser_profile",
    "browser_control",
    "browser_snapshot",
    "browser_action",
    "browser_pdf",
    "browser_download",
    "browser_cookie",
    "browser_storage",
    "browser_console_events",
    "browser_network_inspect",
    "browser_cdp_raw",
    "browser_script",
)
_LEGACY_PROJECTION_MARKERS = (
    _LEGACY_BROWSER_PACKAGE_SOURCE_ID,
    "browser_profile",
    "browser_control",
    "browser_snapshot",
    "browser_action",
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    _delete_legacy_tool_provider_backends(inspector)
    _delete_legacy_tool_discovery_runs(inspector)
    _delete_legacy_tool_functions(inspector)
    _delete_legacy_tool_source(inspector)
    _delete_stale_operations_projections(inspector)


def downgrade() -> None:
    # The manifest-backed browser package has been replaced by configured.browser.
    return


def _delete_legacy_tool_provider_backends(inspector: sa.Inspector) -> None:
    if not inspector.has_table("tool_provider_backends"):
        return
    table = sa.table(
        "tool_provider_backends",
        sa.column("source_id", sa.String()),
    )
    op.execute(
        sa.delete(table).where(table.c.source_id == _LEGACY_BROWSER_PACKAGE_SOURCE_ID),
    )


def _delete_legacy_tool_discovery_runs(inspector: sa.Inspector) -> None:
    if not inspector.has_table("tool_source_discovery_runs"):
        return
    table = sa.table(
        "tool_source_discovery_runs",
        sa.column("source_id", sa.String()),
    )
    op.execute(
        sa.delete(table).where(table.c.source_id == _LEGACY_BROWSER_PACKAGE_SOURCE_ID),
    )


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
                table.c.source_id == _LEGACY_BROWSER_PACKAGE_SOURCE_ID,
                table.c.function_id.in_(_LEGACY_BROWSER_PACKAGE_FUNCTION_IDS),
            ),
        ),
    )


def _delete_legacy_tool_source(inspector: sa.Inspector) -> None:
    if not inspector.has_table("tool_sources"):
        return
    table = sa.table(
        "tool_sources",
        sa.column("source_id", sa.String()),
    )
    op.execute(
        sa.delete(table).where(table.c.source_id == _LEGACY_BROWSER_PACKAGE_SOURCE_ID),
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
        *(payload_text.like(f"%{marker}%") for marker in _LEGACY_PROJECTION_MARKERS),
    )
    op.execute(
        sa.delete(table).where(
            table.c.module.in_(("tool", "browser", "daemon")),
            marker_predicate,
        ),
    )
