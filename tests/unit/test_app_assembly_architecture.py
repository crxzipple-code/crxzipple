from __future__ import annotations

import ast
from pathlib import Path
import re

from crxzipple.app import AppKey


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = REPO_ROOT / "frontend" / "src"
PRODUCTION_SCAN_ROOTS = (
    REPO_ROOT / "src" / "crxzipple" / "app",
    REPO_ROOT / "src" / "crxzipple" / "interfaces",
    REPO_ROOT / "src" / "crxzipple" / "modules",
)
RUNTIME_LOOKUP_ROOTS = (
    REPO_ROOT / "src" / "crxzipple" / "interfaces",
    REPO_ROOT / "src" / "crxzipple" / "modules",
)


def _production_python_files(*roots: Path) -> list[Path]:
    return sorted(
        path
        for root in roots
        for path in ((root,) if root.is_file() and root.suffix == ".py" else root.rglob("*.py"))
    )


def _frontend_source_files() -> list[Path]:
    return sorted(
        path
        for path in FRONTEND_ROOT.rglob("*")
        if path.suffix in {".ts", ".vue"}
    )


def _forbidden_import_violations(
    roots: tuple[Path, ...],
    forbidden_modules: tuple[str, ...],
) -> list[str]:
    violations: list[str] = []
    for path in _production_python_files(*roots):
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            stripped = line.strip()
            if stripped.startswith("from ") and " import " in stripped:
                imported_module = stripped.removeprefix("from ").split(" import ", 1)[
                    0
                ].strip()
                for forbidden_module in forbidden_modules:
                    if (
                        imported_module == forbidden_module
                        or imported_module.startswith(f"{forbidden_module}.")
                    ):
                        violations.append(
                            f"{path.relative_to(REPO_ROOT)}:{line_number}: {stripped}",
                        )
            if stripped.startswith("import "):
                imported_modules = [
                    item.strip().split(" as ", 1)[0]
                    for item in stripped.removeprefix("import ").split(",")
                ]
                for imported_module in imported_modules:
                    for forbidden_module in forbidden_modules:
                        if (
                            imported_module == forbidden_module
                            or imported_module.startswith(f"{forbidden_module}.")
                        ):
                            violations.append(
                                f"{path.relative_to(REPO_ROOT)}:{line_number}: "
                                f"{stripped}",
                            )

    return violations


def test_production_entrypoints_do_not_import_old_bootstrap_container() -> None:
    forbidden_patterns = {
        "bootstrap facade import": re.compile(
            r"^\s*from\s+crxzipple\.bootstrap\s+import\b",
            flags=re.MULTILINE,
        ),
        "bootstrap module import": re.compile(
            r"^\s*import\s+crxzipple\.bootstrap\b",
            flags=re.MULTILINE,
        ),
        "old build_container call": re.compile(r"\bbuild_container\s*\("),
    }
    violations: list[str] = []
    for path in _production_python_files(*PRODUCTION_SCAN_ROOTS):
        text = path.read_text(encoding="utf-8")
        for label, pattern in forbidden_patterns.items():
            if pattern.search(text):
                violations.append(f"{path.relative_to(REPO_ROOT)}: {label}")

    assert violations == []


def test_runtime_entrypoints_use_explicit_appkey_lookups_only() -> None:
    allowed = re.compile(
        r"\bcontainer\.(?:require|get|has|snapshot)\s*\("
        r"|\bcontainer\.(?:target|registry)\b"
        r"|\bcontainer\.close\b",
    )
    container_access = re.compile(r"\bcontainer\.[A-Za-z_][A-Za-z0-9_]*")
    violations: list[str] = []
    for path in _production_python_files(*RUNTIME_LOOKUP_ROOTS):
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            match = container_access.search(line)
            if match and not allowed.search(line):
                violations.append(f"{path.relative_to(REPO_ROOT)}:{line_number}: {line.strip()}")

    assert violations == []


def test_runtime_container_has_no_attribute_compatibility_surface() -> None:
    container_text = (
        REPO_ROOT / "src" / "crxzipple" / "app" / "container.py"
    ).read_text(encoding="utf-8")
    registry_text = (
        REPO_ROOT / "src" / "crxzipple" / "app" / "registry.py"
    ).read_text(encoding="utf-8")

    assert "def __getattr__(" not in container_text
    assert "def __getattr__(" not in registry_text
    assert "setattr(" not in container_text
    assert "setattr(" not in registry_text


