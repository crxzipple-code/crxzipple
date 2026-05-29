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
from crxzipple.modules.tool.application import (
    ToolDiscoveryAdapter,
    ToolDiscoveryAdapterRegistry,
    ToolDiscoveryService,
    ToolFunctionCandidate,
    ToolFunctionRequirements,
    ToolFunctionRuntimeKind,
    ToolSourceCatalogKind,
    ToolSourceCatalogRecord,
    ToolSourceDiscoveryResult,
)
from crxzipple.shared.access import (
    AccessConsumerRef,
    AccessCredentialKind,
    AccessCredentialRequirementDeclaration,
    AccessCredentialRequirementSet,
    AccessCredentialSlotRef,
)
from tests.unit.http_test_support import AppKey, HttpModuleTestCase


class UiAccessHttpTestCase(HttpModuleTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.repository = SqlAlchemyAccessGovernanceRepository(
            self.client.app.state.container.require(AppKey.DATABASE_SESSION_FACTORY),
        )
        self.audit_repository = SqlAlchemyAccessActionAuditRepository(
            self.client.app.state.container.require(AppKey.DATABASE_SESSION_FACTORY),
        )

    def _seed_access_control_plane(self) -> None:
        timestamp = datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc)
        self.client.app.state.container.require(AppKey.SETTINGS_ACTION_SERVICE).create_resource(
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
                            "requirement_sets": [
                                ["openai:api_key(env:OPENAI_API_KEY)"],
                            ],
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

    def _seed_tool_catalog_requirement(self) -> None:
        source = ToolSourceCatalogRecord(
            source_id="unit.tool.credential_source",
            kind=ToolSourceCatalogKind.LOCAL_PACKAGE,
            display_name="Unit Tool Credential Source",
        )
        discovery = ToolDiscoveryService(
            ToolDiscoveryAdapterRegistry(
                {
                    ToolSourceCatalogKind.LOCAL_PACKAGE: (
                        _ToolCredentialRequirementDiscoveryAdapter()
                    ),
                },
            ),
        )
        self.client.app.state.container.require(
            AppKey.TOOL_SOURCE_COMMAND_SERVICE,
        ).sync_source(
            source,
            discovery_service=discovery,
        )

    def _seed_lark_access_bindings(self) -> None:
        self.client.app.state.container.require(AppKey.SETTINGS_ACTION_SERVICE).create_resource(
            CreateSettingsResourceInput(
                resource_id="access_lark",
                resource_kind="access-assets",
                owner_module="settings",
                display_name="Lark App Credentials",
                payload={
                    "assets": [
                        {
                            "asset_id": "asset_lark",
                            "asset_kind": "credential_bundle",
                            "display_name": "Lark App Credentials",
                            "governance_scope": "workspace",
                            "consumer_modules": ["channels"],
                        },
                    ],
                    "credential_bindings": [
                        {
                            "binding_id": "access-binding:lark-app-id",
                            "asset_id": "asset_lark",
                            "binding_kind": "api_key",
                            "source_kind": "env",
                            "source_ref": "LARK_APP_ID",
                        },
                        {
                            "binding_id": "access-binding:lark-app-secret",
                            "asset_id": "asset_lark",
                            "binding_kind": "app_secret",
                            "source_kind": "env",
                            "source_ref": "LARK_APP_SECRET",
                        },
                    ],
                },
                reason="seed Lark channel credentials",
                publish=True,
                source="unit_test",
            ),
        )

    def test_ui_access_overview_reads_real_access_tables(self) -> None:
        self._seed_access_control_plane()

        response = self.client.get("/ui/access")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ready")
        self.assertFalse(payload["degraded"])
        self.assertEqual(payload["counts"]["assets"], len(payload["assets"]["assets"]))
        self.assertGreaterEqual(payload["counts"]["assets"], 1)
        self.assertGreaterEqual(payload["counts"]["credential_bindings"], 1)
        self.assertEqual(
            payload["counts"]["credential_requirements"],
            len(payload["credential_requirements"]),
        )
        self.assertEqual(
            payload["counts"]["missing_requirements"],
            len(payload["missing_requirements"]),
        )
        asset = next(
            item
            for item in payload["assets"]["assets"]
            if item["asset_id"] == "asset_openai"
        )
        self.assertEqual(asset["credential_binding_count"], 1)
        seeded_requirements = [
            item
            for item in payload["credential_requirements"]
            if item["binding_id"] == "cred_openai_literal"
        ]
        self.assertEqual(len(seeded_requirements), 2)
        self.assertEqual(
            seeded_requirements[0]["binding_id"],
            "cred_openai_literal",
        )
        readiness = next(
            item
            for item in payload["readiness"]
            if item["target_id"] == "asset_openai"
        )
        self.assertEqual(readiness["status"], "setup_needed")
        seeded_consumers = [
            item
            for item in payload["consumer_bindings"]
            if item["asset_id"] == "asset_openai"
        ]
        self.assertEqual(len(seeded_consumers), 2)
        payload_text = json.dumps(payload, sort_keys=True)
        requirement_text = json.dumps(
            {
                "credential_requirements": payload["credential_requirements"],
                "consumer_bindings": payload["consumer_bindings"],
            },
            sort_keys=True,
        )
        self.assertNotIn("sk-real-secret", payload_text)
        self.assertNotIn("OPENAI_API_KEY", requirement_text)

    def test_ui_access_reads_tool_catalog_credential_requirements(self) -> None:
        self._seed_access_control_plane()
        self._seed_tool_catalog_requirement()

        response = self.client.get("/ui/access")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        rows = [
            item
            for item in payload["credential_requirements"]
            if item["consumer_module"] == "tool"
            and item["consumer_id"] == "catalog_credential_tool"
            and item["slot"] == "api_key"
        ]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["provider"], "openai")
        self.assertEqual(rows[0]["expected_kind"], "api_key")
        self.assertIsNone(rows[0]["binding_id"])
        self.assertTrue(rows[0]["missing"])
        self.assertFalse(rows[0]["ready"])

    def test_ui_access_reads_channel_profile_credential_requirements(self) -> None:
        self._seed_lark_access_bindings()
        profile_response = self.client.put(
            "/channels/profiles/lark",
            json={
                "enabled": True,
                "accounts": [
                    {
                        "account_id": "default",
                        "enabled": True,
                        "transport_mode": "long_connection",
                        "credential_bindings": {
                            "lark_app_id": "access-binding:lark-app-id",
                            "lark_app_secret": "access-binding:lark-app-secret",
                        },
                        "metadata": {"agent_id": "crxzipple"},
                    },
                ],
            },
        )
        self.assertEqual(profile_response.status_code, 200)

        response = self.client.get("/ui/access")

        self.assertEqual(response.status_code, 200)
        rows = [
            item
            for item in response.json()["credential_requirements"]
            if item["consumer_module"] == "channels"
            and item["consumer_id"] == "channels.lark.account:default"
        ]
        self.assertEqual({item["slot"] for item in rows}, {"lark_app_id", "lark_app_secret"})
        self.assertTrue(all(item["ready"] for item in rows))
        self.assertEqual(
            {item["slot"]: item["binding_id"] for item in rows},
            {
                "lark_app_id": "access-binding:lark-app-id",
                "lark_app_secret": "access-binding:lark-app-secret",
            },
        )

    def test_ui_access_merges_tool_catalog_requirement_with_settings_binding(
        self,
    ) -> None:
        self._seed_access_control_plane()
        self._seed_tool_catalog_requirement()

        action_response = self.client.post(
            "/access/actions",
            json={
                "action_id": "bind_catalog_tool_openai",
                "resource_kind": "credential_requirement",
                "target_id": "consumer:tool:tool:catalog_credential_tool:api_key",
                "intent": "bind_credential_requirement",
                "changes": {
                    "consumer_module": "tool",
                    "consumer_kind": "tool",
                    "consumer_id": "catalog_credential_tool",
                    "slot": "api_key",
                    "display_name": "Catalog Credential Tool",
                    "provider": "openai",
                    "expected_kind": "api_key",
                    "credential_binding_id": "cred_openai_literal",
                    "requirement_sets": [["openai:api_key(api_key)"]],
                    "status": "active",
                },
                "reason": "Bind catalog credential tool API key.",
                "actor": "unit-test",
            },
        )
        self.assertEqual(action_response.status_code, 200)

        response = self.client.get("/ui/access")

        self.assertEqual(response.status_code, 200)
        rows = [
            item
            for item in response.json()["credential_requirements"]
            if item["consumer_module"] == "tool"
            and item["consumer_id"] == "catalog_credential_tool"
            and item["slot"] == "api_key"
        ]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["binding_id"], "cred_openai_literal")
        self.assertTrue(rows[0]["ready"])
        self.assertFalse(rows[0]["missing"])

    def test_ui_access_requirement_catalog_is_redacted_in_overview(self) -> None:
        self._seed_access_control_plane()

        response = self.client.get("/ui/access")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        seeded_requirements = [
            item
            for item in payload["credential_requirements"]
            if item["binding_id"] == "cred_openai_literal"
        ]
        self.assertEqual(len(seeded_requirements), 2)
        self.assertTrue(all(item["ready"] for item in seeded_requirements))
        self.assertFalse(any(item["missing"] for item in seeded_requirements))
        row = seeded_requirements[0]
        self.assertEqual(row["expected_kind"], "api_key")
        self.assertEqual(row["slot"], "api_key")
        self.assertEqual(row["binding_id"], "cred_openai_literal")
        payload_text = json.dumps(payload, sort_keys=True)
        self.assertNotIn("sk-real-secret", payload_text)
        self.assertNotIn("OPENAI_API_KEY", payload_text)

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
        asset = next(
            item
            for item in list_payload["assets"]
            if item["asset_id"] == "asset_openai"
        )
        self.assertEqual(asset["credential_binding_count"], 1)
        self.assertEqual(detail_payload["asset_id"], "asset_openai")
        self.assertEqual(
            detail_payload["credential_bindings"][0]["source_ref"],
            "***",
        )
        payload_text = json.dumps(detail_payload, sort_keys=True)
        self.assertIn('"masked_preview": "***"', payload_text)
        self.assertNotIn("sk-real-secret", payload_text)
        self.assertNotIn("secret-from-credential-metadata", payload_text)

    def test_ui_access_audit_route_is_not_exposed_from_settings_surface(self) -> None:
        self._seed_access_control_plane()

        audits_response = self.client.get("/ui/access/audits")

        self.assertEqual(audits_response.status_code, 404)

    def test_ui_access_returns_degraded_json_when_dependency_missing(self) -> None:
        container = self.client.app.state.container
        previous_repository = container.registry._applications[
            AppKey.ACCESS_GOVERNANCE_REPOSITORY
        ]
        container.registry._applications[AppKey.ACCESS_GOVERNANCE_REPOSITORY] = None
        try:
            response = self.client.get("/ui/access")
        finally:
            container.registry._applications[
                AppKey.ACCESS_GOVERNANCE_REPOSITORY
            ] = previous_repository

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
        self.assertNotIn("/ui/access/audits", routes)


