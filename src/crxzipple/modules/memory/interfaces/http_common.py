from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.modules.memory.application import MemoryActorContext, MemoryUseContext
from crxzipple.modules.memory.domain import MemorySpace
from crxzipple.modules.settings.domain import SettingsNotFoundError
from crxzipple.shared.settings import MemoryConfig


def resolve_memory_context(
    container: AppContainer,
    agent_id: str | None,
):
    context = container.require(AppKey.MEMORY_CONTEXT_RESOLVER).resolve(agent_id)
    if context is None:
        raise HTTPException(
            status_code=404,
            detail="No file-backed memory context is available for this agent.",
        )
    return context


def resolve_memory_space_context(
    container: AppContainer,
    scope_ref: str,
    *,
    require_enabled: bool = True,
) -> tuple[MemorySpace, MemoryUseContext]:
    space = container.require(AppKey.MEMORY_SPACE_SERVICE).get_space(scope_ref)
    if space is None:
        raise HTTPException(status_code=404, detail="Memory space was not found.")
    if require_enabled and not space.enabled:
        raise HTTPException(status_code=409, detail="Memory space is disabled.")
    return space, MemoryUseContext(
        space_id=space.scope_ref,
        storage_root=space.storage_root,
        retrieval_backend=space.retrieval_backend,  # type: ignore[arg-type]
    )


def indexed_file_count(
    container: AppContainer,
    context: MemoryUseContext,
) -> int | None:
    index_manager = getattr(
        container.require(AppKey.FILE_MEMORY_SERVICE),
        "index_manager",
        None,
    )
    index_store = getattr(index_manager, "index_store", None)
    indexed_file_hashes = getattr(index_store, "indexed_file_hashes", None)
    if not callable(indexed_file_hashes):
        return None
    try:
        return len(
            indexed_file_hashes(
                storage_root=context.storage_root,
                space_id=context.space_id,
            ),
        )
    except Exception:
        return None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def memory_runtime_defaults_payload(container: AppContainer) -> dict[str, Any]:
    query = container.require(AppKey.SETTINGS_QUERY_SERVICE)
    try:
        resource = query.get_resource("default")
        if resource.resource_kind != "memory-config":
            raise SettingsNotFoundError("memory default settings resource was not found.")
        effective = query.get_effective(resource.id).effective_value
    except SettingsNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Memory runtime defaults are not available.",
        ) from exc
    if not isinstance(effective, Mapping):
        raise HTTPException(
            status_code=500,
            detail="Memory runtime defaults payload is invalid.",
        )
    payload = {"id": "default", **dict(effective)}
    try:
        config = MemoryConfig.from_payload(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Memory runtime defaults payload is invalid: {exc}",
        ) from exc
    return config.to_payload()


def runtime_actor_context(
    agent_id: str | None,
    scope_ref: str | None,
) -> MemoryActorContext:
    normalized_agent = agent_id.strip() if agent_id else None
    normalized_scope = scope_ref.strip() if scope_ref else None
    if not normalized_agent and not normalized_scope:
        raise ValueError("Memory runtime test requires agent_id or scope_ref.")
    return MemoryActorContext(agent_id=normalized_agent, scope_ref=normalized_scope)
