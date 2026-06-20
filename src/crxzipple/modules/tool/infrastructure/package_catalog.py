from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from crxzipple.modules.tool.application.catalog_models import (
    ToolFunctionCandidate,
    ToolFunctionRequirements,
    ToolFunctionRuntimeKind,
    ToolProviderBackendCandidate,
    ToolSourceCatalogKind,
    ToolSourceCatalogRecord,
    ToolSourceDiscoveryResult,
)
from crxzipple.modules.tool.application.discovery import ToolDiscoveryAdapter
from crxzipple.modules.tool.application.provider_backend_service import (
    PROVIDER_BACKEND_POLICY_METADATA_KEY,
)
from crxzipple.modules.tool.application.specifications import ToolSpec
from crxzipple.modules.tool.application.activation import (
    ToolDependencyRequirement,
    ToolHandlerPlan,
    ToolPackagePlan,
)
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.infrastructure.discovery.openapi import (
    OpenApiDiscoveryProvider,
)


class ToolPackageDiscoveryAdapter(ToolDiscoveryAdapter):
    def __init__(self, package_plans: tuple[ToolPackagePlan, ...]) -> None:
        self._plans_by_source_id = {
            tool_package_source_id(plan): plan for plan in package_plans
        }

    def discover(self, source: ToolSourceCatalogRecord) -> ToolSourceDiscoveryResult:
        plan = self._plans_by_source_id.get(source.source_id)
        if plan is None:
            raise ToolValidationError(
                f"Bundled tool source '{source.source_id}' has no package plan.",
            )
        if plan.package_kind == "local_package":
            return ToolSourceDiscoveryResult.completed(
                source_id=source.source_id,
                candidates=_local_package_candidates(source, plan),
                provider_backend_candidates=_provider_backend_candidates(
                    source,
                    plan,
                ),
                metadata={
                    "source": "bundled_tool_package",
                    "namespace": plan.namespace,
                    "package_kind": plan.package_kind,
                },
            )
        if plan.package_kind == "openapi" and plan.openapi is not None:
            provider = OpenApiDiscoveryProvider(
                plan.openapi.provider,
                capability_ids=plan.openapi.capability_ids,
            )
            return ToolSourceDiscoveryResult.completed(
                source_id=source.source_id,
                candidates=tuple(
                    ToolFunctionCandidate.from_tool_spec(
                        spec,
                        source_id=source.source_id,
                        metadata={
                            "source": "bundled_tool_package",
                            "namespace": plan.namespace,
                            "package_kind": plan.package_kind,
                            "provider_name": spec.provider_name,
                            "manifest_path": plan.manifest_path,
                        },
                    )
                    for spec in provider.discover_specs()
                ),
                provider_backend_candidates=_provider_backend_candidates(
                    source,
                    plan,
                ),
                metadata={
                    "source": "bundled_tool_package",
                    "namespace": plan.namespace,
                    "package_kind": plan.package_kind,
                    "provider_name": plan.openapi.provider.name,
                },
            )
        raise ToolValidationError(
            f"Bundled tool source '{source.source_id}' has unsupported package kind "
            f"'{plan.package_kind}'.",
        )


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


def _local_package_candidates(
    source: ToolSourceCatalogRecord,
    plan: ToolPackagePlan,
) -> tuple[ToolFunctionCandidate, ...]:
    return tuple(
        _candidate_from_local_handler(source, plan, handler)
        for handler in plan.local_handlers
        if handler.tool.enabled
    )


def _provider_backend_candidates(
    source: ToolSourceCatalogRecord,
    plan: ToolPackagePlan,
) -> tuple[ToolProviderBackendCandidate, ...]:
    return tuple(
        ToolProviderBackendCandidate(
            source_id=source.source_id,
            backend_id=backend.backend_id,
            capability=backend.capability,
            display_name=backend.display_name,
            runtime_kind=backend.runtime_kind,
            runtime_ref=backend.runtime_ref,
            requirements=ToolFunctionRequirements(
                credential_requirements=backend.credential_requirements,
            ),
            priority=backend.priority,
            enabled=backend.enabled,
            metadata={
                "source": "bundled_tool_package",
                "namespace": plan.namespace,
                "package_kind": plan.package_kind,
                "manifest_path": plan.manifest_path,
                **dict(backend.metadata),
            },
        )
        for backend in plan.provider_backends
    )


