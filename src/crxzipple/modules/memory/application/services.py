from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any, Callable, Protocol
from uuid import uuid4

from crxzipple.modules.memory.domain.entities import MemoryCandidate, MemoryEntry
from crxzipple.modules.memory.domain.exceptions import (
    MemoryCandidateAlreadyReviewedError,
    MemoryCandidateNotFoundError,
    MemoryEntryNotFoundError,
)
from crxzipple.modules.memory.domain.repositories import (
    MemoryCandidateRepository,
    MemoryEntryRepository,
)
from crxzipple.modules.memory.domain.value_objects import MemoryCandidateStatus
from crxzipple.modules.memory.infrastructure.index_manager import (
    WorkspaceMemoryIndexManager,
)
from crxzipple.modules.memory.infrastructure.workspace_store import WorkspaceMemoryStore
from crxzipple.shared.domain.aggregates import AggregateRoot


@dataclass(frozen=True, slots=True)
class CreateMemoryCandidateInput:
    agent_id: str
    title: str
    content: str
    summary: str = ""
    candidate_id: str | None = None
    session_key: str | None = None
    run_id: str | None = None
    tags: tuple[str, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ApproveMemoryCandidateInput:
    candidate_id: str
    entry_id: str | None = None


@dataclass(frozen=True, slots=True)
class RejectMemoryCandidateInput:
    candidate_id: str
    reason: str = "rejected"


@dataclass(frozen=True, slots=True)
class ListMemoryCandidatesInput:
    agent_id: str | None = None
    session_key: str | None = None
    run_id: str | None = None
    status: MemoryCandidateStatus | None = None
    limit: int | None = None


@dataclass(frozen=True, slots=True)
class ListMemoryEntriesInput:
    agent_id: str | None = None
    query: str | None = None
    limit: int | None = None


@dataclass(frozen=True, slots=True)
class RecallMemoryEntriesInput:
    agent_id: str
    query_text: str
    limit: int = 3
    search_limit: int = 25


@dataclass(frozen=True, slots=True)
class RecordMemoryFlushInput:
    agent_id: str
    content: str
    title: str | None = None
    summary: str | None = None
    session_key: str | None = None
    run_id: str | None = None
    tags: tuple[str, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)


class MemoryUnitOfWork(Protocol):
    memory_candidates: MemoryCandidateRepository
    memory_entries: MemoryEntryRepository

    def __enter__(self) -> "MemoryUnitOfWork":
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        ...

    def collect(self, aggregate: AggregateRoot[Any]) -> None:
        ...

    def commit(self) -> None:
        ...

    def rollback(self) -> None:
        ...


class MemoryApplicationService:
    def __init__(
        self,
        uow_factory: Callable[[], MemoryUnitOfWork],
        *,
        workspace_resolver: Callable[[str], str | None] | None = None,
        workspace_store: WorkspaceMemoryStore | None = None,
        index_manager: WorkspaceMemoryIndexManager | None = None,
    ) -> None:
        self.uow_factory = uow_factory
        self.workspace_resolver = workspace_resolver
        self.workspace_store = workspace_store or WorkspaceMemoryStore()
        self.index_manager = index_manager or WorkspaceMemoryIndexManager(
            workspace_store=self.workspace_store,
        )

    def create_candidate(self, data: CreateMemoryCandidateInput) -> MemoryCandidate:
        candidate = MemoryCandidate.create(
            candidate_id=data.candidate_id or uuid4().hex,
            agent_id=data.agent_id,
            title=data.title,
            content=data.content,
            summary=data.summary,
            session_key=data.session_key,
            run_id=data.run_id,
            tags=data.tags,
            metadata=data.metadata,
        )
        entry = self._auto_capture_entry(candidate)
        with self.uow_factory() as uow:
            uow.memory_candidates.add(candidate)
            uow.collect(candidate)
            if entry is not None:
                uow.memory_entries.add(entry)
                uow.collect(entry)
            uow.commit()
            return candidate

    def approve_candidate(self, data: ApproveMemoryCandidateInput) -> MemoryEntry:
        with self.uow_factory() as uow:
            candidate = uow.memory_candidates.get(data.candidate_id)
            if candidate is None:
                raise MemoryCandidateNotFoundError(
                    f"Memory candidate '{data.candidate_id}' was not found.",
                )
            if candidate.status is not MemoryCandidateStatus.PENDING:
                raise MemoryCandidateAlreadyReviewedError(
                    f"Memory candidate '{candidate.id}' has already been reviewed.",
                )

            entry = self._resolve_existing_entry(
                uow,
                candidate=candidate,
                entry_id=candidate.approved_entry_id,
            )
            if entry is None:
                entry = self._capture_entry(
                    candidate,
                    entry_id=data.entry_id or uuid4().hex,
                )
            if entry is None:
                entry = MemoryEntry.create(
                    entry_id=data.entry_id or uuid4().hex,
                    agent_id=candidate.agent_id,
                    title=candidate.title,
                    content=candidate.content,
                    summary=candidate.summary,
                    session_key=candidate.session_key,
                    run_id=candidate.run_id,
                    source_candidate_id=candidate.id,
                    tags=candidate.tags,
                    metadata=candidate.metadata,
                )
                candidate.record(entry_id=entry.id)
            candidate.mark_approved()
            uow.memory_candidates.add(candidate)
            uow.memory_entries.add(entry)
            uow.collect(candidate)
            uow.collect(entry)
            uow.commit()
            return entry

    def reject_candidate(self, data: RejectMemoryCandidateInput) -> MemoryCandidate:
        with self.uow_factory() as uow:
            candidate = uow.memory_candidates.get(data.candidate_id)
            if candidate is None:
                raise MemoryCandidateNotFoundError(
                    f"Memory candidate '{data.candidate_id}' was not found.",
                )
            if candidate.status is not MemoryCandidateStatus.PENDING:
                raise MemoryCandidateAlreadyReviewedError(
                    f"Memory candidate '{candidate.id}' has already been reviewed.",
                )

            approved_entry_id = candidate.approved_entry_id
            candidate.reject(reason=data.reason)
            if approved_entry_id is not None:
                workspace_dir = self._resolve_workspace(candidate.agent_id)
                if workspace_dir is not None:
                    self.workspace_store.remove_entry(
                        workspace_dir=workspace_dir,
                        entry_id=approved_entry_id,
                    )
                uow.memory_entries.delete(approved_entry_id)
            uow.memory_candidates.add(candidate)
            uow.collect(candidate)
            uow.commit()
            return candidate

    def get_candidate(self, candidate_id: str) -> MemoryCandidate:
        with self.uow_factory() as uow:
            candidate = uow.memory_candidates.get(candidate_id)
            if candidate is None:
                raise MemoryCandidateNotFoundError(
                    f"Memory candidate '{candidate_id}' was not found.",
                )
            return candidate

    def list_candidates(
        self,
        data: ListMemoryCandidatesInput | None = None,
    ) -> list[MemoryCandidate]:
        request = data or ListMemoryCandidatesInput()
        with self.uow_factory() as uow:
            return uow.memory_candidates.list(
                agent_id=request.agent_id,
                session_key=request.session_key,
                run_id=request.run_id,
                status=request.status,
                limit=request.limit,
            )

    def get_entry(self, entry_id: str) -> MemoryEntry:
        with self.uow_factory() as uow:
            entry = uow.memory_entries.get(entry_id)
            if entry is None:
                raise MemoryEntryNotFoundError(
                    f"Memory entry '{entry_id}' was not found.",
                )
            return self._resolve_workspace_projection(entry) or entry

    def list_entries(
        self,
        data: ListMemoryEntriesInput | None = None,
    ) -> list[MemoryEntry]:
        request = data or ListMemoryEntriesInput()
        with self.uow_factory() as uow:
            if request.query is not None and request.query.strip():
                entries = self._search_entries(
                    uow,
                    agent_id=request.agent_id,
                    query=request.query,
                    limit=request.limit,
                )
            else:
                entries = self._list_entries(
                    uow,
                    agent_id=request.agent_id,
                    query=None,
                    limit=request.limit,
                )
        return entries

    def recall_entries(
        self,
        data: RecallMemoryEntriesInput,
    ) -> list[MemoryEntry]:
        normalized_agent_id = data.agent_id.strip()
        normalized_query_text = data.query_text.strip()
        if not normalized_agent_id or not normalized_query_text:
            return []

        with self.uow_factory() as uow:
            candidates = self._search_entries(
                uow,
                agent_id=normalized_agent_id,
                query=normalized_query_text,
                limit=max(1, data.search_limit),
            )

        query_tokens = _tokenize(normalized_query_text)
        if not query_tokens:
            return candidates[: max(0, data.limit)]

        scored: list[tuple[int, MemoryEntry]] = []
        for entry in candidates:
            score = _score_entry(entry, query_tokens)
            if score <= 0:
                continue
            scored.append((score, entry))
        scored.sort(
            key=lambda item: (
                item[0],
                _sortable_datetime(item[1].updated_at),
                _sortable_datetime(item[1].created_at),
                item[1].id,
            ),
            reverse=True,
        )
        return [entry for _, entry in scored[: max(0, data.limit)]]

    def record_flush_entry(
        self,
        data: RecordMemoryFlushInput,
    ) -> MemoryEntry:
        normalized_content = data.content.strip()
        if not normalized_content:
            raise ValueError("Memory flush content cannot be empty.")

        entry = MemoryEntry.create(
            entry_id=uuid4().hex,
            agent_id=data.agent_id,
            title=(data.title or _derive_title(normalized_content)),
            content=normalized_content,
            summary=(data.summary or _derive_summary(normalized_content)),
            session_key=data.session_key,
            run_id=data.run_id,
            source_candidate_id=None,
            tags=_normalize_flush_tags(data.tags),
            metadata={
                "kind": "memory_flush",
                "capture_mode": "flush",
                **dict(data.metadata),
            },
        )
        workspace_dir = self._resolve_workspace(data.agent_id)
        stored_entry = entry
        if workspace_dir is not None:
            stored_entry = self.workspace_store.append_entry(
                workspace_dir=workspace_dir,
                entry=entry,
            )
        with self.uow_factory() as uow:
            uow.memory_entries.add(stored_entry)
            uow.collect(stored_entry)
            uow.commit()
        return stored_entry

    def _auto_capture_entry(self, candidate: MemoryCandidate) -> MemoryEntry | None:
        entry = self._capture_entry(candidate, entry_id=uuid4().hex)
        if entry is None:
            return None
        candidate.metadata["capture_mode"] = "auto"
        candidate.metadata["capture_storage"] = "workspace_file"
        return entry

    def _capture_entry(
        self,
        candidate: MemoryCandidate,
        *,
        entry_id: str,
    ) -> MemoryEntry | None:
        workspace_dir = self._resolve_workspace(candidate.agent_id)
        if workspace_dir is None:
            return None
        entry = MemoryEntry.create(
            entry_id=entry_id,
            agent_id=candidate.agent_id,
            title=candidate.title,
            content=candidate.content,
            summary=candidate.summary,
            session_key=candidate.session_key,
            run_id=candidate.run_id,
            source_candidate_id=candidate.id,
            tags=candidate.tags,
            metadata=candidate.metadata,
        )
        try:
            stored_entry = self.workspace_store.append_entry(
                workspace_dir=workspace_dir,
                entry=entry,
            )
        except OSError as exc:
            candidate.metadata["capture_error"] = str(exc)
            return None
        candidate.record(entry_id=stored_entry.id)
        candidate.metadata.pop("capture_error", None)
        memory_file_path = stored_entry.metadata.get("memory_file_path")
        if isinstance(memory_file_path, str) and memory_file_path.strip():
            candidate.metadata["memory_file_path"] = memory_file_path.strip()
        return stored_entry

    def _resolve_existing_entry(
        self,
        uow: MemoryUnitOfWork,
        *,
        candidate: MemoryCandidate,
        entry_id: str | None,
    ) -> MemoryEntry | None:
        if entry_id is None or not entry_id.strip():
            return None
        workspace_dir = self._resolve_workspace(candidate.agent_id)
        if workspace_dir is not None:
            entry = self.workspace_store.get_entry(
                workspace_dir=workspace_dir,
                entry_id=entry_id,
            )
            if entry is not None:
                return entry
        return uow.memory_entries.get(entry_id)

    def _resolve_workspace_projection(self, entry: MemoryEntry) -> MemoryEntry | None:
        workspace_dir = self._resolve_workspace(entry.agent_id)
        if workspace_dir is None:
            return None
        storage_kind = entry.metadata.get("storage_kind")
        if storage_kind != "workspace_file":
            return None
        return self.workspace_store.get_entry(
            workspace_dir=workspace_dir,
            entry_id=entry.id,
        )

    def _list_entries(
        self,
        uow: MemoryUnitOfWork,
        *,
        agent_id: str | None,
        query: str | None,
        limit: int | None,
    ) -> list[MemoryEntry]:
        db_entries = uow.memory_entries.list(
            agent_id=agent_id,
            query=query,
            limit=None,
        )
        workspace_entries: list[MemoryEntry] = []
        if agent_id is not None and agent_id.strip():
            workspace_dir = self._resolve_workspace(agent_id)
            if workspace_dir is not None:
                workspace_entries = self.workspace_store.list_entries(
                    workspace_dir=workspace_dir,
                    agent_id=agent_id,
                    query=query,
                    limit=None,
                )
        merged: dict[str, MemoryEntry] = {entry.id: entry for entry in db_entries}
        for entry in workspace_entries:
            merged[entry.id] = entry
        items = sorted(
            merged.values(),
            key=lambda entry: (
                _sortable_datetime(entry.updated_at),
                _sortable_datetime(entry.created_at),
                entry.id,
            ),
            reverse=True,
        )
        if limit is not None and limit > 0:
            return items[:limit]
        return items

    def _search_entries(
        self,
        uow: MemoryUnitOfWork,
        *,
        agent_id: str | None,
        query: str,
        limit: int | None,
    ) -> list[MemoryEntry]:
        normalized_query = query.strip()
        if not normalized_query:
            return self._list_entries(
                uow,
                agent_id=agent_id,
                query=None,
                limit=limit,
            )
        query_tokens = _tokenize(normalized_query)
        db_entries = self._search_db_entries(
            uow,
            agent_id=agent_id,
            query=normalized_query,
            query_tokens=query_tokens,
        )
        workspace_entries: list[MemoryEntry] = []
        if agent_id is not None and agent_id.strip():
            workspace_dir = self._resolve_workspace(agent_id)
            if workspace_dir is not None:
                workspace_entries = self.index_manager.search_entries(
                    workspace_dir=workspace_dir,
                    agent_id=agent_id,
                    query=normalized_query,
                    limit=None,
                )
        merged: dict[str, MemoryEntry] = {entry.id: entry for entry in db_entries}
        for entry in workspace_entries:
            merged[entry.id] = entry
        items = list(merged.values())
        if query_tokens:
            items = [
                entry
                for entry in items
                if _score_entry(entry, query_tokens) > 0
                or _query_text_matches(entry, normalized_query)
            ]
            items.sort(
                key=lambda entry: (
                    _score_entry(entry, query_tokens),
                    _sortable_datetime(entry.updated_at),
                    _sortable_datetime(entry.created_at),
                    entry.id,
                ),
                reverse=True,
            )
        else:
            items.sort(
                key=lambda entry: (
                    _sortable_datetime(entry.updated_at),
                    _sortable_datetime(entry.created_at),
                    entry.id,
                ),
                reverse=True,
            )
        if limit is not None and limit > 0:
            return items[:limit]
        return items

    def _search_db_entries(
        self,
        uow: MemoryUnitOfWork,
        *,
        agent_id: str | None,
        query: str,
        query_tokens: tuple[str, ...],
    ) -> list[MemoryEntry]:
        direct_matches = uow.memory_entries.list(
            agent_id=agent_id,
            query=query,
            limit=None,
        )
        if not query_tokens:
            return direct_matches
        merged: dict[str, MemoryEntry] = {entry.id: entry for entry in direct_matches}
        for entry in uow.memory_entries.list(
            agent_id=agent_id,
            query=None,
            limit=None,
        ):
            if _score_entry(entry, query_tokens) <= 0:
                continue
            merged[entry.id] = entry
        return list(merged.values())

    def _resolve_workspace(self, agent_id: str) -> str | None:
        if self.workspace_resolver is None:
            return None
        normalized_agent_id = agent_id.strip()
        if not normalized_agent_id:
            return None
        try:
            workspace_dir = self.workspace_resolver(normalized_agent_id)
        except Exception:
            return None
        if workspace_dir is None or not workspace_dir.strip():
            return None
        return workspace_dir.strip()


def _tokenize(value: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            token
            for token in re.findall(r"[A-Za-z0-9_:-]+", value.casefold())
            if len(token) >= 3
        ),
    )


