from __future__ import annotations

from collections import Counter

from crxzipple.modules.operations.application.read_models.models import (
    OperationsChartSectionModel,
    OperationsChartSegmentModel,
)
from crxzipple.modules.operations.application.read_models.skills_common import (
    source,
    status_label,
)
from crxzipple.modules.operations.application.read_models.skills_models import (
    SkillRecord,
)


def readiness_chart(records: tuple[SkillRecord, ...]) -> OperationsChartSectionModel:
    counts = Counter(record.status for record in records)
    segments = (
        OperationsChartSegmentModel("ready", "Ready", counts["Ready"], "success"),
        OperationsChartSegmentModel(
            "setup_needed",
            "Setup Needed",
            counts["Setup Needed"],
            "warning",
        ),
        OperationsChartSegmentModel(
            "unsupported",
            "Unsupported",
            counts["Unsupported"],
            "warning",
        ),
        OperationsChartSegmentModel("disabled", "Disabled", counts["Disabled"], "neutral"),
        OperationsChartSegmentModel("invalid", "Invalid", counts["Invalid"], "danger"),
    )
    return OperationsChartSectionModel(
        "resolution_outcomes",
        "Skill Readiness",
        "donut",
        sum(item.value for item in segments),
        tuple(item for item in segments if item.value),
    )


def source_chart(records: tuple[SkillRecord, ...]) -> OperationsChartSectionModel:
    counts = Counter(source(record.package) for record in records)
    return OperationsChartSectionModel(
        "skill_package_sources",
        "Skill Package Sources",
        "donut",
        sum(counts.values()),
        tuple(
            OperationsChartSegmentModel(item_source, status_label(item_source), count, "info")
            for item_source, count in sorted(counts.items())
        ),
    )
