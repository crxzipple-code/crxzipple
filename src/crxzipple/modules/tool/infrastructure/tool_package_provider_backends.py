from __future__ import annotations

from pathlib import Path

from crxzipple.modules.tool.application.activation import ToolProviderBackendPlan
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.infrastructure.tool_package_access import (
    parse_credential_requirement_sets,
)
from crxzipple.modules.tool.infrastructure.tool_package_manifest_values import (
    mapping_payload,
    required_string,
)


def load_provider_backend_plans(
    raw_backends: object,
    manifest_path: Path,
    *,
    namespace: str,
) -> tuple[ToolProviderBackendPlan, ...]:
    if raw_backends in (None, []):
        return ()
    if not isinstance(raw_backends, list):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field 'provider_backends' must be a list.",
        )
    backends: list[ToolProviderBackendPlan] = []
    for item in raw_backends:
        if not isinstance(item, dict):
            raise ToolValidationError(
                f"Tool namespace manifest '{manifest_path}' provider_backends entries must be mappings.",
            )
        backends.append(
            _load_provider_backend_plan(
                item,
                manifest_path,
                namespace=namespace,
            ),
        )
    return tuple(backends)


def _load_provider_backend_plan(
    item: dict[str, object],
    manifest_path: Path,
    *,
    namespace: str,
) -> ToolProviderBackendPlan:
    backend_id = required_string(item, "id", manifest_path)
    runtime_ref = required_string(item, "runtime_ref", manifest_path)
    runtime_kind = str(item.get("runtime_kind", "local")).strip() or "local"
    if runtime_kind not in {
        "local",
        "remote",
        "sandbox",
        "mcp",
        "openapi",
        "cli",
        "provider_backend",
    }:
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' provider backend runtime_kind "
            f"'{runtime_kind}' is unsupported.",
        )
    return ToolProviderBackendPlan(
        namespace=namespace,
        backend_id=backend_id,
        capability=str(item.get("capability", "custom")).strip() or "custom",
        display_name=(
            str(item.get("display_name") or item.get("name") or backend_id).strip()
            or backend_id
        ),
        runtime_kind=runtime_kind,
        runtime_ref=runtime_ref,
        credential_requirements=parse_credential_requirement_sets(
            item.get("credential_requirements", []),
            manifest_path,
            tool_id=backend_id,
            runtime_key=runtime_ref,
        ),
        priority=max(int(item.get("priority", 100)), 0),
        enabled=bool(item.get("enabled", True)),
        metadata=mapping_payload(item.get("metadata")),
    )
