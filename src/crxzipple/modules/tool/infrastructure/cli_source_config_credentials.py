from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.infrastructure.cli_source_config_values import (
    mapping_tuple,
    optional_text,
    required_text,
)
from crxzipple.shared.access import AccessCredentialKind

CLI_CREDENTIAL_INJECTION_KINDS = frozenset({"env", "file"})
FORBIDDEN_DIRECT_CREDENTIAL_SOURCE_PREFIXES = (
    "env:",
    "file:",
    "codex_auth_json",
    "codex-cli",
    "auth_ref",
)


@dataclass(frozen=True, slots=True)
class CliCredentialBindingConfig:
    binding_id: str
    injection: str = "env"
    env_name: str | None = None
    file_env_name: str | None = None
    file_name: str = "credential"
    expected_kind: AccessCredentialKind = AccessCredentialKind.API_KEY
    provider: str | None = None
    slot: str | None = None
    display_name: str | None = None


def credential_binding_configs(
    value: object,
    *,
    source_id: str,
) -> tuple[CliCredentialBindingConfig, ...]:
    configs: list[CliCredentialBindingConfig] = []
    for index, item in enumerate(
        mapping_tuple(value, field_name=f"{source_id}.provider.credential_bindings"),
    ):
        injection = optional_text(item.get("injection")) or "env"
        if injection not in CLI_CREDENTIAL_INJECTION_KINDS:
            allowed = ", ".join(sorted(CLI_CREDENTIAL_INJECTION_KINDS))
            raise ToolValidationError(
                f"CLI credential injection must be one of: {allowed}.",
            )
        binding_id = required_text(
            item.get("binding_id"),
            field_name=f"{source_id}.provider.credential_bindings[{index}].binding_id",
        )
        if item.get("credential_binding_id") is not None:
            raise ToolValidationError(
                f"{source_id}.provider.credential_bindings[{index}] must use binding_id; "
                "field 'credential_binding_id' is no longer accepted.",
            )
        _reject_direct_credential_binding_source(
            binding_id,
            source_id=source_id,
            index=index,
        )
        env_name = optional_text(item.get("env_name"))
        file_env_name = optional_text(item.get("file_env_name"))
        if injection == "env" and env_name is None:
            raise ToolValidationError(
                f"CLI credential binding '{binding_id}' requires env_name for env injection.",
            )
        if injection == "file" and file_env_name is None:
            raise ToolValidationError(
                f"CLI credential binding '{binding_id}' requires file_env_name for file injection.",
            )
        configs.append(
            CliCredentialBindingConfig(
                binding_id=binding_id,
                injection=injection,
                env_name=env_name,
                file_env_name=file_env_name,
                file_name=optional_text(item.get("file_name")) or "credential",
                expected_kind=_credential_kind(item.get("expected_kind")),
                provider=optional_text(item.get("provider")),
                slot=optional_text(item.get("slot")),
                display_name=optional_text(item.get("display_name")),
            ),
        )
    return tuple(configs)


def _reject_direct_credential_binding_source(
    binding_id: str,
    *,
    source_id: str,
    index: int,
) -> None:
    normalized = binding_id.strip()
    if normalized.startswith(FORBIDDEN_DIRECT_CREDENTIAL_SOURCE_PREFIXES):
        raise ToolValidationError(
            f"{source_id}.provider.credential_bindings[{index}].binding_id must "
            "reference an Access credential binding id, not a direct credential source.",
        )


def _credential_kind(value: object) -> AccessCredentialKind:
    raw = optional_text(value) or AccessCredentialKind.API_KEY.value
    try:
        return AccessCredentialKind(raw)
    except ValueError as exc:
        raise ToolValidationError(
            f"CLI credential expected_kind '{raw}' is not supported.",
        ) from exc
