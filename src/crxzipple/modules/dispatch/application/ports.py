from __future__ import annotations

from typing import Protocol

from crxzipple.shared.domain.events import Event


class DispatchEventPublishPort(Protocol):
    def publish(self, event: Event) -> None:
        ...
