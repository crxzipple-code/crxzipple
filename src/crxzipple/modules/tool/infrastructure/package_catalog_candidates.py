from __future__ import annotations

from typing import Any

from crxzipple.modules.tool.application.activation import (
    ToolHandlerPlan,
    ToolPackagePlan,
)
from crxzipple.modules.tool.application.catalog_models import (
    ToolFunctionCandidate,
    ToolFunctionRequirements,
    ToolFunctionRuntimeKind,
    ToolProviderBackendCandidate,
    ToolSourceCatalogRecord,
)
from crxzipple.modules.tool.application.provider_backend_service import (
    PROVIDER_BACKEND_POLICY_METADATA_KEY,
)
from crxzipple.modules.tool.application.specifications import ToolSpec
from crxzipple.modules.tool.infrastructure.discovery.openapi import (
    OpenApiDiscoveryProvider,
)
from .package_catalog_payloads import dependency_payload, sequence


def local_package_candidates(
    source: ToolSourceCatalogRecord,
    plan: ToolPackagePlan,
) -> tuple[ToolFunctionCandidate, ...]:
    return tuple(
        _candidate_from_local_handler(source, plan, handler)
        for handler in plan.local_handlers
        if handler.tool.enabled
    )


def openapi_package_candidates(
    source: ToolSourceCatalogRecord,
    plan: ToolPackagePlan,
) -> tuple[ToolFunctionCandidate, ...]:
    if plan.openapi is None:
        return ()
    provider = OpenApiDiscoveryProvider(
        plan.openapi.provider,
        capability_ids=plan.openapi.capability_ids,
    )
    return tuple(
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
    )


def provider_backend_candidates(
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
            dependency_payload(dependency)
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
            for item in sequence(backend.metadata.get("stable_functions"))
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


__all__ = [
    "local_package_candidates",
    "openapi_package_candidates",
    "provider_backend_candidates",
]
