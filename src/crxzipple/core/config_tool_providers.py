from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from crxzipple.core.config_env import load_structured_config, optional_positive_int


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OPENAPI_PROVIDER_DIR = PROJECT_ROOT / "config" / "tool_providers"


@dataclass(frozen=True, slots=True)
class OpenApiCredentialBinding:
    scheme_name: str
    credential_binding_id: str | None = None
    username_binding_id: str | None = None
    password_binding_id: str | None = None


@dataclass(frozen=True, slots=True)
class OpenApiProviderSettings:
    name: str
    spec_location: str
    base_url: str | None = None
    description: str = ""
    timeout_seconds: int = 30
    max_concurrency: int | None = None
    credential_bindings: tuple[OpenApiCredentialBinding, ...] = ()
    default_effect_ids: tuple[str, ...] = ()
    runtime_requirements: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "runtime_requirements",
            tuple(
                dict.fromkeys(
                    str(requirement).strip()
                    for requirement in self.runtime_requirements
                    if str(requirement).strip()
                ),
            ),
        )


@dataclass(frozen=True, slots=True)
class McpProviderSettings:
    name: str
    command: tuple[str, ...] = ()
    transport: str = "stdio"
    endpoint_url: str | None = None
    description: str = ""
    timeout_seconds: int = 30
    max_concurrency: int | None = None
    default_effect_ids: tuple[str, ...] = ()
    runtime_requirements: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        transport = self.transport.strip().lower()
        if transport not in {"stdio", "http"}:
            raise ValueError(
                f"MCP provider '{self.name}' transport must be one of: http, stdio.",
            )
        command = tuple(part.strip() for part in self.command if part.strip())
        endpoint_url = self.endpoint_url.strip() if isinstance(self.endpoint_url, str) else ""
        if transport == "stdio" and not command:
            raise ValueError(f"MCP provider '{self.name}' command cannot be empty.")
        if transport == "http" and not endpoint_url:
            raise ValueError(f"MCP provider '{self.name}' endpoint_url cannot be empty.")
        object.__setattr__(self, "transport", transport)
        object.__setattr__(self, "command", command)
        object.__setattr__(self, "endpoint_url", endpoint_url or None)
        object.__setattr__(
            self,
            "runtime_requirements",
            tuple(
                dict.fromkeys(
                    str(requirement).strip()
                    for requirement in self.runtime_requirements
                    if str(requirement).strip()
                ),
            ),
        )


def load_openapi_provider_settings() -> tuple[OpenApiProviderSettings, ...]:
    providers_by_name: dict[str, OpenApiProviderSettings] = {}

    for config_path in _iter_openapi_provider_config_paths():
        for provider in _load_openapi_provider_settings_from_path(config_path):
            providers_by_name[provider.name] = provider

    raw = os.getenv("APP_TOOL_OPENAPI_PROVIDERS")
    if raw is None or not raw.strip():
        return tuple(providers_by_name.values())

    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError("APP_TOOL_OPENAPI_PROVIDERS must decode to a JSON list.")

    for item in payload:
        provider = _build_openapi_provider_settings(
            item,
            source_description="APP_TOOL_OPENAPI_PROVIDERS",
        )
        providers_by_name[provider.name] = provider

    return tuple(providers_by_name.values())


def load_mcp_provider_settings() -> tuple[McpProviderSettings, ...]:
    raw = os.getenv("APP_TOOL_MCP_PROVIDERS")
    if raw is None or not raw.strip():
        return ()

    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError("APP_TOOL_MCP_PROVIDERS must decode to a JSON list.")

    providers: list[McpProviderSettings] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError(
                "APP_TOOL_MCP_PROVIDERS items must decode to JSON objects.",
            )

        name = str(item.get("name", "")).strip()
        if not name:
            raise ValueError("MCP provider name cannot be empty.")

        transport = str(item.get("transport") or "stdio").strip().lower()
        endpoint_url = item.get("endpoint_url")
        if endpoint_url is not None and not isinstance(endpoint_url, str):
            raise ValueError(
                f"MCP provider '{name}' endpoint_url must be a string when provided.",
            )
        command = item.get("command")
        args = item.get("args", [])
        command_parts: tuple[str, ...]
        if isinstance(command, list):
            command_parts = tuple(str(part).strip() for part in command if str(part).strip())
        elif isinstance(command, str) and command.strip():
            if not isinstance(args, list):
                raise ValueError(
                    f"MCP provider '{name}' args must decode to a JSON list.",
                )
            command_parts = (
                command.strip(),
                *(str(part).strip() for part in args if str(part).strip()),
            )
        elif transport == "http":
            command_parts = ()
        else:
            raise ValueError(
                f"MCP provider '{name}' must define command as a string or list.",
            )

        if transport == "stdio" and not command_parts:
            raise ValueError(f"MCP provider '{name}' command cannot be empty.")

        providers.append(
            McpProviderSettings(
                name=name,
                command=command_parts,
                transport=transport,
                endpoint_url=endpoint_url,
                description=str(item.get("description", "")).strip(),
                timeout_seconds=max(int(item.get("timeout_seconds", 30)), 1),
                max_concurrency=optional_positive_int(
                    item.get("max_concurrency"),
                    label=f"MCP provider '{name}' max_concurrency",
                ),
                default_effect_ids=tuple(
                    str(part).strip()
                    for part in item.get("default_effect_ids", []) or []
                    if str(part).strip()
                ),
                runtime_requirements=tuple(
                    str(part).strip()
                    for part in item.get("runtime_requirements", []) or []
                    if str(part).strip()
                ),
            ),
        )

    return tuple(providers)