def test_orchestration_uses_runtime_request_draft_collector_not_legacy_surface_builder() -> None:
    violations: list[str] = []
    for path in _production_python_files(
        REPO_ROOT / "src" / "crxzipple" / "modules" / "orchestration",
        REPO_ROOT / "src" / "crxzipple" / "app" / "assembly" / "orchestration.py",
    ):
        text = path.read_text(encoding="utf-8")
        if "RuntimeLlmRequestDraftBuilder" in text:
            violations.append(str(path.relative_to(REPO_ROOT)))

    assert violations == []


def test_orchestration_application_does_not_embed_provider_specific_request_rendering() -> None:
    provider_specific_terms = (
        "openai",
        "codex",
        "anthropic",
        "gemini",
        "previous_response_id",
        "responses",
        "chat_completions",
    )
    allowed_paths: set[Path] = set()
    violations: list[str] = []
    for path in _production_python_files(
        REPO_ROOT / "src" / "crxzipple" / "modules" / "orchestration" / "application",
    ):
        relative = path.relative_to(REPO_ROOT)
        if relative in allowed_paths:
            continue
        text = path.read_text(encoding="utf-8").lower()
        for term in provider_specific_terms:
            if term in text:
                violations.append(f"{relative}: {term}")

    assert violations == []


def test_runtime_kernel_does_not_embed_generic_evidence_judges_or_task_specialization() -> None:
    judge_terms = (
        "EvidenceGate",
        "EvidenceOutcomeClassifier",
    )
    kernel_roots = (
        REPO_ROOT / "src" / "crxzipple" / "app" / "integration",
        REPO_ROOT / "src" / "crxzipple" / "modules" / "orchestration",
        REPO_ROOT / "src" / "crxzipple" / "modules" / "context_workspace",
        REPO_ROOT / "src" / "crxzipple" / "modules" / "llm",
    )
    task_patterns = {
        "east_china_airlines": re.compile(r"东航|ceair", flags=re.IGNORECASE),
        "flight_domain": re.compile(r"航班|airline", flags=re.IGNORECASE),
    }
    violations: list[str] = []
    for path in _production_python_files(*kernel_roots):
        relative = path.relative_to(REPO_ROOT)
        text = path.read_text(encoding="utf-8")
        for term in judge_terms:
            if term in text:
                violations.append(f"{relative}: {term}")
        for label, pattern in task_patterns.items():
            if pattern.search(text):
                violations.append(f"{relative}: {label}")

    assert violations == []


def test_browser_core_does_not_embed_task_specific_site_logic() -> None:
    task_patterns = {
        "east_china_airlines": re.compile(r"东航|东方航空|ceair", flags=re.IGNORECASE),
        "travel_booking_site": re.compile(r"携程|ctrip", flags=re.IGNORECASE),
        "flight_ticket_domain": re.compile(r"航班|机票", flags=re.IGNORECASE),
    }
    violations: list[str] = []
    for path in _production_python_files(
        REPO_ROOT / "src" / "crxzipple" / "modules" / "browser",
    ):
        relative = path.relative_to(REPO_ROOT)
        text = path.read_text(encoding="utf-8")
        for label, pattern in task_patterns.items():
            if pattern.search(text):
                violations.append(f"{relative}: {label}")

    assert violations == []


def test_session_module_does_not_store_provider_wire_transcript_semantics() -> None:
    provider_wire_terms = (
        "previous_response_id",
        "provider_request_payload",
        "provider_wire",
        "chat_completions",
        "responses.create",
        "openai",
        "codex",
        "anthropic",
        "gemini",
    )
    violations: list[str] = []
    for path in _production_python_files(
        REPO_ROOT / "src" / "crxzipple" / "modules" / "session",
    ):
        relative = path.relative_to(REPO_ROOT)
        text = path.read_text(encoding="utf-8").lower()
        for term in provider_wire_terms:
            if term in text:
                violations.append(f"{relative}: {term}")

    assert violations == []


