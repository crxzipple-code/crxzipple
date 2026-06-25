from __future__ import annotations

from pydantic import BaseModel

from crxzipple.modules.operations.application.read_models import (
    OperationsOwnerFactSourceModel,
    OperationsProjectionDiagnosticsModel,
)


class OperationsOwnerFactSourceResponse(BaseModel):
    module: str
    facts: list[str]
    read_path: str

    @classmethod
    def from_value(
        cls,
        value: OperationsOwnerFactSourceModel,
    ) -> "OperationsOwnerFactSourceResponse":
        return cls(
            module=value.module,
            facts=list(value.facts),
            read_path=value.read_path,
        )


class OperationsProjectionDiagnosticsResponse(BaseModel):
    module: str
    owner_sources: list[OperationsOwnerFactSourceResponse]
    owner_call_count: int
    processed_item_count: int
    elapsed_ms: float
    freshness_at: str | None = None

    @classmethod
    def from_value(
        cls,
        value: OperationsProjectionDiagnosticsModel | None,
    ) -> "OperationsProjectionDiagnosticsResponse | None":
        if value is None:
            return None
        return cls(
            module=value.module,
            owner_sources=[
                OperationsOwnerFactSourceResponse.from_value(item)
                for item in value.owner_sources
            ],
            owner_call_count=value.owner_call_count,
            processed_item_count=value.processed_item_count,
            elapsed_ms=value.elapsed_ms,
            freshness_at=value.freshness_at,
        )


class OperationsProjectionFreshnessResponse(BaseModel):
    module: str
    kind: str
    query_key: str
    updated_at: str


class OperationsRuntimeStatusItemResponse(BaseModel):
    id: str
    label: str
    value: str
    status: str
    tone: str = "neutral"
    details: str | None = None


class OperationsRuntimeStatusResponse(BaseModel):
    updated_at: str
    checks: list[OperationsRuntimeStatusItemResponse]
