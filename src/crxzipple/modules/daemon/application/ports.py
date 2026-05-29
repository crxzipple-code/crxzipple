from __future__ import annotations

from typing import Protocol

from crxzipple.modules.process.domain import ProcessSession


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


class DaemonProcessControlPort(Protocol):
    def start_command(
        self,
        *,
        command: str,
        shell: str,
        working_directory: str,
        session_key: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ProcessSession:
        ...

    def list_sessions(self) -> tuple[ProcessSession, ...]:
        ...

    def list_sessions_metadata(self) -> tuple[ProcessSession, ...]:
        ...

    def get_session(self, *, process_id: str) -> ProcessSession:
        ...

    def terminate_session(self, *, process_id: str) -> ProcessSession:
        ...
