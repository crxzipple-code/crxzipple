from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Protocol

from crxzipple.modules.process.domain import ProcessCleanupResult, ProcessSession


class ProcessRetentionRepository(Protocol):
    @property
    def root_dir(self) -> Path:
        ...

    def list_all(self, *, include_output: bool = True) -> tuple[ProcessSession, ...]:
        ...

    def refresh(
        self,
        session: ProcessSession,
        *,
        include_output: bool = True,
    ) -> ProcessSession:
        ...

    def remove(self, process_id: str) -> None:
        ...


def cleanup_terminal_sessions(
    repository: ProcessRetentionRepository,
    *,
    ended_before: datetime | None = None,
    max_terminal_sessions: int | None = None,
    max_terminal_bytes: int | None = None,
) -> ProcessCleanupResult:
    max_sessions = _normalize_optional_non_negative(max_terminal_sessions)
    max_bytes = _normalize_optional_non_negative(max_terminal_bytes)
    sessions = tuple(
        repository.refresh(session, include_output=False)
        for session in repository.list_all(include_output=False)
    )
    running_ids = tuple(session.id for session in sessions if session.is_running)
    terminal_sessions = [session for session in sessions if not session.is_running]
    terminal_sessions.sort(key=_session_reference_time, reverse=True)

    remove_ids: set[str] = set()
    if ended_before is not None:
        remove_ids.update(
            session.id
            for session in terminal_sessions
            if _session_reference_time(session) < ended_before
        )
    if max_sessions is not None:
        remove_ids.update(session.id for session in terminal_sessions[max_sessions:])
    if max_bytes is not None:
        _apply_terminal_byte_budget(
            root_dir=repository.root_dir,
            terminal_sessions=terminal_sessions,
            remove_ids=remove_ids,
            max_bytes=max_bytes,
        )

    removed_ids: list[str] = []
    reclaimed_bytes = 0
    for process_id in sorted(remove_ids):
        reclaimed_bytes += _session_dir_size(repository.root_dir, process_id)
        repository.remove(process_id)
        removed_ids.append(process_id)
    return ProcessCleanupResult(
        removed_process_ids=tuple(removed_ids),
        reclaimed_bytes=reclaimed_bytes,
        retained_running_process_ids=running_ids,
    )


def _apply_terminal_byte_budget(
    *,
    root_dir: Path,
    terminal_sessions: list[ProcessSession],
    remove_ids: set[str],
    max_bytes: int,
) -> None:
    kept_sessions = [session for session in terminal_sessions if session.id not in remove_ids]
    total_bytes = sum(_session_dir_size(root_dir, session.id) for session in kept_sessions)
    for session in reversed(kept_sessions):
        if total_bytes <= max_bytes:
            break
        total_bytes -= _session_dir_size(root_dir, session.id)
        remove_ids.add(session.id)


def _session_dir_size(root_dir: Path, process_id: str) -> int:
    session_dir = root_dir / process_id
    if not session_dir.exists() or not session_dir.is_dir():
        return 0
    total = 0
    for path in session_dir.iterdir():
        if not path.is_file():
            continue
        try:
            total += path.stat().st_size
        except OSError:
            continue
    return total


def _session_reference_time(session: ProcessSession) -> datetime:
    return session.ended_at or session.updated_at or session.started_at


def _normalize_optional_non_negative(value: int | None) -> int | None:
    if value is None:
        return None
    return max(int(value), 0)
