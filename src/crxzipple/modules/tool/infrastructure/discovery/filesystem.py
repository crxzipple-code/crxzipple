from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import importlib.util
import inspect
import json
from pathlib import Path
from typing import Any

from crxzipple.modules.tool.application.specifications import ToolSpec
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


@dataclass(frozen=True, slots=True)
class FilesystemLocalToolHandler:
    module_path: str
    attribute_path: str

    def __call__(self, arguments: dict[str, Any]) -> Any:
        handler = _load_entrypoint(self.module_path, self.attribute_path)
        return handler(arguments)


class FilesystemLocalToolDiscoveryProvider:
    source_kind = ToolSourceKind.LOCAL_DISCOVERY

    def __init__(
        self,
        catalog: LocalToolCatalog,
        root_paths: tuple[str, ...],
        *,
        name: str = "local_filesystem",
    ) -> None:
        self.catalog = catalog
        self.root_paths = root_paths
        self.name = name
        self.description = "Discovers local tools from tool.json manifests on disk."

    def discover_specs(self) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        for manifest_path in _iter_manifest_paths(self.root_paths):
            spec, handler = _load_manifest(manifest_path, provider_name=self.name)
            self.catalog.register(
                _tool_from_spec(spec),
                handler,
                provider_name=self.name,
            )
            specs.append(spec)
        return specs


def _iter_manifest_paths(root_paths: tuple[str, ...]) -> list[Path]:
    manifest_paths: list[Path] = []
    for raw_path in root_paths:
        path = Path(raw_path).expanduser()
        if not path.exists():
            continue
        if path.is_file():
            if path.name == "tool.json":
                manifest_paths.append(path)
            continue
        manifest_paths.extend(sorted(path.rglob("tool.json")))
    return sorted(dict.fromkeys(manifest_paths))


def _load_manifest(
    manifest_path: Path,
    *,
    provider_name: str,
) -> tuple[ToolSpec, LocalToolHandler]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ToolValidationError(
            f"Tool manifest '{manifest_path}' must decode to a JSON object.",
        )

    entrypoint = str(payload.get("entrypoint", "")).strip()
    if not entrypoint:
        raise ToolValidationError(
            f"Tool manifest '{manifest_path}' must define entrypoint.",
        )

    module_path, attribute_path = _resolve_entrypoint(
        manifest_path.parent,
        entrypoint,
    )
    handler = FilesystemLocalToolHandler(
        module_path=module_path,
        attribute_path=attribute_path,
    )

    spec = ToolSpec(
        id=_required_string(payload, "id", manifest_path),
        name=_required_string(payload, "name", manifest_path),
        description=_required_string(payload, "description", manifest_path),
        provider_name=provider_name,
        kind=_parse_kind(payload.get("kind", ToolKind.FUNCTION.value), manifest_path),
        parameters=_parse_parameters(payload.get("parameters", []), manifest_path),
        tags=_parse_tags(payload.get("tags", []), manifest_path),
        required_effect_ids=_parse_effect_ids(
            payload.get("required_effect_ids", []),
            manifest_path,
        ),
        execution_policy=ToolExecutionPolicy(
            timeout_seconds=int(payload.get("timeout_seconds", 30)),
            requires_confirmation=bool(payload.get("requires_confirmation", False)),
            mutates_state=bool(payload.get("mutates_state", False)),
        ),
        execution_support=ToolExecutionSupport(
            supported_modes=_parse_modes(
                payload.get("supported_modes", [ToolMode.INLINE.value]),
                manifest_path,
            ),
            supported_strategies=_parse_strategies(
                payload.get(
                    "supported_strategies",
                    [ToolExecutionStrategy.ASYNC.value],
                ),
                manifest_path,
            ),
            supported_environments=_parse_environments(
                payload.get("supported_environments", [ToolEnvironment.LOCAL.value]),
                manifest_path,
            ),
        ),
        source_kind=ToolSourceKind.LOCAL_DISCOVERY,
        runtime_key=str(payload.get("runtime_key") or payload.get("id") or "").strip()
        or None,
        enabled=bool(payload.get("enabled", True)),
    )
    return spec, handler


def _required_string(
    payload: dict[str, Any],
    field_name: str,
    manifest_path: Path,
) -> str:
    value = str(payload.get(field_name, "")).strip()
    if not value:
        raise ToolValidationError(
            f"Tool manifest '{manifest_path}' must define non-empty '{field_name}'.",
        )
    return value


def _parse_kind(raw: Any, manifest_path: Path) -> ToolKind:
    try:
        return ToolKind(str(raw))
    except ValueError as exc:
        raise ToolValidationError(
            f"Tool manifest '{manifest_path}' declares unsupported kind '{raw}'.",
        ) from exc


