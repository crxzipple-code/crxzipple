from __future__ import annotations

from typing import Protocol

from crxzipple.modules.llm.domain.entities import LlmInvocation, LlmProfile
from crxzipple.modules.llm.domain.value_objects import LlmResponseEvent, LlmResponseItem


class LlmProfileRepository(Protocol):
    def add(self, profile: LlmProfile) -> None:
        ...

    def delete(self, llm_id: str) -> None:
        ...

    def get(self, llm_id: str) -> LlmProfile | None:
        ...

    def list(self) -> list[LlmProfile]:
        ...


class LlmInvocationRepository(Protocol):
    def add(self, invocation: LlmInvocation) -> None:
        ...

    def get(self, invocation_id: str) -> LlmInvocation | None:
        ...

    def list(
        self,
        *,
        llm_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[LlmInvocation]:
        ...

    def add_response_event(self, event: LlmResponseEvent) -> None:
        ...

    def list_response_events(
        self,
        invocation_id: str,
        *,
        limit: int | None = None,
        after_sequence: int | None = None,
    ) -> list[LlmResponseEvent]:
        ...

    def get_response_item(self, item_id: str) -> LlmResponseItem | None:
        ...
