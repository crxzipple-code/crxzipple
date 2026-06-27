from __future__ import annotations

from dataclasses import fields
from pathlib import Path

from crxzipple.core.config import OpenApiCredentialBinding


ROOT = Path(__file__).resolve().parents[2]


def test_openapi_credential_binding_contract_has_no_direct_sources() -> None:
    field_names = {field.name for field in fields(OpenApiCredentialBinding)}

    assert "source" not in field_names
    assert "username_source" not in field_names
    assert "password_source" not in field_names
    assert {
        "credential_binding_id",
        "username_binding_id",
        "password_binding_id",
    }.issubset(field_names)


def test_builtin_tool_manifests_do_not_embed_direct_credential_sources() -> None:
    scanned_paths = [
        *sorted((ROOT / "tools").glob("*/tool.yaml")),
        *sorted((ROOT / "config" / "tool_providers").glob("**/*.yaml")),
        *sorted((ROOT / "config" / "tool_providers").glob("**/*.yml")),
        *sorted((ROOT / "config" / "tool_providers").glob("**/*.json")),
    ]
    leaks: list[str] = []
    for path in scanned_paths:
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if any(marker in line for marker in ("env:", "file:", "codex_auth_json")):
                leaks.append(f"{path.relative_to(ROOT)}:{line_number}: {line.strip()}")

    assert leaks == []


def test_tool_submission_requires_catalog_function_without_runtime_fallback() -> None:
    submission_preparation = (
        ROOT
        / "src"
        / "crxzipple"
        / "modules"
        / "tool"
        / "application"
        / "submission_preparation.py"
    ).read_text(encoding="utf-8")

    catalog_lookup = "function = uow.tool_functions.get(data.tool_id)"
    function_build = "tool = build_tool_from_function(function)"

    assert catalog_lookup in submission_preparation
    assert function_build in submission_preparation
    assert "catalog_service.resolve_tool" not in submission_preparation
    assert "runtime_gateway.list_registered_tools()" not in submission_preparation


def test_tool_catalog_does_not_discover_sources_during_runtime_resolution() -> None:
    catalog_service = (
        ROOT
        / "src"
        / "crxzipple"
        / "modules"
        / "tool"
        / "application"
        / "catalog_service.py"
    ).read_text(encoding="utf-8")
    app_tool_assembly = (
        ROOT / "src" / "crxzipple" / "app" / "assembly" / "tool.py"
    ).read_text(encoding="utf-8")
    local_runtime_registry = (
        ROOT
        / "src"
        / "crxzipple"
        / "modules"
        / "tool"
        / "infrastructure"
        / "discovery"
        / "local_runtime_registry.py"
    ).read_text(encoding="utf-8")
    filesystem_discovery = (
        ROOT
        / "src"
        / "crxzipple"
        / "modules"
        / "tool"
        / "infrastructure"
        / "discovery"
        / "filesystem.py"
    )
    skills_manifest = (ROOT / "tools" / "skills" / "tool.yaml").read_text(
        encoding="utf-8",
    )

    assert "def discover_resolution_specs" not in catalog_service
    assert "def refresh_local_extension_discovery" not in catalog_service
    assert "discover_tools(" not in catalog_service
    assert "list_discovery_providers(" not in catalog_service
    assert "filesystem_provider.discover_specs()" not in app_tool_assembly
    assert "FilesystemLocalToolDiscoveryProvider" not in app_tool_assembly
    assert not filesystem_discovery.exists()
    assert "class LocalToolRuntimeRegistry" in local_runtime_registry
    assert "class LocalToolCatalog" not in local_runtime_registry
    assert "def replace_provider_tools" not in local_runtime_registry
    assert "local_runtime_registry" not in skills_manifest


def test_tool_package_activation_filters_local_handlers_by_function_catalog() -> None:
    app_tool_assembly = (
        ROOT / "src" / "crxzipple" / "app" / "assembly" / "tool.py"
    ).read_text(encoding="utf-8")
    app_tool_package_assembly = (
        ROOT / "src" / "crxzipple" / "app" / "assembly" / "tool_packages.py"
    ).read_text(encoding="utf-8")
    tool_package_activation_resolution = (
        ROOT
        / "src"
        / "crxzipple"
        / "modules"
        / "tool"
        / "infrastructure"
        / "tool_package_activation_resolution.py"
    ).read_text(encoding="utf-8")

    assert "AppKey.TOOL_SOURCE_QUERY_SERVICE" in app_tool_assembly
    assert "def active_local_function_refs_by_namespace(" in app_tool_package_assembly
    assert "local_function_refs_by_namespace=" in app_tool_package_assembly
    assert "def _local_handler_enabled_by_catalog(" in tool_package_activation_resolution
    assert "context.local_function_refs_for_namespace(" in tool_package_activation_resolution


def test_process_local_tool_registration_api_is_removed() -> None:
    catalog_service = (
        ROOT
        / "src"
        / "crxzipple"
        / "modules"
        / "tool"
        / "application"
        / "catalog_service.py"
    ).read_text(encoding="utf-8")
    application_service = (
        ROOT
        / "src"
        / "crxzipple"
        / "modules"
        / "tool"
        / "application"
        / "services.py"
    ).read_text(encoding="utf-8")

    assert "def register(self, data: RegisterToolInput)" not in catalog_service
    assert "def register(self, data: RegisterToolInput)" not in application_service
    assert "register_process_local_tool" not in catalog_service
    assert "register_process_local_tool" not in application_service
    assert "tool.process_local_registered" not in catalog_service
    assert "SetToolAvailabilityInput" not in application_service


def test_orchestration_tool_port_uses_runtime_pool_service() -> None:
    app_tool_assembly = (
        ROOT / "src" / "crxzipple" / "app" / "assembly" / "tool.py"
    ).read_text(encoding="utf-8")
    app_tool_service_graph = (
        ROOT / "src" / "crxzipple" / "app" / "assembly" / "tool_service_graph.py"
    ).read_text(encoding="utf-8")
    runtime_pool_service = (
        ROOT
        / "src"
        / "crxzipple"
        / "modules"
        / "tool"
        / "application"
        / "runtime_pool_service.py"
    ).read_text(encoding="utf-8")

    assert "AppKey.TOOL_RUNTIME_POOL_SERVICE" in app_tool_assembly
    assert "runtime_pool_service.list_enabled_tools(" in app_tool_service_graph
    assert "runtime_context=runtime_context" in app_tool_service_graph
    assert "include_process_local_overlay" not in app_tool_assembly
    assert "include_process_local_overlay" not in app_tool_service_graph
    assert "runtime_context=runtime_context" in (
        ROOT
        / "src"
        / "crxzipple"
        / "modules"
        / "orchestration"
        / "application"
        / "tool_resolver.py"
    ).read_text(encoding="utf-8")
    assert "class ToolRuntimePoolService" in runtime_pool_service
    assert "process_local_tool_provider" not in runtime_pool_service
    assert "uow.tool_functions.list(status=ToolFunctionStatus.ACTIVE)" in (
        runtime_pool_service
    )
    assert "check_tool_access(tool)" in runtime_pool_service
    assert "check_tool_runtime(" in runtime_pool_service
