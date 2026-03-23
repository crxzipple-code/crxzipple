from __future__ import annotations

from crxzipple.modules.llm.application.adapters import LlmAdapter
from crxzipple.modules.llm.domain.value_objects import LlmApiFamily


class LlmAdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[LlmApiFamily, LlmAdapter] = {}

    def register(self, api_family: LlmApiFamily, adapter: LlmAdapter) -> None:
        self._adapters[api_family] = adapter

    def get(self, api_family: LlmApiFamily) -> LlmAdapter | None:
        return self._adapters.get(api_family)