def _derive_title(content: str) -> str:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return "Memory flush"
    first = lines[0]
    if first.startswith("#"):
        normalized = first.lstrip("# ").strip()
        if normalized:
            return normalized[:120]
    if first.lower().startswith("title:"):
        normalized = first.split(":", 1)[1].strip()
        if normalized:
            return normalized[:120]
    return first[:120] or "Memory flush"


def _derive_summary(content: str) -> str:
    for line in (item.strip() for item in content.splitlines()):
        if not line:
            continue
        if line.startswith("#"):
            continue
        if line.lower().startswith("title:"):
            continue
        return line[:240]
    return content.strip()[:240]


def _normalize_flush_tags(tags: tuple[str, ...]) -> tuple[str, ...]:
    normalized = ["memory_flush", *tags]
    return tuple(
        dict.fromkeys(
            tag.strip().lower()
            for tag in normalized
            if tag is not None and tag.strip()
        ),
    )


def _score_entry(entry: MemoryEntry, query_tokens: tuple[str, ...]) -> int:
    title = entry.title.casefold()
    summary = entry.summary.casefold()
    content = entry.content.casefold()
    tags = tuple(tag.casefold() for tag in entry.tags)

    score = 0
    for token in query_tokens:
        if token in title:
            score += 5
        if token in summary:
            score += 4
        if token in content:
            score += 2
        if any(token in tag for tag in tags):
            score += 3
    return score


def _query_text_matches(entry: MemoryEntry, query_text: str) -> bool:
    normalized_query = query_text.casefold()
    if not normalized_query:
        return False
    if normalized_query in entry.title.casefold():
        return True
    if normalized_query in entry.summary.casefold():
        return True
    if normalized_query in entry.content.casefold():
        return True
    return any(normalized_query in tag.casefold() for tag in entry.tags)


def _sortable_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
