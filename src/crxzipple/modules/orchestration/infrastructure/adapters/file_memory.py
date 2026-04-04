from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from crxzipple.modules.agent.application import AgentApplicationService
from crxzipple.modules.agent.domain import AgentNotFoundError, AgentValidationError
from crxzipple.modules.agent.domain.entities import AgentProfile
from crxzipple.modules.memory.application import (
    FileBackedMemoryService,
    MemoryExcerpt,
    MemorySearchHit,
    MemoryUseContext,
    MemoryWriteResult,
)
from crxzipple.modules.orchestration.application.ports import MemoryPort
from crxzipple.modules.orchestration.infrastructure.memory_bindings import (
    AgentMemoryBinding,
)


@dataclass(frozen=True, slots=True)
class FileMemoryContextResolver:
    agent_service: AgentApplicationService
    default_retrieval_backend: str
    binding_loader: Callable[[str], AgentMemoryBinding] | None = None
    context_observer: Callable[[MemoryUseContext], None] | None = None

    def resolve(self, space_ref: str | None) -> MemoryUseContext | None:
        normalized_space_ref = (space_ref or "").strip()
        if not normalized_space_ref:
            return None
        try:
            profile = self.agent_service.get_profile(normalized_space_ref)
        except AgentNotFoundError:
            return self._resolve_by_memory_space_id(normalized_space_ref)
        except AgentValidationError:
            context = self._context_from_registered_home(normalized_space_ref)
            if context is not None:
                self._observe(context)
            return context
        context = self._context_from_profile(profile)
        if context is not None:
            self._observe(context)
        return context

    def _resolve_by_memory_space_id(self, space_id: str) -> MemoryUseContext | None:
        try:
            profiles = self.agent_service.list_profiles()
        except AgentValidationError:
            return None
        matches = [
            profile
            for profile in profiles
            if self._space_id_for_profile(profile, self._resolve_binding(profile)) == space_id
        ]
        if len(matches) != 1:
            return None
        context = self._context_from_profile(matches[0])
        if context is not None:
            self._observe(context)
        return context

    def _context_from_registered_home(self, profile_id: str) -> MemoryUseContext | None:
        home_dir = self.agent_service.resolve_registered_home(profile_id)
        if home_dir is None or not home_dir.strip():
            return None
        binding = AgentMemoryBinding()
        if self.binding_loader is not None:
            loaded_binding = self.binding_loader(home_dir)
            if loaded_binding.to_payload():
                binding = loaded_binding
        return MemoryUseContext(
            space_id=binding.space_id or profile_id,
            storage_root=home_dir,
            retrieval_backend=self.default_retrieval_backend,
        )

    def _context_from_profile(self, profile: AgentProfile) -> MemoryUseContext | None:
        storage_root = profile.runtime_preferences.resolved_home_dir
        if storage_root is None or not storage_root.strip():
            return None
        return MemoryUseContext(
            space_id=self._space_id_for_profile(profile, self._resolve_binding(profile)),
            storage_root=storage_root,
            retrieval_backend=self._retrieval_backend_for_profile(profile),
        )

    def _resolve_binding(self, profile: AgentProfile) -> AgentMemoryBinding:
        home_dir = profile.runtime_preferences.resolved_home_dir
        if self.binding_loader is not None and home_dir is not None:
            binding = self.binding_loader(home_dir)
            if binding.to_payload():
                return binding
        return AgentMemoryBinding()

    @staticmethod
    def _space_id_for_profile(
        profile: AgentProfile,
        binding: AgentMemoryBinding,
    ) -> str:
        return binding.space_id or profile.id

    def _retrieval_backend_for_profile(self, profile: AgentProfile) -> str:
        return (
            profile.runtime_preferences.memory_retrieval_backend
            or self.default_retrieval_backend
        )

    def _observe(self, context: MemoryUseContext) -> None:
        if self.context_observer is not None:
            self.context_observer(context)


@dataclass(slots=True)
class FileBackedMemoryPortAdapter(MemoryPort):
    service: FileBackedMemoryService
    context_resolver: FileMemoryContextResolver | None = None

    def resolve_context(
        self,
        *,
        space_id: str | None,
    ) -> MemoryUseContext | None:
        if self.context_resolver is None:
            return None
        return self.context_resolver.resolve(space_id)

    def search(
        self,
        *,
        context: MemoryUseContext,
        query: str,
        limit: int = 6,
    ) -> list[MemorySearchHit]:
        return self.service.search(
            context=context,
            query=query,
            limit=limit,
        )

    def warm_context(
        self,
        *,
        context: MemoryUseContext,
    ) -> bool:
        return self.service.warm_context(context=context)

    def get(
        self,
        *,
        context: MemoryUseContext,
        path: str,
        start_line: int | None = None,
        line_count: int | None = None,
    ) -> MemoryExcerpt | None:
        return self.service.get(
            context=context,
            path=path,
            start_line=start_line,
            line_count=line_count,
        )

    def append_daily(
        self,
        *,
        context: MemoryUseContext,
        content: str,
        title: str | None = None,
    ) -> MemoryWriteResult:
        return self.service.append_daily(
            context=context,
            content=content,
            title=title,
        )

    def write_long_term(
        self,
        *,
        context: MemoryUseContext,
        content: str,
    ) -> MemoryWriteResult:
        return self.service.write_long_term(
            context=context,
            content=content,
        )

    def archive_session(
        self,
        *,
        context: MemoryUseContext,
        content: str,
        slug: str | None = None,
    ) -> MemoryWriteResult:
        return self.service.archive_session(
            context=context,
            content=content,
            slug=slug,
        )
