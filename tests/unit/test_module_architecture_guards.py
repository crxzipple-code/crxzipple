from __future__ import annotations

import ast
from pathlib import Path

from crxzipple.modules.operations.application.read_models.llm_projection_diagnostics import (
    llm_projection_diagnostics,
)
from crxzipple.modules.operations.application.read_models.orchestration_projection_diagnostics import (
    orchestration_projection_diagnostics,
)
from crxzipple.modules.operations.application.read_models.tool_projection_diagnostics import (
    tool_projection_diagnostics,
)
from crxzipple.modules.workbench.application.projection_diagnostics import (
    workbench_run_owner_fact_sources,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULES_ROOT = REPO_ROOT / "src" / "crxzipple" / "modules"
FRONTEND_ROOT = REPO_ROOT / "frontend" / "src"


def _python_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def _source_files(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    return sorted(
        path
        for suffix in suffixes
        for path in root.rglob(f"*{suffix}")
        if "__pycache__" not in path.parts
    )


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imported_modules(path: Path) -> list[str]:
    imports: list[str] = []
    for node in ast.walk(_parse(path)):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _module_name_for_path(path: Path) -> str:
    parts = path.relative_to(MODULES_ROOT).parts
    return parts[0]


def test_dispatch_runtime_has_no_in_memory_repository_backdoor() -> None:
    retired_path = MODULES_ROOT / "dispatch" / "infrastructure" / "in_memory_repository.py"

    assert not retired_path.exists()

    dispatch_infrastructure = _source(
        MODULES_ROOT / "dispatch" / "infrastructure" / "__init__.py",
    )
    assert "InMemoryDispatchTaskRepository" not in dispatch_infrastructure


def test_dispatch_interfaces_do_not_bypass_application_service() -> None:
    interface_files = (
        MODULES_ROOT / "dispatch" / "interfaces" / "cli.py",
        MODULES_ROOT / "dispatch" / "interfaces" / "http.py",
    )
    forbidden_import_prefixes = (
        "crxzipple.modules.dispatch.infrastructure",
        "crxzipple.shared.application.unit_of_work",
        "crxzipple.shared.infrastructure",
    )
    forbidden_source_markers = (
        "dispatch_tasks",
        "DispatchTask(",
        ".complete(",
        ".fail(",
        ".cancel(",
        ".enqueue(",
        "claim_queued(",
        "claim_next_queued(",
        "uow.",
    )
    violations: list[str] = []

    for path in interface_files:
        for imported_module in _imported_modules(path):
            if imported_module.startswith(forbidden_import_prefixes):
                violations.append(
                    f"{path.relative_to(REPO_ROOT)}: imports {imported_module}",
                )
        source = _source(path)
        for marker in forbidden_source_markers:
            if marker in source:
                violations.append(
                    f"{path.relative_to(REPO_ROOT)}: references {marker}",
                )

    assert violations == []


def test_module_domain_packages_remain_pure() -> None:
    forbidden_external_prefixes = (
        "fastapi",
        "sqlalchemy",
        "redis",
        "playwright",
        "requests",
        "httpx",
    )
    forbidden_same_module_layers = (
        ".application",
        ".infrastructure",
        ".interfaces",
    )
    violations: list[str] = []

    for path in _python_files(MODULES_ROOT):
        if "domain" not in path.relative_to(MODULES_ROOT).parts:
            continue
        owner_module = _module_name_for_path(path)
        for imported_module in _imported_modules(path):
            if imported_module.startswith(forbidden_external_prefixes):
                violations.append(
                    f"{path.relative_to(REPO_ROOT)}: imports {imported_module}",
                )
                continue

            if not imported_module.startswith("crxzipple.modules."):
                continue

            parts = imported_module.split(".")
            imported_owner = parts[2] if len(parts) > 2 else ""
            if imported_owner != owner_module:
                violations.append(
                    f"{path.relative_to(REPO_ROOT)}: imports cross-module domain "
                    f"{imported_module}",
                )
                continue

            if any(layer in imported_module for layer in forbidden_same_module_layers):
                violations.append(
                    f"{path.relative_to(REPO_ROOT)}: imports non-domain layer "
                    f"{imported_module}",
                )

    assert violations == []


def test_workbench_and_operations_projection_layers_do_not_write_persistence() -> None:
    projection_roots = (
        MODULES_ROOT / "workbench" / "application",
        MODULES_ROOT / "operations" / "application",
    )
    forbidden_import_prefixes = (
        "sqlalchemy",
        "crxzipple.modules.operations.infrastructure.persistence",
    )
    forbidden_import_fragments = (
        ".infrastructure.persistence",
    )
    forbidden_call_names = (
        "commit",
        "rollback",
        "flush",
        "delete",
        "save",
        "upsert",
    )
    violations: list[str] = []

    for path in (file for root in projection_roots for file in _python_files(root)):
        for imported_module in _imported_modules(path):
            if imported_module.startswith(forbidden_import_prefixes) or any(
                fragment in imported_module for fragment in forbidden_import_fragments
            ):
                violations.append(
                    f"{path.relative_to(REPO_ROOT)}: imports {imported_module}",
                )

        for node in ast.walk(_parse(path)):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in forbidden_call_names
            ):
                violations.append(
                    f"{path.relative_to(REPO_ROOT)}:{node.lineno}: calls "
                    f"{node.func.attr}()",
                )

    assert violations == []


def test_operations_read_model_files_remain_focused() -> None:
    read_model_root = MODULES_ROOT / "operations" / "application" / "read_models"
    max_lines = 250
    violations: list[str] = []

    for path in _python_files(read_model_root):
        if path.name == "__init__.py":
            continue
        line_count = len(_source(path).splitlines())
        if line_count > max_lines:
            violations.append(
                f"{path.relative_to(REPO_ROOT)} has {line_count} lines; "
                f"split focused helpers before exceeding {max_lines}",
            )

    assert violations == []


def test_tool_core_has_no_site_specific_task_logic() -> None:
    forbidden_markers = (
        "ceair",
        "东航",
        "东方航空",
        "flight_search",
        "航班",
        "机票",
        "昆明",
        "上海",
    )
    violations: list[str] = []

    for path in _python_files(MODULES_ROOT / "tool"):
        source = _source(path).lower()
        for marker in forbidden_markers:
            if marker.lower() in source:
                violations.append(f"{path.relative_to(REPO_ROOT)}: contains {marker}")

    assert violations == []


def test_browser_core_has_no_site_specific_navigation_logic() -> None:
    forbidden_markers = (
        "ceair",
        "东航",
        "东方航空",
        "flight_search",
        "航班",
        "机票",
        "昆明",
        "上海",
        "ctrip",
        "携程",
        "airline",
    )
    violations: list[str] = []

    for path in _python_files(MODULES_ROOT / "browser"):
        source = _source(path).lower()
        for marker in forbidden_markers:
            if marker.lower() in source:
                violations.append(f"{path.relative_to(REPO_ROOT)}: contains {marker}")

    assert violations == []


def test_mobile_core_has_no_app_or_task_specific_flow_logic() -> None:
    forbidden_markers = (
        "ceair",
        "东航",
        "东方航空",
        "flight_search",
        "航班",
        "机票",
        "昆明",
        "上海",
        "ctrip",
        "携程",
        "booking",
        "checkout",
        "com.taobao",
        "com.sankuai",
        "com.alibaba.android.user.login",
    )
    violations: list[str] = []

    for path in _python_files(MODULES_ROOT / "mobile"):
        source = _source(path).lower()
        for marker in forbidden_markers:
            if marker.lower() in source:
                violations.append(f"{path.relative_to(REPO_ROOT)}: contains {marker}")

    assert violations == []


def test_operations_python_files_remain_focused() -> None:
    max_lines = 250
    violations: list[str] = []

    for path in _python_files(MODULES_ROOT / "operations"):
        if path.name == "__init__.py":
            continue
        line_count = len(_source(path).splitlines())
        if line_count > max_lines:
            violations.append(
                f"{path.relative_to(REPO_ROOT)} has {line_count} lines; "
                f"split focused helpers before exceeding {max_lines}",
            )

    assert violations == []


def test_operations_file_observation_store_is_not_shared_runtime_fallback() -> None:
    allowed_file_store_path = (
        MODULES_ROOT / "operations" / "infrastructure" / "observation_store.py"
    )
    forbidden_runtime_roots = (
        REPO_ROOT / "src" / "crxzipple" / "app",
        REPO_ROOT / "src" / "crxzipple" / "interfaces",
    )
    violations: list[str] = []

    infrastructure_exports = _source(
        MODULES_ROOT / "operations" / "infrastructure" / "__init__.py",
    )
    if "FileBackedOperationsObservationStore" in infrastructure_exports:
        violations.append(
            "src/crxzipple/modules/operations/infrastructure/__init__.py exports "
            "FileBackedOperationsObservationStore",
        )

    for path in (file for root in forbidden_runtime_roots for file in _python_files(root)):
        source = _source(path)
        if (
            "FileBackedOperationsObservationStore" in source
            or "operations.infrastructure.observation_store" in source
        ):
            violations.append(
                f"{path.relative_to(REPO_ROOT)} references file-backed Operations "
                "observation store",
            )

    for path in _python_files(MODULES_ROOT / "operations"):
        if path == allowed_file_store_path:
            continue
        if "FileBackedOperationsObservationStore" in _source(path):
            violations.append(
                f"{path.relative_to(REPO_ROOT)} references file-backed Operations "
                "observation store outside its explicit implementation",
            )

    assert violations == []


def test_orchestration_service_graph_is_not_cross_module_api() -> None:
    allowed_paths = {
        REPO_ROOT / "src" / "crxzipple" / "app" / "assembly" / "orchestration.py",
        MODULES_ROOT / "orchestration" / "application" / "service_graph.py",
    }
    violations: list[str] = []

    for path in _python_files(REPO_ROOT / "src" / "crxzipple"):
        if path in allowed_paths:
            continue
        source = _source(path)
        if "OrchestrationServiceGraph" in source:
            violations.append(
                f"{path.relative_to(REPO_ROOT)} references OrchestrationServiceGraph",
            )

    assert violations == []


def test_operations_frontend_uses_operations_daemon_projection_not_daemon_owner_api() -> None:
    violations: list[str] = []
    operations_frontend = FRONTEND_ROOT / "pages" / "operations"

    for path in _source_files(operations_frontend, (".ts", ".tsx", ".vue")):
        source = _source(path)
        for marker in (
            '"/daemon',
            "'/daemon",
            "`/daemon",
            'buildApiUrl("/daemon',
            "buildApiUrl('/daemon",
        ):
            if marker in source:
                violations.append(
                    f"{path.relative_to(REPO_ROOT)} references daemon owner API "
                    f"marker {marker}",
                )

    assert violations == []


def test_runtime_frontend_pages_do_not_bypass_projection_apis() -> None:
    runtime_frontend_roots = (
        FRONTEND_ROOT / "pages" / "operations",
        FRONTEND_ROOT / "pages" / "workbench",
    )
    owner_api_prefixes = (
        "/access",
        "/agents",
        "/browser",
        "/channels",
        "/context",
        "/daemon",
        "/llms",
        "/memory",
        "/orchestration",
        "/sessions",
        "/skills",
        "/tools",
    )
    quote_prefixes = ('"', "'", "`")
    forbidden_markers = tuple(
        f"{quote}{prefix}"
        for quote in quote_prefixes
        for prefix in owner_api_prefixes
    )
    violations: list[str] = []

    for path in (
        source_file
        for root in runtime_frontend_roots
        for source_file in _source_files(root, (".ts", ".tsx", ".vue"))
    ):
        source = _source(path)
        for marker in forbidden_markers:
            if marker in source:
                violations.append(
                    f"{path.relative_to(REPO_ROOT)} references owner API "
                    f"marker {marker}",
                )

    assert violations == []


def test_workbench_and_operations_projectors_declare_owner_fact_sources() -> None:
    workbench_sources = workbench_run_owner_fact_sources()
    assert {source.module for source in workbench_sources} == {
        "agent",
        "artifacts",
        "llm",
        "orchestration",
        "session",
        "tool",
    }
    assert all(source.facts and source.read_path for source in workbench_sources)

    operations_diagnostics = (
        tool_projection_diagnostics(
            tools=[],
            runs=[],
            workers=[],
            assignments=[],
            sources=(),
            functions=(),
            provider_backends=(),
            discovery_runs_by_source={},
            observed_events=(),
            owner_call_count=0,
            elapsed_ms=0,
            freshness_at="",
        ),
        llm_projection_diagnostics(
            profiles=[],
            invocations=[],
            observed_events=(),
            resolver_events=(),
            response_events_by_invocation={},
            owner_call_count=0,
            elapsed_ms=0,
            freshness_at="",
        ),
        orchestration_projection_diagnostics(
            runs=[],
            leases=[],
            ingress_requests=[],
            continuation_tasks=[],
            dispatch_tasks=[],
            observed_events=(),
            owner_call_count=0,
            elapsed_ms=0,
            freshness_at="",
        ),
    )
    assert {
        diagnostics.module for diagnostics in operations_diagnostics
    } == {"llm", "orchestration", "tool"}
    for diagnostics in operations_diagnostics:
        assert diagnostics.owner_sources
        assert all(
            source.module and source.facts and source.read_path
            for source in diagnostics.owner_sources
        )


def test_orchestration_does_not_import_provider_adapter_internals() -> None:
    orchestration_root = MODULES_ROOT / "orchestration"
    forbidden_prefixes = (
        "crxzipple.modules.llm.infrastructure.adapters",
    )
    violations = [
        f"{path.relative_to(REPO_ROOT)}: imports {imported_module}"
        for path in _python_files(orchestration_root)
        for imported_module in _imported_modules(path)
        if imported_module.startswith(forbidden_prefixes)
    ]

    assert violations == []


def test_tool_application_does_not_import_orchestration_runtime_owner() -> None:
    tool_application_root = MODULES_ROOT / "tool" / "application"
    forbidden_prefixes = (
        "crxzipple.modules.orchestration.application",
        "crxzipple.modules.orchestration.infrastructure",
        "crxzipple.modules.orchestration.interfaces",
    )
    violations = [
        f"{path.relative_to(REPO_ROOT)}: imports {imported_module}"
        for path in _python_files(tool_application_root)
        for imported_module in _imported_modules(path)
        if imported_module.startswith(forbidden_prefixes)
    ]

    assert violations == []


def test_event_relay_does_not_import_owner_runtime_mutators() -> None:
    event_relay_root = MODULES_ROOT / "event_relay"
    forbidden_prefixes = (
        "crxzipple.modules.orchestration.infrastructure",
        "crxzipple.modules.orchestration.interfaces",
        "crxzipple.modules.tool.application",
        "crxzipple.modules.tool.infrastructure",
        "crxzipple.modules.tool.interfaces",
    )
    forbidden_orchestration_application_prefixes = (
        "crxzipple.modules.orchestration.application",
    )
    allowed_orchestration_application_prefixes = (
        "crxzipple.modules.orchestration.application.ports",
    )
    violations: list[str] = []

    for path in _python_files(event_relay_root):
        for imported_module in _imported_modules(path):
            if imported_module.startswith(forbidden_prefixes):
                violations.append(
                    f"{path.relative_to(REPO_ROOT)}: imports {imported_module}",
                )
            if imported_module.startswith(
                forbidden_orchestration_application_prefixes,
            ) and not imported_module.startswith(allowed_orchestration_application_prefixes):
                violations.append(
                    f"{path.relative_to(REPO_ROOT)}: imports {imported_module}",
                )

    assert violations == []


def test_llm_request_builders_do_not_read_session_repositories() -> None:
    request_builder_files = (
        MODULES_ROOT / "llm" / "application" / "runtime_request.py",
        MODULES_ROOT / "llm" / "application" / "runtime_request_factory.py",
        MODULES_ROOT / "llm" / "application" / "llm_adapter_request_builder.py",
        MODULES_ROOT / "llm" / "application" / "llm_invocation_runner.py",
        MODULES_ROOT / "llm" / "application" / "llm_streaming_invocation_runner.py",
        MODULES_ROOT / "llm" / "application" / "provider_request_input_preview.py",
        MODULES_ROOT / "llm" / "application" / "provider_request_preview_recorder.py",
        *(MODULES_ROOT / "llm" / "infrastructure" / "adapters").glob("*.py"),
        *(MODULES_ROOT / "llm" / "infrastructure" / "rendering").glob("*.py"),
    )
    forbidden_import_prefixes = (
        "crxzipple.modules.session.infrastructure",
        "crxzipple.modules.session.domain.repositories",
    )
    forbidden_source_markers = (
        "SessionRepository",
        "SessionItemRepository",
        "SessionInstanceRepository",
        "SqlAlchemySessionRepository",
        "SqlAlchemySessionItemRepository",
        "SqlAlchemySessionInstanceRepository",
        "InMemorySessionRepository",
        "InMemorySessionItemRepository",
        "InMemorySessionInstanceRepository",
    )
    violations: list[str] = []

    for path in sorted(set(request_builder_files)):
        for imported_module in _imported_modules(path):
            if imported_module.startswith(forbidden_import_prefixes):
                violations.append(
                    f"{path.relative_to(REPO_ROOT)}: imports {imported_module}",
                )
        source = _source(path)
        for marker in forbidden_source_markers:
            if marker in source:
                violations.append(
                    f"{path.relative_to(REPO_ROOT)}: references {marker}",
                )

    assert violations == []


def test_access_and_authorization_do_not_cross_own_truth_boundaries() -> None:
    checks = (
        (
            MODULES_ROOT / "access",
            "crxzipple.modules.authorization",
            "Access must not own or inspect internal authorization truth",
        ),
        (
            MODULES_ROOT / "authorization",
            "crxzipple.modules.access",
            "Authorization must not own or inspect external credential truth",
        ),
    )
    violations: list[str] = []

    for root, forbidden_prefix, message in checks:
        for path in _python_files(root):
            for imported_module in _imported_modules(path):
                if imported_module.startswith(forbidden_prefix):
                    violations.append(
                        f"{path.relative_to(REPO_ROOT)}: imports {imported_module}; "
                        f"{message}",
                    )

    assert violations == []
