from __future__ import annotations

from dataclasses import fields
import inspect
from pathlib import Path
import re

from crxzipple.app import AppContainer, AppKey, AssemblyTarget
from crxzipple.app.assembly.runtime import runtime_plan
from crxzipple.modules.browser.interfaces.facade import BrowserInterfaceFacade


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKLIST_DOC = (
    REPO_ROOT
    / "docs"
    / "reports"
    / "module-lifecycle-tool-loading-checklist-20260513.md"
)
DEPENDENCY_MAP_DOC = (
    REPO_ROOT
    / "docs"
    / "reports"
    / "module-lifecycle-tool-loading-dependency-map-20260513.md"
)


def _normalized_doc(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def test_module_lifecycle_checklist_records_p0_forbidden_tool_loading_shapes() -> None:
    text = _normalized_doc(CHECKLIST_DOC)

    required_constraints = [
        "Module core 不持有 `container`、`PortResolver`、`SimpleNamespace` 或跨模块 lookup lambda。",
        "Runtime handler 不允许在执行时动态查 container、resolver、registry 或 owner module service。",
        "守卫：`src/crxzipple/modules/tool` 与 `tools/*` 的 handler 运行路径不得持有 `AppContainer`。",
        "守卫：tool handler 构造不得接收 `SimpleNamespace`、`PortResolver`、`container`、`resolver` 这类服务定位器对象。",
        "守卫：tool handler 执行路径不得出现 `orchestration_*_lookup` 延迟查询。",
        "守卫：`app/container.py` 中不得构造 `register_tool_namespaces(SimpleNamespace(...))`；只能由已命名的 tool package activation task 触发 apply。",
    ]

    for constraint in required_constraints:
        assert constraint in text


def test_dependency_map_captures_current_two_phase_scanned_tool_loading() -> None:
    text = _normalized_doc(DEPENDENCY_MAP_DOC)

    required_snapshot_points = [
        "discover_tool_namespaces()",
        "ToolPackageApplyContext(explicit dependency bindings, registries, settings)",
        "activate_tool_packages(...)",
        "app activation scanned package stage",
        "previous two-phase split has been removed from the runtime container path",
        "scan once, resolve dependencies once, apply local/openapi/runtime handlers once",
    ]

    for point in required_snapshot_points:
        assert point in text


def test_container_uses_single_scanned_tool_package_apply_hook() -> None:
    plan = runtime_plan()
    tool_activation_tasks = [
        task for task in plan.activation_tasks if task.key == "tool.activate_packages"
    ]
    app_tool_assembly = (
        REPO_ROOT / "src" / "crxzipple" / "app" / "assembly" / "tool.py"
    ).read_text(encoding="utf-8")
    app_tool_package_assembly = (
        REPO_ROOT / "src" / "crxzipple" / "app" / "assembly" / "tool_packages.py"
    ).read_text(encoding="utf-8")
    tool_packages = (
        REPO_ROOT
        / "src"
        / "crxzipple"
        / "modules"
        / "tool"
        / "infrastructure"
        / "tool_packages.py"
    ).read_text(encoding="utf-8")
    sandbox_worker = (
        REPO_ROOT
        / "src"
        / "crxzipple"
        / "modules"
        / "tool"
        / "infrastructure"
        / "runtimes"
        / "sandbox_worker.py"
    ).read_text(encoding="utf-8")

    assert len(tool_activation_tasks) == 1
    assert app_tool_package_assembly.count("apply_tool_package_plans(") == 1
    assert "register_tool_namespaces(" not in app_tool_assembly
    assert "def register_scanned_tool_packages(" not in tool_packages
    assert "register_scanned_tool_packages" not in sandbox_worker
    assert "include_local=False" not in app_tool_package_assembly
    assert "include_runtimes=False" not in app_tool_package_assembly


def test_modules_do_not_import_app_assembly_layer() -> None:
    violations: list[str] = []
    for path in sorted((REPO_ROOT / "src" / "crxzipple" / "modules").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if re.search(r"^\s*from crxzipple\.app\b", text, flags=re.MULTILINE):
            violations.append(str(path.relative_to(REPO_ROOT)))
        if re.search(r"^\s*import crxzipple\.app\b", text, flags=re.MULTILINE):
            violations.append(str(path.relative_to(REPO_ROOT)))

    assert violations == []


def test_browser_module_does_not_reintroduce_private_mcp_runtime() -> None:
    forbidden_terms = (
        "chrome-devtools-mcp",
        "ChromeMcpClientPool",
        "McpControlEngine",
        "McpBackedActionEngine",
        "build_mcp_client",
        "mcp_client",
    )
    violations: list[str] = []
    for path in sorted((REPO_ROOT / "src" / "crxzipple" / "modules" / "browser").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for term in forbidden_terms:
            if term in text:
                violations.append(f"{path.relative_to(REPO_ROOT)}: {term}")

    assert violations == []


def test_browser_runtime_resolves_proxy_secrets_only_through_access_provider() -> None:
    runtime_paths = (
        REPO_ROOT
        / "src"
        / "crxzipple"
        / "modules"
        / "browser"
        / "infrastructure"
        / "host_runner.py",
        REPO_ROOT
        / "src"
        / "crxzipple"
        / "modules"
        / "browser"
        / "infrastructure"
        / "proxy_adapter.py",
    )
    combined = "\n".join(path.read_text(encoding="utf-8") for path in runtime_paths)

    assert '"resolve_credential"' in combined
    assert "AccessConsumerRef(" in combined
    assert "os.environ" not in combined
    assert "os.getenv" not in combined
    assert "getenv(" not in combined
    assert "read_text(" not in combined


def test_browser_interface_facade_stays_thin_application_surface() -> None:
    public_methods = tuple(
        name
        for name, member in inspect.getmembers(BrowserInterfaceFacade, inspect.isfunction)
        if not name.startswith("_")
    )
    field_names = tuple(field.name for field in fields(BrowserInterfaceFacade))
    facade_source = (
        REPO_ROOT / "src" / "crxzipple" / "modules" / "browser" / "interfaces" / "facade.py"
    ).read_text(encoding="utf-8")

    assert public_methods == ("execute",)
    assert field_names == (
        "control_command_assembler",
        "page_action_assembler",
        "execution_coordinator",
        "profile_probe_service",
    )
    assert "daemon" not in facade_source.lower()
    assert "mcp" not in facade_source.lower()
    assert "cdp_url" not in facade_source
    assert "server_url" not in facade_source


def test_container_stays_as_composition_root_not_infrastructure_catalog() -> None:
    path = REPO_ROOT / "src" / "crxzipple" / "app" / "container.py"
    line_count = len(path.read_text(encoding="utf-8").splitlines())

    assert line_count <= 120


def test_tool_package_activation_declares_requirements_and_target_scope() -> None:
    plan = runtime_plan()
    factories = {factory.key: factory for factory in plan.factories}
    tasks = {task.key: task for task in plan.activation_tasks}

    tool_execution = factories["tool.execution_services"]
    tool_runtime_event = factories["tool.runtime_event_service"]
    tool_activation = tasks["tool.activate_packages"]

    assert AppKey.ACCESS_SERVICE in tool_execution.requires
    assert AppKey.DAEMON_SERVICE in tool_execution.requires
    assert AppKey.ARTIFACT_SERVICE in tool_execution.requires
    assert AppKey.TOOL_RUNTIME_GATEWAY in tool_execution.requires
    assert AppKey.TOOL_WORKER_SERVICE in tool_runtime_event.requires
    assert AppKey.TOOL_PACKAGE_PLANS in tool_activation.requires
    assert AppKey.TOOL_CAPABILITY_BINDINGS in tool_activation.requires
    assert AssemblyTarget.TOOL_WORKER in tool_activation.targets
    assert AssemblyTarget.ORCHESTRATION_EXECUTOR in tool_activation.targets
    assert AssemblyTarget.TOOL_SCHEDULER not in tool_activation.targets


def test_tool_execution_binding_assembly_lives_in_app_tool_assembly() -> None:
    app_runtime_assembly = (
        REPO_ROOT / "src" / "crxzipple" / "app" / "assembly" / "runtime.py"
    ).read_text(encoding="utf-8")
    app_tool_assembly = (
        REPO_ROOT / "src" / "crxzipple" / "app" / "assembly" / "tool.py"
    ).read_text(encoding="utf-8")
    app_tool_package_assembly = (
        REPO_ROOT / "src" / "crxzipple" / "app" / "assembly" / "tool_packages.py"
    ).read_text(encoding="utf-8")

    assert "def _runtime_tool_dependency_bindings(" not in app_runtime_assembly
    assert "ToolDependencyBinding(" not in app_runtime_assembly
    assert "ToolPackageApplyContext(" not in app_runtime_assembly
    assert "def build_tool_execution_capability_bindings(" in app_tool_package_assembly
    assert "def build_tool_execution_services(" in app_tool_assembly
    assert "artifact_service" in app_tool_package_assembly
    assert "browser_tool_application" in app_tool_package_assembly
    assert "mobile_facade" in app_tool_package_assembly
    assert "process_service" in app_tool_package_assembly
    assert "session_runtime_control" in app_tool_package_assembly


def test_orchestration_uses_tool_execution_port_before_tool_package_apply() -> None:
    plan = runtime_plan()
    factories = {factory.key: factory for factory in plan.factories}
    tasks = {task.key: task for task in plan.activation_tasks}
    factory_order = [factory.key for factory in plan.factories]
    app_orchestration_assembly = (
        REPO_ROOT
        / "src"
        / "crxzipple"
        / "app"
        / "assembly"
        / "orchestration.py"
    ).read_text(encoding="utf-8")

    tool_port = app_orchestration_assembly.index(
        "tool_port = ToolServiceAdapter(tool_service)",
    )
    tool_resolver = app_orchestration_assembly.index(
        "tool_resolver = ToolResolver(",
    )
    orchestration_engine = app_orchestration_assembly.index(
        "orchestration_engine = OrchestrationEngine(",
    )
    orchestration_graph = app_orchestration_assembly.index(
        "service_graph = OrchestrationServiceGraph(",
    )
    orchestration_block = app_orchestration_assembly[tool_port:orchestration_graph]

    assert (
        factory_order.index("tool.execution_services")
        < factory_order.index("orchestration.runtime")
    )
    assert AppKey.TOOL_SERVICE in factories["tool.execution_services"].provides
    assert AppKey.TOOL_ORCHESTRATION_PORT in factories["orchestration.runtime"].requires
    assert AppKey.TOOL_SERVICE not in factories["orchestration.runtime"].requires
    assert tasks["tool.activate_packages"].active_for(AssemblyTarget.ORCHESTRATION_EXECUTOR)
    assert tool_port < tool_resolver < orchestration_engine < orchestration_graph
    assert "tool_catalog=tool_port" in orchestration_block
    assert "tool_execution_port=tool_port" in orchestration_block
    assert "tool_infrastructure.local_runtime_registry" not in orchestration_block
    assert "tool_infrastructure.remote_tool_registry" not in orchestration_block


def test_app_container_does_not_expose_internal_tool_assembly_registries() -> None:
    assert set(AppContainer.__dataclass_fields__) == {"target", "registry"}

    key_values = {key.value for key in AppKey}
    forbidden_public_fields = [
        "tool_discovery_registry",
        "sandbox_tool_registry",
        "credential_provider",
        "channel_system_config",
        "browser_system_config",
        "browser_runtime_state_store",
        "browser_profile_probe_service",
        "mobile_system_config",
        "mobile_state_root",
        "mobile_runtime_state_store",
        "daemon_state_root",
        "daemon_spec_syncers",
    ]
    for field in forbidden_public_fields:
        assert field not in key_values


def test_operations_source_read_model_context_is_explicitly_typed() -> None:
    operations_assembly = (
        REPO_ROOT / "src" / "crxzipple" / "app" / "assembly" / "operations.py"
    ).read_text(encoding="utf-8")
    factory = (
        REPO_ROOT
        / "src"
        / "crxzipple"
        / "modules"
        / "operations"
        / "application"
        / "read_models"
        / "factory.py"
    ).read_text(encoding="utf-8")

    assert "from types import SimpleNamespace" not in operations_assembly
    assert "operations_projection_context = SimpleNamespace(" not in operations_assembly
    assert "OperationsSourceReadModelContext(" in operations_assembly
    assert "class OperationsSourceReadModelContext" in factory
    assert "def build_operations_source_read_model_provider(\n    context: OperationsSourceReadModelContext," in factory
    assert 'getattr(context, "settings_query_service"' not in factory
    assert 'getattr(container, "settings_query_service"' not in factory


def test_orchestration_does_not_reintroduce_retired_prompt_helpers() -> None:
    retired_paths = (
        "src/crxzipple/modules/orchestration/application/prompt_input_collectr.py",
        "src/crxzipple/modules/orchestration/application/memory_context.py",
        "src/crxzipple/modules/orchestration/application/workspace_context.py",
        "src/crxzipple/modules/orchestration/application/prompting/flow_prompts.py",
    )
    forbidden_terms = (
        "PromptAssembler",
        "load_workspace_context_files",
        "workspace_context_files",
        "build_available_tools_block",
        "recall_prompt_memories",
    )
    scanned_roots = (
        REPO_ROOT / "src" / "crxzipple" / "app" / "assembly",
        REPO_ROOT / "src" / "crxzipple" / "modules" / "orchestration",
    )
    violations: list[str] = []

    for relative_path in retired_paths:
        path = REPO_ROOT / relative_path
        if path.exists():
            violations.append(f"{relative_path}: retired file exists")

    for root in scanned_roots:
        for path in sorted(root.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for term in forbidden_terms:
                if term in text:
                    violations.append(f"{path.relative_to(REPO_ROOT)}: {term}")

    assert violations == []


def test_tool_handler_factory_deps_are_manifest_driven() -> None:
    tool_packages = (
        REPO_ROOT
        / "src"
        / "crxzipple"
        / "modules"
        / "tool"
        / "infrastructure"
        / "tool_packages.py"
    ).read_text(encoding="utf-8")
    openai_image_manifest = (
        REPO_ROOT / "tools" / "openai_image" / "tool.yaml"
    ).read_text(encoding="utf-8")
    openai_image_handler = (
        REPO_ROOT / "tools" / "openai_image" / "local.py"
    ).read_text(encoding="utf-8")

    assert 'binding.namespace != "openai_image"' not in tool_packages
    assert 'binding.namespace == "openai_image"' not in tool_packages
    assert "namespace: openai_image" in openai_image_manifest
    assert "id: credential_provider" in openai_image_manifest
    assert "kind: service_dependency" in openai_image_manifest
    assert "_legacy_deps" not in openai_image_handler
    assert "getattr(legacy" not in openai_image_handler
    assert "CredentialBindingRef(" in openai_image_handler
    assert "AccessConsumerRef(" in openai_image_handler
    assert "allow_literal=False" not in openai_image_handler
    assert "workspace_dir=workspace_dir" not in openai_image_handler
    assert "trace_context=" not in openai_image_handler

    memory_manifest = (REPO_ROOT / "tools" / "memory" / "tool.yaml").read_text(
        encoding="utf-8",
    )
    assert "namespace: memory" in memory_manifest
    assert "id: memory_runtime_service" in memory_manifest
    assert "id: file_memory_service" not in memory_manifest
    assert "id: memory_context_resolver" not in memory_manifest

    workspace_manifest = (REPO_ROOT / "tools" / "workspace" / "tool.yaml").read_text(
        encoding="utf-8",
    )
    command_manifest = (REPO_ROOT / "tools" / "command" / "tool.yaml").read_text(
        encoding="utf-8",
    )
    assert "id: session_workspace_lookup" in workspace_manifest
    assert "id: session_workspace_lookup" in command_manifest
    assert "id: process_service" in command_manifest

    sessions_manifest = (REPO_ROOT / "tools" / "sessions" / "tool.yaml").read_text(
        encoding="utf-8",
    )
    assert "id: session_service" in sessions_manifest
    assert "id: session_runtime_control" in sessions_manifest
    assert "id: orchestration_run_query_service" not in sessions_manifest
    assert "id: orchestration_cancellation_service" not in sessions_manifest
    assert "id: orchestration_scheduler_service" not in sessions_manifest

    skills_manifest = (REPO_ROOT / "tools" / "skills" / "tool.yaml").read_text(
        encoding="utf-8",
    )
    assert "id: local_runtime_registry" not in skills_manifest
    assert "tool_catalog.read" not in skills_manifest
    assert "id: skill_manager" in skills_manifest

    mobile_manifest = (REPO_ROOT / "tools" / "mobile" / "tool.yaml").read_text(
        encoding="utf-8",
    )
    assert "id: mobile_facade" in mobile_manifest
    assert "id: mobile_result_serializer" in mobile_manifest

    browser_manifest = REPO_ROOT / "tools" / "browser" / "tool.yaml"
    app_tool_assembly = (
        REPO_ROOT / "src" / "crxzipple" / "app" / "assembly" / "tool.py"
    ).read_text(encoding="utf-8")
    browser_manifest_text = browser_manifest.read_text(encoding="utf-8")
    browser_local = (REPO_ROOT / "tools" / "browser" / "local.py").read_text(
        encoding="utf-8",
    )
    assert browser_manifest.exists()
    assert "def _register_browser_tool_source_catalog" not in app_tool_assembly
    assert "register_browser_tool_source_catalog" not in app_tool_assembly
    assert "namespace: browser" in browser_manifest_text
    assert "bundled.local_package.browser" in browser_manifest_text
    assert "browser-profile-runtime" in browser_manifest_text
    assert "tools.browser.local:create_browser_manifest_handler" in browser_manifest_text
    assert "def create_browser_manifest_handler" in browser_local
    assert "browser_tool_application" in browser_manifest_text
    assert "browser_system_config_store" in browser_manifest_text


def test_tool_handler_runtime_paths_do_not_hold_service_locator_objects() -> None:
    scanned_paths = [
        *sorted((REPO_ROOT / "tools").glob("*/local.py")),
        *sorted((REPO_ROOT / "tools").glob("*/remote.py")),
        *sorted((REPO_ROOT / "tools").glob("*/sandbox.py")),
        *sorted(
            (
                REPO_ROOT
                / "src"
                / "crxzipple"
                / "modules"
                / "tool"
                / "infrastructure"
                / "runtimes"
            ).glob("*.py"),
        ),
    ]
    forbidden_patterns = {
        "AppContainer": re.compile(r"\bAppContainer\b"),
        "SimpleNamespace": re.compile(r"\bSimpleNamespace\b"),
        "PortResolver": re.compile(r"\bPortResolver\b"),
        "ToolHandlerFactoryDeps": re.compile(r"\bToolHandlerFactoryDeps\b"),
        "require_service": re.compile(r"\brequire_service\b"),
        "container_attribute": re.compile(r"\bcontainer\."),
        "container_argument": re.compile(r"\bcontainer\s*="),
        "orchestration_lookup": re.compile(r"\borchestration_.*_lookup\b"),
    }
    violations: list[str] = []
    for path in scanned_paths:
        text = path.read_text(encoding="utf-8")
        for label, pattern in forbidden_patterns.items():
            if pattern.search(text):
                violations.append(f"{path.relative_to(REPO_ROOT)}: {label}")

    assert violations == []


def test_local_browser_tool_handlers_do_not_direct_read_daemon_or_cdp_runtime() -> None:
    scanned_paths = sorted((REPO_ROOT / "tools" / "browser").glob("*.py"))
    forbidden_patterns = {
        "DaemonInstance": re.compile(r"\bDaemonInstance\b"),
        "daemon_service": re.compile(r"\bdaemon_service\b"),
        "daemon_manager": re.compile(r"\bdaemon_manager\b"),
        "host_browser_service": re.compile(r"\bhost:browser:"),
        "mcp_browser_service": re.compile(r"\bmcp:browser:"),
        "cdp_url": re.compile(r"\bcdp_url\b"),
        "server_url": re.compile(r"\bserver_url\b"),
    }
    violations: list[str] = []
    for path in scanned_paths:
        text = path.read_text(encoding="utf-8")
        for label, pattern in forbidden_patterns.items():
            if pattern.search(text):
                violations.append(f"{path.relative_to(REPO_ROOT)}: {label}")

    assert violations == []


def test_dependency_map_lists_current_handler_service_locator_surface() -> None:
    text = _normalized_doc(DEPENDENCY_MAP_DOC)

    required_dependencies = [
        "`credential_provider` / Access service",
        "`memory_runtime_service`",
        "`process_service`",
        "`session_service`",
        "`session_runtime_control`",
        "`session_workspace_lookup`",
        "`skill_manager`",
        "`browser_*` services and serializers",
        "`mobile_*` services and serializers",
    ]

    for dependency in required_dependencies:
        assert dependency in text


def test_dependency_map_tracks_p7_as_non_failing_plan_guards() -> None:
    text = _normalized_doc(DEPENDENCY_MAP_DOC)

    required_plan_guards = [
        "Architecture tests now guard both governance text and the production app assembly shape",
        "Tool namespaces are scanned once.",
        "handlers are applied once.",
        "Duplicate tool id or namespace registration fails fast",
        "OpenAI image handlers receive a typed dependency object with `credential_provider`",
        "Missing required internal service dependencies fail activation",
        "Missing external credentials such as `openai-api-key` appear as setup readiness state",
        "HTTP readiness and run submission agree for tools with missing Access requirements",
        "Orchestration construction depends on `ToolExecutionPort`",
        "startup happen after readiness checks",
    ]

    for guard in required_plan_guards:
        assert guard in text


def test_checklist_records_p3_done_and_p4_p5_remaining_acceptance_scope() -> None:
    text = _normalized_doc(CHECKLIST_DOC)

    required_review_points = [
        "P4 生产代码已落地",
        "Tool scanned package 已从两段装载收成单次 apply hook。",
        "`app/assembly/tool_packages.py` 统一保留 `ToolPackageApplyContext` 与",
        "`OpenAIImageDeps(credential_provider=...)` 这类 typed deps 是目标形态",
        "Tool execution path 已接入 `ToolAccessReadinessPort`",
        "Tool execution path 已接入 `ToolRuntimeReadinessPort`",
        "Access 负责 binding/readiness/setup 真相",
        "OAuth account credential binding 已纳入同一 Tool readiness 门禁",
        "DaemonServiceToolRuntimeReadinessAdapter",
        "Required internal service dependency 已在 Tool package apply 阶段 fail-fast",
        "Browser 工具目录已收敛为 `bundled.local_package.browser` source 下的 `browser.*`",
        "Operations Tool 风险表已读取合并 Tool readiness",
        "typed deps 迁移完成后，architecture tests 应从文档守卫升级为生产代码守卫",
    ]

    for point in required_review_points:
        assert point in text


def test_dependency_map_records_handler_lookup_migration_surface() -> None:
    text = _normalized_doc(DEPENDENCY_MAP_DOC)

    required_migration_points = [
        "P4 implementation has landed for the app assembly path",
        "`ToolPackageApplyContext`",
        "`ResolvedToolPackageActivation`",
        "Sessions tools use the `session_runtime_control` port",
        "Handler factories declare required internal service dependencies before apply.",
        "Handler factories receive typed dependency objects or explicit fields, not `SimpleNamespace`, `PortResolver`, `container`, or `resolver`.",
        "`session_runtime_control`",
        "Missing required internal dependencies fail during resolve/apply",
        "Missing internal service dependencies fail activation and prevent worker or orchestration executor startup.",
        "Missing Access credential/access requirements produce Tool readiness states before execution is queued.",
        "Missing OAuth account/token readiness is covered through Access credential binding checks.",
        "Missing daemon readiness now produces catalog/readiness states such as `setup_needed` or `degraded`",
        "Missing daemon runtime readiness is reported before execution is queued",
        "Operations Tool risk rows classify Access and Runtime readiness separately.",
    ]

    for point in required_migration_points:
        assert point in text
