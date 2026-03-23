from __future__ import annotations

from typing import Protocol

from crxzipple.modules.llm.domain.entities import LlmInvocation, LlmProfile


class LlmProfileRepository(Protocol):
    def add(self, profile: LlmProfile) -> None:
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

    def list(self, *, llm_id: str | None = None) -> list[LlmInvocation]:
        ...
