from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from crxzipple.shared.settings import RuntimeDefaultsConfig


@dataclass(frozen=True, slots=True)
class RuntimeSettingsBootstrapConfig:
    orchestration_run_lease_seconds: int = 30
    orchestration_run_heartbeat_seconds: float = 5.0
    orchestration_executor_max_concurrent_assignments: int = 4
    orchestration_auto_compaction_enabled: bool = True
    orchestration_auto_compaction_reserve_tokens: int = 20_000
    orchestration_auto_compaction_soft_threshold_tokens: int = 4_000
    tool_run_max_attempts: int = 3
    tool_run_lease_seconds: int = 30
    tool_run_heartbeat_seconds: float = 5.0
    tool_worker_max_in_flight: int = 4
    tool_worker_default_run_concurrency: int = 4
    tool_worker_image_run_concurrency: int = 4
    tool_worker_shared_state_run_concurrency: int = 1
    tool_remote_default_max_concurrency: int = 16


def runtime_bootstrap_config_from_settings(
    config: RuntimeDefaultsConfig | Mapping[str, Any],
) -> RuntimeSettingsBootstrapConfig:
    payload = _payload_from_config(config)
    orchestration = _mapping(payload.get("orchestration"))
    tool_worker = _mapping(payload.get("tool_worker"))

    return RuntimeSettingsBootstrapConfig(
        orchestration_run_lease_seconds=_positive_int(
            _value(payload, orchestration, flat_key="orchestration_run_lease_seconds", nested_key="run_lease_seconds"),
            default=30,
            field_name="orchestration_run_lease_seconds",
        ),
        orchestration_run_heartbeat_seconds=_positive_float(
            _value(payload, orchestration, flat_key="orchestration_run_heartbeat_seconds", nested_key="run_heartbeat_seconds"),
            default=5.0,
            field_name="orchestration_run_heartbeat_seconds",
        ),
        orchestration_executor_max_concurrent_assignments=_positive_int(
            _value(
                payload,
                orchestration,
                flat_key="orchestration_executor_max_concurrent_assignments",
                nested_key="executor_max_concurrent_assignments",
                aliases=("max_concurrent_assignments",),
            ),
            default=4,
            field_name="orchestration_executor_max_concurrent_assignments",
        ),
        orchestration_auto_compaction_enabled=_bool(
            _value(payload, orchestration, flat_key="orchestration_auto_compaction_enabled", nested_key="auto_compaction_enabled"),
            default=True,
        ),
        orchestration_auto_compaction_reserve_tokens=_positive_int(
            _value(payload, orchestration, flat_key="orchestration_auto_compaction_reserve_tokens", nested_key="auto_compaction_reserve_tokens"),
            default=20_000,
            field_name="orchestration_auto_compaction_reserve_tokens",
        ),
        orchestration_auto_compaction_soft_threshold_tokens=_positive_int(
            _value(payload, orchestration, flat_key="orchestration_auto_compaction_soft_threshold_tokens", nested_key="auto_compaction_soft_threshold_tokens"),
            default=4_000,
            field_name="orchestration_auto_compaction_soft_threshold_tokens",
        ),
        tool_run_max_attempts=_positive_int(
            _value(payload, tool_worker, flat_key="tool_run_max_attempts", nested_key="run_max_attempts"),
            default=3,
            field_name="tool_run_max_attempts",
        ),
        tool_run_lease_seconds=_positive_int(
            _value(payload, tool_worker, flat_key="tool_run_lease_seconds", nested_key="run_lease_seconds"),
            default=30,
            field_name="tool_run_lease_seconds",
        ),
        tool_run_heartbeat_seconds=_positive_float(
            _value(payload, tool_worker, flat_key="tool_run_heartbeat_seconds", nested_key="run_heartbeat_seconds"),
            default=5.0,
            field_name="tool_run_heartbeat_seconds",
        ),
        tool_worker_max_in_flight=_positive_int(
            _value(payload, tool_worker, flat_key="tool_worker_max_in_flight", nested_key="max_in_flight"),
            default=4,
            field_name="tool_worker_max_in_flight",
        ),
        tool_worker_default_run_concurrency=_positive_int(
            _value(payload, tool_worker, flat_key="tool_worker_default_run_concurrency", nested_key="default_run_concurrency"),
            default=4,
            field_name="tool_worker_default_run_concurrency",
        ),
        tool_worker_image_run_concurrency=_positive_int(
            _value(payload, tool_worker, flat_key="tool_worker_image_run_concurrency", nested_key="image_run_concurrency"),
            default=4,
            field_name="tool_worker_image_run_concurrency",
        ),
        tool_worker_shared_state_run_concurrency=_positive_int(
            _value(payload, tool_worker, flat_key="tool_worker_shared_state_run_concurrency", nested_key="shared_state_run_concurrency"),
            default=1,
            field_name="tool_worker_shared_state_run_concurrency",
        ),
        tool_remote_default_max_concurrency=_positive_int(
            _value(payload, tool_worker, flat_key="tool_remote_default_max_concurrency", nested_key="remote_default_max_concurrency"),
            default=16,
            field_name="tool_remote_default_max_concurrency",
        ),
    )


def _payload_from_config(config: RuntimeDefaultsConfig | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(config, RuntimeDefaultsConfig):
        return dict(config.to_payload())
    if isinstance(config, Mapping):
        return dict(config)
    raise TypeError("Runtime defaults config must be a RuntimeDefaultsConfig or mapping.")


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _value(
    payload: Mapping[str, Any],
    nested: Mapping[str, Any],
    *,
    flat_key: str,
    nested_key: str,
    aliases: tuple[str, ...] = (),
) -> object:
    for key in (nested_key, *aliases):
        if key in nested and nested[key] is not None:
            return nested[key]
    if flat_key in payload and payload[flat_key] is not None:
        return payload[flat_key]
    return None


def _bool(value: object, *, default: bool) -> bool:
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _positive_int(value: object, *, default: int, field_name: str) -> int:
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    parsed = int(value)
    if parsed < 1:
        raise ValueError(f"{field_name} must be positive.")
    return parsed


def _positive_float(value: object, *, default: float, field_name: str) -> float:
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    parsed = float(value)
    if parsed <= 0:
        raise ValueError(f"{field_name} must be positive.")
    return parsed


__all__ = [
    "RuntimeSettingsBootstrapConfig",
    "runtime_bootstrap_config_from_settings",
]
