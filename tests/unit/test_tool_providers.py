from __future__ import annotations

from unittest.mock import patch

from tests.unit.tool_test_support import *  # noqa: F403


class ToolProvidersTestCase(ToolTestCaseBase):
    def test_scanned_tool_packages_register_system_tools_without_bootstrap_hardcoding(self) -> None:
        namespaces = discover_tool_namespaces()

        self.assertEqual(
            [namespace.name for namespace in namespaces],
            [
                "brave_search",
                "browser",
                "command",
                "debug",
                "itick_market",
                "memory",
                "mobile",
                "open_meteo_geocoding",
                "open_meteo_weather",
                "openai_image",
                "sessions",
                "skills",
                "workspace",
            ],
        )
        self.assertEqual(
            [namespace.kind for namespace in namespaces],
            [
                "openapi",
                "local_package",
                "local_package",
                "local_package",
                "openapi",
                "local_package",
                "local_package",
                "openapi",
                "openapi",
                "local_package",
                "local_package",
                "local_package",
                "local_package",
            ],
        )
        self.assertTrue(
            all(
                isinstance(namespace, ToolNamespaceDefinition)
                for namespace in namespaces
            ),
        )
        self.assertEqual(
            [len(namespace.local_bindings) for namespace in namespaces],
            [0, 5, 2, 1, 0, 4, 9, 0, 0, 2, 8, 1, 6],
        )
        self.assertEqual(
            [len(namespace.remote_bindings) for namespace in namespaces],
            [0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        )
        self.assertEqual(
            [len(namespace.sandbox_bindings) for namespace in namespaces],
            [0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        )

        catalog = LocalToolCatalog()
        remote_registry = ToolRuntimeRegistry()
        sandbox_registry = ToolRuntimeRegistry()
        register_scanned_tool_packages(
            SimpleNamespace(
                local_tool_catalog=catalog,
                remote_tool_registry=remote_registry,
                sandbox_tool_registry=sandbox_registry,
                file_memory_service=self.container.file_memory_service,
                memory_context_resolver=self.container.memory_context_resolver,
                process_service=self.container.process_service,
                session_service=self.container.session_service,
                session_workspace_lookup=lambda _session_key: "/tmp/workspace",
                orchestration_run_query_service_lookup=(
                    lambda: self.container.orchestration_run_query_service
                ),
                orchestration_cancellation_service_lookup=(
                    lambda: self.container.orchestration_cancellation_service
                ),
                orchestration_scheduler_service_lookup=(
                    lambda: self.container.orchestration_scheduler_service
                ),
                skill_manager=self.container.skill_manager,
            ),
        )

        registered_ids = [tool.id for tool in catalog.list_local_tools()]
        self.assertEqual(
            sorted(registered_ids),
            sorted(
                [
                    "echo",
                    "apply_patch",
                    "exec",
                    "process",
                    "memory_flush_skip",
                    "memory_read",
                    "memory_search",
                    "memory_write_daily",
                    "openai_image_edit",
                    "openai_image_generate",
                    "edit",
                    "read",
                    "session_status",
                    "sessions_history",
                    "sessions_list",
                    "sessions_send",
                    "sessions_spawn",
                    "subagents",
                    "sessions_stop",
                    "sessions_yield",
                    "skill_read",
                    "workspace_list",
                    "write",
                    "workspace_search",
                ],
            ),
        )
        self.assertIsNotNone(remote_registry.get_handler("remote.echo"))
        self.assertIsNotNone(sandbox_registry.get_handler("sandbox.echo"))

    def test_lists_discovery_providers_and_discovers_by_provider_name(self) -> None:
        providers = self.container.tool_service.list_discovery_providers()

        self.assertEqual(
            [provider.name for provider in providers],
            ["local_builtin", "local_filesystem"],
        )
        self.assertEqual(providers[0].name, "local_builtin")
        self.assertEqual(providers[0].source_kind, ToolSourceKind.LOCAL_DISCOVERY)

        discovered = self.container.tool_service.discover_tools(
            provider_name="local_builtin",
        )

        self.assertEqual([tool.id for tool in discovered], ["echo"])
        self.assertEqual(discovered[0].source_kind, ToolSourceKind.LOCAL_DISCOVERY)

    def test_discovers_and_executes_openapi_remote_tools(self) -> None:
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
            tool_openapi_providers=(
                OpenApiProviderSettings(
                    name="sample_api",
                    spec_location=openapi_fixture_path("sample_openapi.json"),
                    base_url=server.base_url,
                    description="Sample OpenAPI provider",
                    timeout_seconds=5,
                    max_concurrency=2,
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

        try:
            container = harness.build_container(settings=settings)
            providers = container.tool_service.list_discovery_providers()
            self.assertEqual(
                [provider.name for provider in providers],
                ["local_builtin", "local_filesystem", "sample_api"],
            )

            discovered = container.tool_service.discover_tools(
                provider_name="sample_api",
            )
            self.assertEqual(
                [tool.id for tool in discovered],
                ["sample_api.echo_message", "sample_api.search_docs"],
            )
            self.assertEqual(discovered[0].kind, ToolKind.HTTP)
            self.assertEqual(
                discovered[0].execution_support.supported_environments,
                (ToolEnvironment.REMOTE,),
            )
            self.assertEqual(discovered[1].parameters[-1].name, "body")
            registration = container.remote_tool_registry.get_registration(
                "openapi.sample_api.echo_message",
            )
            self.assertIsNotNone(registration)
            assert registration is not None
            self.assertEqual(registration.concurrency_key, "openapi:sample_api")
            self.assertEqual(registration.max_concurrency, 2)

            with patch(
                "requests.request",
                side_effect=AssertionError(
                    "OpenAPI remote tools must use async HTTP transport",
                ),
            ):
                echo_run = asyncio.run(
                    container.tool_service.execute(
                        ExecuteToolInput(
                            tool_id="sample_api.echo_message",
                            arguments={"message": "hello", "uppercase": True},
                            environment=ToolEnvironment.REMOTE,
                        ),
                    ),
                )
            self.assertEqual(echo_run.status, ToolRunStatus.SUCCEEDED)
            self.assertEqual(echo_run.output_payload["message"], "HELLO")
            self.assertEqual(echo_run.result.metadata["status_code"], 200)
            self.assertIn(
                "api_key=%5Bredacted%5D",
                echo_run.result.metadata["request"]["url"],
            )
            self.assertNotIn(
                "sample-api-key",
                echo_run.result.metadata["request"]["url"],
            )

            with patch(
                "requests.request",
                side_effect=AssertionError(
                    "OpenAPI remote tools must use async HTTP transport",
                ),
            ):
                search_run = asyncio.run(
                    container.tool_service.execute(
                        ExecuteToolInput(
                            tool_id="sample_api.search_docs",
                            arguments={"body": {"query": "ddd", "limit": 2}},
                            environment=ToolEnvironment.REMOTE,
                        ),
                    ),
                )
            self.assertEqual(search_run.status, ToolRunStatus.SUCCEEDED)
            self.assertEqual(search_run.output_payload["query"], "ddd")
            self.assertEqual(search_run.output_payload["limit"], 2)
        finally:
            if previous_api_key is None:
                os.environ.pop("SAMPLE_API_KEY", None)
            else:
                os.environ["SAMPLE_API_KEY"] = previous_api_key
            if previous_bearer_token is None:
                os.environ.pop("SAMPLE_BEARER_TOKEN", None)
            else:
                os.environ["SAMPLE_BEARER_TOKEN"] = previous_bearer_token
            if "container" in locals():
                container.engine.dispose()
            harness.close()

    def test_filesystem_local_provider_reconciles_removed_tool_manifests(self) -> None:
        harness = SqliteTestHarness()
        with tempfile.TemporaryDirectory() as tempdir:
            tools_root = Path(tempdir)
            tool_dir = tools_root / "temp_echo"
            tool_dir.mkdir(parents=True)
            (tool_dir / "run.py").write_text(
                "\n".join(
                    [
                        "from __future__ import annotations",
                        "",
                        "def run(arguments: dict[str, object]) -> dict[str, object]:",
                        "    return {'message': arguments.get('message')}",
                        "",
                    ],
                ),
                encoding="utf-8",
            )
            (tool_dir / "tool.json").write_text(
                "\n".join(
                    [
                        "{",
                        '  "id": "temp_echo",',
                        '  "name": "Temp Echo",',
                        '  "description": "Temp echo tool",',
                        '  "entrypoint": "run.py:run"',
                        "}",
                    ],
                ),
                encoding="utf-8",
            )

            settings = replace(
                load_settings(),
                database_url=harness.database_url,
                tool_local_paths=(str(tools_root),),
            )
            container = harness.build_container(settings=settings)
            try:
                self.assertIn(
                    "temp_echo",
                    [tool.id for tool in container.tool_service.list_tools()],
                )
                (tool_dir / "tool.json").unlink()
                self.assertNotIn(
                    "temp_echo",
                    [tool.id for tool in container.tool_service.list_tools()],
                )
            finally:
                container.close()
                harness.close()

    def test_discovers_and_executes_mcp_remote_tools(self) -> None:
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
                    max_concurrency=3,
                ),
            ),
        )

        try:
            container = harness.build_container(settings=settings)
            providers = container.tool_service.list_discovery_providers()
            self.assertEqual(
                [provider.name for provider in providers],
                ["local_builtin", "local_filesystem", "sample_mcp"],
            )

            discovered = container.tool_service.discover_tools(
                provider_name="sample_mcp",
            )
            self.assertEqual(
                [tool.id for tool in discovered],
                ["sample_mcp.echo", "sample_mcp.sum"],
            )
            self.assertEqual(discovered[0].kind, ToolKind.MCP)
            self.assertEqual(
                discovered[0].execution_support.supported_environments,
                (ToolEnvironment.REMOTE,),
            )
            registration = container.remote_tool_registry.get_registration(
                "mcp.sample_mcp.echo",
            )
            self.assertIsNotNone(registration)
            assert registration is not None
            self.assertEqual(registration.concurrency_key, "mcp:sample_mcp")
            self.assertEqual(registration.max_concurrency, 3)

            with patch(
                "crxzipple.modules.tool.infrastructure.mcp_client.McpStdioClient.call_tool",
                side_effect=AssertionError(
                    "MCP remote tools must use async stdio transport",
                ),
            ):
                echo_run = asyncio.run(
                    container.tool_service.execute(
                        ExecuteToolInput(
                            tool_id="sample_mcp.echo",
                            arguments={"message": "hello mcp", "uppercase": True},
                            environment=ToolEnvironment.REMOTE,
                        ),
                    ),
                )
            self.assertEqual(echo_run.status, ToolRunStatus.SUCCEEDED)
            self.assertEqual(
                echo_run.output_payload["content"]["message"],
                "HELLO MCP",
            )
            self.assertEqual(echo_run.result.metadata["provider"], "sample_mcp")
            first_server_pid = echo_run.output_payload["content"]["server_pid"]
            first_request_count = echo_run.output_payload["content"]["request_count"]

            with patch(
                "crxzipple.modules.tool.infrastructure.mcp_client.McpStdioClient.call_tool",
                side_effect=AssertionError(
                    "MCP remote tools must use async stdio transport",
                ),
            ):
                sum_run = asyncio.run(
                    container.tool_service.execute(
                        ExecuteToolInput(
                            tool_id="sample_mcp.sum",
                            arguments={"left": 2, "right": 5},
                            environment=ToolEnvironment.REMOTE,
                        ),
                    ),
                )
            self.assertEqual(sum_run.status, ToolRunStatus.SUCCEEDED)
            self.assertEqual(sum_run.output_payload["content"]["total"], 7)
            self.assertEqual(
                sum_run.output_payload["content"]["server_pid"],
                first_server_pid,
            )
            self.assertGreater(
                sum_run.output_payload["content"]["request_count"],
                first_request_count,
            )
        finally:
            if "container" in locals():
                container.close()
            harness.close()

    def test_discovers_filesystem_local_tools_and_executes_with_process_strategy(self) -> None:
        harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            database_url=harness.database_url,
            tool_local_paths=(fixture_path("local_tools"),),
        )

        try:
            container = harness.build_container(settings=settings)
            providers = container.tool_service.list_discovery_providers()
            self.assertEqual(
                [provider.name for provider in providers],
                ["local_builtin", "local_filesystem"],
            )

            discovered = container.tool_service.discover_tools(
                provider_name="local_filesystem",
            )
            self.assertEqual([tool.id for tool in discovered], ["greeter"])
            self.assertEqual(discovered[0].source_kind, ToolSourceKind.LOCAL_DISCOVERY)

            tool_run = asyncio.run(
                container.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="greeter",
                        arguments={"name": "filesystem"},
                        strategy=ToolExecutionStrategy.PROCESS,
                    ),
                ),
            )
            self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
            self.assertEqual(tool_run.output_payload["message"], "hello filesystem")
            self.assertEqual(tool_run.result.metadata["environment"], "local")
            self.assertNotEqual(tool_run.result.metadata["process_id"], os.getpid())
        finally:
            if "container" in locals():
                container.close()
            harness.close()

    def test_process_local_overlay_with_same_id_remains_until_removed(self) -> None:
        tool = self.container.tool_service.register(
            RegisterToolInput(
                id="echo",
                name="Old Echo",
                description="Stale discovered copy.",
                source_kind=ToolSourceKind.LOCAL_DISCOVERY,
                runtime_key="echo",
            ),
        )
        self.assertEqual(tool.name, "Old Echo")

        discovered = self.container.tool_service.discover_tools(
            provider_name="local_builtin",
        )

        self.assertEqual([item.id for item in discovered], ["echo"])
        refreshed = next(
            item for item in self.container.tool_service.list_tools() if item.id == "echo"
        )
        self.assertEqual(refreshed.id, "echo")
        self.assertEqual(refreshed.name, "Old Echo")

    def test_discover_does_not_override_manual_tool_with_same_id(self) -> None:
        tool = self.container.tool_service.register(
            RegisterToolInput(
                id="echo",
                name="Manual Echo",
                description="Manual override should stay untouched.",
                source_kind=ToolSourceKind.MANUAL,
            ),
        )
        self.assertEqual(tool.name, "Manual Echo")

        discovered = self.container.tool_service.discover_tools(
            provider_name="local_builtin",
        )

        self.assertEqual([item.id for item in discovered], ["echo"])
        current = next(
            item for item in self.container.tool_service.list_tools() if item.id == "echo"
        )
        self.assertEqual(current.name, "Manual Echo")
