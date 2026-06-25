from __future__ import annotations

from pydantic import BaseModel

from crxzipple.modules.operations.application.read_models import (
    MetricCardModel,
    OperationsModuleRoleModel,
    OperationsTabModel,
    RuntimeActionModel,
)


class MetricCardResponse(BaseModel):
    id: str
    label: str
    value: str
    delta: str
    tone: str = "neutral"

    @classmethod
    def from_value(cls, value: MetricCardModel) -> "MetricCardResponse":
        return cls(
            id=value.id,
            label=value.label,
            value=value.value,
            delta=value.delta,
            tone=value.tone,
        )


class RuntimeActionResponse(BaseModel):
    id: str
    label: str
    owner: str = "runtime"
    kind: str = "operation"
    risk: str = "normal"
    allowed: bool = True
    disabled_reason: str | None = None
    requires_confirmation: bool = False
    reason_required: bool = False
    audit_event: str | None = None
    method: str | None = None
    endpoint: str | None = None

    @classmethod
    def from_value(cls, value: RuntimeActionModel) -> "RuntimeActionResponse":
        return cls(
            id=value.id,
            label=value.label,
            owner=getattr(value, "owner", "runtime"),
            kind=getattr(value, "kind", "operation"),
            risk=value.risk,
            allowed=getattr(value, "allowed", True),
            disabled_reason=getattr(value, "disabled_reason", None),
            requires_confirmation=getattr(value, "requires_confirmation", False),
            reason_required=getattr(value, "reason_required", False),
            audit_event=getattr(value, "audit_event", None),
            method=getattr(value, "method", None),
            endpoint=getattr(value, "endpoint", None),
        )


class OperationsTabResponse(BaseModel):
    id: str
    label: str
    count: int | None = None
    tone: str = "neutral"

    @classmethod
    def from_value(cls, value: OperationsTabModel) -> "OperationsTabResponse":
        return cls(
            id=value.id,
            label=value.label,
            count=value.count,
            tone=value.tone,
        )


class OperationsModuleRoleResponse(BaseModel):
    label: str
    can_operate: bool
    scope: str | None = None

    @classmethod
    def from_value(
        cls, value: OperationsModuleRoleModel
    ) -> "OperationsModuleRoleResponse":
        return cls(
            label=value.label,
            can_operate=value.can_operate,
            scope=value.scope,
        )
