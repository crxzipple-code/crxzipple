from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, fields, is_dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol

from crxzipple.modules.tool.application.catalog_models import (
    ToolFunctionCatalogRecord,
    ToolFunctionRequirements,
    ToolFunctionStatus,
    ToolProviderBackendCandidate,
    ToolSourceCatalogKind,
    ToolSourceCatalogRecord,
    ToolSourceDiscoveryRunRecord,
    ToolSourceDiscoveryResult,
    ToolSourceDiscoveryStatus,
    ToolSourceStatus as CatalogToolSourceStatus,
)
from crxzipple.modules.tool.application.discovery import ToolDiscoveryService
from crxzipple.modules.tool.application.reconcile_service import (
    ToolCatalogReconcileResult,
    ToolCatalogReconcileService,
    ToolFunctionCatalogRepository,
)
from crxzipple.modules.tool.domain.entities import ToolProviderBackend, ToolSource
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.domain.repositories import ToolSourceRepository
from crxzipple.modules.tool.domain.value_objects import (
    ToolCatalogSourceKind,
    ToolFunctionRuntimeKind as DomainToolFunctionRuntimeKind,
    ToolProviderBackendStatus,
    ToolProviderCapability,
    ToolSourceStatus,
)
from crxzipple.shared.access import (
    AccessConsumerRef,
    AccessCredentialKind,
    AccessCredentialRequirementDeclaration,
    AccessCredentialRequirementSet,
    AccessCredentialSlotRef,
    AccessCredentialTransport,
    AccessSetupFlowHint,
    AccessSetupFlowKind,
)
from crxzipple.shared.domain import AggregateRoot, Event


class ToolSourceUnitOfWork(Protocol):
    tool_sources: ToolSourceRepository
    tool_source_discovery_runs: Any
    tool_function_catalog: ToolFunctionCatalogRepository
    tool_functions: Any
    tool_provider_backends: Any

    def __enter__(self) -> "ToolSourceUnitOfWork":
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        ...

    def commit(self) -> None:
        ...

    def collect(self, aggregate: AggregateRoot[Any]) -> None:
        ...


@dataclass(kw_only=True)
class _EventBuffer(AggregateRoot[str]):
    pass


class _UnitOfWorkEventPublisher:
    def __init__(self, uow: ToolSourceUnitOfWork) -> None:
        self._uow = uow
        self._buffer = _EventBuffer(id="tool.catalog.reconcile.events")

    def publish(self, event: Event) -> None:
        self._buffer.record_event(event)
        self._uow.collect(self._buffer)


@dataclass(frozen=True, slots=True)
class ToolSourceCommandResult:
    source: ToolSourceCatalogRecord
    changed: bool


@dataclass(frozen=True, slots=True)
class ToolFunctionCommandResult:
    function: ToolFunctionCatalogRecord
    changed: bool


@dataclass(frozen=True, slots=True)
class ToolSourceSyncResult:
    source: ToolSourceCatalogRecord
    discovery: ToolSourceDiscoveryResult | None = None
    reconcile: ToolCatalogReconcileResult | None = None
    skipped: bool = False
    error_message: str | None = None

    @property
    def changed(self) -> bool:
        return bool(
            self.reconcile is not None and self.reconcile.changed,
        )


@dataclass(frozen=True, slots=True)
class ToolSourceCatalogSyncResult:
    results: tuple[ToolSourceSyncResult, ...]

    @property
    def source_count(self) -> int:
        return len(self.results)

    @property
    def function_count(self) -> int:
        return sum(
            len(result.discovery.candidates)
            for result in self.results
            if result.discovery is not None
        )

    @property
    def changed_count(self) -> int:
        return sum(
            len(result.reconcile.changed)
            for result in self.results
            if result.reconcile is not None
        )

    @property
    def error_count(self) -> int:
        return sum(1 for result in self.results if result.error_message)


@dataclass(frozen=True, slots=True)
class ToolPromptBundleGroup:
    group_key: str
    title: str
    summary: str
    function_ids: tuple[str, ...]
    function_count: int
    capability_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ToolPromptBundle:
    source_id: str
    title: str
    summary: str
    source_kind: str
    function_ids: tuple[str, ...]
    function_count: int
    groups: tuple[ToolPromptBundleGroup, ...] = ()
    credential_requirement_count: int = 0
    runtime_requirement_count: int = 0
    capability_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


