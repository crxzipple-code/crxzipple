from __future__ import annotations

from crxzipple.interfaces.runtime_container import AppKey
from crxzipple.modules.settings import CreateSettingsResourceInput
from tests.unit.cli_test_support import (
    CliModuleTestCase,
    Path,
    SampleApiServer,
    app,
    fixture_path,
    json,
    openapi_fixture_path,
    os,
    patch,
    shutil,
    sys,
    tempfile,
    time,
    unittest,
)


class ToolCliTestCase(CliModuleTestCase):
    def _seed_sample_openapi_access_bindings(self) -> None:
        container = self.harness.build_runtime_container()
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
                    "metadata": {"source": "test_tool_cli"},
                },
                reason="seed sample OpenAPI Access bindings",
                publish=True,
                source="unit_test",
            ),
        )

    def test_tool_run_is_denied_by_cli_guard_when_abac_blocks_it(self) -> None:
        env = dict(self.env)
        env["APP_AUTHORIZATION_ENABLED"] = "true"
        env["APP_AUTHORIZATION_POLICY_PATHS"] = str(
            Path(__file__).resolve().parents[2]
            / "config"
            / "authorization_policies"
            / "default.yaml"
        )
        run_result = self.runner.invoke(
            app,
            [
                "tool",
                "run",
                "dangerous_write",
                "--input",
                "{}",
            ],
            env=env,
        )
        self.assertEqual(run_result.exit_code, 1)

    def test_tool_list_and_roots_commands_return_payload(self) -> None:
        list_result = self.runner.invoke(app, ["tool", "list"], env=self.env)
        roots_result = self.runner.invoke(app, ["tool", "roots"], env=self.env)

        self.assertEqual(list_result.exit_code, 0)
        self.assertIn('"id": "echo"', list_result.stdout)
        self.assertEqual(roots_result.exit_code, 0)
        self.assertIn('/.crxzipple/tools', roots_result.stdout)

    def test_tool_run_commands_return_runtime_payload(self) -> None:
        run_result = self.runner.invoke(
            app,
            [
                "tool",
                "run",
                "echo",
                "--input",
                '{"message": "hello"}',
            ],
            env=self.env,
        )

        self.assertEqual(run_result.exit_code, 0)
        run_payload = json.loads(run_result.stdout)
        self.assertEqual(run_payload["tool_id"], "echo")
        self.assertEqual(run_payload["status"], "succeeded")
        self.assertEqual(run_payload["output_payload"]["message"], "hello")

        runs_result = self.runner.invoke(
            app,
            ["tool", "runs", "--tool-id", "echo"],
            env=self.env,
        )

        self.assertEqual(runs_result.exit_code, 0)
        runs_payload = json.loads(runs_result.stdout)
        self.assertEqual(len(runs_payload), 1)
        self.assertEqual(runs_payload[0]["id"], run_payload["id"])

        get_run_result = self.runner.invoke(
            app,
            ["tool", "get-run", run_payload["id"]],
            env=self.env,
        )

        self.assertEqual(get_run_result.exit_code, 0)
        fetched_run_payload = json.loads(get_run_result.stdout)
        self.assertEqual(fetched_run_payload["id"], run_payload["id"])

    def test_tool_sources_and_functions_commands_return_catalog_payload(self) -> None:
        sources_result = self.runner.invoke(
            app,
            ["tool", "sources"],
            env=self.env,
        )

        self.assertEqual(sources_result.exit_code, 0)
        sources_payload = json.loads(sources_result.stdout)
        self.assertIn("bundled.local_package.debug", {
            item["source_id"] for item in sources_payload
        })

        functions_result = self.runner.invoke(
            app,
            ["tool", "functions"],
            env=self.env,
        )

        self.assertEqual(functions_result.exit_code, 0)
        functions_payload = json.loads(functions_result.stdout)
        self.assertIn("echo", {item["function_id"] for item in functions_payload})

    def test_tool_source_commands_manage_sources_and_discovery_history(self) -> None:
        sources_result = self.runner.invoke(
            app,
            ["tool", "sources"],
            env=self.env,
        )

        self.assertEqual(sources_result.exit_code, 0)
        sources_payload = json.loads(sources_result.stdout)
        source_ids = [item["source_id"] for item in sources_payload]
        self.assertIn("bundled.local_package.debug", source_ids)

        history_result = self.runner.invoke(
            app,
            ["tool", "source-history", "bundled.local_package.debug"],
            env=self.env,
        )

        self.assertEqual(history_result.exit_code, 0)
        history_payload = json.loads(history_result.stdout)
        self.assertGreaterEqual(len(history_payload), 1)
        self.assertEqual(history_payload[0]["status"], "completed")

        refresh_result = self.runner.invoke(
            app,
            ["tool", "source-refresh", "bundled.local_package.debug"],
            env=self.env,
        )

        self.assertEqual(refresh_result.exit_code, 0)
        refresh_payload = json.loads(refresh_result.stdout)
        self.assertEqual(refresh_payload["source"]["status"], "active")
        self.assertEqual(refresh_payload["discovery"]["status"], "completed")

        functions_result = self.runner.invoke(
            app,
            [
                "tool",
                "functions",
                "--source-id",
                "bundled.local_package.debug",
            ],
            env=self.env,
        )
        self.assertEqual(functions_result.exit_code, 0)
        functions_payload = json.loads(functions_result.stdout)
        self.assertTrue(functions_payload)
        function_id = functions_payload[0]["function_id"]

        disable_function_result = self.runner.invoke(
            app,
            ["tool", "function-disable", function_id],
            env=self.env,
        )
        self.assertEqual(disable_function_result.exit_code, 0)
        self.assertFalse(json.loads(disable_function_result.stdout)["function"]["enabled"])

        enable_function_result = self.runner.invoke(
            app,
            ["tool", "function-enable", function_id],
            env=self.env,
        )
        self.assertEqual(enable_function_result.exit_code, 0)
        self.assertTrue(json.loads(enable_function_result.stdout)["function"]["enabled"])

        policy_result = self.runner.invoke(
            app,
            [
                "tool",
                "function-policy",
                function_id,
                "--trust-policy",
                '{"level":"trusted"}',
                "--approval-policy",
                '{"requires_approval":false}',
                "--credential-binding-overrides",
                '{"api_key":"cli-binding"}',
                "--required-effect-overrides",
                "cli.effect",
            ],
            env=self.env,
        )
        self.assertEqual(policy_result.exit_code, 0)
        policy_payload = json.loads(policy_result.stdout)["function"]
        self.assertEqual(policy_payload["trust_policy"], {"level": "trusted"})
        self.assertEqual(
            policy_payload["approval_policy"],
            {"requires_approval": False},
        )
        self.assertEqual(
            policy_payload["credential_binding_overrides"],
            {"api_key": "cli-binding"},
        )
        self.assertEqual(policy_payload["required_effect_overrides"], ["cli.effect"])

        config_json = json.dumps(
            {
                "source": "configured_tool_provider",
                "package_kind": "openapi",
                "provider": {
                    "name": "cli_sample",
                    "spec_location": "https://example.test/openapi.json",
                },
            },
        )
        create_source_result = self.runner.invoke(
            app,
            [
                "tool",
                "source-create",
                "configured.openapi.cli-sample",
                "--kind",
                "openapi",
                "--display-name",
                "CLI Sample",
                "--config",
                config_json,
                "--runtime-requirements",
                "bounded_network.http",
            ],
            env=self.env,
        )
        self.assertEqual(create_source_result.exit_code, 0)
        create_payload = json.loads(create_source_result.stdout)
        self.assertEqual(
            create_payload["source"]["source_id"],
            "configured.openapi.cli-sample",
        )
        self.assertEqual(create_payload["source"]["status"], "active")

        update_config_json = json.dumps(
            {
                "source": "configured_tool_provider",
                "package_kind": "openapi",
                "provider": {
                    "name": "cli_sample",
                    "spec_location": "https://example.test/renamed-openapi.json",
                },
            },
        )
        update_source_result = self.runner.invoke(
            app,
            [
                "tool",
                "source-update",
                "configured.openapi.cli-sample",
                "--kind",
                "openapi",
                "--display-name",
                "CLI Sample Renamed",
                "--config",
                update_config_json,
            ],
            env=self.env,
        )
        self.assertEqual(update_source_result.exit_code, 0)
        update_payload = json.loads(update_source_result.stdout)
        self.assertEqual(
            update_payload["source"]["display_name"],
            "CLI Sample Renamed",
        )
        self.assertEqual(
            update_payload["source"]["config"]["provider"]["spec_location"],
            "https://example.test/renamed-openapi.json",
        )

        created_history_result = self.runner.invoke(
            app,
            ["tool", "source-history", "configured.openapi.cli-sample"],
            env=self.env,
        )
        self.assertEqual(created_history_result.exit_code, 0)
        self.assertEqual(json.loads(created_history_result.stdout), [])

    def test_tool_openapi_provider_commands_discover_and_execute_remote_tools(self) -> None:
        server = SampleApiServer()
        server.start()
        env = dict(self.env)
        env["SAMPLE_API_KEY"] = "sample-api-key"
        env["SAMPLE_BEARER_TOKEN"] = "sample-bearer-token"
        env["APP_TOOL_OPENAPI_PROVIDERS"] = json.dumps(
            [
                {
                    "name": "sample_api",
                    "spec_location": openapi_fixture_path("sample_openapi.json"),
                    "base_url": server.base_url,
                    "description": "Sample OpenAPI provider",
                    "timeout_seconds": 5,
                    "credentials": {
                        "ApiKeyQuery": "binding.sample.query",
                        "BearerAuth": "binding.sample.bearer",
                    },
                },
            ],
        )
        self._seed_sample_openapi_access_bindings()

        try:
            list_result = self.runner.invoke(
                app,
                ["tool", "list"],
                env=env,
            )
            self.assertEqual(list_result.exit_code, 0)
            discovered_payload = [
                item
                for item in json.loads(list_result.stdout)
                if item["id"].startswith("sample_api.")
            ]
            self.assertEqual(
                [item["id"] for item in discovered_payload],
                ["sample_api.echo_message", "sample_api.search_docs"],
            )

            run_result = self.runner.invoke(
                app,
                [
                    "tool",
                    "run",
                    "sample_api.echo_message",
                    "--input",
                    '{"message":"cli","uppercase":true}',
                    "--environment",
                    "remote",
                ],
                env=env,
            )
            self.assertEqual(run_result.exit_code, 0)
            run_payload = json.loads(run_result.stdout)
            self.assertEqual(run_payload["status"], "succeeded")
            self.assertEqual(run_payload["output_payload"]["message"], "CLI")
            self.assertIn(
                "api_key=%5Bredacted%5D",
                run_payload["result"]["metadata"]["request"]["url"],
            )
            self.assertNotIn(
                "sample-api-key",
                run_payload["result"]["metadata"]["request"]["url"],
            )

            search_result = self.runner.invoke(
                app,
                [
                    "tool",
                    "run",
                    "sample_api.search_docs",
                    "--environment",
                    "remote",
                    "--input",
                    '{"body":{"query":"cli auth","limit":2}}',
                ],
                env=env,
            )
            self.assertEqual(search_result.exit_code, 0)
            search_payload = json.loads(search_result.stdout)
            self.assertEqual(search_payload["status"], "succeeded")
            self.assertEqual(search_payload["output_payload"]["query"], "cli auth")
        finally:
            server.close()

    def test_tool_openapi_provider_commands_load_yaml_provider_configs(self) -> None:
        server = SampleApiServer()
        server.start()
        env = dict(self.env)
        env["SAMPLE_API_KEY"] = "sample-api-key"
        env["SAMPLE_BEARER_TOKEN"] = "sample-bearer-token"

        with tempfile.TemporaryDirectory() as tempdir:
            temp_root = Path(tempdir)
            providers_dir = temp_root / "tool_providers"
            specs_dir = temp_root / "specs"
            providers_dir.mkdir()
            specs_dir.mkdir()
            shutil.copy(
                openapi_fixture_path("sample_openapi.json"),
                specs_dir / "sample_openapi.json",
            )
            (providers_dir / "sample_api.yaml").write_text(
                "\n".join(
                    [
                        "name: sample_api",
                        "spec_location: ../specs/sample_openapi.json",
                        f"base_url: {server.base_url}",
                        "description: Sample OpenAPI provider loaded from YAML",
                        "timeout_seconds: 5",
                        "credentials:",
                        "  ApiKeyQuery: binding.sample.query",
                        "  BearerAuth: binding.sample.bearer",
                        "",
                    ],
                ),
                encoding="utf-8",
            )
            env["APP_TOOL_OPENAPI_PROVIDER_PATHS"] = str(providers_dir)
            self._seed_sample_openapi_access_bindings()

            try:
                list_result = self.runner.invoke(
                    app,
                    ["tool", "list"],
                    env=env,
                )
                self.assertEqual(list_result.exit_code, 0)
                discovered_payload = [
                    item
                    for item in json.loads(list_result.stdout)
                    if item["id"].startswith("sample_api.")
                ]
                self.assertEqual(
                    [item["id"] for item in discovered_payload],
                    ["sample_api.echo_message", "sample_api.search_docs"],
                )

                run_result = self.runner.invoke(
                    app,
                    [
                        "tool",
                        "run",
                        "sample_api.search_docs",
                        "--environment",
                        "remote",
                        "--input",
                        '{"body":{"query":"yaml config","limit":2}}',
                    ],
                    env=env,
                )
                self.assertEqual(run_result.exit_code, 0)
                run_payload = json.loads(run_result.stdout)
                self.assertEqual(run_payload["status"], "succeeded")
                self.assertEqual(run_payload["output_payload"]["query"], "yaml config")
                self.assertTrue(
                    run_payload["result"]["metadata"]["tool"].endswith(
                        "sample_api.search_docs",
                    ),
                )
            finally:
                server.close()

    def test_tool_mcp_provider_commands_discover_and_execute_remote_tools(self) -> None:
        env = dict(self.env)
        env["APP_TOOL_MCP_PROVIDERS"] = json.dumps(
            [
                {
                    "name": "sample_mcp",
                    "command": [sys.executable, fixture_path("mcp_sample_server.py")],
                    "description": "Sample MCP provider",
                    "timeout_seconds": 5,
                },
            ],
        )

        list_result = self.runner.invoke(
            app,
            ["tool", "list"],
            env=env,
        )
        self.assertEqual(list_result.exit_code, 0)
        discovered_payload = [
            item
            for item in json.loads(list_result.stdout)
            if item["id"].startswith("sample_mcp.")
        ]
        self.assertEqual(
            [item["id"] for item in discovered_payload],
            ["sample_mcp.echo", "sample_mcp.sum"],
        )

        run_result = self.runner.invoke(
            app,
            [
                "tool",
                "run",
                "sample_mcp.echo",
                "--input",
                '{"message":"mcp cli","uppercase":true}',
                "--environment",
                "remote",
            ],
            env=env,
        )
        self.assertEqual(run_result.exit_code, 0)
        run_payload = json.loads(run_result.stdout)
        self.assertEqual(run_payload["status"], "succeeded")
        self.assertEqual(run_payload["output_payload"]["content"]["message"], "MCP CLI")

    def test_tool_roots_do_not_discover_legacy_filesystem_tools(self) -> None:
        env = dict(self.env)
        with tempfile.TemporaryDirectory() as tempdir:
            tools_root = Path(tempdir)
            shutil.copytree(fixture_path("local_tools"), tools_root / "tools")
            with (
                patch(
                    "crxzipple.core.config.DEFAULT_WORKSPACE_TOOL_DIR",
                    tools_root / ".crxzipple" / "tools",
                ),
                patch(
                    "crxzipple.core.config.DEFAULT_BUNDLED_TOOL_DIR",
                    tools_root / "tools",
                ),
            ):
                roots_result = self.runner.invoke(
                    app,
                    ["tool", "roots"],
                    env=env,
                )
                self.assertEqual(roots_result.exit_code, 0)
                roots_payload = json.loads(roots_result.stdout)
                self.assertEqual(
                    roots_payload[1]["path"],
                    str((tools_root / "tools").resolve()),
                )
                list_result = self.runner.invoke(
                    app,
                    ["tool", "list"],
                    env=env,
                )
                self.assertEqual(list_result.exit_code, 0)
                listed_ids = {item["id"] for item in json.loads(list_result.stdout)}
                self.assertNotIn("greeter", listed_ids)

    def test_tool_inline_process_run_returns_process_context(self) -> None:
        run_result = self.runner.invoke(
            app,
            [
                "tool",
                "run",
                "echo",
                "--strategy",
                "process",
                "--input",
                '{"message": "process cli"}',
            ],
            env=self.env,
        )

        self.assertEqual(run_result.exit_code, 0)
        run_payload = json.loads(run_result.stdout)
        self.assertEqual(run_payload["status"], "succeeded")
        self.assertEqual(run_payload["output_payload"]["message"], "process cli")
        self.assertNotEqual(run_payload["result"]["metadata"]["process_id"], os.getpid())

    def test_tool_background_run_eventually_succeeds(self) -> None:
        worker_id = "cli-background-worker"
        run_result = self.runner.invoke(
            app,
            [
                "tool",
                "run",
                "echo",
                "--mode",
                "background",
                "--input",
                '{"message": "queued hello"}',
            ],
            env=self.env,
        )

        self.assertEqual(run_result.exit_code, 0)
        run_payload = json.loads(run_result.stdout)
        self.assertEqual(run_payload["status"], "queued")

        deadline = time.monotonic() + 5
        fetched_run_payload = None
        while time.monotonic() < deadline:
            scheduler_result = self.runner.invoke(
                app,
                ["tool-scheduler", "once", "--worker-id", worker_id],
                env=self.env,
            )
            self.assertEqual(scheduler_result.exit_code, 0)
            worker_result = self.runner.invoke(
                app,
                ["tool-worker", "once", "--worker-id", worker_id],
                env=self.env,
            )
            self.assertEqual(worker_result.exit_code, 0)
            get_run_result = self.runner.invoke(
                app,
                ["tool", "get-run", run_payload["id"]],
                env=self.env,
            )
            self.assertEqual(get_run_result.exit_code, 0)
            fetched_run_payload = json.loads(get_run_result.stdout)
            if fetched_run_payload["status"] == "succeeded":
                break
            time.sleep(0.05)

        self.assertIsNotNone(fetched_run_payload)
        self.assertEqual(fetched_run_payload["status"], "succeeded")
        self.assertEqual(fetched_run_payload["output_payload"]["message"], "queued hello")
        self.assertEqual(fetched_run_payload["result"]["metadata"]["environment"], "local")
        self.assertEqual(fetched_run_payload["attempt_count"], 1)
        self.assertEqual(fetched_run_payload["worker_id"], worker_id)

    def test_tool_scheduler_run_accepts_daemon_worker_id(self) -> None:
        result = self.runner.invoke(
            app,
            [
                "tool-scheduler",
                "run-scheduler",
                "--worker-id",
                "worker-tool-scheduler-1",
                "--max-idle-cycles",
                "1",
                "--poll-interval-seconds",
                "0.05",
            ],
            env=self.env,
        )

        self.assertEqual(result.exit_code, 0)

    def test_tool_scheduler_run_rejects_sqlite_without_explicit_runtime_fallback(self) -> None:
        result = self.runner.invoke(
            app,
            [
                "tool-scheduler",
                "run-scheduler",
                "--max-idle-cycles",
                "1",
            ],
            env=self.env_without_sqlite_runtime_fallback(),
        )

        self.assertEqual(result.exit_code, 1)
        self.assertIn("Refusing to start tool scheduler with SQLite", result.stderr)
        self.assertIn("APP_ALLOW_SQLITE_RUNTIME_FALLBACK=1", result.stderr)

    def test_tool_worker_run_uses_configured_inflight_capacity_by_default(self) -> None:
        env = dict(self.env)
        env["APP_TOOL_WORKER_MAX_IN_FLIGHT"] = "6"

        result = self.runner.invoke(
            app,
            [
                "tool-worker",
                "run",
                "--worker-id",
                "cli-config-worker",
                "--max-idle-cycles",
                "1",
                "--poll-interval-seconds",
                "0.05",
            ],
            env=env,
        )

        self.assertEqual(result.exit_code, 0)
        container = self.harness.build_runtime_container()
        workers = {
            worker.id: worker
            for worker in container.require(AppKey.TOOL_SERVICE).list_tool_workers()
        }
        self.assertEqual(workers["cli-config-worker"].max_in_flight, 6)

    def test_tool_worker_run_rejects_sqlite_without_explicit_runtime_fallback(self) -> None:
        result = self.runner.invoke(
            app,
            [
                "tool-worker",
                "run",
                "--worker-id",
                "cli-guard-worker",
                "--max-idle-cycles",
                "1",
            ],
            env=self.env_without_sqlite_runtime_fallback(),
        )

        self.assertEqual(result.exit_code, 1)
        self.assertIn("Refusing to start tool worker with SQLite", result.stderr)
        self.assertIn("APP_ALLOW_SQLITE_RUNTIME_FALLBACK=1", result.stderr)

    def test_tool_background_process_run_eventually_succeeds(self) -> None:
        worker_id = "cli-process-worker"
        run_result = self.runner.invoke(
            app,
            [
                "tool",
                "run",
                "echo",
                "--mode",
                "background",
                "--strategy",
                "process",
                "--input",
                '{"message": "queued process hello"}',
            ],
            env=self.env,
        )

        self.assertEqual(run_result.exit_code, 0)
        run_payload = json.loads(run_result.stdout)
        self.assertEqual(run_payload["status"], "queued")
        self.assertEqual(run_payload["target"]["strategy"], "process")

        deadline = time.monotonic() + 5
        fetched_run_payload = None
        while time.monotonic() < deadline:
            scheduler_result = self.runner.invoke(
                app,
                ["tool-scheduler", "once", "--worker-id", worker_id],
                env=self.env,
            )
            self.assertEqual(scheduler_result.exit_code, 0)
            worker_result = self.runner.invoke(
                app,
                ["tool-worker", "once", "--worker-id", worker_id],
                env=self.env,
            )
            self.assertEqual(worker_result.exit_code, 0)
            get_run_result = self.runner.invoke(
                app,
                ["tool", "get-run", run_payload["id"]],
                env=self.env,
            )
            self.assertEqual(get_run_result.exit_code, 0)
            fetched_run_payload = json.loads(get_run_result.stdout)
            if fetched_run_payload["status"] == "succeeded":
                break
            time.sleep(0.05)

        self.assertIsNotNone(fetched_run_payload)
        self.assertEqual(fetched_run_payload["status"], "succeeded")
        self.assertEqual(
            fetched_run_payload["output_payload"]["message"],
            "queued process hello",
        )
        self.assertEqual(fetched_run_payload["target"]["strategy"], "process")
        self.assertEqual(fetched_run_payload["worker_id"], worker_id)
        self.assertNotEqual(
            fetched_run_payload["result"]["metadata"]["process_id"],
            os.getpid(),
        )

    def test_tool_cancel_run_command_returns_cancelled_payload(self) -> None:
        run_result = self.runner.invoke(
            app,
            [
                "tool",
                "run",
                "echo",
                "--mode",
                "background",
                "--input",
                '{"message": "cancel via cli"}',
            ],
            env=self.env,
        )
        self.assertEqual(run_result.exit_code, 0)
        run_payload = json.loads(run_result.stdout)

        cancel_result = self.runner.invoke(
            app,
            ["tool", "cancel-run", run_payload["id"]],
            env=self.env,
        )
        self.assertEqual(cancel_result.exit_code, 0)
        cancel_payload = json.loads(cancel_result.stdout)
        self.assertEqual(cancel_payload["status"], "cancelled")
        self.assertIsNotNone(cancel_payload["cancel_requested_at"])

    def test_tool_roots_command_reports_fixed_directories(self) -> None:
        result = self.runner.invoke(
            app,
            ["tool", "roots"],
            env=self.env,
        )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertTrue(len(payload) >= 2)
        self.assertTrue(payload[0]["path"].endswith("/.crxzipple/tools"))


if __name__ == "__main__":
    unittest.main()
