from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from crxzipple.modules.agent.application import AgentApplicationService
from crxzipple.modules.agent.domain import AgentNotFoundError, AgentValidationError
from crxzipple.modules.agent.domain.entities import AgentProfile
from crxzipple.modules.memory.application import (
    MEMORY_CONTEXT_RESOLVE_FAILED_EVENT,
    MEMORY_CONTEXT_RESOLVED_EVENT,
    MemoryEventEmitter,
    MemorySpaceService,
    MemoryUseContext,
    emit_memory_event,
)
from crxzipple.modules.memory.domain import MemorySpaceOwnerKind


@dataclass(frozen=True, slots=True)
class AgentMemoryScopeResolver:
    agent_service: AgentApplicationService
    memory_spaces: MemorySpaceService
    default_retrieval_backend: str
    context_observer: Callable[[MemoryUseContext], None] | None = None
    event_emitter: MemoryEventEmitter | None = None

    def resolve(self, space_ref: str | None) -> MemoryUseContext | None:
        normalized_space_ref = (space_ref or "").strip()
        if not normalized_space_ref:
            self._observe_resolution(
                normalized_space_ref,
                None,
                reason="empty space reference",
            )
            return None
        try:
            profile = self.agent_service.get_profile(normalized_space_ref)
        except AgentNotFoundError:
            context = self._resolve_existing_or_bound_space(normalized_space_ref)
            if context is None:
                self._observe_resolution(
                    normalized_space_ref,
                    None,
                    reason="agent or memory space not found",
                )
            return context
        except AgentValidationError:
            self._observe_resolution(
                normalized_space_ref,
                None,
                reason="agent profile is not readable",
            )
            return None
        context = self._context_from_profile(profile)
        if context is not None:
            self._observe(context)
            self._observe_resolution(normalized_space_ref, context)
        else:
            self._observe_resolution(
                normalized_space_ref,
                None,
                reason="agent memory is not configured",
            )
        return context

    def _resolve_existing_or_bound_space(
        self,
        scope_ref: str,
    ) -> MemoryUseContext | None:
        context = self.memory_spaces.resolve_context(scope_ref)
        if context is not None:
            self._observe(context)
            self._observe_resolution(scope_ref, context)
            return context
        profile = self._first_profile_bound_to_scope(scope_ref)
        if profile is None:
            return None
        context = self._context_from_profile(profile)
        if context is not None:
            self._observe(context)
            self._observe_resolution(scope_ref, context)
        return context

    def _first_profile_bound_to_scope(self, scope_ref: str) -> AgentProfile | None:
        try:
            profiles = self.agent_service.list_profiles()
        except AgentValidationError:
            return None
        matches = [
            profile
            for profile in profiles
            if profile.memory.enabled
            and profile.memory.effective_scope_ref(profile.id) == scope_ref
        ]
        return sorted(matches, key=lambda item: item.id)[0] if matches else None

    def _context_from_profile(self, profile: AgentProfile) -> MemoryUseContext | None:
        if not profile.memory.enabled:
            return None
        scope_ref = profile.memory.effective_scope_ref(profile.id)
        owner_kind = memory_scope_owner_kind(scope_ref, agent_id=profile.id)
        space = self.memory_spaces.ensure_space(
            scope_ref=scope_ref,
            owner_kind=owner_kind,
            owner_id=profile.id,
            retrieval_backend=self.default_retrieval_backend,
        )
        return self.memory_spaces.resolve_context(space.scope_ref)

    def _observe(self, context: MemoryUseContext) -> None:
        if self.context_observer is not None:
            self.context_observer(context)

    def _observe_resolution(
        self,
        space_ref: str | None,
        context: MemoryUseContext | None,
        *,
        reason: str = "resolved",
    ) -> None:
        if context is None:
            emit_memory_event(
                self.event_emitter,
                MEMORY_CONTEXT_RESOLVE_FAILED_EVENT,
                status="failed",
                level="warning",
                payload={
                    "agent_id": (space_ref or "").strip(),
                    "space_ref": (space_ref or "").strip(),
                    "reason": reason,
                    "owner_id": (space_ref or "").strip(),
                    "owner_kind": "memory_space",
                },
            )
            return
        emit_memory_event(
            self.event_emitter,
            MEMORY_CONTEXT_RESOLVED_EVENT,
            context=context,
            status="resolved",
            payload={
                "agent_id": (space_ref or "").strip(),
                "space_ref": (space_ref or "").strip(),
                "reason": reason,
            },
        )


def memory_scope_owner_kind(scope_ref: str, *, agent_id: str) -> MemorySpaceOwnerKind:
    normalized = scope_ref.strip()
    if normalized == agent_id:
        return "agent"
    if normalized.startswith("project:"):
        return "project"
    if normalized.startswith("team:"):
        return "team"
    if normalized.startswith("system:"):
        return "system"
    return "shared"
