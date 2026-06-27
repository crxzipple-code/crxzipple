from __future__ import annotations

from crxzipple.modules.tool.application.catalog_models import ToolSourceCatalogRecord
from crxzipple.modules.tool.infrastructure.cli_source_config import (
    CliPromotedFunctionConfig,
    CliToolSourceConfig,
)
from crxzipple.shared.access import (
    AccessConsumerRef,
    AccessCredentialRequirementDeclaration,
    AccessCredentialRequirementSet,
    AccessCredentialSlotRef,
    AccessCredentialTransport,
)


def guided_cli_credential_requirements(
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


def promoted_cli_credential_requirements(
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
    "guided_cli_credential_requirements",
    "promoted_cli_credential_requirements",
]
