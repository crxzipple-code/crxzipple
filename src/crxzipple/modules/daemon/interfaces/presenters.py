from __future__ import annotations

from typing import Any


def _instance_environment_payload(instance) -> dict[str, object]:  # noqa: ANN001
    metadata = dict(instance.metadata)
    env_keys = metadata.get("env_keys")
    if not isinstance(env_keys, list):
        env_keys = []
    return {
        "env_fingerprint": metadata.get("env_fingerprint"),
        "env_keys": list(env_keys),
        "env_drift_detected": bool(metadata.get("env_drift_detected")),
        "expected_env_fingerprint": metadata.get("expected_env_fingerprint"),
        "actual_env_fingerprint": metadata.get("actual_env_fingerprint"),
    }


def spec_payload(spec) -> dict[str, object]:  # noqa: ANN001
    return {
        "key": spec.key,
        "display_name": spec.display_name,
        "service_group": getattr(spec, "service_group", None),
        "role": spec.role,
        "managed_by": spec.managed_by,
        "transport": spec.transport,
        "replica_mode": spec.replica_mode,
        "desired_replicas": spec.desired_replicas,
        "start_policy": spec.start_policy,
        "restart_policy": spec.restart_policy,
        "healthcheck_policy": spec.healthcheck_policy,
        "match_policy": spec.match_policy,
        "metadata": dict(spec.metadata),
    }


def service_set_payload(service_set) -> dict[str, object]:  # noqa: ANN001
    return {
        "key": service_set.key,
        "display_name": service_set.display_name,
        "description": service_set.description,
        "service_keys": list(service_set.service_keys),
        "service_roles": list(service_set.service_roles),
        "service_groups": list(service_set.service_groups),
    }


def instance_payload(instance) -> dict[str, object]:  # noqa: ANN001
    return {
        "id": instance.id,
        "service_key": instance.service_key,
        "status": instance.status,
        "worker_id": instance.worker_id,
        "pid": instance.pid,
        "endpoint": instance.endpoint,
        "started_at": instance.started_at.isoformat() if instance.started_at else None,
        "last_healthcheck_at": (
            instance.last_healthcheck_at.isoformat()
            if instance.last_healthcheck_at
            else None
        ),
        "last_error": instance.last_error,
        **_instance_environment_payload(instance),
        "metadata": dict(instance.metadata),
    }


def lease_payload(lease) -> dict[str, object]:  # noqa: ANN001
    return {
        "id": lease.id,
        "service_key": lease.service_key,
        "instance_id": lease.instance_id,
        "owner_kind": lease.owner_kind,
        "owner_id": lease.owner_id,
        "status": lease.status,
        "acquired_at": lease.acquired_at.isoformat() if lease.acquired_at else None,
        "heartbeat_at": lease.heartbeat_at.isoformat() if lease.heartbeat_at else None,
        "expires_at": lease.expires_at.isoformat() if lease.expires_at else None,
        "metadata": dict(lease.metadata),
    }


def service_detail_payload(
    *,
    spec,
    instances,
    leases,
) -> dict[str, Any]:  # noqa: ANN001
    instance_list = tuple(instances)
    lease_list = tuple(leases)
    status_counts: dict[str, int] = {}
    for instance in instance_list:
        status_counts[instance.status] = status_counts.get(instance.status, 0) + 1
    lease_counts: dict[str, int] = {}
    for lease in lease_list:
        lease_counts[lease.status] = lease_counts.get(lease.status, 0) + 1
    recent_errors = sorted(
        (
            {
                "instance_id": instance.id,
                "status": instance.status,
                "last_error": instance.last_error,
                "last_healthcheck_at": (
                    instance.last_healthcheck_at.isoformat()
                    if instance.last_healthcheck_at
                    else None
                ),
            }
            for instance in instance_list
            if instance.last_error
        ),
        key=lambda item: item["last_healthcheck_at"] or "",
        reverse=True,
    )
    drifted_instances = sorted(
        (
            {
                "instance_id": instance.id,
                "status": instance.status,
                "worker_id": instance.worker_id,
                "last_healthcheck_at": (
                    instance.last_healthcheck_at.isoformat()
                    if instance.last_healthcheck_at
                    else None
                ),
                **_instance_environment_payload(instance),
            }
            for instance in instance_list
            if bool(instance.metadata.get("env_drift_detected"))
        ),
        key=lambda item: item["last_healthcheck_at"] or "",
        reverse=True,
    )
    env_fingerprints = sorted(
        {
            str(instance.metadata.get("env_fingerprint")).strip()
            for instance in instance_list
            if instance.metadata.get("env_fingerprint") is not None
            and str(instance.metadata.get("env_fingerprint")).strip()
        },
    )
    active_leases = [
        {
            "lease_id": lease.id,
            "instance_id": lease.instance_id,
            "owner_kind": lease.owner_kind,
            "owner_id": lease.owner_id,
            "expires_at": lease.expires_at.isoformat() if lease.expires_at else None,
        }
        for lease in lease_list
        if lease.status == "active"
    ]
    return {
        "service": spec_payload(spec),
        "summary": {
            "instance_count": len(instance_list),
            "status_counts": status_counts,
            "lease_count": len(lease_list),
            "lease_counts": lease_counts,
            "availability": "leased" if active_leases else "available",
            "env_fingerprints": env_fingerprints,
            "environment_consistency": (
                "mixed" if len(env_fingerprints) > 1 else "consistent"
            ),
            "env_drift_instance_count": len(drifted_instances),
            "drifted_instances": drifted_instances,
            "active_leases": active_leases,
            "recent_errors": recent_errors,
        },
        "instances": [instance_payload(instance) for instance in instance_list],
        "leases": [lease_payload(lease) for lease in lease_list],
    }
