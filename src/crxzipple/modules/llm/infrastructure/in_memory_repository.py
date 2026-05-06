from __future__ import annotations

from crxzipple.modules.llm.domain.entities import LlmInvocation, LlmProfile


class InMemoryLlmProfileRepository:
    def __init__(self) -> None:
        self._items: dict[str, LlmProfile] = {}

    def add(self, profile: LlmProfile) -> None:
        self._items[profile.id] = profile

    def get(self, llm_id: str) -> LlmProfile | None:
        return self._items.get(llm_id)

    def list(self) -> list[LlmProfile]:
        return list(self._items.values())


class InMemoryLlmInvocationRepository:
    def __init__(self) -> None:
        self._items: dict[str, LlmInvocation] = {}

    def add(self, invocation: LlmInvocation) -> None:
        self._items[invocation.id] = invocation

    def get(self, invocation_id: str) -> LlmInvocation | None:
        return self._items.get(invocation_id)

    def list(
        self,
        *,
        llm_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[LlmInvocation]:
        items = sorted(
            self._items.values(),
            key=lambda invocation: invocation.created_at,
            reverse=True,
        )
        if llm_id is not None:
            items = [item for item in items if item.llm_id == llm_id]
        start = max(int(offset), 0)
        if limit is None:
            return items[start:]
        return items[start : start + max(int(limit), 0)]
