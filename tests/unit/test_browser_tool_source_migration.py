from __future__ import annotations

from dataclasses import replace
import importlib.util
from pathlib import Path
import unittest

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Column, JSON, MetaData, String, Table, inspect, select

from crxzipple.core.config import load_settings
from crxzipple.core.db import build_engine
from tests.unit.support import SqliteTestHarness


class BrowserToolSourceMigrationTestCase(unittest.TestCase):
    def test_migration_is_chained_after_operations_observation_store(self) -> None:
        migration = _load_migration_0061()

        self.assertEqual(migration.down_revision, "0060_operations_observation_store")

    def test_manifest_retirement_migration_is_chained_after_catalog_cleanup(self) -> None:
        migration = _load_migration_0062()

        self.assertEqual(
            migration.down_revision,
            "0061_cleanup_legacy_browser_tool_sources",
        )

    def test_migration_removes_legacy_browser_catalog_and_stale_projections(self) -> None:
        harness = SqliteTestHarness()
        settings = replace(load_settings(), database_url=harness.database_url)
        engine = build_engine(settings)
        migration = _load_migration_0061()
        try:
            with engine.begin() as connection:
                tables = _create_catalog_cleanup_fixture(connection)
                context = MigrationContext.configure(connection)
                migration.op = Operations(context)

                migration.upgrade()
                migration.upgrade()

                self.assertEqual(
                    _values(connection, tables["tool_sources"], "source_id"),
                    {"configured.browser", "configured.mcp.sample"},
                )
                self.assertEqual(
                    _values(connection, tables["tool_functions"], "function_id"),
                    {"browser.snapshot", "mcp.sample.echo"},
                )
                self.assertEqual(
                    _values(
                        connection,
                        tables["tool_source_discovery_runs"],
                        "discovery_run_id",
                    ),
                    {"discovery-new", "discovery-sample"},
                )
                self.assertEqual(
                    _values(connection, tables["tool_provider_backends"], "backend_id"),
                    {"backend-new", "backend-sample"},
                )
                self.assertEqual(
                    _values(connection, tables["operations_projections"], "query_key"),
                    {"browser-clean", "tool-clean"},
                )

            inspector = inspect(engine)
            self.assertIn("tool_sources", inspector.get_table_names())
        finally:
            engine.dispose()
            harness.close()

    def test_manifest_retirement_migration_removes_recreated_browser_package(
        self,
    ) -> None:
        harness = SqliteTestHarness()
        settings = replace(load_settings(), database_url=harness.database_url)
        engine = build_engine(settings)
        migration = _load_migration_0062()
        try:
            with engine.begin() as connection:
                tables = _create_manifest_retirement_fixture(connection)
                context = MigrationContext.configure(connection)
                migration.op = Operations(context)

                migration.upgrade()
                migration.upgrade()

                self.assertEqual(
                    _values(connection, tables["tool_sources"], "source_id"),
                    {"configured.browser", "configured.mcp.sample"},
                )
                self.assertEqual(
                    _values(connection, tables["tool_functions"], "function_id"),
                    {"browser.snapshot", "mcp.sample.echo"},
                )
                self.assertEqual(
                    _values(
                        connection,
                        tables["tool_source_discovery_runs"],
                        "discovery_run_id",
                    ),
                    {"discovery-new", "discovery-sample"},
                )
                self.assertEqual(
                    _values(connection, tables["tool_provider_backends"], "backend_id"),
                    {"backend-new", "backend-sample"},
                )
                self.assertEqual(
                    _values(connection, tables["operations_projections"], "query_key"),
                    {"browser-clean", "tool-clean"},
                )
        finally:
            engine.dispose()
            harness.close()


