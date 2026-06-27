from __future__ import annotations

from typing import Any, Mapping

from crxzipple.modules.tool.application.ports import (
    ToolAccessReadinessPort,
    ToolRuntimeReadinessPort,
)
from crxzipple.modules.tool.application.service_support import (
    credential_requirement_sets_from_payload,
)
from crxzipple.modules.tool.domain.entities import Tool, ToolProviderBackend

from .provider_backend_models import ToolProviderBackendReadiness


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


__all__ = ["ToolProviderBackendReadinessEvaluator"]
