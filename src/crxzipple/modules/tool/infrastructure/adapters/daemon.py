from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.tool.application.ports import (
    ToolRuntimeReadiness,
    ToolRuntimeReadinessCheck,
    ToolRuntimeReadinessPort,
)
from crxzipple.modules.tool.domain.entities import Tool
from crxzipple.modules.tool.infrastructure.adapters.daemon_proxy_readiness import (
    browser_proxy_readiness,
    proxy_blocker_reason,
)
from crxzipple.modules.tool.infrastructure.adapters.daemon_readiness_metadata import (
    daemon_group_metadata,
    daemon_metadata,
    daemon_reason,
    daemon_setup_available,
    daemon_status,
)


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
                metadata=daemon_group_metadata(
                    service_group,
                    specs,
                    tuple(instances),
                ),
            )
        proxy_readiness = browser_proxy_readiness(
            specs,
            access_service=self.access_service,
        )
        proxy_blockers = tuple(item for item in proxy_readiness if not item["ready"])
        status = daemon_status(tuple(instances)) if instances else "setup_needed"
        reason = f"Daemon service group '{service_group}' has no ready instance."
        if proxy_blockers:
            reason = f"{reason} {proxy_blocker_reason(proxy_blockers)}"
        setup_available = any(daemon_setup_available(spec) for spec in specs)
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
                    **daemon_group_metadata(service_group, specs, tuple(instances)),
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
                **daemon_group_metadata(service_group, specs, tuple(instances)),
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
                metadata=daemon_metadata(spec, ready_instances),
            )
        if not instances:
            proxy_readiness = browser_proxy_readiness(
                (spec,),
                access_service=self.access_service,
            )
            proxy_blockers = tuple(item for item in proxy_readiness if not item["ready"])
            reason = f"Daemon service '{service_key}' has no ready instance."
            if proxy_blockers:
                reason = f"{reason} {proxy_blocker_reason(proxy_blockers)}"
            return ToolRuntimeReadinessCheck(
                requirement=requirement,
                status="setup_needed",
                ready=False,
                reason=reason,
                setup_available=daemon_setup_available(spec),
                metadata={
                    **daemon_metadata(spec, instances),
                    **(
                        {"proxy_readiness": proxy_readiness}
                        if proxy_readiness
                        else {}
                    ),
                },
            )
        status = daemon_status(instances)
        reason = daemon_reason(service_key, instances, status=status)
        return ToolRuntimeReadinessCheck(
            requirement=requirement,
            status=status,
            ready=False,
            reason=reason,
            setup_available=daemon_setup_available(spec),
            metadata=daemon_metadata(spec, instances),
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
