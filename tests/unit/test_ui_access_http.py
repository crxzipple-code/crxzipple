from __future__ import annotations

from datetime import datetime, timezone
import json

from crxzipple.modules.access.application.repositories import (
    AccessReadinessSnapshotRecord,
)
from crxzipple.modules.access.infrastructure.persistence import (
    SqlAlchemyAccessActionAuditRepository,
    SqlAlchemyAccessGovernanceRepository,
)
from crxzipple.modules.settings import CreateSettingsResourceInput
from tests.unit.http_test_support import HttpModuleTestCase


class UiAccessHttpTestCase(HttpModuleTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.repository = SqlAlchemyAccessGovernanceRepository(
            self.client.app.state.container.session_factory,
        )
        self.audit_repository = SqlAlchemyAccessActionAuditRepository(
            self.client.app.state.container.session_factory,
        )

    def _seed_access_control_plane(self) -> None:
        timestamp = datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc)
        self.client.app.state.container.settings_action_service.create_resource(
            CreateSettingsResourceInput(
                resource_id="access_openai",
                resource_kind="access-assets",
                owner_module="settings",
                display_name="OpenAI API",
                payload={
                    "assets": [
                        {
                            "asset_id": "asset_openai",
                            "asset_kind": "secret_asset",
                            "display_name": "OpenAI API",
                            "governance_scope": "workspace",
                            "secret_policy": {"storage": "binding_only"},
                            "storage_key": "vault://access/openai",
                            "consumer_modules": ["llm", "tool"],
                            "readiness_policy": {"probe": "credential_binding"},
                            "rotation_policy": {"interval_days": 90},
                            "export_policy": {"mode": "metadata_only"},
                            "metadata": {
                                "owner": "settings",
                                "token": "secret-from-asset-metadata",
                            },
                        },
                    ],
                    "credential_bindings": [
                        {
                            "binding_id": "cred_openai_literal",
                            "asset_id": "asset_openai",
                            "binding_kind": "api_key",
                            "source_kind": "literal",
                            "source_ref": "sk-real-secret",
                            "masked_preview": "sk-***",
                            "metadata": {
                                "api_key": "secret-from-credential-metadata",
                            },
                        },
                    ],
                    "consumer_bindings": [
                        {
                            "binding_id": f"consumer_{module}_openai",
                            "consumer_module": module,
                            "consumer_kind": "module",
                            "consumer_id": module,
                            "display_name": module,
                            "asset_id": "asset_openai",
                            "credential_binding_id": "cred_openai_literal",
                            "metadata": {"source": "test_access_read_model"},
                        }
                        for module in ("llm", "tool")
                    ],
                },
                reason="seed Settings-owned access config",
                publish=True,
                source="unit_test",
            ),
        )
        self.repository.create_readiness_snapshot(
            AccessReadinessSnapshotRecord(
                snapshot_id="ready_openai_1",
                target_kind="asset",
                target_id="asset_openai",
                status="setup_needed",
                ready=False,
                reason="missing rotation check",
                checks=(
                    {
                        "target_type": "credential_binding",
                        "requirement": "literal-secret",
                    },
                ),
                metadata={"access_token": "readiness-secret"},
                created_at=timestamp,
            ),
        )
        audit = self.audit_repository.record_attempt(
            action_type="credential_binding.create",
            target_type="credential_binding",
            target_id="cred_openai_literal",
            reason="unit test",
            operator="unit-test",
            request_metadata={"api_key": "secret-from-audit-request"},
            created_at=timestamp,
        )
        self.audit_repository.mark_succeeded(
            audit.audit_id,
            result={"binding_id": "cred_openai_literal", "token": "audit-secret"},
        )

    def test_ui_access_overview_reads_real_access_tables(self) -> None:
        self._seed_access_control_plane()

        response = self.client.get("/ui/access")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ready")
        self.assertFalse(payload["degraded"])
        self.assertEqual(payload["counts"]["assets"], 1)
        self.assertEqual(payload["counts"]["credential_bindings"], 1)
        self.assertEqual(payload["assets"]["assets"][0]["asset_id"], "asset_openai")
        self.assertEqual(payload["readiness"][0]["status"], "setup_needed")
        self.assertEqual(len(payload["consumer_bindings"]), 2)
        self.assertNotIn("sk-real-secret", json.dumps(payload, sort_keys=True))

    def test_settings_access_assets_route_uses_settings_read_model(self) -> None:
        self._seed_access_control_plane()

        access_response = self.client.get("/ui/access")
        settings_response = self.client.get("/ui/settings/access-assets")

        self.assertEqual(access_response.status_code, 200)
        self.assertEqual(settings_response.status_code, 200)
        settings_payload = settings_response.json()
        self.assertEqual(settings_payload["resource"], "access-assets")
        self.assertIn("resources", settings_payload)
        settings_text = json.dumps(settings_payload, sort_keys=True)
        self.assertNotIn("sk-real-secret", settings_text)
        self.assertNotIn("secret-from-asset-metadata", settings_text)
        self.assertNotIn("secret-from-credential-metadata", settings_text)

    def test_ui_access_assets_and_detail_are_redacted(self) -> None:
        self._seed_access_control_plane()

        list_response = self.client.get("/ui/access/assets")
        detail_response = self.client.get("/ui/access/assets/asset_openai")

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(detail_response.status_code, 200)
        list_payload = list_response.json()
        detail_payload = detail_response.json()
        self.assertEqual(list_payload["assets"][0]["credential_binding_count"], 1)
        self.assertEqual(detail_payload["asset_id"], "asset_openai")
        self.assertEqual(
            detail_payload["credential_bindings"][0]["source_ref"],
            "***",
        )
        payload_text = json.dumps(detail_payload, sort_keys=True)
        self.assertIn("sk-***", payload_text)
        self.assertNotIn("sk-real-secret", payload_text)
        self.assertNotIn("secret-from-credential-metadata", payload_text)

    def test_ui_access_audits_are_redacted(self) -> None:
        self._seed_access_control_plane()

        audits_response = self.client.get("/ui/access/audits")

        self.assertEqual(audits_response.status_code, 200)
        audits_payload = audits_response.json()
        self.assertEqual(audits_payload["audits"][0]["target_id"], "cred_openai_literal")
        payload_text = json.dumps({"audits": audits_payload}, sort_keys=True)
        self.assertNotIn("secret-from-audit-request", payload_text)
        self.assertNotIn("audit-secret", payload_text)

    def test_ui_access_returns_degraded_json_when_dependency_missing(self) -> None:
        previous_repository = self.client.app.state.container.access_governance_repository
        self.client.app.state.container.access_governance_repository = None
        try:
            response = self.client.get("/ui/access")
        finally:
            self.client.app.state.container.access_governance_repository = (
                previous_repository
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "degraded")
        self.assertTrue(payload["degraded"])
        self.assertIn("access_governance_repository", payload["dependency_missing"])
        self.assertEqual(payload["counts"]["assets"], 0)

    def test_ui_bootstrap_lists_access_control_plane_routes(self) -> None:
        response = self.client.get("/ui/bootstrap")

        self.assertEqual(response.status_code, 200)
        routes = response.json()["routes"]
        self.assertIn("/ui/access", routes)
        self.assertIn("/ui/access/assets/{asset_id}", routes)
        self.assertIn("/ui/access/audits", routes)
