from __future__ import annotations

from types import SimpleNamespace
import tempfile
from pathlib import Path
from unittest.mock import patch

from tools.browser.local import create_browser_manifest_handler
from crxzipple.interfaces.runtime_container import AppKey
from crxzipple.modules.browser.domain import BrowserValidationError
from crxzipple.modules.settings import CreateSettingsResourceInput
from crxzipple.modules.tool.application.activation import (
    ToolHandlerFactoryDeps,
    ToolPackageApplyContext,
    ToolOpenApiPlan,
    ToolPackagePlan,
    ToolRuntimePlan,
)
from crxzipple.modules.tool.application.catalog_models import (
    ToolFunctionCatalogRecord,
    ToolFunctionRuntimeKind,
    ToolSourceCatalogKind,
    ToolSourceCatalogRecord,
)
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.infrastructure import (
    activate_configured_provider_runtimes,
    apply_tool_package_plans,
    discover_tool_package_plans,
    load_tool_package_plan,
)
from tools.browser.local import (
    BrowserToolDeps,
    _augment_browser_error_with_guidance,
    _format_browser_action_trace_result,
)
from tests.unit.tool_test_support import (
    ExecuteToolInput,
    LocalToolRuntimeRegistry,
    McpProviderSettings,
    OpenApiCredentialBinding,
    OpenApiProviderSettings,
    SampleApiServer,
    SqliteTestHarness,
    ToolEnvironment,
    ToolKind,
    ToolNamespaceDefinition,
    ToolRunStatus,
    ToolRuntimeRegistry,
    ToolTestCaseBase,
    asyncio,
    discover_tool_namespaces,
    fixture_path,
    load_settings,
    openapi_fixture_path,
    os,
    replace,
    sys,
    tool_dependency_bindings,
)


def _browser_manifest_handlers(deps: BrowserToolDeps) -> dict[str, object]:
    services = {
        "browser_tool_application": deps.browser_tool_application,
        "browser_system_config_store": deps.browser_system_config_store,
        "browser_profile_resolver": deps.browser_profile_resolver,
        "browser_capabilities_resolver": deps.browser_capabilities_resolver,
        "browser_observation_service": deps.browser_observation_service,
        "settings": deps.settings,
        "artifact_service": deps.artifact_service,
        "browser_runtime_state_store": deps.browser_runtime_state_store,
        "browser_profile_probe_service": deps.browser_profile_probe_service,
        "browser_profile_allocator_service": deps.browser_profile_allocator_service,
    }
    handlers: dict[str, object] = {}
    for binding in load_tool_package_plan("tools/browser/tool.yaml").local_handlers:
        handler = create_browser_manifest_handler(
            ToolHandlerFactoryDeps(
                namespace="browser",
                tool_id=binding.tool.id,
                entrypoint=binding.entrypoint,
                services=services,
                config={},
                capability_ids=binding.capability_ids,
                requirements=binding.dependencies,
            ),
        )
        if handler is not None:
            handlers[binding.tool.id] = handler
    return handlers


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
                "metadata": {"source": "test_tool_providers"},
            },
            reason="seed sample OpenAPI Access bindings",
            publish=True,
            source="unit_test",
        ),
    )


