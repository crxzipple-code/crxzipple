from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.ports_tooling import (
    OperationsToolQueryPort,
)
from crxzipple.modules.operations.application.read_models.tool_overview_type_sections import (
    tool_types_section,
)
from crxzipple.modules.operations.application.read_models.tool_page_facts import (
    ToolPageFacts,
)
from crxzipple.modules.operations.application.read_models.tool_readiness_sections import (
    auth_missing_section,
)
from crxzipple.modules.operations.application.read_models.tool_source_catalog_sections import (
    cli_process_health_section,
    discovery_failures_section,
    function_catalog_section,
    source_health_section,
)
from crxzipple.modules.operations.application.read_models.tool_source_provider_sections import (
    provider_backend_health_section,
)


def tool_catalog_sections(
    *,
    facts: ToolPageFacts,
    tool_service: OperationsToolQueryPort,
    access_service: Any | None,
) -> dict[str, Any]:
    return {
        "tool_types": tool_types_section(facts.tools, facts.runs),
        "source_health": source_health_section(
            facts.sources,
            functions=facts.functions,
            discovery_runs_by_source=facts.discovery_runs_by_source,
        ),
        "discovery_failures": discovery_failures_section(
            facts.sources,
            discovery_runs_by_source=facts.discovery_runs_by_source,
        ),
        "function_catalog": function_catalog_section(facts.functions),
        "provider_backend_health": provider_backend_health_section(
            facts.provider_backends,
            runs=facts.runs,
            readiness_by_backend_id=facts.provider_backend_readiness,
            now=facts.now,
        ),
        "cli_process_health": cli_process_health_section(
            facts.sources,
            functions=facts.functions,
        ),
        "auth_missing": auth_missing_section(
            facts.tools,
            facts.runs,
            tool_service=tool_service,
            access_service=access_service,
            now=facts.now,
        ),
    }
