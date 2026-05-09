from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from crxzipple.core.db import Base
from crxzipple.modules.access.application.repositories import (
    AccessAssetRecord,
    AccessConnectionProfileRecord,
    AccessConsumerBindingRecord,
    AccessCredentialBindingRecord,
    AccessReadinessSnapshotRecord,
    AccessSecretBindingRecord,
    AccessSetupSessionRecord,
)
from crxzipple.modules.access.infrastructure.persistence import (
    AccessActionAuditModel,
    AccessAssetModel,
    AccessConnectionProfileModel,
    AccessConsumerBindingModel,
    AccessCredentialBindingModel,
    AccessReadinessSnapshotModel,
    AccessSecretBindingModel,
    AccessSetupSessionModel,
    SqlAlchemyAccessActionAuditRepository,
    SqlAlchemyAccessGovernanceRepository,
)


class AccessPersistenceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        _ = (
            AccessActionAuditModel,
            AccessAssetModel,
            AccessConnectionProfileModel,
            AccessConsumerBindingModel,
            AccessCredentialBindingModel,
            AccessReadinessSnapshotModel,
            AccessSecretBindingModel,
            AccessSetupSessionModel,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
        )
        self.repository = SqlAlchemyAccessGovernanceRepository(self.session_factory)
        self.audit_repository = SqlAlchemyAccessActionAuditRepository(
            self.session_factory,
        )

    def tearDown(self) -> None:
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_access_governance_repository_records_core_tables_without_secret_values(
        self,
    ) -> None:
        timestamp = datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc)

        asset = self.repository.create_asset(
            AccessAssetRecord(
                asset_id="asset_openai",
                asset_kind="secret_asset",
                display_name="OpenAI API",
                governance_scope="workspace",
                secret_policy={"storage": "binding_only"},
                storage_key="vault://access/openai",
                consumer_modules=("llm", "tool"),
                readiness_policy={"probe": "credential_binding"},
                rotation_policy={"interval_days": 90},
                export_policy={"mode": "metadata_only"},
                redaction_policy={"fields": ["source_ref", "masked_preview"]},
                metadata={"owner": "access"},
                created_at=timestamp,
            ),
        )
        credential_binding = self.repository.create_credential_binding(
            AccessCredentialBindingRecord(
                binding_id="cred_openai_env",
                asset_id=asset.asset_id,
                binding_kind="api_key",
                source_kind="env",
                source_ref="OPENAI_API_KEY",
                masked_preview="sk-...tail",
                redaction_policy={"mode": "masked"},
                metadata={"imported_from": "settings"},
                created_at=timestamp,
            ),
        )
        consumer_binding = self.repository.create_consumer_binding(
            AccessConsumerBindingRecord(
                binding_id="consumer_llm_writer",
                consumer_module="llm",
                consumer_kind="llm_profile",
                consumer_id="writer",
                display_name="Writer model",
                asset_id=asset.asset_id,
                credential_binding_id=credential_binding.binding_id,
                requirement_sets=(("openai:api_key(env:OPENAI_API_KEY)",),),
                redaction_policy={"mode": "metadata_only"},
                metadata={"imported_from": "settings"},
                created_at=timestamp,
            ),
        )
        self.repository.create_secret_binding(
            AccessSecretBindingRecord(
                binding_id="secret_openai",
                credential_binding_id=credential_binding.binding_id,
                storage_key="vault://access/openai",
                source_kind="keychain_ref",
                source_ref="keychain:item/openai",
                masked_preview="sk-...tail",
                redaction_policy={"mode": "masked"},
                created_at=timestamp,
            ),
        )
        self.repository.create_connection_profile(
            AccessConnectionProfileRecord(
                profile_id="conn_openai",
                asset_id=asset.asset_id,
                provider="openai",
                profile_kind="llm_provider",
                endpoint_ref="https://api.openai.com",
                credential_binding_id=credential_binding.binding_id,
                redaction_policy={"mode": "metadata_only"},
                created_at=timestamp,
            ),
        )
        self.repository.create_setup_session(
            AccessSetupSessionRecord(
                session_id="setup_openai",
                target_kind="credential_binding",
                target_id=credential_binding.binding_id,
                status="waiting_for_user",
                flow_kind="env_var",
                requested_by="tests",
                expires_at=timestamp + timedelta(minutes=15),
                redaction_policy={"mode": "metadata_only"},
                created_at=timestamp,
            ),
        )
        self.repository.create_readiness_snapshot(
            AccessReadinessSnapshotRecord(
                snapshot_id="ready_openai_1",
                target_kind="credential_binding",
                target_id=credential_binding.binding_id,
                status="ready",
                ready=True,
                reason="binding resolved",
                checks=({"kind": "env", "status": "ready"},),
                redaction_policy={"mode": "masked"},
                created_at=timestamp,
            ),
        )

        self.assertEqual(self.repository.get_asset("asset_openai"), asset)
        self.assertEqual(
            self.repository.get_credential_binding("cred_openai_env"),
            credential_binding,
        )
        self.assertEqual(
            self.repository.get_consumer_binding("consumer_llm_writer"),
            consumer_binding,
        )
        self.assertEqual(len(self.repository.list_consumer_bindings()), 1)
        self.assertEqual(len(self.repository.list_secret_bindings()), 1)
        self.assertEqual(len(self.repository.list_connection_profiles()), 1)
        self.assertEqual(len(self.repository.list_setup_sessions()), 1)
        self.assertEqual(len(self.repository.list_readiness_snapshots()), 1)

        inspector = inspect(self.engine)
        for table_name in ("access_credential_bindings", "access_secret_bindings"):
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            self.assertNotIn("secret", columns)
            self.assertNotIn("secret_value", columns)
            self.assertNotIn("raw_secret", columns)
            self.assertIn("masked_preview", columns)
            self.assertIn("metadata", columns)
        connection_columns = {
            column["name"]
            for column in inspector.get_columns("access_connection_profiles")
        }
        self.assertNotIn("secret", connection_columns)
        self.assertNotIn("secret_value", connection_columns)
        self.assertNotIn("raw_secret", connection_columns)
        self.assertIn("credential_binding_id", connection_columns)
        self.assertIn("endpoint_ref", connection_columns)
        self.assertIn("metadata", connection_columns)

    def test_action_audit_records_attempt_and_terminal_status(self) -> None:
        attempt = self.audit_repository.record_attempt(
            action_type="credential_binding.create",
            target_type="credential_binding",
            target_id="cred_openai_env",
            reason="test setup",
            operator="unit-test",
            request_metadata={"source_kind": "env"},
            redaction_policy={"mode": "metadata_only"},
        )

        self.assertEqual(attempt.status, "attempted")

        succeeded = self.audit_repository.mark_succeeded(
            attempt.audit_id,
            result={"binding_id": "cred_openai_env"},
        )

        self.assertEqual(succeeded.status, "succeeded")
        self.assertEqual(succeeded.result, {"binding_id": "cred_openai_env"})
        self.assertEqual(self.audit_repository.list_recent(), (succeeded,))

        failed = self.audit_repository.record_attempt(
            action_type="setup_session.complete",
            target_type="setup_session",
            target_id="setup_openai",
            reason="exercise failure path",
        )
        failed = self.audit_repository.mark_failed(
            failed.audit_id,
            error={"code": "not_ready"},
        )

        self.assertEqual(failed.status, "failed")
        self.assertEqual(failed.error, {"code": "not_ready"})


if __name__ == "__main__":
    unittest.main()
