from __future__ import annotations

from dataclasses import dataclass
import importlib
from pathlib import Path
from typing import Any

import yaml

from crxzipple.core.config import (
    PROJECT_ROOT,
    OpenApiCredentialBinding,
    OpenApiProviderSettings,
)
from crxzipple.modules.tool.domain import (
    Tool,
    ToolEnvironment,
    ToolExecutionPolicy,
    ToolExecutionSupport,
    ToolExecutionStrategy,
    ToolKind,
    ToolMode,
    ToolParameter,
    ToolSourceKind,
)
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.infrastructure.discovery.local_catalog import (
    LocalToolCatalog,
    LocalToolHandler,
)
from crxzipple.modules.tool.infrastructure.discovery.openapi import (
    OpenApiDiscoveryProvider,
)
from crxzipple.modules.tool.infrastructure.discovery.providers import (
    ToolDiscoveryRegistry,
)
from crxzipple.modules.tool.infrastructure.runtimes.openapi_remote import (
    register_openapi_remote_handlers,
)
from crxzipple.modules.tool.infrastructure.runtimes.registry import (
    AsyncToolHandler,
    ToolRuntimeRegistry,
)


DEFAULT_TOOL_ROOT = PROJECT_ROOT / "tools"


@dataclass(frozen=True, slots=True)
class LocalToolBinding:
    tool: Tool
    provider_name: str
    entrypoint: str


@dataclass(frozen=True, slots=True)
class RuntimeToolBinding:
    runtime_key: str
    entrypoint: str


@dataclass(frozen=True, slots=True)
class ToolNamespaceDefinition:
    name: str
    root_path: str
    manifest_path: str
    kind: str
    local_bindings: tuple[LocalToolBinding, ...] = ()
    remote_bindings: tuple[RuntimeToolBinding, ...] = ()
    sandbox_bindings: tuple[RuntimeToolBinding, ...] = ()
    openapi_provider: OpenApiProviderSettings | None = None


def discover_tool_namespaces(
    root_dir: str | Path = DEFAULT_TOOL_ROOT,
) -> tuple[ToolNamespaceDefinition, ...]:
    root = Path(root_dir).expanduser().resolve()
    if not root.exists():
        return ()

    namespaces: list[ToolNamespaceDefinition] = []
    for manifest_path in sorted(root.glob("*/tool.yaml")):
        namespaces.append(_load_namespace(manifest_path))
    return tuple(namespaces)


def register_scanned_tool_packages(
    container: Any,
    *,
    root_dir: str | Path = DEFAULT_TOOL_ROOT,
    include_openapi: bool = True,
) -> tuple[str, ...]:
    local_tool_catalog = getattr(container, "local_tool_catalog", None)
    remote_tool_registry = getattr(container, "remote_tool_registry", None)
    sandbox_tool_registry = getattr(container, "sandbox_tool_registry", None)
    tool_discovery_registry = getattr(container, "tool_discovery_registry", None)

    registered_namespaces: list[str] = []
    for namespace in discover_tool_namespaces(root_dir=root_dir):
        if namespace.kind == "local_package":
            if isinstance(local_tool_catalog, LocalToolCatalog):
                for binding in namespace.local_bindings:
                    handler = _build_local_handler(binding.entrypoint, container)
                    if handler is None:
                        continue
                    local_tool_catalog.register(
                        binding.tool,
                        handler,
                        provider_name=binding.provider_name,
                    )
            if isinstance(remote_tool_registry, ToolRuntimeRegistry):
                for binding in namespace.remote_bindings:
                    handler = _build_runtime_handler(binding.entrypoint, container)
                    if handler is None:
                        continue
                    remote_tool_registry.register(binding.runtime_key, handler)
            if isinstance(sandbox_tool_registry, ToolRuntimeRegistry):
                for binding in namespace.sandbox_bindings:
                    handler = _build_runtime_handler(binding.entrypoint, container)
                    if handler is None:
                        continue
                    sandbox_tool_registry.register(binding.runtime_key, handler)
        elif (
            namespace.kind == "openapi"
            and include_openapi
            and namespace.openapi_provider is not None
            and isinstance(tool_discovery_registry, ToolDiscoveryRegistry)
            and isinstance(remote_tool_registry, ToolRuntimeRegistry)
        ):
            provider = OpenApiDiscoveryProvider(namespace.openapi_provider)
            tool_discovery_registry.register(provider)
            register_openapi_remote_handlers(
                remote_tool_registry,
                provider.operations(),
            )
        registered_namespaces.append(namespace.name)
    return tuple(registered_namespaces)