def _parse_parameters(raw: Any, manifest_path: Path) -> tuple[ToolParameter, ...]:
    if not isinstance(raw, list):
        raise ToolValidationError(
            f"Tool manifest '{manifest_path}' field 'parameters' must be a list.",
        )

    parameters: list[ToolParameter] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ToolValidationError(
                f"Tool manifest '{manifest_path}' parameter entries must be objects.",
            )
        parameters.append(
            ToolParameter(
                name=_required_parameter_field(item, "name", manifest_path),
                data_type=_required_parameter_field(item, "data_type", manifest_path),
                description=str(item.get("description", "")).strip(),
                required=bool(item.get("required", True)),
            ),
        )
    return tuple(parameters)


def _required_parameter_field(
    payload: dict[str, Any],
    field_name: str,
    manifest_path: Path,
) -> str:
    value = str(payload.get(field_name, "")).strip()
    if not value:
        raise ToolValidationError(
            f"Tool manifest '{manifest_path}' parameters require non-empty '{field_name}'.",
        )
    return value


def _parse_tags(raw: Any, manifest_path: Path) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise ToolValidationError(
            f"Tool manifest '{manifest_path}' field 'tags' must be a list.",
        )
    return tuple(str(tag).strip() for tag in raw if str(tag).strip())


def _parse_effect_ids(raw: Any, manifest_path: Path) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise ToolValidationError(
            f"Tool manifest '{manifest_path}' field 'required_effect_ids' must be a list.",
        )
    return tuple(str(effect_id).strip() for effect_id in raw if str(effect_id).strip())


def _parse_modes(raw: Any, manifest_path: Path) -> tuple[ToolMode, ...]:
    return tuple(_parse_enum_sequence(raw, ToolMode, "supported_modes", manifest_path))


def _parse_strategies(raw: Any, manifest_path: Path) -> tuple[ToolExecutionStrategy, ...]:
    return tuple(
        _parse_enum_sequence(
            raw,
            ToolExecutionStrategy,
            "supported_strategies",
            manifest_path,
        ),
    )


def _parse_environments(raw: Any, manifest_path: Path) -> tuple[ToolEnvironment, ...]:
    return tuple(
        _parse_enum_sequence(
            raw,
            ToolEnvironment,
            "supported_environments",
            manifest_path,
        ),
    )


def _parse_enum_sequence(
    raw: Any,
    enum_type: type[ToolMode | ToolExecutionStrategy | ToolEnvironment],
    field_name: str,
    manifest_path: Path,
) -> list[ToolMode | ToolExecutionStrategy | ToolEnvironment]:
    if not isinstance(raw, list):
        raise ToolValidationError(
            f"Tool manifest '{manifest_path}' field '{field_name}' must be a list.",
        )

    values: list[ToolMode | ToolExecutionStrategy | ToolEnvironment] = []
    for item in raw:
        try:
            values.append(enum_type(str(item)))
        except ValueError as exc:
            raise ToolValidationError(
                f"Tool manifest '{manifest_path}' field '{field_name}' contains unsupported value '{item}'.",
            ) from exc
    return values


def _resolve_entrypoint(manifest_dir: Path, entrypoint: str) -> tuple[str, str]:
    module_ref, separator, attribute_path = entrypoint.partition(":")
    if separator != ":" or not module_ref.strip() or not attribute_path.strip():
        raise ToolValidationError(
            "Local filesystem tool entrypoint must use '<relative_file.py>:<callable>' syntax.",
        )

    module_path = (manifest_dir / module_ref.strip()).resolve()
    if module_path.suffix != ".py":
        raise ToolValidationError(
            f"Local filesystem tool entrypoint '{entrypoint}' must point to a Python file.",
        )
    if not module_path.exists():
        raise ToolValidationError(
            f"Local filesystem tool entrypoint file '{module_path}' was not found.",
        )
    return str(module_path), attribute_path.strip()


def _tool_from_spec(spec: ToolSpec) -> Tool:
    return Tool(
        id=spec.id,
        name=spec.name,
        description=spec.description,
        kind=spec.kind,
        parameters=spec.parameters,
        tags=spec.tags,
        execution_policy=spec.execution_policy,
        execution_support=spec.execution_support,
        source_kind=spec.source_kind,
        runtime_key=spec.runtime_key,
        enabled=spec.enabled,
    )


@lru_cache(maxsize=None)
def _load_entrypoint(module_path: str, attribute_path: str) -> LocalToolHandler:
    module_name = (
        "crxzipple_dynamic_local_tool_"
        + str(abs(hash(module_path))).replace("-", "_")
    )
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ToolValidationError(
            f"Could not load local tool module from '{module_path}'.",
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    target: Any = module
    for attribute_name in attribute_path.split("."):
        if not hasattr(target, attribute_name):
            raise ToolValidationError(
                f"Local tool entrypoint '{module_path}:{attribute_path}' was not found.",
            )
        target = getattr(target, attribute_name)

    if not callable(target):
        raise ToolValidationError(
            f"Local tool entrypoint '{module_path}:{attribute_path}' is not callable.",
        )
    if inspect.ismethod(target):
        raise ToolValidationError(
            f"Local tool entrypoint '{module_path}:{attribute_path}' must be a top-level callable.",
        )
    return target
