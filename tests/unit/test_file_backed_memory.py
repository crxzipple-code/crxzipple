from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from crxzipple.modules.memory import FileBackedMemoryService, MemoryUseContext
from crxzipple.modules.memory.domain.services import search_snippet
from crxzipple.modules.memory.infrastructure.indexing import (
    FileMemoryIndexManager,
    OpenAICompatibleMemoryEmbeddingProvider,
)
from crxzipple.modules.memory.infrastructure.storage import FileMemoryStore
from tests.unit.support import SampleEmbeddingApiServer


def _file_backed_memory_service(
    *,
    index_manager: FileMemoryIndexManager | None = None,
) -> FileBackedMemoryService:
    return FileBackedMemoryService(
        store=FileMemoryStore(),
        index_manager=index_manager or FileMemoryIndexManager(),
    )


class FileBackedMemoryTestCase(unittest.TestCase):
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

    def test_append_daily_writes_markdown_and_returns_slice(self) -> None:
        written = self.service.append_daily(
            context=self.context,
            title="Today",
            content="Remember the benchmark plan.\nUse the latest dataset.",
            now=datetime(2026, 3, 27, 8, 30, tzinfo=timezone.utc),
        )

        self.assertEqual(written.path, "memory/2026-03-27.md")
        excerpt = self.service.get(
            context=self.context,
            path=written.path,
            start_line=written.line_start,
            line_count=4,
        )

        self.assertIsNotNone(excerpt)
        assert excerpt is not None
        self.assertEqual(excerpt.kind, "daily")
        self.assertIn("## Today", excerpt.text)
        self.assertIn("benchmark plan", excerpt.text)

    def test_write_long_term_and_search_return_chunk_hit(self) -> None:
        self.service.write_long_term(
            context=self.context,
            content="# Preferences\nUse concise answers with concrete file refs.\n",
        )

        hits = self.service.search(
            context=self.context,
            query="concise file refs",
            limit=3,
        )

        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].path, "MEMORY.md")
        self.assertEqual(hits[0].kind, "long_term")
        self.assertGreaterEqual(hits[0].start_line, 1)
        self.assertIn("concrete file refs", hits[0].snippet)
        self.assertEqual(hits[0].item.space_id, "writer")
        self.assertEqual(hits[0].item.path, "MEMORY.md")
        self.assertEqual(hits[0].item.kind, "long_term")
        self.assertTrue(hits[0].item.id)
        self.assertTrue(hits[0].item.preview)
        self.assertIn("concrete file refs", hits[0].item.preview)
        self.assertTrue(hits[0].item.content_hash)
        self.assertTrue(hits[0].item.source_file_hash)

    def test_search_snippet_prefers_specific_query_term(self) -> None:
        text = "\n".join(
            [
                "# Daily Memory",
                "",
                "- User asked what tools are available and asked about skills.",
                "- Mentioned available skill: `memory-recall` for recalling prior project decisions.",
                "- User's birthday is **October 5**.",
                "- Keep answers practical.",
            ],
        )

        snippet = search_snippet(
            text,
            "user birthday date or birthday preference",
            max_chars=140,
        )

        self.assertIn("birthday is **October 5**", snippet)
        self.assertNotIn("what tools are available", snippet)

    def test_search_surfaces_birthday_line_in_snippet(self) -> None:
        self.service.append_daily(
            context=self.context,
            content="\n".join(
                [
                    "- User asked what tools are available and asked about skills.",
                    "- Mentioned available skill: `memory-recall` for recalling prior project decisions, user preferences, historical commitments, or long-term workspace context.",
                    "- User's birthday is **October 5**.",
                ],
            ),
            now=datetime(2026, 3, 28, 8, 30, tzinfo=timezone.utc),
        )

        hits = self.service.search(
            context=self.context,
            query="user birthday date or birthday preference",
            limit=3,
        )

        self.assertEqual(len(hits), 1)
        self.assertIn("birthday is **October 5**", hits[0].snippet)

    def test_index_uses_openclaw_like_schema(self) -> None:
        self.service.write_long_term(
            context=self.context,
            content="# Preferences\nTrack indexing schema explicitly.\n",
        )
        self.service.warm_context(context=self.context)

        db_path = self.service.index_manager.index_db_path(self.root, self.context.space_id)
        with sqlite3.connect(db_path) as connection:
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')",
                ).fetchall()
            }
            meta = dict(connection.execute("SELECT key, value FROM meta").fetchall())

        self.assertIn("meta", tables)
        self.assertIn("files", tables)
        self.assertIn("chunks", tables)
        self.assertIn("chunks_fts", tables)
        self.assertIn("chunks_vec", tables)
        self.assertIn("embedding_cache", tables)
        self.assertEqual(meta["schema_version"], "openclaw-like-v1")
        self.assertEqual(meta["chunk_chars"], str(self.service.index_manager.chunk_chars))
        self.assertEqual(meta["overlap_chars"], str(self.service.index_manager.overlap_chars))
        self.assertEqual(meta["index_mode"], "vector")
        self.assertEqual(meta["vector_provider"], "local")

    def test_search_reindexes_after_file_changes(self) -> None:
        memory_path = self.root / "MEMORY.md"
        memory_path.write_text("# Notes\nAlpha retrieval path.\n", encoding="utf-8")

        first_hits = self.service.search(
            context=self.context,
            query="alpha retrieval",
            limit=3,
        )
        db_path = self.service.index_manager.index_db_path(self.root, self.context.space_id)
        with sqlite3.connect(db_path) as connection:
            first_hash = str(
                connection.execute(
                    "SELECT hash FROM files WHERE path = ?",
                    ("MEMORY.md",),
                ).fetchone()[0],
            )
        memory_path.write_text("# Notes\nGamma storage path.\n", encoding="utf-8")
        second_hits = self.service.search(
            context=self.context,
            query="gamma storage",
            limit=3,
        )
        with sqlite3.connect(db_path) as connection:
            second_hash = str(
                connection.execute(
                    "SELECT hash FROM files WHERE path = ?",
                    ("MEMORY.md",),
                ).fetchone()[0],
            )
        stale_hits = self.service.search(
            context=self.context,
            query="alpha retrieval",
            limit=3,
        )

        self.assertEqual(len(first_hits), 1)
        self.assertEqual(len(second_hits), 1)
        self.assertEqual(second_hits[0].path, "MEMORY.md")
        self.assertNotEqual(first_hash, second_hash)
        self.assertEqual(stale_hits, [])

    def test_write_archive_writes_slugged_markdown_file(self) -> None:
        written = self.service.write_archive(
            context=self.context,
            content="# Archive\nUser asked for the release checklist.",
            slug="Release Checklist",
            now=datetime(2026, 3, 27, 10, 15, tzinfo=timezone.utc),
        )

        self.assertEqual(written.path, "memory/2026-03-27-release-checklist.md")
        excerpt = self.service.get(
            context=self.context,
            path=written.path,
        )

        self.assertIsNotNone(excerpt)
        assert excerpt is not None
        self.assertEqual(excerpt.kind, "archive")
        self.assertIn("# Archive", excerpt.text)

    def test_vector_search_handles_typos_with_local_embeddings(self) -> None:
        vector_context = MemoryUseContext(
            space_id="writer",
            storage_root=str(self.root),
            retrieval_backend="vector",
        )
        self.service.write_long_term(
            context=vector_context,
            content="# Release Notes\nKeep the release checklist updated.\n",
        )

        hits = self.service.search(
            context=vector_context,
            query="relese cheklist",
            limit=3,
        )

        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].path, "MEMORY.md")
        self.assertIn("release checklist", hits[0].snippet.casefold())

    def test_metadata_change_rebuilds_index_mode(self) -> None:
        keyword_context = MemoryUseContext(
            space_id="writer",
            storage_root=str(self.root),
            retrieval_backend="keyword",
        )
        vector_context = MemoryUseContext(
            space_id="writer",
            storage_root=str(self.root),
            retrieval_backend="vector",
        )
        self.service.write_long_term(
            context=keyword_context,
            content="# Notes\nTrack the approval checklist.\n",
        )
        self.service.warm_context(context=keyword_context)

        db_path = self.service.index_manager.index_db_path(self.root, keyword_context.space_id)
        with sqlite3.connect(db_path) as connection:
            keyword_meta = dict(connection.execute("SELECT key, value FROM meta").fetchall())
            keyword_vec_count = int(
                connection.execute("SELECT count(*) FROM chunks_vec").fetchone()[0],
            )

        self.service.search(
            context=vector_context,
            query="approval cheklist",
            limit=3,
        )
        with sqlite3.connect(db_path) as connection:
            vector_meta = dict(connection.execute("SELECT key, value FROM meta").fetchall())
            vector_vec_count = int(
                connection.execute("SELECT count(*) FROM chunks_vec").fetchone()[0],
            )

        self.assertEqual(keyword_meta["index_mode"], "keyword")
        self.assertEqual(keyword_vec_count, 0)
        self.assertEqual(vector_meta["index_mode"], "vector")
        self.assertEqual(vector_meta["vector_provider"], "local")
        self.assertGreater(vector_vec_count, 0)

    def test_openai_compatible_provider_populates_embedding_cache(self) -> None:
        previous_token = os.environ.get("OPENAI_COMPATIBLE_TOKEN")
        os.environ["OPENAI_COMPATIBLE_TOKEN"] = "sample-embedding-token"
        server = SampleEmbeddingApiServer()
        server.start()
        try:
            service = _file_backed_memory_service(
                index_manager=FileMemoryIndexManager(
                    embedding_provider=OpenAICompatibleMemoryEmbeddingProvider(
                        base_url=server.base_url + "/v1",
                        model_name="sample-embedding-model",
                        credential_binding="env:OPENAI_COMPATIBLE_TOKEN",
                        resolved_credential="sample-embedding-token",
                        timeout_seconds=5,
                    ),
                ),
            )
            context = MemoryUseContext(
                space_id="writer",
                storage_root=str(self.root),
                retrieval_backend="vector",
            )
            service.write_long_term(
                context=context,
                content="# Notes\nKeep the release checklist fresh.\n",
            )
            service.warm_context(context=context)

            db_path = service.index_manager.index_db_path(self.root, context.space_id)
            with sqlite3.connect(db_path) as connection:
                meta = dict(connection.execute("SELECT key, value FROM meta").fetchall())
                cache_count = int(
                    connection.execute(
                        "SELECT count(*) FROM embedding_cache WHERE provider = ?",
                        ("openai_compatible",),
                    ).fetchone()[0],
                )

            hits = service.search(
                context=context,
                query="release cheklist",
                limit=3,
            )
            self.assertEqual(meta["vector_provider"], "openai_compatible")
            self.assertEqual(meta["vector_model"], "sample-embedding-model")
            self.assertGreater(cache_count, 0)
            self.assertEqual(len(hits), 1)
        finally:
            server.close()
            if previous_token is None:
                os.environ.pop("OPENAI_COMPATIBLE_TOKEN", None)
            else:
                os.environ["OPENAI_COMPATIBLE_TOKEN"] = previous_token

    def test_write_marks_dirty_and_search_syncs_on_demand(self) -> None:
        self.service.write_long_term(
            context=self.context,
            content="# Notes\nWarm the index on demand.\n",
        )

        db_path = self.service.index_manager.index_db_path(self.root, self.context.space_id)
        if db_path.exists():
            with sqlite3.connect(db_path) as connection:
                files_count = int(connection.execute("SELECT count(*) FROM files").fetchone()[0])
            self.assertEqual(files_count, 0)

        hits = self.service.search(
            context=self.context,
            query="warm the index",
            limit=3,
        )

        self.assertEqual(len(hits), 1)
        with sqlite3.connect(db_path) as connection:
            files_count = int(connection.execute("SELECT count(*) FROM files").fetchone()[0])
        self.assertGreater(files_count, 0)

    def test_dirty_path_sync_reindexes_changed_file_without_full_scan(self) -> None:
        memory_path = self.root / "MEMORY.md"
        memory_path.write_text("# Notes\nAlpha retrieval path.\n", encoding="utf-8")
        self.service.warm_context(context=self.context)

        def fail_full_scan(_self, *, storage_root):
            raise AssertionError(f"unexpected full scan for {storage_root}")

        with patch.object(
            type(self.service.index_manager.source_scanner),
            "scan",
            side_effect=fail_full_scan,
        ):
            memory_path.write_text("# Notes\nGamma retrieval path.\n", encoding="utf-8")
            self.service.index_manager.mark_dirty(
                context=self.context,
                changed_paths=("MEMORY.md",),
            )

            hits = self.service.search(
                context=self.context,
                query="gamma retrieval",
                limit=3,
            )

        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].path, "MEMORY.md")

    def test_dirty_path_sync_deletes_removed_file_without_full_scan(self) -> None:
        memory_path = self.root / "MEMORY.md"
        memory_path.write_text("# Notes\nAlpha retrieval path.\n", encoding="utf-8")
        self.service.warm_context(context=self.context)
        memory_path.unlink()

        def fail_full_scan(_self, *, storage_root):
            raise AssertionError(f"unexpected full scan for {storage_root}")

        with patch.object(
            type(self.service.index_manager.source_scanner),
            "scan",
            side_effect=fail_full_scan,
        ):
            self.service.index_manager.mark_dirty(
                context=self.context,
                changed_paths=("MEMORY.md",),
            )
            hits = self.service.search(
                context=self.context,
                query="alpha retrieval",
                limit=3,
            )

        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
