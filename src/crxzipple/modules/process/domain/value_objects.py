from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ProcessStatus(str, Enum):
    RUNNING = "running"
    EXITED = "exited"
    FAILED = "failed"
    KILLED = "killed"


class ProcessStream(str, Enum):
    STDOUT = "stdout"
    STDERR = "stderr"


@dataclass(frozen=True, slots=True)
class ProcessOutputWindow:
    process_id: str
    status: ProcessStatus
    exit_code: int | None
    stdout: str
    stderr: str
    stdout_offset: int
    stderr_offset: int
    next_stdout_offset: int
    next_stderr_offset: int
    started_at: datetime
    ended_at: datetime | None


@dataclass(frozen=True, slots=True)
class ProcessCleanupResult:
    removed_process_ids: tuple[str, ...]
    reclaimed_bytes: int
    retained_running_process_ids: tuple[str, ...]

    @property
    def removed_count(self) -> int:
        return len(self.removed_process_ids)
