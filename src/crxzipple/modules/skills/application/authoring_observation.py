from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from crxzipple.modules.skills.application.events import (
    SkillEventEmitter,
    emit_skill_event,
)
from crxzipple.modules.skills.application.authoring_payloads import (
    draft_audit_payload,
    draft_event_payload,
)
from crxzipple.modules.skills.application.models import (
    SkillDraft,
    SkillDraftAuditRecord,
)
from crxzipple.modules.skills.application.ports import (
    SkillAuthoringDraftRepositoryPort,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def record_draft_audit(
    repository: SkillAuthoringDraftRepositoryPort,
    *,
    action: str,
    status: str,
    draft_id: str | None = None,
    before: SkillDraft | None = None,
    after: SkillDraft | None = None,
    metadata: dict[str, object] | None = None,
) -> None:
    draft = after or before
    resolved_draft_id = draft_id or (draft.draft_id if draft is not None else "")
    if not resolved_draft_id:
        return
    repository.append_draft_audit(
        SkillDraftAuditRecord(
            audit_id=f"skill-draft-audit:{uuid4().hex}",
            draft_id=resolved_draft_id,
            action=action,
            status=status,
            actor=(draft.actor if draft is not None else None),
            reason=(draft.reason if draft is not None else None),
            before_payload=draft_audit_payload(before),
            after_payload=draft_audit_payload(after),
            metadata=dict(metadata or {}),
            created_at=utc_now(),
        ),
    )


def emit_draft_lifecycle_event(
    event_emitter: SkillEventEmitter | None,
    event_name: str,
    draft: SkillDraft,
    *,
    status: str | None = None,
    level: str = "info",
    extra: dict[str, object] | None = None,
) -> None:
    emit_skill_event(
        event_emitter,
        event_name,
        payload=draft_event_payload(draft, extra=extra),
        status=status or draft.status.value,
        level=level,
    )
