from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from crxzipple.modules.tool.application.ports import (
    ToolRuntimeReadiness,
    ToolRuntimeReadinessCheck,
    ToolRuntimeReadinessPort,
)
from crxzipple.modules.tool.domain.entities import Tool


@dataclass(slots=True)
class DaemonServiceToolRuntimeReadinessAdapter(ToolRuntimeReadinessPort):
    daemon_service: Any
    access_service: Any | None = None

    def check_tool_runtime(
        self,
        tool: Tool,
        *,
        workspace_dir: str | None = None,
    ) -> ToolRuntimeReadiness:
        del workspace_dir
        requirement_sets = tuple(
            tuple(requirement for requirement in item if requirement.strip())
            for item in tool.runtime_requirement_sets
            if item
        )
        if not requirement_sets:
            return ToolRuntimeReadiness(
                ready=True,
                status="ready",
                reason="No runtime requirements are declared.",
            )

        checked_sets: list[tuple[ToolRuntimeReadinessCheck, ...]] = []
        for requirement_set in requirement_sets:
            checks = tuple(self._check_requirement(requirement) for requirement in requirement_set)
            checked_sets.append(checks)
            if checks and all(check.ready for check in checks):
                return ToolRuntimeReadiness(
                    ready=True,
                    status="ready",
                    reason="All runtime requirements are ready.",
                    checks=tuple(check for check_set in checked_sets for check in check_set),
                )
        return _blocked_readiness(tool=tool, checked_sets=checked_sets)

    def _check_requirement(self, requirement: str) -> ToolRuntimeReadinessCheck:
        normalized = requirement.strip()
        if not normalized:
            return ToolRuntimeReadinessCheck(
                requirement=requirement,
                status="unsupported",
                ready=False,
                reason="Runtime requirement is empty.",
            )
        if normalized.startswith("daemon-group:"):
            service_group = normalized.removeprefix("daemon-group:").strip()
            return self._check_daemon_service_group(
                normalized,
                service_group=service_group,
            )
        if normalized == "browser-profile-runtime":
            return self._check_daemon_service_group(
                normalized,
                service_group="browser",
            )
        if normalized.startswith("cli:"):
            source_id = normalized.removeprefix("cli:").strip()
            return ToolRuntimeReadinessCheck(
                requirement=normalized,
                status="ready",
                ready=True,
                reason="CLI source runtime is activated inside the Tool runtime registry.",
                metadata={"source_id": source_id},
            )
        if not normalized.startswith("daemon:"):
            return ToolRuntimeReadinessCheck(
                requirement=normalized,
                status="unsupported",
                ready=False,
                reason=f"Unsupported runtime requirement '{normalized}'.",
            )
        service_key = normalized.removeprefix("daemon:").strip()
        if not service_key:
            return ToolRuntimeReadinessCheck(
                requirement=normalized,
                status="unsupported",
                ready=False,
                reason="Daemon runtime requirement has no service key.",
            )
        return self._check_daemon_service(normalized, service_key=service_key)

    def _check_daemon_service_group(
        self,
        requirement: str,
        *,
        service_group: str,
    ) -> ToolRuntimeReadinessCheck:
        if not service_group:
            return ToolRuntimeReadinessCheck(
                requirement=requirement,
                status="unsupported",
                ready=False,
                reason="Daemon runtime group requirement has no service group.",
            )
        try:
            specs = tuple(
                self.daemon_service.list_service_specs(service_group=service_group),
            )
        except Exception as exc:
            return ToolRuntimeReadinessCheck(
                requirement=requirement,
                status="degraded",
                ready=False,
                reason=f"Daemon service group '{service_group}' could not be inspected: {exc}",
                metadata={"service_group": service_group},
            )
        if not specs:
            return ToolRuntimeReadinessCheck(
                requirement=requirement,
                status="unsupported",
                ready=False,
                reason=f"Daemon service group '{service_group}' is not registered.",
                metadata={"service_group": service_group},
            )
        instances: list[Any] = []
        for spec in specs:
            try:
                instances.extend(self.daemon_service.list_instances(service_key=spec.key))
            except Exception as exc:
                return ToolRuntimeReadinessCheck(
                    requirement=requirement,
                    status="degraded",
                    ready=False,
                    reason=f"Daemon service '{spec.key}' could not be inspected: {exc}",
                    metadata={"service_group": service_group, "service_key": spec.key},
                )
        ready_instances = tuple(instance for instance in instances if instance.status == "ready")
        if ready_instances:
            return ToolRuntimeReadinessCheck(
                requirement=requirement,
                status="ready",
                ready=True,
                reason=f"Daemon service group '{service_group}' has a ready instance.",
                metadata=_daemon_group_metadata(
                    service_group,
                    specs,
                    tuple(instances),
                ),
            )
        proxy_readiness = _browser_proxy_readiness(
            specs,
            access_service=self.access_service,
        )
        proxy_blockers = tuple(item for item in proxy_readiness if not item["ready"])
        status = _daemon_status(tuple(instances)) if instances else "setup_needed"
        reason = f"Daemon service group '{service_group}' has no ready instance."
        if proxy_blockers:
            reason = f"{reason} {_proxy_blocker_reason(proxy_blockers)}"
        setup_available = any(_daemon_setup_available(spec) for spec in specs)
        if (
            requirement == "browser-profile-runtime"
            and setup_available
            and not proxy_blockers
        ):
            return ToolRuntimeReadinessCheck(
                requirement=requirement,
                status="launchable",
                ready=True,
                reason=(
                    "Browser daemon service group has no ready instance, "
                    "but a profile host can be launched or attached on demand."
                ),
                setup_available=True,
                metadata={
                    **_daemon_group_metadata(service_group, specs, tuple(instances)),
                    **(
                        {"proxy_readiness": proxy_readiness}
                        if proxy_readiness
                        else {}
                    ),
                },
            )
        return ToolRuntimeReadinessCheck(
            requirement=requirement,
            status=status,
            ready=False,
            reason=reason,
            setup_available=setup_available,
            metadata={
                **_daemon_group_metadata(service_group, specs, tuple(instances)),
                **(
                    {"proxy_readiness": proxy_readiness}
                    if proxy_readiness
                    else {}
                ),
            },
        )

    def _check_daemon_service(
        self,
        requirement: str,
        *,
        service_key: str,
    ) -> ToolRuntimeReadinessCheck:
        try:
            spec = self.daemon_service.get_service_spec(service_key)
        except Exception as exc:
            return ToolRuntimeReadinessCheck(
                requirement=requirement,
                status="unsupported",
                ready=False,
                reason=f"Daemon service '{service_key}' is not registered: {exc}",
                metadata={"service_key": service_key},
            )
        try:
            instances = tuple(self.daemon_service.list_instances(service_key=service_key))
        except Exception as exc:
            return ToolRuntimeReadinessCheck(
                requirement=requirement,
                status="degraded",
                ready=False,
                reason=f"Daemon service '{service_key}' could not be inspected: {exc}",
                metadata={"service_key": service_key},
            )
        ready_instances = tuple(instance for instance in instances if instance.status == "ready")
        if ready_instances:
            return ToolRuntimeReadinessCheck(
                requirement=requirement,
                status="ready",
                ready=True,
                reason=f"Daemon service '{service_key}' has a ready instance.",
                metadata=_daemon_metadata(spec, ready_instances),
            )
        if not instances:
            proxy_readiness = _browser_proxy_readiness(
                (spec,),
                access_service=self.access_service,
            )
            proxy_blockers = tuple(item for item in proxy_readiness if not item["ready"])
            reason = f"Daemon service '{service_key}' has no ready instance."
            if proxy_blockers:
                reason = f"{reason} {_proxy_blocker_reason(proxy_blockers)}"
            return ToolRuntimeReadinessCheck(
                requirement=requirement,
                status="setup_needed",
                ready=False,
                reason=reason,
                setup_available=_daemon_setup_available(spec),
                metadata={
                    **_daemon_metadata(spec, instances),
                    **(
                        {"proxy_readiness": proxy_readiness}
                        if proxy_readiness
                        else {}
                    ),
                },
            )
        status = _daemon_status(instances)
        reason = _daemon_reason(service_key, instances, status=status)
        return ToolRuntimeReadinessCheck(
            requirement=requirement,
            status=status,
            ready=False,
            reason=reason,
            setup_available=_daemon_setup_available(spec),
            metadata=_daemon_metadata(spec, instances),
        )