def _load_namespace(manifest_path: Path) -> ToolNamespaceDefinition:
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' must decode to a mapping.",
        )

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
    if kind == "local_package":
        return ToolNamespaceDefinition(
            name=namespace_name,
            root_path=str(manifest_path.parent),
            manifest_path=str(manifest_path),
            kind=kind,
            local_bindings=_load_local_bindings(payload, manifest_path),
            remote_bindings=_load_runtime_bindings(
                payload.get("remote_runtimes", []),
                manifest_path,
            ),
            sandbox_bindings=_load_runtime_bindings(
                payload.get("sandbox_runtimes", []),
                manifest_path,
            ),
        )
    if kind == "openapi":
        return ToolNamespaceDefinition(
            name=namespace_name,
            root_path=str(manifest_path.parent),
            manifest_path=str(manifest_path),
            kind=kind,
            openapi_provider=_load_openapi_provider(payload, manifest_path),
        )

    raise ToolValidationError(
        f"Tool namespace manifest '{manifest_path}' declares unsupported kind '{kind}'.",
    )


def _load_local_bindings(
    payload: dict[str, Any],
    manifest_path: Path,
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
        bindings.append(
            LocalToolBinding(
                tool=_build_tool(item, manifest_path),
                provider_name=str(item.get("provider_name", "local_system")).strip()
                or "local_system",
                entrypoint=_required_string(item, "entrypoint", manifest_path),
            ),
        )
    return tuple(bindings)


def _load_runtime_bindings(
    raw_bindings: object,
    manifest_path: Path,
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
                runtime_key=_required_string(item, "runtime_key", manifest_path),
                entrypoint=_required_string(item, "entrypoint", manifest_path),
            ),
        )
    return tuple(bindings)


def _build_tool(
    payload: dict[str, Any],
    manifest_path: Path,
) -> Tool:
    return Tool(
        id=_required_string(payload, "id", manifest_path),
        name=_required_string(payload, "name", manifest_path),
        description=_required_string(payload, "description", manifest_path),
        kind=_parse_enum(
            payload.get("tool_kind", ToolKind.FUNCTION.value),
            enum_type=ToolKind,
            field_name="tool_kind",
            manifest_path=manifest_path,
        ),
        parameters=_parse_parameters(payload.get("parameters", []), manifest_path),
        tags=_parse_string_list(payload.get("tags", []), "tags", manifest_path),
        required_effect_ids=_parse_string_list(
            payload.get("required_effect_ids", []),
            "required_effect_ids",
            manifest_path,
        ),
        execution_policy=ToolExecutionPolicy(
            timeout_seconds=max(int(payload.get("timeout_seconds", 30)), 1),
            requires_confirmation=bool(payload.get("requires_confirmation", False)),
            mutates_state=bool(payload.get("mutates_state", False)),
        ),
        execution_support=ToolExecutionSupport(
            supported_modes=_parse_enum_list(
                payload.get("supported_modes", [ToolMode.INLINE.value]),
                enum_type=ToolMode,
                field_name="supported_modes",
                manifest_path=manifest_path,
            ),
            supported_strategies=_parse_enum_list(
                payload.get(
                    "supported_strategies",
                    [ToolExecutionStrategy.ASYNC.value],
                ),
                enum_type=ToolExecutionStrategy,
                field_name="supported_strategies",
                manifest_path=manifest_path,
            ),
            supported_environments=_parse_enum_list(
                payload.get(
                    "supported_environments",
                    [ToolEnvironment.LOCAL.value],
                ),
                enum_type=ToolEnvironment,
                field_name="supported_environments",
                manifest_path=manifest_path,
            ),
        ),
        source_kind=_parse_enum(
            payload.get("source_kind", ToolSourceKind.LOCAL_DISCOVERY.value),
            enum_type=ToolSourceKind,
            field_name="source_kind",
            manifest_path=manifest_path,
        ),
        runtime_key=(
            str(payload["runtime_key"]).strip()
            if payload.get("runtime_key") is not None
            else None
        ),
        enabled=bool(payload.get("enabled", True)),
    )


def _load_openapi_provider(
    payload: dict[str, Any],
    manifest_path: Path,
) -> OpenApiProviderSettings:
    spec_raw = str(payload.get("spec", "")).strip()
    if not spec_raw:
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' kind openapi must define spec.",
        )
    spec_path = (manifest_path.parent / spec_raw).resolve()
    if not spec_path.is_file():
        raise ToolValidationError(
            f"OpenAPI spec '{spec_raw}' referenced by '{manifest_path}' was not found.",
        )
    return OpenApiProviderSettings(
        name=_required_string(payload, "namespace", manifest_path),
        spec_location=str(spec_path),
        base_url=(
            str(payload["base_url"]).strip()
            if payload.get("base_url") is not None
            else None
        ),
        description=str(payload.get("description", "")).strip(),
        timeout_seconds=max(int(payload.get("timeout_seconds", 30)), 1),
        credential_bindings=_parse_openapi_credentials(
            payload.get("credentials", {}),
            manifest_path,
        ),
        default_effect_ids=_parse_string_list(
            payload.get("default_effect_ids", []),
            "default_effect_ids",
            manifest_path,
        ),
    )


