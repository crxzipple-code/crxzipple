from __future__ import annotations

from crxzipple.modules.tool.application.catalog_models import (
    ToolFunctionCandidate,
    ToolFunctionRuntimeKind,
    ToolSourceCatalogRecord,
    ToolSourceDiscoveryResult,
)
from crxzipple.modules.tool.application.specifications import ToolSpec
from crxzipple.modules.tool.domain import (
    ToolDefinitionOrigin,
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolExecutionSupport,
    ToolMode,
)
from crxzipple.modules.tool.infrastructure.cli_source_config import (
    CliPromotedFunctionConfig,
    CliToolSourceConfig,
)
from crxzipple.modules.tool.infrastructure.cli_source_config_values import safe_tool_id
from crxzipple.modules.tool.infrastructure.cli_source_discovery_credentials import (
    guided_cli_credential_requirements,
    promoted_cli_credential_requirements,
)
from crxzipple.modules.tool.infrastructure.cli_source_discovery_guided import (
    GUIDED_CLI_ACTIONS,
    guided_cli_description,
    guided_cli_effects,
    guided_cli_name,
    guided_cli_parameters,
    guided_cli_policy,
    promoted_cli_effects,
    promoted_cli_policy,
)


def discover_cli_source(
    source: ToolSourceCatalogRecord,
) -> ToolSourceDiscoveryResult:
    config = CliToolSourceConfig.from_source(source)
    promoted_candidates = tuple(
        _promoted_cli_candidate(source, config, promoted)
        for promoted in config.promoted_functions
    )
    return ToolSourceDiscoveryResult.completed(
        source_id=source.source_id,
        candidates=(
            *(
                _guided_cli_candidate(source, config, action)
                for action in GUIDED_CLI_ACTIONS
            ),
            *promoted_candidates,
        ),
        metadata={
            "source": "configured_tool_provider",
            "package_kind": "cli",
            "provider_name": config.provider_name,
            "actions": GUIDED_CLI_ACTIONS,
            "promoted_functions": tuple(
                promoted.function_id for promoted in config.promoted_functions
            ),
        },
    )


def _guided_cli_candidate(
    source: ToolSourceCatalogRecord,
    config: CliToolSourceConfig,
    action: str,
) -> ToolFunctionCandidate:
    spec = _guided_cli_spec(source, config, action)
    return ToolFunctionCandidate.from_tool_spec(
        spec,
        source_id=source.source_id,
        stable_key=f"cli.{source.source_id}.{action}",
        runtime_kind=ToolFunctionRuntimeKind.CLI,
        handler_ref=spec.runtime_key,
        metadata={
            "source": "configured_tool_provider",
            "package_kind": "cli",
            "provider_name": config.provider_name,
            "cli_action": action,
        },
    )


def _promoted_cli_candidate(
    source: ToolSourceCatalogRecord,
    config: CliToolSourceConfig,
    promoted: CliPromotedFunctionConfig,
) -> ToolFunctionCandidate:
    spec = _promoted_cli_spec(source, config, promoted)
    return ToolFunctionCandidate.from_tool_spec(
        spec,
        source_id=source.source_id,
        stable_key=f"cli.{source.source_id}.promoted.{promoted.function_id}",
        runtime_kind=ToolFunctionRuntimeKind.CLI,
        handler_ref=spec.runtime_key,
        metadata={
            "source": "configured_tool_provider",
            "package_kind": "cli",
            "provider_name": config.provider_name,
            "cli_action": "cli_promoted_execute",
            "promoted_function_id": promoted.function_id,
            "promoted_function": promoted.metadata_payload(),
        },
    )


def _guided_cli_spec(
    source: ToolSourceCatalogRecord,
    config: CliToolSourceConfig,
    action: str,
) -> ToolSpec:
    return ToolSpec(
        id=f"{safe_tool_id(source.source_id)}_{action}",
        name=guided_cli_name(config, action),
        description=guided_cli_description(config, action),
        provider_name=config.provider_name,
        parameters=guided_cli_parameters(action),
        tags=("cli", "guided", config.provider_name),
        required_effect_ids=guided_cli_effects(config, action),
        runtime_requirement_sets=((config.source_marker,),),
        execution_policy=guided_cli_policy(config, action),
        execution_support=ToolExecutionSupport(
            supported_modes=(ToolMode.INLINE,),
            supported_strategies=(ToolExecutionStrategy.ASYNC,),
            supported_environments=(ToolEnvironment.REMOTE,),
        ),
        definition_origin=ToolDefinitionOrigin.REMOTE_DISCOVERY,
        runtime_key=f"cli.{safe_tool_id(source.source_id)}.{action}",
        credential_requirements=guided_cli_credential_requirements(
            source,
            config,
            action,
        ),
    )


def _promoted_cli_spec(
    source: ToolSourceCatalogRecord,
    config: CliToolSourceConfig,
    promoted: CliPromotedFunctionConfig,
) -> ToolSpec:
    safe_source_id = safe_tool_id(source.source_id)
    safe_function_id = safe_tool_id(promoted.function_id)
    return ToolSpec(
        id=f"{safe_source_id}_{safe_function_id}",
        name=promoted.name,
        description=promoted.description,
        provider_name=config.provider_name,
        parameters=tuple(
            parameter.as_tool_parameter()
            for parameter in promoted.parameters
        ),
        tags=("cli", "promoted", config.provider_name),
        required_effect_ids=promoted_cli_effects(config, promoted),
        runtime_requirement_sets=((config.source_marker,),),
        execution_policy=promoted_cli_policy(config, promoted),
        execution_support=ToolExecutionSupport(
            supported_modes=(ToolMode.INLINE,),
            supported_strategies=(ToolExecutionStrategy.ASYNC,),
            supported_environments=(ToolEnvironment.REMOTE,),
        ),
        definition_origin=ToolDefinitionOrigin.REMOTE_DISCOVERY,
        runtime_key=f"cli.{safe_source_id}.promoted.{safe_function_id}",
        credential_requirements=promoted_cli_credential_requirements(
            source,
            config,
            promoted,
        ),
    )


__all__ = [
    "GUIDED_CLI_ACTIONS",
    "discover_cli_source",
]
