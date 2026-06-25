from __future__ import annotations

from typing import Any

from crxzipple.modules.llm.domain import LlmInvocation, LlmProfile


def blocked_profiles(
    profiles: list[LlmProfile],
    *,
    access_service: Any | None,
) -> list[LlmProfile]:
    return [
        profile
        for profile in profiles
        if not profile_access_readiness(profile, access_service=access_service)["ready"]
    ]


def profile_access_readiness(
    profile: LlmProfile,
    *,
    access_service: Any | None,
) -> dict[str, Any]:
    if not profile.enabled:
        return {
            "ready": False,
            "status": "disabled",
            "reason": "profile is disabled",
        }
    if not profile.credential_binding_id:
        if profile.provider.value == "ollama":
            return {
                "ready": True,
                "status": "ready",
                "reason": "local provider does not require a credential binding",
            }
        return {
            "ready": False,
            "status": "setup_needed",
            "reason": "profile has no access credential binding id",
        }
    if access_service is None or not hasattr(access_service, "check_credential_binding"):
        return {
            "ready": False,
            "status": "unknown",
            "reason": "access readiness service is not connected",
        }
    try:
        readiness = access_service.check_credential_binding(profile.credential_binding_id)
    except Exception as exc:
        return {
            "ready": False,
            "status": "error",
            "reason": str(exc) or type(exc).__name__,
        }
    return {
        "ready": bool(getattr(readiness, "ready", False)),
        "status": getattr(getattr(readiness, "status", None), "value", None)
        or str(getattr(readiness, "status", "unknown")),
        "reason": str(getattr(readiness, "reason", "")) or "access readiness unknown",
    }


def readiness_tone(readiness: dict[str, Any]) -> str:
    if readiness.get("ready"):
        return "success"
    status = str(readiness.get("status") or "")
    if status in {"setup_needed", "waiting_user", "unknown", "disabled"}:
        return "warning"
    return "danger"


def availability_label(profile: LlmProfile, readiness: dict[str, Any]) -> str:
    if not profile.enabled:
        return "Disabled"
    if readiness.get("ready"):
        return "Available"
    status = str(readiness.get("status") or "unknown")
    if status == "setup_needed":
        return "Auth Required"
    if status == "unsupported":
        return "Unsupported"
    if status == "unknown":
        return "Unknown"
    return "Blocked"


def latest_invocation_by_profile(
    invocations: list[LlmInvocation],
) -> dict[str, LlmInvocation]:
    latest: dict[str, LlmInvocation] = {}
    for invocation in sorted(invocations, key=lambda item: item.created_at, reverse=True):
        latest.setdefault(invocation.llm_id, invocation)
    return latest


def context_label(profile: LlmProfile) -> str:
    return str(profile.context_window_tokens) if profile.context_window_tokens else "-"


def capability_label(profile: LlmProfile) -> str:
    if not profile.capabilities:
        return "-"
    return ", ".join(capability.value for capability in profile.capabilities)


def credential_label(value: str | None) -> str:
    if value is None or not value.strip():
        return "-"
    return value.strip()


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