def _parse_openapi_credentials(
    raw_credentials: object,
    manifest_path: Path,
) -> tuple[OpenApiCredentialBinding, ...]:
    if raw_credentials in (None, {}):
        return ()
    if not isinstance(raw_credentials, dict):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field 'credentials' must be a mapping.",
        )
    bindings: list[OpenApiCredentialBinding] = []
    for raw_scheme_name, raw_binding in raw_credentials.items():
        scheme_name = str(raw_scheme_name).strip()
        if not scheme_name:
            raise ToolValidationError(
                f"Tool namespace manifest '{manifest_path}' credentials require non-empty scheme names.",
            )
        if isinstance(raw_binding, str):
            value = raw_binding.strip()
            if not value:
                raise ToolValidationError(
                    f"Tool namespace manifest '{manifest_path}' credential binding '{scheme_name}' cannot be empty.",
                )
            bindings.append(
                OpenApiCredentialBinding(
                    scheme_name=scheme_name,
                    source=value,
                ),
            )
            continue
        if not isinstance(raw_binding, dict):
            raise ToolValidationError(
                f"Tool namespace manifest '{manifest_path}' credential binding '{scheme_name}' must be a string or mapping.",
            )
        bindings.append(
            OpenApiCredentialBinding(
                scheme_name=scheme_name,
                source=(
                    str(raw_binding["source"]).strip()
                    if raw_binding.get("source") is not None
                    else None
                ),
                username_source=(
                    str(raw_binding.get("username_source") or "").strip() or None
                ),
                password_source=(
                    str(raw_binding.get("password_source") or "").strip() or None
                ),
            ),
        )
    return tuple(bindings)


def _parse_parameters(
    raw_parameters: object,
    manifest_path: Path,
) -> tuple[ToolParameter, ...]:
    if not isinstance(raw_parameters, list):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field 'parameters' must be a list.",
        )
    parameters: list[ToolParameter] = []
    for item in raw_parameters:
        if not isinstance(item, dict):
            raise ToolValidationError(
                f"Tool namespace manifest '{manifest_path}' parameter entries must be mappings.",
            )
        parameters.append(
            ToolParameter(
                name=_required_string(item, "name", manifest_path),
                data_type=_required_string(item, "data_type", manifest_path),
                description=str(item.get("description", "")).strip(),
                required=bool(item.get("required", True)),
            ),
        )
    return tuple(parameters)


def _parse_string_list(
    raw_values: object,
    field_name: str,
    manifest_path: Path,
) -> tuple[str, ...]:
    if not isinstance(raw_values, list):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field '{field_name}' must be a list.",
        )
    return tuple(
        str(item).strip()
        for item in raw_values
        if str(item).strip()
    )


def _parse_enum_list(
    raw_values: object,
    *,
    enum_type,
    field_name: str,
    manifest_path: Path,
) -> tuple[Any, ...]:
    if not isinstance(raw_values, list):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field '{field_name}' must be a list.",
        )
    return tuple(
        _parse_enum(
            value,
            enum_type=enum_type,
            field_name=field_name,
            manifest_path=manifest_path,
        )
        for value in raw_values
    )


def _parse_enum(
    raw_value: object,
    *,
    enum_type,
    field_name: str,
    manifest_path: Path,
):
    try:
        return enum_type(str(raw_value).strip())
    except ValueError as exc:
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field '{field_name}' "
            f"declares unsupported value '{raw_value}'.",
        ) from exc


def _required_string(
    payload: dict[str, Any],
    field_name: str,
    manifest_path: Path,
) -> str:
    value = str(payload.get(field_name, "")).strip()
    if not value:
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' must define non-empty '{field_name}'.",
        )
    return value


def _build_local_handler(
    entrypoint: str,
    container: Any,
) -> LocalToolHandler | None:
    builder = _load_entrypoint(entrypoint)
    handler = builder(container)
    if handler is not None and not callable(handler):
        raise ToolValidationError(
            f"Tool entrypoint '{entrypoint}' did not return a callable handler.",
        )
    return handler


def _build_runtime_handler(
    entrypoint: str,
    container: Any,
) -> AsyncToolHandler | None:
    builder = _load_entrypoint(entrypoint)
    handler = builder(container)
    if handler is not None and not callable(handler):
        raise ToolValidationError(
            f"Tool runtime entrypoint '{entrypoint}' did not return a callable handler.",
        )
    return handler


def _load_entrypoint(entrypoint: str):
    module_name, separator, symbol_name = entrypoint.partition(":")
    module_name = module_name.strip()
    symbol_name = symbol_name.strip()
    if separator != ":" or not module_name or not symbol_name:
        raise ToolValidationError(
            f"Tool entrypoint '{entrypoint}' must use the form 'module.path:callable_name'.",
        )
    module = importlib.import_module(module_name)
    target = getattr(module, symbol_name, None)
    if target is None:
        raise ToolValidationError(
            f"Tool entrypoint '{entrypoint}' could not resolve callable '{symbol_name}'.",
        )
    if not callable(target):
        raise ToolValidationError(
            f"Tool entrypoint '{entrypoint}' resolved non-callable symbol '{symbol_name}'.",
        )
    return target
