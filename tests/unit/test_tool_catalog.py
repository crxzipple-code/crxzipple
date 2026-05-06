from __future__ import annotations

from crxzipple.modules.tool.application import ToolDiscoveryProviderDescriptor
from crxzipple.modules.tool.application.specifications import ToolSpec
from crxzipple.shared.domain.events import Event

from tests.unit.tool_test_support import *  # noqa: F403


class _CountingDiscoveryGateway:
    def __init__(
        self,
        *,
        specs_by_provider: dict[str, list[ToolSpec]] | None = None,
    ) -> None:
        self.calls: list[str | None] = []
        self.specs_by_provider = specs_by_provider or {}

    def list_providers(self) -> list[ToolDiscoveryProviderDescriptor]:
        return [
            ToolDiscoveryProviderDescriptor(
                name="local_builtin",
                description="Local builtins",
                source_kind=ToolSourceKind.LOCAL_DISCOVERY,
            ),
            ToolDiscoveryProviderDescriptor(
                name="local_filesystem",
                description="Local filesystem",
                source_kind=ToolSourceKind.LOCAL_DISCOVERY,
            ),
            ToolDiscoveryProviderDescriptor(
                name="sample_api",
                description="Sample API",
                source_kind=ToolSourceKind.REMOTE_REGISTRY,
            ),
        ]

    def discover(self, *, provider_name: str | None = None) -> list[ToolSpec]:
        self.calls.append(provider_name)
        if provider_name is None:
            specs: list[ToolSpec] = []
            for provider_specs in self.specs_by_provider.values():
                specs.extend(provider_specs)
            return specs
        return list(self.specs_by_provider.get(provider_name, []))


