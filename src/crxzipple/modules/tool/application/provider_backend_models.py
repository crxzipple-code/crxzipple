from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from crxzipple.modules.tool.domain.entities import ToolProviderBackend
from crxzipple.modules.tool.domain.value_objects import ToolProviderCapability


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


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


__all__ = [
    "PROVIDER_BACKEND_METADATA_KEY",
    "PROVIDER_BACKEND_POLICY_METADATA_KEY",
    "ToolProviderBackendPolicy",
    "ToolProviderBackendReadiness",
    "ToolProviderBackendResolution",
]