def _blocked_readiness(
    *,
    tool: Tool,
    checked_sets: list[tuple[ToolRuntimeReadinessCheck, ...]],
) -> ToolRuntimeReadiness:
    checks = tuple(check for check_set in checked_sets for check in check_set)
    if not checks:
        return ToolRuntimeReadiness(
            ready=False,
            status="setup_needed",
            reason=f"Tool '{tool.id}' declares runtime requirements but none were checkable.",
        )
    reasons = tuple(
        dict.fromkeys(check.reason for check in checks if not check.ready and check.reason)
    )
    unsupported = any(check.status == "unsupported" for check in checks if not check.ready)
    degraded = any(check.status == "degraded" for check in checks if not check.ready)
    return ToolRuntimeReadiness(
        ready=False,
        status="unsupported" if unsupported else ("degraded" if degraded else "setup_needed"),
        reason="; ".join(reasons) or "Tool runtime setup is required.",
        checks=checks,
    )


def _daemon_setup_available(spec: Any) -> bool:
    return getattr(spec, "start_policy", None) in {"eager", "ensure", "lazy"}


def _daemon_status(instances: tuple[Any, ...]) -> str:
    statuses = {str(getattr(instance, "status", "")).strip().lower() for instance in instances}
    if "degraded" in statuses:
        return "degraded"
    if statuses & {"starting", "stopping"}:
        return "degraded"
    if statuses & {"failed", "stopped"}:
        return "setup_needed"
    return "degraded"


