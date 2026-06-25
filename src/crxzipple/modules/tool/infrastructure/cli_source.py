from __future__ import annotations

from typing import Any

from crxzipple.modules.process.application import ProcessApplicationService
from crxzipple.modules.tool.application.catalog_models import (
    ToolFunctionCatalogRecord,
    ToolFunctionStatus,
    ToolSourceCatalogRecord,
)
from crxzipple.modules.tool.infrastructure.cli_source_config import (
    CliToolSourceConfig,
)
from crxzipple.modules.tool.infrastructure.cli_source_discovery import (
    discover_cli_source,
)
from crxzipple.modules.tool.infrastructure.cli_source_runtime import (
    CliGuidedRuntime,
)
from crxzipple.modules.tool.infrastructure.runtimes.registry import ToolRuntimeRegistry


def register_cli_guided_handlers(
    registry: ToolRuntimeRegistry,
    *,
    source: ToolSourceCatalogRecord,
    functions: tuple[ToolFunctionCatalogRecord, ...],
    process_service: ProcessApplicationService,
    credential_provider: Any | None = None,
    events_service: Any | None = None,
    max_concurrency: int | None = None,
    replace: bool = False,
) -> None:
    config = CliToolSourceConfig.from_source(source)
    runtime = CliGuidedRuntime(
        config,
        process_service=process_service,
        credential_provider=credential_provider,
        events_service=events_service,
    )
    for function in functions:
        if function.status is not ToolFunctionStatus.ACTIVE or not function.enabled:
            continue
        action = str(function.metadata.get("cli_action") or "").strip()
        handler = runtime.handler_for(action, metadata=function.metadata)
        if handler is None:
            continue
        registry.register(
            function.handler_ref,
            handler,
            concurrency_key=f"cli:{config.provider_name}",
            max_concurrency=config.max_concurrency or max_concurrency,
            replace=replace,
        )


__all__ = [
    "CliToolSourceConfig",
    "discover_cli_source",
    "register_cli_guided_handlers",
]
