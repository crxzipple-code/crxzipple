from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from crxzipple.modules.process.domain import (
    ProcessOutputWindow,
    ProcessSession,
    ProcessValidationError,
)
from crxzipple.modules.process.application.ports import (
    ProcessSessionRepositoryPort,
    ProcessSupervisorPort,
)


@dataclass(slots=True)
class ProcessApplicationService:
    repository: ProcessSessionRepositoryPort
    supervisor: ProcessSupervisorPort

    def start_command(
        self,
        *,
        command: str,
        shell: str,
        working_directory: str,
        session_key: str | None = None,
        metadata: dict[str, object] | None = None,
        env: Mapping[str, str] | None = None,
    ) -> ProcessSession:
        return self.supervisor.start(
            session_key=session_key,
            command=command,
            shell=shell,
            working_directory=working_directory,
            metadata=metadata,
            env=env,
        )

    def list_sessions(self) -> tuple[ProcessSession, ...]:
        return tuple(self.repository.refresh(session) for session in self.repository.list_all())

    def list_sessions_metadata(self) -> tuple[ProcessSession, ...]:
        return tuple(
            self.repository.refresh(session, include_output=False)
            for session in self.repository.list_all(include_output=False)
        )

    def get_session(self, *, process_id: str) -> ProcessSession:
        return self.repository.refresh(self.repository.get(process_id))

    def read_output(
        self,
        *,
        process_id: str,
        stdout_offset: int = 0,
        stderr_offset: int = 0,
        limit: int = 4000,
    ) -> ProcessOutputWindow:
        session = self.repository.refresh(
            self.repository.get(process_id, include_output=False),
            include_output=False,
        )
        normalized_limit = max(int(limit), 1)
        stdout_start = max(int(stdout_offset), 0)
        stderr_start = max(int(stderr_offset), 0)
        stdout_slice, next_stdout_offset = self.repository.read_stdout_window(
            process_id,
            offset=stdout_start,
            limit=normalized_limit,
        )
        stderr_slice, next_stderr_offset = self.repository.read_stderr_window(
            process_id,
            offset=stderr_start,
            limit=normalized_limit,
        )
        return ProcessOutputWindow(
            process_id=session.id,
            status=session.status,
            exit_code=session.exit_code,
            stdout=stdout_slice,
            stderr=stderr_slice,
            stdout_offset=stdout_start,
            stderr_offset=stderr_start,
            next_stdout_offset=next_stdout_offset,
            next_stderr_offset=next_stderr_offset,
            started_at=session.started_at,
            ended_at=session.ended_at,
        )

    def terminate_session(self, *, process_id: str) -> ProcessSession:
        session = self.get_session(process_id=process_id)
        if not session.is_running:
            return session
        return self.supervisor.terminate(process_id)

    def remove_session(self, *, process_id: str) -> None:
        session = self.get_session(process_id=process_id)
        if session.is_running:
            raise ProcessValidationError(
                f"Process '{process_id}' is still running; kill it before removing it.",
            )
        self.repository.remove(process_id)

    def close(self) -> None:
        self.supervisor.close()
