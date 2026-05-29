from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Protocol

from crxzipple.modules.memory.application.models import MemoryUseContext
from crxzipple.modules.memory.domain import (
    MemorySpace,
    MemorySpaceOwnerKind,
    MemorySpaceStatus,
)


class MemorySpaceRepository(Protocol):
    def get(self, scope_ref: str) -> MemorySpace | None:
        ...

    def list(self, *, include_disabled: bool = False) -> tuple[MemorySpace, ...]:
        ...

    def upsert(self, space: MemorySpace) -> MemorySpace:
        ...

    def delete(self, scope_ref: str) -> None:
        ...


class MemorySpaceService:
    def __init__(
        self,
        repository: MemorySpaceRepository,
        *,
        default_storage_root: str = ".crxzipple/memory",
    ) -> None:
        self._repository = repository
        self._default_storage_root = _normalize_storage_root(default_storage_root)

    def ensure_space(
        self,
        *,
        scope_ref: str,
        owner_kind: MemorySpaceOwnerKind,
        owner_id: str,
        storage_root: str | None = None,
        retrieval_backend: str,
        engine_id: str = "file_markdown",
        status: MemorySpaceStatus = "active",
        replace_storage_root: bool = False,
        metadata: dict[str, object] | None = None,
    ) -> MemorySpace:
        now = datetime.now(timezone.utc)
        existing = self._repository.get(scope_ref)
        resolved_storage_root = (
            _normalize_storage_root(storage_root)
            if storage_root is not None
            else self.storage_root_for_scope(scope_ref)
        )
        if existing is None:
            return self._repository.upsert(
                MemorySpace(
                    scope_ref=scope_ref,
                    owner_kind=owner_kind,
                    owner_id=owner_id,
                    engine_id=engine_id,
                    storage_root=resolved_storage_root,
                    retrieval_backend=retrieval_backend,
                    status=status,
                    metadata=metadata or {},
                    created_at=now,
                    updated_at=now,
                ),
            )
        keep_shared_owner = existing.owner_kind == "shared" and not replace_storage_root
        updated = replace(
            existing,
            owner_kind=existing.owner_kind if keep_shared_owner else owner_kind,
            owner_id=existing.owner_id if keep_shared_owner else owner_id,
            engine_id=engine_id,
            storage_root=(
                resolved_storage_root if replace_storage_root else existing.storage_root
            ),
            retrieval_backend=retrieval_backend,
            status=existing.status,
            metadata=dict(existing.metadata if metadata is None else metadata),
            updated_at=now,
        )
        return self._repository.upsert(updated)

    def storage_root_for_scope(self, scope_ref: str) -> str:
        return str(Path(self._default_storage_root) / _safe_scope_path(scope_ref))

    def upsert_space(
        self,
        *,
        scope_ref: str,
        owner_kind: MemorySpaceOwnerKind,
        owner_id: str,
        storage_root: str | None = None,
        retrieval_backend: str,
        engine_id: str = "file_markdown",
        status: MemorySpaceStatus = "active",
        metadata: dict[str, object] | None = None,
    ) -> MemorySpace:
        normalized_scope = scope_ref.strip()
        existing = self._repository.get(normalized_scope) if normalized_scope else None
        now = datetime.now(timezone.utc)
        resolved_storage_root = (
            _normalize_storage_root(storage_root)
            if storage_root is not None
            else (
                existing.storage_root
                if existing is not None
                else self.storage_root_for_scope(scope_ref)
            )
        )
        return self._repository.upsert(
            MemorySpace(
                scope_ref=scope_ref,
                owner_kind=owner_kind,
                owner_id=owner_id,
                engine_id=engine_id,
                storage_root=resolved_storage_root,
                retrieval_backend=retrieval_backend,
                status=status,
                metadata=dict(existing.metadata if metadata is None and existing else metadata or {}),
                created_at=existing.created_at if existing is not None else now,
                updated_at=now,
            ),
        )

    def get_space(self, scope_ref: str) -> MemorySpace | None:
        normalized = scope_ref.strip()
        if not normalized:
            return None
        return self._repository.get(normalized)

    def list_spaces(
        self,
        *,
        include_disabled: bool = False,
    ) -> tuple[MemorySpace, ...]:
        return self._repository.list(include_disabled=include_disabled)

    def resolve_context(self, scope_ref: str) -> MemoryUseContext | None:
        space = self.get_space(scope_ref)
        if space is None or not space.enabled:
            return None
        return MemoryUseContext(
            space_id=space.scope_ref,
            storage_root=space.storage_root,
            retrieval_backend=space.retrieval_backend,  # type: ignore[arg-type]
        )

    def disable_space(self, scope_ref: str) -> MemorySpace | None:
        space = self.get_space(scope_ref)
        if space is None:
            return None
        return self._repository.upsert(
            replace(
                space,
                status="disabled",
                updated_at=datetime.now(timezone.utc),
            ),
        )

    def delete_space(self, scope_ref: str) -> None:
        self._repository.delete(scope_ref)


def _normalize_storage_root(value: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError("Memory storage root cannot be empty.")
    return str(Path(normalized).expanduser())


def _safe_scope_path(scope_ref: str) -> str:
    normalized = str(scope_ref).strip()
    if not normalized:
        raise ValueError("Memory scope_ref cannot be empty.")
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", normalized).strip(".-")
    return safe or "default"
