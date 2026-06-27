from __future__ import annotations

from typing import Any

from crxzipple.modules.tool.application.activation import (
    ToolDependencyRequirement,
    ToolPackagePlan,
)
from crxzipple.modules.tool.application.catalog_models import (
    ToolSourceCatalogKind,
    ToolSourceCatalogRecord,
)
from .package_catalog_payloads import dependency_payload, stable_payload


def tool_source_records_from_package_plans(
    package_plans: tuple[ToolPackagePlan, ...],
    *,
    include_openapi: bool = True,
) -> tuple[ToolSourceCatalogRecord, ...]:
    records: list[ToolSourceCatalogRecord] = []
    for plan in package_plans:
        if plan.package_kind == "openapi" and not include_openapi:
            continue
        records.append(_source_record_from_package_plan(plan))
    return tuple(records)


def tool_package_source_id(plan: ToolPackagePlan) -> str:
    prefix = (
        "bundled.openapi"
        if plan.package_kind == "openapi"
        else "bundled.local_package"
    )
    return f"{prefix}.{plan.namespace}"


def _source_record_from_package_plan(plan: ToolPackagePlan) -> ToolSourceCatalogRecord:
    kind = (
        ToolSourceCatalogKind.OPENAPI
        if plan.package_kind == "openapi"
        else ToolSourceCatalogKind.LOCAL_PACKAGE
    )
    return ToolSourceCatalogRecord(
        source_id=tool_package_source_id(plan),
        kind=kind,
        display_name=_display_name(plan),
        description=_description(plan),
        config=_source_config(plan),
        runtime_requirements=_runtime_requirements(plan),
    )


def _source_config(plan: ToolPackagePlan) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source": "bundled_tool_package",
        "namespace": plan.namespace,
        "package_kind": plan.package_kind,
        "root_path": plan.root_path,
        "manifest_path": plan.manifest_path,
        "capability_ids": list(plan.capability_ids),
    }
    if plan.runtime_request:
        payload["runtime_request"] = stable_payload(plan.runtime_request)
    if plan.local_handlers:
        payload["local_tools"] = [
            {
                "tool_id": handler.tool.id,
                "provider_name": handler.provider_name,
                "entrypoint": handler.entrypoint,
                "capability_ids": list(handler.capability_ids),
            }
            for handler in plan.local_handlers
            if handler.tool.enabled
        ]
    if plan.remote_runtimes:
        payload["remote_runtimes"] = [
            {
                "runtime_key": runtime.runtime_key,
                "entrypoint": runtime.entrypoint,
                "capability_ids": list(runtime.capability_ids),
            }
            for runtime in plan.remote_runtimes
        ]
    if plan.sandbox_runtimes:
        payload["sandbox_runtimes"] = [
            {
                "runtime_key": runtime.runtime_key,
                "entrypoint": runtime.entrypoint,
                "capability_ids": list(runtime.capability_ids),
            }
            for runtime in plan.sandbox_runtimes
        ]
    if plan.openapi is not None:
        payload["openapi"] = {
            "namespace": plan.openapi.namespace,
            "provider": stable_payload(plan.openapi.provider),
            "capability_ids": list(plan.openapi.capability_ids),
            "dependencies": [
                dependency_payload(dependency)
                for dependency in plan.openapi.dependencies
            ],
        }
    if plan.provider_backends:
        payload["provider_backends"] = [
            {
                "backend_id": backend.backend_id,
                "capability": backend.capability,
                "display_name": backend.display_name,
                "runtime_kind": backend.runtime_kind,
                "runtime_ref": backend.runtime_ref,
                "priority": backend.priority,
                "enabled": backend.enabled,
            }
            for backend in plan.provider_backends
        ]
    return payload


def _runtime_requirements(plan: ToolPackagePlan) -> tuple[str, ...]:
    requirements: list[str] = []
    for dependency in _package_dependencies(plan):
        if dependency.required:
            requirements.append(dependency.id)
    return tuple(dict.fromkeys(requirements))


def _package_dependencies(
    plan: ToolPackagePlan,
) -> tuple[ToolDependencyRequirement, ...]:
    dependencies: list[ToolDependencyRequirement] = []
    for handler in plan.local_handlers:
        dependencies.extend(handler.dependencies)
    for runtime in (*plan.remote_runtimes, *plan.sandbox_runtimes):
        dependencies.extend(runtime.dependencies)
    if plan.openapi is not None:
        dependencies.extend(plan.openapi.dependencies)
    return tuple(dependencies)


def _display_name(plan: ToolPackagePlan) -> str:
    return plan.namespace.replace("_", " ").replace("-", " ").title()


def _description(plan: ToolPackagePlan) -> str:
    if plan.openapi is not None and plan.openapi.provider.description:
        return plan.openapi.provider.description
    return f"Bundled {plan.package_kind} tool source '{plan.namespace}'."


__all__ = ["tool_package_source_id", "tool_source_records_from_package_plans"]