class ToolSourceQueryService:
    def __init__(self, uow_factory: Callable[[], ToolSourceUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def list_sources(
        self,
        *,
        kind: ToolSourceCatalogKind | str | None = None,
        status: CatalogToolSourceStatus | str | None = None,
    ) -> tuple[ToolSourceCatalogRecord, ...]:
        with self._uow_factory() as uow:
            sources = uow.tool_sources.list(
                kind=_domain_source_kind(kind) if kind is not None else None,
                status=_domain_source_status(status) if status is not None else None,
            )
            return tuple(_source_entity_to_record(source) for source in sources)

    def get_source(self, source_id: str) -> ToolSourceCatalogRecord | None:
        with self._uow_factory() as uow:
            source = uow.tool_sources.get(source_id)
            if source is None:
                return None
            return _source_entity_to_record(source)

    def list_discovery_runs(
        self,
        source_id: str,
        *,
        limit: int = 20,
    ) -> tuple[ToolSourceDiscoveryRunRecord, ...]:
        with self._uow_factory() as uow:
            return uow.tool_source_discovery_runs.list_by_source(
                source_id,
                limit=limit,
            )

    def list_functions(
        self,
        *,
        source_id: str | None = None,
        status: ToolFunctionStatus | str | None = None,
    ) -> tuple[ToolFunctionCatalogRecord, ...]:
        with self._uow_factory() as uow:
            functions = uow.tool_functions.list(
                source_id=source_id,
                status=status,
            )
            return tuple(_function_entity_to_record(function) for function in functions)

    def get_function(self, function_id: str) -> ToolFunctionCatalogRecord | None:
        with self._uow_factory() as uow:
            function = uow.tool_functions.get(function_id)
            if function is None:
                return None
            return _function_entity_to_record(function)

    def list_prompt_bundles(
        self,
        function_ids: Iterable[str],
    ) -> tuple[ToolPromptBundle, ...]:
        requested_ids = tuple(
            dict.fromkeys(
                str(function_id).strip()
                for function_id in function_ids
                if str(function_id).strip()
            ),
        )
        if not requested_ids:
            return ()

        with self._uow_factory() as uow:
            functions_by_id = uow.tool_functions.list_by_ids(requested_ids)
            function_records = []
            source_ids = []
            for function_id in requested_ids:
                function = functions_by_id.get(function_id)
                if function is None:
                    continue
                function_record = _function_entity_to_record(function)
                if (
                    function_record.status is not ToolFunctionStatus.ACTIVE
                    or not function_record.enabled
                ):
                    continue
                function_records.append(function_record)
                if function_record.source_id not in source_ids:
                    source_ids.append(function_record.source_id)

            sources_by_id = uow.tool_sources.list_by_ids(tuple(source_ids))

        source_records: dict[str, ToolSourceCatalogRecord] = {}
        function_records_by_source: dict[str, list[ToolFunctionCatalogRecord]] = {}
        ordered_source_ids: list[str] = []
        for function_record in function_records:
            source_record = source_records.get(function_record.source_id)
            if source_record is None:
                source = sources_by_id.get(function_record.source_id)
                if source is None:
                    continue
                source_record = _source_entity_to_record(source)
                if source_record.status is not CatalogToolSourceStatus.ACTIVE:
                    continue
                source_records[source_record.source_id] = source_record
                ordered_source_ids.append(source_record.source_id)
            function_records_by_source.setdefault(
                function_record.source_id,
                [],
            ).append(function_record)

        return tuple(
            _prompt_bundle_from_records(
                source_records[source_id],
                tuple(function_records_by_source.get(source_id, ())),
            )
            for source_id in ordered_source_ids
            if function_records_by_source.get(source_id)
        )

    def list_provider_backends(
        self,
        *,
        source_id: str | None = None,
        capability: ToolProviderCapability | str | None = None,
        status: ToolProviderBackendStatus | str | None = None,
    ) -> tuple[ToolProviderBackend, ...]:
        with self._uow_factory() as uow:
            return tuple(
                uow.tool_provider_backends.list(
                    source_id=source_id,
                    capability=capability,
                    status=status,
                ),
            )

    def get_provider_backend(self, backend_id: str) -> ToolProviderBackend | None:
        with self._uow_factory() as uow:
            return uow.tool_provider_backends.get(backend_id)


class ToolSourceCommandService:
    def __init__(self, uow_factory: Callable[[], ToolSourceUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def upsert_source(
        self,
        source: ToolSourceCatalogRecord,
        *,
        dry_run: bool = False,
    ) -> ToolSourceCommandResult:
        with self._uow_factory() as uow:
            existing = uow.tool_sources.get(source.source_id)
            merged = _merge_source(
                incoming=source,
                existing=existing,
                observed_at=_utc_now(),
            )
            changed = existing is None or _source_changed(existing, merged)
            if changed and not dry_run:
                merged.record_event(
                    _source_event(
                        (
                            "tool.source.created"
                            if existing is None
                            else "tool.source.updated"
                        ),
                        merged,
                        observed_at=merged.updated_at,
                        previous=_source_snapshot(existing),
                        changed_fields=_source_changed_fields(existing, merged),
                    ),
                )
                uow.tool_sources.upsert(merged)
                uow.collect(merged)
                uow.commit()
            return ToolSourceCommandResult(
                source=_source_entity_to_record(merged),
                changed=changed,
            )

    def create_source(
        self,
        source: ToolSourceCatalogRecord,
        *,
        dry_run: bool = False,
    ) -> ToolSourceCommandResult:
        _validate_owner_writable_source(source)
        with self._uow_factory() as uow:
            existing = uow.tool_sources.get(source.source_id)
            if existing is not None:
                raise ToolValidationError(
                    f"Tool source '{source.source_id}' already exists.",
                )
            entity = _source_record_to_entity(source, observed_at=_utc_now())
            if not dry_run:
                entity.record_event(
                    _source_event(
                        "tool.source.created",
                        entity,
                        observed_at=entity.created_at,
                    ),
                )
                uow.tool_sources.upsert(entity)
                uow.collect(entity)
                uow.commit()
            return ToolSourceCommandResult(
                source=_source_entity_to_record(entity),
                changed=True,
            )

    def update_source(
        self,
        source_id: str,
        source: ToolSourceCatalogRecord,
        *,
        dry_run: bool = False,
    ) -> ToolSourceCommandResult:
        if source.source_id != source_id.strip():
            raise ToolValidationError(
                "Tool source update source_id must match the route source_id.",
            )
        _validate_owner_writable_source(source)
        with self._uow_factory() as uow:
            existing = uow.tool_sources.get(source_id)
            if existing is None:
                raise ToolValidationError(
                    f"Tool source '{source_id}' does not exist.",
                )
            incoming = _source_record_to_entity(source, observed_at=_utc_now())
            incoming.status = existing.status
            incoming.last_discovered_at = existing.last_discovered_at
            incoming.last_discovery_status = existing.last_discovery_status
            updated = _merge_source(
                incoming=_source_entity_to_record(incoming),
                existing=existing,
                observed_at=_utc_now(),
            )
            changed = _source_changed(existing, updated)
            if changed and not dry_run:
                updated.record_event(
                    _source_event(
                        "tool.source.updated",
                        updated,
                        observed_at=updated.updated_at,
                        previous=_source_snapshot(existing),
                        changed_fields=_source_changed_fields(existing, updated),
                    ),
                )
                uow.tool_sources.upsert(updated)
                uow.collect(updated)
                uow.commit()
            return ToolSourceCommandResult(
                source=_source_entity_to_record(updated),
                changed=changed,
            )

    def disable_source(self, source_id: str) -> ToolSourceCommandResult:
        return self._set_source_status(source_id, ToolSourceStatus.DISABLED)

    def restore_source(self, source_id: str) -> ToolSourceCommandResult:
        return self._set_source_status(source_id, ToolSourceStatus.ACTIVE)

    def delete_source(self, source_id: str) -> ToolSourceCommandResult:
        return self._set_source_status(source_id, ToolSourceStatus.DELETED)

    def sync_sources(
        self,
        sources: tuple[ToolSourceCatalogRecord, ...],
        *,
        discovery_service: ToolDiscoveryService,
        deprecate_stale: bool = False,
        dry_run: bool = False,
    ) -> ToolSourceCatalogSyncResult:
        return ToolSourceCatalogSyncResult(
            results=tuple(
                self.sync_source(
                    source,
                    discovery_service=discovery_service,
                    deprecate_stale=deprecate_stale,
                    dry_run=dry_run,
                )
                for source in sources
            ),
        )

    def sync_source(
        self,
        source: ToolSourceCatalogRecord,
        *,
        discovery_service: ToolDiscoveryService,
        deprecate_stale: bool = False,
        dry_run: bool = False,
    ) -> ToolSourceSyncResult:
        current = self.upsert_source(source, dry_run=dry_run).source
        if current.status in {
            CatalogToolSourceStatus.DISABLED,
            CatalogToolSourceStatus.DELETED,
        }:
            return ToolSourceSyncResult(source=current, skipped=True)

        try:
            discovery = discovery_service.discover(current)
        except Exception as exc:
            discovery = ToolSourceDiscoveryResult.failed(
                source_id=current.source_id,
                error_message=str(exc),
            )

        with self._uow_factory() as uow:
            existing = uow.tool_sources.get(current.source_id)
            result_source = _merge_source(
                incoming=current,
                existing=existing,
                discovery=discovery,
                observed_at=discovery.discovered_at,
            )
            if not dry_run:
                result_source.record_event(
                    _source_event(
                        (
                            "tool.source.discovery_completed"
                            if discovery.status is ToolSourceDiscoveryStatus.COMPLETED
                            else "tool.source.discovery_failed"
                        ),
                        result_source,
                        observed_at=discovery.discovered_at,
                        previous=_source_snapshot(existing),
                        discovery=discovery,
                        changed_fields=_source_changed_fields(existing, result_source),
                    ),
                )
                uow.tool_sources.upsert(result_source)
                uow.tool_source_discovery_runs.add(
                    ToolSourceDiscoveryRunRecord.from_result(
                        source=_source_entity_to_record(result_source),
                        discovery=discovery,
                    ),
                )
                uow.collect(result_source)

            reconcile_result: ToolCatalogReconcileResult | None = None
            if discovery.status is ToolSourceDiscoveryStatus.COMPLETED:
                reconcile_result = ToolCatalogReconcileService(
                    uow.tool_function_catalog,
                    event_publisher=(
                        _UnitOfWorkEventPublisher(uow) if not dry_run else None
                    ),
                ).reconcile_discovery_result(
                    discovery,
                    deprecate_stale=deprecate_stale,
                    dry_run=dry_run,
                )
                _upsert_provider_backend_candidates(
                    uow.tool_provider_backends,
                    discovery.provider_backend_candidates,
                    observed_at=discovery.discovered_at,
                    dry_run=dry_run,
                )
            if not dry_run:
                uow.commit()

        return ToolSourceSyncResult(
            source=_source_entity_to_record(result_source),
            discovery=discovery,
            reconcile=reconcile_result,
            error_message=discovery.error_message,
        )

    def _set_source_status(
        self,
        source_id: str,
        status: ToolSourceStatus,
    ) -> ToolSourceCommandResult:
        with self._uow_factory() as uow:
            existing = uow.tool_sources.get(source_id)
            if existing is None:
                raise ToolValidationError(
                    f"Tool source '{source_id}' does not exist.",
                )
            if existing.status is status:
                return ToolSourceCommandResult(
                    source=_source_entity_to_record(existing),
                    changed=False,
                )
            now = _utc_now()
            previous = _source_snapshot(existing)
            existing.status = status
            existing.revision += 1
            existing.updated_at = now
            existing.record_event(
                _source_event(
                    _source_status_event_name(status),
                    existing,
                    observed_at=now,
                    previous=previous,
                    changed_fields=("status",),
                ),
            )
            uow.tool_sources.upsert(existing)
            uow.collect(existing)
            uow.commit()
            return ToolSourceCommandResult(
                source=_source_entity_to_record(existing),
                changed=True,
            )


class ToolFunctionCommandService:
    def __init__(self, uow_factory: Callable[[], ToolSourceUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def set_function_enabled(
        self,
        function_id: str,
        *,
        enabled: bool,
    ) -> ToolFunctionCommandResult:
        with self._uow_factory() as uow:
            function = uow.tool_functions.get(function_id)
            if function is None:
                raise ToolValidationError(
                    f"Tool function '{function_id}' does not exist.",
                )
            if function.status is ToolFunctionStatus.DELETED:
                raise ToolValidationError(
                    f"Tool function '{function_id}' is deleted.",
                )
            changed = function.enabled is not bool(enabled)
            if changed:
                function.enabled = bool(enabled)
                function.revision += 1
                function.updated_at = _utc_now()
                function.record_event(
                    _function_event(
                        (
                            "tool.function.enabled"
                            if function.enabled
                            else "tool.function.disabled"
                        ),
                        _function_entity_to_record(function),
                        observed_at=function.updated_at,
                        changed_fields=("enabled",),
                    ),
                )
                uow.tool_functions.upsert(function)
                uow.collect(function)
                uow.commit()
            return ToolFunctionCommandResult(
                function=_function_entity_to_record(function),
                changed=changed,
            )

    def update_function_policy(
        self,
        function_id: str,
        *,
        trust_policy: Mapping[str, Any],
        approval_policy: Mapping[str, Any],
        credential_binding_overrides: Mapping[str, str],
        required_effect_overrides: tuple[str, ...] | None,
    ) -> ToolFunctionCommandResult:
        with self._uow_factory() as uow:
            function = uow.tool_functions.get(function_id)
            if function is None:
                raise ToolValidationError(
                    f"Tool function '{function_id}' does not exist.",
                )
            if function.status is ToolFunctionStatus.DELETED:
                raise ToolValidationError(
                    f"Tool function '{function_id}' is deleted.",
                )
            current = _function_entity_to_record(function)
            updated = replace(
                current,
                trust_policy=trust_policy,
                approval_policy=approval_policy,
                credential_binding_overrides=credential_binding_overrides,
                required_effect_overrides=required_effect_overrides,
            )
            changed_fields = tuple(
                field_name
                for field_name, current_value, next_value in (
                    ("trust_policy", current.trust_policy, updated.trust_policy),
                    ("approval_policy", current.approval_policy, updated.approval_policy),
                    (
                        "credential_binding_overrides",
                        current.credential_binding_overrides,
                        updated.credential_binding_overrides,
                    ),
                    (
                        "required_effect_overrides",
                        current.required_effect_overrides,
                        updated.required_effect_overrides,
                    ),
                )
                if current_value != next_value
            )
            changed = bool(changed_fields)
            if changed:
                function.trust_policy = dict(updated.trust_policy)
                function.approval_policy = dict(updated.approval_policy)
                function.credential_binding_overrides = dict(
                    updated.credential_binding_overrides,
                )
                function.required_effect_overrides = (
                    tuple(updated.required_effect_overrides)
                    if updated.required_effect_overrides is not None
                    else None
                )
                function.revision += 1
                function.updated_at = _utc_now()
                function.record_event(
                    _function_event(
                        "tool.function.policy_updated",
                        _function_entity_to_record(function),
                        observed_at=function.updated_at,
                        changed_fields=changed_fields,
                    ),
                )
                uow.tool_functions.upsert(function)
                uow.collect(function)
                uow.commit()
            return ToolFunctionCommandResult(
                function=_function_entity_to_record(function),
                changed=changed,
            )


def _prompt_bundle_from_records(
    source: ToolSourceCatalogRecord,
    functions: tuple[ToolFunctionCatalogRecord, ...],
) -> ToolPromptBundle:
    prompt = _prompt_config(source)
    title = _prompt_text(prompt, "title") or source.display_name
    summary = (
        _prompt_text(prompt, "summary")
        or source.description
        or f"Tool bundle '{title}' exposed by source '{source.source_id}'."
    )
    return ToolPromptBundle(
        source_id=source.source_id,
        title=title,
        summary=summary,
        source_kind=source.kind.value,
        function_ids=tuple(function.function_id for function in functions),
        function_count=len(functions),
        groups=_prompt_bundle_groups(source, prompt, functions),
        credential_requirement_count=_credential_requirement_count(
            source,
            functions,
        ),
        runtime_requirement_count=_runtime_requirement_count(source, functions),
        capability_ids=_bundle_capability_ids(source, functions),
        metadata={
            "source_id": source.source_id,
            "source_kind": source.kind.value,
            "prompt": dict(prompt),
            "config_hash": source.config_hash,
            "function_ids": [function.function_id for function in functions],
        },
    )


def _prompt_config(source: ToolSourceCatalogRecord) -> Mapping[str, Any]:
    raw_prompt = source.config.get("prompt")
    if isinstance(raw_prompt, Mapping):
        return dict(raw_prompt)
    provider = source.config.get("provider")
    if isinstance(provider, Mapping):
        provider_prompt = provider.get("prompt")
        if isinstance(provider_prompt, Mapping):
            return dict(provider_prompt)
    return {}


def _prompt_bundle_groups(
    source: ToolSourceCatalogRecord,
    prompt: Mapping[str, Any],
    functions: tuple[ToolFunctionCatalogRecord, ...],
) -> tuple[ToolPromptBundleGroup, ...]:
    raw_groups = prompt.get("groups")
    function_by_id = {function.function_id: function for function in functions}
    groups: list[tuple[int, int, ToolPromptBundleGroup]] = []
    grouped_function_ids: set[str] = set()
    if isinstance(raw_groups, Mapping):
        for index, (raw_group_key, raw_group) in enumerate(raw_groups.items()):
            group_key = str(raw_group_key).strip()
            if not group_key or not isinstance(raw_group, Mapping):
                continue
            declared_function_ids = _prompt_group_function_ids(raw_group)
            group_functions = tuple(
                function_by_id[function_id]
                for function_id in declared_function_ids
                if function_id in function_by_id
            )
            if not group_functions:
                continue
            grouped_function_ids.update(function.function_id for function in group_functions)
            title = _prompt_text(raw_group, "title") or group_key.replace("_", " ").title()
            summary = (
                _prompt_text(raw_group, "summary")
                or f"Tool functions in the '{title}' group."
            )
            order = _prompt_group_order(raw_group, fallback=1000 + index)
            groups.append(
                (
                    order,
                    index,
                    ToolPromptBundleGroup(
                        group_key=group_key,
                        title=title,
                        summary=summary,
                        function_ids=tuple(
                            function.function_id for function in group_functions
                        ),
                        function_count=len(group_functions),
                        capability_ids=_function_capability_ids(group_functions),
                        metadata={
                            "group_key": group_key,
                            "order": order,
                            "function_ids": [
                                function.function_id for function in group_functions
                            ],
                            **_prompt_group_metadata(raw_group),
                        },
                    ),
                ),
            )
    ungrouped_functions = tuple(
        function
        for function in functions
        if function.function_id not in grouped_function_ids
    )
    if ungrouped_functions:
        group_key = "source" if not groups else "other"
        order = 10000 + len(groups)
        groups.append(
            (
                order,
                len(groups),
                ToolPromptBundleGroup(
                    group_key=group_key,
                    title=_default_source_group_title(source, prompt, group_key),
                    summary=_default_source_group_summary(source, prompt, group_key),
                    function_ids=tuple(function.function_id for function in ungrouped_functions),
                    function_count=len(ungrouped_functions),
                    capability_ids=_function_capability_ids(ungrouped_functions),
                    metadata={
                        "group_key": group_key,
                        "order": order,
                        "auto_source_group": True,
                        "source_kind": source.kind.value,
                        "function_ids": [
                            function.function_id for function in ungrouped_functions
                        ],
                    },
                ),
            ),
        )
    return tuple(group for _, _, group in sorted(groups, key=lambda item: item[:2]))


def _default_source_group_title(
    source: ToolSourceCatalogRecord,
    prompt: Mapping[str, Any],
    group_key: str,
) -> str:
    if group_key == "other":
        return "Other Functions"
    return _prompt_text(prompt, "title") or source.display_name


def _default_source_group_summary(
    source: ToolSourceCatalogRecord,
    prompt: Mapping[str, Any],
    group_key: str,
) -> str:
    if group_key == "other":
        return (
            "Additional functions from this source that were not assigned to a "
            "more specific prompt group. Expand to inspect exact callable functions."
        )
    source_summary = _prompt_text(prompt, "summary") or source.description
    kind_summary = _default_source_kind_summary(source.kind)
    if source_summary:
        return (
            f"{source_summary} {kind_summary} Expand this group to inspect exact "
            "callable functions and their input schemas."
        )
    return f"{kind_summary} Expand this group to inspect exact callable functions and their input schemas."


def _default_source_kind_summary(source_kind: ToolSourceCatalogKind) -> str:
    if source_kind is ToolSourceCatalogKind.OPENAPI:
        return "OpenAPI source operations are API-backed calls from one configured service."
    if source_kind is ToolSourceCatalogKind.MCP:
        return "MCP source tools are remote protocol capabilities from one configured server."
    if source_kind is ToolSourceCatalogKind.CLI:
        return "CLI source entries are command-line guidance; use command execution tools to inspect help and run commands."
    if source_kind is ToolSourceCatalogKind.LOCAL_PACKAGE:
        return "Local package functions are CRXZipple-owned runtime capabilities from one package."
    if source_kind is ToolSourceCatalogKind.PROVIDER_BACKEND:
        return "Provider backend functions are routed through one configured backend capability."
    return "Tool source functions come from one configured capability source."


def _prompt_group_order(group: Mapping[str, Any], *, fallback: int) -> int:
    raw_order = group.get("order")
    if raw_order is None:
        return fallback
    try:
        return int(raw_order)
    except (TypeError, ValueError):
        return fallback


def _prompt_group_function_ids(group: Mapping[str, Any]) -> tuple[str, ...]:
    raw_function_ids = group.get("function_ids")
    if not isinstance(raw_function_ids, Iterable) or isinstance(
        raw_function_ids,
        (str, bytes),
    ):
        return ()
    return tuple(
        dict.fromkeys(
            str(function_id).strip()
            for function_id in raw_function_ids
            if str(function_id).strip()
        ),
    )


def _prompt_group_metadata(group: Mapping[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    default_schema_ids = _prompt_group_string_values(
        group.get("default_tool_schema_ids"),
    )
    if default_schema_ids:
        metadata["default_tool_schema_ids"] = list(default_schema_ids)
    default_schema_source = _prompt_text(group, "default_tool_schema_source")
    if default_schema_source:
        metadata["default_tool_schema_source"] = default_schema_source
    default_schema_max_count = _prompt_group_positive_int(
        group.get("default_tool_schema_max_count"),
    )
    if default_schema_max_count is not None:
        metadata["default_tool_schema_max_count"] = default_schema_max_count
    return metadata


def _prompt_group_string_values(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
        return ()
    return tuple(
        dict.fromkeys(
            str(item).strip()
            for item in value
            if str(item).strip()
        ),
    )


def _prompt_group_positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.strip():
        try:
            parsed = int(value.strip())
        except ValueError:
            return None
        return parsed if parsed > 0 else None
    return None


def _prompt_text(prompt: Mapping[str, Any], key: str) -> str | None:
    value = prompt.get(key)
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _credential_requirement_count(
    source: ToolSourceCatalogRecord,
    functions: tuple[ToolFunctionCatalogRecord, ...],
) -> int:
    return len(source.credential_requirements) + sum(
        len(function.requirements.credential_requirements)
        for function in functions
    )


def _runtime_requirement_count(
    source: ToolSourceCatalogRecord,
    functions: tuple[ToolFunctionCatalogRecord, ...],
) -> int:
    function_requirement_count = sum(
        len(requirement_set)
        for function in functions
        for requirement_set in function.requirements.runtime_requirement_sets
    )
    return len(source.runtime_requirements) + function_requirement_count


def _bundle_capability_ids(
    source: ToolSourceCatalogRecord,
    functions: tuple[ToolFunctionCatalogRecord, ...],
) -> tuple[str, ...]:
    raw_source_capabilities = source.config.get("capability_ids")
    source_capabilities = (
        tuple(
            str(capability_id).strip()
            for capability_id in raw_source_capabilities
            if str(capability_id).strip()
        )
        if isinstance(raw_source_capabilities, (list, tuple))
        else ()
    )
    return tuple(
        dict.fromkeys(
            capability_id
            for capability_id in (
                *source_capabilities,
                *_function_capability_ids(functions),
            )
            if capability_id
        ),
    )


def _function_capability_ids(
    functions: tuple[ToolFunctionCatalogRecord, ...],
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            capability_id
            for function in functions
            for capability_id in function.capabilities
            if capability_id
        ),
    )


def _source_status_event_name(status: ToolSourceStatus) -> str:
    if status is ToolSourceStatus.DISABLED:
        return "tool.source.disabled"
    if status is ToolSourceStatus.DELETED:
        return "tool.source.deleted"
    return "tool.source.restored"


def _source_snapshot(source: ToolSource | None) -> dict[str, Any] | None:
    if source is None:
        return None
    return {
        "status": source.status.value,
        "revision": source.revision,
        "config_hash": source.config_hash,
        "last_discovery_status": source.last_discovery_status,
    }


def _source_event(
    name: str,
    source: ToolSource,
    *,
    observed_at: datetime,
    previous: Mapping[str, Any] | None = None,
    discovery: ToolSourceDiscoveryResult | None = None,
    changed_fields: tuple[str, ...] = (),
) -> Event:
    payload: dict[str, Any] = {
        "source_id": source.source_id,
        "kind": source.kind.value,
        "display_name": source.display_name,
        "status": source.status.value,
        "revision": source.revision,
        "config_hash": source.config_hash,
    }
    if source.last_discovery_status:
        payload["discovery_status"] = source.last_discovery_status
    if previous is not None:
        payload["previous_status"] = previous.get("status")
        payload["previous_revision"] = previous.get("revision")
        payload["previous_config_hash"] = previous.get("config_hash")
        previous_discovery_status = previous.get("last_discovery_status")
        if previous_discovery_status:
            payload["previous_discovery_status"] = previous_discovery_status
    if discovery is not None:
        payload["discovery_status"] = discovery.status.value
        payload["function_count"] = len(discovery.candidates)
        payload["provider_backend_count"] = len(discovery.provider_backend_candidates)
        if discovery.error_message:
            payload["error_message"] = discovery.error_message
    if changed_fields:
        payload["changed_fields"] = changed_fields
    return Event(
        name=name,
        payload=payload,
        occurred_at=observed_at,
        ordering_key=source.source_id,
    )


def _function_event(
    name: str,
    function: ToolFunctionCatalogRecord,
    *,
    observed_at: datetime,
    changed_fields: tuple[str, ...] = (),
) -> Event:
    payload: dict[str, Any] = {
        "function_id": function.function_id,
        "source_id": function.source_id,
        "stable_key": function.stable_key,
        "schema_hash": function.schema_hash,
        "status": function.status.value,
        "enabled": function.enabled,
        "revision": function.revision,
    }
    if changed_fields:
        payload["changed_fields"] = changed_fields
    return Event(
        name=name,
        payload=payload,
        occurred_at=observed_at,
        ordering_key=function.function_id,
    )


def _merge_source(
    *,
    incoming: ToolSourceCatalogRecord,
    existing: ToolSource | None,
    discovery: ToolSourceDiscoveryResult | None = None,
    observed_at: datetime,
) -> ToolSource:
    incoming_entity = _source_record_to_entity(
        incoming,
        observed_at=observed_at,
        discovery=discovery,
    )
    if existing is None:
        return incoming_entity

    status = existing.status
    if status not in {ToolSourceStatus.DISABLED, ToolSourceStatus.DELETED}:
        status = incoming_entity.status

    changed = _source_config_changed(existing, incoming_entity)
    discovery_changed = discovery is not None and (
        existing.last_discovered_at != incoming_entity.last_discovered_at
        or existing.last_discovery_status != incoming_entity.last_discovery_status
        or existing.status != status
    )
    revision = existing.revision + 1 if changed or discovery_changed else existing.revision
    updated_at = observed_at if changed or discovery_changed else existing.updated_at
    return ToolSource(
        id=existing.source_id,
        kind=incoming_entity.kind,
        display_name=incoming_entity.display_name,
        description=incoming_entity.description,
        config=incoming_entity.config,
        credential_requirements=incoming_entity.credential_requirements,
        runtime_requirements=incoming_entity.runtime_requirements,
        status=status,
        revision=revision,
        config_hash=incoming_entity.config_hash,
        last_discovered_at=incoming_entity.last_discovered_at,
        last_discovery_status=incoming_entity.last_discovery_status,
        created_at=existing.created_at,
        updated_at=updated_at,
    )


def _upsert_provider_backend_candidates(
    repository: Any,
    candidates: tuple[ToolProviderBackendCandidate, ...],
    *,
    observed_at: datetime,
    dry_run: bool,
) -> None:
    if dry_run:
        return
    for candidate in candidates:
        existing = repository.get(candidate.backend_id)
        repository.upsert(
            _provider_backend_candidate_to_entity(
                candidate,
                existing=existing,
                observed_at=observed_at,
            ),
        )


def _provider_backend_candidate_to_entity(
    candidate: ToolProviderBackendCandidate,
    *,
    existing: ToolProviderBackend | None,
    observed_at: datetime,
) -> ToolProviderBackend:
    status = ToolProviderBackendStatus.ACTIVE
    enabled = candidate.enabled
    created_at = observed_at
    if existing is not None:
        created_at = existing.created_at
        enabled = existing.enabled
        status = (
            existing.status
            if existing.status
            in {ToolProviderBackendStatus.DISABLED, ToolProviderBackendStatus.DELETED}
            else ToolProviderBackendStatus.ACTIVE
        )
    return ToolProviderBackend(
        id=candidate.backend_id,
        source_id=candidate.source_id,
        capability=ToolProviderCapability(candidate.capability),
        display_name=candidate.display_name,
        credential_requirements=tuple(
            _stable_payload(requirement)
            for requirement in candidate.requirements.credential_requirements
        ),
        runtime_ref={
            "runtime_kind": DomainToolFunctionRuntimeKind(
                candidate.runtime_kind,
            ).value,
            "ref": candidate.runtime_ref,
            "metadata": _stable_payload(candidate.metadata),
        },
        priority=candidate.priority,
        enabled=enabled,
        status=status,
        created_at=created_at,
        updated_at=observed_at,
    )


def _source_record_to_entity(
    record: ToolSourceCatalogRecord,
    *,
    observed_at: datetime,
    discovery: ToolSourceDiscoveryResult | None = None,
) -> ToolSource:
    status = _domain_source_status(record.status)
    if discovery is not None and discovery.status is ToolSourceDiscoveryStatus.FAILED:
        status = ToolSourceStatus.ERROR
    return ToolSource(
        id=record.source_id,
        kind=_domain_source_kind(record.kind),
        display_name=record.display_name,
        description=record.description,
        config=dict(record.config),
        credential_requirements=tuple(
            _stable_payload(requirement)
            for requirement in record.credential_requirements
        ),
        runtime_requirements=tuple(
            {"requirement": requirement}
            for requirement in record.runtime_requirements
        ),
        status=status,
        revision=record.revision,
        config_hash=record.config_hash,
        last_discovered_at=(
            discovery.discovered_at
            if discovery is not None
            else record.last_discovered_at
        ),
        last_discovery_status=(
            discovery.status.value
            if discovery is not None
            else (
                record.last_discovery_status.value
                if isinstance(record.last_discovery_status, ToolSourceDiscoveryStatus)
                else record.last_discovery_status
            )
        ),
        created_at=record.created_at or observed_at,
        updated_at=record.updated_at or observed_at,
    )


def _source_entity_to_record(source: ToolSource) -> ToolSourceCatalogRecord:
    return ToolSourceCatalogRecord(
        source_id=source.source_id,
        kind=ToolSourceCatalogKind(source.kind.value),
        display_name=source.display_name,
        description=source.description,
        config=dict(source.config),
        credential_requirements=tuple(source.credential_requirements),  # type: ignore[arg-type]
        runtime_requirements=tuple(
            str(item.get("requirement", "")).strip()
            for item in source.runtime_requirements
            if str(item.get("requirement", "")).strip()
        ),
        status=CatalogToolSourceStatus(source.status.value),
        revision=source.revision,
        config_hash=source.config_hash,
        last_discovered_at=source.last_discovered_at,
        last_discovery_status=(
            ToolSourceDiscoveryStatus(source.last_discovery_status)
            if source.last_discovery_status
            and source.last_discovery_status
            in {status.value for status in ToolSourceDiscoveryStatus}
            else None
        ),
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


def _function_entity_to_record(function: Any) -> ToolFunctionCatalogRecord:
    return ToolFunctionCatalogRecord(
        function_id=function.function_id,
        source_id=function.source_id,
        stable_key=function.stable_key,
        name=function.name,
        description=function.description,
        input_schema=dict(function.input_schema),
        runtime_kind=function.runtime_kind.value,
        handler_ref=_handler_ref_from_payload(function.handler_ref),
        requirements=ToolFunctionRequirements(
            credential_requirements=_credential_requirement_sets_from_payload(
                function.credential_requirements,
            ),
            access_requirement_sets=function.access_requirement_sets,
            runtime_requirement_sets=_runtime_requirement_sets_from_payload(
                function.runtime_requirements,
            ),
            required_effect_ids=function.required_effect_ids,
        ),
        capabilities=function.capability_ids,
        schema_hash=function.schema_hash,
        status=function.status.value,
        revision=function.revision,
        enabled=function.enabled,
        trust_policy=function.trust_policy,
        approval_policy=function.approval_policy,
        credential_binding_overrides=function.credential_binding_overrides,
        required_effect_overrides=function.required_effect_overrides,
        metadata=function.metadata,
        created_at=function.created_at,
        updated_at=function.updated_at,
        last_seen_at=function.last_seen_at,
        stale_since=function.stale_since,
        deprecated_at=function.deprecated_at,
    )


def _runtime_requirement_sets_from_payload(
    payload: tuple[Mapping[str, Any], ...],
) -> tuple[tuple[str, ...], ...]:
    requirement_sets: list[tuple[str, ...]] = []
    for item in payload:
        raw = item.get("requirements")
        if not isinstance(raw, list | tuple):
            raw = (item.get("requirement"),)
        values = tuple(str(value).strip() for value in raw if str(value).strip())
        if values:
            requirement_sets.append(values)
    return tuple(requirement_sets)


def _credential_requirement_sets_from_payload(
    payload: object | None,
) -> tuple[AccessCredentialRequirementSet, ...]:
    if not isinstance(payload, list | tuple):
        return ()
    requirement_sets: list[AccessCredentialRequirementSet] = []
    for item in payload:
        if isinstance(item, Mapping):
            requirement_sets.append(_credential_requirement_set_from_payload(item))
    return tuple(requirement_sets)


def _credential_requirement_set_from_payload(
    payload: Mapping[str, Any],
) -> AccessCredentialRequirementSet:
    consumer = _consumer_ref_from_payload(payload.get("consumer"))
    raw_requirements = payload.get("requirements")
    requirements: list[AccessCredentialRequirementDeclaration] = []
    if isinstance(raw_requirements, list | tuple):
        for item in raw_requirements:
            if isinstance(item, Mapping):
                requirements.append(
                    _credential_requirement_from_payload(
                        item,
                        default_consumer=consumer,
                    ),
                )
    return AccessCredentialRequirementSet(
        requirement_set_id=str(payload.get("requirement_set_id", "")).strip(),
        consumer=consumer,
        requirements=tuple(requirements),
        alternative=bool(payload.get("alternative", False)),
        metadata=_mapping_payload(payload.get("metadata")),
    )


def _credential_requirement_from_payload(
    payload: Mapping[str, Any],
    *,
    default_consumer: AccessConsumerRef,
) -> AccessCredentialRequirementDeclaration:
    slot_payload = _mapping_payload(payload.get("slot"))
    setup_payload = _mapping_payload(payload.get("setup_flow_hint"))
    return AccessCredentialRequirementDeclaration(
        requirement_id=str(payload.get("requirement_id", "")).strip(),
        consumer=(
            _consumer_ref_from_payload(payload.get("consumer"))
            if isinstance(payload.get("consumer"), Mapping)
            else default_consumer
        ),
        slot=AccessCredentialSlotRef(
            slot=str(slot_payload.get("slot", "")).strip(),
            expected_kind=AccessCredentialKind(
                str(slot_payload.get("expected_kind", AccessCredentialKind.API_KEY.value)),
            ),
            binding_id=(
                str(slot_payload["binding_id"]).strip()
                if slot_payload.get("binding_id") is not None
                else None
            ),
            required=bool(slot_payload.get("required", True)),
            display_name=(
                str(slot_payload["display_name"]).strip()
                if slot_payload.get("display_name") is not None
                else None
            ),
            scopes=tuple(
                str(item).strip()
                for item in slot_payload.get("scopes", ())
                if str(item).strip()
            ),
            metadata=_mapping_payload(slot_payload.get("metadata")),
        ),
        provider=(
            str(payload["provider"]).strip()
            if payload.get("provider") is not None
            else None
        ),
        transport=AccessCredentialTransport(
            str(payload.get("transport", AccessCredentialTransport.RUNTIME_CONTEXT.value)),
        ),
        parameter_name=(
            str(payload["parameter_name"]).strip()
            if payload.get("parameter_name") is not None
            else None
        ),
        setup_flow_hint=AccessSetupFlowHint(
            flow_kind=AccessSetupFlowKind(
                str(setup_payload.get("flow_kind", AccessSetupFlowKind.NONE.value)),
            ),
            provider=(
                str(setup_payload["provider"]).strip()
                if setup_payload.get("provider") is not None
                else None
            ),
            authorization_url=(
                str(setup_payload["authorization_url"]).strip()
                if setup_payload.get("authorization_url") is not None
                else None
            ),
            token_url=(
                str(setup_payload["token_url"]).strip()
                if setup_payload.get("token_url") is not None
                else None
            ),
            device_code_url=(
                str(setup_payload["device_code_url"]).strip()
                if setup_payload.get("device_code_url") is not None
                else None
            ),
            callback_url=(
                str(setup_payload["callback_url"]).strip()
                if setup_payload.get("callback_url") is not None
                else None
            ),
            metadata=_mapping_payload(setup_payload.get("metadata")),
        ),
        metadata=_mapping_payload(payload.get("metadata")),
    )


def _consumer_ref_from_payload(payload: object | None) -> AccessConsumerRef:
    values = _mapping_payload(payload)
    return AccessConsumerRef(
        consumer_id=str(values.get("consumer_id", "")).strip(),
        module=str(values.get("module", "")).strip(),
        component=(
            str(values["component"]).strip()
            if values.get("component") is not None
            else None
        ),
        runtime_ref=(
            str(values["runtime_ref"]).strip()
            if values.get("runtime_ref") is not None
            else None
        ),
        metadata=_mapping_payload(values.get("metadata")),
    )


def _mapping_payload(value: object | None) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _handler_ref_from_payload(payload: Mapping[str, Any]) -> str:
    for key in ("ref", "handler", "runtime_key"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _validate_owner_writable_source(source: ToolSourceCatalogRecord) -> None:
    config_source = str(source.config.get("source") or "").strip()
    if config_source == "bundled_tool_package":
        raise ToolValidationError(
            "Bundled tool package sources are managed by the Tool package loader.",
        )
    if source.kind not in {
        ToolSourceCatalogKind.OPENAPI,
        ToolSourceCatalogKind.MCP,
        ToolSourceCatalogKind.CLI,
    }:
        raise ToolValidationError(
            "Tool source create/update currently supports configured OpenAPI, MCP and CLI sources.",
        )
    if config_source != "configured_tool_provider":
        raise ToolValidationError(
            "Configured Tool source config.source must be 'configured_tool_provider'.",
        )
    package_kind = str(source.config.get("package_kind") or "").strip()
    if package_kind != source.kind.value:
        raise ToolValidationError(
            f"Configured Tool source config.package_kind must be '{source.kind.value}'.",
        )
    provider = source.config.get("provider")
    if not isinstance(provider, Mapping):
        raise ToolValidationError(
            "Configured Tool source config.provider must be an object.",
        )
    provider_name = str(provider.get("name") or "").strip()
    if not provider_name:
        raise ToolValidationError(
            "Configured Tool source config.provider.name is required.",
        )
    if source.kind is ToolSourceCatalogKind.OPENAPI:
        spec_location = str(provider.get("spec_location") or "").strip()
        if not spec_location:
            raise ToolValidationError(
                "Configured OpenAPI source config.provider.spec_location is required.",
            )
    if source.kind is ToolSourceCatalogKind.MCP:
        command = provider.get("command")
        if not isinstance(command, list | tuple) or not all(
            isinstance(item, str) and item.strip()
            for item in command
        ):
            raise ToolValidationError(
                "Configured MCP source config.provider.command must be a non-empty string list.",
            )
    if source.kind is ToolSourceCatalogKind.CLI:
        executable = str(provider.get("executable") or "").strip()
        command = provider.get("command")
        has_command = isinstance(command, list | tuple) and all(
            isinstance(item, str) and item.strip()
            for item in command
        )
        if not executable and not has_command:
            raise ToolValidationError(
                "Configured CLI source config.provider.executable or command is required.",
            )
        allowed_subcommands = provider.get("allowed_subcommands")
        if (
            not isinstance(allowed_subcommands, list | tuple)
            or not allowed_subcommands
            or not all(
                isinstance(item, str) and item.strip()
                for item in allowed_subcommands
            )
        ):
            raise ToolValidationError(
                "Configured CLI source config.provider.allowed_subcommands must be a non-empty string list.",
            )


def _domain_source_kind(value: ToolSourceCatalogKind | str) -> ToolCatalogSourceKind:
    kind = ToolSourceCatalogKind(str(value))
    try:
        return ToolCatalogSourceKind(kind.value)
    except ValueError as exc:
        raise ToolValidationError(
            f"Tool source kind '{kind.value}' is not supported by the persistent catalog.",
        ) from exc


def _domain_source_status(
    value: CatalogToolSourceStatus | str,
) -> ToolSourceStatus:
    return ToolSourceStatus(CatalogToolSourceStatus(str(value)).value)


def _source_config_changed(existing: ToolSource, incoming: ToolSource) -> bool:
    return any(
        (
            existing.kind != incoming.kind,
            existing.display_name != incoming.display_name,
            existing.description != incoming.description,
            existing.config_hash != incoming.config_hash,
            existing.config != incoming.config,
            existing.credential_requirements != incoming.credential_requirements,
            existing.runtime_requirements != incoming.runtime_requirements,
        ),
    )


def _source_changed(existing: ToolSource, incoming: ToolSource) -> bool:
    return _source_config_changed(existing, incoming) or any(
        (
            existing.status != incoming.status,
            existing.last_discovered_at != incoming.last_discovered_at,
            existing.last_discovery_status != incoming.last_discovery_status,
        ),
    )


def _source_changed_fields(
    existing: ToolSource | None,
    incoming: ToolSource,
) -> tuple[str, ...]:
    if existing is None:
        return ()
    comparisons: tuple[tuple[str, Any, Any], ...] = (
        ("kind", existing.kind, incoming.kind),
        ("display_name", existing.display_name, incoming.display_name),
        ("description", existing.description, incoming.description),
        ("config", existing.config, incoming.config),
        (
            "credential_requirements",
            existing.credential_requirements,
            incoming.credential_requirements,
        ),
        ("runtime_requirements", existing.runtime_requirements, incoming.runtime_requirements),
        ("status", existing.status, incoming.status),
        ("config_hash", existing.config_hash, incoming.config_hash),
        ("last_discovered_at", existing.last_discovered_at, incoming.last_discovered_at),
        (
            "last_discovery_status",
            existing.last_discovery_status,
            incoming.last_discovery_status,
        ),
    )
    return tuple(
        field_name
        for field_name, current, next_value in comparisons
        if _stable_payload(current) != _stable_payload(next_value)
    )


def _stable_payload(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _stable_payload(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(key): _stable_payload(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, tuple | list):
        return [_stable_payload(item) for item in value]
    return value


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


__all__ = [
    "ToolFunctionCommandResult",
    "ToolFunctionCommandService",
    "ToolSourceCatalogSyncResult",
    "ToolSourceCommandResult",
    "ToolSourceCommandService",
    "ToolSourceQueryService",
    "ToolSourceSyncResult",
    "ToolSourceUnitOfWork",
]