class ToolCatalogTestCase(ToolTestCaseBase):
    def test_registers_rich_tool_definition_without_persisting_definition(self) -> None:
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

        resolved = self.container.tool_service.get_tool("web_search")
        self.assertEqual(resolved.kind, ToolKind.HTTP)
        self.assertEqual(resolved.tags, ("search", "external"))
        self.assertEqual(resolved.execution_policy.timeout_seconds, 45)
        self.assertEqual(
            resolved.execution_support.supported_environments,
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

    def test_list_enabled_tools_refreshes_filesystem_discovery_once(self) -> None:
        gateway = _CountingDiscoveryGateway()
        self.container.tool_service.discovery_gateway = gateway

        self.container.tool_service.list_enabled_tools()
        self.container.tool_service.list_enabled_tools()

        self.assertEqual(gateway.calls, ["local_filesystem", "sample_api", "sample_api"])

    def test_explicit_filesystem_discovery_refreshes_after_hot_path_resolution(self) -> None:
        gateway = _CountingDiscoveryGateway()
        self.container.tool_service.discovery_gateway = gateway

        self.container.tool_service.list_enabled_tools()
        self.container.tool_service.discover_tools(provider_name="local_filesystem")
        self.container.tool_service.list_enabled_tools()

        self.assertEqual(
            gateway.calls,
            [
                "local_filesystem",
                "sample_api",
                "local_filesystem",
                "sample_api",
            ],
        )

    def test_discovers_local_tools_without_persisting_definitions(self) -> None:
        discovered = self.container.tool_service.discover_local_tools()

        self.assertEqual([tool.id for tool in discovered], ["echo"])
        self.assertEqual(discovered[0].source_kind, ToolSourceKind.LOCAL_DISCOVERY)
        self.assertEqual(discovered[0].runtime_key, "echo")

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
            for tool in self.container.tool_service.list_tools()
        }

        persisted = tools["memory_write_daily"]
        self.assertEqual(
            persisted.description,
            "Append a durable markdown note to the current daily memory file.",
        )
        self.assertIn("surface:interactive", persisted.tags)
        self.assertIn("surface:maintenance_write", persisted.tags)

    def test_ensure_local_system_tools_registered_excludes_legacy_memory_get(self) -> None:
        managed_tools = self.container.tool_service.ensure_local_system_tools_registered()

        self.assertIn("memory_search", [tool.id for tool in managed_tools])
        self.assertNotIn(
            "memory_get",
            [tool.id for tool in self.container.tool_service.list_tools()],
        )

    def test_get_tool_returns_runtime_system_managed_tool_without_db_row(self) -> None:
        tool = self.container.tool_service.get_tool("memory_search")

        self.assertEqual(tool.id, "memory_search")
        self.assertIn("system-managed", tool.tags)

    def test_get_tool_returns_workspace_read_tool_without_db_row(self) -> None:
        tool = self.container.tool_service.get_tool("read")

        self.assertEqual(tool.id, "read")
        self.assertEqual(tool.required_effect_ids, ("workspace_read",))
        self.assertIn("scope:workspace_bound", tool.tags)
        self.assertIn("system-managed", tool.tags)

    def test_get_tool_returns_workspace_write_tool_without_db_row(self) -> None:
        tool = self.container.tool_service.get_tool("write")

        self.assertEqual(tool.id, "write")
        self.assertEqual(tool.required_effect_ids, ("workspace_write",))
        self.assertTrue(tool.execution_policy.mutates_state)
        self.assertIn("scope:workspace_bound", tool.tags)
        self.assertIn("system-managed", tool.tags)

    def test_get_tool_returns_workspace_edit_tool_without_db_row(self) -> None:
        tool = self.container.tool_service.get_tool("edit")

        self.assertEqual(tool.id, "edit")
        self.assertEqual(tool.required_effect_ids, ("workspace_write",))
        self.assertTrue(tool.execution_policy.mutates_state)
        self.assertIn("scope:workspace_bound", tool.tags)
        self.assertIn("system-managed", tool.tags)

    def test_get_tool_returns_workspace_apply_patch_tool_without_db_row(self) -> None:
        tool = self.container.tool_service.get_tool("apply_patch")

        self.assertEqual(tool.id, "apply_patch")
        self.assertEqual(tool.required_effect_ids, ("workspace_write",))
        self.assertTrue(tool.execution_policy.mutates_state)
        self.assertIn("scope:workspace_bound", tool.tags)
        self.assertIn("system-managed", tool.tags)

    def test_get_tool_returns_workspace_exec_tool_without_db_row(self) -> None:
        tool = self.container.tool_service.get_tool("exec")

        self.assertEqual(tool.id, "exec")
        self.assertEqual(tool.required_effect_ids, ("command_execution",))
        self.assertTrue(tool.execution_policy.mutates_state)
        self.assertIn("system-managed", tool.tags)

    def test_get_tool_returns_background_process_tool_without_db_row(self) -> None:
        tool = self.container.tool_service.get_tool("process")

        self.assertEqual(tool.id, "process")
        self.assertEqual(tool.required_effect_ids, ("command_execution",))
        self.assertTrue(tool.execution_policy.mutates_state)
        self.assertIn("system-managed", tool.tags)

    def test_get_tool_returns_workspace_search_tool_without_db_row(self) -> None:
        tool = self.container.tool_service.get_tool("workspace_search")

        self.assertEqual(tool.id, "workspace_search")
        self.assertEqual(tool.required_effect_ids, ("workspace_read",))
        self.assertFalse(tool.execution_policy.mutates_state)
        self.assertIn("scope:workspace_bound", tool.tags)
        self.assertIn("system-managed", tool.tags)

    def test_get_tool_returns_mobile_snapshot_tool_from_local_package(self) -> None:
        tool = self.container.tool_service.get_tool("mobile_snapshot")

        self.assertEqual(tool.id, "mobile_snapshot")
        self.assertEqual(tool.runtime_key, "mobile_snapshot")
        self.assertIn("mobile", tool.tags)
        self.assertIn("system-managed", tool.tags)

    def test_get_tool_returns_session_status_tool_from_local_package(self) -> None:
        tool = self.container.tool_service.get_tool("session_status")

        self.assertEqual(tool.id, "session_status")
        self.assertEqual(tool.runtime_key, "session_status")
        self.assertIn("session", tool.tags)
        self.assertIn("system-managed", tool.tags)

    def test_get_tool_returns_workspace_list_tool_without_db_row(self) -> None:
        tool = self.container.tool_service.get_tool("workspace_list")

        self.assertEqual(tool.id, "workspace_list")
        self.assertEqual(tool.required_effect_ids, ("workspace_read",))
        self.assertFalse(tool.execution_policy.mutates_state)
        self.assertIn("scope:workspace_bound", tool.tags)
        self.assertIn("system-managed", tool.tags)

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
        self.assertTrue(enabled.enabled)
        disabled = self.container.tool_service.set_availability(
            SetToolAvailabilityInput(id="deploy", enabled=False),
        )

        self.assertFalse(disabled.enabled)
        event_names = [
            event.event_name
            for event in self.container.event_bus.published_events
            if isinstance(event, Event) and bool(event.name)
        ][-2:]
        self.assertEqual(event_names, ["tool.enabled", "tool.disabled"])