class _ToolCredentialRequirementDiscoveryAdapter(ToolDiscoveryAdapter):
    def discover(self, source):  # noqa: ANN001, ANN201
        consumer = AccessConsumerRef(
            consumer_id="catalog_credential_tool",
            module="tool",
            component="unit_test",
        )
        return ToolSourceDiscoveryResult.completed(
            source_id=source.source_id,
            candidates=(
                ToolFunctionCandidate(
                    stable_key="unit.catalog_credential_tool",
                    source_id=source.source_id,
                    function_id="catalog_credential_tool",
                    name="Catalog Credential Tool",
                    description="Declares an API key requirement from Tool catalog.",
                    input_schema={"type": "object", "properties": {}},
                    runtime_kind=ToolFunctionRuntimeKind.LOCAL,
                    handler_ref="catalog_credential_tool",
                    requirements=ToolFunctionRequirements(
                        credential_requirements=(
                            AccessCredentialRequirementSet(
                                requirement_set_id="catalog_credential_tool.default",
                                consumer=consumer,
                                requirements=(
                                    AccessCredentialRequirementDeclaration(
                                        requirement_id=(
                                            "catalog_credential_tool.api_key"
                                        ),
                                        consumer=consumer,
                                        slot=AccessCredentialSlotRef(
                                            slot="api_key",
                                            expected_kind=AccessCredentialKind.API_KEY,
                                        ),
                                        provider="openai",
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )
