from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import hashlib
import subprocess

from crxzipple.modules.process.domain import (
    ProcessCleanupResult,
    ProcessNotFoundError,
    ProcessSession,
    ProcessStatus,
)
from crxzipple.modules.process.infrastructure.repository_retention import (
    cleanup_terminal_sessions,
)


def derive_process_store_root(namespace: str) -> Path:
    digest = hashlib.sha1(namespace.encode("utf-8"), usedforsecurity=False).hexdigest()
    return Path(tempfile.gettempdir()) / "crxzipple-processes" / digest


class FilesystemProcessSessionRepository:
    def __init__(self, root_dir: str | Path) -> None:
        self._root_dir = Path(root_dir).expanduser().resolve()
        self._root_dir.mkdir(parents=True, exist_ok=True)

    @property
    def root_dir(self) -> Path:
        return self._root_dir

    def create_session_dir(self, process_id: str) -> Path:
        session_dir = self._session_dir(process_id)
        session_dir.mkdir(parents=True, exist_ok=False)
        return session_dir

    def save(self, session: ProcessSession) -> None:
        session_dir = self._session_dir(session.id)
        session_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "id": session.id,
            "command": session.command,
            "shell": session.shell,
            "working_directory": session.working_directory,
            "session_key": session.session_key,
            "metadata": dict(session.metadata),
            "pid": session.pid,
            "status": session.status.value,
            "exit_code": session.exit_code,
            "created_at": session.created_at.isoformat(),
            "started_at": session.started_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "ended_at": (
                session.ended_at.isoformat() if session.ended_at is not None else None
            ),
            "termination_requested_at": (
                session.termination_requested_at.isoformat()
                if session.termination_requested_at is not None
                else None
            ),
        }
        self._metadata_path(session.id).write_text(
            json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def get(self, process_id: str, *, include_output: bool = True) -> ProcessSession:
        payload = self._load_payload(process_id)
        return self._hydrate_session(payload, include_output=include_output)

    def list_all(self, *, include_output: bool = True) -> tuple[ProcessSession, ...]:
        sessions: list[ProcessSession] = []
        for metadata_path in sorted(self._root_dir.glob("*/session.json")):
            try:
                payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            try:
                sessions.append(self._hydrate_session(payload, include_output=include_output))
            except Exception:
                continue
        sessions.sort(key=lambda item: item.started_at, reverse=True)
        return tuple(sessions)

    def remove(self, process_id: str) -> None:
        session_dir = self._resolve_session_dir(process_id)
        if not session_dir.exists():
            raise ProcessNotFoundError(f"Process '{process_id}' was not found.")
        for child in sorted(session_dir.iterdir(), reverse=True):
            child.unlink(missing_ok=True)
        session_dir.rmdir()

    def cleanup_terminal_sessions(
        self,
        *,
        ended_before: datetime | None = None,
        max_terminal_sessions: int | None = None,
        max_terminal_bytes: int | None = None,
    ) -> ProcessCleanupResult:
        return cleanup_terminal_sessions(
            self,
            ended_before=ended_before,
            max_terminal_sessions=max_terminal_sessions,
            max_terminal_bytes=max_terminal_bytes,
        )

    def read_stdout(self, process_id: str) -> str:
        return self._read_text_file(self._stdout_path(process_id))

    def read_stderr(self, process_id: str) -> str:
        return self._read_text_file(self._stderr_path(process_id))

    def read_stdout_window(
        self,
        process_id: str,
        *,
        offset: int,
        limit: int,
    ) -> tuple[str, int]:
        return self._read_text_window(
            self._stdout_path(process_id),
            offset=offset,
            limit=limit,
        )

    def read_stderr_window(
        self,
        process_id: str,
        *,
        offset: int,
        limit: int,
    ) -> tuple[str, int]:
        return self._read_text_window(
            self._stderr_path(process_id),
            offset=offset,
            limit=limit,
        )

    def read_exit_code(self, process_id: str) -> int | None:
        path = self._exit_code_path(process_id)
        if not path.exists():
            return None
        try:
            return int(path.read_text(encoding="utf-8").strip())
        except Exception:
            return None

    def stdout_path(self, process_id: str) -> Path:
        return self._stdout_path(process_id)

    def stderr_path(self, process_id: str) -> Path:
        return self._stderr_path(process_id)

    def exit_code_path(self, process_id: str) -> Path:
        return self._exit_code_path(process_id)

    def refresh(self, session: ProcessSession, *, include_output: bool = True) -> ProcessSession:
        refreshed = replace(
            session,
            stdout=self.read_stdout(session.id) if include_output else "",
            stderr=self.read_stderr(session.id) if include_output else "",
        )
        exit_code = self.read_exit_code(session.id)
        if exit_code is not None:
            if refreshed.status is ProcessStatus.RUNNING:
                refreshed.mark_exited(exit_code=exit_code)
                self.save(refreshed)
            return refreshed
        if refreshed.pid is not None and _pid_is_running(refreshed.pid):
            return refreshed
        if refreshed.status is ProcessStatus.RUNNING:
            if refreshed.termination_requested_at is not None:
                refreshed.status = ProcessStatus.KILLED
            else:
                refreshed.status = ProcessStatus.FAILED
            refreshed.ended_at = refreshed.ended_at or _utcnow()
            refreshed.updated_at = _utcnow()
            self.save(refreshed)
        return refreshed

    def _session_dir(self, process_id: str) -> Path:
        _require_safe_process_id(process_id)
        return self._root_dir / process_id

    def _resolve_session_dir(self, process_id: str) -> Path:
        _require_safe_process_id(process_id)
        local_dir = self._session_dir(process_id)
        if (local_dir / "session.json").exists():
            return local_dir
        try:
            namespace_dirs = sorted(self._root_dir.parent.iterdir())
        except OSError:
            return local_dir
        for namespace_dir in namespace_dirs:
            if namespace_dir == self._root_dir or not namespace_dir.is_dir():
                continue
            candidate_dir = namespace_dir / process_id
            if (candidate_dir / "session.json").exists():
                return candidate_dir
        return local_dir

    def _metadata_path(self, process_id: str) -> Path:
        return self._resolve_session_dir(process_id) / "session.json"

    def _stdout_path(self, process_id: str) -> Path:
        return self._resolve_session_dir(process_id) / "stdout.log"

    def _stderr_path(self, process_id: str) -> Path:
        return self._resolve_session_dir(process_id) / "stderr.log"

    def _exit_code_path(self, process_id: str) -> Path:
        return self._resolve_session_dir(process_id) / "exit_code"

    def _load_payload(self, process_id: str) -> dict[str, object]:
        path = self._metadata_path(process_id)
        if not path.exists():
            raise ProcessNotFoundError(f"Process '{process_id}' was not found.")
        return json.loads(path.read_text(encoding="utf-8"))

    def _hydrate_session(
        self,
        payload: dict[str, object],
        *,
        include_output: bool = True,
    ) -> ProcessSession:
        process_id = str(payload["id"])
        session = ProcessSession(
            id=process_id,
            command=str(payload["command"]),
            shell=str(payload["shell"]),
            working_directory=str(payload["working_directory"]),
            session_key=(
                str(payload["session_key"]) if payload.get("session_key") is not None else None
            ),
            metadata=dict(payload.get("metadata", {})),
            pid=int(payload["pid"]) if payload.get("pid") is not None else None,
            status=ProcessStatus(str(payload.get("status", ProcessStatus.RUNNING.value))),
            exit_code=(
                int(payload["exit_code"]) if payload.get("exit_code") is not None else None
            ),
            created_at=_parse_datetime(payload.get("created_at")),
            started_at=_parse_datetime(payload.get("started_at")),
            updated_at=_parse_datetime(payload.get("updated_at")),
            ended_at=_parse_datetime(payload.get("ended_at")),
            termination_requested_at=_parse_datetime(payload.get("termination_requested_at")),
        )
        if not include_output:
            return session
        return replace(
            session,
            stdout=self.read_stdout(process_id),
            stderr=self.read_stderr(process_id),
        )

    @staticmethod
    def _read_text_file(path: Path) -> str:
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8", errors="replace")

    @staticmethod
    def _read_text_window(path: Path, *, offset: int, limit: int) -> tuple[str, int]:
        if not path.exists():
            return "", max(int(offset), 0)
        normalized_offset = max(int(offset), 0)
        normalized_limit = max(int(limit), 1)
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(normalized_offset)
            text = handle.read(normalized_limit)
            next_offset = handle.tell()
        return text, next_offset


def _require_safe_process_id(process_id: str) -> None:
    normalized = process_id.strip()
    if (
        not normalized
        or normalized != process_id
        or normalized in {".", ".."}
        or Path(normalized).name != normalized
        or "\\" in normalized
    ):
        raise ProcessNotFoundError(f"Process '{process_id}' was not found.")


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return datetime.fromisoformat(value)


def _pid_is_running(pid: int) -> bool:
    try:
        result = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(pid)],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        result = None
    if result is not None:
        if result.returncode != 0:
            return False
        status = result.stdout.strip().upper()
        if not status:
            return False
        if "Z" in status:
            return False
        return True
    try:
        import os

        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
