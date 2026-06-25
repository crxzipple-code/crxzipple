from __future__ import annotations

from typing import Any, Mapping

from crxzipple.modules.operations.application.read_models.presenters import (
    title_label,
)
from crxzipple.modules.operations.application.read_models.tool_source_common import (
    record_value,
    sequence,
)


def provider_backend_status_label(backend: Any) -> str:
    status = record_value(backend, "status") or "unknown"
    if not bool(getattr(backend, "enabled", True)):
        return "Disabled"
    return title_label(status)


def provider_backend_credential_label(backend: Any) -> str:
    bindings = _provider_backend_credential_bindings(backend)
    if not bindings:
        return "-"
    return ", ".join(bindings)


def provider_backend_readiness_label(
    readiness: Mapping[str, Any] | None,
) -> str:
    if readiness is None:
        return "Unknown"
    if bool(readiness.get("ready")):
        return "Ready"
    status = title_label(readiness.get("status") or "unknown")
    checks = readiness.get("checks")
    if isinstance(checks, list) and checks:
        ready = sum(
            1
            for check in checks
            if isinstance(check, Mapping) and bool(check.get("ready"))
        )
        return f"{status} ({ready}/{len(checks)})"
    return status


def provider_backend_tone(
    backend: Any,
    readiness: Mapping[str, Any] | None,
) -> str:
    status = record_value(backend, "status")
    if status in {"error", "deleted"}:
        return "danger"
    if status == "disabled" or not bool(getattr(backend, "enabled", True)):
        return "warning"
    if readiness is None:
        return "warning"
    return "success" if bool(readiness.get("ready")) else "warning"


def provider_backend_runtime_label(backend: Any) -> str:
    runtime_ref = getattr(backend, "runtime_ref", None)
    if not isinstance(runtime_ref, Mapping):
        return "-"
    runtime_kind = str(runtime_ref.get("runtime_kind") or "").strip()
    ref = str(runtime_ref.get("ref") or "").strip()
    if runtime_kind and ref:
        return f"{runtime_kind}:{ref}"
    return runtime_kind or ref or "-"


def _provider_backend_credential_bindings(backend: Any) -> tuple[str, ...]:
    return tuple(
        binding_id
        for binding_id, _expected_kind in _provider_backend_credential_bindings_with_kind(
            backend,
        )
    )


def _provider_backend_credential_bindings_with_kind(
    backend: Any,
) -> tuple[tuple[str, str | None], ...]:
    pairs: list[tuple[str, str | None]] = []
    for requirement_set in sequence(getattr(backend, "credential_requirements", ())):
        if not isinstance(requirement_set, Mapping):
            continue
        for requirement in sequence(requirement_set.get("requirements")):
            if not isinstance(requirement, Mapping):
                continue
            slot = requirement.get("slot")
            if not isinstance(slot, Mapping):
                continue
            binding_id = str(slot.get("binding_id") or "").strip()
            if not binding_id:
                continue
            expected_kind = str(slot.get("expected_kind") or "").strip() or None
            pairs.append((binding_id, expected_kind))
    return tuple(dict.fromkeys(pairs))
