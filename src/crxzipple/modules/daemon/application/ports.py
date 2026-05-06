from __future__ import annotations

from typing import Protocol


class ShellResolver(Protocol):
    def __call__(self) -> str:
        ...


class EndpointProbe(Protocol):
    def __call__(
        self,
        *,
        endpoint: str,
        healthcheck_policy: str,
        timeout_seconds: float,
    ) -> None:
        ...
