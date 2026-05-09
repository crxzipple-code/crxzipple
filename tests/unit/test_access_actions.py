from __future__ import annotations

from dataclasses import replace
import unittest

from crxzipple.modules.access.application.actions import (
    AccessActionRequest,
    AccessActionService,
)
from crxzipple.modules.access.application.query import AccessControlPlaneQueryProvider
from crxzipple.modules.access.application.repositories import (
    AccessActionAuditRecord,
    AccessCredentialBindingRecord,
    AccessSetupSessionRecord,
)
from crxzipple.modules.access.application.setup import AccessSetupSessionService
from crxzipple.modules.access.application.settings_integration import (
    AccessSettingsActionAdapter,
    AccessSettingsConfigProvider,
)
from crxzipple.modules.settings import create_in_memory_settings_services


class FakeAccessGovernanceRepository:
    def __init__(self) -> None:
        self.credential_bindings: list[AccessCredentialBindingRecord] = []
        self.setup_sessions: list[AccessSetupSessionRecord] = []

    def create_credential_binding(
        self,
        record: AccessCredentialBindingRecord,
    ) -> AccessCredentialBindingRecord:
        self.credential_bindings.append(record)
        return record

    def create_setup_session(
        self,
        record: AccessSetupSessionRecord,
    ) -> AccessSetupSessionRecord:
        self.setup_sessions.append(record)
        return record


class FakeAccessActionAuditRepository:
    def __init__(self) -> None:
        self.records: dict[str, AccessActionAuditRecord] = {}
        self.attempts: list[AccessActionAuditRecord] = []

    def record_attempt(
        self,
        *,
        action_type: str,
        target_type: str,
        target_id: str | None,
        reason: str,
        operator: str | None = None,
        source: str = "access",
        request_metadata: dict[str, object] | None = None,
        redaction_policy: dict[str, object] | None = None,
        created_at=None,
    ) -> AccessActionAuditRecord:
        record = AccessActionAuditRecord(
            audit_id=f"audit_{len(self.records) + 1}",
            action_type=action_type,
            target_type=target_type,
            target_id=target_id,
            status="attempted",
            operator=operator,
            source=source,
            reason=reason,
            request_metadata=dict(request_metadata or {}),
            redaction_policy=dict(redaction_policy or {}),
            created_at=created_at,
        )
        self.records[record.audit_id] = record
        self.attempts.append(record)
        return record

    def mark_succeeded(
        self,
        audit_id: str,
        *,
        result: dict[str, object] | None = None,
        updated_at=None,
    ) -> AccessActionAuditRecord:
        current = self.records[audit_id]
        record = replace(
            current,
            status="succeeded",
            result=dict(result or {}),
            updated_at=updated_at,
        )
        self.records[audit_id] = record
        return record

    def mark_failed(
        self,
        audit_id: str,
        *,
        error: dict[str, object],
        updated_at=None,
    ) -> AccessActionAuditRecord:
        current = self.records[audit_id]
        record = replace(
            current,
            status="failed",
            error=dict(error),
            updated_at=updated_at,
        )
        self.records[audit_id] = record
        return record


class AccessActionServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.governance_repository = FakeAccessGovernanceRepository()
        self.audit_repository = FakeAccessActionAuditRepository()
        self.settings_services = create_in_memory_settings_services()
        self.service = AccessActionService(
            binding_repository=self.governance_repository,
            audit_repository=self.audit_repository,
            setup_session_service=AccessSetupSessionService(
                repository=self.governance_repository,
                audit_repository=self.audit_repository,
            ),
            settings_action_adapter=AccessSettingsActionAdapter(
                action_service=self.settings_services.actions,
                query_service=self.settings_services.queries,
            ),
        )

    def test_register_env_binding_records_settings_audit(self) -> None:
        result = self.service.execute(
            AccessActionRequest(
                action_id="act_register_openai",
                resource_kind="credential_binding",
                target_id="cred_openai_env",
                intent="register_env_binding",
                changes={"source_ref": "OPENAI_API_KEY", "binding_kind": "api_key"},
                reason="register OpenAI credential source",
                actor="unit-test",
                trace_context={"request_id": "trace-1"},
            ),
        )

        self.assertEqual(result.status, "succeeded")
        self.assertTrue(result.audit_ref)
        assert result.audit_ref is not None
        self.assertTrue(result.audit_ref.startswith("settings_audit_"))
        self.assertEqual(result.asset["binding_id"], "cred_openai_env")
        self.assertEqual(self.governance_repository.credential_bindings, [])
        settings_audits = self.settings_services.queries.list_audits()
        self.assertEqual(len(settings_audits), 1)
        self.assertEqual(settings_audits[0].action_type, "settings.resource.create")
        config = AccessSettingsConfigProvider(
            self.settings_services.queries,
        ).view()
        binding = config.get_credential_binding("cred_openai_env")
        self.assertIsNotNone(binding)
        assert binding is not None
        self.assertEqual(binding.source_kind, "env")
        self.assertEqual(binding.source_ref, "OPENAI_API_KEY")
        self.assertEqual(self.audit_repository.attempts, [])

    def test_config_write_requires_settings_action_adapter(self) -> None:
        service = AccessActionService(
            binding_repository=self.governance_repository,
            audit_repository=self.audit_repository,
        )

        with self.assertRaisesRegex(RuntimeError, "settings action adapter is required"):
            service.execute(
                AccessActionRequest(
                    action_id="act_register_openai",
                    resource_kind="credential_binding",
                    target_id="cred_openai_env",
                    intent="register_env_binding",
                    changes={
                        "source_ref": "OPENAI_API_KEY",
                        "binding_kind": "api_key",
                    },
                    reason="register OpenAI credential source",
                ),
            )

        self.assertEqual(self.governance_repository.credential_bindings, [])
        self.assertEqual(self.audit_repository.attempts, [])

    def test_access_read_model_reads_materialized_settings_config(self) -> None:
        self.service.execute(
            AccessActionRequest(
                action_id="act_register_openai",
                resource_kind="credential_binding",
                target_id="cred_openai_env",
                intent="register_env_binding",
                changes={"source_ref": "OPENAI_API_KEY", "binding_kind": "api_key"},
                reason="register OpenAI credential source",
            ),
        )

        provider = AccessControlPlaneQueryProvider(
            governance_repository=self.governance_repository,
            audit_repository=self.audit_repository,
            settings_config_provider=AccessSettingsConfigProvider(
                self.settings_services.queries,
            ),
        )

        payload = provider.overview().to_payload()
        self.assertEqual(payload["counts"]["credential_bindings"], 1)
        self.assertEqual(
            payload["credential_bindings"][0]["binding_id"],
            "cred_openai_env",
        )

    def test_unsupported_action_records_failed_audit(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported"):
            self.service.execute(
                AccessActionRequest(
                    action_id="act_unknown",
                    resource_kind="credential_binding",
                    target_id="cred_openai_env",
                    intent="enable_magic_binding",
                    reason="exercise failure path",
                ),
            )

        self.assertEqual(self.audit_repository.records["audit_1"].status, "failed")
        self.assertEqual(
            self.audit_repository.records["audit_1"].error["code"],
            "ValueError",
        )

    def test_missing_reason_is_rejected_without_audit_attempt(self) -> None:
        with self.assertRaisesRegex(ValueError, "reason is required"):
            self.service.execute(
                AccessActionRequest(
                    action_id="act_missing_reason",
                    resource_kind="credential_binding",
                    target_id="cred_openai_env",
                    intent="noop",
                    reason="",
                ),
            )

        self.assertEqual(self.audit_repository.attempts, [])

    def test_dangerous_action_requires_confirmation_and_risk_ack(self) -> None:
        with self.assertRaisesRegex(ValueError, "confirmation"):
            self.service.execute(
                AccessActionRequest(
                    action_id="act_delete_openai",
                    resource_kind="credential_binding",
                    target_id="cred_openai_env",
                    intent="delete_credential_binding",
                    reason="delete unused binding",
                    risk_acknowledged=True,
                ),
            )

        with self.assertRaisesRegex(ValueError, "risk acknowledgement"):
            self.service.execute(
                AccessActionRequest(
                    action_id="act_delete_openai",
                    resource_kind="credential_binding",
                    target_id="cred_openai_env",
                    intent="delete_credential_binding",
                    reason="delete unused binding",
                    confirmation="cred_openai_env",
                ),
            )
        self.assertEqual(self.audit_repository.attempts, [])

    def test_begin_setup_session_does_not_audit_secret_values(self) -> None:
        result = self.service.execute(
            AccessActionRequest(
                action_id="act_setup_openai",
                resource_kind="credential_binding",
                target_id="cred_openai_env",
                intent="begin_setup_session",
                changes={
                    "flow_kind": "env",
                    "expected_binding_kind": "api_key",
                    "secret_capture_policy": {
                        "mode": "binding_only",
                    },
                    "validation_state": {"status": "pending"},
                },
                reason="start credential setup",
                actor="unit-test",
                trace_context={"request_id": "trace-setup"},
            ),
        )

        self.assertEqual(result.status, "succeeded")
        self.assertEqual(len(self.governance_repository.setup_sessions), 1)
        self.assertEqual(result.asset["resource_kind"], "setup_session")
        audit_payload = repr(
            [
                audit.request_metadata
                for audit in self.audit_repository.records.values()
            ],
        ) + repr(
            [audit.result for audit in self.audit_repository.records.values()],
        )
        self.assertIn("before_redacted", audit_payload)
        self.assertIn("after_redacted", audit_payload)
        self.assertIn("permission_decision", audit_payload)

    def test_setup_session_rejects_raw_secret_inputs(self) -> None:
        with self.assertRaisesRegex(ValueError, "raw secret values"):
            self.service.execute(
                AccessActionRequest(
                    action_id="act_setup_openai",
                    resource_kind="credential_binding",
                    target_id="cred_openai_env",
                    intent="begin_setup_session",
                    changes={
                        "flow_kind": "env",
                        "secret_capture_policy": {
                            "mode": "binding_only",
                            "secret_value": "sk-should-not-be-stored",
                        },
                    },
                    reason="start credential setup",
                    actor="unit-test",
                ),
            )

        self.assertEqual(self.audit_repository.attempts, [])


if __name__ == "__main__":
    unittest.main()