def _create_catalog_cleanup_fixture(connection) -> dict[str, Table]:  # noqa: ANN001
    metadata = MetaData()
    tool_sources = Table(
        "tool_sources",
        metadata,
        Column("source_id", String(100), primary_key=True),
    )
    tool_functions = Table(
        "tool_functions",
        metadata,
        Column("function_id", String(100), primary_key=True),
        Column("source_id", String(100), nullable=False),
    )
    discovery_runs = Table(
        "tool_source_discovery_runs",
        metadata,
        Column("discovery_run_id", String(100), primary_key=True),
        Column("source_id", String(100), nullable=False),
    )
    provider_backends = Table(
        "tool_provider_backends",
        metadata,
        Column("backend_id", String(100), primary_key=True),
        Column("source_id", String(100), nullable=False),
    )
    projections = Table(
        "operations_projections",
        metadata,
        Column("module", String(80), primary_key=True),
        Column("kind", String(80), primary_key=True),
        Column("query_key", String(160), primary_key=True),
        Column("payload", JSON(), nullable=False),
    )
    metadata.create_all(connection)
    connection.execute(
        tool_sources.insert(),
        [
            {"source_id": "configured.mcp.browser_user"},
            {"source_id": "configured.mcp.browser_crxzipple"},
            {"source_id": "bundled.local_package.browser"},
            {"source_id": "configured.browser"},
            {"source_id": "configured.mcp.sample"},
        ],
    )
    connection.execute(
        tool_functions.insert(),
        [
            {
                "function_id": "mcp.browser_user.take_snapshot",
                "source_id": "configured.mcp.browser_user",
            },
            {
                "function_id": "browser_snapshot",
                "source_id": "bundled.local_package.browser",
            },
            {
                "function_id": "browser.snapshot",
                "source_id": "configured.browser",
            },
            {
                "function_id": "mcp.sample.echo",
                "source_id": "configured.mcp.sample",
            },
        ],
    )
    connection.execute(
        discovery_runs.insert(),
        [
            {
                "discovery_run_id": "discovery-old-mcp",
                "source_id": "configured.mcp.browser_user",
            },
            {
                "discovery_run_id": "discovery-old-package",
                "source_id": "bundled.local_package.browser",
            },
            {
                "discovery_run_id": "discovery-new",
                "source_id": "configured.browser",
            },
            {
                "discovery_run_id": "discovery-sample",
                "source_id": "configured.mcp.sample",
            },
        ],
    )
    connection.execute(
        provider_backends.insert(),
        [
            {
                "backend_id": "backend-old-mcp",
                "source_id": "configured.mcp.browser_user",
            },
            {
                "backend_id": "backend-old-package",
                "source_id": "bundled.local_package.browser",
            },
            {
                "backend_id": "backend-new",
                "source_id": "configured.browser",
            },
            {
                "backend_id": "backend-sample",
                "source_id": "configured.mcp.sample",
            },
        ],
    )
    connection.execute(
        projections.insert(),
        [
            {
                "module": "tool",
                "kind": "page",
                "query_key": "tool-old",
                "payload": {"source_id": "configured.mcp.browser_user"},
            },
            {
                "module": "daemon",
                "kind": "page",
                "query_key": "daemon-old",
                "payload": {"service_key": "mcp:browser:user"},
            },
            {
                "module": "browser",
                "kind": "page",
                "query_key": "browser-clean",
                "payload": {"service_key": "host:browser:user"},
            },
            {
                "module": "tool",
                "kind": "page",
                "query_key": "tool-clean",
                "payload": {"source_id": "configured.browser"},
            },
        ],
    )
    return {
        "tool_sources": tool_sources,
        "tool_functions": tool_functions,
        "tool_source_discovery_runs": discovery_runs,
        "tool_provider_backends": provider_backends,
        "operations_projections": projections,
    }


