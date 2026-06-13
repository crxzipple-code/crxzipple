from __future__ import annotations

import os
import sqlite3
from unittest.mock import patch

from crxzipple.interfaces.runtime_container import AppKey
from tests.unit.browser_tool_package_support import browser_function_catalog_candidates
from crxzipple.modules.tool.domain import (
    ToolDefinitionOrigin,
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolKind,
    ToolMode,
    ToolParameter,
)
from crxzipple.shared.domain.events import Event

from tests.unit.tool_test_support import ToolTestCaseBase


class ToolCatalogTestCase(ToolTestCaseBase):
    def test_catalog_reads_rich_tool_function_record(self) -> None:
        tool = self.seed_tool(
            tool_id="web_search",
            name="Web Search",
            description="Searches external knowledge sources.",
            kind=ToolKind.HTTP,
            parameters=(
                ToolParameter(
                    name="query",
                    data_type="string",
                    description="Search query text.",
                ),
                ToolParameter(
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
            definition_origin=ToolDefinitionOrigin.REMOTE_DISCOVERY,
            runtime_key="search.http",
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
        self.assertEqual(tool.definition_origin, ToolDefinitionOrigin.REMOTE_DISCOVERY)
        self.assertEqual(tool.runtime_key, "search.http")

        resolved = self.tool_service.get_tool("web_search")
        self.assertEqual(resolved.kind, ToolKind.HTTP)
        self.assertEqual(resolved.tags, ("search", "external"))
        self.assertEqual(resolved.execution_policy.timeout_seconds, 45)
        self.assertEqual(
            resolved.execution_support.supported_environments,
            (ToolEnvironment.LOCAL, ToolEnvironment.REMOTE),
        )

    def test_list_enabled_tools_respects_availability(self) -> None:
        self.seed_tool(
            tool_id="read_docs",
            name="Read Docs",
            description="Reads internal documentation.",
        )
        self.seed_tool(
            tool_id="dangerous_write",
            name="Dangerous Write",
            description="Writes to external systems.",
            mutates_state=True,
            enabled=False,
        )

        enabled_tools = self.tool_service.list_enabled_tools()

        enabled_ids = [tool.id for tool in enabled_tools]
        self.assertIn("read_docs", enabled_ids)
        self.assertNotIn("dangerous_write", enabled_ids)
        self.assertIn("memory_search", enabled_ids)
        self.assertIn("memory_write_daily", enabled_ids)
        self.assertIn("mobile_script", enabled_ids)
        self.assertIn("mobile_snapshot", enabled_ids)
        self.assertIn("mobile_tap", enabled_ids)
        self.assertIn("mobile_swipe", enabled_ids)
        self.assertIn("session_status", enabled_ids)
        self.assertIn("sessions_list", enabled_ids)
        self.assertIn("sessions_history", enabled_ids)
        self.assertIn("sessions_send", enabled_ids)
        self.assertIn("sessions_spawn", enabled_ids)
        self.assertIn("subagents", enabled_ids)
        self.assertIn("sessions_stop", enabled_ids)
        self.assertIn("sessions_yield", enabled_ids)
        self.assertNotIn("mobile_session", enabled_ids)

    def test_catalog_service_has_no_runtime_discovery_entrypoints(self) -> None:
        self.assertFalse(hasattr(self.tool_service.catalog_service, "discover_tools"))
        self.assertFalse(
            hasattr(self.tool_service.catalog_service, "list_discovery_providers"),
        )

        self.tool_service.list_enabled_tools()
        self.tool_service.list_enabled_tools()

    def test_runtime_pool_filters_access_readiness_for_call_context(self) -> None:
        runtime_context = {"caller": "tool-worker", "agent_id": "assistant"}

        with patch.dict(os.environ, {}, clear=True):
            blocked_ids = {
                tool.id
                for tool in self.tool_service.list_runtime_pool_tools(
                    runtime_context=runtime_context,
                )
            }
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-openai-key"}, clear=True):
            ready_ids = {
                tool.id
                for tool in self.tool_service.list_runtime_pool_tools(
                    runtime_context=runtime_context,
                )
            }

        self.assertNotIn("openai_image_generate", blocked_ids)
        self.assertNotIn("openai_image_edit", blocked_ids)
        self.assertIn("openai_image_generate", ready_ids)
        self.assertIn("openai_image_edit", ready_ids)

    def test_fresh_schema_omits_legacy_tools_table(self) -> None:
        database_path = self.harness.database_url.removeprefix("sqlite:///")

        with sqlite3.connect(database_path) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'",
                )
            }

        self.assertNotIn("tools", tables)
        self.assertIn("tool_runs", tables)
        self.assertIn("tool_run_assignments", tables)
        self.assertIn("tool_workers", tables)

    def test_list_tools_uses_runtime_system_managed_definition(self) -> None:
        tools = {
            tool.id: tool
            for tool in self.tool_service.list_tools()
        }

        persisted = tools["memory_write_daily"]
        self.assertEqual(
            persisted.description,
            "Append a durable markdown note to the current daily memory file.",
        )
        self.assertIn("surface:interactive", persisted.tags)
        self.assertIn("surface:maintenance_write", persisted.tags)

    def test_catalog_excludes_retired_legacy_memory_get_tool(self) -> None:
        managed_tools = self.tool_service.list_tools()

        self.assertIn("memory_search", [tool.id for tool in managed_tools])
        self.assertNotIn(
            "memory_get",
            [tool.id for tool in self.tool_service.list_tools()],
        )

    def test_get_tool_returns_local_package_memory_search_tool(self) -> None:
        tool = self.tool_service.get_tool("memory_search")

        self.assertEqual(tool.id, "memory_search")
        self.assertIn("system-managed", tool.tags)
        self.assertEqual(tool.context_requirements, ("agent_id",))

    def test_runtime_pool_filters_tools_missing_declared_context(self) -> None:
        without_agent = {
            tool.id
            for tool in self.tool_service.list_runtime_pool_tools(
                runtime_context={"caller": "orchestration"},
            )
        }
        with_agent = {
            tool.id
            for tool in self.tool_service.list_runtime_pool_tools(
                runtime_context={"caller": "orchestration", "agent_id": "assistant"},
            )
        }

        self.assertNotIn("memory_search", without_agent)
        self.assertNotIn("memory_write_daily", without_agent)
        self.assertIn("memory_search", with_agent)
        self.assertIn("memory_write_daily", with_agent)

    def test_tool_readiness_reports_missing_context_requirement(self) -> None:
        missing = self.tool_service.check_readiness("memory_search")
        ready = self.tool_service.check_readiness(
            "memory_search",
            agent_id="assistant",
        )

        self.assertFalse(missing["ready"])
        self.assertEqual(missing["status"], "setup_needed")
        self.assertEqual(missing["checks"][0]["category"], "context")
        self.assertEqual(missing["checks"][0]["requirement"], "agent_id")
        self.assertTrue(ready["ready"])

    def test_build_tool_surface_groups_ready_functions_by_source_prompt(self) -> None:
        source_id = "test.local_package.workspace_runtime"
        self.seed_tool(
            tool_id="surface_read",
            name="Surface Read",
            description="Read workspace content.",
            source_id=source_id,
            tags=("surface:interactive",),
        )
        self.seed_tool(
            tool_id="surface_write",
            name="Surface Write",
            description="Write workspace content.",
            source_id=source_id,
            mutates_state=True,
            tags=("surface:interactive",),
        )
        self.seed_tool(
            tool_id="surface_hidden",
            name="Surface Hidden",
            description="Hidden by runtime pool.",
            source_id=source_id,
            enabled=False,
        )
        with self.uow_factory() as uow:
            source = uow.tool_sources.get(source_id)
            self.assertIsNotNone(source)
            source.config = {
                **source.config,
                "prompt": {
                    "title": "Workspace Runtime",
                    "summary": "Workspace tool surface.",
                    "groups": {
                        "read": {
                            "title": "Read",
                            "summary": "Read-only tools.",
                            "function_ids": ["surface_read"],
                            "order": 10,
                            "default_expanded": True,
                        },
                        "write": {
                            "title": "Write",
                            "summary": "Mutation tools.",
                            "function_ids": ["surface_write"],
                            "order": 20,
                        },
                    },
                },
            }
            uow.tool_sources.upsert(source)
            uow.commit()

        surface = self.tool_service.build_tool_surface(
            session_id="session-1",
            run_id="run-1",
            agent_id="assistant",
            surface_id="tool_surface:test",
        )

        self.assertEqual(surface.surface_id, "tool_surface:test")
        self.assertEqual(surface.session_id, "session-1")
        surface_source = next(
            source
            for source in surface.sources
            if source.source_id == source_id
        )
        self.assertEqual(surface_source.title, "Workspace Runtime")
        self.assertEqual(
            [group.group_key for group in surface_source.groups],
            ["read", "write"],
        )
        self.assertEqual(surface_source.groups[0].function_refs, ("surface_read",))
        self.assertEqual(surface_source.groups[1].function_refs, ("surface_write",))
        functions = {
            function.function_id: function
            for function in surface.functions
            if function.source_id == source_id
        }
        self.assertEqual(functions["surface_read"].group_key, "read")
        self.assertEqual(functions["surface_write"].group_key, "write")
        self.assertTrue(functions["surface_read"].readiness["ready"])
        self.assertTrue(functions["surface_write"].mutates_state)
        self.assertNotIn("surface_hidden", functions)
        self.assertIn(
            "surface_hidden",
            [
                item["tool_id"]
                for item in surface.diagnostics["excluded"]
            ],
        )

    def test_build_tool_surface_can_persist_request_time_snapshot(self) -> None:
        source_id = "test.local_package.persisted_surface"
        self.seed_tool(
            tool_id="persisted_surface_read",
            name="Persisted Surface Read",
            description="Read from a persisted surface.",
            source_id=source_id,
            tags=("surface:interactive",),
        )
        self.seed_tool(
            tool_id="persisted_surface_hidden_from_request",
            name="Persisted Surface Hidden From Request",
            description="Available in runtime pool but not visible in this request.",
            source_id=source_id,
            tags=("surface:interactive",),
        )

        surface = self.tool_service.build_tool_surface(
            session_id="session-persist",
            run_id="run-persist",
            agent_id="assistant",
            surface_id="tool_surface:persisted",
            tool_ids=("persisted_surface_read",),
            persist=True,
        )

        with self.uow_factory() as uow:
            persisted = uow.tool_surfaces.get("tool_surface:persisted")
            by_run = uow.tool_surfaces.list_for_run("run-persist")

        self.assertEqual(surface.surface_id, "tool_surface:persisted")
        self.assertIsNotNone(persisted)
        assert persisted is not None
        self.assertEqual(persisted.surface_id, "tool_surface:persisted")
        self.assertEqual(persisted.session_id, "session-persist")
        self.assertEqual(persisted.run_id, "run-persist")
        self.assertEqual(persisted.agent_id, "assistant")
        self.assertEqual(persisted.estimate["function_count"], surface.estimate["function_count"])
        self.assertIn(
            "persisted_surface_read",
            [function.function_id for function in persisted.functions],
        )
        self.assertNotIn(
            "persisted_surface_hidden_from_request",
            [function.function_id for function in persisted.functions],
        )
        self.assertEqual(persisted.diagnostics["requested_tool_count"], 1)
        self.assertEqual([item.surface_id for item in by_run], ["tool_surface:persisted"])

    def test_get_tool_returns_workspace_read_tool_from_catalog(self) -> None:
        tool = self.tool_service.get_tool("read")

        self.assertEqual(tool.id, "read")
        self.assertEqual(tool.required_effect_ids, ("workspace_read",))
        self.assertIn("scope:workspace_bound", tool.tags)
        self.assertIn("system-managed", tool.tags)

    def test_get_tool_returns_workspace_write_tool_from_catalog(self) -> None:
        tool = self.tool_service.get_tool("write")

        self.assertEqual(tool.id, "write")
        self.assertEqual(tool.required_effect_ids, ("workspace_write",))
        self.assertTrue(tool.execution_policy.mutates_state)
        self.assertIn("scope:workspace_bound", tool.tags)
        self.assertIn("system-managed", tool.tags)

    def test_get_tool_returns_workspace_edit_tool_from_catalog(self) -> None:
        tool = self.tool_service.get_tool("edit")

        self.assertEqual(tool.id, "edit")
        self.assertEqual(tool.required_effect_ids, ("workspace_write",))
        self.assertTrue(tool.execution_policy.mutates_state)
        self.assertIn("scope:workspace_bound", tool.tags)
        self.assertIn("system-managed", tool.tags)

    def test_get_tool_returns_workspace_apply_patch_tool_from_catalog(self) -> None:
        tool = self.tool_service.get_tool("apply_patch")

        self.assertEqual(tool.id, "apply_patch")
        self.assertEqual(tool.required_effect_ids, ("workspace_write",))
        self.assertTrue(tool.execution_policy.mutates_state)
        self.assertIn("scope:workspace_bound", tool.tags)
        self.assertIn("system-managed", tool.tags)

    def test_get_tool_returns_workspace_exec_tool_from_catalog(self) -> None:
        tool = self.tool_service.get_tool("exec")

        self.assertEqual(tool.id, "exec")
        self.assertEqual(tool.required_effect_ids, ("command_execution",))
        self.assertTrue(tool.execution_policy.mutates_state)
        self.assertIn("system-managed", tool.tags)
        parameter_names = {param.name for param in tool.parameters}
        self.assertIn("max_output_tokens", parameter_names)
        self.assertIn("yield_time_ms", parameter_names)

    def test_get_tool_returns_background_process_tool_from_catalog(self) -> None:
        tool = self.tool_service.get_tool("process")

        self.assertEqual(tool.id, "process")
        self.assertEqual(tool.required_effect_ids, ("command_execution",))
        self.assertTrue(tool.execution_policy.mutates_state)
        self.assertIn("system-managed", tool.tags)

    def test_get_tool_returns_workspace_search_tool_from_catalog(self) -> None:
        tool = self.tool_service.get_tool("workspace_search")

        self.assertEqual(tool.id, "workspace_search")
        self.assertEqual(tool.required_effect_ids, ("workspace_read",))
        self.assertFalse(tool.execution_policy.mutates_state)
        self.assertIn("scope:workspace_bound", tool.tags)
        self.assertIn("system-managed", tool.tags)

    def test_get_tool_returns_mobile_snapshot_tool_from_local_package(self) -> None:
        tool = self.tool_service.get_tool("mobile_snapshot")

        self.assertEqual(tool.id, "mobile_snapshot")
        self.assertEqual(tool.runtime_key, "mobile_snapshot")
        self.assertIn("mobile", tool.tags)
        self.assertIn("system-managed", tool.tags)

    def test_browser_catalog_exposes_configured_runtime_functions(self) -> None:
        browser_tools = [
            tool
            for tool in self.tool_service.list_tools()
            if tool.id.startswith("browser.") or tool.id.startswith("mcp.browser")
        ]

        expected_ids = {
            candidate.function_id
            for candidate in browser_function_catalog_candidates()
        }
        self.assertEqual({tool.id for tool in browser_tools}, expected_ids)

        enabled_ids = {item.id for item in self.tool_service.list_enabled_tools()}
        self.assertTrue(expected_ids.issubset(enabled_ids))
        self.assertNotIn("mcp.browser", {tool.source_id for tool in browser_tools})
        self.assertNotIn("browser_cdp_raw", enabled_ids)
        self.assertNotIn("browser_network_inspect", enabled_ids)

        for tool in browser_tools:
            self.assertEqual(tool.source_id, "bundled.local_package.browser")
            self.assertEqual(tool.runtime_key, tool.id)
            self.assertEqual(tool.required_effect_ids, ("local_tool_access",))
            self.assertIn("browser", tool.tags)
            self.assertIn("system-managed", tool.tags)

    def test_get_tool_returns_session_status_tool_from_local_package(self) -> None:
        tool = self.tool_service.get_tool("session_status")

        self.assertEqual(tool.id, "session_status")
        self.assertEqual(tool.runtime_key, "session_status")
        self.assertIn("session", tool.tags)
        self.assertIn("system-managed", tool.tags)

    def test_get_tool_returns_workspace_list_tool_without_db_row(self) -> None:
        tool = self.tool_service.get_tool("workspace_list")

        self.assertEqual(tool.id, "workspace_list")
        self.assertEqual(tool.required_effect_ids, ("workspace_read",))
        self.assertFalse(tool.execution_policy.mutates_state)
        self.assertIn("scope:workspace_bound", tool.tags)
        self.assertIn("system-managed", tool.tags)

    def test_enable_and_disable_tool(self) -> None:
        self.seed_tool(
            tool_id="deploy",
            name="Deploy",
            description="Deploys a service.",
            mutates_state=True,
            enabled=False,
        )

        command_service = self.container.require(AppKey.TOOL_FUNCTION_COMMAND_SERVICE)
        enabled = command_service.set_function_enabled("deploy", enabled=True)
        self.assertTrue(enabled.function.enabled)
        disabled = command_service.set_function_enabled("deploy", enabled=False)

        self.assertFalse(disabled.function.enabled)
        event_names = [
            event.event_name
            for event in self.published_event_bus_events()
            if isinstance(event, Event) and bool(event.name)
        ][-2:]
        self.assertEqual(
            event_names,
            ["tool.function.enabled", "tool.function.disabled"],
        )
