from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EventOutboxPublishResult:
    published: int = 0
    failed: int = 0

    @property
    def processed(self) -> int:
        return self.published + self.failed
