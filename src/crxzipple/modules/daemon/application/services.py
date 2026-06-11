from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from crxzipple.modules.daemon.domain import (
    DaemonInstance,
    DaemonLease,
    DaemonNotFoundError,
    DaemonServiceSetSpec,
    DaemonServiceSpec,
    utcnow,
    DaemonValidationError,
)

_MAX_INACTIVE_INSTANCE_HISTORY_PER_SERVICE = 8
_MAX_INACTIVE_LEASE_HISTORY_PER_SERVICE = 128
_LEASE_DEPTH_METADATA_KEY = "_lease_depth"
_ACTIVE_INSTANCE_STATUSES = frozenset({"starting", "ready", "degraded", "stopping"})


def _spec_server_url(spec: DaemonServiceSpec) -> str | None:
    raw = spec.metadata.get("server_url")
    if not isinstance(raw, str):
        return None
    normalized = raw.strip()
    return normalized or None


DEFAULT_DAEMON_SERVICE_SETS: tuple[DaemonServiceSetSpec, ...] = (
    DaemonServiceSetSpec(
        key="workers",
        display_name="Workers",
        description="Core runtime worker daemons managed by the dev/runtime stack.",
        service_keys=(
            "worker:orchestration-scheduler",
            "worker:orchestration",
            "worker:event-outbox",
            "worker:event-relay",
            "worker:operations-observer",
            "worker:tool-scheduler",
            "worker:tool",
        ),
    ),
    DaemonServiceSetSpec(
        key="orchestration-runtime",
        display_name="Orchestration Runtime",
        description=(
            "Scheduler and executor runtimes for orchestration runs."
        ),
        service_keys=(
            "worker:orchestration-scheduler",
            "worker:orchestration",
        ),
    ),
    DaemonServiceSetSpec(
        key="operations-runtime",
        display_name="Operations Runtime",
        description="Observer runtime for operations read models.",
        service_keys=("worker:operations-observer",),
    ),
    DaemonServiceSetSpec(
        key="channels-stack",
        display_name="Channels",
        description="Managed channel runtime processes.",
        service_groups=("channels",),
    ),
    DaemonServiceSetSpec(
        key="browser-stack",
        display_name="Browser Stack",
        description="Managed browser host processes; lazy browser capabilities remain explicit.",
        service_groups=("browser",),
    ),
    DaemonServiceSetSpec(
        key="ocr-stack",
        display_name="OCR Stack",
        description="Managed OCR host capabilities.",
        service_groups=("ocr",),
    ),
)


class DaemonServiceSpecStore(Protocol):
    def load(self) -> tuple[DaemonServiceSpec, ...]:
        ...

    def save(self, specs: tuple[DaemonServiceSpec, ...]) -> tuple[DaemonServiceSpec, ...]:
        ...


class DaemonInstanceStore(Protocol):
    def list(self) -> tuple[DaemonInstance, ...]:
        ...

    def save(self, instances: tuple[DaemonInstance, ...]) -> tuple[DaemonInstance, ...]:
        ...


class DaemonLeaseStore(Protocol):
    def list(self) -> tuple[DaemonLease, ...]:
        ...

    def save(self, leases: tuple[DaemonLease, ...]) -> tuple[DaemonLease, ...]:
        ...


class DaemonLeaseEventLog(Protocol):
    def append(self, records: tuple[dict[str, object], ...]) -> None:
        ...


def _lease_depth(lease: DaemonLease) -> int:
    raw = lease.metadata.get(_LEASE_DEPTH_METADATA_KEY, 1)
    try:
        return max(int(raw), 1)
    except (TypeError, ValueError):
        return 1


def _set_lease_depth(lease: DaemonLease, depth: int) -> None:
    updated_metadata = dict(lease.metadata)
    updated_metadata[_LEASE_DEPTH_METADATA_KEY] = max(int(depth), 1)
    lease.metadata = updated_metadata


