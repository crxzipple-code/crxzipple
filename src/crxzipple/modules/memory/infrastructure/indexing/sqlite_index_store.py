from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
from pathlib import Path
import re
import sqlite3
import time

from crxzipple.modules.memory.application.contracts import MemoryIndexStore, MemorySearchGateway
from crxzipple.modules.memory.application.models import MemorySearchRecord
from crxzipple.modules.memory.domain import IndexedChunk, IndexedMemoryFile, score_from_rank
from crxzipple.modules.memory.infrastructure.indexing.embeddings import (
    cosine_similarity,
    decode_embedding,
    encode_embedding,
)
from crxzipple.modules.memory.infrastructure.storage import ensure_storage_root


_INDEX_SOURCE = "memory"
_INDEX_MODEL = "filebacked"
_MIN_VECTOR_SCORE = 0.45


class SqliteMemoryIndexStore(MemoryIndexStore, MemorySearchGateway):
    def index_db_path(
        self,
        *,
        storage_root: str | Path,
        space_id: str,
    ) -> Path:
        root = ensure_storage_root(storage_root)
        state_dir = root / ".state"
        state_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(space_id.encode("utf-8")).hexdigest()[:12]
        return state_dir / f"memory-index-{digest}.sqlite3"

    def sync_metadata(
        self,
        *,
        storage_root: str | Path,
        space_id: str,
        expected: dict[str, str],
    ) -> bool:
        with self._connect(storage_root=storage_root, space_id=space_id) as connection:
            rows = connection.execute("SELECT key, value FROM meta").fetchall()
            existing = {str(row["key"]): str(row["value"]) for row in rows}
            needs_full_reindex = bool(existing) and existing != expected
            stale_keys = [key for key in existing if key not in expected]
            if stale_keys:
                connection.executemany(
                    "DELETE FROM meta WHERE key = ?",
                    ((key,) for key in stale_keys),
                )
            for key, value in expected.items():
                connection.execute(
                    """
                    INSERT INTO meta (key, value)
                    VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value
                    """,
                    (key, value),
                )
            connection.commit()
            return needs_full_reindex

    def indexed_file_hashes(
        self,
        *,
        storage_root: str | Path,
        space_id: str,
    ) -> dict[str, str]:
        with self._connect(storage_root=storage_root, space_id=space_id) as connection:
            rows = connection.execute(
                """
                SELECT path, hash
                FROM files
                WHERE source = ?
                """,
                (_INDEX_SOURCE,),
            ).fetchall()
        return {str(row["path"]): str(row["hash"]) for row in rows}

    def clear(
        self,
        *,
        storage_root: str | Path,
        space_id: str,
    ) -> None:
        with self._connect(storage_root=storage_root, space_id=space_id) as connection:
            try:
                connection.execute("DELETE FROM chunks_fts")
            except sqlite3.OperationalError:
                pass
            connection.execute("DELETE FROM chunks_vec")
            connection.execute("DELETE FROM chunks")
            connection.execute("DELETE FROM files")
            connection.commit()

    def delete_path(
        self,
        *,
        storage_root: str | Path,
        space_id: str,
        path: str,
    ) -> None:
        with self._connect(storage_root=storage_root, space_id=space_id) as connection:
            self._delete_path_rows(connection, path)
            connection.commit()

    def replace_file_chunks(
        self,
        *,
        storage_root: str | Path,
        space_id: str,
        indexed_file: IndexedMemoryFile,
        chunks: tuple[IndexedChunk, ...] | list[IndexedChunk],
        embeddings: Sequence[tuple[float, ...]] | None,
        embedding_provider_name: str | None,
        embedding_model_name: str | None,
        embedding_provider_key: str | None,
        retrieval_backend: str,
    ) -> None:
        with self._connect(storage_root=storage_root, space_id=space_id) as connection:
            self._delete_path_rows(connection, indexed_file.path)
            model = retrieval_backend.strip() or _INDEX_MODEL
            for index, chunk in enumerate(chunks):
                chunk_hash = hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()
                chunk_id = hashlib.sha256(
                    (
                        f"{indexed_file.path}:{_INDEX_SOURCE}:{index}:"
                        f"{chunk.start_line}:{chunk.end_line}:{chunk_hash}"
                    ).encode("utf-8"),
                ).hexdigest()
                embedding = (
                    embeddings[index]
                    if embeddings is not None and index < len(embeddings)
                    else None
                )
                connection.execute(
                    """
                    INSERT INTO chunks (
                        id,
                        path,
                        source,
                        start_line,
                        end_line,
                        hash,
                        model,
                        text,
                        embedding,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk_id,
                        indexed_file.path,
                        _INDEX_SOURCE,
                        chunk.start_line,
                        chunk.end_line,
                        chunk_hash,
                        model,
                        chunk.text,
                        encode_embedding(embedding or ()),
                        indexed_file.mtime_ns,
                    ),
                )
                if embedding is not None:
                    connection.execute(
                        """
                        INSERT INTO chunks_vec (
                            id,
                            embedding
                        )
                        VALUES (?, ?)
                        """,
                        (chunk_id, encode_embedding(embedding)),
                    )
                try:
                    connection.execute(
                        """
                        INSERT INTO chunks_fts (
                            text,
                            id,
                            path,
                            source,
                            model,
                            start_line,
                            end_line
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            chunk.text,
                            chunk_id,
                            indexed_file.path,
                            _INDEX_SOURCE,
                            model,
                            chunk.start_line,
                            chunk.end_line,
                        ),
                    )
                except sqlite3.OperationalError:
                    pass
                if (
                    embedding is not None
                    and embedding_provider_name is not None
                    and embedding_model_name is not None
                    and embedding_provider_key is not None
                ):
                    self._store_embedding_cache_rows(
                        connection,
                        provider_name=embedding_provider_name,
                        model_name=embedding_model_name,
                        provider_key=embedding_provider_key,
                        embeddings_by_hash={chunk_hash: embedding},
                    )
            connection.execute(
                """
                INSERT INTO files (
                    path,
                    source,
                    hash,
                    mtime,
                    size
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    source = excluded.source,
                    hash = excluded.hash,
                    mtime = excluded.mtime,
                    size = excluded.size
                """,
                (
                    indexed_file.path,
                    _INDEX_SOURCE,
                    indexed_file.source_file_hash,
                    indexed_file.mtime_ns,
                    indexed_file.size_bytes,
                ),
            )
            connection.commit()

    def load_embedding_cache(
        self,
        *,
        storage_root: str | Path,
        space_id: str,
        provider_name: str,
        model_name: str,
        provider_key: str,
        content_hashes: Sequence[str],
    ) -> dict[str, tuple[float, ...]]:
        normalized_hashes = tuple(dict.fromkeys(str(item) for item in content_hashes if str(item)))
        if not normalized_hashes:
            return {}
        placeholders = ",".join("?" for _ in normalized_hashes)
        with self._connect(storage_root=storage_root, space_id=space_id) as connection:
            rows = connection.execute(
                f"""
                SELECT hash, embedding
                FROM embedding_cache
                WHERE provider = ?
                  AND model = ?
                  AND provider_key = ?
                  AND hash IN ({placeholders})
                """,
                (provider_name, model_name, provider_key, *normalized_hashes),
            ).fetchall()
        return {
            str(row["hash"]): decode_embedding(str(row["embedding"]))
            for row in rows
        }

    def store_embedding_cache(
        self,
        *,
        storage_root: str | Path,
        space_id: str,
        provider_name: str,
        model_name: str,
        provider_key: str,
        embeddings_by_hash: Mapping[str, Sequence[float]],
    ) -> None:
        if not embeddings_by_hash:
            return
        with self._connect(storage_root=storage_root, space_id=space_id) as connection:
            self._store_embedding_cache_rows(
                connection,
                provider_name=provider_name,
                model_name=model_name,
                provider_key=provider_key,
                embeddings_by_hash=embeddings_by_hash,
            )
            connection.commit()

    def search_records(
        self,
        *,
        storage_root: str | Path,
        space_id: str,
        query: str,
        limit: int,
        retrieval_backend: str,
        query_embedding: Sequence[float] | None = None,
    ) -> list[MemorySearchRecord]:
        with self._connect(storage_root=storage_root, space_id=space_id) as connection:
            fts_enabled = self._fts_enabled(connection)
            normalized_backend = retrieval_backend.strip().lower()
            if normalized_backend == "vector":
                vector_records = self._search_records_vector(
                    connection=connection,
                    query_embedding=query_embedding,
                    limit=limit,
                )
                if vector_records:
                    return vector_records
            if normalized_backend == "hybrid":
                hybrid_records = self._search_records_hybrid(
                    connection=connection,
                    query=query,
                    query_embedding=query_embedding,
                    limit=limit,
                    fts_enabled=fts_enabled,
                )
                if hybrid_records:
                    return hybrid_records
            return self._search_records_keyword(
                connection=connection,
                query=query,
                limit=limit,
                fts_enabled=fts_enabled,
            )

    def _connect(
        self,
        *,
        storage_root: str | Path,
        space_id: str,
    ) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.index_db_path(storage_root=storage_root, space_id=space_id),
        )
        connection.row_factory = sqlite3.Row
        self._initialize_schema(connection)
        return connection

    def _initialize_schema(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """,
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                path TEXT PRIMARY KEY,
                source TEXT NOT NULL DEFAULT 'memory',
                hash TEXT NOT NULL,
                mtime INTEGER NOT NULL,
                size INTEGER NOT NULL
            )
            """,
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'memory',
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                hash TEXT NOT NULL,
                model TEXT NOT NULL,
                text TEXT NOT NULL,
                embedding TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """,
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks_vec (
                id TEXT PRIMARY KEY,
                embedding TEXT NOT NULL
            )
            """,
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS embedding_cache (
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                provider_key TEXT NOT NULL,
                hash TEXT NOT NULL,
                embedding TEXT NOT NULL,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY(provider, model, provider_key, hash)
            )
            """,
        )
        try:
            connection.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
                USING fts5(
                    text,
                    id UNINDEXED,
                    path UNINDEXED,
                    source UNINDEXED,
                    model UNINDEXED,
                    start_line UNINDEXED,
                    end_line UNINDEXED
                )
                """,
            )
        except sqlite3.OperationalError:
            pass
        connection.execute("CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_files_source ON files(source)")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_embedding_cache_provider ON embedding_cache(provider, model, provider_key)"
        )
        connection.commit()

    @staticmethod
    def _fts_enabled(connection: sqlite3.Connection) -> bool:
        try:
            connection.execute("SELECT count(*) FROM chunks_fts").fetchone()
        except sqlite3.OperationalError:
            return False
        return True

    def _delete_path_rows(self, connection: sqlite3.Connection, path: str) -> None:
        try:
            connection.execute(
                "DELETE FROM chunks_fts WHERE path = ? AND source = ?",
                (path, _INDEX_SOURCE),
            )
        except sqlite3.OperationalError:
            pass
        connection.execute(
            """
            DELETE FROM chunks_vec
            WHERE id IN (
                SELECT id
                FROM chunks
                WHERE path = ? AND source = ?
            )
            """,
            (path, _INDEX_SOURCE),
        )
        connection.execute(
            "DELETE FROM chunks WHERE path = ? AND source = ?",
            (path, _INDEX_SOURCE),
        )
        connection.execute(
            "DELETE FROM files WHERE path = ? AND source = ?",
            (path, _INDEX_SOURCE),
        )

    def _search_records_keyword(
        self,
        *,
        connection: sqlite3.Connection,
        query: str,
        limit: int,
        fts_enabled: bool,
    ) -> list[MemorySearchRecord]:
        if fts_enabled:
            tokens = _tokenize(query)
            if tokens:
                rows = connection.execute(
                    """
                    SELECT
                        c.id,
                        c.path,
                        c.start_line,
                        c.end_line,
                        c.text,
                        c.hash AS chunk_hash,
                        c.updated_at,
                        f.hash AS file_hash,
                        bm25(chunks_fts) AS rank
                    FROM chunks_fts
                    JOIN chunks c
                      ON c.id = chunks_fts.id
                    JOIN files f
                      ON f.path = c.path
                     AND f.source = c.source
                    WHERE chunks_fts MATCH ?
                    ORDER BY rank, c.path, c.start_line
                    LIMIT ?
                    """,
                    (_fts_query(tokens), limit),
                ).fetchall()
                return [
                    _record_from_row(row, score=score_from_rank(_safe_rank(row)))
                    for row in rows
                ]
        pattern = f"%{query.casefold()}%"
        rows = connection.execute(
            """
            SELECT
                c.id,
                c.path,
                c.start_line,
                c.end_line,
                c.text,
                c.hash AS chunk_hash,
                c.updated_at,
                f.hash AS file_hash
            FROM chunks c
            JOIN files f
              ON f.path = c.path
             AND f.source = c.source
            WHERE lower(c.text) LIKE ? OR lower(c.path) LIKE ?
            ORDER BY c.path, c.start_line
            LIMIT ?
            """,
            (pattern, pattern, limit),
        ).fetchall()
        return [_record_from_row(row, score=0.25) for row in rows]

    def _search_records_vector(
        self,
        *,
        connection: sqlite3.Connection,
        query_embedding: Sequence[float] | None,
        limit: int,
    ) -> list[MemorySearchRecord]:
        if query_embedding is None:
            return []
        rows = connection.execute(
            """
            SELECT
                c.id,
                c.path,
                c.start_line,
                c.end_line,
                c.text,
                c.hash AS chunk_hash,
                c.updated_at,
                f.hash AS file_hash,
                v.embedding AS vector_embedding
            FROM chunks c
            JOIN chunks_vec v
              ON v.id = c.id
            JOIN files f
              ON f.path = c.path
             AND f.source = c.source
            ORDER BY c.path, c.start_line
            """
        ).fetchall()
        scored = [
            (
                cosine_similarity(
                    query_embedding,
                    decode_embedding(str(row["vector_embedding"])),
                ),
                row,
            )
            for row in rows
        ]
        scored = [item for item in scored if item[0] >= _MIN_VECTOR_SCORE]
        scored.sort(key=lambda item: (-item[0], str(item[1]["path"]), int(item[1]["start_line"])))
        return [_record_from_row(row, score=score) for score, row in scored[:limit]]

    def _search_records_hybrid(
        self,
        *,
        connection: sqlite3.Connection,
        query: str,
        query_embedding: Sequence[float] | None,
        limit: int,
        fts_enabled: bool,
    ) -> list[MemorySearchRecord]:
        keyword_records = self._search_records_keyword(
            connection=connection,
            query=query,
            limit=max(limit * 3, limit),
            fts_enabled=fts_enabled,
        )
        vector_records = self._search_records_vector(
            connection=connection,
            query_embedding=query_embedding,
            limit=max(limit * 3, limit),
        )
        combined: dict[str, MemorySearchRecord] = {}
        weights: dict[str, float] = {}
        for record in keyword_records:
            combined[record.id] = record
            weights[record.id] = weights.get(record.id, 0.0) + (record.score * 0.65)
        for record in vector_records:
            combined.setdefault(record.id, record)
            weights[record.id] = weights.get(record.id, 0.0) + (record.score * 0.35)
        ranked = sorted(
            combined.values(),
            key=lambda record: (
                -weights.get(record.id, 0.0),
                record.path,
                record.start_line,
            ),
        )
        return [
            MemorySearchRecord(
                id=record.id,
                path=record.path,
                start_line=record.start_line,
                end_line=record.end_line,
                text=record.text,
                content_hash=record.content_hash,
                source_file_hash=record.source_file_hash,
                updated_at=record.updated_at,
                score=weights.get(record.id, 0.0),
            )
            for record in ranked[:limit]
        ]

    def _store_embedding_cache_rows(
        self,
        connection: sqlite3.Connection,
        *,
        provider_name: str,
        model_name: str,
        provider_key: str,
        embeddings_by_hash: Mapping[str, Sequence[float]],
    ) -> None:
        updated_at = int(time.time() * 1_000_000_000)
        connection.executemany(
            """
            INSERT INTO embedding_cache (
                provider,
                model,
                provider_key,
                hash,
                embedding,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider, model, provider_key, hash) DO UPDATE SET
                embedding = excluded.embedding,
                updated_at = excluded.updated_at
            """,
            (
                (
                    provider_name,
                    model_name,
                    provider_key,
                    content_hash,
                    encode_embedding(embedding),
                    updated_at,
                )
                for content_hash, embedding in embeddings_by_hash.items()
            ),
        )


def _tokenize(value: str) -> tuple[str, ...]:
    return tuple(
        token
        for token in re.findall(r"[0-9A-Za-z_]+", value.casefold())
        if token
    )


def _fts_query(tokens: tuple[str, ...]) -> str:
    return " OR ".join(f'"{token}"' for token in tokens)


def _record_from_row(row: sqlite3.Row, *, score: float) -> MemorySearchRecord:
    return MemorySearchRecord(
        id=str(row["id"]),
        path=str(row["path"]),
        start_line=int(row["start_line"]),
        end_line=int(row["end_line"]),
        text=str(row["text"]),
        content_hash=str(row["chunk_hash"]),
        source_file_hash=str(row["file_hash"]),
        updated_at=int(row["updated_at"]),
        score=float(score),
    )


def _safe_rank(row: sqlite3.Row) -> float:
    try:
        return float(row["rank"])
    except (KeyError, TypeError, ValueError):
        return 1.0
