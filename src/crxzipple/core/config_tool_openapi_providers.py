from __future__ import annotations

import json
import os
from pathlib import Path

from crxzipple.core.config_env import load_structured_config, optional_positive_int
from crxzipple.core.config_tool_openapi_credentials import (
    load_openapi_credential_bindings,
)
from crxzipple.core.config_tool_provider_models import OpenApiProviderSettings


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OPENAPI_PROVIDER_DIR = PROJECT_ROOT / "config" / "tool_providers"


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
        credential_bindings=load_openapi_credential_bindings(
            raw.get("credentials", {}),
            provider_name=name,
        ),
        default_effect_ids=_string_tuple(raw.get("default_effect_ids", []) or []),
        runtime_requirements=_string_tuple(raw.get("runtime_requirements", []) or []),
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


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())
