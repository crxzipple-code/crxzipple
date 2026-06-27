from __future__ import annotations

from crxzipple.modules.tool.application.catalog_models import (
    ToolSourceCatalogRecord,
    ToolSourceDiscoveryResult,
)
from crxzipple.modules.tool.application.discovery import ToolDiscoveryAdapter
from crxzipple.modules.tool.application.activation import ToolPackagePlan
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from .package_catalog_candidates import (
    local_package_candidates,
    openapi_package_candidates,
    provider_backend_candidates,
)
from .package_catalog_records import (
    tool_package_source_id,
    tool_source_records_from_package_plans,
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
                candidates=local_package_candidates(source, plan),
                provider_backend_candidates=provider_backend_candidates(source, plan),
                metadata={
                    "source": "bundled_tool_package",
                    "namespace": plan.namespace,
                    "package_kind": plan.package_kind,
                },
            )
        if plan.package_kind == "openapi" and plan.openapi is not None:
            return ToolSourceDiscoveryResult.completed(
                source_id=source.source_id,
                candidates=openapi_package_candidates(source, plan),
                provider_backend_candidates=provider_backend_candidates(source, plan),
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


__all__ = [
    "ToolPackageDiscoveryAdapter",
    "tool_package_source_id",
    "tool_source_records_from_package_plans",
]
