from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.llm.application import LlmApplicationService
from crxzipple.modules.orchestration.application.ports import LlmPort


@dataclass(slots=True)
class LlmServiceAdapter(LlmPort):
    service: LlmApplicationService

    def get_profile(self, llm_id: str):
        return self.service.get_profile(llm_id)

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
