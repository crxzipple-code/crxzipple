from __future__ import annotations

from pathlib import Path
from typing import Any

from crxzipple.core.config import OpenApiProviderSettings
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.infrastructure.tool_package_manifest_parsers import (
    parse_string_list,
    required_string,
)
from crxzipple.modules.tool.infrastructure.tool_package_openapi_credentials import (
    parse_openapi_credential_bindings,
)


def load_openapi_provider_from_manifest(
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
        name=required_string(payload, "namespace", manifest_path),
        spec_location=str(spec_path),
        base_url=(
            str(payload["base_url"]).strip()
            if payload.get("base_url") is not None
            else None
        ),
        description=str(payload.get("description", "")).strip(),
        timeout_seconds=max(int(payload.get("timeout_seconds", 30)), 1),
        max_concurrency=_parse_optional_positive_int(
            payload.get("max_concurrency"),
            field_name="max_concurrency",
            manifest_path=manifest_path,
        ),
        credential_bindings=parse_openapi_credential_bindings(
            payload.get("credentials", {}),
            manifest_path,
        ),
        default_effect_ids=parse_string_list(
            payload.get("default_effect_ids", []),
            "default_effect_ids",
            manifest_path,
        ),
        runtime_requirements=tuple(
            parse_string_list(
                payload.get("runtime_requirements", []),
                "runtime_requirements",
                manifest_path,
            ),
        ),
    )


def _parse_optional_positive_int(
    raw_value: object,
    *,
    field_name: str,
    manifest_path: Path,
) -> int | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, str) and not raw_value.strip():
        return None
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field '{field_name}' must be a positive integer.",
        ) from exc
    if parsed < 1:
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field '{field_name}' must be a positive integer.",
        )
    return parsed


__all__ = ["load_openapi_provider_from_manifest"]
