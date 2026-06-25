from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class OperationsActionAuditRequest(BaseModel):
    operator: str | None = None
    source: str | None = "operations"
    metadata: dict[str, Any] = Field(default_factory=dict)


class OperationsActionRequest(BaseModel):
    reason: str | None = None
    confirmation: bool | str | None = None
    risk_acknowledged: bool = False
    risk_ack: bool = False
    operator: str | None = None
    source: str | None = "operations"
    metadata: dict[str, Any] = Field(default_factory=dict)
    audit: OperationsActionAuditRequest | None = None

    def acknowledged_risk(self) -> bool:
        return bool(self.risk_acknowledged or self.risk_ack)


class OperationsActionReasonRequest(OperationsActionRequest):
    pass


class OperationsDaemonServiceActionRequest(OperationsActionRequest):
    pass
