from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.daemon_browser_instance_summary import (
    browser_instance_summary_items,
)
from crxzipple.modules.operations.application.read_models.daemon_common import (
    _bool,
    _short,
    _status_label,
    _text,
    _yes_no,
)
from crxzipple.modules.operations.application.read_models.daemon_detail_common import (
    matching_events,
)
from crxzipple.modules.operations.application.read_models.daemon_events import (
    daemon_events_table,
)
from crxzipple.modules.operations.application.read_models.daemon_models import (
    DaemonInstanceDetailModel,
)
from crxzipple.modules.operations.application.read_models.daemon_status_helpers import (
    _tone_for_status,
)
from crxzipple.modules.operations.application.read_models.daemon_tables import (
    daemon_leases_table,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
    OperationsKeyValueSectionModel,
)


def daemon_instance_details(
    *,
    instances: tuple[dict[str, Any], ...],
    service_by_key: dict[str, dict[str, Any]],
    leases_by_instance: dict[str, list[dict[str, Any]]],
    events: tuple[OperationsObservedEvent, ...],
) -> tuple[DaemonInstanceDetailModel, ...]:
    details: list[DaemonInstanceDetailModel] = []
    for instance in instances[:80]:
        instance_id = _text(instance.get("id"), "")
        service_key = _text(instance.get("service_key"), "")
        service = service_by_key.get(service_key, {})
        leases = tuple(leases_by_instance.get(instance_id, []))
        status = _status_label(instance.get("status"))
        details.append(
            DaemonInstanceDetailModel(
                instance_id=instance_id,
                title=_text(service.get("display_name") or service_key or instance_id),
                status=status,
                tone=_tone_for_status(status),
                summary=(
                    OperationsKeyValueItemModel("Instance ID", instance_id),
                    OperationsKeyValueItemModel("Service Key", service_key),
                    *browser_instance_summary_items(instance, service),
                    OperationsKeyValueItemModel("Status", status, _tone_for_status(status)),
                    OperationsKeyValueItemModel("PID", _text(instance.get("pid"))),
                    OperationsKeyValueItemModel("Worker ID", _text(instance.get("worker_id"))),
                    OperationsKeyValueItemModel("Endpoint", _text(instance.get("endpoint"))),
                    OperationsKeyValueItemModel("Started At", _text(instance.get("started_at"))),
                    OperationsKeyValueItemModel(
                        "Last Healthcheck At",
                        _text(instance.get("last_healthcheck_at")),
                    ),
                ),
                environment=_environment_section(instance),
                service=_service_section(service),
                leases=daemon_leases_table(
                    leases,
                    total=len(leases),
                    service_by_key=service_by_key,
                ),
                events=daemon_events_table(
                    matching_events(
                        events,
                        service_key=service_key,
                        entity_id=instance_id,
                    )
                ),
                raw_payload={
                    "instance": dict(instance),
                    "service": dict(service),
                    "leases": [dict(item) for item in leases],
                },
            )
        )
    return tuple(details)


def _environment_section(instance: dict[str, Any]) -> OperationsKeyValueSectionModel:
    env_keys = instance.get("env_keys")
    if not isinstance(env_keys, list):
        env_keys = []
    drift = _bool(instance.get("env_drift_detected"))
    return OperationsKeyValueSectionModel(
        id="environment",
        title="Environment",
        items=(
            OperationsKeyValueItemModel(
                "Drift Detected",
                _yes_no(drift),
                "warning" if drift else "success",
            ),
            OperationsKeyValueItemModel("Env Fingerprint", _short(instance.get("env_fingerprint"), 32)),
            OperationsKeyValueItemModel(
                "Expected Fingerprint",
                _short(instance.get("expected_env_fingerprint"), 32),
            ),
            OperationsKeyValueItemModel(
                "Actual Fingerprint",
                _short(instance.get("actual_env_fingerprint"), 32),
            ),
            OperationsKeyValueItemModel(
                "Env Keys",
                ", ".join(_text(item, "") for item in env_keys[:12]) if env_keys else "-",
            ),
            OperationsKeyValueItemModel("Last Error", _short(instance.get("last_error"), 160)),
        ),
    )


def _service_section(service: dict[str, Any]) -> OperationsKeyValueSectionModel:
    metadata = service.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    return OperationsKeyValueSectionModel(
        id="service",
        title="Service",
        items=(
            OperationsKeyValueItemModel("Display Name", _text(service.get("display_name"))),
            OperationsKeyValueItemModel("Service Group", _text(service.get("service_group"))),
            OperationsKeyValueItemModel("Role", _text(service.get("role"))),
            OperationsKeyValueItemModel("Managed By", _text(service.get("managed_by"))),
            OperationsKeyValueItemModel("Transport", _text(service.get("transport"))),
            OperationsKeyValueItemModel("Replica Mode", _text(service.get("replica_mode"))),
            OperationsKeyValueItemModel("Desired", _text(service.get("desired_replicas"))),
            OperationsKeyValueItemModel("Start Policy", _text(service.get("start_policy"))),
            OperationsKeyValueItemModel("Restart Policy", _text(service.get("restart_policy"))),
            OperationsKeyValueItemModel("Healthcheck Policy", _text(service.get("healthcheck_policy"))),
            OperationsKeyValueItemModel("Match Policy", _text(service.get("match_policy"))),
            OperationsKeyValueItemModel("CLI Args", _text(metadata.get("cli_args"))),
        ),
    )
