from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MetricCardModel:
    id: str
    label: str
    value: str
    delta: str
    tone: str = "neutral"


@dataclass(frozen=True, slots=True)
class RuntimeActionModel:
    id: str
    label: str
    owner: str = "operations"
    kind: str = "operation"
    risk: str = "normal"
    allowed: bool = True
    disabled_reason: str | None = None
    requires_confirmation: bool = False
    reason_required: bool = False
    audit_event: str | None = None
    method: str | None = None
    endpoint: str | None = None


@dataclass(frozen=True, slots=True)
class OperationsTabModel:
    id: str
    label: str
    count: int | None = None
    tone: str = "neutral"


@dataclass(frozen=True, slots=True)
class OperationsModuleRoleModel:
    label: str
    can_operate: bool
    scope: str | None = None


@dataclass(frozen=True, slots=True)
class OperationsKeyValueItemModel:
    label: str
    value: str
    tone: str = "neutral"


@dataclass(frozen=True, slots=True)
class OperationsKeyValueSectionModel:
    id: str
    title: str
    items: tuple[OperationsKeyValueItemModel, ...]


@dataclass(frozen=True, slots=True)
class OperationsChartSegmentModel:
    id: str
    label: str
    value: int
    tone: str = "neutral"


@dataclass(frozen=True, slots=True)
class OperationsChartSectionModel:
    id: str
    title: str
    kind: str
    total: int
    segments: tuple[OperationsChartSegmentModel, ...]


@dataclass(frozen=True, slots=True)
class OperationsTableColumnModel:
    key: str
    label: str


@dataclass(frozen=True, slots=True)
class OperationsTableRowModel:
    id: str
    cells: dict[str, str]
    status: str | None = None
    tone: str = "neutral"


@dataclass(frozen=True, slots=True)
class OperationsTableSectionModel:
    id: str
    title: str
    columns: tuple[OperationsTableColumnModel, ...]
    rows: tuple[OperationsTableRowModel, ...]
    total: int
    view_all_route: str | None = None
    empty_state: str | None = None


@dataclass(frozen=True, slots=True)
class OperationsModuleOverview:
    module: str
    title: str
    subtitle: str
    health: str
    updated_at: str
    metrics: tuple[MetricCardModel, ...]
    queue: tuple[dict[str, str], ...]
    lane_locks: tuple[dict[str, str], ...]
    executor: tuple[dict[str, str], ...]
    actions: tuple[RuntimeActionModel, ...]
