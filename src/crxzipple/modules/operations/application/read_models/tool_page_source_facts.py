from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.operations.application.read_models.ports_tooling import (
    OperationsToolQueryPort,
)
from crxzipple.modules.operations.application.read_models.tool_source_queries import (
    safe_discovery_runs_by_source,
    safe_tool_functions,
    safe_tool_provider_backend_readiness,
    safe_tool_provider_backends,
    safe_tool_sources,
)


@dataclass(frozen=True, slots=True)
class ToolPageSourceFacts:
    sources: tuple[Any, ...]
    functions: tuple[Any, ...]
    provider_backends: tuple[Any, ...]
    provider_backend_readiness: dict[str, Any]
    discovery_runs_by_source: dict[str, tuple[Any, ...]]


def collect_tool_page_source_facts(
    tool_service: OperationsToolQueryPort,
) -> ToolPageSourceFacts:
    sources = safe_tool_sources(tool_service)
    functions = safe_tool_functions(tool_service)
    provider_backends = safe_tool_provider_backends(tool_service)
    return ToolPageSourceFacts(
        sources=sources,
        functions=functions,
        provider_backends=provider_backends,
        provider_backend_readiness=safe_tool_provider_backend_readiness(
            tool_service,
            provider_backends,
        ),
        discovery_runs_by_source=safe_discovery_runs_by_source(
            tool_service,
            sources,
            limit=5,
        ),
    )