def _create_manifest_retirement_fixture(connection) -> dict[str, Table]:  # noqa: ANN001
    metadata = MetaData()
    tool_sources = Table(
        "tool_sources",
        metadata,
        Column("source_id", String(100), primary_key=True),
    )
    tool_functions = Table(
        "tool_functions",
        metadata,
        Column("function_id", String(100), primary_key=True),
        Column("source_id", String(100), nullable=False),
    )
    discovery_runs = Table(
        "tool_source_discovery_runs",
        metadata,
        Column("discovery_run_id", String(100), primary_key=True),
        Column("source_id", String(100), nullable=False),
    )
    provider_backends = Table(
        "tool_provider_backends",
        metadata,
        Column("backend_id", String(100), primary_key=True),
        Column("source_id", String(100), nullable=False),
    )
    projections = Table(
        "operations_projections",
        metadata,
        Column("module", String(80), primary_key=True),
        Column("kind", String(80), primary_key=True),
        Column("query_key", String(160), primary_key=True),
        Column("payload", JSON(), nullable=False),
    )
    metadata.create_all(connection)
    connection.execute(
        tool_sources.insert(),
        [
            {"source_id": "bundled.local_package.browser"},
            {"source_id": "configured.browser"},
            {"source_id": "configured.mcp.sample"},
        ],
    )
    connection.execute(
        tool_functions.insert(),
        [
            {
                "function_id": "browser_profile",
                "source_id": "bundled.local_package.browser",
            },
            {
                "function_id": "browser_action",
                "source_id": "bundled.local_package.browser",
            },
            {
                "function_id": "browser.snapshot",
                "source_id": "configured.browser",
            },
            {
                "function_id": "mcp.sample.echo",
                "source_id": "configured.mcp.sample",
            },
        ],
    )
    connection.execute(
        discovery_runs.insert(),
        [
            {
                "discovery_run_id": "discovery-old-package",
                "source_id": "bundled.local_package.browser",
            },
            {
                "discovery_run_id": "discovery-new",
                "source_id": "configured.browser",
            },
            {
                "discovery_run_id": "discovery-sample",
                "source_id": "configured.mcp.sample",
            },
        ],
    )
    connection.execute(
        provider_backends.insert(),
        [
            {
                "backend_id": "backend-old-package",
                "source_id": "bundled.local_package.browser",
            },
            {
                "backend_id": "backend-new",
                "source_id": "configured.browser",
            },
            {
                "backend_id": "backend-sample",
                "source_id": "configured.mcp.sample",
            },
        ],
    )
    connection.execute(
        projections.insert(),
        [
            {
                "module": "tool",
                "kind": "page",
                "query_key": "tool-old",
                "payload": {"source_id": "bundled.local_package.browser"},
            },
            {
                "module": "tool",
                "kind": "browser_profile",
                "query_key": "tool-old-detail",
                "payload": {"function_id": "browser_profile"},
            },
            {
                "module": "browser",
                "kind": "page",
                "query_key": "browser-clean",
                "payload": {"service_key": "host:browser:user"},
            },
            {
                "module": "tool",
                "kind": "page",
                "query_key": "tool-clean",
                "payload": {"source_id": "configured.browser"},
            },
        ],
    )
    return {
        "tool_sources": tool_sources,
        "tool_functions": tool_functions,
        "tool_source_discovery_runs": discovery_runs,
        "tool_provider_backends": provider_backends,
        "operations_projections": projections,
    }


def _values(connection, table: Table, column_name: str) -> set[str]:  # noqa: ANN001
    return set(connection.execute(select(table.c[column_name])).scalars())


def _load_migration_0061():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "0061_cleanup_legacy_browser_tool_sources.py"
    )
    spec = importlib.util.spec_from_file_location(
        "migration_0061_cleanup_legacy_browser_tool_sources",
        migration_path,
    )
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def _load_migration_0062():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "0062_drop_retired_browser_local_package_manifest.py"
    )
    spec = importlib.util.spec_from_file_location(
        "migration_0062_drop_retired_browser_local_package_manifest",
        migration_path,
    )
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


if __name__ == "__main__":
    unittest.main()