def _iter_openapi_provider_config_paths() -> tuple[Path, ...]:
    raw = os.getenv("APP_TOOL_OPENAPI_PROVIDER_PATHS", "").strip()
    if raw:
        configured_paths = [
            Path(part.strip()).expanduser()
            for part in raw.split(os.pathsep)
            if part.strip()
        ]
    elif DEFAULT_OPENAPI_PROVIDER_DIR.exists():
        configured_paths = [DEFAULT_OPENAPI_PROVIDER_DIR]
    else:
        configured_paths = []

    resolved_files: list[Path] = []
    for path in configured_paths:
        if path.is_dir():
            resolved_files.extend(
                candidate
                for pattern in ("*.yaml", "*.yml", "*.json")
                for candidate in sorted(path.glob(pattern))
                if candidate.is_file()
            )
            continue
        if path.is_file():
            resolved_files.append(path)

    unique_files: list[Path] = []
    seen: set[Path] = set()
    for path in resolved_files:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_files.append(resolved)
    return tuple(unique_files)


def _load_openapi_provider_settings_from_path(
    config_path: Path,
) -> tuple[OpenApiProviderSettings, ...]:
    payload = load_structured_config(config_path)
    if isinstance(payload, dict):
        items = [payload]
    elif isinstance(payload, list):
        items = payload
    else:
        raise ValueError(
            f"OpenAPI provider config '{config_path}' must decode to an object or list.",
        )

    providers: list[OpenApiProviderSettings] = []
    for item in items:
        providers.append(
            _build_openapi_provider_settings(
                item,
                source_path=config_path,
                source_description=str(config_path),
            ),
        )
    return tuple(providers)


def _build_openapi_provider_settings(
    raw: object,
    *,
    source_path: Path | None = None,
    source_description: str,
) -> OpenApiProviderSettings:
    if not isinstance(raw, dict):
        raise ValueError(
            f"{source_description} items must decode to JSON/YAML objects.",
        )

    name = str(raw.get("name", "")).strip()
    spec_location = str(
        raw.get("spec_location") or raw.get("spec_url") or raw.get("spec_path") or "",
    ).strip()
    if not name:
        raise ValueError("OpenAPI provider name cannot be empty.")
    if not spec_location:
        raise ValueError(
            f"OpenAPI provider '{name}' must define spec_location/spec_url/spec_path.",
        )

    return OpenApiProviderSettings(
        name=name,
        spec_location=_resolve_openapi_spec_location(
            spec_location,
            source_path=source_path,
        ),
        base_url=(
            str(raw["base_url"]).strip()
            if raw.get("base_url") is not None
            else None
        ),
        description=str(raw.get("description", "")).strip(),
        timeout_seconds=max(int(raw.get("timeout_seconds", 30)), 1),
        max_concurrency=optional_positive_int(
            raw.get("max_concurrency"),
            label=f"OpenAPI provider '{name}' max_concurrency",
        ),
        credential_bindings=_load_openapi_credential_bindings(
            raw.get("credentials", {}),
            provider_name=name,
        ),
        default_effect_ids=tuple(
            str(item).strip()
            for item in raw.get("default_effect_ids", []) or []
            if str(item).strip()
        ),
        runtime_requirements=tuple(
            str(item).strip()
            for item in raw.get("runtime_requirements", []) or []
            if str(item).strip()
        ),
    )


