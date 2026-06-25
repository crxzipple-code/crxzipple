from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models import (
    AccessOperationsQuery,
    BrowserOperationsQuery,
    ChannelsOperationsQuery,
    ContextWorkspaceOperationsQuery,
    DaemonOperationsQuery,
    EventsOperationsQuery,
    LlmOperationsQuery,
    MemoryOperationsQuery,
    OperationsReadModelProvider,
    SkillsOperationsQuery,
    ToolOperationsQuery,
)


def module_page(provider: OperationsReadModelProvider, module: str) -> Any:
    if module == "orchestration":
        return provider.orchestration_page()
    if module == "tool":
        return provider.tool_page(ToolOperationsQuery(limit=50))
    if module == "browser":
        return provider.browser_page(BrowserOperationsQuery(limit=1000))
    if module == "llm":
        return provider.llm_page(LlmOperationsQuery(limit=50))
    if module == "access":
        return provider.access_page(AccessOperationsQuery(limit=1000))
    if module == "channels":
        return provider.channels_page(ChannelsOperationsQuery(limit=1000))
    if module == "memory":
        return provider.memory_page(MemoryOperationsQuery(limit=1000))
    if module == "context_workspace":
        return provider.context_workspace_page(
            ContextWorkspaceOperationsQuery(limit=1000),
        )
    if module == "skills":
        return provider.skills_page(SkillsOperationsQuery(limit=1000))
    if module == "events":
        return provider.events_page(EventsOperationsQuery(limit=1000))
    if module == "daemon":
        return provider.daemon_page(DaemonOperationsQuery(limit=1000))
    raise KeyError(module)
