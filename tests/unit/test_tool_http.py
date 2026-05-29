from __future__ import annotations

from tests.unit.http_test_support import *
from tests.unit.tool_runtime_test_support import process_next_background_tool_run
from crxzipple.modules.settings import CreateSettingsResourceInput
from crxzipple.modules.mobile.domain import (
    MobileActionCommand,
    MobileActionResult,
    MobileActionTarget,
)
from crxzipple.modules.tool.domain import (
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolExecutionTarget,
    ToolFunctionStatus,
    ToolMode,
    ToolRun,
    ToolRunResult,
)
from crxzipple.modules.tool.interfaces.dto import ToolRunDTO
from crxzipple.shared.access import (
    AccessConsumerRef,
    AccessCredentialKind,
    AccessCredentialRequirementDeclaration,
    AccessCredentialRequirementSet,
    AccessCredentialSlotRef,
    AccessCredentialTransport,
    AccessSetupFlowHint,
    AccessSetupFlowKind,
)


def _seed_sample_openapi_access_bindings(container) -> None:  # noqa: ANN001
    container.require(AppKey.SETTINGS_ACTION_SERVICE).create_resource(
        CreateSettingsResourceInput(
            resource_id="access_sample_openapi",
            resource_kind="access-assets",
            owner_module="settings",
            display_name="Sample OpenAPI credentials",
            payload={
                "credential_bindings": [
                    {
                        "binding_id": "binding.sample.query",
                        "binding_kind": "api_key",
                        "source_kind": "env",
                        "source_ref": "SAMPLE_API_KEY",
                    },
                    {
                        "binding_id": "binding.sample.bearer",
                        "binding_kind": "bearer_token",
                        "source_kind": "env",
                        "source_ref": "SAMPLE_BEARER_TOKEN",
                    },
                ],
                "metadata": {"source": "test_tool_http"},
            },
            reason="seed sample OpenAPI Access bindings",
            publish=True,
            source="unit_test",
        ),
    )


