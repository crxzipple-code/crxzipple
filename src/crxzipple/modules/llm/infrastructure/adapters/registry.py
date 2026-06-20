from __future__ import annotations

from collections.abc import Callable

from crxzipple.modules.llm.application.adapters import LlmAdapter
from crxzipple.modules.llm.domain.value_objects import LlmApiFamily


class LlmAdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[LlmApiFamily, LlmAdapter] = {}
        self._factories: dict[LlmApiFamily, Callable[[], LlmAdapter]] = {}

    def register(self, api_family: LlmApiFamily, adapter: LlmAdapter) -> None:
        self._adapters[api_family] = adapter

    def register_factory(
        self,
        api_family: LlmApiFamily,
        factory: Callable[[], LlmAdapter],
    ) -> None:
        self._factories[api_family] = factory

    def get(self, api_family: LlmApiFamily) -> LlmAdapter | None:
        adapter = self._adapters.get(api_family)
        if adapter is not None:
            return adapter
        factory = self._factories.get(api_family)
        if factory is None:
            return None
        adapter = factory()
        self._adapters[api_family] = adapter
        return adapter
