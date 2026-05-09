from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from crxzipple.modules.settings import create_bootstrap_settings_services


class SettingsEnvironmentSetupTestCase(unittest.TestCase):
    def test_environment_seed_stores_database_summary_without_raw_secret(self) -> None:
        raw_database_url = (
            "postgresql://app:db-password@db.example.test:5432/app"
            "?sslmode=require&token=query-token"
        )
        services = create_bootstrap_settings_services(
            SimpleNamespace(
                environment="secret-env",
                database_url=raw_database_url,
                events_backend="redis",
                sandbox_backend="host",
                authorization_policy_paths=("/etc/crxzipple/policies",),
                authorization_runtime_policy_path="/etc/crxzipple/runtime.yaml",
            ),
        )

        payload = services.queries.get_effective("secret-env").effective_value
        payload_text = json.dumps(payload, sort_keys=True)

        self.assertNotIn("db-password", payload_text)
        self.assertNotIn("query-token", payload_text)
        self.assertNotIn(raw_database_url, payload_text)
        self.assertNotIn("database_url", payload)
        version = services.repositories.versions.get("secret-env:v1")
        self.assertIsNotNone(version)
        version_text = json.dumps(version.payload if version is not None else {}, sort_keys=True)
        self.assertNotIn("db-password", version_text)
        self.assertNotIn("query-token", version_text)
        self.assertNotIn(raw_database_url, version_text)

        database = payload["database_connection"]
        self.assertEqual(database["driver"], "postgresql")
        self.assertEqual(database["host"], "db.example.test")
        self.assertEqual(database["port"], 5432)
        self.assertEqual(database["database"], "app")
        self.assertTrue(database["username_present"])
        self.assertTrue(database["password_present"])
        self.assertEqual(database["query_keys"], ["sslmode", "token"])
        self.assertEqual(
            database["redacted_url"],
            "postgresql://<user>:***@db.example.test:5432/app?sslmode=***&token=***",
        )
        self.assertTrue(database["fingerprint"].startswith("sha256:"))
        self.assertEqual(payload["authorization_policy_paths"], ["/etc/crxzipple/policies"])
        self.assertEqual(
            payload["authorization_runtime_policy_path"],
            "/etc/crxzipple/runtime.yaml",
        )


if __name__ == "__main__":
    unittest.main()
