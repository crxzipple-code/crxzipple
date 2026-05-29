from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from crxzipple.modules.tool.application.catalog_models import (
    ToolFunctionCandidate,
    ToolFunctionCatalogRecord,
    ToolFunctionStatus,
    ToolSourceDiscoveryResult,
)
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.shared.domain.events import Event


class ToolFunctionCatalogRepository(Protocol):
    def list_by_source(self, source_id: str) -> tuple[ToolFunctionCatalogRecord, ...]:
        ...

    def add(self, function: ToolFunctionCatalogRecord) -> None:
        ...

    def update(self, function: ToolFunctionCatalogRecord) -> None:
        ...


class ToolCatalogEventPublisher(Protocol):
    def publish(self, event: Event) -> None:
        ...


@dataclass(frozen=True, slots=True)
class ToolCatalogReconcileResult:
    source_id: str
    created: tuple[ToolFunctionCatalogRecord, ...] = ()
    updated: tuple[ToolFunctionCatalogRecord, ...] = ()
    unchanged: tuple[ToolFunctionCatalogRecord, ...] = ()
    stale: tuple[ToolFunctionCatalogRecord, ...] = ()
    deprecated: tuple[ToolFunctionCatalogRecord, ...] = ()
    events: tuple[Event, ...] = ()
    dry_run: bool = False

    @property
    def changed(self) -> tuple[ToolFunctionCatalogRecord, ...]:
        return self.created + self.updated + self.stale + self.deprecated


class ToolCatalogReconcileService:
    def __init__(
        self,
        repository: ToolFunctionCatalogRepository,
        *,
        event_publisher: ToolCatalogEventPublisher | None = None,
        clock: object | None = None,
    ) -> None:
        self._repository = repository
        self._event_publisher = event_publisher
        self._clock = clock

    def reconcile_discovery_result(
        self,
        result: ToolSourceDiscoveryResult,
        *,
        deprecate_stale: bool = False,
        dry_run: bool = False,
    ) -> ToolCatalogReconcileResult:
        return self.reconcile(
            source_id=result.source_id,
            candidates=result.candidates,
            observed_at=result.discovered_at,
            deprecate_stale=deprecate_stale,
            dry_run=dry_run,
        )

    def reconcile(
        self,
        *,
        source_id: str,
        candidates: tuple[ToolFunctionCandidate, ...],
        observed_at: datetime | None = None,
        deprecate_stale: bool = False,
        dry_run: bool = False,
    ) -> ToolCatalogReconcileResult:
        normalized_source_id = source_id.strip()
        if not normalized_source_id:
            raise ToolValidationError("Tool catalog reconcile source_id is required.")

        now = observed_at or self._now()
        candidate_by_key = _candidate_map(
            candidates,
            source_id=normalized_source_id,
        )
        existing = self._repository.list_by_source(normalized_source_id)
        existing_by_key = _existing_map(existing)

        created: list[ToolFunctionCatalogRecord] = []
        updated: list[ToolFunctionCatalogRecord] = []
        unchanged: list[ToolFunctionCatalogRecord] = []
        stale: list[ToolFunctionCatalogRecord] = []
        deprecated: list[ToolFunctionCatalogRecord] = []
        events: list[Event] = []

        for stable_key in sorted(candidate_by_key):
            candidate = candidate_by_key[stable_key]
            current = existing_by_key.get(stable_key)
            if current is None:
                created_record = ToolFunctionCatalogRecord.from_candidate(
                    candidate,
                    observed_at=now,
                )
                created.append(created_record)
                event = _function_event(
                    "tool.function.created",
                    created_record,
                    observed_at=now,
                )
                events.append(event)
                if not dry_run:
                    self._repository.add(created_record)
                continue

            next_record = current.seen_from_candidate(candidate, observed_at=now)
            if next_record == current:
                unchanged.append(current)
                continue

            updated.append(next_record)
            event = _function_event(
                "tool.function.updated",
                next_record,
                observed_at=now,
                previous=current,
                changed_fields=current.changed_fields_from_candidate(candidate),
            )
            events.append(event)
            if not dry_run:
                self._repository.update(next_record)

        seen_keys = set(candidate_by_key)
        for current in sorted(existing, key=lambda item: item.stable_key):
            if current.stable_key in seen_keys:
                continue
            if current.status is ToolFunctionStatus.STALE and deprecate_stale:
                deprecated_record = current.mark_deprecated(observed_at=now)
                if deprecated_record == current:
                    unchanged.append(current)
                    continue
                deprecated.append(deprecated_record)
                event = _function_event(
                    "tool.function.deprecated",
                    deprecated_record,
                    observed_at=now,
                    previous=current,
                )
                events.append(event)
                if not dry_run:
                    self._repository.update(deprecated_record)
                continue
            if current.status is ToolFunctionStatus.ACTIVE:
                stale_record = current.mark_stale(observed_at=now)
                stale.append(stale_record)
                event = _function_event(
                    "tool.function.stale",
                    stale_record,
                    observed_at=now,
                    previous=current,
                )
                events.append(event)
                if not dry_run:
                    self._repository.update(stale_record)
                continue
            unchanged.append(current)

        if not dry_run:
            self._publish(tuple(events))

        return ToolCatalogReconcileResult(
            source_id=normalized_source_id,
            created=tuple(created),
            updated=tuple(updated),
            unchanged=tuple(unchanged),
            stale=tuple(stale),
            deprecated=tuple(deprecated),
            events=tuple(events),
            dry_run=dry_run,
        )

    def _publish(self, events: tuple[Event, ...]) -> None:
        if self._event_publisher is None:
            return
        for event in events:
            self._event_publisher.publish(event)

    def _now(self) -> datetime:
        if self._clock is not None and hasattr(self._clock, "now"):
            value = self._clock.now()
            if isinstance(value, datetime):
                return value
        return datetime.now(timezone.utc)