def _candidate_from_local_handler(
    source: ToolSourceCatalogRecord,
    plan: ToolPackagePlan,
    handler: ToolHandlerPlan,
) -> ToolFunctionCandidate:
    spec = ToolSpec.from_tool(handler.tool, provider_name=handler.provider_name)
    provider_backend_policy = _provider_backend_policy_for_function(
        plan,
        function_id=spec.id,
    )
    metadata: dict[str, Any] = {
        "source": "bundled_tool_package",
        "namespace": plan.namespace,
        "package_kind": plan.package_kind,
        "provider_name": handler.provider_name,
        "runtime_key": handler.tool.resolved_runtime_key(),
        "entrypoint": handler.entrypoint,
        "manifest_path": plan.manifest_path,
        "dependencies": tuple(
            _dependency_payload(dependency)
            for dependency in handler.dependencies
        ),
    }
    if provider_backend_policy:
        metadata[PROVIDER_BACKEND_POLICY_METADATA_KEY] = provider_backend_policy
    return ToolFunctionCandidate.from_tool_spec(
        spec,
        source_id=source.source_id,
        stable_key=f"local_package.{plan.namespace}.{spec.id}",
        runtime_kind=ToolFunctionRuntimeKind.LOCAL,
        handler_ref=handler.tool.resolved_runtime_key(),
        metadata=metadata,
    )


def _provider_backend_policy_for_function(
    plan: ToolPackagePlan,
    *,
    function_id: str,
) -> dict[str, Any] | None:
    matching_backends = tuple(
        backend
        for backend in plan.provider_backends
        if function_id in {
            str(item).strip()
            for item in _sequence(backend.metadata.get("stable_functions"))
            if str(item).strip()
        }
    )
    if not matching_backends:
        return None
    primary = sorted(matching_backends, key=lambda backend: backend.priority)[0]
    fallback_backend_ids = [
        backend.backend_id
        for backend in sorted(matching_backends, key=lambda backend: backend.priority)
        if backend.backend_id != primary.backend_id
    ]
    return {
        "capability": primary.capability,
        "default_backend_id": primary.backend_id,
        "fallback_backend_ids": fallback_backend_ids,
        "allowed_backend_ids": [backend.backend_id for backend in matching_backends],
    }


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
        payload["runtime_request"] = _stable_payload(plan.runtime_request)
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
            "provider": _stable_payload(plan.openapi.provider),
            "capability_ids": list(plan.openapi.capability_ids),
            "dependencies": [
                _dependency_payload(dependency)
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


def _dependency_payload(dependency: ToolDependencyRequirement) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": dependency.id,
        "kind": dependency.kind,
        "required": dependency.required,
    }
    if dependency.description:
        payload["description"] = dependency.description
    if dependency.metadata:
        payload["metadata"] = dict(dependency.metadata)
    return payload


def _display_name(plan: ToolPackagePlan) -> str:
    return plan.namespace.replace("_", " ").replace("-", " ").title()


def _description(plan: ToolPackagePlan) -> str:
    if plan.openapi is not None and plan.openapi.provider.description:
        return plan.openapi.provider.description
    return f"Bundled {plan.package_kind} tool source '{plan.namespace}'."


def _stable_payload(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _stable_payload(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(key): _stable_payload(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, tuple | list):
        return [_stable_payload(item) for item in value]
    return value


def _sequence(value: object) -> tuple[object, ...]:
    if value is None:
        return ()
    if isinstance(value, tuple | list):
        return tuple(value)
    return (value,)


__all__ = [
    "ToolPackageDiscoveryAdapter",
    "tool_package_source_id",
    "tool_source_records_from_package_plans",
]
