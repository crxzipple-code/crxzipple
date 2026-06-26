from __future__ import annotations

from typing import Any

from crxzipple.modules.tool.application import (
    ToolFunctionCatalogRecord,
    ToolSourceCatalogRecord,
    ToolSourceDiscoveryRunRecord,
    ToolSourceSyncResult,
)
from crxzipple.modules.tool.interfaces.dto import _credential_requirement_set_payload
from crxzipple.modules.tool.interfaces.http_models import (
    ToolExecutionPolicyResponse,
    ToolExecutionSupportResponse,
    ToolExecutionTargetResponse,
    ToolFunctionResponse,
    ToolParameterResponse,
    ToolProviderBackendResponse,
    ToolResponse,
    ToolRunErrorResponse,
    ToolRunResponse,
    ToolRunResultResponse,
    ToolSourceDiscoveryRunResponse,
    ToolSourceResponse,
    ToolSourceSyncResponse,
    ToolSourceWriteRequest,
)
from crxzipple.shared.time import (
    format_datetime_utc,
    format_optional_datetime_utc,
)


def tool_response(tool: Any) -> ToolResponse:
    return ToolResponse(
        id=tool.id,
        source_id=tool.source_id,
        name=tool.name,
        description=tool.description,
        kind=tool.kind.value,
        parameters=[
            ToolParameterResponse(
                name=parameter.name,
                data_type=parameter.data_type,
                description=parameter.description,
                required=parameter.required,
            )
            for parameter in tool.parameters
        ],
        tags=list(tool.tags),
        required_effect_ids=list(tool.required_effect_ids),
        access_requirements=list(tool.access_requirements),
        access_requirement_sets=[
            list(requirement_set)
            for requirement_set in tool.access_requirement_sets
        ],
        runtime_requirement_sets=[
            list(requirement_set)
            for requirement_set in tool.runtime_requirement_sets
        ],
        context_requirements=list(tool.context_requirements),
        credential_requirements=[
            _credential_requirement_set_payload(requirement_set)
            for requirement_set in tool.credential_requirements
        ],
        execution_policy=ToolExecutionPolicyResponse(
            timeout_seconds=tool.execution_policy.timeout_seconds,
            requires_confirmation=tool.execution_policy.requires_confirmation,
            mutates_state=tool.execution_policy.mutates_state,
            supports_parallel=tool.execution_policy.supports_parallel,
            resource_scope=tool.execution_policy.resource_scope,
            serial_group_key=tool.execution_policy.serial_group_key,
        ),
        execution_support=ToolExecutionSupportResponse(
            supported_modes=[
                mode.value for mode in tool.execution_support.supported_modes
            ],
            supported_strategies=[
                strategy.value
                for strategy in tool.execution_support.supported_strategies
            ],
            supported_environments=[
                environment.value
                for environment in tool.execution_support.supported_environments
            ],
        ),
        definition_origin=tool.definition_origin.value,
        runtime_key=tool.runtime_key,
        enabled=tool.enabled,
    )


def tool_source_response(source: ToolSourceCatalogRecord) -> ToolSourceResponse:
    return ToolSourceResponse(
        source_id=source.source_id,
        kind=source.kind.value,
        display_name=source.display_name,
        description=source.description,
        config=dict(source.config),
        credential_requirements=[
            _source_credential_requirement_payload(requirement)
            for requirement in source.credential_requirements
        ],
        runtime_requirements=list(source.runtime_requirements),
        status=source.status.value,
        revision=source.revision,
        config_hash=source.config_hash,
        last_discovered_at=format_optional_datetime_utc(source.last_discovered_at),
        last_discovery_status=(
            source.last_discovery_status.value
            if source.last_discovery_status is not None
            else None
        ),
        created_at=format_optional_datetime_utc(source.created_at),
        updated_at=format_optional_datetime_utc(source.updated_at),
    )


def tool_source_record_from_request(
    payload: ToolSourceWriteRequest,
) -> ToolSourceCatalogRecord:
    return ToolSourceCatalogRecord(
        source_id=payload.source_id,
        kind=payload.kind,
        display_name=payload.display_name,
        description=payload.description,
        config=payload.config,
        credential_requirements=tuple(payload.credential_requirements),  # type: ignore[arg-type]
        runtime_requirements=tuple(payload.runtime_requirements),
        status=payload.status,
    )


