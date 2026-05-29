from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from crxzipple.modules.access import (
    AccessApplicationService,
    AccessReadinessStatus,
    AccessSetupFlowKind,
    CredentialResolutionError,
    CredentialResolver,
    canonical_credential_binding,
    credential_binding_env_name,
    is_credential_binding,
    parse_access_requirement,
)
from crxzipple.modules.access.application.repositories import AccessCredentialBindingRecord
from crxzipple.shared.access import AccessConsumerRef, AccessResolvedCredential


class _StaticCredentialConfigView:
    def __init__(self, records: dict[str, AccessCredentialBindingRecord]) -> None:
        self.records = records

    def get_credential_binding(
        self,
        binding_id: str,
    ) -> AccessCredentialBindingRecord | None:
        return self.records.get(binding_id)


class _MissingOAuthAccountRepository:
    def get_oauth_account(self, account_id: str) -> None:
        return None

    def get_oauth_provider(self, provider_id: str) -> None:
        return None


class _FakeAccessEventPublisher:
    def __init__(self) -> None:
        self.events: list[object] = []

    def publish(self, event: object) -> None:
        self.events.append(event)


class AccessApplicationServiceTestCase(unittest.TestCase):
    def test_parse_access_requirement_splits_provider_kind_and_scopes(self) -> None:
        requirement = parse_access_requirement(
            "github:oauth_connector(repo_read, issues_read)",
        )

        self.assertEqual(requirement.raw, "github:oauth_connector(repo_read, issues_read)")
        self.assertEqual(requirement.provider, "github")
        self.assertEqual(requirement.kind, "oauth_connector")
        self.assertEqual(requirement.scopes, ("repo_read", "issues_read"))

    def test_credential_binding_helpers_define_shared_binding_shape(self) -> None:
        self.assertTrue(is_credential_binding("env:OPENAI_API_KEY"))
        self.assertTrue(is_credential_binding("file:credentials/openai.txt"))
        self.assertFalse(is_credential_binding("inline-token"))
        self.assertFalse(is_credential_binding("codex-cli"))
        self.assertEqual(
            credential_binding_env_name("env:OPENAI_API_KEY"),
            "OPENAI_API_KEY",
        )
        self.assertIsNone(credential_binding_env_name("file:credentials/openai.txt"))
        self.assertEqual(canonical_credential_binding("codex-cli"), "codex-cli")

    def test_credential_resolver_supports_env_and_workspace_relative_file_bindings(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            workspace = Path(tempdir)
            credential_file = workspace / "credentials" / "token.txt"
            credential_file.parent.mkdir()
            credential_file.write_text("file-token\n", encoding="utf-8")
            resolver = CredentialResolver()

            with patch.dict("os.environ", {"ACCESS_TOKEN": "env-token"}):
                self.assertEqual(resolver.resolve("env:ACCESS_TOKEN"), "env-token")
                self.assertEqual(
                    resolver.resolve(
                        "file:credentials/token.txt",
                        workspace_dir=str(workspace),
                    ),
                    "file-token",
                )

    def test_credential_resolver_reports_missing_credentials(self) -> None:
        resolver = CredentialResolver()

        with self.assertRaises(CredentialResolutionError):
            resolver.resolve("env:MISSING_ACCESS_TOKEN")
        self.assertFalse(resolver.is_ready("file:missing.txt"))

    def test_credential_resolver_only_allows_literals_when_requested(self) -> None:
        resolver = CredentialResolver()

        with self.assertRaises(CredentialResolutionError):
            resolver.resolve("inline-token")

        self.assertEqual(
            resolver.resolve("inline-token", allow_literal=True),
            "inline-token",
        )

    def test_resolved_credentials_carry_safe_audit_context(self) -> None:
        event_publisher = _FakeAccessEventPublisher()
        service = AccessApplicationService(
            config_view=_StaticCredentialConfigView(
                {
                    "openai-api-key": AccessCredentialBindingRecord(
                        binding_id="openai-api-key",
                        asset_id="asset_openai",
                        binding_kind="api_key",
                        source_kind="env",
                        source_ref="OPENAI_API_KEY",
                        masked_preview="env:OPENAI_API_KEY",
                    ),
                },
            ),
            event_publisher=event_publisher,
        )

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-real-secret"}):
            credential = service.resolve_credential(
                "openai-api-key",
                consumer=AccessConsumerRef(
                    consumer_id="llm.profile:default",
                    module="llm",
                ),
                trace_context={
                    "request_id": "trace-1",
                    "api_key": "sk-trace-secret",
                    "nested": {"token": "trace-token"},
                },
            )

        self.assertIsInstance(credential, AccessResolvedCredential)
        self.assertEqual(credential, "sk-real-secret")
        audit_context = credential.audit_context
        self.assertEqual(audit_context["credential_binding_id"], "openai-api-key")
        self.assertEqual(audit_context["binding_kind"], "api_key")
        self.assertEqual(audit_context["source_ref"], "env:***")
        self.assertEqual(audit_context["masked_preview"], "env:***")
        self.assertEqual(audit_context["consumer"]["module"], "llm")
        self.assertEqual(audit_context["trace_context"]["request_id"], "trace-1")
        self.assertEqual(audit_context["trace_context"]["api_key"], "***")
        self.assertEqual(audit_context["trace_context"]["nested"]["token"], "***")
        audit_payload = repr(audit_context)
        self.assertNotIn("sk-real-secret", audit_payload)
        self.assertNotIn("sk-trace-secret", audit_payload)
        self.assertNotIn("trace-token", audit_payload)
        event_names = [getattr(event, "name", "") for event in event_publisher.events]
        self.assertEqual(
            event_names,
            [
                "access.credential.resolve.requested",
                "access.credential.resolve.succeeded",
                "access.credential.lease.granted",
            ],
        )
        event_payload = repr(
            [getattr(event, "payload", {}) for event in event_publisher.events],
        )
        self.assertIn("openai-api-key", event_payload)
        self.assertNotIn("sk-real-secret", event_payload)
        self.assertNotIn("sk-trace-secret", event_payload)
        self.assertNotIn("trace-token", event_payload)

    def test_failed_credential_resolution_publishes_denied_event(self) -> None:
        event_publisher = _FakeAccessEventPublisher()
        service = AccessApplicationService(event_publisher=event_publisher)

        with self.assertRaises(CredentialResolutionError):
            service.resolve_credential(
                "env:MISSING_ACCESS_TOKEN",
                consumer=AccessConsumerRef(
                    consumer_id="tool:weather",
                    module="tool",
                ),
                trace_context={"trace_id": "trace-access-failed"},
            )

        event_names = [getattr(event, "name", "") for event in event_publisher.events]
        self.assertEqual(
            event_names,
            [
                "access.credential.resolve.requested",
                "access.credential.resolve.failed",
                "access.credential.lease.denied",
            ],
        )
        self.assertEqual(
            getattr(event_publisher.events[-1], "payload", {}).get("status"),
            "denied",
        )

    def test_service_reports_ready_auth_requirements_from_registry_and_env(self) -> None:
        service = AccessApplicationService(
            ready_auth_requirements=("github:oauth_connector(repo_read)",),
        )

        with patch.dict(
            "os.environ",
            {"CRXZIPPLE_READY_AUTH_REQUIREMENTS": "gmail:oauth_connector(mail_read)"},
        ):
            ready = service.list_ready_auth_requirements(
                requirements=(
                    "github:oauth_connector(repo_read)",
                    "gmail:oauth_connector(mail_read)",
                    "slack:oauth_connector(channels_read)",
                ),
            )

        self.assertEqual(
            ready,
            (
                "github:oauth_connector(repo_read)",
                "gmail:oauth_connector(mail_read)",
            ),
        )

    def test_service_checks_credential_binding_readiness(self) -> None:
        service = AccessApplicationService()

        with patch.dict("os.environ", {"ACCESS_TOKEN": "present"}):
            ready = service.check_requirement("env:ACCESS_TOKEN")
        missing = service.check_requirement("env:MISSING_ACCESS_TOKEN")

        self.assertEqual(ready.status, AccessReadinessStatus.READY)
        self.assertEqual(missing.status, AccessReadinessStatus.SETUP_NEEDED)

    def test_service_returns_setup_flow_for_missing_env_requirement(self) -> None:
        service = AccessApplicationService()

        missing = service.check_requirement("env:MISSING_ACCESS_TOKEN")

        self.assertEqual(missing.status, AccessReadinessStatus.SETUP_NEEDED)
        self.assertIsNotNone(missing.setup_flow)
        assert missing.setup_flow is not None
        self.assertEqual(missing.setup_flow.kind, AccessSetupFlowKind.ENV)
        self.assertEqual(missing.setup_flow.env_vars, ("MISSING_ACCESS_TOKEN",))
        self.assertTrue(missing.setup_available)

    def test_service_no_longer_offers_codex_cli_login_setup(self) -> None:
        service = AccessApplicationService()

        flow = service.begin_setup("codex_auth_json")

        self.assertEqual(flow.kind, AccessSetupFlowKind.UNSUPPORTED)
        self.assertEqual(flow.command, ())
        self.assertEqual(flow.actions, ())

    def test_oauth_account_binding_missing_account_returns_setup_flow(self) -> None:
        service = AccessApplicationService(
            config_view=_StaticCredentialConfigView(
                {
                    "codex-oauth-default": AccessCredentialBindingRecord(
                        asset_id="oauth_provider:openai-codex",
                        binding_id="codex-oauth-default",
                        binding_kind="oauth2_account",
                        source_kind="oauth_account",
                        source_ref="openai-codex:default",
                        masked_preview="oauth_account",
                    ),
                },
            ),
            oauth_account_repository=_MissingOAuthAccountRepository(),
            oauth_token_store=object(),
        )

        readiness = service.check_credential_binding("codex-oauth-default")

        self.assertEqual(readiness.status, AccessReadinessStatus.SETUP_NEEDED)
        self.assertIn("openai-codex:default", readiness.reason)
        self.assertIsNotNone(readiness.setup_flow)
        assert readiness.setup_flow is not None
        self.assertEqual(readiness.setup_flow.kind, AccessSetupFlowKind.OAUTH_BROWSER)
        self.assertEqual(readiness.setup_flow.callback_url, "http://localhost:1455/auth/callback")
        self.assertEqual(readiness.setup_flow.action_label, "Start OAuth login")
        self.assertEqual(
            readiness.setup_flow.metadata["access_action_intent"],
            "begin_codex_oauth_login",
        )


if __name__ == "__main__":
    unittest.main()
