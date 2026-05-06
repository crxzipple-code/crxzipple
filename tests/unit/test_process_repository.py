from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from crxzipple.modules.process.domain import ProcessSession, ProcessStatus
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


if __name__ == "__main__":
    unittest.main()
