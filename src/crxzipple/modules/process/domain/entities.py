from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from crxzipple.modules.process.domain.exceptions import ProcessValidationError
from crxzipple.modules.process.domain.value_objects import ProcessStatus, ProcessStream
from crxzipple.shared.domain import AggregateRoot


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(kw_only=True)
class ProcessSession(AggregateRoot[str]):
    command: str
    shell: str
    working_directory: str
    session_key: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    pid: int | None = None
    status: ProcessStatus = ProcessStatus.RUNNING
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    created_at: datetime = field(default_factory=utcnow)
    started_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    ended_at: datetime | None = None
    termination_requested_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ProcessValidationError("Process session id cannot be empty.")
        if not self.command.strip():
            raise ProcessValidationError("Process session command cannot be empty.")
        if not self.shell.strip():
            raise ProcessValidationError("Process session shell cannot be empty.")
        if not self.working_directory.strip():
            raise ProcessValidationError(
                "Process session working_directory cannot be empty.",
            )
        self.command = self.command.strip()
        self.shell = self.shell.strip()
        self.working_directory = self.working_directory.strip()
        self.session_key = (
            self.session_key.strip() or None if self.session_key is not None else None
        )
        self.metadata = dict(self.metadata)

    def append_output(self, *, stream: ProcessStream, text: str) -> None:
        if not text:
            return
        if stream is ProcessStream.STDOUT:
            self.stdout += text
        else:
            self.stderr += text
        self.updated_at = utcnow()

    def mark_termination_requested(self) -> None:
        self.termination_requested_at = utcnow()
        self.updated_at = self.termination_requested_at

    def mark_exited(self, *, exit_code: int, ended_at: datetime | None = None) -> None:
        finished_at = ended_at or utcnow()
        self.exit_code = exit_code
        if self.termination_requested_at is not None:
            self.status = ProcessStatus.KILLED
        elif exit_code == 0:
            self.status = ProcessStatus.EXITED
        else:
            self.status = ProcessStatus.FAILED
        self.ended_at = finished_at
        self.updated_at = finished_at

    @property
    def is_running(self) -> bool:
        return self.status is ProcessStatus.RUNNING
