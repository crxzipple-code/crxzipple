from __future__ import annotations

from collections.abc import Mapping

from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmProviderKind,
)


def credential_expectation_for(
    provider: LlmProviderKind,
    api_family: LlmApiFamily,
) -> dict[str, object]:
    if (
        provider is LlmProviderKind.OPENAI_CODEX
        or api_family is LlmApiFamily.OPENAI_CODEX_RESPONSES
    ):
        return {"kind": "oauth2_account", "label": "OAuth account", "required": True}
    if (
        provider in {
            LlmProviderKind.OPENAI,
            LlmProviderKind.ANTHROPIC,
            LlmProviderKind.GOOGLE,
        }
        or api_family
        in {
            LlmApiFamily.OPENAI_RESPONSES,
            LlmApiFamily.ANTHROPIC_MESSAGES,
            LlmApiFamily.GEMINI_GENERATE_CONTENT,
        }
    ):
        return {"kind": "api_key", "label": "API key", "required": True}
    if (
        provider is LlmProviderKind.OPENAI_COMPATIBLE
        or api_family is LlmApiFamily.OPENAI_CHAT_COMPATIBLE
    ):
        return {"kind": "optional_api_key", "label": "API key or none", "required": False}
    if provider is LlmProviderKind.OLLAMA or api_family is LlmApiFamily.OLLAMA_NATIVE:
        return {"kind": "none", "label": "no credential", "required": False}
    return {"kind": "any", "label": "Access credential", "required": False}


def credential_binding_matches_expectation(
    metadata: Mapping[str, object],
    expectation_kind: object,
) -> bool:
    if expectation_kind == "any":
        return True
    if expectation_kind == "none":
        return False
    if expectation_kind == "oauth2_account":
        return is_oauth_account_binding(metadata)
    if expectation_kind in {"api_key", "optional_api_key"}:
        return is_api_key_binding(metadata)
    return True


def credential_binding_type_label(metadata: Mapping[str, object]) -> str:
    if is_oauth_account_binding(metadata):
        return "OAuth account"
    if is_api_key_binding(metadata):
        return "API key"
    return (
        metadata_text(metadata, "binding_kind")
        or metadata_text(metadata, "source_kind")
        or "credential"
    )


def is_api_key_binding(metadata: Mapping[str, object]) -> bool:
    if is_oauth_account_binding(metadata):
        return False
    kind = metadata_text(metadata, "binding_kind")
    return kind == "api_key"


def is_oauth_account_binding(metadata: Mapping[str, object]) -> bool:
    return (
        metadata_text(metadata, "source_kind") == "oauth_account"
        or metadata_text(metadata, "binding_kind") == "oauth2_account"
        or metadata_text(metadata, "binding_kind") == "openid_connect"
    )


def metadata_text(metadata: Mapping[str, object], key: str) -> str:
    value = metadata.get(key)
    return str(value).strip().lower() if value is not None else ""


def optional_string_config_value(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
