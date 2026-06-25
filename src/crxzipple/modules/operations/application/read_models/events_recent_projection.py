from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.observation_event_projection import (
    observed_event_from_record,
)
from crxzipple.modules.operations.application.observation_models import (
    OperationsObservedEvent,
)
from crxzipple.modules.operations.application.read_models.events_contract_matching import (
    contract_label,
    contract_status,
    match_payload,
    match_route_contracts,
    match_topic_contracts,
)
from crxzipple.modules.operations.application.read_models.events_state_common import (
    display,
    jsonable,
)
from crxzipple.shared.time import format_datetime_utc


def event_summary_from_record(
    record: Any,
    *,
    definition_registry: Any | None,
    contract_registry: Any | None,
) -> dict[str, Any] | None:
    try:
        observed = observed_event_from_record(
            record,
            definition_registry=definition_registry,
        )
    except Exception:
        return None
    envelope = getattr(record, "envelope", None)
    if envelope is None:
        return None
    topic = display(getattr(envelope, "topic", None))
    payload = jsonable(getattr(envelope, "payload", {}) or {})
    trace = jsonable(getattr(envelope, "trace", {}) or {})
    if not isinstance(payload, dict):
        payload = {}
    if not isinstance(trace, dict):
        trace = {}
    return event_summary_from_observed_event(
        observed,
        definition_registry=definition_registry,
        contract_registry=contract_registry,
        topic=topic,
        payload=payload,
        trace=trace,
    )


def event_summary_from_observed_event(
    observed: OperationsObservedEvent,
    *,
    definition_registry: Any | None,
    contract_registry: Any | None,
    topic: str | None = None,
    payload: dict[str, Any] | None = None,
    trace: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    topic = display(topic or observed.topic)
    event_name = observed.event_name
    definition = (
        definition_registry.get_by_event_name(event_name)
        if definition_registry is not None
        else None
    )
    surfaces = _safe_surfaces_for_event_name(definition_registry, event_name)
    contract_matches = match_topic_contracts(contract_registry, topic)
    route_matches = match_route_contracts(contract_registry, topic)
    resolved_contract_status = contract_status(
        observed=observed,
        definition=definition,
        contract_matches=contract_matches,
    )
    payload = jsonable(payload if payload is not None else observed.payload)
    trace = jsonable(trace if trace is not None else {})
    if not isinstance(payload, dict):
        payload = {}
    if not isinstance(trace, dict):
        trace = {}
    return {
        "event_id": observed.id,
        "cursor": display(observed.cursor),
        "topic": topic,
        "event_name": event_name,
        "owner": observed.owner,
        "module": observed.module,
        "kind": observed.kind,
        "status": observed.status,
        "level": observed.level,
        "entity_id": observed.entity_id,
        "run_id": observed.run_id,
        "trace_id": observed.trace_id,
        "created_at": format_datetime_utc(observed.occurred_at),
        "definition_id": display(getattr(definition, "definition_id", None)),
        "surface_ids": tuple(
            display(getattr(surface, "surface_id", None)) for surface in surfaces
        ),
        "contract_status": resolved_contract_status,
        "contract_label": contract_label(
            definition=definition,
            contract_matches=contract_matches,
        ),
        "contract_matches": tuple(match_payload(item) for item in contract_matches),
        "route_matches": tuple(match_payload(item) for item in route_matches),
        "payload": payload,
        "trace": trace,
        "observed": observed.to_payload(),
    }


def _safe_surfaces_for_event_name(
    definition_registry: Any | None,
    event_name: str,
) -> tuple[Any, ...]:
    method = getattr(definition_registry, "list_surfaces_for_event_name", None)
    if not callable(method):
        return ()
    try:
        return tuple(method(event_name) or ())
    except Exception:
        return ()
