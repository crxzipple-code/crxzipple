from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.modules.operations.interfaces.http_models import (
    OperationsActionAuditResponse,
)

router = APIRouter()


@router.get(
    "/actions/audits",
    response_model=list[OperationsActionAuditResponse],
)
def list_operations_action_audits(
    container: Annotated[AppContainer, Depends(get_container)],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[OperationsActionAuditResponse]:
    return [
        OperationsActionAuditResponse.from_value(audit)
        for audit in container.require(
            AppKey.OPERATIONS_ACTION_AUDIT_STORE
        ).list_recent(
            limit=limit,
            offset=offset,
        )
    ]
