from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from crxzipple.modules.tool.application.ports import (
    ToolAccessReadinessPort,
    ToolRuntimeReadinessPort,
)
from crxzipple.modules.tool.application.service_support import (
    credential_requirement_sets_from_payload,
)
from crxzipple.modules.tool.domain.entities import Tool, ToolFunction, ToolProviderBackend
from crxzipple.modules.tool.domain.exceptions import (
    ToolExecutionNotAllowedError,
    ToolValidationError,
)
from crxzipple.modules.tool.domain.value_objects import (
    ToolProviderBackendStatus,
    ToolProviderCapability,
)

PROVIDER_BACKEND_POLICY_METADATA_KEY = "provider_backend_policy"
PROVIDER_BACKEND_METADATA_KEY = "provider_backend"


@dataclass(frozen=True, slots=True)
class ToolProviderBackendPolicy:
    capability: ToolProviderCapability
    default_backend_id: str | None = None
    fallback_backend_ids: tuple[str, ...] = ()
    allowed_backend_ids: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"capability": self.capability.value}
        if self.default_backend_id:
            payload["default_backend_id"] = self.default_backend_id
        if self.fallback_backend_ids:
            payload["fallback_backend_ids"] = list(self.fallback_backend_ids)
        if self.allowed_backend_ids:
            payload["allowed_backend_ids"] = list(self.allowed_backend_ids)
        return payload


@dataclass(frozen=True, slots=True)
class ToolProviderBackendResolution:
    backend: ToolProviderBackend
    policy: ToolProviderBackendPolicy

    def to_payload(self) -> dict[str, Any]:
        return {
            "backend_id": self.backend.backend_id,
            "source_id": self.backend.source_id,
            "capability": self.backend.capability.value,
            "display_name": self.backend.display_name,
            "runtime_ref": dict(self.backend.runtime_ref),
            "credential_requirements": [
                dict(requirement)
                for requirement in self.backend.credential_requirements
            ],
            "credential_bindings": _credential_bindings(
                self.backend.credential_requirements,
            ),
            "policy": self.policy.to_payload(),
        }


@dataclass(frozen=True, slots=True)
class ToolProviderBackendReadiness:
    ready: bool
    status: str
    reason: str
    setup_available: bool = False
    checks: tuple[dict[str, Any], ...] = ()
    parts: Mapping[str, dict[str, Any]] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "status": self.status,
            "reason": self.reason,
            "setup_available": self.setup_available,
            "checks": [dict(check) for check in self.checks],
            "parts": {
                category: dict(payload)
                for category, payload in self.parts.items()
            },
        }


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


class ToolProviderBackendReadinessEvaluator:
    def check_backend_readiness(
        self,
        backend: ToolProviderBackend,
        *,
        access_readiness: ToolAccessReadinessPort | None = None,
        runtime_readiness: ToolRuntimeReadinessPort | None = None,
    ) -> ToolProviderBackendReadiness:
        tool = _tool_from_provider_backend(backend)
        access_payload = _backend_access_readiness_payload(
            tool,
            access_readiness=access_readiness,
        )
        runtime_payload = _backend_runtime_readiness_payload(
            tool,
            runtime_readiness=runtime_readiness,
        )
        return _combined_backend_readiness(
            access=access_payload,
            runtime=runtime_payload,
        )


def provider_backend_policy_from_metadata(
    metadata: Mapping[str, Any],
) -> ToolProviderBackendPolicy | None:
    raw_policy = metadata.get(PROVIDER_BACKEND_POLICY_METADATA_KEY)
    if raw_policy in (None, ""):
        return None
    if not isinstance(raw_policy, Mapping):
        raise ToolValidationError("Tool provider backend policy must be a mapping.")
    raw_capability = str(raw_policy.get("capability") or "").strip()
    if not raw_capability:
        raise ToolValidationError(
            "Tool provider backend policy must declare a capability.",
        )
    try:
        capability = ToolProviderCapability(raw_capability)
    except ValueError as exc:
        raise ToolValidationError(
            f"Tool provider backend policy capability '{raw_capability}' is unsupported.",
        ) from exc
    default_backend_id = _optional_text(raw_policy.get("default_backend_id"))
    fallback_backend_ids = _text_tuple(raw_policy.get("fallback_backend_ids"))
    allowed_backend_ids = tuple(
        dict.fromkeys(
            (
                *_text_tuple(raw_policy.get("allowed_backend_ids")),
                *(
                    (default_backend_id,)
                    if default_backend_id is not None
                    else ()
                ),
                *fallback_backend_ids,
            ),
        ),
    )
    return ToolProviderBackendPolicy(
        capability=capability,
        default_backend_id=default_backend_id,
        fallback_backend_ids=fallback_backend_ids,
        allowed_backend_ids=allowed_backend_ids,
    )


