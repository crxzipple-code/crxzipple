from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from crxzipple.modules.tool.application.ports import (
    ToolAccessReadiness,
    ToolAccessReadinessCheck,
    ToolAccessReadinessPort,
)
from crxzipple.modules.tool.domain.entities import Tool
from crxzipple.shared.access import (
    AccessCredentialRequirementDeclaration,
    AccessCredentialRequirementSet,
    AccessSetupFlowHint,
)


@dataclass(slots=True)
class AccessServiceToolReadinessAdapter(ToolAccessReadinessPort):
    access_service: Any

    def check_tool_access(
        self,
        tool: Tool,
    ) -> ToolAccessReadiness:
        credential_sets = tuple(tool.credential_requirements)
        if credential_sets:
            return _readiness_from_credential_sets(
                credential_sets,
                access_service=self.access_service,
                tool=tool,
            )
        requirement_sets = tuple(
            tuple(requirement for requirement in item if requirement.strip())
            for item in tool.access_requirement_sets
            if item
        )
        if requirement_sets:
            return _readiness_from_access_requirement_sets(
                requirement_sets,
                access_service=self.access_service,
                tool=tool,
            )
        return ToolAccessReadiness(
            ready=True,
            status="ready",
            reason="No access requirements are declared.",
        )


def _readiness_from_credential_sets(
    credential_sets: tuple[AccessCredentialRequirementSet, ...],
    *,
    access_service: Any,
    tool: Tool,
) -> ToolAccessReadiness:
    checked_sets: list[tuple[ToolAccessReadinessCheck, ...]] = []
    for requirement_set in credential_sets:
        checks = tuple(
            _credential_requirement_check(
                requirement,
                access_service=access_service,
            )
            for requirement in requirement_set.requirements
        )
        checked_sets.append(checks)
        if checks and all(check.ready for check in checks):
            return ToolAccessReadiness(
                ready=True,
                status="ready",
                reason="All credential requirements are ready.",
                checks=tuple(check for check_set in checked_sets for check in check_set),
            )
    return _blocked_readiness(tool=tool, checked_sets=checked_sets)


def _credential_requirement_check(
    requirement: AccessCredentialRequirementDeclaration,
    *,
    access_service: Any,
) -> ToolAccessReadinessCheck:
    binding_id = requirement.slot.binding_id
    expected_kind = requirement.slot.expected_kind.value
    if not binding_id:
        ready = not requirement.slot.required
        return ToolAccessReadinessCheck(
            requirement=requirement.slot.slot,
            requirement_id=requirement.requirement_id,
            binding_id=None,
            expected_kind=expected_kind,
            ready=ready,
            status="ready" if ready else "setup_needed",
            reason=(
                "Optional credential binding is not configured."
                if ready
                else "Credential binding is not configured."
            ),
            setup_available=_setup_hint_available(requirement.setup_flow_hint),
            setup_flow=_setup_hint_payload(requirement.setup_flow_hint),
        )
    readiness = access_service.check_credential_binding(
        binding_id,
        expected_kind=expected_kind,
    )
    return _check_from_access_readiness(
        readiness,
        requirement_id=requirement.requirement_id,
        binding_id=binding_id,
        expected_kind=expected_kind,
    )


def _readiness_from_access_requirement_sets(
    requirement_sets: tuple[tuple[str, ...], ...],
    *,
    access_service: Any,
    tool: Tool,
) -> ToolAccessReadiness:
    checked_sets: list[tuple[ToolAccessReadinessCheck, ...]] = []
    for requirement_set in requirement_sets:
        checks = tuple(
            _check_from_access_readiness(readiness)
            for readiness in access_service.check_requirements(
                requirement_set,
            )
        )
        checked_sets.append(checks)
        if checks and all(check.ready for check in checks):
            return ToolAccessReadiness(
                ready=True,
                status="ready",
                reason="All access requirements are ready.",
                checks=tuple(check for check_set in checked_sets for check in check_set),
            )
    return _blocked_readiness(tool=tool, checked_sets=checked_sets)


def _blocked_readiness(
    *,
    tool: Tool,
    checked_sets: list[tuple[ToolAccessReadinessCheck, ...]],
) -> ToolAccessReadiness:
    checks = tuple(check for check_set in checked_sets for check in check_set)
    if not checks:
        return ToolAccessReadiness(
            ready=False,
            status="setup_needed",
            reason=f"Tool '{tool.id}' declares access requirements but none were checkable.",
        )
    reasons = tuple(
        dict.fromkeys(check.reason for check in checks if not check.ready and check.reason)
    )
    unsupported = any(check.status == "unsupported" for check in checks if not check.ready)
    mismatch = next(
        (
            check.status
            for check in checks
            if not check.ready and "mismatch" in check.status
        ),
        None,
    )
    return ToolAccessReadiness(
        ready=False,
        status=mismatch or ("unsupported" if unsupported else "setup_needed"),
        reason="; ".join(reasons) or "Tool access setup is required.",
        checks=checks,
    )


def _check_from_access_readiness(
    readiness: Any,
    *,
    requirement_id: str | None = None,
    binding_id: str | None = None,
    expected_kind: str | None = None,
) -> ToolAccessReadinessCheck:
    payload = _payload(readiness)
    status = _readiness_status(readiness, payload)
    requirement = str(payload.get("requirement") or binding_id or "").strip()
    return ToolAccessReadinessCheck(
        requirement=requirement or "-",
        requirement_id=requirement_id,
        binding_id=binding_id,
        expected_kind=expected_kind,
        ready=bool(payload.get("ready", getattr(readiness, "ready", False))),
        status=status,
        reason=str(payload.get("reason") or getattr(readiness, "reason", "") or status),
        setup_available=bool(
            payload.get("setup_available", getattr(readiness, "setup_available", False)),
        ),
        setup_flow=_mapping_or_none(payload.get("setup_flow")),
        metadata={"access_status": status},
    )


def _payload(readiness: Any) -> dict[str, Any]:
    to_payload = getattr(readiness, "to_payload", None)
    if callable(to_payload):
        payload = to_payload()
        if isinstance(payload, dict):
            return dict(payload)
    return {}


def _readiness_status(readiness: Any, payload: Mapping[str, Any]) -> str:
    status = payload.get("status")
    if isinstance(status, str) and status.strip():
        return status.strip()
    raw_status = getattr(readiness, "status", None)
    value = getattr(raw_status, "value", None)
    if isinstance(value, str) and value.strip():
        return value.strip()
    normalized = str(raw_status or "").strip()
    return normalized or "unknown"


def _setup_hint_available(hint: AccessSetupFlowHint) -> bool:
    return hint.flow_kind.value not in {"none", ""}


def _setup_hint_payload(hint: AccessSetupFlowHint) -> dict[str, Any] | None:
    if not _setup_hint_available(hint):
        return None
    payload: dict[str, Any] = {"kind": hint.flow_kind.value}
    for key in (
        "provider",
        "authorization_url",
        "token_url",
        "device_code_url",
        "callback_url",
    ):
        value = getattr(hint, key)
        if value:
            payload[key] = value
    if hint.metadata:
        payload["metadata"] = dict(hint.metadata)
    return payload


def _mapping_or_none(value: Any) -> Mapping[str, Any] | None:
    return dict(value) if isinstance(value, Mapping) else None
