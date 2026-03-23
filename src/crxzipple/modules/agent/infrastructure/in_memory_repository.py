from __future__ import annotations

from crxzipple.modules.agent.domain.entities import AgentProfile


class InMemoryAgentProfileRepository:
    def __init__(self) -> None:
        self._items: dict[str, AgentProfile] = {}

    def add(self, profile: AgentProfile) -> None:
        self._items[profile.id] = profile

    def get(self, profile_id: str) -> AgentProfile | None:
        return self._items.get(profile_id)

    def list(self) -> list[AgentProfile]:
        return sorted(self._items.values(), key=lambda item: item.id)