def test_prompt_engine_retired_legacy_import_paths_do_not_return() -> None:
    retired_paths = (
        REPO_ROOT
        / "src"
        / "crxzipple"
        / "modules"
        / "orchestration"
        / "application"
        / "prompt_surface.py",
        REPO_ROOT
        / "src"
        / "crxzipple"
        / "app"
        / "integration"
        / "context_workspace_orchestration.py",
    )
    violations = [
        f"{path.relative_to(REPO_ROOT)}: retired file"
        for path in retired_paths
        if path.exists()
    ]

    violations.extend(
        _forbidden_import_violations(
            PRODUCTION_SCAN_ROOTS,
            ("crxzipple.modules.orchestration.application.prompt_surface",),
        ),
    )
    exact_retired_adapter_import = re.compile(
        r"^\s*from\s+crxzipple\.app\.integration\.context_workspace_orchestration\s+"
        r"import\b"
        r"|^\s*import\s+crxzipple\.app\.integration\.context_workspace_orchestration\s*$",
        flags=re.MULTILINE,
    )
    for path in _production_python_files(*PRODUCTION_SCAN_ROOTS):
        text = path.read_text(encoding="utf-8")
        if exact_retired_adapter_import.search(text):
            violations.append(
                f"{path.relative_to(REPO_ROOT)}: retired exact adapter import",
            )

    assert violations == []


def test_app_container_close_uses_only_registered_lifecycle_tasks() -> None:
    container_text = (
        REPO_ROOT / "src" / "crxzipple" / "app" / "container.py"
    ).read_text(encoding="utf-8")
    forbidden_resource_keys = (
        "TOOL_CLEANUP_CALLBACKS",
        "BROWSER_INFRASTRUCTURE",
        "PROCESS_SERVICE",
        "MEMORY_WATCH_REGISTRY",
        "EVENTS_SERVICE",
        "DATABASE_ENGINE",
    )

    assert "RUNTIME_CLEANUP_TASKS" in container_text
    for key in forbidden_resource_keys:
        assert key not in container_text


def test_app_assembly_does_not_construct_cross_module_orchestration_commands() -> None:
    assembly_root = REPO_ROOT / "src" / "crxzipple" / "app" / "assembly"
    forbidden = (
        "SubmitOrchestrationTurnInput",
        "SubmitBoundOrchestrationTurnInput",
        "AcceptOrchestrationRunInput",
        "InboundInstruction",
        "SessionRouteContext",
        "DirectSessionScope",
    )
    violations: list[str] = []
    for path in _production_python_files(assembly_root):
        text = path.read_text(encoding="utf-8")
        for name in forbidden:
            if re.search(rf"\b{re.escape(name)}\b", text):
                violations.append(f"{path.relative_to(REPO_ROOT)}: {name}")

    assert violations == []


def test_tool_enablement_truth_is_not_materialized_from_settings() -> None:
    forbidden = (
        "ToolEnablementService",
        "ToolEnablementConfig",
        "TOOL_ENABLEMENT_SERVICE",
        "tool_enablements(",
    )
    scan_roots = (
        REPO_ROOT / "src" / "crxzipple" / "app",
        REPO_ROOT / "src" / "crxzipple" / "modules" / "tool",
        REPO_ROOT / "src" / "crxzipple" / "modules" / "settings",
        REPO_ROOT / "src" / "crxzipple" / "shared" / "settings.py",
    )
    violations: list[str] = []
    for path in _production_python_files(*scan_roots):
        text = path.read_text(encoding="utf-8")
        for name in forbidden:
            if name in text:
                violations.append(f"{path.relative_to(REPO_ROOT)}: {name}")

    assert violations == []


def test_skill_enablement_truth_is_not_materialized_from_settings() -> None:
    retired_integration_file = (
        REPO_ROOT
        / "src"
        / "crxzipple"
        / "modules"
        / "skills"
        / "application"
        / "settings_integration.py"
    )
    forbidden = (
        "SkillEnablementManagerAdapter",
        "SKILL_ENABLEMENT_SERVICE",
        "skill_enablements(",
        "modules.skills.application.settings_integration",
    )
    scan_roots = (
        REPO_ROOT / "src" / "crxzipple" / "app",
        REPO_ROOT / "src" / "crxzipple" / "interfaces",
        REPO_ROOT / "src" / "crxzipple" / "modules" / "settings",
        REPO_ROOT / "src" / "crxzipple" / "shared",
    )
    violations: list[str] = []

    if retired_integration_file.exists():
        violations.append(f"{retired_integration_file.relative_to(REPO_ROOT)}: retired file")

    for path in _production_python_files(*scan_roots):
        text = path.read_text(encoding="utf-8")
        for name in forbidden:
            if name in text:
                violations.append(f"{path.relative_to(REPO_ROOT)}: {name}")

    assert violations == []


