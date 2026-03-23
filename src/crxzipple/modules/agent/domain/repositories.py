from __future__ import annotations

from typing import Protocol

from crxzipple.modules.agent.domain.entities import AgentProfile


class AgentProfileRepository(Protocol):
    def add(self, profile: AgentProfile) -> None:
        ...

    def get(self, profile_id: str) -> AgentProfile | None:
        ...

    def list(self) -> list[AgentProfile]:
        ...
