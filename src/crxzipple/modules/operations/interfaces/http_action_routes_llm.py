from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from crxzipple.interfaces.authorization import authorize_llm_action
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.runtime_container import AppContainer
from crxzipple.modules.llm.domain import (
    LlmAdapterNotConfiguredError,
    LlmInvocationNotAllowedError,
    LlmNotFoundError,
)
from crxzipple.modules.operations.interfaces.http_action_audit import (
    _begin_operations_action_audit,
    _mark_operations_action_failed,
    _mark_operations_action_succeeded,
)
from crxzipple.modules.operations.interfaces.http_action_service import (
    operations_action_service,
)
from crxzipple.modules.operations.interfaces.http_models import (
    OperationsActionReasonRequest,
    OperationsLlmWarmupResponse,
)

router = APIRouter()


@router.post(
    "/llm/profiles/{llm_id}/warmup",
    response_model=OperationsLlmWarmupResponse,
)
def warmup_llm_profile_from_operations(
    llm_id: str,
    request: OperationsActionReasonRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OperationsLlmWarmupResponse:
    reason, audit_id = _begin_operations_action_audit(
        container,
        request,
        action_type="llm.profile.warmup",
        target_type="llm_profile",
        target_id=llm_id,
        target={"llm_id": llm_id},
        default_reason="Operations LLM profile warmup",
        risk="controlled",
    )
    try:
        authorize_llm_action(
            container,
            llm_id=llm_id,
            action="llm.warmup",
            interface_name="operations",
        )
        result = operations_action_service(container).warmup_llm_profile(
            llm_id=llm_id,
            reason=reason,
        )
    except LlmNotFoundError as exc:
        http_exc = HTTPException(status_code=404, detail=str(exc))
        _mark_operations_action_failed(container, audit_id, http_exc)
        raise http_exc from None
    except LlmInvocationNotAllowedError as exc:
        http_exc = HTTPException(status_code=400, detail=str(exc))
        _mark_operations_action_failed(container, audit_id, http_exc)
        raise http_exc from None
    except LlmAdapterNotConfiguredError as exc:
        http_exc = HTTPException(status_code=503, detail=str(exc))
        _mark_operations_action_failed(container, audit_id, http_exc)
        raise http_exc from None
    except Exception as exc:
        _mark_operations_action_failed(container, audit_id, exc)
        raise
    response = OperationsLlmWarmupResponse(
        llm_id=result.llm_id,
        status=result.status,
        details=dict(result.details),
    )
    _mark_operations_action_succeeded(container, audit_id, response)
    return response
