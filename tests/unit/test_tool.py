from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
import threading
import time
import unittest

from crxzipple.core.config import (
    McpProviderSettings,
    OpenApiCredentialBinding,
    OpenApiProviderSettings,
    load_settings,
)
from crxzipple.modules.dispatch.application import RecoverAbandonedDispatchTasksInput
from crxzipple.modules.dispatch.domain import DispatchTaskStatus
from crxzipple.modules.tool.application import (
    ExecuteToolInput,
    RegisterToolInput,
    RegisterToolParameterInput,
    SetToolAvailabilityInput,
)
from crxzipple.modules.tool.domain import (
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolKind,
    ToolMode,
    ToolSourceKind,
    ToolRunStatus,
)
from tests.unit.support import (
    SampleApiServer,
    SqliteTestHarness,
    fixture_path,
    openapi_fixture_path,
)


class ToolTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_openapi_provider_paths = os.environ.get(
            "APP_TOOL_OPENAPI_PROVIDER_PATHS",
        )
        os.environ["APP_TOOL_OPENAPI_PROVIDER_PATHS"] = os.pathsep
        self.harness = SqliteTestHarness()
        self.container = self.harness.build_container()

    def tearDown(self) -> None:
        self.container.engine.dispose()
        self.harness.close()
        if self.previous_openapi_provider_paths is None:
            os.environ.pop("APP_TOOL_OPENAPI_PROVIDER_PATHS", None)
        else:
            os.environ["APP_TOOL_OPENAPI_PROVIDER_PATHS"] = (
                self.previous_openapi_provider_paths
            )

    def test_registers_rich_tool_definition(self) -> None:
        tool = self.container.tool_service.register(
            RegisterToolInput(
                id="web_search",
                name="Web Search",
                description="Searches external knowledge sources.",
                kind=ToolKind.HTTP,
                parameters=(
                    RegisterToolParameterInput(
                        name="query",
                        data_type="string",
                        description="Search query text.",
                    ),
                    RegisterToolParameterInput(
                        name="limit",
                        data_type="integer",
                        description="Maximum number of results.",
                        required=False,
                    ),
                ),
                tags=("search", "external", "search"),
                timeout_seconds=45,
                requires_confirmation=True,
                mutates_state=False,
                supported_modes=(ToolMode.INLINE, ToolMode.BACKGROUND),
                supported_strategies=(
                    ToolExecutionStrategy.ASYNC,
                    ToolExecutionStrategy.THREAD,
                ),
                supported_environments=(
                    ToolEnvironment.LOCAL,
                    ToolEnvironment.REMOTE,
                ),
                source_kind=ToolSourceKind.REMOTE_REGISTRY,
                runtime_key="search.http",
            ),
        )

        self.assertEqual(tool.kind, ToolKind.HTTP)
        self.assertEqual(tool.tags, ("search", "external"))
        self.assertEqual(len(tool.parameters), 2)
        self.assertEqual(tool.parameters[0].name, "query")
        self.assertTrue(tool.parameters[0].required)
        self.assertFalse(tool.parameters[1].required)
        self.assertTrue(tool.execution_policy.requires_confirmation)
        self.assertEqual(tool.execution_policy.timeout_seconds, 45)
        self.assertEqual(
            tool.execution_support.supported_modes,
            (ToolMode.INLINE, ToolMode.BACKGROUND),
        )
        self.assertEqual(tool.source_kind, ToolSourceKind.REMOTE_REGISTRY)
        self.assertEqual(tool.runtime_key, "search.http")

        with self.container.uow_factory() as uow:
            persisted = uow.tools.get("web_search")

        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.kind, ToolKind.HTTP)
        self.assertEqual(persisted.tags, ("search", "external"))
        self.assertEqual(persisted.execution_policy.timeout_seconds, 45)
        self.assertEqual(
            persisted.execution_support.supported_environments,
            (ToolEnvironment.LOCAL, ToolEnvironment.REMOTE),
        )

    def test_list_enabled_tools_respects_availability(self) -> None:
        self.container.tool_service.register(
            RegisterToolInput(
                id="read_docs",
                name="Read Docs",
                description="Reads internal documentation.",
            ),
        )
        self.container.tool_service.register(
            RegisterToolInput(
                id="dangerous_write",
                name="Dangerous Write",
                description="Writes to external systems.",
                mutates_state=True,
                enabled=False,
            ),
        )

        enabled_tools = self.container.tool_service.list_enabled_tools()

        self.assertEqual([tool.id for tool in enabled_tools], ["read_docs"])

    def test_discovers_local_tools_and_persists_them(self) -> None:
        discovered = self.container.tool_service.discover_local_tools()

        self.assertEqual([tool.id for tool in discovered], ["echo"])
        self.assertEqual(discovered[0].source_kind, ToolSourceKind.LOCAL_DISCOVERY)
        self.assertEqual(discovered[0].runtime_key, "echo")

        with self.container.uow_factory() as uow:
            persisted = uow.tools.get("echo")

        self.assertIsNotNone(persisted)
        self.assertEqual(
            persisted.execution_support.supported_strategies,
            (
                ToolExecutionStrategy.ASYNC,
                ToolExecutionStrategy.THREAD,
                ToolExecutionStrategy.PROCESS,
            ),
        )

    def test_lists_discovery_providers_and_discovers_by_provider_name(self) -> None:
        providers = self.container.tool_service.list_discovery_providers()

        self.assertEqual(len(providers), 1)
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
                ["local_builtin", "sample_api"],
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
                "api_key=sample-api-key",
                echo_run.result.metadata["request"]["url"],
            )

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
            server.close()

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
                ),
            ),
        )

        try:
            container = harness.build_container(settings=settings)
            providers = container.tool_service.list_discovery_providers()
            self.assertEqual(
                [provider.name for provider in providers],
                ["local_builtin", "sample_mcp"],
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

    def test_refreshes_existing_discovered_tool_definition_on_repeat_discover(self) -> None:
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
        refreshed = self.container.tool_service.list_tools()[0]
        self.assertEqual(refreshed.id, "echo")
        self.assertEqual(refreshed.name, "Echo")
        self.assertIn("builtin", refreshed.tags)
        event_names = [event.name for event in self.container.event_bus.published_events]
        self.assertIn("tool.discovered_refreshed", event_names)

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
        current = self.container.tool_service.list_tools()[0]
        self.assertEqual(current.name, "Manual Echo")
        event_names = [event.name for event in self.container.event_bus.published_events]
        self.assertNotIn("tool.discovered_refreshed", event_names)

    def test_executes_local_inline_async_tool_and_persists_run(self) -> None:
        self.container.tool_service.discover_local_tools()

        tool_run = asyncio.run(
            self.container.tool_service.execute(
                ExecuteToolInput(
                    tool_id="echo",
                    arguments={"message": "hello"},
                ),
            ),
        )

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(tool_run.output_payload["message"], "hello")
        self.assertIsNotNone(tool_run.started_at)
        self.assertIsNotNone(tool_run.completed_at)

        with self.container.uow_factory() as uow:
            persisted = uow.tool_runs.get(tool_run.id)

        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(persisted.output_payload["received"]["message"], "hello")

        event_names = [event.name for event in self.container.event_bus.published_events]
        self.assertIn("tool.run.created", event_names)
        self.assertIn("tool.run.started", event_names)
        self.assertIn("tool.run.succeeded", event_names)

    def test_executes_sandbox_inline_async_tool_via_runtime_router(self) -> None:
        self.container.tool_service.register(
            RegisterToolInput(
                id="sandbox_echo",
                name="Sandbox Echo",
                description="Executes through the sandbox adapter.",
                supported_environments=(ToolEnvironment.SANDBOX,),
                source_kind=ToolSourceKind.MANUAL,
                runtime_key="sandbox.echo",
            ),
        )

        tool_run = asyncio.run(
            self.container.tool_service.execute(
                ExecuteToolInput(
                    tool_id="sandbox_echo",
                    arguments={"message": "sandbox hello"},
                    environment=ToolEnvironment.SANDBOX,
                ),
            ),
        )

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(tool_run.output_payload["message"], "sandbox hello")
        self.assertEqual(tool_run.result.metadata["environment"], "sandbox")
        self.assertTrue(tool_run.result.metadata["sandboxed"])
        self.assertNotEqual(tool_run.result.metadata["process_id"], os.getpid())
        self.assertTrue(
            Path(tool_run.result.metadata["working_directory"]).name.startswith(
                "tool-sandbox-",
            ),
        )

    def test_executes_local_inline_thread_tool_and_reports_thread_context(self) -> None:
        self.container.tool_service.discover_local_tools()

        tool_run = asyncio.run(
            self.container.tool_service.execute(
                ExecuteToolInput(
                    tool_id="echo",
                    arguments={"message": "thread hello"},
                    strategy=ToolExecutionStrategy.THREAD,
                ),
            ),
        )

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(tool_run.output_payload["message"], "thread hello")
        self.assertEqual(tool_run.result.metadata["process_id"], os.getpid())
        self.assertNotEqual(
            tool_run.result.metadata["thread_ident"],
            threading.get_ident(),
        )

    def test_executes_local_inline_process_tool_and_reports_process_context(self) -> None:
        self.container.tool_service.discover_local_tools()

        tool_run = asyncio.run(
            self.container.tool_service.execute(
                ExecuteToolInput(
                    tool_id="echo",
                    arguments={"message": "process hello"},
                    strategy=ToolExecutionStrategy.PROCESS,
                ),
            ),
        )

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(tool_run.output_payload["message"], "process hello")
        self.assertNotEqual(tool_run.result.metadata["process_id"], os.getpid())

    def test_executes_local_background_async_tool_and_updates_lifecycle(self) -> None:
        self.container.tool_service.discover_local_tools()

        queued_run = asyncio.run(
            self.container.tool_service.execute(
                ExecuteToolInput(
                    tool_id="echo",
                    arguments={"message": "background hello"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )

        self.assertEqual(queued_run.status, ToolRunStatus.QUEUED)
        dispatch_task = self.container.dispatch_service.get_task(queued_run.id)
        self.assertEqual(dispatch_task.status, DispatchTaskStatus.QUEUED)
        self.assertEqual(dispatch_task.owner_kind, "tool_run")

        deadline = time.monotonic() + 5
        persisted = None
        while time.monotonic() < deadline:
            if persisted is None or persisted.status is ToolRunStatus.QUEUED:
                self.container.tool_service.process_next_queued_run(
                    worker_id="worker-local",
                )
            persisted = self.container.tool_service.get_tool_run(queued_run.id)
            if persisted.status is ToolRunStatus.SUCCEEDED:
                break
            time.sleep(0.05)

        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(persisted.output_payload["message"], "background hello")
        self.assertEqual(persisted.result.metadata["environment"], "local")
        self.assertEqual(persisted.attempt_count, 1)
        self.assertEqual(persisted.worker_id, "worker-local")
        self.assertIsNotNone(persisted.heartbeat_at)
        self.assertIsNone(persisted.lease_expires_at)
        completed_dispatch_task = self.container.dispatch_service.get_task(queued_run.id)
        self.assertEqual(completed_dispatch_task.status, DispatchTaskStatus.COMPLETED)

        event_names = [event.name for event in self.container.event_bus.published_events]
        self.assertIn("tool.run.queued", event_names)

    def test_background_claim_and_heartbeat_keep_dispatch_lease_in_sync(self) -> None:
        self.container.tool_service.discover_local_tools()
        queued_run = asyncio.run(
            self.container.tool_service.execute(
                ExecuteToolInput(
                    tool_id="echo",
                    arguments={"message": "lease hello"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )

        claimed = self.container.tool_service.claim_next_queued_run(
            worker_id="worker-lease",
        )

        self.assertIsNotNone(claimed)
        assert claimed is not None
        dispatch_task = self.container.dispatch_service.get_task(queued_run.id)
        self.assertEqual(dispatch_task.status, DispatchTaskStatus.CLAIMED)
        self.assertIsNotNone(dispatch_task.lease_expires_at)
        initial_lease_expires_at = dispatch_task.lease_expires_at
        time.sleep(0.01)

        self.container.tool_service.heartbeat_run(
            queued_run.id,
            worker_id="worker-lease",
        )

        refreshed_task = self.container.dispatch_service.get_task(queued_run.id)
        self.assertIsNotNone(refreshed_task.lease_expires_at)
        assert refreshed_task.lease_expires_at is not None
        assert initial_lease_expires_at is not None
        self.assertGreater(refreshed_task.lease_expires_at, initial_lease_expires_at)

    def test_background_async_run_heartbeats_while_sync_handler_blocks(self) -> None:
        def blocking_echo(arguments: dict[str, object]) -> dict[str, object]:
            time.sleep(0.2)
            return {"message": arguments.get("message")}

        tool = self.container.tool_service.register(
            RegisterToolInput(
                id="blocking_echo",
                name="Blocking Echo",
                description="Blocks synchronously before returning.",
                supported_modes=(ToolMode.BACKGROUND,),
                runtime_key="blocking_echo",
            ),
        )
        self.container.local_tool_catalog.register(tool, blocking_echo)
        self.container.tool_service.worker_lease_seconds = 1
        self.container.tool_service.worker_heartbeat_seconds = 0.02

        queued_run = asyncio.run(
            self.container.tool_service.execute(
                ExecuteToolInput(
                    tool_id="blocking_echo",
                    arguments={"message": "keep alive"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )

        worker_result: dict[str, object] = {}

        def run_worker() -> None:
            worker_result["run"] = self.container.tool_service.process_next_queued_run(
                worker_id="worker-heartbeat-thread",
            )

        thread = threading.Thread(target=run_worker)
        thread.start()

        deadline = time.monotonic() + 2
        initial_heartbeat_at = None
        while time.monotonic() < deadline:
            current = self.container.tool_service.get_tool_run(queued_run.id)
            if current.status is ToolRunStatus.RUNNING:
                initial_heartbeat_at = current.heartbeat_at
                break
            time.sleep(0.01)
        else:
            self.fail("Tool run never reached RUNNING state.")

        assert initial_heartbeat_at is not None

        heartbeat_advanced = False
        while time.monotonic() < deadline:
            current = self.container.tool_service.get_tool_run(queued_run.id)
            if (
                current.status is ToolRunStatus.RUNNING
                and current.heartbeat_at is not None
                and current.heartbeat_at > initial_heartbeat_at
            ):
                heartbeat_advanced = True
                break
            if not thread.is_alive():
                break
            time.sleep(0.01)

        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertTrue(heartbeat_advanced)

        finished = self.container.tool_service.get_tool_run(queued_run.id)
        self.assertEqual(finished.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(finished.output_payload["message"], "keep alive")
        self.assertIn("run", worker_result)

    def test_executes_local_background_thread_tool_and_updates_lifecycle(self) -> None:
        self.container.tool_service.discover_local_tools()

        queued_run = asyncio.run(
            self.container.tool_service.execute(
                ExecuteToolInput(
                    tool_id="echo",
                    arguments={"message": "background thread hello"},
                    mode=ToolMode.BACKGROUND,
                    strategy=ToolExecutionStrategy.THREAD,
                ),
            ),
        )

        self.assertEqual(queued_run.status, ToolRunStatus.QUEUED)

        deadline = time.monotonic() + 5
        persisted = None
        while time.monotonic() < deadline:
            if persisted is None or persisted.status is ToolRunStatus.QUEUED:
                self.container.tool_service.process_next_queued_run(
                    worker_id="worker-thread-bg",
                )
            persisted = self.container.tool_service.get_tool_run(queued_run.id)
            if persisted.status is ToolRunStatus.SUCCEEDED:
                break
            time.sleep(0.05)

        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(persisted.output_payload["message"], "background thread hello")
        self.assertEqual(persisted.result.metadata["process_id"], os.getpid())
        self.assertNotEqual(
            persisted.result.metadata["thread_ident"],
            threading.get_ident(),
        )
        self.assertEqual(persisted.worker_id, "worker-thread-bg")

    def test_executes_local_background_process_tool_and_updates_lifecycle(self) -> None:
        self.container.tool_service.discover_local_tools()

        queued_run = asyncio.run(
            self.container.tool_service.execute(
                ExecuteToolInput(
                    tool_id="echo",
                    arguments={"message": "background process hello"},
                    mode=ToolMode.BACKGROUND,
                    strategy=ToolExecutionStrategy.PROCESS,
                ),
            ),
        )

        self.assertEqual(queued_run.status, ToolRunStatus.QUEUED)

        deadline = time.monotonic() + 5
        persisted = None
        while time.monotonic() < deadline:
            if persisted is None or persisted.status is ToolRunStatus.QUEUED:
                self.container.tool_service.process_next_queued_run(
                    worker_id="worker-process-bg",
                )
            persisted = self.container.tool_service.get_tool_run(queued_run.id)
            if persisted.status is ToolRunStatus.SUCCEEDED:
                break
            time.sleep(0.05)

        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(persisted.output_payload["message"], "background process hello")
        self.assertNotEqual(persisted.result.metadata["process_id"], os.getpid())
        self.assertEqual(persisted.worker_id, "worker-process-bg")

    def test_executes_remote_background_async_tool_and_updates_lifecycle(self) -> None:
        self.container.tool_service.register(
            RegisterToolInput(
                id="remote_echo",
                name="Remote Echo",
                description="Executes through the remote adapter.",
                supported_modes=(ToolMode.INLINE, ToolMode.BACKGROUND),
                supported_environments=(ToolEnvironment.REMOTE,),
                source_kind=ToolSourceKind.REMOTE_REGISTRY,
                runtime_key="remote.echo",
            ),
        )

        queued_run = asyncio.run(
            self.container.tool_service.execute(
                ExecuteToolInput(
                    tool_id="remote_echo",
                    arguments={"message": "remote hello"},
                    mode=ToolMode.BACKGROUND,
                    environment=ToolEnvironment.REMOTE,
                ),
            ),
        )

        self.assertEqual(queued_run.status, ToolRunStatus.QUEUED)

        deadline = time.monotonic() + 5
        persisted = None
        while time.monotonic() < deadline:
            if persisted is None or persisted.status is ToolRunStatus.QUEUED:
                self.container.tool_service.process_next_queued_run(
                    worker_id="worker-remote",
                )
            persisted = self.container.tool_service.get_tool_run(queued_run.id)
            if persisted.status is ToolRunStatus.SUCCEEDED:
                break
            time.sleep(0.05)

        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(persisted.output_payload["message"], "remote hello")
        self.assertEqual(persisted.result.metadata["environment"], "remote")

    def test_retries_background_run_until_attempt_budget_is_exhausted(self) -> None:
        async def always_fail(arguments: dict[str, object]) -> dict[str, object]:
            raise RuntimeError(f"boom: {arguments.get('message')}")

        tool = self.container.tool_service.register(
            RegisterToolInput(
                id="always_fail",
                name="Always Fail",
                description="Fails every time.",
                supported_modes=(ToolMode.BACKGROUND,),
                runtime_key="always_fail",
            ),
        )
        self.container.local_tool_catalog.register(tool, always_fail)

        queued_run = asyncio.run(
            self.container.tool_service.execute(
                ExecuteToolInput(
                    tool_id="always_fail",
                    arguments={"message": "retry me"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )

        self.assertEqual(queued_run.status, ToolRunStatus.QUEUED)

        first_attempt = self.container.tool_service.process_next_queued_run(
            worker_id="worker-retry",
        )
        second_attempt = self.container.tool_service.process_next_queued_run(
            worker_id="worker-retry",
        )
        final_attempt = self.container.tool_service.process_next_queued_run(
            worker_id="worker-retry",
        )

        self.assertIsNotNone(first_attempt)
        self.assertEqual(first_attempt.status, ToolRunStatus.QUEUED)
        self.assertIsNotNone(second_attempt)
        self.assertEqual(second_attempt.status, ToolRunStatus.QUEUED)
        self.assertIsNotNone(final_attempt)
        self.assertEqual(final_attempt.status, ToolRunStatus.FAILED)
        self.assertEqual(final_attempt.attempt_count, 3)
        self.assertIn("boom: retry me", final_attempt.error_message)

        persisted = self.container.tool_service.get_tool_run(queued_run.id)
        self.assertEqual(persisted.status, ToolRunStatus.FAILED)
        self.assertEqual(persisted.attempt_count, 3)
        self.assertEqual(persisted.max_attempts, 3)
        dispatch_task = self.container.dispatch_service.get_task(queued_run.id)
        self.assertEqual(dispatch_task.status, DispatchTaskStatus.FAILED)

    def test_recovers_abandoned_background_run_when_lease_expires(self) -> None:
        self.container.tool_service.discover_local_tools()
        queued_run = asyncio.run(
            self.container.tool_service.execute(
                ExecuteToolInput(
                    tool_id="echo",
                    arguments={"message": "recover me"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )

        claimed = self.container.tool_service.claim_next_queued_run(
            worker_id="worker-abandoned",
        )
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.status, ToolRunStatus.DISPATCHING)
        self.assertEqual(claimed.attempt_count, 1)

        with self.container.uow_factory() as uow:
            stale = uow.tool_runs.get(queued_run.id)
            dispatch_task = uow.dispatch_tasks.get(queued_run.id)
            self.assertIsNotNone(stale)
            self.assertIsNotNone(dispatch_task)
            stale.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            dispatch_task.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            uow.tool_runs.add(stale)
            uow.dispatch_tasks.add(dispatch_task)
            uow.commit()

        recovered = self.container.dispatch_service.recover_abandoned_tasks(
            RecoverAbandonedDispatchTasksInput(
                owner_kind="tool_run",
                reason="Worker lease expired before completion.",
            ),
        )
        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0].status, DispatchTaskStatus.QUEUED)

        persisted = self.container.tool_service.get_tool_run(queued_run.id)
        self.assertEqual(persisted.status, ToolRunStatus.QUEUED)
        self.assertEqual(persisted.error_message, "Worker lease expired before completion.")
        dispatch_task = self.container.dispatch_service.get_task(queued_run.id)
        self.assertEqual(dispatch_task.status, DispatchTaskStatus.QUEUED)

    def test_can_cancel_queued_background_run(self) -> None:
        self.container.tool_service.discover_local_tools()
        queued_run = asyncio.run(
            self.container.tool_service.execute(
                ExecuteToolInput(
                    tool_id="echo",
                    arguments={"message": "cancel me"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )

        cancelled = self.container.tool_service.cancel_tool_run(queued_run.id)

        self.assertEqual(cancelled.status, ToolRunStatus.CANCELLED)
        self.assertIsNotNone(cancelled.cancel_requested_at)
        dispatch_task = self.container.dispatch_service.get_task(queued_run.id)
        self.assertEqual(dispatch_task.status, DispatchTaskStatus.CANCELLED)
        self.assertIsNone(
            self.container.tool_service.process_next_queued_run(worker_id="worker-cancel"),
        )

    def test_running_background_run_can_be_cancel_requested(self) -> None:
        async def slow_echo(arguments: dict[str, object]) -> dict[str, object]:
            await asyncio.sleep(0.2)
            return {"message": arguments.get("message")}

        tool = self.container.tool_service.register(
            RegisterToolInput(
                id="slow_echo",
                name="Slow Echo",
                description="Sleeps before returning.",
                supported_modes=(ToolMode.BACKGROUND,),
                runtime_key="slow_echo",
            ),
        )
        self.container.local_tool_catalog.register(tool, slow_echo)

        queued_run = asyncio.run(
            self.container.tool_service.execute(
                ExecuteToolInput(
                    tool_id="slow_echo",
                    arguments={"message": "cancel later"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )

        worker_result: dict[str, object] = {}

        def run_worker() -> None:
            worker_result["run"] = self.container.tool_service.process_next_queued_run(
                worker_id="worker-slow",
            )

        thread = threading.Thread(target=run_worker)
        thread.start()

        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            current = self.container.tool_service.get_tool_run(queued_run.id)
            if current.status is ToolRunStatus.RUNNING:
                break
            time.sleep(0.01)
        else:
            self.fail("Tool run never reached RUNNING state.")

        requested = self.container.tool_service.cancel_tool_run(queued_run.id)
        self.assertEqual(requested.status, ToolRunStatus.CANCEL_REQUESTED)

        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertIn("run", worker_result)

        finished = self.container.tool_service.get_tool_run(queued_run.id)
        self.assertEqual(finished.status, ToolRunStatus.CANCELLED)
        self.assertIsNotNone(finished.cancel_requested_at)
        self.assertEqual(finished.attempt_count, 1)

    def test_enable_and_disable_tool(self) -> None:
        self.container.tool_service.register(
            RegisterToolInput(
                id="deploy",
                name="Deploy",
                description="Deploys a service.",
                mutates_state=True,
                enabled=False,
            ),
        )

        enabled = self.container.tool_service.set_availability(
            SetToolAvailabilityInput(id="deploy", enabled=True),
        )
        disabled = self.container.tool_service.set_availability(
            SetToolAvailabilityInput(id="deploy", enabled=False),
        )

        self.assertTrue(enabled.enabled)
        self.assertFalse(disabled.enabled)
        event_names = [
            event.name for event in self.container.event_bus.published_events[-2:]
        ]
        self.assertEqual(event_names, ["tool.enabled", "tool.disabled"])


if __name__ == "__main__":
    unittest.main()
