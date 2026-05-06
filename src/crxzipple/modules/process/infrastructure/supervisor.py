from __future__ import annotations

import os
import shlex
import signal
import subprocess
import time
from uuid import uuid4

from crxzipple.modules.process.domain import (
    ProcessSession,
    ProcessStatus,
    ProcessValidationError,
)
from crxzipple.modules.process.application.ports import (
    ProcessSessionRepositoryPort,
)


class ProcessSupervisor:
    def __init__(self, repository: ProcessSessionRepositoryPort) -> None:
        self._repository = repository

    def start(
        self,
        *,
        command: str,
        shell: str,
        working_directory: str,
        session_key: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ProcessSession:
        process_id = str(uuid4())
        session_dir = self._repository.create_session_dir(process_id)
        stdout_path = self._repository.stdout_path(process_id)
        stderr_path = self._repository.stderr_path(process_id)
        exit_code_path = self._repository.exit_code_path(process_id)
        shell_command = (
            f"{command}; "
            f"code=$?; "
            f"printf '%s' \"$code\" > {shlex.quote(str(exit_code_path))}; "
            "exit \"$code\""
        )
        try:
            with stdout_path.open("ab") as stdout_file, stderr_path.open("ab") as stderr_file:
                process = subprocess.Popen(
                    [shell, "-lc", shell_command],
                    cwd=working_directory,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    start_new_session=True,
                )
        except OSError as exc:
            try:
                for child in session_dir.iterdir():
                    child.unlink(missing_ok=True)
                session_dir.rmdir()
            except Exception:
                pass
            raise ProcessValidationError(
                "Background command could not be started.",
            ) from exc

        merged_metadata = {
            **(metadata or {}),
            "process_store_root": str(self._repository.root_dir),
            "session_dir": str(session_dir),
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "exit_code_path": str(exit_code_path),
        }
        session = ProcessSession(
            id=process_id,
            session_key=session_key,
            command=command,
            shell=shell,
            working_directory=working_directory,
            metadata=merged_metadata,
            pid=process.pid,
            status=ProcessStatus.RUNNING,
        )
        self._repository.save(session)
        return self._repository.refresh(session)

    def terminate(self, process_id: str) -> ProcessSession:
        session = self._repository.refresh(self._repository.get(process_id))
        if not session.is_running or session.pid is None:
            return session
        session.mark_termination_requested()
        self._repository.save(session)
        _signal_process(session.pid, signal.SIGTERM)
        deadline = time.time() + 2
        while time.time() < deadline:
            refreshed = self._repository.refresh(self._repository.get(process_id))
            if not refreshed.is_running:
                return refreshed
            time.sleep(0.1)
        _signal_process(session.pid, signal.SIGKILL)
        deadline = time.time() + 2
        while time.time() < deadline:
            refreshed = self._repository.refresh(self._repository.get(process_id))
            if not refreshed.is_running:
                return refreshed
            time.sleep(0.1)
        return self._repository.refresh(self._repository.get(process_id))

    def close(self) -> None:
        return None


def _signal_process(pid: int, sig: signal.Signals) -> None:
    try:
        pgid = os.getpgid(pid)
    except (ProcessLookupError, PermissionError):
        pgid = None
    if pgid is not None:
        try:
            os.killpg(pgid, sig)
            return
        except ProcessLookupError:
            return
        except PermissionError:
            pass
    try:
        os.kill(pid, sig)
    except (ProcessLookupError, PermissionError):
        return