def _daemon_reason(service_key: str, instances: tuple[Any, ...], *, status: str) -> str:
    errors = tuple(
        str(getattr(instance, "last_error", "") or "").strip()
        for instance in instances
        if str(getattr(instance, "last_error", "") or "").strip()
    )
    if errors:
        return f"Daemon service '{service_key}' is not ready: {'; '.join(errors)}"
    statuses = ", ".join(
        sorted({str(getattr(instance, "status", "unknown")) for instance in instances})
    )
    return f"Daemon service '{service_key}' is {status}: {statuses or 'unknown'}."


def _browser_proxy_readiness(
    specs: tuple[Any, ...],
    *,
    access_service: Any | None,
) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for spec in specs:
        metadata = _mapping(getattr(spec, "metadata", None))
        if str(metadata.get("proxy_mode") or "").strip().lower() != "access_binding":
            continue
        profile_name = str(metadata.get("profile_name") or "").strip()
        binding_id = str(metadata.get("proxy_binding_id") or "").strip()
        credential_kind = _normalize_proxy_credential_kind(
            metadata.get("proxy_credential_kind"),
        )
        if not binding_id:
            rows.append(
                {
                    "profile_name": profile_name,
                    "binding_id": None,
                    "expected_kind": credential_kind,
                    "ready": False,
                    "status": "setup_needed",
                    "reason": "Browser proxy is configured as access_binding but no proxy_binding_id is set.",
                }
            )
            continue
        check = getattr(access_service, "check_credential_binding", None)
        if not callable(check):
            rows.append(
                {
                    "profile_name": profile_name,
                    "binding_id": binding_id,
                    "expected_kind": credential_kind,
                    "ready": False,
                    "status": "setup_needed",
                    "reason": "Access credential readiness is unavailable for browser proxy binding.",
                }
            )
            continue
        try:
            readiness = check(binding_id, expected_kind=credential_kind)
        except TypeError:
            try:
                readiness = check(binding_id)
            except Exception as exc:  # noqa: BLE001
                rows.append(
                    _proxy_readiness_error(
                        profile_name,
                        binding_id,
                        exc,
                        expected_kind=credential_kind,
                    )
                )
                continue
        except Exception as exc:  # noqa: BLE001
            rows.append(
                _proxy_readiness_error(
                    profile_name,
                    binding_id,
                    exc,
                    expected_kind=credential_kind,
                )
            )
            continue
        payload = _payload(readiness)
        rows.append(
            {
                "profile_name": profile_name,
                "binding_id": binding_id,
                "expected_kind": credential_kind,
                "ready": bool(payload.get("ready", getattr(readiness, "ready", False))),
                "status": str(
                    payload.get("status") or getattr(readiness, "status", "setup_needed"),
                ),
                "reason": str(
                    payload.get("reason") or getattr(readiness, "reason", "") or "",
                ),
            }
        )
    return tuple(rows)


def _proxy_readiness_error(
    profile_name: str,
    binding_id: str,
    exc: Exception,
    *,
    expected_kind: str,
) -> dict[str, Any]:
    return {
        "profile_name": profile_name,
        "binding_id": binding_id,
        "expected_kind": expected_kind,
        "ready": False,
        "status": "setup_needed",
        "reason": f"Browser proxy credential readiness failed: {exc}",
    }


def _proxy_blocker_reason(blockers: tuple[dict[str, Any], ...]) -> str:
    parts = []
    for item in blockers[:3]:
        binding = item.get("binding_id") or "<missing>"
        status = item.get("status") or "setup_needed"
        reason = item.get("reason") or "credential setup is required"
        parts.append(f"Browser proxy credential '{binding}' is {status}: {reason}")
    return " ".join(parts)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _normalize_proxy_credential_kind(value: Any) -> str:
    credential_kind = str(value or "basic").strip().lower()
    if credential_kind == "bearer":
        credential_kind = "bearer_token"
    if credential_kind not in {"basic", "bearer_token"}:
        return "basic"
    return credential_kind


def _payload(value: Any) -> dict[str, Any]:
    to_payload = getattr(value, "to_payload", None)
    if callable(to_payload):
        payload = to_payload()
        if isinstance(payload, dict):
            return dict(payload)
    return {}


def _daemon_metadata(spec: Any, instances: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "service_key": getattr(spec, "key", None),
        "display_name": getattr(spec, "display_name", None),
        "service_group": getattr(spec, "service_group", None),
        "role": getattr(spec, "role", None),
        "start_policy": getattr(spec, "start_policy", None),
        "desired_replicas": getattr(spec, "desired_replicas", None),
        "instance_count": len(instances),
        "instance_statuses": [
            str(getattr(instance, "status", "unknown")) for instance in instances
        ],
    }


def _daemon_group_metadata(
    service_group: str,
    specs: tuple[Any, ...],
    instances: tuple[Any, ...],
) -> dict[str, Any]:
    return {
        "service_group": service_group,
        "service_keys": [str(getattr(spec, "key", "")) for spec in specs],
        "start_policies": [str(getattr(spec, "start_policy", "")) for spec in specs],
        "desired_replicas": sum(
            int(getattr(spec, "desired_replicas", 0) or 0) for spec in specs
        ),
        "instance_count": len(instances),
        "instance_statuses": [
            str(getattr(instance, "status", "unknown")) for instance in instances
        ],
    }
