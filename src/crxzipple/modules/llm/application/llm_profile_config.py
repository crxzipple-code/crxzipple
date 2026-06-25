from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from crxzipple.modules.llm.application.llm_profile_service import (
    llm_profile_from_register_input,
)
from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmCapability,
    LlmDefaults,
    LlmModelFamily,
    LlmProviderKind,
    LlmSourceKind,
)

_forbidden_credential_binding_prefixes = ("env:", "file:")
_forbidden_credential_binding_ids = {"codex_auth_json", "codex-cli", "auth_ref"}
_forbidden_credential_binding_id_prefixes = ("codex_auth_json:", "auth_ref:")


class LlmProfileImportLike(Protocol):
    profile_id: str
    provider: str | LlmProviderKind
    api_family: str | LlmApiFamily
    model_name: str


@dataclass(frozen=True, slots=True)
class RegisterLlmProfileInput:
    id: str
    provider: LlmProviderKind
    api_family: LlmApiFamily
    model_name: str
    context_window_tokens: int | None = None
    model_family: LlmModelFamily = LlmModelFamily.GENERAL
    capabilities: tuple[LlmCapability, ...] = field(default_factory=tuple)
    default_params: LlmDefaults = field(default_factory=LlmDefaults)
    base_url: str | None = None
    credential_binding_id: str | None = None
    timeout_seconds: int = 60
    max_concurrency: int | None = None
    concurrency_key: str | None = None
    source_kind: LlmSourceKind = LlmSourceKind.MANUAL
    enabled: bool = True

    @classmethod
    def from_config(
        cls,
        config: LlmProfileImportLike | Mapping[str, Any],
    ) -> "RegisterLlmProfileInput":
        return register_llm_profile_input_from_config(config)


def register_llm_profile_input_from_config(
    config: LlmProfileImportLike | Mapping[str, Any],
) -> RegisterLlmProfileInput:
    """Convert an import payload into LLM owner-module input."""

    if any(
        _config_has(config, key)
        for key in ("credential_binding", "credential_binding_ref", "auth_ref")
    ):
        raise ValueError(
            "LLM profile config must use credential_binding_id, not credential_binding.",
        )

    return RegisterLlmProfileInput(
        id=str(_config_value(config, "id", _config_value(config, "profile_id"))),
        provider=_coerce_provider_kind(_config_value(config, "provider")),
        api_family=_coerce_api_family(_config_value(config, "api_family")),
        model_name=str(_config_value(config, "model_name")),
        context_window_tokens=_optional_int_config_value(
            _config_value(config, "context_window_tokens", None),
        ),
        model_family=_coerce_model_family(
            _config_value(config, "model_family", LlmModelFamily.GENERAL),
        ),
        capabilities=_capabilities_for_profile_config(config),
        default_params=_defaults_from_config_value(
            _config_value(config, "default_params", None),
        ),
        base_url=_optional_string_config_value(_config_value(config, "base_url", None)),
        credential_binding_id=_credential_binding_id_from_config_value(
            _config_value(config, "credential_binding_id", None),
        ),
        timeout_seconds=_int_config_value(
            _config_value(config, "timeout_seconds", 60),
            default=60,
        ),
        max_concurrency=_optional_int_config_value(
            _config_value(config, "max_concurrency", None),
        ),
        concurrency_key=_optional_string_config_value(
            _config_value(config, "concurrency_key", None),
        ),
        source_kind=_coerce_source_kind(
            _config_value(config, "source_kind", LlmSourceKind.IMPORTED),
        ),
        enabled=_bool_config_value(_config_value(config, "enabled", True)),
    )


def llm_profile_from_config(
    config: LlmProfileImportLike | Mapping[str, Any],
) -> LlmProfile:
    return llm_profile_from_register_input(
        register_llm_profile_input_from_config(config),
    )


def _config_value(config: object, key: str, default: object = None) -> object:
    if isinstance(config, Mapping):
        return config.get(key, default)
    return getattr(config, key, default)


def _config_has(config: object, key: str) -> bool:
    if isinstance(config, Mapping):
        return key in config
    return hasattr(config, key)


