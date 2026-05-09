from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from crxzipple.core.db import Base
from crxzipple.modules.settings.application import CreateSettingsResourceInput
from crxzipple.modules.settings.infrastructure.persistence import (
    SettingsActionAuditModel,
    SettingsEffectiveSnapshotModel,
    SettingsEffectiveSnapshotRecord,
    SettingsOverrideModel,
    SettingsOverrideRecord,
    SettingsResourceModel,
    SettingsResourceRecord,
    SettingsResourceVersionModel,
    SettingsResourceVersionRecord,
    SettingsValidationResultModel,
    SettingsValidationResultRecord,
    SqlAlchemySettingsActionAuditRepository,
    SqlAlchemySettingsGovernanceRepository,
    create_sqlalchemy_settings_services,
)


class SettingsPersistenceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        _ = (
            SettingsActionAuditModel,
            SettingsEffectiveSnapshotModel,
            SettingsOverrideModel,
            SettingsResourceModel,
            SettingsResourceVersionModel,
            SettingsValidationResultModel,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
        )
        self.repository = SqlAlchemySettingsGovernanceRepository(self.session_factory)
        self.audit_repository = SqlAlchemySettingsActionAuditRepository(
            self.session_factory,
        )

    def tearDown(self) -> None:
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_governance_repository_records_versions_and_current_snapshot(self) -> None:
        timestamp = datetime(2026, 5, 7, 9, 0, tzinfo=timezone.utc)

        resource = self.repository.create_resource(
            SettingsResourceRecord(
                resource_id="llm.profile.writer",
                resource_kind="llm-profile",
                display_name="Writer profile",
                governance_scope="workspace",
                config_contract={
                    "name": "LegacyLlmProfileImportPayload",
                    "schema_version": "1",
                },
                contract_version="1",
                storage_key="settings://llm-profiles/writer",
                consumer_modules=("llm", "orchestration"),
                resolution_policy={"order": ["published", "environment"]},
                validation_policy={"required": ["provider", "model"]},
                dry_run_policy={"impact": "llm_profile"},
                secret_policy={"mode": "access_ref_only"},
                metadata={"owner": "settings"},
                created_at=timestamp,
            ),
        )
        self.assertEqual(self.repository.get_resource(resource.resource_id), resource)

        draft = self.repository.create_version(
            SettingsResourceVersionRecord(
                version_id="llm.profile.writer.v1",
                resource_id=resource.resource_id,
                resource_kind=resource.resource_kind,
                version_number=1,
                status="draft",
                payload={"provider": "openai", "model": "gpt-5-mini"},
                source_kind="bootstrap",
                source_ref="config/llm_profiles/writer.yaml",
                contract_version="1",
                redaction_policy={"mode": "metadata_only"},
                created_by="importer",
                reason="initial import",
                created_at=timestamp,
            ),
        )
        published = self.repository.create_version(
            SettingsResourceVersionRecord(
                version_id="llm.profile.writer.v2",
                resource_id=resource.resource_id,
                resource_kind=resource.resource_kind,
                version_number=2,
                status="published",
                payload={
                    "provider": "openai",
                    "model": "gpt-5.1",
                    "credential_binding_ref": "access://credential/openai",
                },
                source_kind="settings_action",
                source_ref="settingsact_publish_writer",
                contract_version="1",
                redaction_policy={"mode": "metadata_only"},
                validation_result_id="validation_writer_v2",
                created_by="unit-test",
                reason="publish validated model",
                published_at=timestamp + timedelta(minutes=2),
                created_at=timestamp + timedelta(minutes=1),
            ),
        )

        self.assertEqual(
            self.repository.list_versions(resource.resource_id), (published, draft)
        )
        self.assertEqual(
            self.repository.get_latest_published_version(resource.resource_id),
            published,
        )
        updated_resource = self.repository.get_resource(resource.resource_id)
        self.assertIsNotNone(updated_resource)
        assert updated_resource is not None
        self.assertEqual(updated_resource.latest_version_number, 2)
        self.assertEqual(updated_resource.published_version_id, published.version_id)

        self.repository.record_effective_snapshot(
            SettingsEffectiveSnapshotRecord(
                snapshot_id="snapshot_writer_v1",
                resource_id=resource.resource_id,
                resource_kind=resource.resource_kind,
                scope_key="workspace",
                version_id=draft.version_id,
                version_number=draft.version_number,
                effective_payload=draft.payload,
                resolution_trace=({"source": "draft"},),
                sources=({"kind": "bootstrap", "ref": draft.source_ref},),
                generated_at=timestamp + timedelta(minutes=1),
                created_at=timestamp + timedelta(minutes=1),
            ),
        )
        current_snapshot = self.repository.record_effective_snapshot(
            SettingsEffectiveSnapshotRecord(
                snapshot_id="snapshot_writer_v2",
                resource_id=resource.resource_id,
                resource_kind=resource.resource_kind,
                scope_key="workspace",
                version_id=published.version_id,
                version_number=published.version_number,
                effective_payload=published.payload,
                resolution_trace=({"source": "published"}, {"source": "override"}),
                sources=(
                    {"kind": "settings_resource_version", "id": published.version_id},
                ),
                overrides_applied=({"override_id": "override_writer_timeout"},),
                generated_at=timestamp + timedelta(minutes=3),
                created_at=timestamp + timedelta(minutes=3),
            ),
        )

        latest_snapshot = self.repository.get_latest_effective_snapshot(
            resource.resource_id,
            scope_key="workspace",
        )
        self.assertEqual(latest_snapshot, current_snapshot)
        snapshots = self.repository.list_effective_snapshots(
            resource.resource_id,
            scope_key="workspace",
        )
        self.assertEqual(
            (snapshots[0].snapshot_id, snapshots[0].is_current),
            ("snapshot_writer_v2", True),
        )
        self.assertEqual(
            (snapshots[1].snapshot_id, snapshots[1].is_current),
            ("snapshot_writer_v1", False),
        )

        override = self.repository.create_override(
            SettingsOverrideRecord(
                override_id="override_writer_timeout",
                resource_id=resource.resource_id,
                resource_kind=resource.resource_kind,
                override_kind="environment",
                scope_key="workspace",
                priority=200,
                override_payload={"timeout_seconds": 60},
                source_kind="env",
                source_ref="CRXZIPPLE_LLM_WRITER_TIMEOUT",
                reason="local workspace override",
                actor="unit-test",
                redaction_policy={"mode": "metadata_only"},
                created_at=timestamp,
            ),
        )
        self.assertEqual(
            self.repository.list_overrides(resource_id=resource.resource_id),
            (override,),
        )

        validation = self.repository.record_validation_result(
            SettingsValidationResultRecord(
                validation_id="validation_writer_v2",
                resource_id=resource.resource_id,
                resource_kind=resource.resource_kind,
                version_id=published.version_id,
                validator="settings.llm_profile",
                status="passed",
                valid=True,
                issues=(),
                checked_payload_digest="sha256:writer-v2",
                redaction_policy={"mode": "metadata_only"},
                created_at=timestamp,
            ),
        )
        self.assertEqual(
            self.repository.list_validation_results(version_id=published.version_id),
            (validation,),
        )

    def test_action_audit_records_actor_reason_risk_and_redacted_metadata(self) -> None:
        attempt = self.audit_repository.record_attempt(
            action_id="action_publish_writer",
            action_type="publish",
            target_type="settings_resource",
            target_id="llm.profile.writer",
            resource_kind="llm-profile",
            reason="publish tested profile",
            actor="unit-test",
            risk="elevated",
            confirmation=True,
            risk_acknowledged=True,
            request_metadata={"credential": "access://credential/openai"},
            redaction_policy={"mode": "metadata_only"},
            trace_context={"request_id": "trace-settings-publish"},
        )

        self.assertEqual(attempt.status, "attempted")
        self.assertEqual(attempt.actor, "unit-test")
        self.assertEqual(attempt.reason, "publish tested profile")
        self.assertEqual(attempt.risk, "elevated")
        self.assertEqual(
            attempt.request_metadata,
            {"credential": "access://credential/openai"},
        )

        succeeded = self.audit_repository.mark_succeeded(
            attempt.audit_id,
            result={"version_id": "llm.profile.writer.v2"},
        )

        self.assertEqual(succeeded.status, "succeeded")
        self.assertEqual(succeeded.result, {"version_id": "llm.profile.writer.v2"})
        self.assertEqual(self.audit_repository.list_recent(), (succeeded,))

        failed = self.audit_repository.record_attempt(
            action_type="rollback",
            target_type="settings_resource",
            target_id="llm.profile.writer",
            reason="exercise failure path",
        )
        failed = self.audit_repository.mark_failed(
            failed.audit_id,
            error={"code": "validation_failed"},
        )

        self.assertEqual(failed.status, "failed")
        self.assertEqual(failed.error, {"code": "validation_failed"})

    def test_schema_has_settings_tables_without_raw_secret_columns(self) -> None:
        inspector = inspect(self.engine)
        expected_tables = {
            "settings_action_audits",
            "settings_effective_snapshots",
            "settings_overrides",
            "settings_resource_versions",
            "settings_resources",
            "settings_validation_results",
        }
        self.assertTrue(expected_tables.issubset(set(inspector.get_table_names())))

        forbidden_columns = {"secret", "secret_value", "raw_secret"}
        for table_name in expected_tables:
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            self.assertFalse(columns & forbidden_columns, table_name)

        resource_columns = {
            column["name"] for column in inspector.get_columns("settings_resources")
        }
        self.assertIn("secret_policy", resource_columns)
        self.assertIn("config_contract", resource_columns)
        self.assertIn("storage_key", resource_columns)

        action_columns = {
            column["name"] for column in inspector.get_columns("settings_action_audits")
        }
        self.assertIn("actor", action_columns)
        self.assertIn("risk", action_columns)
        self.assertIn("request_metadata", action_columns)
        self.assertIn("trace_context", action_columns)

    def test_application_services_persist_effective_settings(self) -> None:
        services = create_sqlalchemy_settings_services(self.session_factory)
        services.actions.create_resource(
            CreateSettingsResourceInput(
                resource_id="llm:writer",
                resource_kind="llm-profiles",
                owner_module="llm",
                payload={
                    "profile_id": "writer",
                    "provider": "openai",
                    "api_family": "responses",
                    "model_name": "gpt-5.4",
                },
                actor="unit-test",
                reason="create persisted llm profile",
                publish=True,
            ),
        )

        reopened = create_sqlalchemy_settings_services(self.session_factory)
        effective = reopened.queries.get_effective("llm:writer")

        self.assertEqual(effective.effective_value["model_name"], "gpt-5.4")
        self.assertEqual(
            tuple(
                version.id for version in reopened.queries.list_versions("llm:writer")
            ),
            ("llm:writer:v1",),
        )


if __name__ == "__main__":
    unittest.main()
