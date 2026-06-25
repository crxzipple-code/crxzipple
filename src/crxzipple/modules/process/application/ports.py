from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from crxzipple.modules.process.domain import ProcessSession


class ProcessSessionRepositoryPort(Protocol):
    @property
    def root_dir(self) -> Path:
        ...

    def create_session_dir(self, process_id: str) -> Path:
        ...

    def save(self, session: ProcessSession) -> None:
        ...

    def get(self, process_id: str, *, include_output: bool = True) -> ProcessSession:
        ...

    def list_all(self, *, include_output: bool = True) -> tuple[ProcessSession, ...]:
        ...

    def remove(self, process_id: str) -> None:
        ...

    def read_stdout(self, process_id: str) -> str:
        ...

    def read_stderr(self, process_id: str) -> str:
        ...

    def read_stdout_window(
        self,
        process_id: str,
        *,
        offset: int,
        limit: int,
    ) -> tuple[str, int]:
        ...

    def read_stderr_window(
        self,
        process_id: str,
        *,
        offset: int,
        limit: int,
    ) -> tuple[str, int]:
        ...

    def stdout_path(self, process_id: str) -> Path:
        ...

    def stderr_path(self, process_id: str) -> Path:
        ...

    def exit_code_path(self, process_id: str) -> Path:
        ...

    def refresh(
        self,
        session: ProcessSession,
        *,
        include_output: bool = True,
    ) -> ProcessSession:
        ...


class ProcessSupervisorPort(Protocol):
    def start(
        self,
        *,
        command: str,
        shell: str,
        working_directory: str,
        session_key: str | None = None,
        metadata: dict[str, object] | None = None,
        env: Mapping[str, str] | None = None,
    ) -> ProcessSession:
        ...

    def terminate(self, process_id: str) -> ProcessSession:
        ...

    def close(self) -> None:
        ...
