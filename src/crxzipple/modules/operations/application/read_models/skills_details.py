from __future__ import annotations

from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
)
from crxzipple.modules.operations.application.read_models.skills_common import (
    joined,
    skill_id,
    skill_name,
    source,
    text,
)
from crxzipple.modules.operations.application.read_models.skills_detail_sections import (
    detail_requirements_table,
    events_for_skill_table,
    resources_table,
    skill_payload,
)
from crxzipple.modules.operations.application.read_models.skills_models import (
    SkillDetailModel,
    SkillRecord,
)


def skill_details(
    records: tuple[SkillRecord, ...],
    events: tuple[OperationsObservedEvent, ...],
) -> tuple[SkillDetailModel, ...]:
    return tuple(
        SkillDetailModel(
            skill_id=skill_id(record.package),
            title=skill_name(record.package),
            status=record.status,
            tone=record.tone,
            summary=(
                OperationsKeyValueItemModel("Skill", skill_name(record.package)),
                OperationsKeyValueItemModel("Source", source(record.package)),
                OperationsKeyValueItemModel("Version", text(getattr(record.package, "version", None), "1")),
                OperationsKeyValueItemModel("Tags", joined(getattr(record.package, "tags", ()))),
                OperationsKeyValueItemModel("Required Tools", joined(getattr(getattr(record.package, "requirements", None), "required_tools", ()))),
                OperationsKeyValueItemModel("Path", text(getattr(record.package, "root_path", ""))),
            ),
            requirements=detail_requirements_table(record),
            resources=resources_table(record.package),
            events=events_for_skill_table(events, skill_name(record.package)),
            raw_payload=skill_payload(record.package),
        )
        for record in records[:80]
    )
