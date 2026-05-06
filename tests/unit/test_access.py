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
    is_codex_auth_json_binding,
    is_credential_binding,
    parse_access_requirement,
)


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
        self.assertTrue(is_credential_binding("codex-cli"))
        self.assertTrue(is_codex_auth_json_binding("codex_auth_json"))
        self.assertFalse(is_credential_binding("inline-token"))
        self.assertEqual(
            credential_binding_env_name("env:OPENAI_API_KEY"),
            "OPENAI_API_KEY",
        )
        self.assertIsNone(credential_binding_env_name("file:credentials/openai.txt"))
        self.assertEqual(canonical_credential_binding("codex-cli"), "codex_auth_json")

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

    def test_credential_resolver_supports_codex_auth_json(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            auth_path = Path(tempdir) / "auth.json"
            auth_path.write_text(
                '{"tokens": {"access_token": "codex-token"}}',
                encoding="utf-8",
            )

            resolver = CredentialResolver()

            self.assertEqual(
                resolver.resolve(f"codex_auth_json:{auth_path}"),
                "codex-token",
            )

    def test_credential_resolver_only_allows_literals_when_requested(self) -> None:
        resolver = CredentialResolver()

        with self.assertRaises(CredentialResolutionError):
            resolver.resolve("inline-token")

        self.assertEqual(
            resolver.resolve("inline-token", allow_literal=True),
            "inline-token",
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

    def test_service_returns_command_flow_for_codex_login(self) -> None:
        service = AccessApplicationService()

        flow = service.begin_setup("codex_auth_json")

        self.assertEqual(flow.kind, AccessSetupFlowKind.COMMAND)
        self.assertEqual(flow.command, ("codex", "login"))
        self.assertTrue(flow.path)


if __name__ == "__main__":
    unittest.main()
