from __future__ import annotations

from typing import Any

from crxzipple.modules.tool.domain.entities import ToolFunction, ToolProviderBackend
from crxzipple.modules.tool.domain.exceptions import ToolExecutionNotAllowedError
from crxzipple.modules.tool.domain.value_objects import ToolProviderBackendStatus

from .provider_backend_models import (
    ToolProviderBackendPolicy,
    ToolProviderBackendResolution,
)
from .provider_backend_policy import provider_backend_policy_from_metadata


class ToolProviderBackendResolver:
    def resolve_for_function(
        self,
        *,
        function: ToolFunction,
        repository: Any,
    ) -> ToolProviderBackendResolution | None:
        policy = provider_backend_policy_from_metadata(function.metadata)
        if policy is None:
            return None
        backend = _select_backend(
            policy,
            repository=repository,
            function=function,
        )
        return ToolProviderBackendResolution(backend=backend, policy=policy)


def _select_backend(
    policy: ToolProviderBackendPolicy,
    *,
    repository: Any,
    function: ToolFunction,
) -> ToolProviderBackend:
    ordered_backend_ids = tuple(
        dict.fromkeys(
            backend_id
            for backend_id in (
                policy.default_backend_id,
                *policy.fallback_backend_ids,
            )
            if backend_id
        ),
    )
    errors: list[str] = []
    for backend_id in ordered_backend_ids:
        backend = repository.get(backend_id)
        if backend is None:
            errors.append(f"Provider backend '{backend_id}' was not found.")
            continue
        reason = _backend_unavailable_reason(backend, policy=policy)
        if reason is None:
            return backend
        errors.append(reason)

    candidates = tuple(
        backend
        for backend in repository.list(
            capability=policy.capability,
            status=ToolProviderBackendStatus.ACTIVE,
        )
        if backend.enabled
        and (
            not policy.allowed_backend_ids
            or backend.backend_id in policy.allowed_backend_ids
        )
    )
    if not candidates:
        raise _backend_not_available(
            function,
            policy=policy,
            reason=(
                "; ".join(errors)
                or f"No active provider backend is available for {policy.capability.value}."
            ),
        )
    return candidates[0]


def _backend_unavailable_reason(
    backend: ToolProviderBackend,
    *,
    policy: ToolProviderBackendPolicy,
) -> str | None:
    if backend.capability is not policy.capability:
        return (
            f"Provider backend '{backend.backend_id}' capability "
            f"'{backend.capability.value}' does not satisfy "
            f"'{policy.capability.value}'."
        )
    if backend.status is not ToolProviderBackendStatus.ACTIVE:
        return f"Provider backend '{backend.backend_id}' is {backend.status.value}."
    if not backend.enabled:
        return f"Provider backend '{backend.backend_id}' is disabled."
    if policy.allowed_backend_ids and backend.backend_id not in policy.allowed_backend_ids:
        return f"Provider backend '{backend.backend_id}' is not allowed by policy."
    return None


def _backend_not_available(
    function: ToolFunction,
    *,
    policy: ToolProviderBackendPolicy,
    reason: str,
) -> ToolExecutionNotAllowedError:
    return ToolExecutionNotAllowedError(
        f"Tool '{function.function_id}' provider backend is not available: {reason}",
        code="tool_provider_backend_not_available",
        detail={
            "tool_id": function.function_id,
            "function_id": function.function_id,
            "source_id": function.source_id,
            "category": "provider_backend",
            "policy": policy.to_payload(),
            "reason": reason,
        },
    )


__all__ = ["ToolProviderBackendResolver"]