def test_tool_runtime_catalog_truth_is_not_materialized_from_settings() -> None:
    tool_module_root = REPO_ROOT / "src" / "crxzipple" / "modules" / "tool"
    tool_assembly_path = REPO_ROOT / "src" / "crxzipple" / "app" / "assembly" / "tool.py"
    allowed_assembly_materializer_lines = {
        "requires=(AppKey.SETTINGS_MATERIALIZER,),",
        "materializer = ctx.require(AppKey.SETTINGS_MATERIALIZER)",
        "providers=materializer.tool_providers(),",
        "roots=materializer.tool_roots(),",
    }
    violations: list[str] = []

    for path in _production_python_files(tool_module_root):
        text = path.read_text(encoding="utf-8")
        if "SETTINGS_MATERIALIZER" in text or "materializer.tool_" in text:
            violations.append(f"{path.relative_to(REPO_ROOT)}: settings materializer")

    for line_number, line in enumerate(
        tool_assembly_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        stripped = line.strip()
        if (
            "SETTINGS_MATERIALIZER" in stripped
            or "materializer.tool_" in stripped
        ) and stripped not in allowed_assembly_materializer_lines:
            violations.append(
                f"{tool_assembly_path.relative_to(REPO_ROOT)}:{line_number}: {stripped}",
            )

    assert violations == []


def test_orchestration_does_not_own_skill_runtime_request_resolution() -> None:
    orchestration_root = (
        REPO_ROOT / "src" / "crxzipple" / "modules" / "orchestration"
    )
    forbidden = (
        "resolve_skill.py",
        "ResolveSkill",
        "ResolvedSkillCatalog",
        "ResolvedSkillReadiness",
    )
    violations: list[str] = []
    for path in _production_python_files(orchestration_root):
        if path.name == "resolve_skill.py":
            violations.append(f"{path.relative_to(REPO_ROOT)}: old resolver module")
            continue
        text = path.read_text(encoding="utf-8")
        for name in forbidden[1:]:
            if name in text:
                violations.append(f"{path.relative_to(REPO_ROOT)}: {name}")

    assert violations == []


def test_session_module_does_not_depend_on_context_workspace() -> None:
    violations = _forbidden_import_violations(
        roots=(REPO_ROOT / "src" / "crxzipple" / "modules" / "session",),
        forbidden_modules=("crxzipple.modules.context_workspace",),
    )

    assert violations == []


def test_context_workspace_module_does_not_depend_on_session_truth() -> None:
    violations = _forbidden_import_violations(
        roots=(REPO_ROOT / "src" / "crxzipple" / "modules" / "context_workspace",),
        forbidden_modules=("crxzipple.modules.session",),
    )

    assert violations == []


def test_orchestration_module_uses_context_workspace_port_not_module_imports() -> None:
    violations = _forbidden_import_violations(
        roots=(REPO_ROOT / "src" / "crxzipple" / "modules" / "orchestration",),
        forbidden_modules=("crxzipple.modules.context_workspace",),
    )

    assert violations == []


def test_orchestration_has_no_legacy_full_history_transcript_builder() -> None:
    orchestration_root = (
        REPO_ROOT / "src" / "crxzipple" / "modules" / "orchestration"
    )
    violations: list[str] = []
    for path in _production_python_files(orchestration_root):
        text = path.read_text(encoding="utf-8")
        if "build_runtime_transcript" in text:
            violations.append(f"{path.relative_to(REPO_ROOT)}: build_runtime_transcript")

    assert violations == []


def test_orchestration_read_models_do_not_own_ui_or_trace_projection() -> None:
    read_model_root = (
        REPO_ROOT
        / "src"
        / "crxzipple"
        / "modules"
        / "orchestration"
        / "application"
        / "read_models"
    )
    production_files = [
        path.relative_to(REPO_ROOT)
        for path in _production_python_files(read_model_root)
        if path.name != "__init__.py"
    ]

    assert production_files == []


def test_llm_request_path_does_not_consume_context_debug_body() -> None:
    """Debug render is observation-only and must not become model input."""

    roots = (
        REPO_ROOT / "src" / "crxzipple" / "modules" / "llm" / "application",
        REPO_ROOT / "src" / "crxzipple" / "modules" / "llm" / "infrastructure",
        REPO_ROOT / "src" / "crxzipple" / "modules" / "orchestration" / "application",
    )
    allowed = {
        REPO_ROOT
        / "src"
        / "crxzipple"
        / "modules"
        / "llm"
        / "application"
        / "runtime_request.py",
    }
    violations: list[str] = []
    for path in _production_python_files(*roots):
        if path in allowed:
            continue
        text = path.read_text(encoding="utf-8")
        if "debug_body" in text:
            violations.append(f"{path.relative_to(REPO_ROOT)}: debug_body")

    assert violations == []


def test_provider_request_path_does_not_import_context_observation_rendering() -> None:
    """Provider requests consume ContextSlice data, not debug/observation renders."""

    roots = (
        REPO_ROOT / "src" / "crxzipple" / "modules" / "llm" / "application",
        REPO_ROOT / "src" / "crxzipple" / "modules" / "llm" / "infrastructure",
        REPO_ROOT / "src" / "crxzipple" / "modules" / "orchestration" / "application",
    )
    forbidden_modules = (
        "crxzipple.modules.context_workspace.application.rendering",
    )
    violations = _forbidden_import_violations(
        roots=roots,
        forbidden_modules=forbidden_modules,
    )
    forbidden_symbols = (
        "ContextObservationRenderResult",
        "ContextObservationSnapshotService",
        "RecordContextSnapshotInput",
    )
    for path in _production_python_files(*roots):
        text = path.read_text(encoding="utf-8")
        for symbol in forbidden_symbols:
            if symbol in text:
                violations.append(f"{path.relative_to(REPO_ROOT)}: {symbol}")

    assert violations == []


def test_frontend_prompt_snapshot_uses_context_workspace_surface_only() -> None:
    allowed_debug_body_files = {
        FRONTEND_ROOT / "pages" / "workbench" / "trace" / "api.ts",
        FRONTEND_ROOT / "pages" / "workbench" / "trace" / "TraceInspectorPage.vue",
        FRONTEND_ROOT / "pages" / "workbench" / "api.ts",
        FRONTEND_ROOT / "pages" / "workbench" / "WorkbenchPage.vue",
    }
    forbidden_prompt_api_markers = (
        "/sessions",
        "/orchestration",
        "/llms",
        "/tools",
    )
    violations: list[str] = []

    for path in _frontend_source_files():
        text = path.read_text(encoding="utf-8")
        if "debug_body" in text and path not in allowed_debug_body_files:
            violations.append(f"{path.relative_to(REPO_ROOT)}: debug_body")
        for line_number, line in enumerate(text.splitlines(), start=1):
            lower_line = line.lower()
            if "prompt" not in lower_line:
                continue
            for marker in forbidden_prompt_api_markers:
                if marker in line:
                    violations.append(
                        f"{path.relative_to(REPO_ROOT)}:{line_number}: "
                        f"{line.strip()}",
                    )

    assert violations == []


def test_workbench_runtime_selectors_use_workbench_facade_endpoints() -> None:
    api_text = (
        FRONTEND_ROOT / "pages" / "workbench" / "api.ts"
    ).read_text(encoding="utf-8")

    assert '"/ui/workbench/tools?enabled_only=true"' in api_text
    assert '"/ui/workbench/agents"' in api_text
    assert '"/ui/workbench/models"' in api_text
    assert '"/ui/workbench/turns"' in api_text
    assert "/ui/workbench/turns/" in api_text
    assert "/ui/workbench/context-tree/by-session/" in api_text
    assert "/ui/workbench/context-snapshots/runs/" in api_text
    assert "/ui/workbench/context-snapshots/" in api_text
    assert "/ui/workbench/runs/" in api_text
    assert "/ui/workbench/llm-invocations/" in api_text
    assert '"/tools?enabled_only=true"' not in api_text
    assert '"/agents"' not in api_text
    assert '"/llms"' not in api_text
    assert '"/turns"' not in api_text
    assert "`/turns/" not in api_text
    assert "/context-workspaces/by-session/" not in api_text
    assert "/context-workspaces/runs/" not in api_text
    assert "/context-workspaces/snapshots/" not in api_text
    assert "/turns/${encodeURIComponent(runId)}/llm-request-preview" not in api_text
    assert "/llms/calls/" not in api_text

    trace_api_text = (
        FRONTEND_ROOT / "pages" / "workbench" / "trace" / "api.ts"
    ).read_text(encoding="utf-8")
    assert "/ui/workbench/context-snapshots/runs/" in trace_api_text
    assert "/ui/workbench/context-snapshots/" in trace_api_text
    assert "/ui/workbench/runs/" in trace_api_text
    assert "/ui/workbench/llm-invocations/" in trace_api_text
    assert "/context-workspaces/runs/" not in trace_api_text
    assert "/context-workspaces/snapshots/" not in trace_api_text
    assert "/turns/${encodeURIComponent(runId)}/llm-request-preview" not in trace_api_text
    assert "/llms/calls/" not in trace_api_text


def test_frontend_trace_has_only_workbench_product_route() -> None:
    router_text = (FRONTEND_ROOT / "app" / "router.ts").read_text(encoding="utf-8")
    legacy_trace_page = FRONTEND_ROOT / "pages" / "trace"

    assert 'path: "/workbench/traces/:traceId?"' in router_text
    assert 'path: "/trace/:traceId?"' not in router_text
    assert "name: \"trace\"" not in router_text
    assert not legacy_trace_page.exists()


def test_llm_adapter_common_module_is_retired() -> None:
    adapter_root = (
        REPO_ROOT
        / "src"
        / "crxzipple"
        / "modules"
        / "llm"
        / "infrastructure"
        / "adapters"
    )
    common_path = adapter_root / "common.py"
    violations: list[str] = []

    if common_path.exists():
        violations.append(f"{common_path.relative_to(REPO_ROOT)}: retired module")

    for path in _production_python_files(adapter_root):
        text = path.read_text(encoding="utf-8")
        if "adapters.common" in text or "adapters import common" in text:
            violations.append(f"{path.relative_to(REPO_ROOT)}: common import")

    assert violations == []


def test_session_runtime_integration_uses_orchestration_ports_not_internal_flow() -> None:
    integration_text = (
        REPO_ROOT
        / "src"
        / "crxzipple"
        / "app"
        / "integration"
        / "session_runtime_control.py"
    ).read_text(encoding="utf-8")
    forbidden = (
        "RunIngressCoordinator",
        "RunIntakeCoordinator",
        "RunCancellationService",
        "process_ingress_request",
        "fail_ingress_backed_run_record",
        "OrchestrationScheduler(",
    )

    for name in forbidden:
        assert name not in integration_text


def test_orchestration_ingress_targets_share_intake_builder() -> None:
    graph_text = (
        REPO_ROOT
        / "src"
        / "crxzipple"
        / "modules"
        / "orchestration"
        / "application"
        / "service_graph.py"
    ).read_text(encoding="utf-8")
    ingress_runtime_text = (
        REPO_ROOT
        / "src"
        / "crxzipple"
        / "modules"
        / "orchestration"
        / "application"
        / "ingress_runtime.py"
    ).read_text(encoding="utf-8")

    for text in (graph_text, ingress_runtime_text):
        assert "build_run_intake_coordinator(" in text
        assert "SessionRunPreparationWorkflow(" not in text
        assert "ResolveSessionInput" not in text
        assert "session_start_runtime_request_flow_hint" not in text


def test_orchestration_service_graph_does_not_proxy_owner_coordinator_methods() -> None:
    graph_text = (
        REPO_ROOT
        / "src"
        / "crxzipple"
        / "modules"
        / "orchestration"
        / "application"
        / "service_graph.py"
    ).read_text(encoding="utf-8")
    forbidden_proxy_methods = (
        "def _assign_next_assignment(",
        "def _process_next_assigned_assignment(",
        "def _next_assigned_assignment(",
        "def _process_assigned_assignment(",
        "def _process_assigned_assignment_async(",
        "def _advance_assignment(",
        "def _wait_assignment_on_tool(",
        "def _wait_for_confirmation(",
        "def _heartbeat_assignment(",
        "def _complete_assignment(",
        "def _fail_assignment(",
        "def _admit_assignment(",
        "def _clear_runtime_request_flow_hint(",
        "def _request_compaction(",
        "def _request_heartbeat(",
        "def _request_memory_flush(",
        "def _request_due_heartbeats(",
        "def _recover_abandoned_runs(",
        "def _expire_executor_leases(",
        "def _handle_recovered_dispatch_task(",
        "def _handle_terminal_tool_run(",
        "def _continue_recovery_contract(",
    )

    for name in forbidden_proxy_methods:
        assert name not in graph_text


def test_orchestration_recovery_depends_on_wait_continuation_not_wait_coordinator() -> None:
    recovery_text = (
        REPO_ROOT
        / "src"
        / "crxzipple"
        / "modules"
        / "orchestration"
        / "application"
        / "coordinators"
        / "recovery.py"
    ).read_text(encoding="utf-8")

    assert "RunWaitCoordinator" not in recovery_text
    assert "wait_coordinator" not in recovery_text
    assert "continue_recovery_contract: Callable[[str], OrchestrationRun]" in recovery_text


def test_runtime_plan_does_not_expose_internal_service_graphs() -> None:
    from crxzipple.app.assembly.runtime import runtime_plan

    plan = runtime_plan()
    app_key_values = {key.value for key in AppKey}
    factory_keys = {factory.key for factory in plan.factories}
    provided_values = {
        provided
        for factory in plan.factories
        for provided in factory.provides
    }

    assert "orchestration.service_graph" not in app_key_values
    assert "orchestration.runtime" not in app_key_values
    assert "tool.service_graph" not in app_key_values
    assert "orchestration.service_graph" not in provided_values
    assert "orchestration.runtime" not in provided_values
    assert "tool.service_graph" not in provided_values
    assert "tool.service_graph" not in factory_keys
    assert "tool.execution_service_graph" not in factory_keys


def test_admin_entrypoints_do_not_require_orchestration_worker_services() -> None:
    scan_roots = (
        REPO_ROOT / "src" / "crxzipple" / "interfaces" / "http",
        REPO_ROOT / "src" / "crxzipple" / "interfaces" / "cli",
        REPO_ROOT / "src" / "crxzipple" / "modules" / "orchestration" / "interfaces",
        REPO_ROOT / "src" / "crxzipple" / "modules" / "operations" / "interfaces",
    )
    allowed = {
        REPO_ROOT
        / "src"
        / "crxzipple"
        / "modules"
        / "orchestration"
        / "interfaces"
        / "worker_cli.py",
        REPO_ROOT
        / "src"
        / "crxzipple"
        / "modules"
        / "orchestration"
        / "interfaces"
        / "worker_cli_common.py",
    }
    forbidden = (
        "AppKey.ORCHESTRATION_SCHEDULER_SERVICE",
        "AppKey.ORCHESTRATION_EXECUTOR_SERVICE",
    )
    violations: list[str] = []

    for path in _production_python_files(*scan_roots):
        if path in allowed:
            continue
        text = path.read_text(encoding="utf-8")
        for name in forbidden:
            if name in text:
                violations.append(f"{path.relative_to(REPO_ROOT)}: {name}")

    assert violations == []


def test_orchestration_worker_cli_keeps_benchmark_runtime_lazy() -> None:
    worker_cli_files = (
        REPO_ROOT
        / "src"
        / "crxzipple"
        / "modules"
        / "orchestration"
        / "interfaces"
        / "worker_cli.py",
        REPO_ROOT
        / "src"
        / "crxzipple"
        / "modules"
        / "orchestration"
        / "interfaces"
        / "worker_cli_common.py",
        REPO_ROOT
        / "src"
        / "crxzipple"
        / "modules"
        / "orchestration"
        / "interfaces"
        / "worker_cli_executor.py",
        REPO_ROOT
        / "src"
        / "crxzipple"
        / "modules"
        / "orchestration"
        / "interfaces"
        / "worker_cli_executor_benchmarks.py",
        REPO_ROOT
        / "src"
        / "crxzipple"
        / "modules"
        / "orchestration"
        / "interfaces"
        / "worker_cli_scheduler.py",
    )
    forbidden_top_level_imports = (
        "crxzipple.modules.agent",
        "crxzipple.modules.llm",
        "crxzipple.modules.tool",
        "crxzipple.modules.orchestration.interfaces.worker_cli_benchmark",
    )
    violations: list[str] = []

    for path in worker_cli_files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            module_names: list[str] = []
            if isinstance(node, ast.Import):
                module_names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                module_names.append(node.module)
            for module_name in module_names:
                for forbidden in forbidden_top_level_imports:
                    if module_name == forbidden or module_name.startswith(
                        f"{forbidden}.",
                    ):
                        violations.append(
                            f"{path.relative_to(REPO_ROOT)}: {module_name}",
                        )

    assert violations == []


def test_activation_tasks_are_declared_idempotent() -> None:
    from crxzipple.app.assembly.runtime import runtime_plan

    plan = runtime_plan()
    non_idempotent = [
        task.key for task in plan.activation_tasks if not bool(task.idempotent)
    ]

    assert non_idempotent == []
