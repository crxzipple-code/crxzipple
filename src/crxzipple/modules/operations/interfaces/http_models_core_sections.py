from __future__ import annotations

from pydantic import BaseModel

from crxzipple.modules.operations.application.read_models import (
    OperationsChartSectionModel,
    OperationsChartSegmentModel,
    OperationsKeyValueItemModel,
    OperationsKeyValueSectionModel,
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)


class OperationsKeyValueItemResponse(BaseModel):
    label: str
    value: str
    tone: str = "neutral"

    @classmethod
    def from_value(
        cls, value: OperationsKeyValueItemModel
    ) -> "OperationsKeyValueItemResponse":
        return cls(label=value.label, value=value.value, tone=value.tone)


class OperationsKeyValueSectionResponse(BaseModel):
    id: str
    title: str
    items: list[OperationsKeyValueItemResponse]

    @classmethod
    def from_value(
        cls, value: OperationsKeyValueSectionModel
    ) -> "OperationsKeyValueSectionResponse":
        return cls(
            id=value.id,
            title=value.title,
            items=[
                OperationsKeyValueItemResponse.from_value(item) for item in value.items
            ],
        )


class OperationsChartSegmentResponse(BaseModel):
    id: str
    label: str
    value: int
    tone: str = "neutral"

    @classmethod
    def from_value(
        cls, value: OperationsChartSegmentModel
    ) -> "OperationsChartSegmentResponse":
        return cls(
            id=value.id,
            label=value.label,
            value=value.value,
            tone=value.tone,
        )


class OperationsChartSectionResponse(BaseModel):
    id: str
    title: str
    kind: str
    total: int
    segments: list[OperationsChartSegmentResponse]

    @classmethod
    def from_value(
        cls, value: OperationsChartSectionModel
    ) -> "OperationsChartSectionResponse":
        return cls(
            id=value.id,
            title=value.title,
            kind=value.kind,
            total=value.total,
            segments=[
                OperationsChartSegmentResponse.from_value(item)
                for item in value.segments
            ],
        )


class OperationsTableColumnResponse(BaseModel):
    key: str
    label: str

    @classmethod
    def from_value(
        cls, value: OperationsTableColumnModel
    ) -> "OperationsTableColumnResponse":
        return cls(key=value.key, label=value.label)


class OperationsTableRowResponse(BaseModel):
    id: str
    cells: dict[str, str]
    status: str | None = None
    tone: str = "neutral"

    @classmethod
    def from_value(cls, value: OperationsTableRowModel) -> "OperationsTableRowResponse":
        return cls(
            id=value.id,
            cells=dict(value.cells),
            status=value.status,
            tone=value.tone,
        )


class OperationsTableSectionResponse(BaseModel):
    id: str
    title: str
    columns: list[OperationsTableColumnResponse]
    rows: list[OperationsTableRowResponse]
    total: int
    view_all_route: str | None = None
    empty_state: str | None = None

    @classmethod
    def from_value(
        cls, value: OperationsTableSectionModel
    ) -> "OperationsTableSectionResponse":
        return cls(
            id=value.id,
            title=value.title,
            columns=[
                OperationsTableColumnResponse.from_value(item) for item in value.columns
            ],
            rows=[OperationsTableRowResponse.from_value(item) for item in value.rows],
            total=value.total,
            view_all_route=value.view_all_route,
            empty_state=value.empty_state,
        )