class DaemonApplicationService:
    def __init__(
        self,
        *,
        service_spec_store: DaemonServiceSpecStore,
        instance_store: DaemonInstanceStore,
        lease_store: DaemonLeaseStore,
        lease_event_log: DaemonLeaseEventLog | None = None,
        service_sets: tuple[DaemonServiceSetSpec, ...] = DEFAULT_DAEMON_SERVICE_SETS,
    ) -> None:
        self.service_spec_store = service_spec_store
        self.instance_store = instance_store
        self.lease_store = lease_store
        self.lease_event_log = lease_event_log
        self.service_sets = tuple(service_sets)

    def _update_service_specs(
        self,
        mutator: Callable[[tuple[DaemonServiceSpec, ...]], tuple[DaemonServiceSpec, ...]],
    ) -> tuple[DaemonServiceSpec, ...]:
        updater = getattr(self.service_spec_store, "update", None)
        if callable(updater):
            return tuple(updater(mutator))
        current = self.service_spec_store.load()
        updated = tuple(mutator(current))
        self.service_spec_store.save(updated)
        return updated

    def _update_instances(
        self,
        mutator: Callable[[tuple[DaemonInstance, ...]], tuple[DaemonInstance, ...]],
    ) -> tuple[DaemonInstance, ...]:
        def _mutate_and_compact(
            instances: tuple[DaemonInstance, ...],
        ) -> tuple[DaemonInstance, ...]:
            updated = tuple(mutator(instances))
            return self._compact_instances_in_memory(updated)

        updater = getattr(self.instance_store, "update", None)
        if callable(updater):
            return tuple(updater(_mutate_and_compact))
        current = self.instance_store.list()
        updated = _mutate_and_compact(current)
        self.instance_store.save(updated)
        return updated

    def _update_leases(
        self,
        mutator: Callable[[tuple[DaemonLease, ...]], tuple[DaemonLease, ...]],
    ) -> tuple[DaemonLease, ...]:
        def _mutate_and_compact(
            leases: tuple[DaemonLease, ...],
        ) -> tuple[DaemonLease, ...]:
            updated = tuple(mutator(leases))
            return self._compact_leases_in_memory(updated)

        updater = getattr(self.lease_store, "update", None)
        if callable(updater):
            return tuple(updater(_mutate_and_compact))
        current = self.lease_store.list()
        updated = _mutate_and_compact(current)
        self.lease_store.save(updated)
        return updated

    def _expire_leases_in_memory(
        self,
        leases: tuple[DaemonLease, ...],
    ) -> tuple[DaemonLease, ...]:
        updated_leases = list(leases)
        now = utcnow()
        for index, lease in enumerate(updated_leases):
            if lease.status != "active" or lease.expires_at is None:
                continue
            if lease.expires_at > now:
                continue
            updated = replace(lease)
            updated.expire()
            updated_leases[index] = updated
            self._append_lease_event("expired", updated)
        return tuple(updated_leases)

    def _compact_leases_in_memory(
        self,
        leases: tuple[DaemonLease, ...],
    ) -> tuple[DaemonLease, ...]:
        active: list[DaemonLease] = []
        inactive_by_service: dict[str, list[DaemonLease]] = {}
        for lease in leases:
            if lease.status == "active":
                active.append(lease)
                continue
            inactive_by_service.setdefault(lease.service_key, []).append(lease)

        compacted = list(active)
        for service_key in sorted(inactive_by_service):
            history = inactive_by_service[service_key]
            history.sort(
                key=lambda lease: (
                    lease.heartbeat_at or lease.expires_at or lease.acquired_at,
                    lease.acquired_at,
                    lease.id,
                ),
                reverse=True,
            )
            compacted.extend(history[:_MAX_INACTIVE_LEASE_HISTORY_PER_SERVICE])
        return tuple(compacted)

    def _compact_instances_in_memory(
        self,
        instances: tuple[DaemonInstance, ...],
    ) -> tuple[DaemonInstance, ...]:
        active: list[DaemonInstance] = []
        inactive_by_service: dict[str, list[DaemonInstance]] = {}
        for instance in instances:
            if instance.status in _ACTIVE_INSTANCE_STATUSES:
                active.append(instance)
                continue
            inactive_by_service.setdefault(instance.service_key, []).append(instance)

        compacted = list(active)
        for service_key in sorted(inactive_by_service):
            history = inactive_by_service[service_key]
            history.sort(
                key=lambda instance: (
                    instance.last_healthcheck_at
                    or instance.started_at
                    or datetime.min.replace(tzinfo=timezone.utc),
                    instance.started_at or datetime.min.replace(tzinfo=timezone.utc),
                    instance.id,
                ),
                reverse=True,
            )
            compacted.extend(history[:_MAX_INACTIVE_INSTANCE_HISTORY_PER_SERVICE])
        return tuple(compacted)

    def _append_lease_event(self, event_kind: str, lease: DaemonLease) -> None:
        if self.lease_event_log is None:
            return
        self.lease_event_log.append(
            (
                {
                    "event_kind": event_kind,
                    "lease_id": lease.id,
                    "service_key": lease.service_key,
                    "instance_id": lease.instance_id,
                    "owner_kind": lease.owner_kind,
                    "owner_id": lease.owner_id,
                    "status": lease.status,
                    "acquired_at": lease.acquired_at.isoformat(),
                    "heartbeat_at": lease.heartbeat_at.isoformat()
                    if lease.heartbeat_at
                    else None,
                    "expires_at": lease.expires_at.isoformat()
                    if lease.expires_at
                    else None,
                    "metadata": dict(lease.metadata),
                },
            ),
        )

    def list_service_sets(self) -> tuple[DaemonServiceSetSpec, ...]:
        return self.service_sets

    def get_service_set(self, key: str) -> DaemonServiceSetSpec:
        normalized_key = key.strip().lower()
        for service_set in self.service_sets:
            if service_set.key == normalized_key:
                return service_set
        raise DaemonNotFoundError(f"Daemon service set '{key}' is not registered.")

    def list_service_specs(
        self,
        *,
        role: str | None = None,
        service_group: str | None = None,
    ) -> tuple[DaemonServiceSpec, ...]:
        specs = self.service_spec_store.load()
        if role is not None:
            normalized_role = role.strip().lower()
            specs = tuple(spec for spec in specs if spec.role == normalized_role)
        if service_group is not None:
            normalized_group = service_group.strip().lower()
            specs = tuple(
                spec for spec in specs if (spec.service_group or "").strip().lower() == normalized_group
            )
        return specs

    def get_service_spec(self, key: str) -> DaemonServiceSpec:
        normalized_key = key.strip().lower()
        for spec in self.service_spec_store.load():
            if spec.key == normalized_key:
                return spec
        raise DaemonNotFoundError(f"Daemon service '{key}' is not registered.")

    def register_service_spec(self, spec: DaemonServiceSpec) -> DaemonServiceSpec:
        def _mutate(specs: tuple[DaemonServiceSpec, ...]) -> tuple[DaemonServiceSpec, ...]:
            updated_specs = list(specs)
            for index, existing in enumerate(updated_specs):
                if existing.key == spec.key:
                    updated_specs[index] = spec
                    return tuple(updated_specs)
            updated_specs.append(spec)
            return tuple(updated_specs)

        self._update_service_specs(_mutate)
        self._reconcile_instances_for_registered_spec(spec)
        return spec

    def _reconcile_instances_for_registered_spec(self, spec: DaemonServiceSpec) -> None:
        if spec.transport != "endpoint":
            return
        desired_endpoint = _spec_server_url(spec)

        def _mutate(instances: tuple[DaemonInstance, ...]) -> tuple[DaemonInstance, ...]:
            updated_instances: list[DaemonInstance] = []
            for instance in instances:
                if instance.service_key != spec.key:
                    updated_instances.append(instance)
                    continue
                updated = replace(instance)
                metadata = dict(updated.metadata)
                if desired_endpoint is None:
                    updated.endpoint = None
                    metadata.pop("server_url", None)
                    metadata.pop("cdp_url", None)
                    updated.metadata = metadata
                    updated.pid = None
                    updated.last_error = None
                    updated.mark_stopped()
                    updated_instances.append(updated)
                    continue
                if updated.endpoint != desired_endpoint or metadata.get("server_url") != desired_endpoint:
                    updated.endpoint = desired_endpoint
                    metadata["server_url"] = desired_endpoint
                    updated.metadata = metadata
                    updated.last_error = None
                    updated.mark_stopped()
                updated_instances.append(updated)
            return tuple(updated_instances)

        self._update_instances(_mutate)

    def remove_service_specs(
        self,
        predicate: Callable[[DaemonServiceSpec], bool],
    ) -> tuple[str, ...]:
        current_specs = self.service_spec_store.load()
        removed_keys = tuple(spec.key for spec in current_specs if predicate(spec))
        if not removed_keys:
            return ()
        removed_key_set = set(removed_keys)
        retire_keys = getattr(self.service_spec_store, "retire_keys", None)
        if callable(retire_keys):
            retire_keys(removed_keys)
        self._update_service_specs(
            lambda specs: tuple(spec for spec in specs if spec.key not in removed_key_set),
        )
        self._update_instances(
            lambda instances: tuple(
                instance for instance in instances if instance.service_key not in removed_key_set
            ),
        )
        self._update_leases(
            lambda leases: tuple(lease for lease in leases if lease.service_key not in removed_key_set),
        )
        return removed_keys

    def list_instances(self, *, service_key: str | None = None) -> tuple[DaemonInstance, ...]:
        instances = self._update_instances(lambda current: current)
        if service_key is None:
            return instances
        normalized_key = service_key.strip().lower()
        return tuple(instance for instance in instances if instance.service_key == normalized_key)

    def get_instance(self, instance_id: str) -> DaemonInstance:
        normalized_id = instance_id.strip().lower()
        for instance in self.instance_store.list():
            if instance.id == normalized_id:
                return instance
        raise DaemonNotFoundError(f"Daemon instance '{instance_id}' was not found.")

    def save_instance(self, instance: DaemonInstance) -> DaemonInstance:
        def _mutate(instances: tuple[DaemonInstance, ...]) -> tuple[DaemonInstance, ...]:
            updated_instances = list(instances)
            for index, existing in enumerate(updated_instances):
                if existing.id == instance.id:
                    updated_instances[index] = instance
                    return tuple(updated_instances)
            updated_instances.append(instance)
            return tuple(updated_instances)

        self._update_instances(_mutate)
        return instance

    def remove_instance(self, *, instance_id: str) -> None:
        normalized_id = instance_id.strip().lower()
        self._update_instances(
            lambda instances: tuple(
                instance
                for instance in instances
                if instance.id != normalized_id
            ),
        )

    def _service_instance_id(self, spec: DaemonServiceSpec) -> str:
        return f"daemon-{spec.key.replace(':', '-')}"

    def _load_or_create_service_instance(
        self,
        *,
        service_key: str,
        pid: int | None = None,
        endpoint: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DaemonInstance:
        spec = self.get_service_spec(service_key)
        existing_instances = self.list_instances(service_key=spec.key)
        if existing_instances:
            instance = existing_instances[0]
        else:
            instance_id = self._service_instance_id(spec)
            try:
                instance = self.get_instance(instance_id)
            except DaemonNotFoundError:
                instance = DaemonInstance(
                    id=instance_id,
                    service_key=spec.key,
                    status="stopped",
                    pid=pid,
                    endpoint=endpoint,
                    metadata={},
                )
        if endpoint is not None:
            instance.endpoint = endpoint
        elif instance.endpoint is None:
            raw_endpoint = spec.metadata.get("server_url")
            if isinstance(raw_endpoint, str) and raw_endpoint.strip():
                instance.endpoint = raw_endpoint.strip()
        if metadata:
            instance.metadata = {**instance.metadata, **dict(metadata)}
        return instance

    def report_service_ready(
        self,
        *,
        service_key: str,
        pid: int | None = None,
        endpoint: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DaemonInstance:
        instance = self._load_or_create_service_instance(
            service_key=service_key,
            pid=pid,
            endpoint=endpoint,
            metadata=metadata,
        )
        if instance.metadata.get("process_id"):
            instance.mark_ready(endpoint=instance.endpoint or endpoint)
        else:
            instance.mark_ready(pid=pid or instance.pid, endpoint=instance.endpoint or endpoint)
        return self.save_instance(instance)

    def report_service_failed(
        self,
        *,
        service_key: str,
        reason: str,
        pid: int | None = None,
        endpoint: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DaemonInstance:
        instance = self._load_or_create_service_instance(
            service_key=service_key,
            pid=pid,
            endpoint=endpoint,
            metadata=metadata,
        )
        instance.mark_failed(reason)
        return self.save_instance(instance)

    def report_service_stopped(
        self,
        *,
        service_key: str,
        clear_metadata_keys: tuple[str, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> tuple[DaemonInstance, ...]:
        instances = list(self.list_instances(service_key=service_key))
        if not instances:
            return ()
        stopped: list[DaemonInstance] = []
        for instance in instances:
            if clear_metadata_keys:
                updated_metadata = dict(instance.metadata)
                for key in clear_metadata_keys:
                    updated_metadata.pop(key, None)
                instance.metadata = updated_metadata
            if metadata:
                instance.metadata = {**instance.metadata, **dict(metadata)}
            instance.mark_stopped()
            stopped.append(self.save_instance(instance))
        return tuple(stopped)

    def _refresh_leases(self) -> tuple[DaemonLease, ...]:
        return self._update_leases(self._expire_leases_in_memory)

    def acquire_lease(
        self,
        *,
        service_key: str,
        owner_kind: str,
        owner_id: str,
        ttl_seconds: int | None = None,
        metadata: dict[str, object] | None = None,
    ) -> DaemonLease:
        spec = self.get_service_spec(service_key)
        normalized_owner_kind = owner_kind.strip().lower()
        normalized_owner_id = owner_id.strip().lower()
        candidates = tuple(
            instance
            for instance in self.list_instances(service_key=spec.key)
            if instance.status in {"ready", "degraded"}
        )
        acquired: DaemonLease | None = None

        def _mutate(leases: tuple[DaemonLease, ...]) -> tuple[DaemonLease, ...]:
            nonlocal acquired
            updated_leases = list(self._expire_leases_in_memory(leases))
            for index, lease in enumerate(updated_leases):
                if lease.service_key != spec.key or lease.status != "active":
                    continue
                if (
                    lease.owner_kind == normalized_owner_kind
                    and lease.owner_id == normalized_owner_id
                ):
                    updated = replace(lease)
                    _set_lease_depth(updated, _lease_depth(lease) + 1)
                    updated.heartbeat(ttl_seconds=ttl_seconds)
                    updated_leases[index] = updated
                    acquired = updated
                    return tuple(updated_leases)
                raise DaemonValidationError(
                    f"Daemon service '{spec.key}' is already leased by "
                    f"{lease.owner_kind}:{lease.owner_id}.",
                )
            if not candidates:
                raise DaemonNotFoundError(
                    f"Daemon service '{service_key}' does not have an active instance.",
                )
            acquired = DaemonLease.create(
                service_key=spec.key,
                instance_id=candidates[0].id,
                owner_kind=normalized_owner_kind,
                owner_id=normalized_owner_id,
                ttl_seconds=ttl_seconds,
                metadata=metadata,
            )
            _set_lease_depth(acquired, 1)
            updated_leases.append(acquired)
            return tuple(updated_leases)

        self._update_leases(_mutate)
        if acquired is None:
            raise DaemonValidationError(f"Failed to acquire daemon lease for '{service_key}'.")
        self._append_lease_event("acquired", acquired)
        return acquired

    def list_leases(self, *, service_key: str | None = None) -> tuple[DaemonLease, ...]:
        leases = self._refresh_leases()
        if service_key is None:
            return leases
        normalized_key = service_key.strip().lower()
        return tuple(lease for lease in leases if lease.service_key == normalized_key)

    def heartbeat_lease(self, lease_id: str, *, ttl_seconds: int | None = None) -> DaemonLease:
        normalized_id = lease_id.strip().lower()
        heartbeat: DaemonLease | None = None

        def _mutate(leases: tuple[DaemonLease, ...]) -> tuple[DaemonLease, ...]:
            nonlocal heartbeat
            updated_leases = list(leases)
            for index, lease in enumerate(updated_leases):
                if lease.id != normalized_id:
                    continue
                updated = replace(lease)
                updated.heartbeat(ttl_seconds=ttl_seconds)
                updated_leases[index] = updated
                heartbeat = updated
                return tuple(updated_leases)
            raise DaemonNotFoundError(f"Daemon lease '{lease_id}' was not found.")

        self._update_leases(_mutate)
        if heartbeat is None:
            raise DaemonNotFoundError(f"Daemon lease '{lease_id}' was not found.")
        return heartbeat

    def release_lease(self, lease_id: str) -> DaemonLease:
        normalized_id = lease_id.strip().lower()
        released: DaemonLease | None = None

        def _mutate(leases: tuple[DaemonLease, ...]) -> tuple[DaemonLease, ...]:
            nonlocal released
            updated_leases = list(leases)
            for index, lease in enumerate(updated_leases):
                if lease.id != normalized_id:
                    continue
                updated = replace(lease)
                depth = _lease_depth(lease)
                if depth > 1:
                    _set_lease_depth(updated, depth - 1)
                else:
                    updated.release()
                updated_leases[index] = updated
                released = updated
                return tuple(updated_leases)
            raise DaemonNotFoundError(f"Daemon lease '{lease_id}' was not found.")

        self._update_leases(_mutate)
        if released is None:
            raise DaemonNotFoundError(f"Daemon lease '{lease_id}' was not found.")
        if released.status == "released":
            self._append_lease_event("released", released)
        return released
