from __future__ import annotations

from tests.unit.http_test_support import *


class ToolHttpTestCase(HttpModuleTestCase):
    def test_tool_endpoints_list_roots_and_tools(self) -> None:
        roots_response = self.client.get("/tools/roots")
        list_response = self.client.get("/tools")

        self.assertEqual(roots_response.status_code, 200)
        self.assertTrue(len(roots_response.json()) >= 2)
        self.assertEqual(list_response.status_code, 200)
        tool_ids = [item["id"] for item in list_response.json()]
        self.assertIn("echo", tool_ids)
        self.assertIn("memory_search", tool_ids)

    def test_tool_runtime_endpoints_discover_execute_and_fetch_runs(self) -> None:
        discover_response = self.client.post("/tools/discover-local")

        self.assertEqual(discover_response.status_code, 200)
        self.assertEqual(discover_response.json()[0]["id"], "echo")

        execute_response = self.client.post(
            "/tools/echo/runs",
            json={"arguments": {"message": "from http"}},
        )

        self.assertEqual(execute_response.status_code, 201)
        run_payload = execute_response.json()
        self.assertEqual(run_payload["tool_id"], "echo")
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

    def test_tool_provider_endpoints_list_and_discover_tools(self) -> None:
        providers_response = self.client.get("/tools/providers")

        self.assertEqual(providers_response.status_code, 200)
        providers_payload = providers_response.json()
        self.assertEqual(
            [item["name"] for item in providers_payload],
            ["local_builtin", "local_filesystem"],
        )

        discover_response = self.client.post(
            "/tools/discover",
            params={"provider": "local_builtin"},
        )

        self.assertEqual(discover_response.status_code, 200)
        discover_payload = discover_response.json()
        self.assertEqual([item["id"] for item in discover_payload], ["echo"])

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
                            source="env:SAMPLE_API_KEY",
                        ),
                        OpenApiCredentialBinding(
                            scheme_name="BearerAuth",
                            source="env:SAMPLE_BEARER_TOKEN",
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

        try:
            providers_response = client.get("/tools/providers")
            self.assertEqual(providers_response.status_code, 200)
            self.assertEqual(
                [item["name"] for item in providers_response.json()],
                ["local_builtin", "local_filesystem", "sample_api"],
            )

            discover_response = client.post(
                "/tools/discover",
                params={"provider": "sample_api"},
            )
            self.assertEqual(discover_response.status_code, 200)
            self.assertEqual(
                [item["id"] for item in discover_response.json()],
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
                "api_key=sample-api-key",
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
            client.app.state.container.engine.dispose()
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
            providers_response = client.get("/tools/providers")
            self.assertEqual(providers_response.status_code, 200)
            self.assertEqual(
                [item["name"] for item in providers_response.json()],
                ["local_builtin", "local_filesystem", "sample_mcp"],
            )

            discover_response = client.post(
                "/tools/discover",
                params={"provider": "sample_mcp"},
            )
            self.assertEqual(discover_response.status_code, 200)
            self.assertEqual(
                [item["id"] for item in discover_response.json()],
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
            client.app.state.container.engine.dispose()
            harness.close()

    def test_filesystem_local_provider_endpoints_discover_and_execute_tools(self) -> None:
        harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            database_url=harness.database_url,
            tool_local_paths=(fixture_path("local_tools"),),
        )

        harness.initialize_schema(settings=settings)
        client = TestClient(
            create_app(
                settings=settings,
                database_url=harness.database_url,
            ),
        )

        try:
            providers_response = client.get("/tools/providers")
            self.assertEqual(providers_response.status_code, 200)
            self.assertEqual(
                [item["name"] for item in providers_response.json()],
                ["local_builtin", "local_filesystem"],
            )

            discover_response = client.post(
                "/tools/discover",
                params={"provider": "local_filesystem"},
            )
            self.assertEqual(discover_response.status_code, 200)
            self.assertEqual(
                [item["id"] for item in discover_response.json()],
                ["greeter"],
            )

            execute_response = client.post(
                "/tools/greeter/runs",
                json={
                    "arguments": {"name": "http"},
                    "strategy": "process",
                },
            )
            self.assertEqual(execute_response.status_code, 201)
            self.assertEqual(
                execute_response.json()["output_payload"]["message"],
                "hello http",
            )
            self.assertEqual(
                execute_response.json()["result"]["metadata"]["environment"],
                "local",
            )
        finally:
            client.close()
            client.app.state.container.engine.dispose()
            harness.close()

    def test_tool_runtime_endpoint_executes_thread_strategy(self) -> None:
        discover_response = self.client.post("/tools/discover-local")
        self.assertEqual(discover_response.status_code, 200)

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
        discover_response = self.client.post("/tools/discover-local")

        self.assertEqual(discover_response.status_code, 200)

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
            worker_response = self.client.app.state.container.tool_service.process_next_queued_run(
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
        discover_response = self.client.post("/tools/discover-local")
        self.assertEqual(discover_response.status_code, 200)

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
            self.client.app.state.container.tool_service.process_next_queued_run(
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
        discover_response = self.client.post("/tools/discover-local")
        self.assertEqual(discover_response.status_code, 200)

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

    def test_tool_runtime_endpoint_executes_sandbox_adapter(self) -> None:
        self.client.app.state.container.tool_service.register(
            RegisterToolInput(
                id="sandbox_echo",
                name="Sandbox Echo",
                description="Executes through the sandbox adapter",
                supported_environments=(ToolEnvironment.SANDBOX,),
                runtime_key="sandbox.echo",
            ),
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
