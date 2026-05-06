from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urljoin
import shlex
import sys

import requests

from crxzipple.modules.daemon.domain import (
    DaemonInstance,
    DaemonNotFoundError,
    DaemonServiceSpec,
    DaemonValidationError,
)
from crxzipple.shared.http import request_url
from crxzipple.modules.process import (
    ProcessApplicationService,
    ProcessNotFoundError,
    ProcessSession,
    ProcessStatus,
)

from .ports import EndpointProbe, ShellResolver
from .services import DaemonApplicationService


class DaemonManager:
    def __init__(
        self,
        *,
        daemon_service: DaemonApplicationService,
        process_service: ProcessApplicationService,
        working_directory: str,
        shell_resolver: ShellResolver,
        python_executable: str | None = None,
        endpoint_probe: EndpointProbe | None = None,
        endpoint_timeout_seconds: float = 5.0,
    ) -> None:
        self.daemon_service = daemon_service
        self.process_service = process_service
        self.working_directory = str(Path(working_directory).resolve())
        self.shell_resolver = shell_resolver
        self.python_executable = python_executable or sys.executable
        self.endpoint_probe = endpoint_probe or _default_endpoint_probe
        self.endpoint_timeout_seconds = max(float(endpoint_timeout_seconds), 0.1)
        self._managed_env_keys = (
            "PYTHONPATH",
            "APP_DATABASE_URL",
            "APP_DAEMON_STATE_DIR",
            "APP_EVENTS_STATE_DIR",
            "APP_OPERATIONS_STATE_DIR",
            "APP_CHANNELS_STATE_DIR",
            "APP_ARTIFACT_STORE_DIR",
            "APP_BROWSER_STATE_DIR",
            "APP_MOBILE_STATE_DIR",
            "APP_EVENTS_BACKEND",
            "APP_EVENTS_REDIS_URL",
            "APP_EVENTS_REDIS_KEY_PREFIX",
            "APP_EVENTS_REDIS_BLOCK_MS",
            "APP_EVENTS_REDIS_DEDUPE_TTL_SECONDS",
            "APP_ORCHESTRATION_RUN_LEASE_SECONDS",
            "APP_ORCHESTRATION_RUN_HEARTBEAT_SECONDS",
            "APP_ORCHESTRATION_EXECUTOR_MAX_CONCURRENT_ASSIGNMENTS",
            "APP_TOOL_RUN_LEASE_SECONDS",
            "APP_TOOL_RUN_HEARTBEAT_SECONDS",
            "APP_TOOL_WORKER_MAX_IN_FLIGHT",
            "APP_TOOL_WORKER_DEFAULT_RUN_CONCURRENCY",
            "APP_TOOL_WORKER_IMAGE_RUN_CONCURRENCY",
            "APP_TOOL_WORKER_SHARED_STATE_RUN_CONCURRENCY",
        )

    def list_instances(
        self,
        *,
        service_key: str | None = None,
        refresh: bool = True,
    ) -> tuple[DaemonInstance, ...]:
        if service_key is not None and refresh:
            return self.refresh_service(service_key)
        instances = self.daemon_service.list_instances(service_key=service_key)
        if not refresh:
            return instances
        refreshed: list[DaemonInstance] = []
        for spec in self.daemon_service.list_service_specs():
            refreshed.extend(self.refresh_service(spec.key))
        if service_key is None:
            return tuple(refreshed)
        normalized_key = service_key.strip().lower()
        return tuple(instance for instance in refreshed if instance.service_key == normalized_key)

    def resolve_reconcile_service_keys(
        self,
        *,
        service_set_keys: tuple[str, ...] = (),
        service_keys: tuple[str, ...] = (),
        service_roles: tuple[str, ...] = (),
        service_groups: tuple[str, ...] = (),
        include_eager: bool = True,
    ) -> tuple[str, ...]:
        ordered_keys: list[str] = []

        def _push(key: str) -> None:
            normalized = key.strip().lower()
            if not normalized or normalized in ordered_keys:
                return
            ordered_keys.append(normalized)

        if include_eager:
            for spec in self.daemon_service.list_service_specs():
                if spec.start_policy == "eager":
                    _push(spec.key)
        for service_set_key in service_set_keys:
            service_set = self.daemon_service.get_service_set(service_set_key)
            for role in service_set.service_roles:
                for spec in self.daemon_service.list_service_specs(role=role):
                    _push(spec.key)
            for group in service_set.service_groups:
                for spec in self.daemon_service.list_service_specs(service_group=group):
                    _push(spec.key)
            for key in service_set.service_keys:
                _push(key)
        for role in service_roles:
            for spec in self.daemon_service.list_service_specs(role=role):
                _push(spec.key)
        for group in service_groups:
            for spec in self.daemon_service.list_service_specs(service_group=group):
                _push(spec.key)
        for key in service_keys:
            _push(key)
        return tuple(ordered_keys)

    def refresh_service(self, service_key: str) -> tuple[DaemonInstance, ...]:
        spec = self.daemon_service.get_service_spec(service_key)
        self._discover_existing_instances(spec)
        instances = list(self.daemon_service.list_instances(service_key=spec.key))
        refreshed_instances = [self._refresh_instance(spec, instance) for instance in instances]
        refreshed_instances = [self._refresh_endpoint_health(spec, instance) for instance in refreshed_instances]
        for instance in refreshed_instances:
            self.daemon_service.save_instance(instance)
        return tuple(refreshed_instances)

    def healthcheck_service(self, service_key: str) -> tuple[DaemonInstance, ...]:
        spec = self.daemon_service.get_service_spec(service_key)
        if self._supports_process_management(spec) or self._supports_endpoint_healthcheck(spec):
            return self.refresh_service(spec.key)
        return self.daemon_service.list_instances(service_key=spec.key)

    def ensure_service(self, service_key: str) -> tuple[DaemonInstance, ...]:
        spec = self.daemon_service.get_service_spec(service_key)
        if not self._supports_process_management(spec):
            if self._supports_endpoint_healthcheck(spec):
                return self.healthcheck_service(spec.key)
            raise DaemonValidationError(
                f"Daemon service '{spec.key}' does not support process-backed ensure.",
            )
        instances = list(self.refresh_service(spec.key))
        active_instances = [
            instance
            for instance in instances
            if instance.status in {"starting", "ready", "degraded"}
        ]
        while len(active_instances) < spec.desired_replicas:
            started = self._start_process_instance(spec, ordinal=len(instances) + 1)
            instances.append(started)
            active_instances.append(started)
        return tuple(instances)

    def reconcile_service(self, service_key: str) -> tuple[DaemonInstance, ...]:
        spec = self.daemon_service.get_service_spec(service_key)
        if not self._supports_process_management(spec):
            return self.healthcheck_service(spec.key)
        instances = list(self.refresh_service(spec.key))
        instances = [self._reconcile_runtime_environment(spec, instance) for instance in instances]
        active_instances = [
            instance
            for instance in instances
            if instance.status in {"starting", "ready", "degraded"}
        ]
        while len(active_instances) < spec.desired_replicas:
            started = self._start_process_instance(spec, ordinal=len(instances) + 1)
            instances.append(started)
            active_instances.append(started)
        if len(active_instances) > spec.desired_replicas:
            for instance in active_instances[spec.desired_replicas :]:
                process_id = self._process_id(instance)
                if process_id is not None:
                    try:
                        session = self.process_service.terminate_session(process_id=process_id)
                    except ProcessNotFoundError:
                        session = None
                    instance = self._merge_process_status(spec, instance, session)
                instance.mark_stopped()
                self.daemon_service.save_instance(instance)
        return self.daemon_service.list_instances(service_key=spec.key)

    def ensure_eager_services(self) -> tuple[DaemonInstance, ...]:
        ensured: list[DaemonInstance] = []
        for spec in self.daemon_service.list_service_specs():
            if spec.start_policy != "eager":
                continue
            ensured.extend(self.ensure_service(spec.key))
        return tuple(ensured)

    def reconcile_eager_services(self) -> tuple[DaemonInstance, ...]:
        reconciled: list[DaemonInstance] = []
        for spec in self.daemon_service.list_service_specs():
            if spec.start_policy != "eager":
                continue
            reconciled.extend(self.reconcile_service(spec.key))
        return tuple(reconciled)

    def stop_service(self, service_key: str) -> tuple[DaemonInstance, ...]:
        spec = self.daemon_service.get_service_spec(service_key)
        instances = list(self.daemon_service.list_instances(service_key=spec.key))
        stopped: list[DaemonInstance] = []
        for instance in instances:
            process_id = self._process_id(instance)
            if process_id is None and instance.status in {"stopped", "failed"}:
                continue
            if process_id is not None:
                try:
                    session = self.process_service.terminate_session(process_id=process_id)
                except ProcessNotFoundError:
                    session = None
                instance = self._merge_process_status(spec, instance, session)
            instance.mark_stopped()
            self.daemon_service.save_instance(instance)
            stopped.append(instance)
        return tuple(stopped)

    def _supports_process_management(self, spec: DaemonServiceSpec) -> bool:
        return spec.transport == "process" and spec.managed_by == "internal"

    def _supports_endpoint_healthcheck(self, spec: DaemonServiceSpec) -> bool:
        return spec.healthcheck_policy == "cdp-version" and bool(self._service_endpoint(spec))

    def _process_id(self, instance: DaemonInstance) -> str | None:
        process_id = instance.metadata.get("process_id")
        if not isinstance(process_id, str):
            return None
        normalized = process_id.strip().lower()
        return normalized or None

    def _service_endpoint(self, spec: DaemonServiceSpec) -> str | None:
        raw = spec.metadata.get("server_url")
        if not isinstance(raw, str):
            return None
        normalized = raw.strip()
        return normalized or None

    def _service_instance_id(self, spec: DaemonServiceSpec) -> str:
        return f"daemon-{spec.key.replace(':', '-')}"

    def _find_matching_instance_for_process_session(
        self,
        *,
        spec: DaemonServiceSpec,
        session: ProcessSession,
    ) -> DaemonInstance | None:
        process_id = session.id.strip().lower()
        daemon_worker_id = session.metadata.get("daemon_worker_id")
        normalized_worker_id = (
            daemon_worker_id.strip()
            if isinstance(daemon_worker_id, str) and daemon_worker_id.strip()
            else None
        )
        instances = self.daemon_service.list_instances(service_key=spec.key)
        for instance in instances:
            if self._process_id(instance) == process_id:
                return instance
        if normalized_worker_id is not None:
            for instance in instances:
                if instance.worker_id == normalized_worker_id:
                    return instance
        if spec.replica_mode == "singleton" and instances:
            return instances[0]
        return None

    def _discover_process_sessions(self, spec: DaemonServiceSpec) -> tuple[DaemonInstance, ...]:
        if not self._supports_process_management(spec):
            return ()
        discovered: list[DaemonInstance] = []
        session_key = f"daemon:{spec.key}"
        list_sessions = getattr(self.process_service, "list_sessions_metadata", None)
        if list_sessions is None:
            list_sessions = self.process_service.list_sessions
        for session in list_sessions():
            if not session.is_running:
                continue
            if (session.session_key or "").strip().lower() != session_key:
                continue
            instance = self._find_matching_instance_for_process_session(spec=spec, session=session)
            if instance is None:
                daemon_worker_id = session.metadata.get("daemon_worker_id")
                instance = DaemonInstance.create(
                    service_key=spec.key,
                    worker_id=daemon_worker_id if isinstance(daemon_worker_id, str) else None,
                    pid=session.pid,
                    endpoint=self._service_endpoint(spec),
                    metadata={},
                )
            metadata = dict(instance.metadata)
            metadata["process_id"] = session.id
            metadata["command"] = session.command
            metadata["session_key"] = session.session_key
            self._copy_process_paths(metadata, session)
            if isinstance(session.metadata.get("env_fingerprint"), str):
                metadata["env_fingerprint"] = session.metadata["env_fingerprint"]
            if isinstance(session.metadata.get("env_keys"), list):
                metadata["env_keys"] = list(session.metadata["env_keys"])
            instance.metadata = metadata
            instance.mark_ready(pid=session.pid, endpoint=self._service_endpoint(spec))
            self.daemon_service.save_instance(instance)
            discovered.append(instance)
        return tuple(discovered)

    def _discover_endpoint_instance(self, spec: DaemonServiceSpec) -> DaemonInstance | None:
        endpoint = self._service_endpoint(spec)
        if endpoint is None:
            return None
        instances = self.daemon_service.list_instances(service_key=spec.key)
        if instances:
            instance = instances[0]
        else:
            if self._supports_process_management(spec):
                return None
            instance_id = self._service_instance_id(spec)
            try:
                instance = self.daemon_service.get_instance(instance_id)
            except DaemonNotFoundError:
                instance = DaemonInstance(
                    id=instance_id,
                    service_key=spec.key,
                    status="stopped",
                    endpoint=endpoint,
                    metadata={},
                )
        instance.endpoint = endpoint
        metadata = dict(instance.metadata)
        metadata["server_url"] = endpoint
        instance.metadata = metadata
        self.daemon_service.save_instance(instance)
        return instance

    def _discover_existing_instances(self, spec: DaemonServiceSpec) -> tuple[DaemonInstance, ...]:
        discovered: list[DaemonInstance] = []
        discovered.extend(self._discover_process_sessions(spec))
        endpoint_instance = self._discover_endpoint_instance(spec)
        if endpoint_instance is not None:
            discovered.append(endpoint_instance)
        return tuple(discovered)

    def _refresh_endpoint_health(
        self,
        spec: DaemonServiceSpec,
        instance: DaemonInstance,
    ) -> DaemonInstance:
        if not self._supports_endpoint_healthcheck(spec):
            return instance
        if self._supports_process_management(spec) and self._process_id(instance) is None:
            return instance
        endpoint = instance.endpoint or self._service_endpoint(spec)
        if endpoint is None:
            return instance
        updated = replace(instance)
        try:
            self.endpoint_probe(
                endpoint=endpoint,
                healthcheck_policy=spec.healthcheck_policy or "",
                timeout_seconds=self.endpoint_timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            if self._supports_process_management(spec) and self._process_id(updated) is not None:
                updated.mark_degraded(str(exc))
            else:
                updated.mark_failed(str(exc))
            return updated
        updated.mark_ready(pid=updated.pid, endpoint=endpoint)
        return updated

    def _refresh_instance(
        self,
        spec: DaemonServiceSpec,
        instance: DaemonInstance,
    ) -> DaemonInstance:
        if not self._supports_process_management(spec):
            return instance
        process_id = self._process_id(instance)
        if process_id is None:
            updated = replace(instance)
            if updated.status != "stopped":
                updated.mark_stopped()
            return updated
        try:
            session = self.process_service.get_session(process_id=process_id)
        except ProcessNotFoundError:
            updated = replace(instance)
            updated.mark_failed("process session was not found")
            return updated
        return self._merge_process_status(spec, instance, session)

    def _merge_process_status(
        self,
        spec: DaemonServiceSpec,
        instance: DaemonInstance,
        session: ProcessSession | None,
    ) -> DaemonInstance:
        updated = replace(instance)
        if session is None:
            self._clear_process_runtime(updated)
            updated.mark_stopped()
            return updated
        updated.pid = session.pid
        updated.metadata = {
            **updated.metadata,
            "process_id": session.id,
            "command": session.command,
            "session_key": session.session_key,
        }
        self._copy_process_paths(updated.metadata, session)
        if session.status is ProcessStatus.RUNNING:
            updated.mark_ready(pid=session.pid)
            return updated
        if session.status is ProcessStatus.EXITED:
            self._clear_process_runtime(updated)
            updated.mark_stopped(now=session.ended_at)
            return updated
        if session.status is ProcessStatus.KILLED:
            self._clear_process_runtime(updated)
            updated.mark_stopped(now=session.ended_at)
            return updated
        self._clear_process_runtime(updated)
        updated.mark_failed(
            f"process exited with status={session.status.value} code={session.exit_code}",
            now=session.ended_at,
        )
        return updated

    def _clear_process_runtime(self, instance: DaemonInstance) -> None:
        instance.pid = None
        metadata = dict(instance.metadata)
        metadata.pop("process_id", None)
        metadata.pop("command", None)
        metadata.pop("session_key", None)
        instance.metadata = metadata

    def _start_process_instance(self, spec: DaemonServiceSpec, *, ordinal: int) -> DaemonInstance:
        worker_id = self._derive_worker_id(spec, ordinal=ordinal)
        command = self._build_process_command(spec, worker_id=worker_id)
        env_keys = self._env_keys_for_spec(spec)
        env_fingerprint = self._env_fingerprint(env_keys)
        metadata = {
            "daemon_service_key": spec.key,
            "env_fingerprint": env_fingerprint,
            "env_keys": list(env_keys),
        }
        if worker_id is not None:
            metadata["daemon_worker_id"] = worker_id
        session = self.process_service.start_command(
            command=command,
            shell=self.shell_resolver(),
            working_directory=self.working_directory,
            session_key=f"daemon:{spec.key}",
            metadata=metadata,
        )
        instance = DaemonInstance.create(
            service_key=spec.key,
            worker_id=worker_id,
            pid=session.pid,
            metadata={
                "process_id": session.id,
                "command": session.command,
                "session_key": session.session_key,
                "env_fingerprint": env_fingerprint,
                "env_keys": list(env_keys),
                **self._process_paths(session),
            },
        )
        instance.mark_ready(pid=session.pid)
        self.daemon_service.save_instance(instance)
        return instance

    def _reconcile_runtime_environment(
        self,
        spec: DaemonServiceSpec,
        instance: DaemonInstance,
    ) -> DaemonInstance:
        if not self._supports_process_management(spec):
            return instance
        process_id = self._process_id(instance)
        if process_id is None:
            return instance
        env_keys = self._env_keys_for_spec(spec)
        expected = self._env_fingerprint(env_keys)
        actual = instance.metadata.get("env_fingerprint")
        if actual == expected:
            return instance
        try:
            session = self.process_service.terminate_session(process_id=process_id)
        except ProcessNotFoundError:
            session = None
        updated = self._merge_process_status(spec, instance, session)
        updated.mark_stopped()
        updated.metadata = {
            **dict(updated.metadata),
            "env_drift_detected": True,
            "expected_env_fingerprint": expected,
            "actual_env_fingerprint": actual,
            "env_keys": list(env_keys),
        }
        self.daemon_service.save_instance(updated)
        return updated

    def _env_fingerprint(self, env_keys: tuple[str, ...]) -> str:
        payload = {
            key: os.environ.get(key)
            for key in env_keys
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _env_keys_for_spec(self, spec: DaemonServiceSpec) -> tuple[str, ...]:
        resolved = list(self._managed_env_keys)
        raw = spec.metadata.get("env_keys")
        if isinstance(raw, list):
            for item in raw:
                if not isinstance(item, str):
                    continue
                normalized = item.strip()
                if normalized and normalized not in resolved:
                    resolved.append(normalized)
        return tuple(resolved)

    def _derive_worker_id(self, spec: DaemonServiceSpec, *, ordinal: int) -> str | None:
        if spec.role != "worker":
            return None
        label = spec.key.replace(":", "-")
        return f"{label}-{ordinal}"

    def _build_process_command(self, spec: DaemonServiceSpec, *, worker_id: str | None) -> str:
        command_argv = spec.metadata.get("command_argv")
        if isinstance(command_argv, list) and all(isinstance(item, str) for item in command_argv):
            if worker_id is not None:
                raise DaemonValidationError(
                    f"Daemon service '{spec.key}' cannot mix worker_id with raw command_argv.",
                )
            return shlex.join(command_argv)
        cli_args = spec.metadata.get("cli_args")
        if not isinstance(cli_args, list) or not all(isinstance(item, str) for item in cli_args):
            raise DaemonValidationError(
                f"Daemon service '{spec.key}' is missing string cli_args or command_argv metadata.",
            )
        argv: list[str] = [
            self.python_executable,
            "-m",
            "crxzipple.main",
            *cli_args,
        ]
        if worker_id is not None:
            argv.extend(["--worker-id", worker_id])
        command = shlex.join(argv)
        env_prefix = self._managed_env_prefix(self._env_keys_for_spec(spec))
        return f"{env_prefix} {command}".strip() if env_prefix else command

    def _copy_process_paths(
        self,
        metadata: dict[str, object],
        session: ProcessSession,
    ) -> None:
        metadata.update(self._process_paths(session))

    def _process_paths(self, session: ProcessSession) -> dict[str, object]:
        copied: dict[str, object] = {}
        for key in (
            "process_store_root",
            "session_dir",
            "stdout_path",
            "stderr_path",
            "exit_code_path",
        ):
            value = session.metadata.get(key)
            if isinstance(value, str) and value.strip():
                copied[key] = value
        return copied

    def _managed_env_prefix(self, env_keys: tuple[str, ...]) -> str:
        parts: list[str] = []
        for key in env_keys:
            value = os.environ.get(key)
            if value is None or not str(value).strip():
                continue
            parts.append(f"{key}={shlex.quote(str(value))}")
        return " ".join(parts)


def _default_endpoint_probe(
    *,
    endpoint: str,
    healthcheck_policy: str,
    timeout_seconds: float,
) -> None:
    normalized_policy = healthcheck_policy.strip().lower()
    if normalized_policy == "cdp-version":
        probe_url = urljoin(endpoint.rstrip("/") + "/", "json/version")
    else:
        raise DaemonValidationError(
            f"Unsupported daemon endpoint healthcheck policy '{healthcheck_policy}'.",
        )
    try:
        response = request_url("GET", probe_url, timeout=timeout_seconds)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise DaemonValidationError(
            f"Endpoint healthcheck failed for {probe_url}: {exc}",
        ) from exc
