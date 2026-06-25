from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.presenters import (
    display_value,
)
from crxzipple.modules.tool.domain import Tool


def tool_combined_readiness_payload(
    tool: Tool,
    payload: dict[str, Any],
) -> dict[str, Any]:
    checks = tuple(
        dict(item) for item in payload.get("checks", []) if isinstance(item, dict)
    )
    blocked_checks = tuple(item for item in checks if not bool(item.get("ready")))
    categories = tuple(
        dict.fromkeys(
            str(item.get("category") or "").strip()
            for item in blocked_checks
            if str(item.get("category") or "").strip()
        ),
    )
    requirements = _readiness_requirements(checks=checks, tool=tool)
    missing = tuple(
        dict.fromkeys(
            str(item.get("binding_id") or item.get("requirement") or "").strip()
            for item in blocked_checks
            if str(item.get("binding_id") or item.get("requirement") or "").strip()
        ),
    )
    action, route = _readiness_action(categories)
    return {
        "ready": bool(payload.get("ready")),
        "status": str(payload.get("status") or "unknown"),
        "reason": str(payload.get("reason") or "tool readiness unknown"),
        "category": _readiness_category_label(categories),
        "requirements": join_values(requirements) if requirements else "-",
        "missing": join_values(missing) if missing else "-",
        "setup": "available" if bool(payload.get("setup_available")) else "unavailable",
        "action": action,
        "route": route,
    }


def tool_access_readiness_payload(
    tool: Tool,
    payload: dict[str, Any],
) -> dict[str, Any]:
    checks = tuple(
        dict(item) for item in payload.get("checks", []) if isinstance(item, dict)
    )
    requirements = tuple(
        dict.fromkeys(
            str(item.get("binding_id") or item.get("requirement") or "").strip()
            for item in checks
            if str(item.get("binding_id") or item.get("requirement") or "").strip()
        ),
    )
    missing = tuple(
        dict.fromkeys(
            str(item.get("binding_id") or item.get("requirement") or "").strip()
            for item in checks
            if not bool(item.get("ready"))
            and str(item.get("binding_id") or item.get("requirement") or "").strip()
        ),
    )
    if not requirements:
        requirements = tuple(
            dict.fromkeys(
                requirement
                for requirement_set in tool.access_requirement_sets
                for requirement in requirement_set
                if requirement.strip()
            ),
        )
    return {
        "ready": bool(payload.get("ready")),
        "status": str(payload.get("status") or "unknown"),
        "reason": str(payload.get("reason") or "access readiness unknown"),
        "category": "Access",
        "requirements": join_values(requirements) if requirements else "-",
        "missing": join_values(missing) if missing else "-",
        "setup": "available" if bool(payload.get("setup_available")) else "unavailable",
        "action": "Open Access",
        "route": "/operations/access",
    }


def readiness_payload(readiness: Any) -> dict[str, Any]:
    if hasattr(readiness, "to_payload"):
        payload = readiness.to_payload()
        if isinstance(payload, dict):
            return dict(payload)
    return {
        "requirement": display_value(getattr(readiness, "requirement", None)),
        "ready": bool(getattr(readiness, "ready", False)),
        "setup_available": bool(getattr(readiness, "setup_available", False)),
        "status": display_value(getattr(getattr(readiness, "status", None), "value", None)),
        "reason": display_value(getattr(readiness, "reason", None)),
    }


def join_values(values: tuple[str, ...] | list[str]) -> str:
    return ", ".join(value for value in values if value) or "-"


def _readiness_requirements(
    *,
    checks: tuple[dict[str, Any], ...],
    tool: Tool,
) -> tuple[str, ...]:
    requirements = tuple(
        dict.fromkeys(
            str(item.get("binding_id") or item.get("requirement") or "").strip()
            for item in checks
            if str(item.get("binding_id") or item.get("requirement") or "").strip()
        ),
    )
    if requirements:
        return requirements
    declared = (
        *(
            requirement
            for requirement_set in tool.access_requirement_sets
            for requirement in requirement_set
            if requirement.strip()
        ),
        *(
            requirement
            for requirement_set in tool.runtime_requirement_sets
            for requirement in requirement_set
            if requirement.strip()
        ),
    )
    return tuple(dict.fromkeys(declared))


def _readiness_category_label(categories: tuple[str, ...]) -> str:
    normalized = set(categories)
    if not normalized:
        return "-"
    if normalized == {"access"}:
        return "Access"
    if normalized == {"runtime"}:
        return "Runtime"
    return "Mixed"


def _readiness_action(categories: tuple[str, ...]) -> tuple[str, str]:
    normalized = set(categories)
    if normalized == {"runtime"}:
        return "Open Daemon", "/operations/daemon"
    if "access" in normalized:
        return "Open Access", "/operations/access"
    if "runtime" in normalized:
        return "Open Daemon", "/operations/daemon"
    return "Inspect Tool", "/operations/tool"