def _candidate_map(
    candidates: tuple[ToolFunctionCandidate, ...],
    *,
    source_id: str,
) -> dict[str, ToolFunctionCandidate]:
    candidate_by_key: dict[str, ToolFunctionCandidate] = {}
    function_ids: dict[str, str] = {}
    for candidate in candidates:
        if candidate.source_id != source_id:
            raise ToolValidationError(
                "Tool catalog reconcile candidate source_id must match source_id.",
            )
        previous_key = candidate_by_key.get(candidate.stable_key)
        if previous_key is not None:
            raise ToolValidationError(
                f"Duplicate tool function candidate stable_key '{candidate.stable_key}'.",
            )
        previous_function_key = function_ids.get(candidate.function_id)
        if previous_function_key is not None:
            raise ToolValidationError(
                "Duplicate tool function candidate function_id "
                f"'{candidate.function_id}' for stable keys "
                f"'{previous_function_key}' and '{candidate.stable_key}'.",
            )
        candidate_by_key[candidate.stable_key] = candidate
        function_ids[candidate.function_id] = candidate.stable_key
    return candidate_by_key


def _existing_map(
    functions: tuple[ToolFunctionCatalogRecord, ...],
) -> dict[str, ToolFunctionCatalogRecord]:
    existing_by_key: dict[str, ToolFunctionCatalogRecord] = {}
    for function in functions:
        if function.stable_key in existing_by_key:
            raise ToolValidationError(
                f"Duplicate existing tool function stable_key '{function.stable_key}'.",
            )
        existing_by_key[function.stable_key] = function
    return existing_by_key


def _function_event(
    name: str,
    function: ToolFunctionCatalogRecord,
    *,
    observed_at: datetime,
    previous: ToolFunctionCatalogRecord | None = None,
    changed_fields: tuple[str, ...] = (),
) -> Event:
    payload = {
        "function_id": function.function_id,
        "source_id": function.source_id,
        "stable_key": function.stable_key,
        "schema_hash": function.schema_hash,
        "status": function.status.value,
        "revision": function.revision,
    }
    if previous is not None:
        payload.update(
            {
                "previous_schema_hash": previous.schema_hash,
                "previous_status": previous.status.value,
                "previous_revision": previous.revision,
            },
        )
    if changed_fields:
        payload["changed_fields"] = changed_fields
    return Event(
        name=name,
        payload=payload,
        occurred_at=observed_at,
        ordering_key=function.function_id,
    )


__all__ = [
    "ToolCatalogEventPublisher",
    "ToolCatalogReconcileResult",
    "ToolCatalogReconcileService",
    "ToolFunctionCatalogRepository",
]
