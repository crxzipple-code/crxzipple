from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.browser_values import (
    dict_value,
    int_value,
    text,
    to_payload,
)


def runtime(profile: Any) -> dict[str, Any]:
    value = getattr(profile, "runtime", None)
    return value if isinstance(value, dict) else {}


def runtime_status(value: dict[str, Any]) -> str:
    return text(value.get("attachment_status"), "idle").lower()


def page_stale(page: dict[str, Any]) -> bool:
    reason = text(page.get("page_generation_reason"), "").lower()
    snapshot_generation = int_value(page.get("snapshot_generation"))
    page_generation = int_value(page.get("page_generation"))
    if reason in {"navigate", "reload", "changed", "host-generation-changed"}:
        return snapshot_generation < 1
    return page_generation > 1 and snapshot_generation < 1


def proxy_label(profile: Any) -> str:
    mode = text(getattr(profile, "proxy_mode", None), "none")
    binding = text(getattr(profile, "proxy_binding_id", None))
    credential_kind = text(getattr(profile, "proxy_credential_kind", None), "basic")
    if binding != "-":
        return f"{mode} · {credential_kind} · {binding}"
    return f"{mode} · {credential_kind}" if mode == "access_binding" else mode


def proxy_readiness_label(profile: Any, *, access_service: Any | None) -> str:
    mode = text(getattr(profile, "proxy_mode", None), "none")
    if mode != "access_binding":
        return "not required"
    binding_id = text(getattr(profile, "proxy_binding_id", None))
    if binding_id == "-":
        return "setup_needed"
    credential_kind = text(getattr(profile, "proxy_credential_kind", None), "basic")
    check = getattr(access_service, "check_credential_binding", None)
    if not callable(check):
        return "unknown"
    try:
        readiness = check(binding_id, expected_kind=credential_kind)
    except TypeError:
        try:
            readiness = check(binding_id)
        except Exception:
            return "unknown"
    except Exception:
        return "unknown"
    payload = to_payload(readiness)
    status = text(payload.get("status") or getattr(readiness, "status", None))
    if not status or status == "-":
        return "ready" if bool(getattr(readiness, "ready", False)) else "setup_needed"
    return status


def proxy_metadata_by_profile(
    instances: tuple[dict[str, Any], ...],
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for instance in instances:
        service_key = text(instance.get("service_key"), "")
        if not service_key.startswith("host:browser:"):
            continue
        metadata = dict_value(instance.get("metadata"))
        profile = text(metadata.get("profile_name") or service_key.rsplit(":", 1)[-1])
        if profile != "-":
            grouped.setdefault(profile, []).append(instance)
    mapped: dict[str, dict[str, Any]] = {}
    for profile, profile_instances in grouped.items():
        mapped[profile] = dict_value(preferred_instance(profile_instances).get("metadata"))
    return mapped


def runtime_proxy_metadata(value: dict[str, Any]) -> dict[str, Any]:
    proxy_egress = dict_value(value.get("proxy_egress"))
    metadata: dict[str, Any] = {}
    if proxy_egress:
        metadata["proxy_egress"] = proxy_egress
    for key in ("proxy_egress_status", "proxy_egress_ip", "proxy_egress_checked_at"):
        item = value.get(key)
        if item is not None:
            metadata[key] = item
    return metadata


def preferred_browser_instances_by_service(
    instances: tuple[dict[str, Any], ...],
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for instance in instances:
        service_key = text(instance.get("service_key"), "")
        if not is_browser_service(service_key):
            continue
        grouped.setdefault(service_key, []).append(instance)
    return {
        service_key: preferred_instance(service_instances)
        for service_key, service_instances in grouped.items()
    }


def preferred_instance(instances: list[dict[str, Any]]) -> dict[str, Any]:
    return max(instances, key=instance_preference_key) if instances else {}


def instance_preference_key(instance: dict[str, Any]) -> tuple[int, str, str]:
    status = text(instance.get("status"), "").lower()
    rank = {
        "ready": 50,
        "running": 40,
        "active": 40,
        "launched": 40,
        "adopted": 40,
        "starting": 30,
        "configured": 20,
        "failed": 10,
        "degraded": 10,
        "stopped": 0,
    }.get(status, 0)
    timestamp = text(
        instance.get("last_healthcheck_at")
        or instance.get("updated_at")
        or instance.get("started_at")
        or instance.get("created_at"),
        "",
    )
    return rank, timestamp, text(instance.get("id"), "")


def proxy_egress_label(metadata: dict[str, Any]) -> str:
    if not metadata:
        return "-"
    raw = metadata.get("proxy_egress")
    egress = dict_value(raw) if isinstance(raw, dict) else {}
    status = text(
        egress.get("status")
        or metadata.get("proxy_egress_status")
        or ("ready" if metadata.get("proxy_egress_ip") else None),
    )
    ip = text(egress.get("ip") or metadata.get("proxy_egress_ip"))
    if ip != "-":
        return f"{status} · {ip}" if status != "-" else ip
    return status


def browser_runtime_kind(service_key: str) -> str:
    if service_key.startswith("host:browser:"):
        return "Browser Host"
    return "Browser"


def is_browser_service(service_key: str) -> bool:
    return service_key.startswith("host:browser:")