class ToolProvidersTestCase(ToolTestCaseBase):
    def test_scanned_tool_packages_register_system_tools_without_bootstrap_hardcoding(self) -> None:
        namespaces = discover_tool_namespaces()

        self.assertEqual(
            [namespace.name for namespace in namespaces],
            [
                "brave_search",
                "browser",
                "command",
                "context_tree",
                "debug",
                "itick_market",
                "market_quote",
                "memory",
                "mobile",
                "open_meteo_geocoding",
                "open_meteo_weather",
                "openai_image",
                "sessions",
                "skills",
                "web",
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
                "local_package",
                "openapi",
                "local_package",
                "local_package",
                "local_package",
                "openapi",
                "openapi",
                "local_package",
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
            [0, 63, 2, 13, 1, 0, 1, 4, 9, 0, 0, 2, 8, 7, 2, 6],
        )
        self.assertEqual(
            [len(namespace.remote_bindings) for namespace in namespaces],
            [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        )
        self.assertEqual(
            [len(namespace.sandbox_bindings) for namespace in namespaces],
            [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        )

        plans = discover_tool_package_plans()
        self.assertTrue(all(isinstance(plan, ToolPackagePlan) for plan in plans))
        self.assertEqual(
            [plan.namespace for plan in plans],
            [ns.name for ns in namespaces],
        )
        self.assertTrue(all(plan.runtime_request for plan in plans))
        command_plan = next(plan for plan in plans if plan.namespace == "command")
        self.assertEqual(command_plan.runtime_request["title"], "Command Execution")
        self.assertIn("shell commands", command_plan.runtime_request["summary"])
        sessions_plan = next(plan for plan in plans if plan.namespace == "sessions")
        sessions_runtime_request_groups = sessions_plan.runtime_request["groups"]
        self.assertEqual(
            list(sessions_runtime_request_groups),
            [
                "state_history",
                "delegation",
                "session_tree",
                "run_control",
            ],
        )
        self.assertIn(
            "session-local execution history",
            sessions_runtime_request_groups["state_history"]["summary"],
        )
        self.assertIn(
            "delegated work should be cancelled",
            sessions_runtime_request_groups["session_tree"]["summary"],
        )
        self.assertEqual(
            sorted(
                function_id
                for group in sessions_runtime_request_groups.values()
                for function_id in group["function_ids"]
            ),
            sorted(handler.tool.id for handler in sessions_plan.local_handlers),
        )
        browser_plan = next(plan for plan in plans if plan.namespace == "browser")
        self.assertEqual(browser_plan.runtime_request["title"], "Browser Automation")
        self.assertEqual(len(browser_plan.local_handlers), 63)
        mobile_plan = next(plan for plan in plans if plan.namespace == "mobile")
        self.assertEqual(
            [dependency.id for dependency in mobile_plan.local_handlers[0].dependencies],
            ["mobile_facade", "mobile_result_serializer"],
        )
        self.assertTrue(
            all(
                dependency.required
                for dependency in mobile_plan.local_handlers[0].dependencies
            ),
        )
        debug_plan = next(plan for plan in plans if plan.namespace == "debug")
        self.assertTrue(
            all(isinstance(plan, ToolRuntimePlan) for plan in debug_plan.remote_runtimes),
        )
        self.assertEqual(debug_plan.remote_runtimes[0].runtime_kind, "remote")
        self.assertEqual(debug_plan.sandbox_runtimes[0].runtime_kind, "sandbox")
        brave_plan = next(plan for plan in plans if plan.namespace == "brave_search")
        self.assertEqual(brave_plan.package_kind, "openapi")
        self.assertEqual(
            brave_plan.capability_ids,
            ("bounded_network.http", "credential.read", "access.readiness"),
        )
        self.assertIsInstance(brave_plan.openapi, ToolOpenApiPlan)
        assert brave_plan.openapi is not None
        self.assertEqual(brave_plan.openapi.provider.name, "brave_search")
        skills_plan = next(plan for plan in plans if plan.namespace == "skills")
        self.assertEqual(
            [
                dependency.id
                for dependency in skills_plan.local_handlers[0].dependencies
            ],
            ["skill_manager"],
        )
        skill_authoring_handler = next(
            handler
            for handler in skills_plan.local_handlers
            if handler.tool.id == "skill_draft_create"
        )
        self.assertEqual(
            [dependency.id for dependency in skill_authoring_handler.dependencies],
            ["skill_manager", "skill_authoring_service"],
        )
        self.assertTrue(skill_authoring_handler.tool.execution_policy.mutates_state)
        self.assertEqual(
            skill_authoring_handler.tool.required_effect_ids,
            ("skill_authoring.create",),
        )
        skill_validate_handler = next(
            handler
            for handler in skills_plan.local_handlers
            if handler.tool.id == "skill_draft_validate"
        )
        self.assertTrue(skill_validate_handler.tool.execution_policy.mutates_state)
        self.assertEqual(
            skill_validate_handler.tool.required_effect_ids,
            ("skill_authoring.validate",),
        )
        skill_diff_handler = next(
            handler
            for handler in skills_plan.local_handlers
            if handler.tool.id == "skill_draft_diff"
        )
        self.assertTrue(skill_diff_handler.tool.execution_policy.mutates_state)
        self.assertEqual(
            skill_diff_handler.tool.required_effect_ids,
            ("skill_authoring.diff",),
        )
        skill_apply_handler = next(
            handler
            for handler in skills_plan.local_handlers
            if handler.tool.id == "skill_draft_apply"
        )
        self.assertTrue(skill_apply_handler.tool.execution_policy.requires_confirmation)
        self.assertTrue(skill_apply_handler.tool.execution_policy.mutates_state)
        self.assertEqual(
            skill_apply_handler.tool.required_effect_ids,
            ("skill_authoring.apply",),
        )

        catalog = LocalToolRuntimeRegistry()
        remote_registry = ToolRuntimeRegistry()
        sandbox_registry = ToolRuntimeRegistry()
        apply_tool_package_plans(
            ToolPackageApplyContext(
                local_runtime_registry=catalog,
                remote_tool_registry=remote_registry,
                sandbox_tool_registry=sandbox_registry,
                dependency_bindings=tool_dependency_bindings({
                    "artifact_service": self.artifact_service,
                    "context_tree_service": self.container.require(
                        AppKey.CONTEXT_TREE_SERVICE,
                    ),
                    "context_observation_snapshot_service": self.container.require(
                        AppKey.CONTEXT_OBSERVATION_SNAPSHOT_SERVICE,
                    ),
                    "credential_provider": self.access_service,
                    "memory_runtime_service": self.memory_runtime_service,
                    "process_service": self.process_service,
                    "session_service": self.session_service,
                    "session_workspace_lookup": lambda _session_key: "/tmp/workspace",
                    "session_runtime_control": object(),
                    "skill_manager": self.skill_manager,
                    "skill_authoring_service": self.skill_manager,
                    "mobile_facade": object(),
                    "mobile_result_serializer": object(),
                }),
            ),
            plans,
        )

        registered_ids = [tool.id for tool in catalog.list_registered_tools()]
        self.assertEqual(
            sorted(registered_ids),
            sorted(
                [
                    "echo",
                    "capability.search",
                    "context_tree.collapse",
                    "context_tree.diff_since",
                    "context_tree.disable_tool_schema",
                    "context_tree.enable_tool_schema",
                    "context_tree.estimate",
                    "context_tree.expand",
                    "context_tree.list",
                    "context_tree.pin",
                    "context_tree.read_snapshot",
                    "context_tree.render_current",
                    "context_tree.update_plan",
                    "context_tree.unpin",
                    "apply_patch",
                    "exec",
                    "process",
                    "market_quote.gold_spot",
                    "memory_flush_skip",
                    "memory_read",
                    "memory_search",
                    "memory_write_daily",
                    "mobile_devices",
                    "mobile_press",
                    "mobile_screenshot",
                    "mobile_script",
                    "mobile_snapshot",
                    "mobile_swipe",
                    "mobile_tap",
                    "mobile_type",
                    "mobile_wait",
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
                    "skill_draft_apply",
                    "skill_draft_create",
                    "skill_draft_diff",
                    "skill_draft_reject",
                    "skill_draft_update",
                    "skill_draft_validate",
                    "skill_read",
                    "web.fetch_json",
                    "web.fetch_text",
                    "workspace_list",
                    "write",
                    "workspace_search",
                ],
            ),
        )
        self.assertIsNotNone(remote_registry.get_handler("remote.echo"))
        self.assertIsNotNone(sandbox_registry.get_handler("sandbox.echo"))

    def test_local_package_credential_requirements_reject_direct_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package_dir = Path(temp_dir) / "direct_credential"
            package_dir.mkdir()
            manifest_path = package_dir / "tool.yaml"
            manifest_path.write_text(
                """
kind: local_package
namespace: direct_credential
local_tools:
  - id: direct_credential_demo
    name: Direct Credential Demo
    description: Invalid direct source binding.
    provider_name: local
    entrypoint: tools.direct_credential.local:run
    tool_kind: function
    parameters: []
    credential_requirements:
      - requirements:
          - slot: demo_api_key
            expected_kind: api_key
            binding_id: env:DEMO_API_KEY
            provider: demo
    supported_modes: [inline]
    supported_strategies: [async]
    supported_environments: [local]
    runtime_key: direct_credential_demo
""".lstrip(),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ToolValidationError, "direct credential source"):
                load_tool_package_plan(manifest_path)

    def test_browser_tool_package_manifest_is_standard_source_contract(self) -> None:
        plan = load_tool_package_plan(
            Path(__file__).resolve().parents[2] / "tools" / "browser" / "tool.yaml",
        )

        self.assertEqual(plan.namespace, "browser")
        self.assertEqual(plan.kind, "local_package")
        self.assertEqual(len(plan.local_bindings), 63)
        self.assertEqual(
            plan.runtime_request["groups"]["navigation"]["default_tool_schema_source"],
            "bundled.local_package.browser.runtime_request_group.navigation",
        )

    def test_mobile_tool_package_fails_fast_without_required_runtime_services(self) -> None:
        mobile_plan = load_tool_package_plan(
            Path(__file__).resolve().parents[2] / "tools" / "mobile" / "tool.yaml",
        )

        with self.assertRaisesRegex(
            ToolValidationError,
            "requires service dependency 'mobile_facade'",
        ):
            apply_tool_package_plans(
                ToolPackageApplyContext(local_runtime_registry=LocalToolRuntimeRegistry()),
                (mobile_plan,),
            )

    def test_skills_tool_package_fails_fast_without_required_skill_manager(self) -> None:
        skills_plan = load_tool_package_plan(
            Path(__file__).resolve().parents[2] / "tools" / "skills" / "tool.yaml",
        )

        with self.assertRaisesRegex(
            ToolValidationError,
            "requires service dependency 'skill_manager'",
        ):
            apply_tool_package_plans(
                ToolPackageApplyContext(
                    local_runtime_registry=LocalToolRuntimeRegistry(),
                ),
                (skills_plan,),
            )

    def test_local_package_activation_uses_active_catalog_runtime_refs(self) -> None:
        skills_plan = load_tool_package_plan(
            Path(__file__).resolve().parents[2] / "tools" / "skills" / "tool.yaml",
        )
        disabled_catalog = LocalToolRuntimeRegistry()

        apply_tool_package_plans(
            ToolPackageApplyContext(
                local_runtime_registry=disabled_catalog,
                local_function_refs_by_namespace={"skills": ()},
                dependency_bindings=tool_dependency_bindings(
                    {
                        "skill_manager": self.skill_manager,
                        "skill_authoring_service": self.skill_manager,
                    },
                ),
            ),
            (skills_plan,),
        )

        self.assertIsNone(disabled_catalog.get_handler("skill_read"))

        active_catalog = LocalToolRuntimeRegistry()
        apply_tool_package_plans(
            ToolPackageApplyContext(
                local_runtime_registry=active_catalog,
                local_function_refs_by_namespace={"skills": ("skill_read",)},
                dependency_bindings=tool_dependency_bindings(
                    {
                        "skill_manager": self.skill_manager,
                        "skill_authoring_service": self.skill_manager,
                    },
                ),
            ),
            (skills_plan,),
        )

        self.assertIsNotNone(active_catalog.get_handler("skill_read"))

    def test_sessions_tool_package_fails_fast_without_session_runtime_control(
        self,
    ) -> None:
        sessions_plan = load_tool_package_plan(
            Path(__file__).resolve().parents[2] / "tools" / "sessions" / "tool.yaml",
        )

        with self.assertRaisesRegex(
            ToolValidationError,
            "requires service dependency 'session_runtime_control'",
        ):
            apply_tool_package_plans(
                ToolPackageApplyContext(
                    local_runtime_registry=LocalToolRuntimeRegistry(),
                    dependency_bindings=tool_dependency_bindings(
                        {"session_service": self.session_service},
                    ),
                ),
                (sessions_plan,),
            )

    def test_tool_package_apply_rejects_duplicate_namespaces(self) -> None:
        debug_plan = load_tool_package_plan(
            Path(__file__).resolve().parents[2] / "tools" / "debug" / "tool.yaml",
        )

        with self.assertRaisesRegex(ToolValidationError, "Duplicate tool namespace"):
            apply_tool_package_plans(
                ToolPackageApplyContext(local_runtime_registry=LocalToolRuntimeRegistry()),
                (debug_plan, debug_plan),
            )

    def test_tool_package_apply_rejects_duplicate_tool_ids(self) -> None:
        debug_plan = load_tool_package_plan(
            Path(__file__).resolve().parents[2] / "tools" / "debug" / "tool.yaml",
        )
        duplicate_tool_plan = ToolPackagePlan(
            namespace="debug_duplicate_tools",
            root_path=debug_plan.root_path,
            manifest_path=debug_plan.manifest_path,
            package_kind="local_package",
            local_handlers=debug_plan.local_handlers,
        )

        with self.assertRaisesRegex(ToolValidationError, "Duplicate tool id"):
            apply_tool_package_plans(
                ToolPackageApplyContext(local_runtime_registry=LocalToolRuntimeRegistry()),
                (debug_plan, duplicate_tool_plan),
            )

    def test_tool_package_apply_rejects_duplicate_runtime_keys(self) -> None:
        debug_plan = load_tool_package_plan(
            Path(__file__).resolve().parents[2] / "tools" / "debug" / "tool.yaml",
        )
        duplicate_runtime_plan = ToolPackagePlan(
            namespace="debug_duplicate_runtimes",
            root_path=debug_plan.root_path,
            manifest_path=debug_plan.manifest_path,
            package_kind="local_package",
            remote_runtimes=debug_plan.remote_runtimes,
        )

        with self.assertRaisesRegex(ToolValidationError, "Duplicate tool runtime"):
            apply_tool_package_plans(
                ToolPackageApplyContext(remote_tool_registry=ToolRuntimeRegistry()),
                (debug_plan, duplicate_runtime_plan),
                include_local=False,
            )

    def test_tool_runtime_registry_rejects_duplicate_runtime_keys(self) -> None:
        async def _runtime_handler(**_kwargs):  # noqa: ANN202
            return {}

        debug_plan = load_tool_package_plan(
            Path(__file__).resolve().parents[2] / "tools" / "debug" / "tool.yaml",
        )
        tool = debug_plan.local_handlers[0].tool
        catalog = LocalToolRuntimeRegistry()
        catalog.register(tool, lambda **_kwargs: {})

        runtime_registry = ToolRuntimeRegistry()
        runtime_registry.register("debug.duplicate", _runtime_handler)
        with self.assertRaisesRegex(ValueError, "already registered"):
            runtime_registry.register("debug.duplicate", _runtime_handler)

    def test_configured_openapi_runtime_activation_uses_persisted_function_metadata(
        self,
    ) -> None:
        source = ToolSourceCatalogRecord(
            source_id="configured.openapi.sample_api",
            kind=ToolSourceCatalogKind.OPENAPI,
            display_name="Sample API",
            config={
                "source": "configured_tool_provider",
                "provider": {
                    "name": "sample_api",
                    "spec_location": "/path/that/must/not/be/read.json",
                    "base_url": "http://127.0.0.1:1",
                    "timeout_seconds": 5,
                    "max_concurrency": 3,
                },
            },
        )
        function = ToolFunctionCatalogRecord(
            function_id="sample_api.echo_message",
            source_id=source.source_id,
            stable_key="openapi.sample_api.echo_message",
            name="Echo Message",
            description="Echo a message.",
            input_schema={
                "type": "object",
                "properties": {"message": {"type": "string"}},
            },
            runtime_kind=ToolFunctionRuntimeKind.OPENAPI,
            handler_ref="openapi.sample_api.echo_message",
            metadata={
                "openapi_operation": {
                    "provider_name": "sample_api",
                    "method": "get",
                    "path_template": "/echo",
                    "base_url": "http://127.0.0.1:1",
                    "timeout_seconds": 5,
                    "path_parameters": [],
                    "query_parameters": ["message"],
                    "body_required": False,
                    "tags": [],
                    "security_schemes": [],
                    "security_requirements": [],
                    "credential_bindings": [],
                    "required_effect_ids": [],
                },
            },
        )
        registry = ToolRuntimeRegistry()

        activate_configured_provider_runtimes(
            sources=(source,),
            functions_by_source={source.source_id: (function,)},
            remote_runtime_registry=registry,
            credential_provider=object(),
            default_max_concurrency=9,
        )

        registration = registry.get_registration("openapi.sample_api.echo_message")
        self.assertIsNotNone(registration)
        assert registration is not None
        self.assertEqual(registration.concurrency_key, "openapi:sample_api")
        self.assertEqual(registration.max_concurrency, 3)

    def test_browser_source_activation_registers_profile_context_catalog(self) -> None:
        source_query = self.container.require(AppKey.TOOL_SOURCE_QUERY_SERVICE)
        source = source_query.get_source("bundled.local_package.browser")

        self.assertIsNotNone(source)
        assert source is not None
        self.assertEqual(source.kind, ToolSourceCatalogKind.LOCAL_PACKAGE)
        self.assertEqual(source.display_name, "Browser")
        self.assertEqual(source.config["source"], "bundled_tool_package")
        self.assertEqual(source.config["namespace"], "browser")
        self.assertEqual(source.config["package_kind"], "local_package")
        runtime_request = source.config["runtime_request"]
        self.assertEqual(runtime_request["title"], "Browser Automation")
        self.assertIn("not just a DOM snapshot tool", runtime_request["summary"])
        self.assertIn("verifiable browser facts", runtime_request["summary"])
        self.assertIn("Avoid repeated tab inventory", runtime_request["summary"])
        self.assertIn("groups", runtime_request)
        runtime_request_groups = runtime_request["groups"]
        self.assertIn("navigation", runtime_request_groups)
        self.assertIn("network", runtime_request_groups)
        self.assertEqual(
            runtime_request_groups["navigation"]["default_tool_schema_ids"],
            ["browser.navigate"],
        )
        self.assertEqual(runtime_request_groups["navigation"]["default_tool_schema_max_count"], 1)
        self.assertIn(
            "not a repeated pre-flight check",
            runtime_request_groups["navigation"]["summary"],
        )
        self.assertIn("date/calendar pickers", runtime_request_groups["forms_overlays"]["summary"])
        self.assertIn("live frontend scripts", runtime_request_groups["code_insight"]["summary"])
        self.assertIn("script/code search as an index", runtime_request_groups["code_insight"]["summary"])
        self.assertIn("browser.evaluate", runtime_request_groups["code_insight"]["summary"])
        self.assertIn("observable evidence", runtime_request_groups["diagnostics"]["summary"])
        self.assertEqual(
            runtime_request_groups["observation"]["default_tool_schema_ids"],
            ["browser.observe"],
        )
        self.assertEqual(runtime_request_groups["network"]["default_tool_schema_max_count"], 6)
        self.assertNotIn(
            "browser.evaluate",
            runtime_request_groups["page_interaction"]["function_ids"],
        )
        self.assertIn("browser.evaluate", runtime_request_groups["code_insight"]["function_ids"])
        self.assertIn(
            "browser.evaluate",
            runtime_request_groups["code_insight"]["default_tool_schema_ids"],
        )
        self.assertEqual(runtime_request_groups["code_insight"]["default_tool_schema_max_count"], 6)

        source_ids = {item.source_id for item in source_query.list_sources()}
        self.assertIn("bundled.local_package.browser", source_ids)
        self.assertNotIn("configured.mcp.browser_user", source_ids)
        self.assertNotIn("configured.mcp.browser_crxzipple", source_ids)

        functions = source_query.list_functions(source_id="bundled.local_package.browser")
        function_ids = sorted(function.function_id for function in functions)
        self.assertEqual(
            function_ids,
            [
                "browser.action.trace",
                "browser.click",
                "browser.code.search",
                "browser.context.acquire",
                "browser.context.current",
                "browser.context.heartbeat",
                "browser.context.reconcile",
                "browser.context.release",
                "browser.diagnostics.collect",
                "browser.dom.box_model",
                "browser.dom.clickability",
                "browser.dom.computed_style",
                "browser.dom.highlight",
                "browser.dom.inspect",
                "browser.dom.mutation_wait",
                "browser.emulation.reset",
                "browser.emulation.set",
                "browser.evaluate",
                "browser.form.fill",
                "browser.form.inspect",
                "browser.geolocation.set",
                "browser.native.run",
                "browser.navigate",
                "browser.network.clear_capture",
                "browser.network.fetch_as_page",
                "browser.network.get_request",
                "browser.network.get_request_body",
                "browser.network.get_response_body",
                "browser.network.inspect",
                "browser.network.list_requests",
                "browser.network.replay_request",
                "browser.network.start_capture",
                "browser.network.stop_capture",
                "browser.network_conditions.set",
                "browser.observe",
                "browser.overlay.observe",
                "browser.overlay.select",
                "browser.page.errors",
                "browser.page.lifecycle",
                "browser.performance.metrics",
                "browser.permissions.clear",
                "browser.permissions.grant",
                "browser.runtime.inspect",
                "browser.screenshot",
                "browser.script.extract_request",
                "browser.script.find_request",
                "browser.script.inspect",
                "browser.script.list",
                "browser.service_worker.inspect",
                "browser.service_worker.list",
                "browser.snapshot",
                "browser.storage.cache.get",
                "browser.storage.cache.list",
                "browser.storage.indexeddb.get",
                "browser.storage.indexeddb.list",
                "browser.storage.indexeddb.query",
                "browser.tabs.close",
                "browser.tabs.list",
                "browser.tabs.select",
                "browser.trace.export",
                "browser.trace.start",
                "browser.trace.stop",
                "browser.type",
            ],
        )
        functions_by_id = {function.function_id: function for function in functions}
        self.assertIn(
            "The snapshot is only a first pass",
            functions_by_id["browser.observe"].description,
        )
        self.assertIn(
            "Use as a quick map",
            functions_by_id["browser.snapshot"].description,
        )
        self.assertIn(
            "endpoint discovered from scripts or network captures",
            functions_by_id["browser.network.fetch_as_page"].description,
        )
        self.assertIn(
            "small bounded matching snippets",
            functions_by_id["browser.code.search"].description,
        )
        code_search_schema = functions_by_id["browser.code.search"].input_schema[
            "properties"
        ]
        self.assertEqual(code_search_schema["limit"]["maximum"], 12)
        self.assertEqual(code_search_schema["limit"]["default"], 8)
        self.assertEqual(code_search_schema["max_scripts"]["maximum"], 24)
        self.assertEqual(code_search_schema["context_lines"]["maximum"], 2)
        self.assertIn(
            "script index",
            functions_by_id["browser.code.search"].description,
        )
        find_request_schema = functions_by_id["browser.script.find_request"].input_schema[
            "properties"
        ]
        self.assertEqual(find_request_schema["limit"]["maximum"], 20)
        self.assertEqual(find_request_schema["max_scripts"]["maximum"], 32)
        self.assertEqual(find_request_schema["context_lines"]["maximum"], 2)
        script_inspect_schema = functions_by_id["browser.script.inspect"].input_schema[
            "properties"
        ]
        self.assertIn("column", script_inspect_schema)
        self.assertEqual(script_inspect_schema["column_window"]["maximum"], 8000)
        self.assertIn(
            "line and column",
            functions_by_id["browser.script.inspect"].description,
        )
        extract_schema = functions_by_id["browser.script.extract_request"].input_schema[
            "properties"
        ]
        self.assertEqual(extract_schema["limit"]["maximum"], 20)
        self.assertEqual(extract_schema["line_count"]["maximum"], 40)
        self.assertEqual(extract_schema["column_window"]["maximum"], 16000)
        self.assertIn(
            "endpoint, HTTP method",
            functions_by_id["browser.script.extract_request"].description,
        )
        self.assertNotIn("browser.runtime.probe_client", functions_by_id)
        self.assertNotIn("browser.runtime.call_client", functions_by_id)
        for function in functions:
            self.assertEqual(function.runtime_kind, ToolFunctionRuntimeKind.LOCAL)
            self.assertEqual(function.source_id, "bundled.local_package.browser")
            self.assertTrue(function.function_id.startswith("browser."))
            self.assertIn("profile", function.input_schema["properties"])
            self.assertIn("profile_pool", function.input_schema["properties"])
            profile_description = function.input_schema["properties"]["profile"][
                "description"
            ]
            self.assertIn("Omit this for normal browser work", profile_description)
            self.assertIn("'default' is not a profile name", profile_description)
            self.assertEqual(
                function.requirements.runtime_requirement_sets,
                (("browser-profile-runtime",),),
            )
            self.assertFalse(function.handler_ref.startswith("mcp."))
            self.assertFalse(function.function_id.startswith("mcp.browser_"))
            for requirement_set in function.requirements.runtime_requirement_sets:
                self.assertFalse(
                    any(
                        requirement.startswith("daemon:mcp:browser:")
                        for requirement in requirement_set
                    ),
                )
        registry = self.container.require(AppKey.TOOL_LOCAL_RUNTIME_REGISTRY)
        for runtime_key in function_ids:
            self.assertIsNotNone(registry.get_handler(runtime_key))
        self.assertIsNone(registry.get_handler("browser_snapshot"))
        runtime_request_group_function_ids = sorted(
            function_id
            for group in runtime_request_groups.values()
            for function_id in group["function_ids"]
        )
        self.assertEqual(runtime_request_group_function_ids, function_ids)
        bundles = source_query.list_runtime_request_bundles(tuple(function_ids))
        self.assertEqual(len(bundles), 1)
        self.assertEqual(bundles[0].title, "Browser Automation")
        self.assertEqual(
            [group.group_key for group in bundles[0].groups],
            [
                "navigation",
                "observation",
                "code_insight",
                "network",
                "action_trace",
                "native_script",
                "forms_overlays",
                "dom_inspection",
                "page_interaction",
                "storage",
                "context_leases",
                "environment",
                "diagnostics",
            ],
        )
        browser_tool = self.container.require(AppKey.TOOL_QUERY_SERVICE).get_tool(
            "browser.snapshot",
        )
        self.assertEqual(browser_tool.source_id, "bundled.local_package.browser")
        self.assertIn("browser.page_action", browser_tool.capability_ids)

    def test_browser_profile_default_error_guides_agent_to_omit_profile(self) -> None:
        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(
                    default_profile="crxzipple",
                    profiles=(SimpleNamespace(name="crxzipple"),),
                )

        deps = BrowserToolDeps(
            browser_tool_application=object(),
            browser_system_config_store=_Store(),
            browser_profile_resolver=object(),
            browser_capabilities_resolver=object(),
            settings=SimpleNamespace(browser_enabled=True),
        )

        error = _augment_browser_error_with_guidance(
            deps=deps,
            profile_name="default",
            exc=BrowserValidationError("Browser profile 'default' is not configured."),
        )

        self.assertIn("omit the profile argument", str(error))
        self.assertIn("browser default profile 'crxzipple'", str(error))
        self.assertIn("'default' is not a Browser profile name", str(error))

    def test_browser_ref_error_guides_agent_to_refresh_refs(self) -> None:
        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(
                    default_profile="crxzipple",
                    profiles=(SimpleNamespace(name="crxzipple"),),
                )

        deps = BrowserToolDeps(
            browser_tool_application=object(),
            browser_system_config_store=_Store(),
            browser_profile_resolver=object(),
            browser_capabilities_resolver=object(),
            settings=SimpleNamespace(browser_enabled=True),
        )

        error = _augment_browser_error_with_guidance(
            deps=deps,
            profile_name="crxzipple",
            exc=BrowserValidationError(
                "Browser ref 'r999' was not found for tab 'tab-1'.",
            ),
        )

        self.assertIn("run browser.observe", str(error))
        self.assertIn("fresh ref", str(error))
        self.assertIn("browser.dom.clickability", str(error))
        self.assertNotIn("use-profile", str(error))

    def test_browser_runtime_handlers_report_public_function_id(self) -> None:
        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _BrowserToolApplication:
            def execute_control(self, **_kwargs):  # noqa: ANN003, ANN201
                return SimpleNamespace(payload={"ok": True}, runtime_metadata={})

            def execute_page_action(self, **_kwargs):  # noqa: ANN003, ANN201
                return SimpleNamespace(payload={"ok": True}, runtime_metadata={})

        class _BrowserObservationService:
            def observe(self, **_kwargs):  # noqa: ANN003, ANN201
                return SimpleNamespace(
                    payload={"ok": True, "kind": "observe", "message": "observed"},
                    runtime_metadata={},
                )

        deps = BrowserToolDeps(
            browser_tool_application=_BrowserToolApplication(),
            browser_system_config_store=_Store(),
            browser_profile_resolver=object(),
            browser_capabilities_resolver=object(),
            browser_observation_service=_BrowserObservationService(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handlers = _browser_manifest_handlers(deps)

        cases = {
            "browser.observe": {},
            "browser.form.inspect": {},
            "browser.form.fill": {"ref": "r1", "text": "Kunming"},
            "browser.overlay.observe": {},
            "browser.overlay.select": {"ref": "r2", "overlay_source_ref": "r1"},
            "browser.action.trace": {"action": "click", "ref": "r1"},
            "browser.native.run": {
                "actions": [
                    {"kind": "fill", "selector": "#depart", "text": "昆明"},
                    {"kind": "wait", "text": "昆明 中国 KMG"},
                    {"kind": "click", "selector": "text=昆明 中国 KMG"},
                ],
            },
            "browser.navigate": {"url": "https://example.com"},
            "browser.click": {"ref": "r1"},
            "browser.dom.inspect": {"ref": "r1"},
            "browser.emulation.set": {"width": 390, "height": 844},
            "browser.diagnostics.collect": {},
            "browser.runtime.inspect": {},
            "browser.script.list": {},
            "browser.script.find_request": {"path": "/api/flights/search"},
            "browser.code.search": {"query": "fetch"},
            "browser.script.extract_request": {"script_id": "1", "query": "fetch"},
            "browser.script.inspect": {"script_id": "1"},
            "browser.network.inspect": {"limit": 10},
            "browser.snapshot": {},
            "browser.tabs.list": {},
        }
        for runtime_key, arguments in cases.items():
            with self.subTest(runtime_key=runtime_key):
                result = asyncio.run(handlers[runtime_key](arguments))

                self.assertEqual(result.metadata["tool"], runtime_key)

    def test_browser_action_envelope_is_visible_to_agent(self) -> None:
        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _BrowserToolApplication:
            def execute_page_action(self, **_kwargs):  # noqa: ANN003, ANN201
                return SimpleNamespace(
                    payload={
                        "ok": True,
                        "target_id": "tab-1",
                        "message": (
                            "Executed click via cdp-backed-playwright; "
                            "no observable page effect."
                        ),
                        "command": {"family": "page-action", "kind": "click"},
                        "value": {
                            "action_envelope": {
                                "kind": "click",
                                "tool_ok": True,
                                "page_effect_ok": False,
                                "page_effect_status": "no_observable_change",
                                "before": {
                                    "target_id": "tab-1",
                                    "url": "https://example.com/form",
                                    "title": "Example Form",
                                },
                                "after": {
                                    "target_id": "tab-1",
                                    "url": "https://example.com/form",
                                    "title": "Example Form",
                                },
                                "changes": {},
                                "result": {"mode": "direct"},
                                "next_action": "use-action-trace-or-observe",
                                "errors": [],
                            },
                        },
                    },
                    runtime_metadata={},
                )

        class _BrowserObservationService:
            def observe(self, **_kwargs):  # noqa: ANN003, ANN201
                return SimpleNamespace(payload={"ok": True}, runtime_metadata={})

        deps = BrowserToolDeps(
            browser_tool_application=_BrowserToolApplication(),
            browser_system_config_store=_Store(),
            browser_profile_resolver=object(),
            browser_capabilities_resolver=object(),
            browser_observation_service=_BrowserObservationService(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handlers = _browser_manifest_handlers(deps)

        result = asyncio.run(handlers["browser.click"]({"target_id": "tab-1", "ref": "r1"}))

        self.assertEqual(result.metadata["tool"], "browser.click")
        self.assertEqual(len(result.blocks), 1)
        text = result.blocks[0]["text"]
        self.assertIn("Browser click completed.", text)
        self.assertIn("- Tool: ok", text)
        self.assertIn("- Page effect: no observable change", text)
        self.assertIn("url=https://example.com/form", text)
        self.assertIn(
            "- Next: use browser.action.trace or browser.observe to verify the next step",
            text,
        )
        self.assertNotIn("Evidence path:", text)
        self.assertNotIn("evidence_path_key", result.metadata["browser_evidence"])

    def test_browser_action_trace_handler_normalizes_wrapped_action_payload(self) -> None:
        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _BrowserToolApplication:
            def __init__(self) -> None:
                self.calls = []

            def execute_page_action(self, **kwargs):  # noqa: ANN003, ANN201
                self.calls.append(dict(kwargs))
                if kwargs["kind"] == "batch":
                    return SimpleNamespace(
                        payload={
                            "command": {"kind": "batch"},
                            "value": {
                                "result": {
                                    "kind": "batch",
                                    "stop_on_error": kwargs["payload"].get(
                                        "stop_on_error",
                                        True,
                                    ),
                                    "results": [],
                                }
                            },
                        },
                        runtime_metadata={},
                    )
                payload = {
                    "command": {"kind": kwargs["kind"]},
                    "value": {
                        "result": {
                            "kind": "action-trace",
                            "trace_id": "trace-query",
                            "profile_name": kwargs["profile_name"],
                            "target_id": kwargs["target_id"],
                            "action": {
                                "kind": kwargs["payload"]["action"],
                                "target": {
                                    "target_id": kwargs["target_id"],
                                    "ref": None,
                                    "selector": kwargs["selector"],
                                },
                                "payload": dict(kwargs["payload"]),
                                "ok": True,
                                "error": None,
                                "resolved_selector": kwargs["selector"],
                                "frame_path": [],
                                "result": {
                                    "kind": kwargs["payload"]["action"],
                                    "text": kwargs["payload"].get("text"),
                                },
                            },
                            "before": {
                                "format": "interactive",
                                "snapshot_preview": "- textbox \"Query\" [ref=r1]",
                            },
                            "after": {
                                "format": "interactive",
                                "snapshot_preview": "- textbox \"Query\" [ref=r1]",
                            },
                            "diff": {
                                "snapshot_changed": False,
                                "before_chars": 26,
                                "after_chars": 26,
                                "ref_count_delta": 0,
                            },
                            "console": {"before_count": 0, "after_count": 0, "new": []},
                            "page_errors": {
                                "before_count": 0,
                                "after_count": 0,
                                "new": [],
                            },
                            "network": {
                                "capture_id": None,
                                "started": False,
                                "stopped": False,
                                "request_count": 0,
                                "requests": [],
                                "errors": [],
                            },
                            "action_envelope": {
                                "kind": "type",
                                "tool_ok": True,
                                "page_effect_ok": False,
                                "page_effect_status": "no_observable_change",
                                "before": {},
                                "after": {},
                                "changes": {
                                    "snapshot_changed": False,
                                    "network_request_count": 0,
                                },
                                "result": {
                                    "recommendation": {
                                        "next_action": "observe-or-inspect-clickability",
                                    },
                                },
                                "next_action": "observe-or-inspect-clickability",
                                "errors": [],
                            },
                            "errors": [],
                        }
                    },
                }
                return SimpleNamespace(payload=payload, runtime_metadata={})

        class _BrowserObservationService:
            def observe(self, **_kwargs):  # noqa: ANN003, ANN201
                return SimpleNamespace(payload={"ok": True}, runtime_metadata={})

        app = _BrowserToolApplication()
        deps = BrowserToolDeps(
            browser_tool_application=app,
            browser_system_config_store=_Store(),
            browser_profile_resolver=object(),
            browser_capabilities_resolver=object(),
            browser_observation_service=_BrowserObservationService(),
            artifact_service=self.artifact_service,
            settings=SimpleNamespace(browser_enabled=True),
        )
        handlers = _browser_manifest_handlers(deps)

        result = asyncio.run(
            handlers["browser.action.trace"](
                {
                    "target_id": "tab-1",
                    "selector": "#query",
                    "action": "type",
                    "text": "Kunming",
                    "include_network": False,
                    "stabilize_ms": 0,
                }
            )
        )

        self.assertEqual(app.calls[-1]["kind"], "action-trace")
        self.assertEqual(app.calls[-1]["selector"], "#query")
        self.assertEqual(app.calls[-1]["payload"]["action"], "type")
        self.assertEqual(app.calls[-1]["payload"]["text"], "Kunming")
        self.assertFalse(app.calls[-1]["payload"]["include_network"])
        self.assertIn("Browser action trace", result.blocks[0]["text"])
        self.assertIn("- Page effect: no observable change", result.blocks[0]["text"])
        self.assertIn("- Next: observe-or-inspect-clickability", result.blocks[0]["text"])
        self.assertIn(
            "- Suggested tools: browser.observe, browser.dom.clickability, browser.dom.inspect",
            result.blocks[0]["text"],
        )
        self.assertNotIn("Evidence path:", result.blocks[0]["text"])
        self.assertEqual(len(result.blocks), 2)
        artifact_block = result.blocks[1]
        self.assertEqual(artifact_block["type"], "file_ref")
        self.assertEqual(artifact_block["mime_type"], "application/json")
        self.assertEqual(artifact_block["name"], "trace-query.json")
        artifact = self.artifact_service.get_artifact(artifact_block["artifact_id"])
        self.assertEqual(artifact.metadata["source"], "browser")
        self.assertEqual(artifact.metadata["attachment_kind"], "action-trace")
        self.assertEqual(artifact.metadata["trace_id"], "trace-query")

        asyncio.run(
            handlers["browser.form.fill"](
                {
                    "target_id": "tab-1",
                    "ref": "r2",
                    "text": "Shanghai",
                    "stabilize_ms": 0,
                }
            )
        )
        self.assertEqual(app.calls[-1]["kind"], "action-trace")
        self.assertEqual(app.calls[-1]["ref"], "r2")
        self.assertEqual(app.calls[-1]["payload"]["action"], "fill")
        self.assertEqual(app.calls[-1]["payload"]["text"], "Shanghai")
        self.assertTrue(app.calls[-1]["payload"]["include_network"])
        self.assertEqual(app.calls[-1]["payload"]["snapshot_limit"], 30)

        asyncio.run(
            handlers["browser.overlay.select"](
                {
                    "target_id": "tab-1",
                    "ref": "r8",
                    "overlay_source_ref": "r2",
                    "stabilize_ms": 0,
                }
            )
        )
        self.assertEqual(app.calls[-1]["kind"], "action-trace")
        self.assertEqual(app.calls[-1]["ref"], "r8")
        self.assertEqual(app.calls[-1]["payload"]["action"], "click")
        self.assertTrue(app.calls[-1]["payload"]["active_overlay"])
        self.assertEqual(
            app.calls[-1]["payload"]["action_payload"]["overlay_source_ref"],
            "r2",
        )
        self.assertTrue(app.calls[-1]["payload"]["action_payload"]["active_overlay"])

        asyncio.run(
            handlers["browser.native.run"](
                {
                    "target_id": "tab-1",
                    "actions": [
                        {"kind": "fill", "selector": "#depart", "text": "昆明"},
                        {"kind": "wait", "text": "昆明 中国 KMG"},
                    ],
                    "stop_on_error": True,
                }
            )
        )
        self.assertEqual(app.calls[-1]["kind"], "batch")
        self.assertEqual(app.calls[-1]["target_id"], "tab-1")
        self.assertEqual(
            app.calls[-1]["payload"]["actions"],
            [
                {"kind": "fill", "selector": "#depart", "text": "昆明"},
                {"kind": "wait", "text": "昆明 中国 KMG"},
            ],
        )
        self.assertTrue(app.calls[-1]["payload"]["stop_on_error"])

    def test_browser_action_trace_formatter_shows_effect_when_action_fails_after_change(
        self,
    ) -> None:
        text = _format_browser_action_trace_result(
            {
                "kind": "action-trace",
                "trace_id": "trace-link",
                "profile_name": "crxzipple",
                "target_id": "tab-1",
                "action": {
                    "kind": "click",
                    "ok": False,
                    "error": {
                        "type": "TimeoutError",
                        "message": "navigation wait timed out",
                    },
                },
                "diff": {
                    "snapshot_changed": True,
                    "before_chars": 28,
                    "after_chars": 363,
                    "ref_count_delta": 9,
                },
                "lifecycle": {
                    "changed": True,
                    "changed_fields": {
                        "url": {
                            "before": "https://example.com/",
                            "after": "https://www.iana.org/help/example-domains",
                        },
                    },
                },
                "recommendation": {
                    "next_action": "continue-from-after-snapshot",
                    "reason": (
                        "The wrapped page action reported failure, but page state "
                        "changed."
                    ),
                },
                "action_envelope": {
                    "kind": "click",
                    "tool_ok": False,
                    "page_effect_ok": True,
                    "page_effect_status": "action_failed_with_observed_effect",
                    "next_action": "continue-from-after-snapshot",
                    "errors": [
                        {
                            "type": "TimeoutError",
                            "message": "navigation wait timed out",
                        },
                    ],
                },
            },
        )

        self.assertIn(
            "- Page effect: observed change (action reported failure)",
            text,
        )
        self.assertIn("- Next: continue-from-after-snapshot", text)
        self.assertIn("- Suggested tools: browser.observe", text)

    def test_configured_mcp_runtime_activation_uses_persisted_function_metadata(
        self,
    ) -> None:
        source = ToolSourceCatalogRecord(
            source_id="configured.mcp.sample_mcp",
            kind=ToolSourceCatalogKind.MCP,
            display_name="Sample MCP",
            config={
                "source": "configured_tool_provider",
                "provider": {
                    "name": "sample_mcp",
                    "command": ["/path/that/must/not/start"],
                    "timeout_seconds": 5,
                    "max_concurrency": 4,
                },
            },
        )
        function = ToolFunctionCatalogRecord(
            function_id="sample_mcp.echo",
            source_id=source.source_id,
            stable_key="mcp.sample_mcp.echo",
            name="MCP Echo",
            description="Echo a message.",
            input_schema={
                "type": "object",
                "properties": {"message": {"type": "string"}},
            },
            runtime_kind=ToolFunctionRuntimeKind.MCP,
            handler_ref="mcp.sample_mcp.echo",
            metadata={
                "mcp_definition": {
                    "provider_name": "sample_mcp",
                    "tool_name": "echo",
                    "tags": ["mcp", "sample_mcp"],
                    "timeout_seconds": 5,
                    "mutates_state": False,
                    "required_effect_ids": [],
                },
            },
        )
        registry = ToolRuntimeRegistry()
        cleanup_callbacks: list[object] = []

        activate_configured_provider_runtimes(
            sources=(source,),
            functions_by_source={source.source_id: (function,)},
            remote_runtime_registry=registry,
            credential_provider=object(),
            default_max_concurrency=9,
            add_cleanup_callback=lambda _source, callback: cleanup_callbacks.append(
                callback,
            ),
        )

        registration = registry.get_registration("mcp.sample_mcp.echo")
        self.assertIsNotNone(registration)
        assert registration is not None
        self.assertEqual(registration.concurrency_key, "mcp:sample_mcp")
        self.assertEqual(registration.max_concurrency, 4)
        self.assertEqual(len(cleanup_callbacks), 1)
        for callback in cleanup_callbacks:
            callback()

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

        try:
            container = harness.build_runtime_container(settings=settings)
            _seed_sample_openapi_access_bindings(container)
            tool_service = container.require(AppKey.TOOL_SERVICE)
            source_query = container.require(AppKey.TOOL_SOURCE_QUERY_SERVICE)
            source = source_query.get_source("configured.openapi.sample_api")
            self.assertIsNotNone(source)
            assert source is not None
            self.assertEqual(source.kind.value, "openapi")
            self.assertEqual(source.last_discovery_status.value, "completed")
            listed_ids = [tool.id for tool in tool_service.list_tools()]
            self.assertIn("sample_api.echo_message", listed_ids)
            self.assertIn("sample_api.search_docs", listed_ids)
            remote_tool_registry = container.require(
                AppKey.TOOL_REMOTE_RUNTIME_REGISTRY,
            )

            discovered = [
                tool
                for tool in tool_service.list_tools()
                if tool.id.startswith("sample_api.")
            ]
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
            registration = remote_tool_registry.get_registration(
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
                    tool_service.execute(
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
                    tool_service.execute(
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
            container = harness.build_runtime_container(settings=settings)
            tool_service = container.require(AppKey.TOOL_SERVICE)
            source_query = container.require(AppKey.TOOL_SOURCE_QUERY_SERVICE)
            source = source_query.get_source("configured.mcp.sample_mcp")
            self.assertIsNotNone(source)
            assert source is not None
            self.assertEqual(source.kind.value, "mcp")
            self.assertEqual(source.last_discovery_status.value, "completed")
            listed_ids = [tool.id for tool in tool_service.list_tools()]
            self.assertIn("sample_mcp.echo", listed_ids)
            self.assertIn("sample_mcp.sum", listed_ids)
            remote_tool_registry = container.require(
                AppKey.TOOL_REMOTE_RUNTIME_REGISTRY,
            )

            discovered = [
                tool
                for tool in tool_service.list_tools()
                if tool.id.startswith("sample_mcp.")
            ]
            self.assertEqual(
                [tool.id for tool in discovered],
                ["sample_mcp.echo", "sample_mcp.sum"],
            )
            self.assertEqual(discovered[0].kind, ToolKind.MCP)
            self.assertEqual(
                discovered[0].execution_support.supported_environments,
                (ToolEnvironment.REMOTE,),
            )
            registration = remote_tool_registry.get_registration(
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
                    tool_service.execute(
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
                    tool_service.execute(
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
