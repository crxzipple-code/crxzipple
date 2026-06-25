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
    ToolExecutionPolicy,
    ToolExecutionStrategy,
    ToolExecutionSupport,
    ToolMode,
    ToolParameter,
)
from crxzipple.modules.tool.infrastructure.cli_source_config import (
    CliPromotedFunctionConfig,
    CliToolSourceConfig,
)
from crxzipple.modules.tool.infrastructure.cli_source_config_values import safe_tool_id
from crxzipple.shared.access import (
    AccessConsumerRef,
    AccessCredentialRequirementDeclaration,
    AccessCredentialRequirementSet,
    AccessCredentialSlotRef,
    AccessCredentialTransport,
)


GUIDED_CLI_ACTIONS: tuple[str, ...] = (
    "cli_help",
    "cli_execute",
    "cli_read_output",
    "cli_cancel",
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
        name=_guided_cli_name(config, action),
        description=_guided_cli_description(config, action),
        provider_name=config.provider_name,
        parameters=_guided_cli_parameters(action),
        tags=("cli", "guided", config.provider_name),
        required_effect_ids=_guided_cli_effects(config, action),
        runtime_requirement_sets=((config.source_marker,),),
        execution_policy=_guided_cli_policy(config, action),
        execution_support=ToolExecutionSupport(
            supported_modes=(ToolMode.INLINE,),
            supported_strategies=(ToolExecutionStrategy.ASYNC,),
            supported_environments=(ToolEnvironment.REMOTE,),
        ),
        definition_origin=ToolDefinitionOrigin.REMOTE_DISCOVERY,
        runtime_key=f"cli.{safe_tool_id(source.source_id)}.{action}",
        credential_requirements=_guided_cli_credential_requirements(
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
        required_effect_ids=_promoted_cli_effects(config, promoted),
        runtime_requirement_sets=((config.source_marker,),),
        execution_policy=_promoted_cli_policy(config, promoted),
        execution_support=ToolExecutionSupport(
            supported_modes=(ToolMode.INLINE,),
            supported_strategies=(ToolExecutionStrategy.ASYNC,),
            supported_environments=(ToolEnvironment.REMOTE,),
        ),
        definition_origin=ToolDefinitionOrigin.REMOTE_DISCOVERY,
        runtime_key=f"cli.{safe_source_id}.promoted.{safe_function_id}",
        credential_requirements=_promoted_cli_credential_requirements(
            source,
            config,
            promoted,
        ),
    )


def _guided_cli_name(config: CliToolSourceConfig, action: str) -> str:
    label = action.removeprefix("cli_").replace("_", " ").title()
    return f"{config.provider_name} {label}"


def _guided_cli_description(config: CliToolSourceConfig, action: str) -> str:
    if action == "cli_help":
        return f"Read help output from configured CLI source '{config.provider_name}'."
    if action == "cli_execute":
        return f"Start a governed command for configured CLI source '{config.provider_name}'."
    if action == "cli_read_output":
        return f"Read stdout/stderr from a governed CLI process for '{config.provider_name}'."
    if action == "cli_cancel":
        return f"Cancel a governed CLI process for '{config.provider_name}'."
    return f"Run guided CLI action '{action}' for '{config.provider_name}'."


def _guided_cli_parameters(action: str) -> tuple[ToolParameter, ...]:
    if action == "cli_help":
        return (
            ToolParameter(
                name="subcommand",
                data_type="string",
                description="Optional allowed subcommand to inspect.",
                required=False,
            ),
        )
    if action == "cli_execute":
        return (
            ToolParameter(
                name="subcommand",
                data_type="string",
                description="Allowed subcommand to execute.",
            ),
            ToolParameter(
                name="args",
                data_type="array[string]",
                description="Additional argv entries allowed by source policy.",
                required=False,
            ),
            ToolParameter(
                name="session_key",
                data_type="string",
                description="Optional caller correlation key for the process session.",
                required=False,
            ),
            ToolParameter(
                name="initial_output_limit",
                data_type="integer",
                description="Initial stdout/stderr bytes to read after spawning.",
                required=False,
            ),
        )
    if action == "cli_read_output":
        return (
            ToolParameter(name="process_id", data_type="string", description="Process session id."),
            ToolParameter(name="stdout_offset", data_type="integer", required=False),
            ToolParameter(name="stderr_offset", data_type="integer", required=False),
            ToolParameter(name="limit", data_type="integer", required=False),
        )
    if action == "cli_cancel":
        return (
            ToolParameter(name="process_id", data_type="string", description="Process session id."),
        )
    return ()


def _guided_cli_effects(
    config: CliToolSourceConfig,
    action: str,
) -> tuple[str, ...]:
    if action == "cli_execute" and config.mutating_subcommands:
        return ("tool.cli.mutate",)
    if action == "cli_cancel":
        return ("tool.cli.cancel",)
    return ()


def _guided_cli_policy(
    config: CliToolSourceConfig,
    action: str,
) -> ToolExecutionPolicy:
    mutates = action == "cli_execute" and bool(config.mutating_subcommands)
    return ToolExecutionPolicy(
        timeout_seconds=config.timeout_seconds,
        requires_confirmation=mutates or action == "cli_cancel",
        mutates_state=mutates or action == "cli_cancel",
    )


def _promoted_cli_effects(
    config: CliToolSourceConfig,
    promoted: CliPromotedFunctionConfig,
) -> tuple[str, ...]:
    if promoted.required_effect_ids:
        return promoted.required_effect_ids
    if promoted.mutates_state or promoted.subcommand in config.mutating_subcommands:
        return ("tool.cli.mutate",)
    return ()


def _promoted_cli_policy(
    config: CliToolSourceConfig,
    promoted: CliPromotedFunctionConfig,
) -> ToolExecutionPolicy:
    mutates = promoted.mutates_state or promoted.subcommand in config.mutating_subcommands
    return ToolExecutionPolicy(
        timeout_seconds=config.timeout_seconds,
        requires_confirmation=mutates,
        mutates_state=mutates,
    )


def _guided_cli_credential_requirements(
    source: ToolSourceCatalogRecord,
    config: CliToolSourceConfig,
    action: str,
) -> tuple[AccessCredentialRequirementSet, ...]:
    if action != "cli_execute" or not config.credential_bindings:
        return ()
    return _cli_credential_requirements(
        source,
        config,
        action=action,
        runtime_ref=f"cli.{source.source_id}.{action}",
        requirement_set_id=f"{source.source_id}.{action}.credentials",
    )


def _promoted_cli_credential_requirements(
    source: ToolSourceCatalogRecord,
    config: CliToolSourceConfig,
    promoted: CliPromotedFunctionConfig,
) -> tuple[AccessCredentialRequirementSet, ...]:
    if not config.credential_bindings:
        return ()
    return _cli_credential_requirements(
        source,
        config,
        action="cli_promoted_execute",
        runtime_ref=f"cli.{source.source_id}.promoted.{promoted.function_id}",
        requirement_set_id=(
            f"{source.source_id}.promoted.{promoted.function_id}.credentials"
        ),
    )


def _cli_credential_requirements(
    source: ToolSourceCatalogRecord,
    config: CliToolSourceConfig,
    *,
    action: str,
    runtime_ref: str,
    requirement_set_id: str,
) -> tuple[AccessCredentialRequirementSet, ...]:
    consumer = AccessConsumerRef(
        consumer_id=f"tool.cli_source:{source.source_id}:{action}",
        module="tool",
        component="cli_source",
        runtime_ref=runtime_ref,
        metadata={
            "provider": config.provider_name,
            "source_id": source.source_id,
        },
    )
    requirements = tuple(
        AccessCredentialRequirementDeclaration(
            requirement_id=f"{source.source_id}.{binding.slot or binding.binding_id}",
            consumer=consumer,
            slot=AccessCredentialSlotRef(
                slot=binding.slot or binding.binding_id,
                expected_kind=binding.expected_kind,
                binding_id=binding.binding_id,
                display_name=binding.display_name,
            ),
            provider=binding.provider,
            transport=AccessCredentialTransport.RUNTIME_CONTEXT,
            parameter_name=binding.env_name or binding.file_env_name,
            metadata={
                "injection": binding.injection,
                "env_name": binding.env_name,
                "file_env_name": binding.file_env_name,
            },
        )
        for binding in config.credential_bindings
    )
    return (
        AccessCredentialRequirementSet(
            requirement_set_id=requirement_set_id,
            consumer=consumer,
            requirements=requirements,
        ),
    )


__all__ = [
    "GUIDED_CLI_ACTIONS",
    "discover_cli_source",
]