def tool_function_response(
    function: ToolFunctionCatalogRecord,
) -> ToolFunctionResponse:
    return ToolFunctionResponse(
        function_id=function.function_id,
        source_id=function.source_id,
        stable_key=function.stable_key,
        name=function.name,
        description=function.description,
        input_schema=dict(function.input_schema),
        runtime_kind=function.runtime_kind.value,
        handler_ref=function.handler_ref,
        capabilities=list(function.capabilities),
        kind=_function_kind(function),
        parameters=_function_parameters(function.input_schema),
        tags=_function_tags(function),
        required_effect_ids=list(
            function.required_effect_overrides
            if function.required_effect_overrides is not None
            else function.requirements.required_effect_ids,
        ),
        access_requirement_sets=[
            list(requirement_set)
            for requirement_set in function.requirements.access_requirement_sets
        ],
        runtime_requirement_sets=[
            list(requirement_set)
            for requirement_set in function.requirements.runtime_requirement_sets
        ],
        context_requirements=_function_context_requirements(function),
        credential_requirements=[
            _credential_requirement_set_payload(requirement_set)
            for requirement_set in function.requirements.credential_requirements
        ],
        execution_policy=_function_execution_policy(function),
        execution_support=_function_execution_support(function),
        definition_origin=_function_definition_origin(function),
        runtime_key=_function_runtime_key(function),
        schema_hash=function.schema_hash,
        status=function.status.value,
        enabled=function.enabled,
        revision=function.revision,
        trust_policy=dict(function.trust_policy),
        approval_policy=dict(function.approval_policy),
        credential_binding_overrides=dict(function.credential_binding_overrides),
        required_effect_overrides=(
            list(function.required_effect_overrides)
            if function.required_effect_overrides is not None
            else None
        ),
        metadata=dict(function.metadata),
        created_at=format_optional_datetime_utc(function.created_at),
        updated_at=format_optional_datetime_utc(function.updated_at),
        last_seen_at=format_optional_datetime_utc(function.last_seen_at),
        stale_since=format_optional_datetime_utc(function.stale_since),
        deprecated_at=format_optional_datetime_utc(function.deprecated_at),
    )


def tool_provider_backend_response(
    backend: Any,
    *,
    readiness: dict[str, Any] | None = None,
) -> ToolProviderBackendResponse:
    return ToolProviderBackendResponse(
        backend_id=backend.backend_id,
        source_id=backend.source_id,
        capability=backend.capability.value,
        display_name=backend.display_name,
        credential_requirements=[
            dict(requirement)
            for requirement in backend.credential_requirements
        ],
        runtime_ref=dict(backend.runtime_ref),
        priority=backend.priority,
        enabled=backend.enabled,
        status=backend.status.value,
        readiness=readiness,
        created_at=format_datetime_utc(backend.created_at),
        updated_at=format_datetime_utc(backend.updated_at),
    )


def provider_backend_readiness_payload(service: Any, backend: Any) -> dict[str, Any] | None:
    check_readiness = getattr(service, "check_provider_backend_readiness", None)
    if not callable(check_readiness):
        return None
    readiness = check_readiness(backend)
    to_payload = getattr(readiness, "to_payload", None)
    if callable(to_payload):
        payload = to_payload()
        if isinstance(payload, dict):
            return payload
    return None


def tool_discovery_run_response(
    run: ToolSourceDiscoveryRunRecord,
) -> ToolSourceDiscoveryRunResponse:
    return ToolSourceDiscoveryRunResponse(
        discovery_run_id=run.discovery_run_id,
        source_id=run.source_id,
        source_revision=run.source_revision,
        config_hash=run.config_hash,
        status=run.status.value,
        discovered_at=format_datetime_utc(run.discovered_at),
        function_count=run.function_count,
        provider_backend_count=run.provider_backend_count,
        error_message=run.error_message,
        metadata=dict(run.metadata),
    )


def tool_source_sync_response(result: ToolSourceSyncResult) -> ToolSourceSyncResponse:
    discovery = None
    if result.discovery is not None:
        discovery = ToolSourceDiscoveryRunResponse(
            discovery_run_id="",
            source_id=result.discovery.source_id,
            source_revision=result.source.revision,
            config_hash=result.source.config_hash,
            status=result.discovery.status.value,
            discovered_at=format_datetime_utc(result.discovery.discovered_at),
            function_count=len(result.discovery.candidates),
            provider_backend_count=len(result.discovery.provider_backend_candidates),
            error_message=result.discovery.error_message,
            metadata=dict(result.discovery.metadata),
        )
    return ToolSourceSyncResponse(
        source=tool_source_response(result.source),
        skipped=result.skipped,
        error_message=result.error_message,
        discovery=discovery,
    )


def tool_run_response(tool_run: Any) -> ToolRunResponse:
    return ToolRunResponse(
        id=tool_run.id,
        tool_id=tool_run.tool_id,
        call_id=tool_run.call_id,
        tool_surface_id=tool_run.tool_surface_id,
        function_id=tool_run.function_id,
        function_revision=tool_run.function_revision,
        source_id=tool_run.source_id,
        source_revision=tool_run.source_revision,
        schema_hash=tool_run.schema_hash,
        target=ToolExecutionTargetResponse(
            mode=tool_run.target.mode.value,
            strategy=tool_run.target.strategy.value,
            environment=tool_run.target.environment.value,
        ),
        status=tool_run.status.value,
        input_payload=dict(tool_run.input_payload),
        metadata=dict(tool_run.metadata),
        result=(
            ToolRunResultResponse(
                content=[dict(block) for block in tool_run.result.blocks],
                details=tool_run.result.details,
                metadata=dict(tool_run.result.metadata),
            )
            if tool_run.result is not None
            else None
        ),
        error=(
            ToolRunErrorResponse(
                message=tool_run.error.message,
                code=tool_run.error.code,
                details=dict(tool_run.error.details),
            )
            if tool_run.error is not None
            else None
        ),
        output_payload=tool_run.output_payload,
        result_envelope_payload=(
            dict(tool_run.result_envelope_payload)
            if tool_run.result_envelope_payload is not None
            else None
        ),
        error_message=tool_run.error_message,
        created_at=format_datetime_utc(tool_run.created_at),
        started_at=format_optional_datetime_utc(tool_run.started_at),
        completed_at=format_optional_datetime_utc(tool_run.completed_at),
        attempt_count=tool_run.attempt_count,
        max_attempts=tool_run.max_attempts,
        worker_id=tool_run.worker_id,
        heartbeat_at=format_optional_datetime_utc(tool_run.heartbeat_at),
        lease_expires_at=format_optional_datetime_utc(
            tool_run.lease_expires_at,
        ),
        cancel_requested_at=format_optional_datetime_utc(
            tool_run.cancel_requested_at,
        ),
    )


