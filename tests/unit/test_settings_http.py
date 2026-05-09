from __future__ import annotations

import json

from crxzipple.modules.settings import CreateSettingsResourceInput
from tests.unit.http_test_support import HttpModuleTestCase


class SettingsHttpTestCase(HttpModuleTestCase):
    def test_settings_overview_is_available_on_public_and_ui_prefixes(self) -> None:
        public_response = self.client.get("/settings")
        ui_response = self.client.get("/ui/settings")

        self.assertEqual(public_response.status_code, 200)
        self.assertEqual(ui_response.status_code, 200)
        for payload in (public_response.json(), ui_response.json()):
            self.assertEqual(payload["resource"], "overview")
            self.assertIn("resource_counts", payload)
            self.assertIn("health", payload)
            self.assertGreaterEqual(payload["counts"]["resources"], 1)

    def test_settings_resource_list_contains_effective_config(self) -> None:
        response = self.client.get("/ui/settings/runtime-defaults")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["resource"], "runtime-defaults")
        self.assertEqual(payload["health"]["status"], "ready")
        self.assertEqual(payload["list"]["total"], 1)
        resource = payload["resources"][0]
        self.assertEqual(resource["resource_id"], "defaults")
        self.assertIn("effective_config", resource)
        self.assertEqual(resource["resolution"]["source"]["kind"], "bootstrap")

    def test_settings_resource_detail_returns_resolution_trace(self) -> None:
        response = self.client.get("/settings/runtime-defaults/defaults")
        ui_response = self.client.get("/ui/settings/runtime-defaults/defaults")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ui_response.status_code, 200)
        payload = response.json()
        self.assertEqual(ui_response.json()["id"], "defaults")
        self.assertEqual(payload["resource"], "runtime-defaults")
        self.assertEqual(payload["id"], "defaults")
        self.assertIn("effective_config", payload)
        self.assertIn("override_trace", payload["resolution"])
        self.assertEqual(payload["validation"]["status"], "valid")

    def test_settings_environment_write_action_is_rejected_by_policy(self) -> None:
        response = self.client.post(
            "/settings/environment/actions/create",
            json={
                "resource_id": "redaction-env",
                "actor": "unit-test",
                "reason": "try generic environment create",
                "payload": {
                    "id": "redaction-env",
                    "display_name": "Redaction Environment",
                    "database_url": "postgresql://app:db-password@db.example.test:5432/app",
                },
            },
        )

        self.assertEqual(response.status_code, 409)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "settings_action_not_allowed_for_kind")
        self.assertEqual(detail["owner_module"], "settings")
        self.assertIn("create", detail["blocked_actions"])
        detail_text = json.dumps(detail, sort_keys=True)
        self.assertNotIn("db-password", detail_text)
        self.assertEqual(detail["audit"]["status"], "failed")

    def test_settings_redacts_sensitive_values_from_legacy_environment_detail(self) -> None:
        container = self.client.app.state.container
        container.settings_action_service.create_resource(
            CreateSettingsResourceInput(
                resource_id="redaction-env",
                resource_kind="environment",
                owner_module="settings",
                reason="create legacy redaction fixture",
                publish=True,
                source="unit_test_legacy_fixture",
                payload={
                    "id": "redaction-env",
                    "display_name": "Redaction Environment",
                    "database_url": "postgresql://app:db-password@db.example.test:5432/app",
                    "postgres_dsn": "host=db.example.test user=app password=dsn-password sslmode=require",
                    "service_url": (
                        "https://client:url-password@example.test/path"
                        "?token=query-token&debug=true"
                    ),
                    "client_token": "raw-client-token",
                    "nested": {
                        "privateKey": "raw-private-key",
                        "safe_label": "visible-name",
                        "endpoint": "https://api.example.test/v1",
                    },
                },
            ),
        )

        detail_response = self.client.get("/settings/environment/redaction-env")
        self.assertEqual(detail_response.status_code, 200)
        payload = detail_response.json()
        payload_text = json.dumps(payload, sort_keys=True)
        for secret in (
            "db-password",
            "dsn-password",
            "url-password",
            "query-token",
            "raw-client-token",
            "raw-private-key",
        ):
            self.assertNotIn(secret, payload_text)
        self.assertEqual(
            payload["payload"]["database_url"],
            "postgresql://app:***@db.example.test:5432/app",
        )
        self.assertEqual(
            payload["payload"]["postgres_dsn"],
            "host=db.example.test user=app password=*** sslmode=require",
        )
        self.assertEqual(
            payload["payload"]["service_url"],
            "https://client:***@example.test/path?token=***&debug=true",
        )
        self.assertEqual(payload["payload"]["client_token"], "***")
        self.assertEqual(payload["payload"]["nested"]["privateKey"], "***")
        self.assertEqual(payload["payload"]["nested"]["safe_label"], "visible-name")
        self.assertEqual(
            payload["payload"]["nested"]["endpoint"],
            "https://api.example.test/v1",
        )

        audits_response = self.client.get("/settings/audit-logs")
        self.assertEqual(audits_response.status_code, 200)
        audits_text = json.dumps(audits_response.json(), sort_keys=True)
        self.assertNotIn("raw-client-token", audits_text)
        self.assertNotIn("db-password", audits_text)

    def test_settings_kind_alias_and_placeholder_description_are_clear(self) -> None:
        response = self.client.get("/ui/settings/event-contracts")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["resource"], "event-registry")
        self.assertEqual(payload["kind"], "event-registry")
        self.assertEqual(payload["status"], "empty")
        self.assertIn("placeholder", payload["description"].lower())
        self.assertIn("Events registry", payload["description"])
        self.assertFalse(payload["action_policy"]["write_actions_allowed"])
        self.assertEqual(payload["action_policy"]["allowed_actions"], [])
        self.assertIsNone(payload["impact"]["dry_run_action"])
        self.assertEqual(payload["danger_zone"]["actions"], [])
        self.assertEqual(payload["actions"], [])

    def test_settings_audit_logs_empty_state_is_stable(self) -> None:
        response = self.client.get("/ui/settings/audit-logs")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["resource"], "audit-logs")
        self.assertEqual(payload["list"]["total"], 0)
        self.assertEqual(payload["resources"], [])
        self.assertIsNone(payload["detail"])
        self.assertEqual(payload["ownership"]["truth_owner"], "settings")
        self.assertEqual(payload["action_policy"]["allowed_actions"], [])

    def test_module_owned_profile_write_action_is_rejected_by_settings_policy(self) -> None:
        self._seed_legacy_profile_settings_resource()
        profile_id = self._first_settings_resource_id("llm-profiles")

        response = self.client.post(
            f"/settings/llm-profiles/{profile_id}/actions/disable",
            json={
                "actor": "unit-test",
                "reason": "try generic llm profile disable",
            },
        )

        self.assertEqual(response.status_code, 409)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "settings_action_not_allowed_for_kind")
        self.assertEqual(detail["owner_module"], "llm")
        self.assertEqual(detail["owner_api"], "/llms")
        self.assertIn("disable", detail["blocked_actions"])
        self.assertEqual(detail["allowed_actions"], [])
        self.assertEqual(detail["ownership"]["settings_role"], "governance_readmodel")
        self.assertEqual(detail["audit"]["status"], "failed")

    def test_module_owned_profile_create_action_is_rejected_without_resource(self) -> None:
        response = self.client.post(
            "/settings/channel-profiles/actions/create",
            json={
                "actor": "unit-test",
                "reason": "try generic channel profile create",
                "payload": {"id": "unit-channel", "channel_type": "webhook"},
            },
        )

        self.assertEqual(response.status_code, 409)
        detail = response.json()["detail"]
        self.assertEqual(detail["owner_module"], "channels")
        self.assertEqual(detail["owner_api"], "/channels")
        self.assertIn("create", detail["blocked_actions"])
        self.assertEqual(detail["audit"]["status"], "failed")

    def test_module_owned_profile_validate_action_is_rejected_by_settings_policy(self) -> None:
        self._seed_legacy_profile_settings_resource()
        profile_id = self._first_settings_resource_id("llm-profiles")

        response = self.client.post(
            f"/settings/llm-profiles/{profile_id}/actions/validate",
            json={"actor": "unit-test"},
        )

        self.assertEqual(response.status_code, 409)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "settings_action_not_allowed_for_kind")
        self.assertEqual(detail["action"], "validate")
        self.assertEqual(detail["kind"], "llm-profiles")
        self.assertEqual(detail["owner_module"], "llm")
        self.assertEqual(detail["allowed_actions"], [])
        self.assertIn("validate", detail["blocked_actions"])
        self.assertEqual(detail["audit"]["status"], "failed")

    def test_module_owned_profile_dry_run_action_is_rejected_by_settings_policy(self) -> None:
        self._seed_legacy_profile_settings_resource()
        profile_id = self._first_settings_resource_id("llm-profiles")

        response = self.client.post(
            f"/settings/llm-profiles/{profile_id}/actions/dry-run",
            json={"actor": "unit-test"},
        )

        self.assertEqual(response.status_code, 409)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "settings_action_not_allowed_for_kind")
        self.assertEqual(detail["action"], "dry-run")
        self.assertEqual(detail["allowed_actions"], [])
        self.assertIn("dry-run", detail["blocked_actions"])
        self.assertEqual(detail["audit"]["status"], "failed")

    def test_module_owned_profile_actions_only_expose_non_write_operations(self) -> None:
        self._seed_legacy_profile_settings_resource()
        response = self.client.get("/ui/settings/llm-profiles")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["ownership"]["truth_owner"], "llm")
        self.assertEqual(payload["action_policy"]["allowed_actions"], [])
        self.assertIn("dry-run", payload["action_policy"]["blocked_actions"])
        self.assertIn("validate", payload["action_policy"]["blocked_actions"])
        self.assertIn("update", payload["action_policy"]["blocked_actions"])
        self.assertEqual(payload["actions"], [])
        self.assertIsNone(payload["impact"]["dry_run_action"])
        detail_action_ids = {
            action["id"].rsplit(".", maxsplit=1)[-1]
            for action in payload["detail"]["actions"]
        }
        self.assertEqual(detail_action_ids, set())
        self.assertIsNone(payload["detail"]["impact"]["dry_run_action"])

    def test_readonly_placeholders_reject_validate_and_dry_run_actions(self) -> None:
        for kind in ("event-registry", "environment"):
            for action in ("validate", "dry-run"):
                response = self.client.post(
                    f"/settings/{kind}/redaction-env/actions/{action}",
                    json={"actor": "unit-test"},
                )

                self.assertEqual(response.status_code, 409)
                detail = response.json()["detail"]
                self.assertEqual(detail["code"], "settings_action_not_allowed_for_kind")
                self.assertEqual(detail["kind"], kind)
                self.assertEqual(detail["allowed_actions"], [])
                self.assertIn(action, detail["blocked_actions"])
                self.assertEqual(detail["audit"]["status"], "failed")

    def test_settings_owned_validate_action_is_still_available(self) -> None:
        response = self.client.post(
            "/settings/runtime-defaults/defaults/actions/validate",
            json={"actor": "unit-test"},
        )

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["action"], "validate")
        self.assertEqual(payload["kind"], "runtime-defaults")
        self.assertEqual(payload["ownership"]["truth_owner"], "settings")
        self.assertIn("validate", payload["action_policy"]["allowed_actions"])
        self.assertEqual(payload["audit"]["status"], "succeeded")

    def test_settings_owned_kind_write_action_is_not_blocked_by_policy(self) -> None:
        response = self.client.post(
            "/settings/memory-config/actions/create",
            json={
                "resource_id": "policy-memory",
                "actor": "unit-test",
                "reason": "create settings owned policy fixture",
                "payload": {"id": "policy-memory", "display_name": "Policy Memory"},
            },
        )

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["ownership"]["truth_owner"], "settings")
        self.assertTrue(payload["action_policy"]["write_actions_allowed"])
        self.assertEqual(payload["result"]["mutation"], "create")

    def test_settings_actions_audit_every_attempt(self) -> None:
        actions = (
            "dry-run",
            "validate",
            "publish",
            "rollback",
            "disable",
            "enable",
            "update",
        )
        for action in actions:
            response = self.client.post(
                f"/settings/runtime-defaults/defaults/actions/{action}",
                json={
                    "actor": "unit-test",
                    "reason": "exercise settings action audit",
                    "risk": "low",
                    "payload": {"unit_test_marker": action},
                },
            )

            self.assertEqual(response.status_code, 202)
            payload = response.json()
            self.assertEqual(payload["action"], action)
            self.assertEqual(payload["audit"]["status"], "succeeded")
            self.assertEqual(payload["audit"]["actor"], "unit-test")

        audits_response = self.client.get("/settings/audit-logs")
        self.assertEqual(audits_response.status_code, 200)
        self.assertGreaterEqual(audits_response.json()["list"]["total"], len(actions))

    def test_settings_write_action_requires_reason_but_still_audits_failure(self) -> None:
        response = self.client.post(
            "/settings/runtime-defaults/defaults/actions/update",
            json={"actor": "unit-test", "payload": {"enabled": True}},
        )

        self.assertEqual(response.status_code, 400)

        audits_response = self.client.get("/settings/audit-logs")
        self.assertEqual(audits_response.status_code, 200)
        self.assertEqual(audits_response.json()["list"]["total"], 1)
        audit = audits_response.json()["resources"][0]
        self.assertEqual(audit["status"], "failed")
        self.assertEqual(audit["action"], "update")

    def test_bootstrap_import_returns_core_and_access_import_results(self) -> None:
        response = self.client.post(
            "/settings/bootstrap-import",
            json={
                "actor": "unit-test",
                "reason": "refresh settings and access governance resources",
            },
        )

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["action"], "bootstrap-import")
        self.assertIn("core", payload["result"])
        self.assertIn("access", payload["result"])
        self.assertIn("access-assets", payload["imported_counts"])

    def _first_settings_resource_id(self, kind: str) -> str:
        response = self.client.get(f"/settings/{kind}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreater(payload["list"]["total"], 0)
        return str(payload["resources"][0]["resource_id"])

    def _seed_legacy_profile_settings_resource(self) -> None:
        self.client.app.state.container.settings_action_service.create_resource(
            CreateSettingsResourceInput(
                resource_id="legacy-openai",
                resource_kind="llm-profiles",
                owner_module="llm",
                reason="seed legacy module-owned profile index",
                publish=True,
                source="unit_test_legacy_fixture",
                payload={
                    "id": "legacy-openai",
                    "provider": "openai",
                    "api_family": "responses",
                    "model_name": "gpt-4.1-mini",
                    "enabled": True,
                },
            ),
        )