def _resolve_openapi_spec_location(
    spec_location: str,
    *,
    source_path: Path | None,
) -> str:
    if source_path is None:
        return spec_location
    if "://" in spec_location or spec_location.startswith("file:"):
        return spec_location
    candidate = Path(spec_location).expanduser()
    if candidate.is_absolute():
        return str(candidate)
    return str((source_path.parent / candidate).resolve())


def _load_openapi_credential_bindings(
    raw: object,
    *,
    provider_name: str,
) -> tuple[OpenApiCredentialBinding, ...]:
    if raw in (None, {}):
        return ()
    if not isinstance(raw, dict):
        raise ValueError(
            f"OpenAPI provider '{provider_name}' credentials must decode to a JSON object.",
        )

    bindings: list[OpenApiCredentialBinding] = []
    for scheme_name, value in raw.items():
        normalized_scheme_name = str(scheme_name).strip()
        if not normalized_scheme_name:
            raise ValueError(
                f"OpenAPI provider '{provider_name}' credential bindings require non-empty scheme names.",
            )

        if isinstance(value, str):
            credential_binding_id = value.strip()
            if not credential_binding_id:
                raise ValueError(
                    f"OpenAPI provider '{provider_name}' credential binding '{normalized_scheme_name}' cannot be empty.",
                )
            _reject_direct_openapi_credential_source(
                credential_binding_id,
                provider_name=provider_name,
                scheme_name=normalized_scheme_name,
                field_name="credential_binding_id",
            )
            bindings.append(
                OpenApiCredentialBinding(
                    scheme_name=normalized_scheme_name,
                    credential_binding_id=credential_binding_id,
                ),
            )
            continue

        if not isinstance(value, dict):
            raise ValueError(
                f"OpenAPI provider '{provider_name}' credential binding '{normalized_scheme_name}' must be a string or object.",
            )

        _reject_legacy_openapi_credential_fields(
            value,
            provider_name=provider_name,
            scheme_name=normalized_scheme_name,
        )
        credential_binding_id = _optional_mapping_text(
            value,
            "credential_binding_id",
        )
        username_binding_id = _optional_mapping_text(
            value,
            "username_binding_id",
        )
        password_binding_id = _optional_mapping_text(
            value,
            "password_binding_id",
        )

        if credential_binding_id is None and (
            username_binding_id is None or password_binding_id is None
        ):
            raise ValueError(
                f"OpenAPI provider '{provider_name}' credential binding '{normalized_scheme_name}' must define credential_binding_id or username/password binding ids.",
            )

        bindings.append(
            OpenApiCredentialBinding(
                scheme_name=normalized_scheme_name,
                credential_binding_id=credential_binding_id,
                username_binding_id=username_binding_id,
                password_binding_id=password_binding_id,
            ),
        )

    return tuple(bindings)


def _optional_mapping_text(value: dict[str, object], *keys: str) -> str | None:
    for key in keys:
        raw = value.get(key)
        if raw is None:
            continue
        normalized = str(raw).strip()
        if normalized:
            return normalized
    return None


def _reject_legacy_openapi_credential_fields(
    value: dict[str, object],
    *,
    provider_name: str,
    scheme_name: str,
) -> None:
    legacy_fields = (
        "source",
        "username_source",
        "password_source",
        "username",
        "password",
        "credential_binding",
        "credential_binding_ref",
        "binding_id",
        "username_binding",
        "password_binding",
    )
    for field_name in legacy_fields:
        if value.get(field_name) is not None:
            raise ValueError(
                f"OpenAPI provider '{provider_name}' credential binding "
                f"'{scheme_name}' must use Access credential binding ids; "
                f"field '{field_name}' is no longer accepted.",
            )
    for field_name in (
        "credential_binding_id",
        "username_binding_id",
        "password_binding_id",
    ):
        candidate = value.get(field_name)
        if candidate is None:
            continue
        _reject_direct_openapi_credential_source(
            str(candidate),
            provider_name=provider_name,
            scheme_name=scheme_name,
            field_name=field_name,
        )


def _reject_direct_openapi_credential_source(
    value: str,
    *,
    provider_name: str,
    scheme_name: str,
    field_name: str,
) -> None:
    normalized = value.strip()
    if normalized.startswith(("env:", "file:", "codex_auth_json", "codex-cli")):
        raise ValueError(
            f"OpenAPI provider '{provider_name}' credential binding '{scheme_name}' "
            f"field '{field_name}' must reference an Access credential binding id, "
            "not a direct credential source.",
        )
