from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProviderOptionFilterResult:
    provider_options: dict[str, object]
    removed_options: tuple[str, ...] = ()


_RESPONSES_API_FAMILIES = frozenset(
    {
        "openai_responses",
        "openai_codex_responses",
    },
)

_RESPONSES_ONLY_PROVIDER_OPTIONS = frozenset(
    {
        "include",
        "parallel_tool_calls",
        "prompt_cache_enabled",
        "prompt_cache_key",
        "text",
    },
)


def filter_provider_options_for_api_family(
    provider_options: Mapping[str, object],
    *,
    llm_api_family: str | None,
) -> ProviderOptionFilterResult:
    api_family = _optional_text(llm_api_family)
    filtered = dict(provider_options)
    if api_family is None or api_family in _RESPONSES_API_FAMILIES:
        return ProviderOptionFilterResult(provider_options=filtered)
    removed: list[str] = []
    for key in tuple(filtered):
        if key not in _RESPONSES_ONLY_PROVIDER_OPTIONS:
            continue
        filtered.pop(key, None)
        removed.append(key)
    return ProviderOptionFilterResult(
        provider_options=filtered,
        removed_options=tuple(removed),
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