def _source_credential_requirement_payload(requirement: object) -> dict[str, Any]:
    if isinstance(requirement, dict):
        return dict(requirement)
    return _credential_requirement_set_payload(requirement)  # type: ignore[arg-type]


def _function_kind(function: ToolFunctionCatalogRecord) -> str:
    return str(function.metadata.get("tool_kind") or "function")


def _function_tags(function: ToolFunctionCatalogRecord) -> list[str]:
    raw_tags = function.metadata.get("tags")
    if not isinstance(raw_tags, list | tuple):
        return []
    return [str(tag).strip() for tag in raw_tags if str(tag).strip()]


def _function_context_requirements(function: ToolFunctionCatalogRecord) -> list[str]:
    raw_values = function.metadata.get("context_requirements")
    if not isinstance(raw_values, list | tuple):
        return []
    return [str(value).strip() for value in raw_values if str(value).strip()]


def _function_parameters(input_schema: dict[str, Any]) -> list[ToolParameterResponse]:
    raw_properties = input_schema.get("properties")
    properties = raw_properties if isinstance(raw_properties, dict) else {}
    raw_required = input_schema.get("required")
    required = (
        {str(item).strip() for item in raw_required if str(item).strip()}
        if isinstance(raw_required, list | tuple)
        else set()
    )
    parameters: list[ToolParameterResponse] = []
    for name, raw_schema in properties.items():
        if not isinstance(name, str) or not name.strip():
            continue
        schema = raw_schema if isinstance(raw_schema, dict) else {}
        data_type = schema.get("x-crxzipple-data-type") or schema.get("type")
        parameters.append(
            ToolParameterResponse(
                name=name,
                data_type=str(data_type or "string"),
                description=str(schema.get("description") or ""),
                required=name in required,
            ),
        )
    return parameters


def _function_execution_policy(
    function: ToolFunctionCatalogRecord,
) -> ToolExecutionPolicyResponse:
    raw_policy = function.metadata.get("execution_policy")
    policy = raw_policy if isinstance(raw_policy, dict) else {}
    return ToolExecutionPolicyResponse(
        timeout_seconds=max(_optional_int(policy.get("timeout_seconds"), 30), 1),
        requires_confirmation=bool(policy.get("requires_confirmation", False)),
        mutates_state=bool(policy.get("mutates_state", False)),
        supports_parallel=bool(policy.get("supports_parallel", True)),
        resource_scope=_optional_policy_text(policy.get("resource_scope")),
        serial_group_key=_optional_policy_text(policy.get("serial_group_key")),
    )


def _function_execution_support(
    function: ToolFunctionCatalogRecord,
) -> ToolExecutionSupportResponse:
    raw_support = function.metadata.get("execution_support")
    support = raw_support if isinstance(raw_support, dict) else {}
    return ToolExecutionSupportResponse(
        supported_modes=_metadata_string_list(
            support.get("supported_modes"),
            fallback=("inline",),
        ),
        supported_strategies=_metadata_string_list(
            support.get("supported_strategies"),
            fallback=("async",),
        ),
        supported_environments=_metadata_string_list(
            support.get("supported_environments"),
            fallback=("local",),
        ),
    )


def _metadata_string_list(value: object, *, fallback: tuple[str, ...]) -> list[str]:
    if not isinstance(value, list | tuple):
        return list(fallback)
    normalized = [str(item).strip() for item in value if str(item).strip()]
    return list(dict.fromkeys(normalized)) or list(fallback)


def _optional_int(value: object, default: int) -> int:
    try:
        return int(value) if value is not None and value != "" else default
    except (TypeError, ValueError):
        return default


def _optional_policy_text(value: object | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _function_definition_origin(function: ToolFunctionCatalogRecord) -> str:
    return str(function.metadata.get("definition_origin") or "local_discovery")


def _function_runtime_key(function: ToolFunctionCatalogRecord) -> str | None:
    runtime_key = function.metadata.get("runtime_key")
    if isinstance(runtime_key, str) and runtime_key.strip():
        return runtime_key.strip()
    handler_ref = function.handler_ref.strip()
    return handler_ref or None
