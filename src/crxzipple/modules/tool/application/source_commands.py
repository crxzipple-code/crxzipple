from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.tool.application.catalog_models import (
    ToolProviderBackendCandidate,
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
)
from crxzipple.modules.tool.application.source_command_models import (
    ToolSourceCatalogSyncResult,
    ToolSourceCommandResult,
    ToolSourceSyncResult,
)
from crxzipple.modules.tool.application.source_events import (
    source_event as _source_event,
    source_snapshot as _source_snapshot,
    source_status_event_name as _source_status_event_name,
)
from crxzipple.modules.tool.application.source_record_mapping import (
    provider_backend_candidate_to_entity as _provider_backend_candidate_to_entity,
    source_entity_to_record as _source_entity_to_record,
    source_record_to_entity as _source_record_to_entity,
)
from crxzipple.modules.tool.application.source_state import (
    merge_source as _merge_source,
    source_changed as _source_changed,
    source_changed_fields as _source_changed_fields,
)
from crxzipple.modules.tool.application.source_unit_of_work import (
    ToolSourceUnitOfWork,
)
from crxzipple.modules.tool.application.source_validation import (
    validate_owner_writable_source as _validate_owner_writable_source,
)
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.domain.value_objects import ToolSourceStatus
from crxzipple.shared.domain import AggregateRoot, Event


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


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


__all__ = ["ToolSourceCommandService"]
