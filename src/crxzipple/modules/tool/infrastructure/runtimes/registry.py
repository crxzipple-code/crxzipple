from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

AsyncToolHandler = Callable[..., Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class ToolRuntimeRegistration:
    runtime_key: str
    handler: AsyncToolHandler
    concurrency_key: str | None = None
    max_concurrency: int | None = None

    def __post_init__(self) -> None:
        normalized_concurrency_key = (
            self.concurrency_key.strip()
            if isinstance(self.concurrency_key, str)
            else None
        )
        if not normalized_concurrency_key:
            normalized_concurrency_key = None
        object.__setattr__(self, "concurrency_key", normalized_concurrency_key)

        if self.max_concurrency is not None and self.max_concurrency < 1:
            raise ValueError("Tool runtime max_concurrency must be positive.")

    def to_payload(self) -> dict[str, object]:
        return {
            "runtime_key": self.runtime_key,
            "concurrency_key": self.concurrency_key,
            "max_concurrency": self.max_concurrency,
        }


class ToolRuntimeRegistry:
    def __init__(self) -> None:
        self._registrations: dict[str, ToolRuntimeRegistration] = {}

    def register(
        self,
        runtime_key: str,
        handler: AsyncToolHandler,
        *,
        concurrency_key: str | None = None,
        max_concurrency: int | None = None,
    ) -> None:
        self._registrations[runtime_key] = ToolRuntimeRegistration(
            runtime_key=runtime_key,
            handler=handler,
            concurrency_key=concurrency_key,
            max_concurrency=max_concurrency,
        )

    def get_registration(self, runtime_key: str) -> ToolRuntimeRegistration | None:
        return self._registrations.get(runtime_key)

    def get_handler(self, runtime_key: str) -> AsyncToolHandler | None:
        registration = self.get_registration(runtime_key)
        if registration is None:
            return None
        return registration.handler

    def registrations(self) -> tuple[ToolRuntimeRegistration, ...]:
        return tuple(
            self._registrations[key]
            for key in sorted(self._registrations)
        )

    def snapshot(self) -> dict[str, object]:
        return {
            "registrations": [
                registration.to_payload()
                for registration in self.registrations()
            ],
        }

    def count(self) -> int:
        return len(self._registrations)
