from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.operations.application.read_models.access import (
    AccessOperationsPage,
    AccessOperationsQuery,
    AccessOperationsReadModelProvider,
)
from crxzipple.modules.operations.application.read_models.channels import (
    ChannelsOperationsPage,
    ChannelsOperationsQuery,
    ChannelsOperationsReadModelProvider,
)
from crxzipple.modules.operations.application.read_models.daemon import (
    DaemonOperationsPage,
    DaemonOperationsQuery,
    DaemonOperationsReadModelProvider,
)
from crxzipple.modules.operations.application.read_models.events import (
    EventsOperationsPage,
    EventsOperationsQuery,
    EventsOperationsReadModelProvider,
)
from crxzipple.modules.operations.application.read_models.llm import (
    LlmOperationsPage,
    LlmOperationsQuery,
    LlmOperationsReadModelProvider,
)
from crxzipple.modules.operations.application.read_models.memory import (
    MemoryOperationsPage,
    MemoryOperationsQuery,
    MemoryOperationsReadModelProvider,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsModuleOverview,
)
from crxzipple.modules.operations.application.read_models.modules import (
    OperationsModulePage,
    OperationsModuleReadModelProvider,
)
from crxzipple.modules.operations.application.read_models.orchestration import (
    OrchestrationOperationsPage,
    OrchestrationOperationsReadModelProvider,
)
from crxzipple.modules.operations.application.read_models.skills import (
    SkillsOperationsPage,
    SkillsOperationsQuery,
    SkillsOperationsReadModelProvider,
)
from crxzipple.modules.operations.application.read_models.tool import (
    ToolOperationsQuery,
    ToolOperationsPage,
    ToolOperationsReadModelProvider,
)


@dataclass(frozen=True, slots=True)
class OperationsReadModelProvider:
    orchestration: OrchestrationOperationsReadModelProvider
    tool: ToolOperationsReadModelProvider
    llm: LlmOperationsReadModelProvider
    memory: MemoryOperationsReadModelProvider
    skills: SkillsOperationsReadModelProvider
    access: AccessOperationsReadModelProvider
    channels: ChannelsOperationsReadModelProvider
    events: EventsOperationsReadModelProvider
    daemon: DaemonOperationsReadModelProvider
    modules: OperationsModuleReadModelProvider

    def orchestration_page(self) -> OrchestrationOperationsPage:
        return self.orchestration.page()

    def tool_page(
        self,
        query: ToolOperationsQuery | None = None,
    ) -> ToolOperationsPage:
        return self.tool.page(query=query)

    def llm_page(
        self,
        query: LlmOperationsQuery | None = None,
    ) -> LlmOperationsPage:
        return self.llm.page(query=query)

    def memory_page(
        self,
        query: MemoryOperationsQuery | None = None,
    ) -> MemoryOperationsPage:
        return self.memory.page(query=query)

    def skills_page(
        self,
        query: SkillsOperationsQuery | None = None,
    ) -> SkillsOperationsPage:
        return self.skills.page(query=query)

    def access_page(
        self,
        query: AccessOperationsQuery | None = None,
    ) -> AccessOperationsPage:
        return self.access.page(query=query)

    def channels_page(
        self,
        query: ChannelsOperationsQuery | None = None,
    ) -> ChannelsOperationsPage:
        return self.channels.page(query=query)

    def events_page(
        self,
        query: EventsOperationsQuery | None = None,
    ) -> EventsOperationsPage:
        return self.events.page(query=query)

    def daemon_page(
        self,
        query: DaemonOperationsQuery | None = None,
    ) -> DaemonOperationsPage:
        return self.daemon.page(query=query)

    def module_page(self, module: str) -> OperationsModulePage | None:
        return self.modules.page(module)

    def module_overview(self, module: str) -> OperationsModuleOverview | None:
        if module == "orchestration":
            return self.orchestration.overview()
        if module == "tool":
            return self.tool.overview()
        if module == "llm":
            return self.llm.overview()
        if module == "memory":
            return self.memory.overview()
        if module == "skills":
            return self.skills.overview()
        if module == "access":
            return self.access.overview()
        if module == "channels":
            return self.channels.overview()
        if module == "events":
            return self.events.overview()
        if module == "daemon":
            return self.daemon.overview()
        return self.modules.overview(module)
