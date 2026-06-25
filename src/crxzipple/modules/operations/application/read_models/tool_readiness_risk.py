from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.ports_tooling import (
    OperationsToolQueryPort,
)
from crxzipple.modules.operations.application.read_models.tool_readiness_payloads import (
    join_values,
    readiness_payload,
    tool_access_readiness_payload,
    tool_combined_readiness_payload,
)
from crxzipple.modules.tool.domain import Tool


def tool_readiness_risk(
    tool: Tool,
    *,
    tool_service: OperationsToolQueryPort | None = None,
    access_service: Any | None,
) -> dict[str, Any]:
    if tool_service is not None and hasattr(tool_service, "check_readiness"):
        readiness = tool_service.check_readiness(tool.id)
        if isinstance(readiness, dict):
            return tool_combined_readiness_payload(tool, readiness)
    return _tool_access_readiness(
        tool,
        tool_service=tool_service,
        access_service=access_service,
    )


def _tool_access_readiness(
    tool: Tool,
    *,
    tool_service: OperationsToolQueryPort | None = None,
    access_service: Any | None,
) -> dict[str, Any]:
    if tool_service is not None and hasattr(tool_service, "check_access_readiness"):
        readiness = tool_service.check_access_readiness(tool.id)
        if readiness is not None:
            return tool_access_readiness_payload(tool, readiness.to_payload())
    requirement_sets = tuple(
        tuple(requirement for requirement in item if requirement.strip())
        for item in tool.access_requirement_sets
        if item
    )
    all_requirements = tuple(
        dict.fromkeys(
            requirement
            for requirement_set in requirement_sets
            for requirement in requirement_set
        ),
    )
    if not requirement_sets:
        return {
            "ready": True,
            "status": "ready",
            "reason": "No access requirement declared",
            "category": "-",
            "requirements": "-",
            "missing": "-",
            "setup": "-",
            "action": "-",
            "route": "-",
        }
    if access_service is None or not hasattr(access_service, "check_requirements"):
        return {
            "ready": False,
            "status": "unknown",
            "reason": "access readiness service is not connected",
            "category": "Access",
            "requirements": join_values(all_requirements),
            "missing": join_values(all_requirements),
            "setup": "-",
            "action": "Open Access",
            "route": "/operations/access",
        }

    checked_sets: list[tuple[dict[str, Any], ...]] = []
    for requirement_set in requirement_sets:
        read_items = tuple(
            readiness_payload(item)
            for item in access_service.check_requirements(requirement_set)
        )
        checked_sets.append(read_items)
        if all(bool(item.get("ready")) for item in read_items):
            return {
                "ready": True,
                "status": "ready",
                "reason": "All requirements are ready",
                "category": "Access",
                "requirements": join_values(all_requirements),
                "missing": "-",
                "setup": "-",
                "action": "-",
                "route": "-",
            }

    missing = tuple(
        dict.fromkeys(
            str(item.get("requirement") or "").strip()
            for checked_set in checked_sets
            for item in checked_set
            if not bool(item.get("ready")) and str(item.get("requirement") or "").strip()
        ),
    )
    reasons = tuple(
        dict.fromkeys(
            str(item.get("reason") or "").strip()
            for checked_set in checked_sets
            for item in checked_set
            if not bool(item.get("ready")) and str(item.get("reason") or "").strip()
        ),
    )
    setup_available = any(
        bool(item.get("setup_available"))
        for checked_set in checked_sets
        for item in checked_set
        if not bool(item.get("ready"))
    )
    unsupported = any(
        str(item.get("status") or "") == "unsupported"
        for checked_set in checked_sets
        for item in checked_set
        if not bool(item.get("ready"))
    )
    return {
        "ready": False,
        "status": "unsupported" if unsupported else "setup_needed",
        "reason": join_values(reasons) if reasons else "access setup is required",
        "category": "Access",
        "requirements": join_values(all_requirements),
        "missing": join_values(missing),
        "setup": "available" if setup_available else "unavailable",
        "action": "Open Access",
        "route": "/operations/access",
    }