def _coerce_provider_kind(value: object) -> LlmProviderKind:
    return value if isinstance(value, LlmProviderKind) else LlmProviderKind(str(value))


def _coerce_api_family(value: object) -> LlmApiFamily:
    return value if isinstance(value, LlmApiFamily) else LlmApiFamily(str(value))


def _coerce_model_family(value: object) -> LlmModelFamily:
    if value is None or (isinstance(value, str) and not value.strip()):
        return LlmModelFamily.GENERAL
    return value if isinstance(value, LlmModelFamily) else LlmModelFamily(str(value))


def _coerce_source_kind(value: object) -> LlmSourceKind:
    if value is None or (isinstance(value, str) and not value.strip()):
        return LlmSourceKind.IMPORTED
    return value if isinstance(value, LlmSourceKind) else LlmSourceKind(str(value))


def _capabilities_from_config_value(value: object) -> tuple[LlmCapability, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, LlmCapability)):
        value = (value,)
    return tuple(
        item if isinstance(item, LlmCapability) else LlmCapability(str(item))
        for item in value
    )


def _capabilities_for_profile_config(
    config: LlmProfileImportLike | Mapping[str, Any],
) -> tuple[LlmCapability, ...]:
    capabilities = list(
        _capabilities_from_config_value(_config_value(config, "capabilities", ())),
    )
    api_family = _coerce_api_family(_config_value(config, "api_family"))
    if (
        api_family is LlmApiFamily.OPENAI_RESPONSES
        and LlmCapability.PROVIDER_NATIVE_CONTINUATION not in capabilities
    ):
        capabilities.append(LlmCapability.PROVIDER_NATIVE_CONTINUATION)
    if (
        api_family is LlmApiFamily.OPENAI_CODEX_RESPONSES
        and LlmCapability.PROVIDER_WEBSOCKET_TRANSPORT in capabilities
        and LlmCapability.PROVIDER_INCREMENTAL_INPUT in capabilities
        and LlmCapability.PROVIDER_NATIVE_CONTINUATION not in capabilities
    ):
        capabilities.append(LlmCapability.PROVIDER_NATIVE_CONTINUATION)
    return tuple(dict.fromkeys(capabilities))


def _defaults_from_config_value(value: object) -> LlmDefaults:
    if value is None:
        return LlmDefaults()
    if isinstance(value, LlmDefaults):
        return value
    if isinstance(value, Mapping):
        return LlmDefaults.from_payload(dict(value))
    to_payload = getattr(value, "to_payload", None)
    if callable(to_payload):
        payload = to_payload()
        if isinstance(payload, Mapping):
            return LlmDefaults.from_payload(dict(payload))

    payload: dict[str, Any] = {}
    for field_name in (
        "temperature",
        "top_p",
        "max_output_tokens",
        "reasoning_effort",
    ):
        field_value = getattr(value, field_name, None)
        if field_value is not None:
            payload[field_name] = field_value
    extra_body = getattr(value, "extra_body", None)
    if isinstance(extra_body, Mapping):
        payload["extra_body"] = dict(extra_body)
    return LlmDefaults.from_payload(payload)


def _credential_binding_id_from_config_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        binding_id = _optional_string_config_value(value)
        if binding_id is not None and _is_forbidden_credential_binding_id(binding_id):
            raise ValueError(
                "LLM credential_binding_id must reference an Access credential binding id.",
            )
        return binding_id
    raise TypeError("LLM credential_binding_id must be an Access credential binding id string.")


def _is_forbidden_credential_binding_id(value: str) -> bool:
    normalized = value.strip()
    return (
        normalized.startswith(_forbidden_credential_binding_prefixes)
        or normalized in _forbidden_credential_binding_ids
        or normalized.startswith(_forbidden_credential_binding_id_prefixes)
    )


def _optional_string_config_value(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _int_config_value(value: object, *, default: int) -> int:
    if value is None:
        return default
    return int(value)


def _optional_int_config_value(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return int(value)


def _bool_config_value(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