def provider_backend_execution_context_payload(
    context_payload: Mapping[str, Any] | None,
    provider_backend_payload: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if not provider_backend_payload:
        return dict(context_payload) if context_payload is not None else None
    payload = dict(context_payload or {})
    payload[PROVIDER_BACKEND_METADATA_KEY] = dict(provider_backend_payload)
    payload["provider_backend_id"] = str(
        provider_backend_payload.get("backend_id") or "",
    ).strip()
    return payload


def _tool_from_provider_backend(backend: ToolProviderBackend) -> Tool:
    return Tool(
        id=backend.backend_id,
        name=backend.display_name,
        description=f"Provider backend {backend.backend_id}",
        credential_requirements=credential_requirement_sets_from_payload(
            backend.credential_requirements,
        ),
        runtime_requirement_sets=_runtime_requirement_sets_from_backend(backend),
        capability_ids=(backend.capability.value,),
        runtime_key=_provider_backend_runtime_key(backend),
        enabled=backend.enabled,
    )


def _backend_access_readiness_payload(
    tool: Tool,
    *,
    access_readiness: ToolAccessReadinessPort | None,
) -> dict[str, Any] | None:
    if access_readiness is not None:
        return _readiness_payload(access_readiness.check_tool_access(tool))
    if tool.credential_requirements or tool.access_requirement_sets:
        return {
            "ready": False,
            "status": "unknown",
            "reason": "Access readiness service is not connected.",
            "setup_available": False,
            "checks": [],
        }
    return None


def _backend_runtime_readiness_payload(
    tool: Tool,
    *,
    runtime_readiness: ToolRuntimeReadinessPort | None,
) -> dict[str, Any] | None:
    if runtime_readiness is not None:
        return _readiness_payload(runtime_readiness.check_tool_runtime(tool))
    if tool.runtime_requirement_sets:
        return {
            "ready": False,
            "status": "unknown",
            "reason": "Runtime readiness service is not connected.",
            "setup_available": False,
            "checks": [],
        }
    return None


def _combined_backend_readiness(
    *,
    access: dict[str, Any] | None,
    runtime: dict[str, Any] | None,
) -> ToolProviderBackendReadiness:
    parts = {
        category: payload
        for category, payload in (("access", access), ("runtime", runtime))
        if payload is not None
    }
    if not parts:
        return ToolProviderBackendReadiness(
            ready=True,
            status="ready",
            reason="No provider backend readiness checks are declared.",
        )

    checks: list[dict[str, Any]] = []
    for category, payload in parts.items():
        raw_checks = payload.get("checks")
        if not isinstance(raw_checks, list):
            continue
        checks.extend(
            {"category": category, **dict(check)}
            for check in raw_checks
            if isinstance(check, Mapping)
        )

    blocked = {
        category: payload
        for category, payload in parts.items()
        if not bool(payload.get("ready"))
    }
    if not blocked:
        return ToolProviderBackendReadiness(
            ready=True,
            status="ready",
            reason="All provider backend readiness checks are ready.",
            setup_available=False,
            checks=tuple(checks),
            parts=parts,
        )

    statuses = tuple(str(payload.get("status") or "") for payload in blocked.values())
    if "unsupported" in statuses:
        status = "unsupported"
    elif "degraded" in statuses:
        status = "degraded"
    elif "unknown" in statuses:
        status = "unknown"
    else:
        status = "setup_needed"
    reasons = tuple(
        dict.fromkeys(
            str(payload.get("reason") or "").strip()
            for payload in blocked.values()
            if str(payload.get("reason") or "").strip()
        ),
    )
    return ToolProviderBackendReadiness(
        ready=False,
        status=status,
        reason="; ".join(reasons) or "Provider backend readiness setup is required.",
        setup_available=any(
            bool(payload.get("setup_available")) for payload in blocked.values()
        ),
        checks=tuple(checks),
        parts=parts,
    )


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


def _runtime_requirement_sets_from_backend(
    backend: ToolProviderBackend,
) -> tuple[tuple[str, ...], ...]:
    values: list[tuple[str, ...]] = []
    for item in _backend_runtime_requirements(backend):
        if isinstance(item, str) and item.strip():
            values.append((item.strip(),))
            continue
        if not isinstance(item, Mapping):
            continue
        raw_requirements = item.get("requirements")
        if isinstance(raw_requirements, list | tuple):
            normalized = tuple(
                dict.fromkeys(
                    str(requirement).strip()
                    for requirement in raw_requirements
                    if str(requirement).strip()
                ),
            )
            if normalized:
                values.append(normalized)
            continue
        raw_requirement = item.get("requirement")
        if isinstance(raw_requirement, str) and raw_requirement.strip():
            values.append((raw_requirement.strip(),))
    return tuple(values)


def _backend_runtime_requirements(backend: ToolProviderBackend) -> tuple[Any, ...]:
    runtime_ref = backend.runtime_ref
    direct = runtime_ref.get("runtime_requirements")
    if isinstance(direct, list | tuple):
        return tuple(direct)
    metadata = runtime_ref.get("metadata")
    if isinstance(metadata, Mapping):
        nested = metadata.get("runtime_requirements")
        if isinstance(nested, list | tuple):
            return tuple(nested)
    return ()


def _provider_backend_runtime_key(backend: ToolProviderBackend) -> str:
    runtime_ref = backend.runtime_ref
    for key in ("ref", "runtime_key", "handler"):
        value = runtime_ref.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return backend.backend_id


def _readiness_payload(readiness: object) -> dict[str, Any]:
    to_payload = getattr(readiness, "to_payload", None)
    if callable(to_payload):
        payload = to_payload()
        if isinstance(payload, Mapping):
            return dict(payload)
    return {}


def _credential_bindings(
    requirement_sets: tuple[dict[str, Any], ...],
) -> dict[str, str]:
    bindings: dict[str, str] = {}
    for requirement_set in requirement_sets:
        raw_requirements = requirement_set.get("requirements")
        if not isinstance(raw_requirements, list | tuple):
            continue
        for requirement in raw_requirements:
            if not isinstance(requirement, Mapping):
                continue
            slot = requirement.get("slot")
            if not isinstance(slot, Mapping):
                continue
            slot_name = _optional_text(slot.get("slot"))
            binding_id = _optional_text(slot.get("binding_id"))
            if slot_name and binding_id:
                bindings[slot_name] = binding_id
    return bindings


def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, tuple | list):
        return tuple(value)
    if value is None:
        return ()
    return (value,)


def _text_tuple(value: object) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            item
            for item in (_optional_text(raw_item) for raw_item in _sequence(value))
            if item
        ),
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
