from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import importlib
from pathlib import Path
import tempfile
import unittest

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect

from crxzipple.core.config import load_settings
from crxzipple.core.db import Base, build_engine, build_session_factory
from crxzipple.modules.skills.domain import (
    SkillEnablementPolicy,
    SkillEnablementTargetKind,
    SkillInstallation,
    SkillInstallationStatus,
    SkillInstallScope,
    SkillPackageIndex,
    SkillPackageStatus,
    SkillReadinessSnapshot,
    SkillReadinessStatus,
    SkillRequirements,
    SkillRuntimeVisibility,
    SkillSource,
    SkillSourceStatus,
    SkillSourceSyncStatus,
    SkillSourceType,
)
from crxzipple.modules.skills.infrastructure.persistence import (
    SkillEnablementPolicyModel,
    SkillInstallationModel,
    SkillPackageIndexModel,
    SkillReadinessSnapshotModel,
    SkillSourceModel,
    SqlAlchemySkillOwnerCatalogRepository,
)
from crxzipple.modules.skills.application import SkillManager
from crxzipple.modules.skills.infrastructure.filesystem import FilesystemSkillRepository
from tests.unit.skill_test_support import write_skill_package
from tests.unit.support import SqliteTestHarness


class SkillOwnerCatalogPersistenceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = SqliteTestHarness()
        self.settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
        )
        self.harness.initialize_schema(settings=self.settings)
        self.engine = build_engine(self.settings)
        Base.metadata.create_all(
            self.engine,
            tables=[
                SkillSourceModel.__table__,
                SkillPackageIndexModel.__table__,
                SkillEnablementPolicyModel.__table__,
                SkillReadinessSnapshotModel.__table__,
                SkillInstallationModel.__table__,
            ],
        )
        self.session_factory = build_session_factory(self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.harness.close()

    def test_models_define_owner_catalog_tables_and_constraints(self) -> None:
        inspector = inspect(self.engine)
        self.assertIn("skill_sources", inspector.get_table_names())
        self.assertIn("skill_packages", inspector.get_table_names())
        self.assertIn("skill_enablement_policies", inspector.get_table_names())
        self.assertIn("skill_readiness", inspector.get_table_names())
        self.assertIn("skill_installations", inspector.get_table_names())

        package_uniques = {
            constraint["name"]
            for constraint in inspector.get_unique_constraints("skill_packages")
        }
        self.assertIn("uq_skill_packages_source_name", package_uniques)
        self.assertIn("uq_skill_packages_source_skill", package_uniques)

    def test_repository_round_trips_source_package_policy_and_readiness(self) -> None:
        now = datetime(2026, 5, 20, 9, 0, tzinfo=timezone.utc)
        repository = SqlAlchemySkillOwnerCatalogRepository(self.session_factory)

        repository.upsert_source(
            SkillSource(
                source_id="source.workspace.main",
                source_type=SkillSourceType.WORKSPACE,
                root_uri="file:///workspace/.crxzipple/skills",
                status=SkillSourceStatus.ACTIVE,
                sync_status=SkillSourceSyncStatus.SUCCEEDED,
                scope="workspace",
                priority=10,
                enabled=True,
                readonly=False,
                metadata={"workspace": "/workspace"},
                last_synced_at=now,
                created_at=now,
                updated_at=now,
            ),
        )
        repository.upsert_package(
            SkillPackageIndex(
                package_id="pkg.workspace.python",
                skill_id="python-dev",
                name="python-dev",
                source_id="source.workspace.main",
                root_uri="file:///workspace/.crxzipple/skills/python-dev",
                manifest_uri="file:///workspace/.crxzipple/skills/python-dev/SKILL.md",
                instructions_uri="file:///workspace/.crxzipple/skills/python-dev/SKILL.md",
                version="1.0.0",
                fingerprint="sha256:skill-v1",
                requirements=SkillRequirements(
                    required_tools=("workspace_read",),
                    suggested_tools=("command",),
                    surfaces=("workbench",),
                ),
                capability_requirements={
                    "tools": ["workspace_read"],
                    "access": ["repo"],
                },
                metadata={"tags": ["coding"]},
                indexed_at=now,
                updated_at=now,
            ),
        )
        repository.upsert_enablement_policy(
            SkillEnablementPolicy(
                policy_id="policy.python-dev",
                target_kind=SkillEnablementTargetKind.SKILL,
                target_id="python-dev",
                enabled=True,
                trusted=True,
                runtime_visibility=SkillRuntimeVisibility.VISIBLE,
                priority=20,
                reason="seeded for workspace",
                created_at=now,
                updated_at=now,
            ),
        )
        repository.upsert_readiness(
            SkillReadinessSnapshot(
                skill_id="python-dev",
                source_id="source.workspace.main",
                status=SkillReadinessStatus.READY,
                checks=({"kind": "tool", "id": "workspace_read", "ok": True},),
                reason=None,
                updated_at=now,
            ),
        )
        repository.record_installation(
            SkillInstallation(
                installation_id="skill-installation.python-dev.create",
                action="package_create",
                status=SkillInstallationStatus.SUCCEEDED,
                source_id="source.workspace.main",
                skill_id="python-dev",
                skill_name="python-dev",
                source_uri=None,
                target_uri="file:///workspace/.crxzipple/skills/python-dev",
                actor_id="tester",
                reason="round-trip test",
                message="created",
                metadata={"workspace": "/workspace"},
                created_at=now,
            ),
        )

        source = repository.get_source("source.workspace.main")
        assert source is not None
        self.assertEqual(source.source_type, SkillSourceType.WORKSPACE)
        self.assertEqual(source.sync_status, SkillSourceSyncStatus.SUCCEEDED)

        package = repository.get_package_by_skill(
            source_id="source.workspace.main",
            skill_id="python-dev",
        )
        assert package is not None
        self.assertEqual(package.fingerprint, "sha256:skill-v1")
        self.assertEqual(package.requirements.required_tools, ("workspace_read",))
        self.assertEqual(package.capability_requirements["access"], ["repo"])

        policies = repository.list_enablement_policies(target_kind="skill")
        self.assertEqual(len(policies), 1)
        self.assertTrue(policies[0].trusted)

        readiness = repository.get_readiness("python-dev")
        assert readiness is not None
        self.assertEqual(readiness.status, SkillReadinessStatus.READY)
        self.assertEqual(readiness.checks[0]["id"], "workspace_read")

        installations = repository.list_installations(skill_id="python-dev")
        self.assertEqual(len(installations), 1)
        self.assertEqual(installations[0].status, SkillInstallationStatus.SUCCEEDED)
        self.assertEqual(installations[0].metadata["workspace"], "/workspace")

    def test_manager_uninstall_marks_owner_package_removed_and_readiness_invalid(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            global_root = root / "global"
            system_root = root / "system"
            write_skill_package(
                global_root / "release-ops",
                name="release-ops",
                description="Prepare and validate releases.",
                instructions="# Release Ops\n\nFollow the release checklist.\n",
            )
            repository = SqlAlchemySkillOwnerCatalogRepository(self.session_factory)
            events: list[tuple[str, dict[str, object]]] = []
            manager = SkillManager(
                repository=FilesystemSkillRepository(
                    global_root=global_root,
                    system_root=system_root,
                ),
                owner_catalog_repository=repository,
                event_emitter=lambda name, payload: events.append((name, payload)),
            )

            manager.sync(workspace_dir=None, source_id="global", surface="")
            manager.readiness(workspace_dir=None, skill_name="release-ops", surface="")
            indexed = repository.get_package_by_skill(
                source_id="global",
                skill_id="release-ops",
            )
            assert indexed is not None
            self.assertEqual(indexed.status, SkillPackageStatus.ACTIVE)

            manager.uninstall(
                workspace_dir=None,
                skill_name="release-ops",
                surface="",
            )

            removed = repository.get_package_by_skill(
                source_id="global",
                skill_id="release-ops",
            )
            readiness = repository.get_readiness("release-ops")
            installations = repository.list_installations(skill_id="release-ops")
            assert removed is not None
            assert readiness is not None
            self.assertEqual(removed.status, SkillPackageStatus.REMOVED)
            self.assertEqual(readiness.status, SkillReadinessStatus.INVALID)
            self.assertEqual(readiness.reason, "removed")
            self.assertEqual(installations[0].action, "package_delete")
            self.assertFalse((global_root / "release-ops").exists())
            readiness_events = [
                payload
                for name, payload in events
                if name == "skills.readiness.changed"
                and payload.get("skill") == "release-ops"
            ]
            self.assertEqual(readiness_events[-1]["status"], "invalid")
            self.assertEqual(readiness_events[-1]["reason"], "removed")

    def test_legacy_filesystem_skill_installs_as_current_frontmatter_package(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            global_root = root / "global"
            system_root = root / "system"
            source_root = root / "legacy-source"
            write_skill_package(
                source_root / "release-ops",
                name="release-ops",
                description="Prepare and validate releases.",
                instructions="# Release Ops\n\nFollow the release checklist.\n",
                required_tools=("git_diff",),
                frontmatter=False,
            )
            repository = SqlAlchemySkillOwnerCatalogRepository(self.session_factory)
            manager = SkillManager(
                repository=FilesystemSkillRepository(
                    global_root=global_root,
                    system_root=system_root,
                ),
                owner_catalog_repository=repository,
            )

            empty_sync_result = manager.sync(
                workspace_dir=None,
                source_id="global",
                surface="",
            )
            manager.install(
                source_dir=str(source_root / "release-ops"),
                scope=SkillInstallScope.GLOBAL,
                workspace_dir=None,
            )
            sync_result = manager.sync(
                workspace_dir=None,
                source_id="global",
                surface="",
            )
            prompt = manager.build_prompt_catalog(workspace_dir=None, surface="")

            installed_root = global_root / "release-ops"
            self.assertEqual(empty_sync_result.synced_count, 0)
            self.assertEqual(sync_result.synced_count, 1)
            self.assertTrue((installed_root / "SKILL.md").is_file())
            self.assertFalse((installed_root / "skill.yaml").exists())
            indexed = repository.get_package_by_skill(
                source_id="global",
                skill_id="release-ops",
            )
            assert indexed is not None
            self.assertEqual(indexed.requirements.required_tools, ("git_diff",))
            self.assertIsNotNone(prompt)
            assert prompt is not None
            self.assertIn("release-ops", prompt.content)
            self.assertIn("requires tools: git_diff", prompt.content)

    def test_migration_revision_is_chained_after_tool_discovery_runs(self) -> None:
        migration = _load_migration_0053()
        self.assertEqual(migration.down_revision, "0052_tool_source_discovery_runs")

    def test_installation_audit_migration_is_chained_after_skill_owner_catalog(
        self,
    ) -> None:
        migration = _load_migration_0054()
        self.assertEqual(migration.down_revision, "0053_skill_owner_catalog")

    def test_migration_upgrade_creates_owner_catalog_tables_idempotently(self) -> None:
        harness = SqliteTestHarness()
        settings = replace(load_settings(), database_url=harness.database_url)
        engine = build_engine(settings)
        migration = _load_migration_0053()
        try:
            with engine.begin() as connection:
                context = MigrationContext.configure(connection)
                migration.op = Operations(context)
                migration.upgrade()
                migration.upgrade()

            inspector = inspect(engine)
            self.assertIn("skill_sources", inspector.get_table_names())
            self.assertIn("skill_packages", inspector.get_table_names())
            self.assertIn("skill_enablement_policies", inspector.get_table_names())
            self.assertIn("skill_readiness", inspector.get_table_names())
            package_indexes = {
                index["name"] for index in inspector.get_indexes("skill_packages")
            }
            self.assertIn("ix_skill_packages_source_id", package_indexes)
            self.assertIn("ix_skill_packages_status", package_indexes)
        finally:
            engine.dispose()
            harness.close()

    def test_migration_upgrade_creates_installation_audit_table_idempotently(
        self,
    ) -> None:
        harness = SqliteTestHarness()
        settings = replace(load_settings(), database_url=harness.database_url)
        engine = build_engine(settings)
        migration = _load_migration_0054()
        try:
            with engine.begin() as connection:
                context = MigrationContext.configure(connection)
                migration.op = Operations(context)
                migration.upgrade()
                migration.upgrade()

            inspector = inspect(engine)
            self.assertIn("skill_installations", inspector.get_table_names())
            indexes = {
                index["name"]
                for index in inspector.get_indexes("skill_installations")
            }
            self.assertIn("ix_skill_installations_action", indexes)
            self.assertIn("ix_skill_installations_skill_id", indexes)
        finally:
            engine.dispose()
            harness.close()


def _load_migration_0053():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "0053_skill_owner_catalog.py"
    )
    spec = importlib.util.spec_from_file_location(
        "migration_0053_skill_owner_catalog",
        migration_path,
    )
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def _load_migration_0054():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "0054_skill_installation_audit.py"
    )
    spec = importlib.util.spec_from_file_location(
        "migration_0054_skill_installation_audit",
        migration_path,
    )
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration
