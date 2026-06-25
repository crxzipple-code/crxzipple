from __future__ import annotations

import json
import unittest

from crxzipple.modules.settings.application.action_policy import (
    SUPPORTED_KINDS,
    kind_action_allowed,
    kind_policy_payload,
    normalize_kind,
)
from crxzipple.modules.settings.application.read_models import (
    runtime_defaults_payload_errors,
    runtime_defaults_validation_payload,
)
from crxzipple.modules.settings.application.redaction import redact_value


class SettingsApplicationReadModelTestCase(unittest.TestCase):
    def test_action_policy_declares_owner_and_blocked_actions(self) -> None:
        policy = kind_policy_payload("llm-profiles")

        self.assertEqual(policy["ownership"]["owner_module"], "llm")
        self.assertEqual(policy["ownership"]["truth_owner"], "llm")
        self.assertEqual(policy["ownership"]["settings_role"], "governance_readmodel")
        self.assertEqual(policy["action_policy"]["allowed_actions"], [])
        self.assertIn("update", policy["action_policy"]["blocked_actions"])
        self.assertEqual(policy["action_policy"]["owner_api"], "/llms")
        self.assertFalse(kind_action_allowed("llm-profiles", "validate"))
        self.assertEqual(normalize_kind("llm_profiles"), "llm-profiles")
        self.assertEqual(normalize_kind("event-contracts"), "event-registry")

    def test_every_supported_kind_declares_runtime_governance_boundary(self) -> None:
        for kind in SUPPORTED_KINDS:
            with self.subTest(kind=kind):
                policy = kind_policy_payload(kind)
                ownership = policy["ownership"]
                action_policy = policy["action_policy"]
                apply_policy = policy["apply_policy"]

                self.assertTrue(ownership["owner_module"])
                self.assertTrue(ownership["truth_owner"])
                self.assertTrue(ownership["truth_source"])
                self.assertIn(
                    ownership["settings_role"],
                    {"owner", "governance_readmodel"},
                )
                self.assertIn("owner_api", action_policy)
                self.assertIsInstance(action_policy["write_actions_allowed"], bool)
                self.assertTrue(apply_policy["mode"])
                self.assertIsInstance(apply_policy["hot_apply"], bool)
                self.assertIsInstance(apply_policy["requires_owner_api"], bool)
                if (
                    action_policy["write_actions_allowed"]
                    or apply_policy["requires_owner_api"]
                ):
                    self.assertTrue(action_policy["owner_api"])

    def test_module_owned_kinds_route_actions_to_owner_api_not_settings_mutation(self) -> None:
        module_owned_kinds = (
            "agent-profiles",
            "llm-profiles",
            "skill-catalog",
            "channel-profiles",
        )

        for kind in module_owned_kinds:
            with self.subTest(kind=kind):
                policy = kind_policy_payload(kind)

                self.assertNotEqual(policy["ownership"]["truth_owner"], "settings")
                self.assertEqual(policy["ownership"]["settings_role"], "governance_readmodel")
                self.assertEqual(policy["apply_policy"]["mode"], "owner_module_api")
                self.assertTrue(policy["apply_policy"]["requires_owner_api"])
                self.assertTrue(policy["action_policy"]["owner_api"])
                self.assertFalse(policy["action_policy"]["write_actions_allowed"])
                self.assertFalse(kind_action_allowed(kind, "create"))
                self.assertFalse(kind_action_allowed(kind, "update"))
                self.assertFalse(kind_action_allowed(kind, "enable"))
                self.assertFalse(kind_action_allowed(kind, "disable"))

    def test_redaction_covers_nested_secrets_database_urls_and_token_counts(self) -> None:
        payload = {
            "database_url": "postgresql://app:db-password@db.example.test:5432/app",
            "service_url": "https://client:url-password@example.test/path?token=query-token",
            "client_token": "raw-token",
            "usage": {"total_tokens": 42},
            "nested": {
                "privateKey": "raw-private-key",
                "safe_label": "visible",
            },
        }

        redacted = redact_value(payload)
        text = json.dumps(redacted, sort_keys=True)

        for secret in ("db-password", "url-password", "query-token", "raw-token", "raw-private-key"):
            self.assertNotIn(secret, text)
        self.assertEqual(
            redacted["database_url"],
            "postgresql://app:***@db.example.test:5432/app",
        )
        self.assertEqual(
            redacted["service_url"],
            "https://client:***@example.test/path?token=***",
        )
        self.assertEqual(redacted["client_token"], "***")
        self.assertEqual(redacted["usage"]["total_tokens"], 42)
        self.assertEqual(redacted["nested"]["safe_label"], "visible")

    def test_runtime_defaults_validation_is_owned_by_application_read_model(self) -> None:
        errors = runtime_defaults_payload_errors(
            {
                "daemon": {"placeholder": True},
                "orchestration": {
                    "run_lease_seconds": 0,
                    "auto_compaction_enabled": "yes",
                },
                "tool_worker": {"unknown": 1},
            },
        )

        self.assertIn("unknown top-level field: daemon", errors)
        self.assertIn("orchestration.run_lease_seconds must be positive.", errors)
        self.assertIn("orchestration.auto_compaction_enabled must be a boolean.", errors)
        self.assertIn("unknown tool_worker field: unknown", errors)

        validation = runtime_defaults_validation_payload({"orchestration": {}, "tool_worker": {}})
        self.assertEqual(validation["status"], "valid")
        self.assertTrue(validation["result"]["ok"])


if __name__ == "__main__":
    unittest.main()
