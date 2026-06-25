from __future__ import annotations

from datetime import datetime, timezone

from crxzipple.modules.access.application.read_models import AccessAuditReadModel
from crxzipple.modules.access.application.query_record_models import (
    audit_model,
    settings_audit_model,
)


def audit_models(
    audit_repository: object | None,
    settings_config_provider: object | None,
    *,
    limit: int,
    offset: int,
) -> tuple[AccessAuditReadModel, ...]:
    window = min(max(int(limit) + max(int(offset), 0), 1), 200)
    models = (
        tuple(
            audit_model(record)
            for record in _list_audits(
                audit_repository,
                limit=window,
                offset=0,
            )
        )
        + _settings_audit_models(settings_config_provider)
    )
    ordered = tuple(
        sorted(
            models,
            key=lambda item: item.created_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        ),
    )
    start = max(int(offset), 0)
    stop = start + min(max(int(limit), 1), 200)
    return ordered[start:stop]


def _list_audits(
    audit_repository: object | None,
    *,
    limit: int,
    offset: int,
) -> tuple[object, ...]:
    if audit_repository is None:
        return ()
    list_recent = getattr(audit_repository, "list_recent", None)
    if list_recent is None:
        return ()
    return tuple(list_recent(limit=limit, offset=offset))


def _settings_audit_models(
    settings_config_provider: object | None,
) -> tuple[AccessAuditReadModel, ...]:
    provider = settings_config_provider
    query_service = getattr(provider, "query_service", None)
    if provider is None or query_service is None:
        return ()
    list_audits = getattr(query_service, "list_audits", None)
    if not callable(list_audits):
        return ()
    audits = []
    for record in list_audits():
        if getattr(record, "target_type", None) != "access-assets":
            continue
        audits.append(settings_audit_model(record))
    return tuple(audits)
