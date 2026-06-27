from __future__ import annotations

from typing import Any, Mapping


def browser_proxy_readiness(
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


def proxy_blocker_reason(blockers: tuple[dict[str, Any], ...]) -> str:
    parts = []
    for item in blockers[:3]:
        binding = item.get("binding_id") or "<missing>"
        status = item.get("status") or "setup_needed"
        reason = item.get("reason") or "credential setup is required"
        parts.append(f"Browser proxy credential '{binding}' is {status}: {reason}")
    return " ".join(parts)


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


__all__ = [
    "browser_proxy_readiness",
    "proxy_blocker_reason",
]
