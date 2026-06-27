from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from crxzipple.modules.tool.application.activation import (
    ToolDependencyRequirement,
    ToolOpenApiPlan,
    ToolRuntimeKind,
)
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.infrastructure.tool_package_access import (
    load_openapi_provider_from_manifest,
)
from crxzipple.modules.tool.infrastructure.tool_package_manifest_values import (
    combined_capability_ids,
    load_capability_ids,
    load_dependency_requirements,
    load_runtime_request_metadata,
)
from crxzipple.modules.tool.infrastructure.tool_package_manifest_parsers import (
    required_string,
)
from crxzipple.modules.tool.infrastructure.tool_package_models import (
    DEFAULT_TOOL_ROOT,
    LocalToolBinding,
    RuntimeToolBinding,
    ToolNamespaceDefinition,
)
from crxzipple.modules.tool.infrastructure.tool_package_provider_backends import (
    load_provider_backend_plans,
)
from crxzipple.modules.tool.infrastructure.tool_package_tool_declarations import (
    build_tool_from_manifest,
)


def discover_tool_namespaces(
    root_dir: str | Path = DEFAULT_TOOL_ROOT,
) -> tuple[ToolNamespaceDefinition, ...]:
    return discover_tool_package_plans(root_dir=root_dir)


def discover_tool_package_plans(
    root_dir: str | Path = DEFAULT_TOOL_ROOT,
) -> tuple[ToolNamespaceDefinition, ...]:
    root = Path(root_dir).expanduser().resolve()
    if not root.exists():
        return ()

    plans: list[ToolNamespaceDefinition] = []
    for manifest_path in sorted(root.glob("*/tool.yaml")):
        plans.append(load_tool_package_plan(manifest_path))
    return tuple(plans)


def load_tool_package_plan(manifest_path: str | Path) -> ToolNamespaceDefinition:
    return _load_namespace(Path(manifest_path).expanduser().resolve())


def _load_yaml_mapping(manifest_path: Path) -> dict[str, object]:
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    payload = yaml.load(manifest_path.read_text(encoding="utf-8"), Loader=loader)
    if not isinstance(payload, dict):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' must decode to a mapping.",
        )
    return payload


def _load_namespace(manifest_path: Path) -> ToolNamespaceDefinition:
    payload = _load_yaml_mapping(manifest_path)

    namespace_name = str(payload.get("namespace", "")).strip()
    if not namespace_name:
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' must define namespace.",
        )
    if manifest_path.parent.name != namespace_name:
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' namespace '{namespace_name}' "
            f"must match directory name '{manifest_path.parent.name}'.",
        )

    kind = str(payload.get("kind", "")).strip()
    package_dependencies = load_dependency_requirements(
        payload.get("dependencies", []),
        manifest_path,
    )
    package_capability_ids = load_capability_ids(payload, manifest_path)
    if kind == "local_package":
        return ToolNamespaceDefinition(
            namespace=namespace_name,
            root_path=str(manifest_path.parent),
            manifest_path=str(manifest_path),
            package_kind=kind,
            capability_ids=package_capability_ids,
            runtime_request=load_runtime_request_metadata(
                payload.get("runtime_request"),
                manifest_path,
            ),
            local_handlers=_load_local_bindings(
                payload,
                manifest_path,
                namespace=namespace_name,
                package_dependencies=package_dependencies,
                package_capability_ids=package_capability_ids,
            ),
            remote_runtimes=_load_runtime_bindings(
                payload.get("remote_runtimes", []),
                manifest_path,
                namespace=namespace_name,
                runtime_kind="remote",
                package_dependencies=package_dependencies,
                package_capability_ids=package_capability_ids,
            ),
            sandbox_runtimes=_load_runtime_bindings(
                payload.get("sandbox_runtimes", []),
                manifest_path,
                namespace=namespace_name,
                runtime_kind="sandbox",
                package_dependencies=package_dependencies,
                package_capability_ids=package_capability_ids,
            ),
            provider_backends=load_provider_backend_plans(
                payload.get("provider_backends", []),
                manifest_path,
                namespace=namespace_name,
            ),
        )
    if kind == "openapi":
        return ToolNamespaceDefinition(
            namespace=namespace_name,
            root_path=str(manifest_path.parent),
            manifest_path=str(manifest_path),
            package_kind=kind,
            capability_ids=package_capability_ids,
            runtime_request=load_runtime_request_metadata(
                payload.get("runtime_request"),
                manifest_path,
            ),
            openapi=ToolOpenApiPlan(
                namespace=namespace_name,
                provider=load_openapi_provider_from_manifest(payload, manifest_path),
                capability_ids=package_capability_ids,
                dependencies=package_dependencies,
            ),
            provider_backends=load_provider_backend_plans(
                payload.get("provider_backends", []),
                manifest_path,
                namespace=namespace_name,
            ),
        )

    raise ToolValidationError(
        f"Tool namespace manifest '{manifest_path}' declares unsupported kind '{kind}'.",
    )


def _load_local_bindings(
    payload: dict[str, Any],
    manifest_path: Path,
    *,
    namespace: str,
    package_dependencies: tuple[ToolDependencyRequirement, ...],
    package_capability_ids: tuple[str, ...],
) -> tuple[LocalToolBinding, ...]:
    raw_tools = payload.get("local_tools", [])
    if not isinstance(raw_tools, list):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field 'local_tools' must be a list.",
        )
    bindings: list[LocalToolBinding] = []
    for item in raw_tools:
        if not isinstance(item, dict):
            raise ToolValidationError(
                f"Tool namespace manifest '{manifest_path}' local_tools entries must be mappings.",
            )
        dependencies = (
            package_dependencies
            + load_dependency_requirements(
                item.get("dependencies", []),
                manifest_path,
            )
        )
        capability_ids = combined_capability_ids(
            package_capability_ids,
            load_capability_ids(item, manifest_path),
        )
        bindings.append(
            LocalToolBinding(
                namespace=namespace,
                tool=build_tool_from_manifest(
                    item,
                    manifest_path,
                    dependency_requirements=dependencies,
                    capability_ids=capability_ids,
                ),
                provider_name=str(item.get("provider_name", "local_system")).strip()
                or "local_system",
                entrypoint=required_string(item, "entrypoint", manifest_path),
                capability_ids=capability_ids,
                dependencies=dependencies,
            ),
        )
    return tuple(bindings)


def _load_runtime_bindings(
    raw_bindings: object,
    manifest_path: Path,
    *,
    namespace: str,
    runtime_kind: ToolRuntimeKind,
    package_dependencies: tuple[ToolDependencyRequirement, ...],
    package_capability_ids: tuple[str, ...],
) -> tuple[RuntimeToolBinding, ...]:
    if not isinstance(raw_bindings, list):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' runtime binding lists must be arrays.",
        )
    bindings: list[RuntimeToolBinding] = []
    for item in raw_bindings:
        if not isinstance(item, dict):
            raise ToolValidationError(
                f"Tool namespace manifest '{manifest_path}' runtime entries must be mappings.",
            )
        bindings.append(
            RuntimeToolBinding(
                namespace=namespace,
                runtime_key=required_string(item, "runtime_key", manifest_path),
                entrypoint=required_string(item, "entrypoint", manifest_path),
                runtime_kind=runtime_kind,
                capability_ids=combined_capability_ids(
                    package_capability_ids,
                    load_capability_ids(item, manifest_path),
                ),
                dependencies=(
                    package_dependencies
                    + load_dependency_requirements(
                        item.get("dependencies", []),
                        manifest_path,
                    )
                ),
            ),
        )
    return tuple(bindings)
