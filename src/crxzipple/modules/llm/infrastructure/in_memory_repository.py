from __future__ import annotations

from crxzipple.modules.llm.domain.entities import LlmInvocation, LlmProfile
from crxzipple.modules.llm.domain import LlmResponseEvent, LlmResponseItem


class InMemoryLlmProfileRepository:
    def __init__(self) -> None:
        self._items: dict[str, LlmProfile] = {}

    def add(self, profile: LlmProfile) -> None:
        self._items[profile.id] = profile

    def delete(self, llm_id: str) -> None:
        self._items.pop(llm_id, None)

    def get(self, llm_id: str) -> LlmProfile | None:
        return self._items.get(llm_id)

    def list(self) -> list[LlmProfile]:
        return list(self._items.values())


class InMemoryLlmInvocationRepository:
    def __init__(self) -> None:
        self._items: dict[str, LlmInvocation] = {}
        self._response_events: dict[str, list[LlmResponseEvent]] = {}

    def add(self, invocation: LlmInvocation) -> None:
        self._items[invocation.id] = invocation

    def get(self, invocation_id: str) -> LlmInvocation | None:
        return self._items.get(invocation_id)

    def list(
        self,
        *,
        llm_id: str | None = None,
        run_id: str | None = None,
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
        if run_id is not None:
            items = [item for item in items if item.run_id == run_id]
        start = max(int(offset), 0)
        if limit is None:
            return items[start:]
        return items[start : start + max(int(limit), 0)]

    def add_response_event(self, event: LlmResponseEvent) -> None:
        events = self._response_events.setdefault(event.invocation_id, [])
        events = [item for item in events if item.id != event.id]
        events.append(event)
        events.sort(key=lambda item: (item.sequence_no, item.id))
        self._response_events[event.invocation_id] = events

    def list_response_events(
        self,
        invocation_id: str,
        *,
        limit: int | None = None,
        after_sequence: int | None = None,
    ) -> list[LlmResponseEvent]:
        events = list(self._response_events.get(invocation_id, ()))
        if after_sequence is not None:
            events = [event for event in events if event.sequence_no > int(after_sequence)]
        if limit is None:
            return events
        return events[: max(int(limit), 0)]

    def get_response_item(self, item_id: str) -> LlmResponseItem | None:
        for invocation in self._items.values():
            for item in invocation.response_items:
                if item.id == item_id:
                    return item
        return None
