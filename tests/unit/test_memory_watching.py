from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from crxzipple.modules.memory import FileBackedMemoryService, MemoryUseContext
from crxzipple.modules.memory.infrastructure.indexing import FileMemoryIndexManager
from crxzipple.modules.memory.infrastructure.storage import FileMemoryStore
from crxzipple.modules.memory.infrastructure.watching.watch_registry import (
    MemoryWatchRegistry,
)


def _file_backed_memory_service() -> FileBackedMemoryService:
    return FileBackedMemoryService(
        store=FileMemoryStore(),
        index_manager=FileMemoryIndexManager(),
    )


class MemoryWatchingTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = tempfile.TemporaryDirectory()
        self.root = Path(self.workspace.name)
        self.context = MemoryUseContext(
            space_id="writer",
            storage_root=str(self.root),
            retrieval_backend="hybrid",
        )
        self.service = _file_backed_memory_service()

    def tearDown(self) -> None:
        self.workspace.cleanup()

    def test_watch_registry_warms_index_after_memory_file_change(self) -> None:
        memory_path = self.root / "MEMORY.md"
        memory_path.write_text("# Notes\nAlpha retrieval path.\n", encoding="utf-8")
        self.service.warm_context(context=self.context)
        db_path = self.service.index_manager.index_db_path(self.root, self.context.space_id)
        with sqlite3.connect(db_path) as connection:
            first_hash = str(
                connection.execute(
                    "SELECT hash FROM files WHERE path = ?",
                    ("MEMORY.md",),
                ).fetchone()[0],
            )

        change_ready = threading.Event()

        def fake_watch(
            _root: str,
            *,
            stop_event: threading.Event,
            debounce: int,
            recursive: bool,
        ):
            self.assertEqual(debounce, 1500)
            self.assertTrue(recursive)
            while not stop_event.is_set():
                if not change_ready.wait(0.05):
                    continue
                change_ready.clear()
                yield {(1, str(memory_path))}
                return

        with patch(
            "crxzipple.modules.memory.infrastructure.watching.watch_registry._watchfiles_watch",
            fake_watch,
        ):
            registry = MemoryWatchRegistry(memory_service=self.service)
            self.addCleanup(registry.close)
            self.assertTrue(registry.ensure_watching(self.context))
            memory_path.write_text("# Notes\nGamma storage path.\n", encoding="utf-8")
            change_ready.set()

            deadline = time.time() + 2.0
            second_hash = first_hash
            while time.time() < deadline:
                with sqlite3.connect(db_path) as connection:
                    second_hash = str(
                        connection.execute(
                            "SELECT hash FROM files WHERE path = ?",
                            ("MEMORY.md",),
                        ).fetchone()[0],
                    )
                if second_hash != first_hash:
                    break
                time.sleep(0.05)

            metrics = registry.snapshot_metrics()

        self.assertNotEqual(first_hash, second_hash)
        self.assertEqual(metrics.watched_roots, 1)
        self.assertEqual(metrics.watched_contexts, 1)
        self.assertGreaterEqual(metrics.filesystem_events, 1)
        self.assertGreaterEqual(metrics.filesystem_sync_runs, 1)
        self.assertEqual(metrics.filesystem_sync_failures, 0)

    def test_watch_registry_interval_warms_index_without_watchfiles(self) -> None:
        memory_path = self.root / "MEMORY.md"
        memory_path.write_text("# Notes\nAlpha retrieval path.\n", encoding="utf-8")
        self.service.warm_context(context=self.context)
        db_path = self.service.index_manager.index_db_path(self.root, self.context.space_id)
        with sqlite3.connect(db_path) as connection:
            first_hash = str(
                connection.execute(
                    "SELECT hash FROM files WHERE path = ?",
                    ("MEMORY.md",),
                ).fetchone()[0],
            )

        with patch(
            "crxzipple.modules.memory.infrastructure.watching.watch_registry._watchfiles_watch",
            None,
        ):
            registry = MemoryWatchRegistry(
                memory_service=self.service,
                interval_seconds=0.05,
            )
            self.addCleanup(registry.close)
            self.assertTrue(registry.ensure_watching(self.context))
            memory_path.write_text("# Notes\nDelta interval path.\n", encoding="utf-8")

            deadline = time.time() + 2.0
            second_hash = first_hash
            while time.time() < deadline:
                with sqlite3.connect(db_path) as connection:
                    second_hash = str(
                        connection.execute(
                            "SELECT hash FROM files WHERE path = ?",
                            ("MEMORY.md",),
                        ).fetchone()[0],
                    )
                if second_hash != first_hash:
                    break
                time.sleep(0.05)

            metrics = registry.snapshot_metrics()

        self.assertNotEqual(first_hash, second_hash)
        self.assertGreaterEqual(metrics.interval_ticks, 1)
        self.assertGreaterEqual(metrics.interval_sync_runs, 1)
        self.assertEqual(metrics.interval_sync_failures, 0)

    def test_watch_registry_rename_event_reindexes_old_and_new_paths(self) -> None:
        old_path = self.root / "memory" / "2026-03-27.md"
        old_path.parent.mkdir(parents=True, exist_ok=True)
        old_path.write_text("## Start\nAlpha retrieval path.\n", encoding="utf-8")
        self.service.warm_context(context=self.context)
        db_path = self.service.index_manager.index_db_path(self.root, self.context.space_id)
        new_path = self.root / "memory" / "2026-03-27-renamed.md"
        rename_ready = threading.Event()

        def fake_watch(
            _root: str,
            *,
            stop_event: threading.Event,
            debounce: int,
            recursive: bool,
        ):
            self.assertEqual(debounce, 1500)
            self.assertTrue(recursive)
            while not stop_event.is_set():
                if not rename_ready.wait(0.05):
                    continue
                rename_ready.clear()
                yield {(1, str(old_path), str(new_path))}
                return

        with patch(
            "crxzipple.modules.memory.infrastructure.watching.watch_registry._watchfiles_watch",
            fake_watch,
        ):
            registry = MemoryWatchRegistry(memory_service=self.service)
            self.addCleanup(registry.close)
            self.assertTrue(registry.ensure_watching(self.context))
            old_path.rename(new_path)
            rename_ready.set()

            deadline = time.time() + 2.0
            rows: list[tuple[str, str]] = []
            while time.time() < deadline:
                with sqlite3.connect(db_path) as connection:
                    rows = [
                        (str(path), str(file_hash))
                        for path, file_hash in connection.execute(
                            "SELECT path, hash FROM files ORDER BY path",
                        ).fetchall()
                    ]
                if rows == [("memory/2026-03-27-renamed.md", rows[0][1])] if rows else False:
                    break
                time.sleep(0.05)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "memory/2026-03-27-renamed.md")


if __name__ == "__main__":
    unittest.main()
