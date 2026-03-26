from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
import threading

from crxzipple.modules.memory.domain.entities import MemoryEntry
from crxzipple.modules.memory.infrastructure.workspace_store import (
    WorkspaceMemoryStore,
    _iter_memory_files,
    _load_entries_from_file,
    _resolve_workspace_root,
)


@dataclass(slots=True)
class WorkspaceMemoryIndexManager:
    workspace_store: WorkspaceMemoryStore = field(default_factory=WorkspaceMemoryStore)
    _lock: threading.RLock = field(init=False, repr=False)
    _connection: sqlite3.Connection = field(init=False, repr=False)
    _fts_enabled: bool = field(init=False, repr=False, default=True)

    def __post_init__(self) -> None:
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(":memory:", check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._fts_enabled = True
        self._initialize_schema()

    def search_entries(
        self,
        *,
        workspace_dir: str,
        agent_id: str | None = None,
        query: str,
        limit: int | None = None,
    ) -> list[MemoryEntry]:
        normalized_query = query.strip()
        if not normalized_query:
            return []
        root = _resolve_workspace_root(workspace_dir)
        if root is None:
            return []
        normalized_agent_id = agent_id.strip() if agent_id is not None else None
        with self._lock:
            self._ensure_synced(root)
            effective_limit = limit if limit is not None and limit > 0 else 20
            if self._fts_enabled:
                rows = self._connection.execute(
                    """
                    SELECT
                        d.entry_id,
                        d.agent_id,
                        d.title,
                        d.content,
                        d.summary,
                        d.session_key,
                        d.run_id,
                        d.source_candidate_id,
                        d.tags_json,
                        d.metadata_json,
                        d.created_at,
                        d.updated_at
                    FROM memory_docs_fts f
                    JOIN memory_docs d
                      ON d.entry_id = f.entry_id
                    WHERE d.workspace_root = ?
                      AND (? IS NULL OR d.agent_id = ?)
                      AND memory_docs_fts MATCH ?
                    ORDER BY bm25(memory_docs_fts), d.updated_at DESC, d.entry_id DESC
                    LIMIT ?
                    """,
                    (
                        str(root),
                        normalized_agent_id,
                        normalized_agent_id,
                        _fts_query(normalized_query),
                        effective_limit,
                    ),
                ).fetchall()
                return [_row_to_entry(row) for row in rows]
            pattern = f"%{normalized_query.casefold()}%"
            rows = self._connection.execute(
                """
                SELECT
                    entry_id,
                    agent_id,
                    title,
                    content,
                    summary,
                    session_key,
                    run_id,
                    source_candidate_id,
                    tags_json,
                    metadata_json,
                    created_at,
                    updated_at
                FROM memory_docs
                WHERE workspace_root = ?
                  AND (? IS NULL OR agent_id = ?)
                  AND (
                    lower(title) LIKE ?
                    OR lower(summary) LIKE ?
                    OR lower(content) LIKE ?
                    OR lower(tags_text) LIKE ?
                  )
                ORDER BY updated_at DESC, entry_id DESC
                LIMIT ?
                """,
                (
                    str(root),
                    normalized_agent_id,
                    normalized_agent_id,
                    pattern,
                    pattern,
                    pattern,
                    pattern,
                    effective_limit,
                ),
            ).fetchall()
            return [_row_to_entry(row) for row in rows]

    def _initialize_schema(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS indexed_files (
                workspace_root TEXT NOT NULL,
                relative_path TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                mtime_ns INTEGER NOT NULL,
                PRIMARY KEY (workspace_root, relative_path)
            )
            """,
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_docs (
                entry_id TEXT PRIMARY KEY,
                workspace_root TEXT NOT NULL,
                relative_path TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                summary TEXT NOT NULL,
                session_key TEXT,
                run_id TEXT,
                source_candidate_id TEXT,
                tags_text TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
        )
        try:
            self._connection.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_docs_fts
                USING fts5(
                    entry_id UNINDEXED,
                    title,
                    summary,
                    content,
                    tags,
                    path
                )
                """,
            )
        except sqlite3.OperationalError:
            self._fts_enabled = False
        self._connection.commit()

    def _ensure_synced(self, root: Path) -> None:
        workspace_root = str(root)
        current_files = {
            path.relative_to(root).as_posix(): path
            for path in _iter_memory_files(root)
        }
        indexed_rows = self._connection.execute(
            """
            SELECT relative_path, size_bytes, mtime_ns
            FROM indexed_files
            WHERE workspace_root = ?
            """,
            (workspace_root,),
        ).fetchall()
        indexed_state = {
            str(row["relative_path"]): (
                int(row["size_bytes"]),
                int(row["mtime_ns"]),
            )
            for row in indexed_rows
        }

        removed_paths = sorted(set(indexed_state) - set(current_files))
        for relative_path in removed_paths:
            self._delete_path(workspace_root=workspace_root, relative_path=relative_path)

        for relative_path, path in current_files.items():
            stat = path.stat()
            file_state = (int(stat.st_size), int(stat.st_mtime_ns))
            if indexed_state.get(relative_path) == file_state:
                continue
            entries = _load_entries_from_file(
                root=root,
                path=path,
                agent_id_hint=None,
            )
            self._replace_path_entries(
                workspace_root=workspace_root,
                relative_path=relative_path,
                size_bytes=file_state[0],
                mtime_ns=file_state[1],
                entries=entries,
            )
        self._connection.commit()

    def _delete_path(self, *, workspace_root: str, relative_path: str) -> None:
        entry_ids = [
            str(row["entry_id"])
            for row in self._connection.execute(
                """
                SELECT entry_id
                FROM memory_docs
                WHERE workspace_root = ? AND relative_path = ?
                """,
                (workspace_root, relative_path),
            ).fetchall()
        ]
        for entry_id in entry_ids:
            if self._fts_enabled:
                self._connection.execute(
                    "DELETE FROM memory_docs_fts WHERE entry_id = ?",
                    (entry_id,),
                )
        self._connection.execute(
            """
            DELETE FROM memory_docs
            WHERE workspace_root = ? AND relative_path = ?
            """,
            (workspace_root, relative_path),
        )
        self._connection.execute(
            """
            DELETE FROM indexed_files
            WHERE workspace_root = ? AND relative_path = ?
            """,
            (workspace_root, relative_path),
        )

    def _replace_path_entries(
        self,
        *,
        workspace_root: str,
        relative_path: str,
        size_bytes: int,
        mtime_ns: int,
        entries: list[MemoryEntry],
    ) -> None:
        self._delete_path(workspace_root=workspace_root, relative_path=relative_path)
        self._connection.execute(
            """
            INSERT INTO indexed_files (workspace_root, relative_path, size_bytes, mtime_ns)
            VALUES (?, ?, ?, ?)
            """,
            (workspace_root, relative_path, size_bytes, mtime_ns),
        )
        for entry in entries:
            self._connection.execute(
                """
                INSERT INTO memory_docs (
                    entry_id,
                    workspace_root,
                    relative_path,
                    agent_id,
                    title,
                    content,
                    summary,
                    session_key,
                    run_id,
                    source_candidate_id,
                    tags_text,
                    tags_json,
                    metadata_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.id,
                    workspace_root,
                    relative_path,
                    entry.agent_id,
                    entry.title,
                    entry.content,
                    entry.summary,
                    entry.session_key,
                    entry.run_id,
                    entry.source_candidate_id,
                    " ".join(entry.tags),
                    json.dumps(list(entry.tags), ensure_ascii=True, sort_keys=True),
                    json.dumps(dict(entry.metadata), ensure_ascii=True, sort_keys=True),
                    entry.created_at.isoformat(),
                    entry.updated_at.isoformat(),
                ),
            )
            if self._fts_enabled:
                self._connection.execute(
                    """
                    INSERT INTO memory_docs_fts (
                        entry_id,
                        title,
                        summary,
                        content,
                        tags,
                        path
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.id,
                        entry.title,
                        entry.summary,
                        entry.content,
                        " ".join(entry.tags),
                        relative_path,
                    ),
                )


def _fts_query(query: str) -> str:
    tokens = list(
        dict.fromkeys(
            token
            for token in re.findall(r"[A-Za-z0-9_:-]+", query.casefold())
            if token
        ),
    )
    if not tokens:
        fallback = query.replace('"', " ").strip()
        return f'"{fallback}"' if fallback else '"memory"'
    return " OR ".join(f'"{token}"' for token in tokens)


def _row_to_entry(row: sqlite3.Row) -> MemoryEntry:
    tags = json.loads(str(row["tags_json"]))
    metadata = json.loads(str(row["metadata_json"]))
    return MemoryEntry(
        id=str(row["entry_id"]),
        agent_id=str(row["agent_id"]),
        title=str(row["title"]),
        content=str(row["content"]),
        summary=str(row["summary"]),
        session_key=_string_or_none(row["session_key"]),
        run_id=_string_or_none(row["run_id"]),
        source_candidate_id=_string_or_none(row["source_candidate_id"]),
        tags=tuple(str(item) for item in tags),
        metadata=metadata if isinstance(metadata, dict) else {},
        created_at=_parse_iso_datetime(row["created_at"]),
        updated_at=_parse_iso_datetime(row["updated_at"]),
    )


def _parse_iso_datetime(value: object) -> datetime:
    if isinstance(value, str) and value.strip():
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    return datetime.now(timezone.utc)


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
