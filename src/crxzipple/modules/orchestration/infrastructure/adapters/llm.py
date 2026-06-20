from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.llm.application import LlmApplicationService
from crxzipple.modules.llm.application.services import llm_profile_from_config
from crxzipple.modules.llm.domain.exceptions import LlmNotFoundError
from crxzipple.modules.orchestration.application.ports import LlmPort


@dataclass(slots=True)
class LlmServiceAdapter(LlmPort):
    service: LlmApplicationService
    configured_profiles: tuple[Any, ...] = ()

    def get_profile(self, llm_id: str):
        get_profile_optional = getattr(self.service, "get_profile_optional", None)
        if callable(get_profile_optional):
            profile = get_profile_optional(llm_id)
            if profile is not None:
                return profile
            return self._configured_profile_or_raise(llm_id)
        try:
            return self.service.get_profile(llm_id)
        except LlmNotFoundError:
            return self._configured_profile_or_raise(llm_id)

    def _configured_profile_or_raise(self, llm_id: str):
        for config in self.configured_profiles:
            profile = llm_profile_from_config(config)
            if profile.id == llm_id:
                return profile
        raise LlmNotFoundError(f"LLM profile '{llm_id}' was not found.")

    def invoke(self, data):
        return self.service.invoke(data)

    async def invoke_async(self, data):
        return await self.service.invoke_async(data)

    def stream_invoke(self, data):
        return self.service.stream_invoke(data)

    def stream_invoke_async(self, data):
        return self.service.stream_invoke_async(data)

    def get_invocation(self, invocation_id: str):
        return self.service.get_invocation(invocation_id)