class ToolHttpTestCase(HttpModuleTestCase):
    def test_tool_run_dto_serializes_naive_datetimes_as_utc(self) -> None:
        tool_run = ToolRun(
            id="tool-run-naive-time",
            tool_id="echo",
            function_id="echo",
            function_revision=7,
            source_id="bundled.local_package.debug",
            source_revision=3,
            schema_hash="schema-hash-123",
            target=ToolExecutionTarget(
                mode=ToolMode.INLINE,
                strategy=ToolExecutionStrategy.ASYNC,
                environment=ToolEnvironment.LOCAL,
            ),
            metadata={"source": "unit-test"},
            created_at=datetime(2026, 4, 18, 7, 0, 0),
            started_at=datetime(2026, 4, 18, 7, 0, 1),
            completed_at=datetime(2026, 4, 18, 7, 0, 2),
            heartbeat_at=datetime(2026, 4, 18, 7, 0, 3),
            lease_expires_at=datetime(2026, 4, 18, 7, 0, 4),
            cancel_requested_at=datetime(2026, 4, 18, 7, 0, 5),
        )

        dto = ToolRunDTO.from_entity(tool_run)

        self.assertEqual(dto.created_at, "2026-04-18T07:00:00+00:00")
        self.assertEqual(dto.started_at, "2026-04-18T07:00:01+00:00")
        self.assertEqual(dto.completed_at, "2026-04-18T07:00:02+00:00")
        self.assertEqual(dto.heartbeat_at, "2026-04-18T07:00:03+00:00")
        self.assertEqual(dto.metadata, {"source": "unit-test"})
        self.assertEqual(dto.function_id, "echo")
        self.assertEqual(dto.function_revision, 7)
        self.assertEqual(dto.source_id, "bundled.local_package.debug")
        self.assertEqual(dto.source_revision, 3)
        self.assertEqual(dto.schema_hash, "schema-hash-123")

    def test_tool_endpoints_list_roots_and_tools(self) -> None:
        roots_response = self.client.get("/tools/roots")
        list_response = self.client.get("/tools")

        self.assertEqual(roots_response.status_code, 200)
        self.assertTrue(len(roots_response.json()) >= 2)
        self.assertEqual(list_response.status_code, 200)
        tool_ids = [item["id"] for item in list_response.json()]
        self.assertIn("echo", tool_ids)
        self.assertIn("memory_search", tool_ids)
        self.assertIn("mobile_script", tool_ids)
        self.assertIn("mobile_snapshot", tool_ids)
        self.assertIn("mobile_screenshot", tool_ids)
        self.assertIn("session_status", tool_ids)
        self.assertIn("sessions_list", tool_ids)
        self.assertIn("sessions_history", tool_ids)
        self.assertIn("sessions_send", tool_ids)
        self.assertIn("sessions_spawn", tool_ids)
        self.assertIn("subagents", tool_ids)
        self.assertIn("sessions_stop", tool_ids)
        self.assertIn("sessions_yield", tool_ids)
        self.assertNotIn("mobile_session", tool_ids)
        memory_tool = next(item for item in list_response.json() if item["id"] == "memory_search")
        self.assertEqual(memory_tool["context_requirements"], ["agent_id"])

    def test_tool_source_endpoints_manage_sources_and_discovery_history(self) -> None:
        sources_response = self.client.get("/tools/sources")

        self.assertEqual(sources_response.status_code, 200)
        sources_payload = sources_response.json()
        source_ids = [item["source_id"] for item in sources_payload]
        self.assertIn("bundled.local_package.debug", source_ids)
        debug_source = next(
            item
            for item in sources_payload
            if item["source_id"] == "bundled.local_package.debug"
        )
        self.assertIn("config", debug_source)
        self.assertIn("runtime_requirements", debug_source)

        history_response = self.client.get(
            "/tools/sources/bundled.local_package.debug/discovery-runs",
        )

        self.assertEqual(history_response.status_code, 200)
        history_payload = history_response.json()
        self.assertGreaterEqual(len(history_payload), 1)
        self.assertEqual(history_payload[0]["status"], "completed")

        refresh_response = self.client.post(
            "/tools/sources/bundled.local_package.debug/refresh",
        )

        self.assertEqual(refresh_response.status_code, 200)
        self.assertEqual(refresh_response.json()["source"]["status"], "active")
        self.assertEqual(refresh_response.json()["discovery"]["status"], "completed")

        disable_response = self.client.post(
            "/tools/sources/bundled.local_package.debug/disable",
        )
        self.assertEqual(disable_response.status_code, 200)
        self.assertEqual(disable_response.json()["status"], "disabled")

        restore_response = self.client.post(
            "/tools/sources/bundled.local_package.debug/restore",
        )
        self.assertEqual(restore_response.status_code, 200)
        self.assertEqual(restore_response.json()["status"], "active")

    def test_tool_source_endpoints_create_and_update_configured_source(self) -> None:
        payload = {
            "source_id": "configured.openapi.http",
            "kind": "openapi",
            "display_name": "HTTP OpenAPI",
            "description": "Created from the owner API.",
            "config": {
                "source": "configured_tool_provider",
                "package_kind": "openapi",
                "provider": {
                    "name": "http_sample",
                    "spec_location": "https://example.test/openapi.json",
                },
            },
            "runtime_requirements": ["bounded_network.http"],
        }

        create_response = self.client.post("/tools/sources", json=payload)

        self.assertEqual(create_response.status_code, 200)
        create_payload = create_response.json()
        self.assertEqual(create_payload["source_id"], "configured.openapi.http")
        self.assertEqual(create_payload["status"], "active")
        self.assertIsNone(create_payload["last_discovery_status"])

        history_response = self.client.get(
            "/tools/sources/configured.openapi.http/discovery-runs",
        )
        self.assertEqual(history_response.status_code, 200)
        self.assertEqual(history_response.json(), [])

        update_payload = {
            **payload,
            "display_name": "Renamed HTTP OpenAPI",
            "config": {
                **payload["config"],
                "provider": {
                    "name": "http_sample",
                    "spec_location": "https://example.test/renamed-openapi.json",
                },
            },
        }
        update_response = self.client.put(
            "/tools/sources/configured.openapi.http",
            json=update_payload,
        )

        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json()["display_name"], "Renamed HTTP OpenAPI")
        self.assertEqual(
            update_response.json()["config"]["provider"]["spec_location"],
            "https://example.test/renamed-openapi.json",
        )
        history_after_update_response = self.client.get(
            "/tools/sources/configured.openapi.http/discovery-runs",
        )
        self.assertEqual(history_after_update_response.status_code, 200)
        self.assertEqual(history_after_update_response.json(), [])

    def test_tool_function_endpoints_list_and_toggle_function_enablement(self) -> None:
        functions_response = self.client.get(
            "/tools/functions",
            params={"source_id": "bundled.local_package.debug"},
        )

        self.assertEqual(functions_response.status_code, 200)
        functions_payload = functions_response.json()
        self.assertTrue(functions_payload)
        function_payload = functions_payload[0]
        function_id = function_payload["function_id"]
        self.assertTrue(function_payload["enabled"])
        self.assertIn("parameters", function_payload)
        self.assertIn("credential_requirements", function_payload)
        self.assertIn("access_requirement_sets", function_payload)
        self.assertIn("runtime_requirement_sets", function_payload)
        self.assertIn("context_requirements", function_payload)
        self.assertIn("execution_policy", function_payload)
        self.assertIn("execution_support", function_payload)
        self.assertIn("runtime_key", function_payload)

        function_response = self.client.get(f"/tools/functions/{function_id}")
        self.assertEqual(function_response.status_code, 200)
        self.assertEqual(function_response.json()["function_id"], function_id)
        self.assertEqual(
            function_response.json()["credential_requirements"],
            function_payload["credential_requirements"],
        )

        disable_response = self.client.post(f"/tools/functions/{function_id}/disable")
        self.assertEqual(disable_response.status_code, 200)
        self.assertFalse(disable_response.json()["enabled"])

        enable_response = self.client.post(f"/tools/functions/{function_id}/enable")
        self.assertEqual(enable_response.status_code, 200)
        self.assertTrue(enable_response.json()["enabled"])

    def test_tool_readiness_endpoint_reports_context_requirements(self) -> None:
        missing_response = self.client.get("/tools/memory_search/readiness")
        ready_response = self.client.get(
            "/tools/memory_search/readiness",
            params={"agent_id": "assistant"},
        )

        self.assertEqual(missing_response.status_code, 200)
        missing_payload = missing_response.json()
        self.assertFalse(missing_payload["ready"])
        self.assertEqual(missing_payload["status"], "setup_needed")
        self.assertEqual(missing_payload["checks"][0]["category"], "context")
        self.assertEqual(missing_payload["checks"][0]["requirement"], "agent_id")
        self.assertEqual(ready_response.status_code, 200)
        self.assertTrue(ready_response.json()["ready"])

    def test_tool_provider_backend_endpoints_list_catalog_backends(self) -> None:
        backends_response = self.client.get("/tools/provider-backends")

        self.assertEqual(backends_response.status_code, 200)
        backends_payload = backends_response.json()
        backend_ids = [item["backend_id"] for item in backends_payload]
        self.assertIn("openai_image.default", backend_ids)
        backend = next(
            item
            for item in backends_payload
            if item["backend_id"] == "openai_image.default"
        )
        self.assertEqual(backend["capability"], "image_generation")
        self.assertEqual(backend["status"], "active")
        self.assertTrue(backend["enabled"])
        self.assertIn("status", backend["readiness"])
        self.assertEqual(backend["runtime_ref"]["ref"], "openai_image_generate")
        self.assertEqual(
            backend["credential_requirements"][0]["requirements"][0]["slot"][
                "binding_id"
            ],
            "openai-api-key",
        )

        detail_response = self.client.get(
            "/tools/provider-backends/openai_image.default",
        )

        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["backend_id"], "openai_image.default")
        self.assertIn("readiness", detail_response.json())

    def test_tool_function_disabled_execution_returns_structured_catalog_error(
        self,
    ) -> None:
        functions_response = self.client.get(
            "/tools/functions",
            params={"source_id": "bundled.local_package.debug"},
        )
        self.assertEqual(functions_response.status_code, 200)
        function_id = functions_response.json()[0]["function_id"]

        disable_response = self.client.post(f"/tools/functions/{function_id}/disable")
        self.assertEqual(disable_response.status_code, 200)

        execute_response = self.client.post(
            f"/tools/{function_id}/runs",
            json={"arguments": {"message": "blocked"}},
        )

        self.assertEqual(execute_response.status_code, 409)
        detail = execute_response.json()["detail"]
        self.assertEqual(detail["code"], "tool_function_disabled")
        self.assertEqual(detail["category"], "catalog")
        self.assertEqual(detail["function_id"], function_id)
        self.assertEqual(detail["function_status"], "active")
        self.assertFalse(detail["enabled"])
        self.assertEqual(
            self.client.app.state.container.require(AppKey.TOOL_SERVICE).list_tool_runs(
                tool_id=function_id,
            ),
            [],
        )

    def test_tool_function_stale_and_deprecated_execution_returns_structured_catalog_error(
        self,
    ) -> None:
        functions_response = self.client.get(
            "/tools/functions",
            params={"source_id": "bundled.local_package.debug"},
        )
        self.assertEqual(functions_response.status_code, 200)
        function_id = functions_response.json()[0]["function_id"]
        container = self.client.app.state.container

        with container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
            function = uow.tool_functions.get(function_id)
            self.assertIsNotNone(function)
            function.status = ToolFunctionStatus.STALE
            function.revision += 1
            uow.tool_functions.upsert(function)
            uow.commit()

        stale_detail_response = self.client.get(f"/tools/functions/{function_id}")
        self.assertEqual(stale_detail_response.status_code, 200)
        self.assertEqual(stale_detail_response.json()["status"], "stale")
        self.assertIn("parameters", stale_detail_response.json())

        stale_response = self.client.post(
            f"/tools/{function_id}/runs",
            json={"arguments": {"message": "blocked"}},
        )

        self.assertEqual(stale_response.status_code, 409)
        stale_detail = stale_response.json()["detail"]
        self.assertEqual(stale_detail["code"], "tool_function_not_executable")
        self.assertEqual(stale_detail["category"], "catalog")
        self.assertEqual(stale_detail["function_id"], function_id)
        self.assertEqual(stale_detail["function_status"], "stale")

        with container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
            function = uow.tool_functions.get(function_id)
            self.assertIsNotNone(function)
            function.status = ToolFunctionStatus.DEPRECATED
            function.revision += 1
            uow.tool_functions.upsert(function)
            uow.commit()

        deprecated_response = self.client.post(
            f"/tools/{function_id}/runs",
            json={"arguments": {"message": "blocked"}},
        )

        self.assertEqual(deprecated_response.status_code, 409)
        deprecated_detail = deprecated_response.json()["detail"]
        self.assertEqual(deprecated_detail["code"], "tool_function_not_executable")
        self.assertEqual(deprecated_detail["category"], "catalog")
        self.assertEqual(deprecated_detail["function_id"], function_id)
        self.assertEqual(deprecated_detail["function_status"], "deprecated")
        self.assertEqual(
            container.require(AppKey.TOOL_SERVICE).list_tool_runs(tool_id=function_id),
            [],
        )

    def test_tool_function_policy_endpoint_updates_owner_policy_fields(self) -> None:
        functions_response = self.client.get(
            "/tools/functions",
            params={"source_id": "bundled.local_package.debug"},
        )
        self.assertEqual(functions_response.status_code, 200)
        function_id = functions_response.json()[0]["function_id"]

        update_response = self.client.put(
            f"/tools/functions/{function_id}/policy",
            json={
                "trust_policy": {"level": "trusted"},
                "approval_policy": {"requires_approval": False},
                "credential_binding_overrides": {"api_key": "debug-binding"},
                "required_effect_overrides": ["debug.effect"],
            },
        )

        self.assertEqual(update_response.status_code, 200)
        payload = update_response.json()
        self.assertEqual(payload["trust_policy"], {"level": "trusted"})
        self.assertEqual(payload["approval_policy"], {"requires_approval": False})
        self.assertEqual(
            payload["credential_binding_overrides"],
            {"api_key": "debug-binding"},
        )
        self.assertEqual(payload["required_effect_overrides"], ["debug.effect"])

    def test_tool_runtime_endpoints_execute_and_fetch_runs(self) -> None:
        execute_response = self.client.post(
            "/tools/echo/runs",
            json={"arguments": {"message": "from http"}},
        )

        self.assertEqual(execute_response.status_code, 201)
        run_payload = execute_response.json()
        self.assertEqual(run_payload["tool_id"], "echo")
        self.assertEqual(run_payload["function_id"], "echo")
        self.assertEqual(run_payload["source_id"], "bundled.local_package.debug")
        self.assertIsNotNone(run_payload["function_revision"])
        self.assertIsNotNone(run_payload["source_revision"])
        self.assertIsNotNone(run_payload["schema_hash"])
        self.assertEqual(run_payload["status"], "succeeded")
        self.assertEqual(run_payload["output_payload"]["message"], "from http")

        list_runs_response = self.client.get("/tools/echo/runs")

        self.assertEqual(list_runs_response.status_code, 200)
        list_payload = list_runs_response.json()
        self.assertEqual(len(list_payload), 1)
        self.assertEqual(list_payload[0]["id"], run_payload["id"])

        get_run_response = self.client.get(f"/tools/runs/{run_payload['id']}")

        self.assertEqual(get_run_response.status_code, 200)
        self.assertEqual(get_run_response.json()["id"], run_payload["id"])
        self.assertEqual(
            get_run_response.json()["schema_hash"],
            run_payload["schema_hash"],
        )

    def test_tool_readiness_endpoint_blocks_missing_access_before_run_creation(self) -> None:
        previous_token = os.environ.get("CRXZIPPLE_HTTP_MISSING_TOKEN")
        os.environ.pop("CRXZIPPLE_HTTP_MISSING_TOKEN", None)
        try:
            container = self.client.app.state.container
            seed_catalog_tool(
                container,
                tool_id="private_http_tool",
                name="Private HTTP Tool",
                description="Tool gated by a missing env credential.",
                access_requirement_sets=(("env:CRXZIPPLE_HTTP_MISSING_TOKEN",),),
            )

            readiness_response = self.client.get("/tools/private_http_tool/readiness")

            self.assertEqual(readiness_response.status_code, 200)
            readiness_payload = readiness_response.json()
            self.assertFalse(readiness_payload["ready"])
            self.assertEqual(readiness_payload["status"], "setup_needed")
            self.assertTrue(readiness_payload["setup_available"])

            execute_response = self.client.post(
                "/tools/private_http_tool/runs",
                json={"arguments": {"message": "should not run"}},
            )

            self.assertEqual(execute_response.status_code, 409)
            detail = execute_response.json()["detail"]
            self.assertEqual(detail["code"], "access_not_ready")
            self.assertEqual(detail["category"], "access")
            self.assertIn("requires access setup", detail["message"])
            self.assertEqual(detail["readiness"]["status"], "setup_needed")
            self.assertTrue(detail["readiness"]["setup_available"])
            self.assertEqual(
                detail["readiness"]["checks"][0]["requirement"],
                "env:CRXZIPPLE_HTTP_MISSING_TOKEN",
            )
            self.assertEqual(
                container.require(AppKey.TOOL_SERVICE).list_tool_runs(
                    tool_id="private_http_tool",
                ),
                [],
            )
        finally:
            if previous_token is None:
                os.environ.pop("CRXZIPPLE_HTTP_MISSING_TOKEN", None)
            else:
                os.environ["CRXZIPPLE_HTTP_MISSING_TOKEN"] = previous_token

    def test_tool_readiness_endpoint_blocks_missing_oauth_account_before_run_creation(
        self,
    ) -> None:
        container = self.client.app.state.container
        container.require(AppKey.SETTINGS_ACTION_SERVICE).create_resource(
            CreateSettingsResourceInput(
                resource_id="access_oauth_missing_account_test",
                resource_kind="access-assets",
                owner_module="settings",
                display_name="Missing OAuth account test binding",
                payload={
                    "credential_bindings": [
                        {
                            "binding_id": "codex-oauth-missing-account",
                            "binding_kind": "oauth2_account",
                            "source_kind": "oauth_account",
                            "source_ref": "openai-codex:missing-account",
                            "masked_preview": "oauth:openai-codex:missing-account",
                        },
                    ],
                    "metadata": {"source": "test_tool_http"},
                },
                reason="seed missing OAuth account binding",
                publish=True,
                source="unit_test",
            ),
        )
        consumer = AccessConsumerRef(
            consumer_id="oauth_gated_tool",
            module="tool",
            component="unit_test",
        )
        seed_catalog_tool(
            container,
            tool_id="oauth_gated_tool",
            name="OAuth Gated Tool",
            description="Tool gated by a missing OAuth account.",
            credential_requirements=(
                AccessCredentialRequirementSet(
                    requirement_set_id="oauth_gated_tool.oauth",
                    consumer=consumer,
                    requirements=(
                        AccessCredentialRequirementDeclaration(
                            requirement_id="oauth_gated_tool.oauth.account",
                            consumer=consumer,
                            slot=AccessCredentialSlotRef(
                                slot="oauth_account",
                                expected_kind=AccessCredentialKind.OAUTH2_ACCOUNT,
                                binding_id="codex-oauth-missing-account",
                            ),
                            provider="openai-codex",
                            transport=AccessCredentialTransport.OAUTH_AUTHORIZATION_HEADER,
                            setup_flow_hint=AccessSetupFlowHint(
                                flow_kind=AccessSetupFlowKind.BROWSER_OAUTH,
                                provider="openai-codex",
                            ),
                        ),
                    ),
                ),
            ),
        )

        readiness_response = self.client.get("/tools/oauth_gated_tool/readiness")

        self.assertEqual(readiness_response.status_code, 200)
        readiness_payload = readiness_response.json()
        self.assertFalse(readiness_payload["ready"])
        self.assertEqual(readiness_payload["status"], "setup_needed")
        self.assertTrue(readiness_payload["setup_available"])
        self.assertEqual(
            readiness_payload["checks"][0]["expected_kind"],
            "oauth2_account",
        )
        self.assertIn("OAuth account", readiness_payload["reason"])

        execute_response = self.client.post(
            "/tools/oauth_gated_tool/runs",
            json={"arguments": {"message": "should not run"}},
        )

        self.assertEqual(execute_response.status_code, 409)
        detail = execute_response.json()["detail"]
        self.assertEqual(detail["code"], "access_not_ready")
        self.assertEqual(detail["category"], "access")
        self.assertIn("requires access setup", detail["message"])
        self.assertEqual(detail["readiness"]["status"], "setup_needed")
        self.assertEqual(
            detail["readiness"]["checks"][0]["expected_kind"],
            "oauth2_account",
        )
        self.assertIn("OAuth account", detail["readiness"]["reason"])
        self.assertEqual(
            container.require(AppKey.TOOL_SERVICE).list_tool_runs(
                tool_id="oauth_gated_tool",
            ),
            [],
        )

    def test_tool_readiness_endpoint_blocks_missing_runtime_daemon_before_run_creation(
        self,
    ) -> None:
        container = self.client.app.state.container
        seed_catalog_tool(
            container,
            tool_id="browser_runtime_gated_tool",
            name="Browser Runtime Gated Tool",
            description="Tool gated by browser daemon readiness.",
            runtime_requirement_sets=(("daemon-group:browser",),),
            handler=lambda _arguments: ToolRunResult.text(
                "ok",
                details={"ok": True},
            ),
        )

        readiness_response = self.client.get("/tools/browser_runtime_gated_tool/readiness")

        self.assertEqual(readiness_response.status_code, 200)
        readiness_payload = readiness_response.json()
        self.assertFalse(readiness_payload["ready"])
        self.assertEqual(readiness_payload["status"], "setup_needed")
        self.assertTrue(readiness_payload["setup_available"])
        self.assertEqual(readiness_payload["checks"][0]["category"], "runtime")
        self.assertEqual(
            readiness_payload["checks"][0]["requirement"],
            "daemon-group:browser",
        )

        blocked_response = self.client.post(
            "/tools/browser_runtime_gated_tool/runs",
            json={"arguments": {"message": "should not run"}},
        )

        self.assertEqual(blocked_response.status_code, 409)
        detail = blocked_response.json()["detail"]
        self.assertEqual(detail["code"], "tool_runtime_not_ready")
        self.assertEqual(detail["category"], "runtime")
        self.assertIn("requires runtime setup", detail["message"])
        self.assertEqual(detail["readiness"]["status"], "setup_needed")
        self.assertEqual(
            detail["readiness"]["checks"][0]["requirement"],
            "daemon-group:browser",
        )
        self.assertEqual(
            container.require(AppKey.TOOL_SERVICE).list_tool_runs(
                tool_id="browser_runtime_gated_tool",
            ),
            [],
        )

        container.require(AppKey.DAEMON_SERVICE).report_service_ready(
            service_key="host:browser:crxzipple",
        )

        ready_response = self.client.get("/tools/browser_runtime_gated_tool/readiness")
        self.assertEqual(ready_response.status_code, 200)
        self.assertTrue(ready_response.json()["ready"])

        execute_response = self.client.post(
            "/tools/browser_runtime_gated_tool/runs",
            json={"arguments": {"message": "runs now"}},
        )

        self.assertEqual(execute_response.status_code, 201)
        self.assertEqual(execute_response.json()["status"], "succeeded")

    def test_missing_tool_run_returns_404_json(self) -> None:
        response = self.client.get("/tools/runs/missing-tool-run")

        self.assertEqual(response.status_code, 404)
        self.assertIn("application/json", response.headers["content-type"])
        self.assertEqual(
            response.json(),
            {"detail": "Tool run 'missing-tool-run' was not found."},
        )

    def test_tool_catalog_endpoints_list_sources_and_functions(self) -> None:
        sources_response = self.client.get("/tools/sources")
        functions_response = self.client.get("/tools/functions")

        self.assertEqual(sources_response.status_code, 200)
        self.assertIn(
            "bundled.local_package.debug",
            [item["source_id"] for item in sources_response.json()],
        )
        self.assertEqual(functions_response.status_code, 200)
        self.assertIn(
            "echo",
            [item["function_id"] for item in functions_response.json()],
        )

    def test_mobile_tool_runtime_endpoint_executes_local_mobile_handler(self) -> None:
        container = self.client.app.state.container
        captured_requests: list[object] = []

        def _execute(request):  # noqa: ANN001, ANN202
            captured_requests.append(request)
            return MobileActionResult(
                ok=True,
                device_name=request.device_name,
                message="Captured mobile UI snapshot.",
                command=MobileActionCommand(
                    device_name=request.device_name,
                    kind=request.kind,
                    target=MobileActionTarget(
                        ref=request.ref,
                        selector=request.selector,
                    ),
                    payload=request.payload,
                    timeout_ms=request.timeout_ms,
                ),
                value={
                    "format": "interactive_text",
                    "snapshot": '- android.widget.EditText "To" [ref=m1]',
                    "text": "To\nSubject\nMessage Body",
                },
            )

        with patch.object(
            type(container.require(AppKey.MOBILE_FACADE)),
            "execute",
            autospec=True,
            side_effect=lambda _self, request: _execute(request),
        ):
            execute_response = self.client.post(
                "/tools/mobile_snapshot/runs",
                json={
                    "arguments": {
                        "device": "pixel",
                        "format": "interactive_text",
                    }
                },
            )

        self.assertEqual(execute_response.status_code, 201)
        payload = execute_response.json()
        self.assertEqual(payload["tool_id"], "mobile_snapshot")
        self.assertEqual(payload["status"], "succeeded")
        self.assertEqual(payload["result"]["content"][0]["type"], "text")
        self.assertIn("Message Body", payload["result"]["content"][0]["text"])

    def test_openapi_provider_endpoints_discover_and_execute_remote_tools(self) -> None:
        server = SampleApiServer()
        server.start()
        harness = SqliteTestHarness()
        previous_api_key = os.environ.get("SAMPLE_API_KEY")
        previous_bearer_token = os.environ.get("SAMPLE_BEARER_TOKEN")
        os.environ["SAMPLE_API_KEY"] = "sample-api-key"
        os.environ["SAMPLE_BEARER_TOKEN"] = "sample-bearer-token"
        settings = replace(
            load_settings(),
            database_url=harness.database_url,
            authorization_enabled=False,
            tool_openapi_providers=(
                OpenApiProviderSettings(
                    name="sample_api",
                    spec_location=openapi_fixture_path("sample_openapi.json"),
                    base_url=server.base_url,
                    description="Sample OpenAPI provider",
                    timeout_seconds=5,
                    credential_bindings=(
                        OpenApiCredentialBinding(
                            scheme_name="ApiKeyQuery",
                            credential_binding_id="binding.sample.query",
                        ),
                        OpenApiCredentialBinding(
                            scheme_name="BearerAuth",
                            credential_binding_id="binding.sample.bearer",
                        ),
                    ),
                ),
            ),
        )

        harness.initialize_schema(settings=settings)
        client = TestClient(
            create_app(
                settings=settings,
                database_url=harness.database_url,
            ),
        )
        _seed_sample_openapi_access_bindings(client.app.state.container)

        try:
            list_response = client.get("/tools")
            self.assertEqual(list_response.status_code, 200)
            listed_tools = [
                item
                for item in list_response.json()
                if item["id"].startswith("sample_api.")
            ]
            self.assertEqual(
                [item["id"] for item in listed_tools],
                ["sample_api.echo_message", "sample_api.search_docs"],
            )

            echo_response = client.post(
                "/tools/sample_api.echo_message/runs",
                json={
                    "arguments": {"message": "http", "uppercase": True},
                    "environment": "remote",
                },
            )
            self.assertEqual(echo_response.status_code, 201)
            self.assertEqual(
                echo_response.json()["output_payload"]["message"],
                "HTTP",
            )
            self.assertIn(
                "api_key=%5Bredacted%5D",
                echo_response.json()["result"]["metadata"]["request"]["url"],
            )
            self.assertNotIn(
                "sample-api-key",
                echo_response.json()["result"]["metadata"]["request"]["url"],
            )

            execute_response = client.post(
                "/tools/sample_api.search_docs/runs",
                json={
                    "arguments": {"body": {"query": "tooling", "limit": 3}},
                    "environment": "remote",
                },
            )
            self.assertEqual(execute_response.status_code, 201)
            self.assertEqual(
                execute_response.json()["output_payload"]["query"],
                "tooling",
            )
        finally:
            if previous_api_key is None:
                os.environ.pop("SAMPLE_API_KEY", None)
            else:
                os.environ["SAMPLE_API_KEY"] = previous_api_key
            if previous_bearer_token is None:
                os.environ.pop("SAMPLE_BEARER_TOKEN", None)
            else:
                os.environ["SAMPLE_BEARER_TOKEN"] = previous_bearer_token
            client.close()
            client.app.state.container.close()
            harness.close()
            server.close()

    def test_mcp_provider_endpoints_discover_and_execute_remote_tools(self) -> None:
        harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            database_url=harness.database_url,
            tool_mcp_providers=(
                McpProviderSettings(
                    name="sample_mcp",
                    command=(sys.executable, fixture_path("mcp_sample_server.py")),
                    description="Sample MCP provider",
                    timeout_seconds=5,
                ),
            ),
        )

        harness.initialize_schema(settings=settings)
        client = TestClient(
            create_app(
                settings=settings,
                database_url=harness.database_url,
            ),
        )

        try:
            list_response = client.get("/tools")
            self.assertEqual(list_response.status_code, 200)
            listed_tools = [
                item
                for item in list_response.json()
                if item["id"].startswith("sample_mcp.")
            ]
            self.assertEqual(
                [item["id"] for item in listed_tools],
                ["sample_mcp.echo", "sample_mcp.sum"],
            )

            execute_response = client.post(
                "/tools/sample_mcp.sum/runs",
                json={
                    "arguments": {"left": 6, "right": 4},
                    "environment": "remote",
                },
            )
            self.assertEqual(execute_response.status_code, 201)
            self.assertEqual(
                execute_response.json()["output_payload"]["content"]["total"],
                10,
            )
        finally:
            client.close()
            client.app.state.container.close()
            harness.close()

    def test_tool_runtime_endpoint_executes_thread_strategy(self) -> None:
        execute_response = self.client.post(
            "/tools/echo/runs",
            json={
                "arguments": {"message": "thread http"},
                "strategy": "thread",
            },
        )

        self.assertEqual(execute_response.status_code, 201)
        run_payload = execute_response.json()
        self.assertEqual(run_payload["status"], "succeeded")
        self.assertEqual(run_payload["output_payload"]["message"], "thread http")
        self.assertEqual(run_payload["result"]["metadata"]["process_id"], os.getpid())
        self.assertNotEqual(
            run_payload["result"]["metadata"]["thread_ident"],
            threading.get_ident(),
        )

    def test_tool_background_runtime_endpoint_eventually_succeeds(self) -> None:
        execute_response = self.client.post(
            "/tools/echo/runs",
            json={
                "arguments": {"message": "background http"},
                "mode": "background",
            },
        )

        self.assertEqual(execute_response.status_code, 201)
        run_payload = execute_response.json()
        self.assertEqual(run_payload["status"], "queued")

        deadline = time.monotonic() + 5
        fetched = None
        while time.monotonic() < deadline:
            worker_response = process_next_background_tool_run(
                self.client.app.state.container,
                worker_id="http-test-worker",
            )
            get_run_response = self.client.get(f"/tools/runs/{run_payload['id']}")
            self.assertEqual(get_run_response.status_code, 200)
            fetched = get_run_response.json()
            if fetched["status"] == "succeeded" or worker_response is not None:
                if fetched["status"] == "succeeded":
                    break
            if fetched["status"] == "succeeded":
                break
            time.sleep(0.05)

        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["status"], "succeeded")
        self.assertEqual(fetched["output_payload"]["message"], "background http")
        self.assertEqual(fetched["result"]["metadata"]["environment"], "local")
        self.assertEqual(fetched["attempt_count"], 1)
        self.assertEqual(fetched["worker_id"], "http-test-worker")

    def test_tool_background_thread_runtime_endpoint_eventually_succeeds(self) -> None:
        execute_response = self.client.post(
            "/tools/echo/runs",
            json={
                "arguments": {"message": "background thread http"},
                "mode": "background",
                "strategy": "thread",
            },
        )

        self.assertEqual(execute_response.status_code, 201)
        run_payload = execute_response.json()
        self.assertEqual(run_payload["status"], "queued")
        self.assertEqual(run_payload["target"]["strategy"], "thread")

        deadline = time.monotonic() + 5
        fetched = None
        while time.monotonic() < deadline:
            process_next_background_tool_run(
                self.client.app.state.container,
                worker_id="http-thread-worker",
            )
            get_run_response = self.client.get(f"/tools/runs/{run_payload['id']}")
            self.assertEqual(get_run_response.status_code, 200)
            fetched = get_run_response.json()
            if fetched["status"] == "succeeded":
                break
            time.sleep(0.05)

        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["status"], "succeeded")
        self.assertEqual(
            fetched["output_payload"]["message"],
            "background thread http",
        )
        self.assertEqual(fetched["target"]["strategy"], "thread")
        self.assertEqual(fetched["worker_id"], "http-thread-worker")
        self.assertEqual(fetched["result"]["metadata"]["process_id"], os.getpid())
        self.assertNotEqual(
            fetched["result"]["metadata"]["thread_ident"],
            threading.get_ident(),
        )

    def test_tool_run_can_be_cancelled_via_http(self) -> None:
        execute_response = self.client.post(
            "/tools/echo/runs",
            json={
                "arguments": {"message": "cancel http"},
                "mode": "background",
            },
        )
        self.assertEqual(execute_response.status_code, 201)
        run_payload = execute_response.json()

        cancel_response = self.client.post(f"/tools/runs/{run_payload['id']}/cancel")
        self.assertEqual(cancel_response.status_code, 200)
        cancel_payload = cancel_response.json()
        self.assertEqual(cancel_payload["status"], "cancelled")
        self.assertIsNotNone(cancel_payload["cancel_requested_at"])

    def test_tool_run_can_be_retried_via_http(self) -> None:
        failed_run = ToolRun.create(
            run_id="http-failed-tool-run",
            tool_id="echo",
            input_payload={"message": "retry http"},
            metadata={"source": "retry-test"},
            invocation_context_payload={"trace_id": "trace-retry-http"},
            target=ToolExecutionTarget(mode=ToolMode.INLINE),
        )
        failed_run.start()
        failed_run.fail("failed before retry")
        with self.client.app.state.container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
            uow.tool_runs.add(failed_run)
            uow.commit()

        retry_response = self.client.post(f"/tools/runs/{failed_run.id}/retry")

        self.assertEqual(retry_response.status_code, 201)
        retry_payload = retry_response.json()
        self.assertNotEqual(retry_payload["id"], failed_run.id)
        self.assertEqual(retry_payload["tool_id"], "echo")
        self.assertEqual(retry_payload["status"], "succeeded")
        self.assertEqual(retry_payload["metadata"], {"source": "retry-test"})
        self.assertEqual(retry_payload["output_payload"]["message"], "retry http")

    def test_tool_runtime_endpoint_executes_sandbox_adapter(self) -> None:
        seed_catalog_tool(
            self.client.app.state.container,
            tool_id="sandbox_echo",
            name="Sandbox Echo",
            description="Executes through the sandbox adapter",
            supported_environments=(ToolEnvironment.SANDBOX,),
            runtime_key="sandbox.echo",
        )

        execute_response = self.client.post(
            "/tools/sandbox_echo/runs",
            json={
                "arguments": {"message": "sandbox http"},
                "environment": "sandbox",
            },
        )

        self.assertEqual(execute_response.status_code, 201)
        run_payload = execute_response.json()
        self.assertEqual(run_payload["status"], "succeeded")
        self.assertEqual(run_payload["output_payload"]["message"], "sandbox http")
        self.assertEqual(run_payload["result"]["metadata"]["environment"], "sandbox")


if __name__ == "__main__":
    unittest.main()
