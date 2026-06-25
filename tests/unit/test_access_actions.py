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
from crxzipple.modules.access.application.services import AccessApplicationService
from crxzipple.modules.access.application.settings_config_views import (
    AccessSettingsConfigProvider,
)
from crxzipple.modules.access.application.settings_integration import (
    AccessSettingsActionAdapter,
)
from crxzipple.modules.access.domain import CredentialResolutionError
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


class FakeAccessEventPublisher:
    def __init__(self) -> None:
        self.events: list[object] = []

    def publish(self, event: object) -> None:
        self.events.append(event)


class FakeOAuthSetupResult:
    status = "waiting_for_user"

    def to_payload(self) -> dict[str, object]:
        return {
            "session_id": "oauthsetup_1",
            "provider_id": "openai-codex",
            "flow_kind": "browser_oauth",
            "authorize_url": "https://auth.openai.com/oauth/authorize?state=test",
            "callback_url": "http://localhost:1455/auth/callback",
            "metadata": {
                "callback_listener": {"status": "listening"},
                "browser_opened": True,
            },
        }


class FakeOAuthAccountResult:
    def __init__(self, account_id: str = "oauth:operator") -> None:
        self.account_id = account_id

    def to_payload(self) -> dict[str, object]:
        return {
            "resource_kind": "oauth_account",
            "account_id": self.account_id,
            "provider_id": "example-oauth",
            "credential_binding_id": "example-oauth-operator",
            "status": "active",
            "granted_scopes": ["profile"],
            "scope_diff": {
                "declared": ["profile"],
                "requested": ["profile"],
                "granted": ["profile"],
                "missing": [],
                "extra": [],
            },
        }


class FakeOAuthAccountRecord:
    def __init__(self, account_id: str, status: str) -> None:
        self.account_id = account_id
        self.provider_id = "example-oauth"
        self.credential_binding_id = "example-oauth-operator"
        self.status = status


class FakeOAuthService:
    def __init__(self) -> None:
        self.codex_oauth_calls: list[dict[str, object]] = []
        self.browser_setup_calls: list[dict[str, object]] = []
        self.device_setup_calls: list[dict[str, object]] = []
        self.complete_calls: list[dict[str, object]] = []
        self.refresh_calls: list[str] = []
        self.rotate_calls: list[dict[str, object]] = []
        self.status_calls: list[dict[str, object]] = []

    def begin_browser_setup(
        self,
        *,
        provider_id: str,
        requested_scopes: tuple[str, ...] = (),
        account_id: str | None = None,
        credential_binding_id: str | None = None,
        actor: str | None = None,
        reason: str = "begin OAuth setup",
    ) -> FakeOAuthSetupResult:
        self.browser_setup_calls.append(
            {
                "provider_id": provider_id,
                "requested_scopes": requested_scopes,
                "account_id": account_id,
                "credential_binding_id": credential_binding_id,
                "actor": actor,
                "reason": reason,
            },
        )
        return FakeOAuthSetupResult()

    def begin_device_code_setup(
        self,
        *,
        provider_id: str,
        requested_scopes: tuple[str, ...] = (),
        account_id: str | None = None,
        credential_binding_id: str | None = None,
        actor: str | None = None,
        reason: str = "begin OAuth device-code setup",
    ) -> FakeOAuthSetupResult:
        self.device_setup_calls.append(
            {
                "provider_id": provider_id,
                "requested_scopes": requested_scopes,
                "account_id": account_id,
                "credential_binding_id": credential_binding_id,
                "actor": actor,
                "reason": reason,
            },
        )
        return FakeOAuthSetupResult()

    def complete_setup_session(
        self,
        *,
        session_id: str,
        code: str | None = None,
        state: str | None = None,
        account_id: str | None = None,
        credential_binding_id: str | None = None,
    ) -> FakeOAuthAccountResult:
        self.complete_calls.append(
            {
                "session_id": session_id,
                "code": code,
                "state": state,
                "account_id": account_id,
                "credential_binding_id": credential_binding_id,
            },
        )
        return FakeOAuthAccountResult(account_id or "oauth:operator")

    def begin_codex_oauth_login(
        self,
        *,
        account_id: str,
        credential_binding_id: str,
        actor: str | None = None,
        reason: str = "begin OpenAI Codex OAuth login",
        open_browser: bool = True,
    ) -> FakeOAuthSetupResult:
        self.codex_oauth_calls.append(
            {
                "account_id": account_id,
                "credential_binding_id": credential_binding_id,
                "actor": actor,
                "reason": reason,
                "open_browser": open_browser,
            },
        )
        return FakeOAuthSetupResult()

    def refresh_account(self, account_id: str) -> FakeOAuthAccountResult:
        self.refresh_calls.append(account_id)
        return FakeOAuthAccountResult(account_id)

    def begin_account_rotation(
        self,
        account_id: str,
        *,
        requested_scopes: tuple[str, ...] = (),
        actor: str | None = None,
        reason: str = "rotate OAuth account",
        flow_kind: str = "browser_oauth",
    ) -> FakeOAuthSetupResult:
        self.rotate_calls.append(
            {
                "account_id": account_id,
                "requested_scopes": requested_scopes,
                "actor": actor,
                "reason": reason,
                "flow_kind": flow_kind,
            },
        )
        return FakeOAuthSetupResult()

    def set_account_status(self, account_id: str, *, status: str) -> FakeOAuthAccountRecord:
        self.status_calls.append({"account_id": account_id, "status": status})
        return FakeOAuthAccountRecord(account_id, status)


class AccessActionServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.governance_repository = FakeAccessGovernanceRepository()
        self.audit_repository = FakeAccessActionAuditRepository()
        self.event_publisher = FakeAccessEventPublisher()
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
            event_publisher=self.event_publisher,
        )

    def _register_openai_binding(self) -> None:
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

    def _bind_weather_tool_to_openai(self) -> None:
        self.service.execute(
            AccessActionRequest(
                action_id="act_bind_weather",
                resource_kind="consumer_binding",
                target_id="consumer:tool:openapi_provider:weather:api_key",
                intent="bind_credential_requirement",
                changes={
                    "credential_binding_id": "cred_openai_env",
                    "consumer_module": "tool",
                    "consumer_kind": "openapi_provider",
                    "consumer_id": "weather",
                    "slot": "api_key",
                    "expected_kind": "api_key",
                    "provider": "weather",
                },
                reason="allow weather tool to use OpenAI credential",
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

    def test_register_app_credential_binding_records_settings_config(self) -> None:
        result = self.service.execute(
            AccessActionRequest(
                action_id="act_register_lark_app",
                resource_kind="credential_binding",
                target_id="lark-app-secret",
                intent="register_app_credential_binding",
                changes={
                    "source_ref": "lark-app-default",
                    "binding_kind": "app_secret",
                    "asset_id": "lark-main-app",
                },
                reason="register Lark app credential reference",
                actor="unit-test",
            ),
        )

        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.asset["binding_id"], "lark-app-secret")
        self.assertEqual(result.asset["binding_kind"], "app_secret")
        self.assertEqual(result.asset["source_kind"], "app_credential")
        config = AccessSettingsConfigProvider(
            self.settings_services.queries,
        ).view()
        binding = config.get_credential_binding("lark-app-secret")
        self.assertIsNotNone(binding)
        assert binding is not None
        self.assertEqual(binding.source_kind, "app_credential")
        self.assertEqual(binding.source_ref, "lark-app-default")

    def test_update_credential_binding_preserves_omitted_fields_and_reports_before_after(
        self,
    ) -> None:
        self.service.execute(
            AccessActionRequest(
                action_id="act_register_openai",
                resource_kind="credential_binding",
                target_id="cred_openai_env",
                intent="register_env_binding",
                changes={
                    "source_ref": "OPENAI_API_KEY",
                    "binding_kind": "api_key",
                    "asset_id": "asset_openai",
                    "masked_preview": "env:OPENAI_API_KEY",
                },
                reason="register OpenAI credential source",
            ),
        )

        result = self.service.execute(
            AccessActionRequest(
                action_id="act_update_openai",
                resource_kind="credential_binding",
                target_id="cred_openai_env",
                intent="update_credential_binding",
                changes={
                    "source_kind": "file",
                    "path": "file:/tmp/openai-token.txt",
                    "binding_kind": "api_key",
                    "masked_preview": "file:***",
                    "status": "disabled",
                },
                reason="move OpenAI credential binding to a file source",
                confirmation="cred_openai_env",
                risk_acknowledged=True,
            ),
        )

        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.asset["binding_id"], "cred_openai_env")
        self.assertEqual(result.asset["source_kind"], "file")
        self.assertEqual(result.asset["source_ref"], "file:/tmp/openai-token.txt")
        self.assertEqual(result.asset["asset_id"], "asset_openai")
        self.assertEqual(result.asset["status"], "disabled")
        self.assertEqual(
            result.asset["previous_fields"]["source_ref"],
            "env:OPENAI_API_KEY",
        )
        self.assertEqual(
            result.asset["updated_fields"]["source_ref"],
            "file:/tmp/openai-token.txt",
        )
        self.assertEqual(
            result.validation["before_redacted"]["source_ref"],
            "env:OPENAI_API_KEY",
        )
        self.assertEqual(
            result.validation["after_redacted"]["source_ref"],
            "file:/tmp/openai-token.txt",
        )
        self.assertEqual(
            result.validation["metadata"]["previous_fields"]["status"],
            "active",
        )
        self.assertEqual(
            result.validation["metadata"]["updated_fields"]["status"],
            "disabled",
        )
        config = AccessSettingsConfigProvider(self.settings_services.queries).view()
        binding = config.get_credential_binding("cred_openai_env")
        self.assertIsNotNone(binding)
        assert binding is not None
        self.assertEqual(binding.source_kind, "file")
        self.assertEqual(binding.source_ref, "/tmp/openai-token.txt")
        self.assertEqual(binding.asset_id, "asset_openai")
        self.assertEqual(binding.masked_preview, "file:***")
        self.assertEqual(binding.status, "disabled")
        settings_audit = self.settings_services.queries.list_audits()[-1]
        audit_metadata = settings_audit.request_metadata["payload"]["metadata"][
            "access_action_validation"
        ]
        self.assertEqual(audit_metadata["binding_id"], "cred_openai_env")
        self.assertEqual(
            audit_metadata["before_redacted"]["source_ref"],
            "env:OPENAI_API_KEY",
        )
        self.assertEqual(
            audit_metadata["after_redacted"]["source_ref"],
            "file:/tmp/openai-token.txt",
        )

    def test_update_credential_binding_rejects_raw_secret_inputs(self) -> None:
        self._register_openai_binding()

        with self.assertRaisesRegex(ValueError, "raw secret values"):
            self.service.execute(
                AccessActionRequest(
                    action_id="act_update_openai",
                    resource_kind="credential_binding",
                    target_id="cred_openai_env",
                    intent="update_credential_binding",
                    changes={"api_key": "sk-should-not-persist"},
                    reason="try to update with a raw secret",
                ),
            )

        config = AccessSettingsConfigProvider(self.settings_services.queries).view()
        binding = config.get_credential_binding("cred_openai_env")
        self.assertIsNotNone(binding)
        assert binding is not None
        self.assertEqual(binding.source_ref, "OPENAI_API_KEY")
        self.assertEqual(len(self.settings_services.queries.list_audits()), 1)

    def test_update_credential_binding_dangerous_status_requires_confirmation(
        self,
    ) -> None:
        self._register_openai_binding()

        with self.assertRaisesRegex(ValueError, "confirmation"):
            self.service.execute(
                AccessActionRequest(
                    action_id="act_update_openai",
                    resource_kind="credential_binding",
                    target_id="cred_openai_env",
                    intent="update_credential_binding",
                    changes={"status": "disabled"},
                    reason="disable stale OpenAI credential through update",
                    risk_acknowledged=True,
                ),
            )

        with self.assertRaisesRegex(ValueError, "risk acknowledgement"):
            self.service.execute(
                AccessActionRequest(
                    action_id="act_update_openai",
                    resource_kind="credential_binding",
                    target_id="cred_openai_env",
                    intent="update_credential_binding",
                    changes={"status": "revoked"},
                    reason="revoke compromised OpenAI credential through update",
                    confirmation="cred_openai_env",
                ),
            )

        config = AccessSettingsConfigProvider(self.settings_services.queries).view()
        binding = config.get_credential_binding("cred_openai_env")
        self.assertIsNotNone(binding)
        assert binding is not None
        self.assertEqual(binding.status, "active")

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

    def test_bind_credential_requirement_records_settings_consumer_binding(self) -> None:
        self._register_openai_binding()

        result = self.service.execute(
            AccessActionRequest(
                action_id="act_bind_weather",
                resource_kind="consumer_binding",
                target_id="consumer:tool:openapi_provider:weather:api_key",
                intent="bind_credential_requirement",
                changes={
                    "credential_binding_id": "cred_openai_env",
                    "consumer_module": "tool",
                    "consumer_kind": "openapi_provider",
                    "consumer_id": "weather",
                    "slot": "api_key",
                    "expected_kind": "api_key",
                    "provider": "weather",
                },
                reason="allow weather tool to use OpenAI credential",
            ),
        )

        self.assertEqual(result.status, "succeeded")
        self.assertTrue(result.audit_ref.startswith("settings_audit_"))
        self.assertEqual(result.asset["resource_kind"], "consumer_binding")
        config = AccessSettingsConfigProvider(self.settings_services.queries).view()
        consumer = config.get_consumer_binding(
            "consumer:tool:openapi_provider:weather:api_key",
        )
        self.assertIsNotNone(consumer)
        assert consumer is not None
        self.assertEqual(consumer.credential_binding_id, "cred_openai_env")
        self.assertEqual(consumer.consumer_module, "tool")

        provider = AccessControlPlaneQueryProvider(
            governance_repository=self.governance_repository,
            audit_repository=self.audit_repository,
            settings_config_provider=AccessSettingsConfigProvider(
                self.settings_services.queries,
            ),
        )
        payload = provider.credential_requirements().to_payload()
        self.assertEqual(len(payload["credential_requirements"]), 1)
        row = payload["credential_requirements"][0]
        self.assertTrue(row["ready"])
        self.assertEqual(row["binding_id"], "cred_openai_env")

    def test_unbind_credential_requirement_keeps_requirement_visible(self) -> None:
        self._register_openai_binding()
        self._bind_weather_tool_to_openai()

        result = self.service.execute(
            AccessActionRequest(
                action_id="act_unbind_weather",
                resource_kind="consumer_binding",
                target_id="consumer:tool:openapi_provider:weather:api_key",
                intent="unbind_credential_requirement",
                changes={},
                reason="remove weather credential binding",
            ),
        )

        self.assertEqual(result.status, "succeeded")
        config = AccessSettingsConfigProvider(self.settings_services.queries).view()
        consumer = config.get_consumer_binding(
            "consumer:tool:openapi_provider:weather:api_key",
        )
        self.assertIsNotNone(consumer)
        assert consumer is not None
        self.assertIsNone(consumer.credential_binding_id)
        provider = AccessControlPlaneQueryProvider(
            governance_repository=self.governance_repository,
            audit_repository=self.audit_repository,
            settings_config_provider=AccessSettingsConfigProvider(
                self.settings_services.queries,
            ),
        )
        payload = provider.credential_requirements().to_payload()
        row = payload["credential_requirements"][0]
        self.assertFalse(row["ready"])
        self.assertTrue(row["missing"])
        self.assertEqual(row["status"], "missing")

    def test_disable_credential_binding_blocks_readiness_and_runtime_resolution(self) -> None:
        self._register_openai_binding()
        self._bind_weather_tool_to_openai()

        result = self.service.execute(
            AccessActionRequest(
                action_id="act_disable_openai",
                resource_kind="credential_binding",
                target_id="cred_openai_env",
                intent="disable_credential_binding",
                reason="disable stale OpenAI credential",
                confirmation="cred_openai_env",
                risk_acknowledged=True,
            ),
        )

        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.asset["status"], "disabled")
        config_provider = AccessSettingsConfigProvider(self.settings_services.queries)
        binding = config_provider.view().get_credential_binding("cred_openai_env")
        self.assertIsNotNone(binding)
        assert binding is not None
        self.assertEqual(binding.status, "disabled")

        query = AccessControlPlaneQueryProvider(
            governance_repository=self.governance_repository,
            audit_repository=self.audit_repository,
            settings_config_provider=config_provider,
        )
        payload = query.credential_requirements().to_payload()
        row = payload["credential_requirements"][0]
        self.assertFalse(row["ready"])
        self.assertEqual(row["status"], "disabled")
        audits = query.audits().to_payload()["audits"]
        self.assertTrue(
            any(
                audit["source"] == "settings.access_config"
                and audit["target_id"] == "cred_openai_env"
                for audit in audits
            ),
        )

        runtime_access = AccessApplicationService(config_view=config_provider.view())
        with self.assertRaisesRegex(CredentialResolutionError, "disabled"):
            runtime_access.resolve_credential("cred_openai_env")

    def test_revoke_credential_binding_is_terminal(self) -> None:
        self._register_openai_binding()

        result = self.service.execute(
            AccessActionRequest(
                action_id="act_revoke_openai",
                resource_kind="credential_binding",
                target_id="cred_openai_env",
                intent="revoke_credential_binding",
                reason="revoke compromised OpenAI credential",
                confirmation="cred_openai_env",
                risk_acknowledged=True,
            ),
        )

        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.asset["status"], "revoked")
        with self.assertRaisesRegex(ValueError, "cannot be re-enabled"):
            self.service.execute(
                AccessActionRequest(
                    action_id="act_enable_revoked_openai",
                    resource_kind="credential_binding",
                    target_id="cred_openai_env",
                    intent="enable_credential_binding",
                    reason="attempt to re-enable revoked credential",
                ),
            )

        with self.assertRaisesRegex(ValueError, "cannot be re-enabled"):
            self.service.execute(
                AccessActionRequest(
                    action_id="act_update_revoked_openai",
                    resource_kind="credential_binding",
                    target_id="cred_openai_env",
                    intent="update_credential_binding",
                    changes={"status": "active"},
                    reason="attempt to reactivate revoked credential through update",
                ),
            )

    def test_bind_unbind_and_verify_are_slot_scoped(self) -> None:
        self.service.execute(
            AccessActionRequest(
                action_id="act_register_lark_app",
                resource_kind="credential_binding",
                target_id="cred_lark_app_id",
                intent="register_env_binding",
                changes={"source_ref": "LARK_APP_ID", "binding_kind": "api_key"},
                reason="register Lark app id binding",
            ),
        )
        self.service.execute(
            AccessActionRequest(
                action_id="act_register_lark_secret",
                resource_kind="credential_binding",
                target_id="cred_lark_secret",
                intent="register_env_binding",
                changes={"source_ref": "LARK_APP_SECRET", "binding_kind": "app_secret"},
                reason="register Lark app secret binding",
            ),
        )
        target = "consumer:channels:channel_account:lark-default"
        shared_changes = {
            "consumer_module": "channels",
            "consumer_kind": "channel_account",
            "consumer_id": "lark/default",
            "provider": "lark",
            "requirement_sets": [
                [
                    "lark:api_key(lark_app_id)",
                    "lark:app_secret(lark_app_secret)",
                ],
            ],
        }

        self.service.execute(
            AccessActionRequest(
                action_id="act_bind_lark_app",
                resource_kind="consumer_binding",
                target_id=target,
                intent="bind_credential_requirement",
                changes={
                    **shared_changes,
                    "slot": "lark_app_id",
                    "expected_kind": "api_key",
                    "credential_binding_id": "cred_lark_app_id",
                },
                reason="bind Lark app id slot",
            ),
        )
        self.service.execute(
            AccessActionRequest(
                action_id="act_bind_lark_secret",
                resource_kind="consumer_binding",
                target_id=target,
                intent="bind_credential_requirement",
                changes={
                    **shared_changes,
                    "slot": "lark_app_secret",
                    "expected_kind": "app_secret",
                    "credential_binding_id": "cred_lark_secret",
                },
                reason="bind Lark app secret slot",
            ),
        )

        config = AccessSettingsConfigProvider(self.settings_services.queries).view()
        consumer = config.get_consumer_binding(target)
        self.assertIsNotNone(consumer)
        assert consumer is not None
        self.assertIsNone(consumer.credential_binding_id)
        self.assertEqual(
            consumer.credential_bindings,
            {
                "lark_app_id": "cred_lark_app_id",
                "lark_app_secret": "cred_lark_secret",
            },
        )

        verify = self.service.execute(
            AccessActionRequest(
                action_id="act_verify_lark_secret",
                resource_kind="consumer_binding",
                target_id=target,
                intent="verify_credential_requirement",
                changes={"slot": "lark_app_secret"},
                reason="verify Lark secret slot",
            ),
        )
        self.assertEqual(verify.status, "succeeded")
        self.assertEqual(verify.readiness["slot"], "lark_app_secret")
        self.assertEqual(verify.readiness["expected_kind"], "app_secret")
        self.assertEqual(verify.readiness["credential_binding_id"], "cred_lark_secret")

        self.service.execute(
            AccessActionRequest(
                action_id="act_unbind_lark_app",
                resource_kind="consumer_binding",
                target_id=target,
                intent="unbind_credential_requirement",
                changes={"slot": "lark_app_id"},
                reason="unbind only the Lark app id slot",
            ),
        )

        provider = AccessControlPlaneQueryProvider(
            governance_repository=self.governance_repository,
            audit_repository=self.audit_repository,
            settings_config_provider=AccessSettingsConfigProvider(
                self.settings_services.queries,
            ),
        )
        rows = {
            item["slot"]: item
            for item in provider.credential_requirements().to_payload()[
                "credential_requirements"
            ]
        }
        self.assertEqual(rows["lark_app_id"]["status"], "missing")
        self.assertEqual(rows["lark_app_secret"]["status"], "ready")
        self.assertEqual(rows["lark_app_secret"]["binding_id"], "cred_lark_secret")

    def test_verify_credential_requirement_reports_kind_mismatch(self) -> None:
        self.service.execute(
            AccessActionRequest(
                action_id="act_register_token",
                resource_kind="credential_binding",
                target_id="cred_bearer_file",
                intent="register_file_binding",
                changes={
                    "path": "/tmp/token.txt",
                    "binding_kind": "bearer_token",
                },
                reason="register bearer credential source",
            ),
        )
        self.service.execute(
            AccessActionRequest(
                action_id="act_bind_mismatch",
                resource_kind="consumer_binding",
                target_id="consumer:tool:openapi_provider:weather:api_key",
                intent="bind_credential_requirement",
                changes={
                    "credential_binding_id": "cred_bearer_file",
                    "consumer_module": "tool",
                    "consumer_kind": "openapi_provider",
                    "consumer_id": "weather",
                    "slot": "api_key",
                    "expected_kind": "api_key",
                    "provider": "weather",
                    "allow_kind_mismatch": True,
                },
                reason="record mismatched binding for verification",
            ),
        )

        result = self.service.execute(
            AccessActionRequest(
                action_id="act_verify_weather",
                resource_kind="consumer_binding",
                target_id="consumer:tool:openapi_provider:weather:api_key",
                intent="verify_credential_requirement",
                changes={},
                reason="verify weather credential requirement",
            ),
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.readiness["status"], "credential_kind_mismatch")
        self.assertFalse(result.validation["ok"])
        self.assertEqual(self.audit_repository.records["audit_1"].status, "succeeded")

    def test_verify_credential_requirement_reports_source_kind_mismatch(self) -> None:
        self.service.execute(
            AccessActionRequest(
                action_id="act_register_oauth_source_as_api_key",
                resource_kind="credential_binding",
                target_id="cred_oauth_source_api_key",
                intent="register_oauth_account_binding",
                changes={
                    "account_id": "example-oauth:operator",
                    "binding_kind": "api_key",
                },
                reason="register incompatible oauth source",
            ),
        )
        self.service.execute(
            AccessActionRequest(
                action_id="act_bind_oauth_source_as_api_key",
                resource_kind="consumer_binding",
                target_id="consumer:tool:openapi_provider:weather:api_key",
                intent="bind_credential_requirement",
                changes={
                    "credential_binding_id": "cred_oauth_source_api_key",
                    "consumer_module": "tool",
                    "consumer_kind": "openapi_provider",
                    "consumer_id": "weather",
                    "slot": "api_key",
                    "expected_kind": "api_key",
                    "provider": "weather",
                },
                reason="record source-kind mismatch for verification",
            ),
        )

        result = self.service.execute(
            AccessActionRequest(
                action_id="act_verify_weather_source",
                resource_kind="consumer_binding",
                target_id="consumer:tool:openapi_provider:weather:api_key",
                changes={},
                intent="verify_credential_requirement",
                reason="verify weather source compatibility",
            ),
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(
            result.readiness["status"],
            "credential_source_kind_mismatch",
        )
        self.assertEqual(
            result.readiness["checks"][2]["code"],
            "credential_source_kind_compatible",
        )

    def test_runtime_resolution_rejects_kind_and_source_mismatches(self) -> None:
        config_view = type(
            "_RuntimeConfigView",
            (),
            {
                "get_credential_binding": lambda _self, binding_id: {
                    "credential:bearer": AccessCredentialBindingRecord(
                        asset_id=None,
                        binding_id="credential:bearer",
                        binding_kind="bearer_token",
                        source_kind="env",
                        source_ref="ACCESS_TOKEN",
                    ),
                    "credential:oauth-source-api-key": AccessCredentialBindingRecord(
                        asset_id=None,
                        binding_id="credential:oauth-source-api-key",
                        binding_kind="api_key",
                        source_kind="oauth_account",
                        source_ref="example-oauth:operator",
                    ),
                }.get(binding_id),
            },
        )()
        runtime_access = AccessApplicationService(config_view=config_view)

        readiness = runtime_access.check_credential_binding(
            "credential:bearer",
            expected_kind="api_key",
        )
        self.assertEqual(readiness.status, "credential_kind_mismatch")
        self.assertIn("credential_kind_mismatch", readiness.reason)
        with self.assertRaisesRegex(
            CredentialResolutionError,
            "credential_kind_mismatch",
        ):
            runtime_access.resolve_credential(
                "credential:bearer",
                expected_kind="api_key",
            )

        source_readiness = runtime_access.check_credential_binding(
            "credential:oauth-source-api-key",
            expected_kind="api_key",
        )
        self.assertEqual(source_readiness.status, "credential_source_kind_mismatch")
        with self.assertRaisesRegex(
            CredentialResolutionError,
            "credential_source_kind_mismatch",
        ):
            runtime_access.resolve_credential("credential:oauth-source-api-key")

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
        event_names = [getattr(event, "name", "") for event in self.event_publisher.events]
        self.assertEqual(
            event_names,
            ["access.action.requested", "access.setup.started"],
        )
        self.assertEqual(
            getattr(self.event_publisher.events[-1], "payload", {}).get("target_id"),
            "cred_openai_env",
        )
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

    def test_actions_reject_raw_secret_inputs_in_oauth_and_nested_metadata(self) -> None:
        for index, request in enumerate(
            (
                AccessActionRequest(
                    action_id="act_oauth_raw_token",
                    resource_kind="oauth_setup_session",
                    target_id="example-oauth",
                    intent="complete_oauth_setup_session",
                    changes={
                        "session_id": "oauthsetup_1",
                        "code": "oauth-code",
                        "metadata": {"access_token": "oauth-token-should-not-enter"},
                    },
                    reason="complete OAuth setup with unsafe metadata",
                ),
                AccessActionRequest(
                    action_id="act_nested_raw_secret",
                    resource_kind="credential_binding",
                    target_id="cred_openai_env",
                    intent="begin_setup_session",
                    changes={
                        "flow_kind": "env",
                        "metadata": {
                            "nested": [
                                {"client_secret": "client-secret-should-not-enter"},
                            ],
                        },
                    },
                    reason="start setup with unsafe nested metadata",
                ),
                AccessActionRequest(
                    action_id="act_trace_raw_secret",
                    resource_kind="credential_binding",
                    target_id="cred_openai_env",
                    intent="begin_setup_session",
                    changes={"flow_kind": "env"},
                    reason="start setup with unsafe trace context",
                    trace_context={
                        "request": {
                            "authorization": "Bearer trace-token-should-not-enter",
                        },
                    },
                ),
            ),
        ):
            with self.subTest(index=index):
                with self.assertRaisesRegex(ValueError, "raw secret values"):
                    self.service.execute(request)

        self.assertEqual(self.audit_repository.attempts, [])

    def test_begin_codex_oauth_login_starts_builtin_oauth_flow(self) -> None:
        oauth_service = FakeOAuthService()
        service = AccessActionService(
            audit_repository=self.audit_repository,
            oauth_service=oauth_service,
        )

        result = service.execute(
            AccessActionRequest(
                action_id="act_start_codex_login",
                resource_kind="oauth_login",
                target_id="openai-codex",
                intent="begin_codex_oauth_login",
                changes={
                    "credential_binding_id": "codex-oauth-default",
                    "account_id": "openai-codex:default",
                    "open_browser": False,
                },
                reason="start Codex login",
                actor="unit-test",
            ),
        )

        self.assertEqual(result.status, "succeeded")
        self.assertEqual(
            oauth_service.codex_oauth_calls,
            [
                {
                    "account_id": "openai-codex:default",
                    "credential_binding_id": "codex-oauth-default",
                    "actor": "unit-test",
                    "reason": "start Codex login",
                    "open_browser": False,
                },
            ],
        )
        self.assertEqual(result.asset["resource_kind"], "oauth_setup_session")
        self.assertEqual(result.asset["authorize_url"], "https://auth.openai.com/oauth/authorize?state=test")
        self.assertEqual(
            self.audit_repository.records["audit_1"].action_type,
            "begin_codex_oauth_login",
        )

    def test_generic_oauth_setup_actions_preserve_account_and_binding(self) -> None:
        oauth_service = FakeOAuthService()
        service = AccessActionService(
            audit_repository=self.audit_repository,
            oauth_service=oauth_service,
        )

        begin = service.execute(
            AccessActionRequest(
                action_id="act_start_oauth",
                resource_kind="oauth_provider",
                target_id="example-oauth",
                intent="begin_oauth_setup_session",
                changes={
                    "provider_id": "example-oauth",
                    "scopes": ["profile"],
                    "account_id": "example-oauth:operator",
                    "credential_binding_id": "example-oauth-operator",
                },
                reason="start generic OAuth setup",
                actor="unit-test",
            ),
        )
        complete = service.execute(
            AccessActionRequest(
                action_id="act_complete_oauth",
                resource_kind="oauth_setup_session",
                target_id="oauthsetup_1",
                intent="complete_oauth_setup_session",
                changes={
                    "session_id": "oauthsetup_1",
                    "code": "oauth-code",
                    "state": "oauth-state",
                    "account_id": "example-oauth:operator",
                    "credential_binding_id": "example-oauth-operator",
                },
                reason="complete generic OAuth setup",
                actor="unit-test",
            ),
        )

        self.assertEqual(begin.status, "succeeded")
        self.assertEqual(complete.status, "succeeded")
        self.assertEqual(
            oauth_service.browser_setup_calls,
            [
                {
                    "provider_id": "example-oauth",
                    "requested_scopes": ("profile",),
                    "account_id": "example-oauth:operator",
                    "credential_binding_id": "example-oauth-operator",
                    "actor": "unit-test",
                    "reason": "start generic OAuth setup",
                },
            ],
        )
        self.assertEqual(
            oauth_service.complete_calls,
            [
                {
                    "session_id": "oauthsetup_1",
                    "code": "oauth-code",
                    "state": "oauth-state",
                    "account_id": "example-oauth:operator",
                    "credential_binding_id": "example-oauth-operator",
                },
            ],
        )

    def test_oauth_account_refresh_and_rotate_are_audited_actions(self) -> None:
        oauth_service = FakeOAuthService()
        service = AccessActionService(
            audit_repository=self.audit_repository,
            oauth_service=oauth_service,
        )

        refresh = service.execute(
            AccessActionRequest(
                action_id="act_refresh_oauth",
                resource_kind="oauth_account",
                target_id="example-oauth:operator",
                intent="refresh_oauth_account",
                reason="refresh OAuth account",
                actor="unit-test",
            ),
        )
        rotate = service.execute(
            AccessActionRequest(
                action_id="act_rotate_oauth",
                resource_kind="oauth_account",
                target_id="example-oauth:operator",
                intent="rotate_oauth_account",
                changes={"flow_kind": "browser_oauth"},
                reason="rotate OAuth account",
                confirmation="act_rotate_oauth",
                risk_acknowledged=True,
                actor="unit-test",
            ),
        )

        self.assertEqual(refresh.status, "succeeded")
        self.assertEqual(rotate.status, "succeeded")
        self.assertEqual(oauth_service.refresh_calls, ["example-oauth:operator"])
        self.assertEqual(
            oauth_service.rotate_calls,
            [
                {
                    "account_id": "example-oauth:operator",
                    "requested_scopes": (),
                    "actor": "unit-test",
                    "reason": "rotate OAuth account",
                    "flow_kind": "browser_oauth",
                },
            ],
        )
        self.assertEqual(
            [
                self.audit_repository.records["audit_1"].action_type,
                self.audit_repository.records["audit_2"].action_type,
            ],
            ["refresh_oauth_account", "rotate_oauth_account"],
        )


if __name__ == "__main__":
    unittest.main()
