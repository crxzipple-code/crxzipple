from __future__ import annotations

from typing import Any


def session_to_payload(session: Any) -> dict[str, object]:
    return {
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
        "ended_at": session.ended_at.isoformat() if session.ended_at is not None else None,
        "termination_requested_at": (
            session.termination_requested_at.isoformat()
            if session.termination_requested_at is not None
            else None
        ),
    }


def output_to_payload(output: Any) -> dict[str, object]:
    return {
        "process_id": output.process_id,
        "status": output.status.value,
        "exit_code": output.exit_code,
        "stdout": output.stdout,
        "stderr": output.stderr,
        "stdout_offset": output.stdout_offset,
        "stderr_offset": output.stderr_offset,
        "next_stdout_offset": output.next_stdout_offset,
        "next_stderr_offset": output.next_stderr_offset,
        "started_at": output.started_at.isoformat(),
        "ended_at": output.ended_at.isoformat() if output.ended_at is not None else None,
    }


def cleanup_to_payload(result: Any) -> dict[str, object]:
    return {
        "removed": result.removed_count,
        "removed_process_ids": list(result.removed_process_ids),
        "reclaimed_bytes": result.reclaimed_bytes,
        "retained_running_process_ids": list(result.retained_running_process_ids),
    }


def matches_filters(
    session: Any,
    *,
    session_key: str | None,
    working_directory: str | None,
) -> bool:
    if session_key is not None and session.session_key != session_key:
        return False
    if working_directory is not None and session.working_directory != working_directory:
        return False
    return True
