from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from crxzipple.modules.process.domain import ProcessSession, ProcessStatus
from crxzipple.modules.process.domain.exceptions import (
    ProcessNotFoundError,
    ProcessValidationError,
)
from crxzipple.modules.process.application.services import ProcessApplicationService
from crxzipple.modules.process.infrastructure.repository import (
    FilesystemProcessSessionRepository,
)


class ProcessRepositoryTestCase(unittest.TestCase):
    def test_get_can_recover_session_from_sibling_namespace_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = FilesystemProcessSessionRepository(Path(temp_dir) / "postgres")
            target = FilesystemProcessSessionRepository(Path(temp_dir) / "sqlite")
            session = ProcessSession(
                id="proc-1",
                command="sleep 60",
                shell="/bin/sh",
                working_directory=temp_dir,
                session_key="daemon:worker:operations-observer",
                metadata={"scope": "source"},
                pid=999999,
                status=ProcessStatus.RUNNING,
            )
            source.save(session)
            source.stdout_path(session.id).write_text("observer-ready\n", encoding="utf-8")

            recovered = target.get(process_id=session.id)

            self.assertEqual(recovered.id, session.id)
            self.assertEqual(recovered.session_key, "daemon:worker:operations-observer")
            self.assertEqual(recovered.metadata["scope"], "source")
            self.assertEqual(recovered.stdout, "observer-ready\n")

    def test_read_output_uses_bounded_windows_without_full_log_read(self) -> None:
        class WindowOnlyRepository(FilesystemProcessSessionRepository):
            def read_stdout(self, process_id: str) -> str:
                raise AssertionError("read_output must not load full stdout")

            def read_stderr(self, process_id: str) -> str:
                raise AssertionError("read_output must not load full stderr")

        with tempfile.TemporaryDirectory() as temp_dir:
            repository = WindowOnlyRepository(Path(temp_dir))
            session = ProcessSession(
                id="proc-1",
                command="printf output",
                shell="/bin/sh",
                working_directory=temp_dir,
                pid=None,
                status=ProcessStatus.EXITED,
                exit_code=0,
            )
            repository.save(session)
            repository.stdout_path(session.id).write_text("abcdef", encoding="utf-8")
            repository.stderr_path(session.id).write_text("uvwxyz", encoding="utf-8")
            service = ProcessApplicationService(repository=repository, supervisor=object())

            output = service.read_output(
                process_id=session.id,
                stdout_offset=2,
                stderr_offset=1,
                limit=3,
            )

            self.assertEqual(output.stdout, "cde")
            self.assertEqual(output.stderr, "vwx")
            self.assertEqual(output.next_stdout_offset, 5)
            self.assertEqual(output.next_stderr_offset, 4)

    def test_repository_rejects_process_id_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = FilesystemProcessSessionRepository(Path(temp_dir))

            with self.assertRaises(ProcessNotFoundError):
                repository.get("../outside")

            with self.assertRaises(ProcessNotFoundError):
                repository.stdout_path("..")

    def test_refresh_marks_stale_running_process_failed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = FilesystemProcessSessionRepository(Path(temp_dir))
            session = ProcessSession(
                id="proc-1",
                command="sleep 60",
                shell="/bin/sh",
                working_directory=temp_dir,
                pid=99999999,
                status=ProcessStatus.RUNNING,
            )
            repository.save(session)

            refreshed = repository.refresh(
                repository.get(session.id, include_output=False),
                include_output=False,
            )

            self.assertEqual(refreshed.status, ProcessStatus.FAILED)
            self.assertIsNotNone(refreshed.ended_at)

    def test_cleanup_terminal_sessions_keeps_running_and_newest_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = FilesystemProcessSessionRepository(Path(temp_dir))
            now = datetime.now(timezone.utc)
            self._save_terminal_session(repository, "old", temp_dir, ended_at=now)
            self._save_terminal_session(
                repository,
                "new",
                temp_dir,
                ended_at=now + timedelta(seconds=1),
            )
            running = ProcessSession(
                id="running",
                command="sleep 60",
                shell="/bin/sh",
                working_directory=temp_dir,
                pid=1,
                status=ProcessStatus.RUNNING,
            )
            repository.save(running)

            result = repository.cleanup_terminal_sessions(max_terminal_sessions=1)

            self.assertEqual(result.removed_process_ids, ("old",))
            self.assertEqual(result.retained_running_process_ids, ("running",))
            with self.assertRaises(ProcessNotFoundError):
                repository.get("old", include_output=False)
            self.assertEqual(repository.get("new", include_output=False).id, "new")
            self.assertEqual(
                repository.get("running", include_output=False).status,
                ProcessStatus.RUNNING,
            )

    def test_cleanup_terminal_sessions_enforces_terminal_byte_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = FilesystemProcessSessionRepository(Path(temp_dir))
            now = datetime.now(timezone.utc)
            self._save_terminal_session(repository, "old", temp_dir, ended_at=now)
            repository.stdout_path("old").write_text("x" * 100, encoding="utf-8")
            self._save_terminal_session(
                repository,
                "new",
                temp_dir,
                ended_at=now + timedelta(seconds=1),
            )
            repository.stdout_path("new").write_text("y", encoding="utf-8")
            new_session_bytes = sum(
                path.stat().st_size for path in (Path(temp_dir) / "new").iterdir()
            )

            result = repository.cleanup_terminal_sessions(
                max_terminal_bytes=new_session_bytes,
            )

            self.assertEqual(result.removed_process_ids, ("old",))
            self.assertGreater(result.reclaimed_bytes, 0)
            self.assertEqual(repository.get("new", include_output=False).id, "new")

    def test_cleanup_sessions_requires_at_least_one_policy_constraint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = FilesystemProcessSessionRepository(Path(temp_dir))
            service = ProcessApplicationService(repository=repository, supervisor=object())

            with self.assertRaises(ProcessValidationError):
                service.cleanup_sessions()

    @staticmethod
    def _save_terminal_session(
        repository: FilesystemProcessSessionRepository,
        process_id: str,
        working_directory: str,
        *,
        ended_at: datetime,
    ) -> None:
        session = ProcessSession(
            id=process_id,
            command="printf done",
            shell="/bin/sh",
            working_directory=working_directory,
            pid=None,
            status=ProcessStatus.EXITED,
            exit_code=0,
            created_at=ended_at,
            started_at=ended_at,
            updated_at=ended_at,
            ended_at=ended_at,
        )
        repository.save(session)


if __name__ == "__main__":
    unittest.main()
