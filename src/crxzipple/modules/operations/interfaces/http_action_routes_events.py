from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.runtime_container import AppContainer
from crxzipple.modules.operations.interfaces.http_action_service import (
    operations_action_service,
)
from crxzipple.modules.operations.interfaces.http_action_audit import (
    _begin_operations_action_audit,
    _mark_operations_action_failed,
    _mark_operations_action_succeeded,
)
from crxzipple.modules.operations.interfaces.http_models import (
    OperationsEventSubscriptionAdvanceRequest,
    OperationsEventSubscriptionAdvanceResponse,
)

router = APIRouter()


@router.post(
    "/events/subscriptions/advance-to-head",
    response_model=OperationsEventSubscriptionAdvanceResponse,
)
def advance_event_subscriptions_to_head(
    request: OperationsEventSubscriptionAdvanceRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OperationsEventSubscriptionAdvanceResponse:
    reason, audit_id = _begin_operations_action_audit(
        container,
        request,
        action_type="events.subscriptions.advance_to_head",
        target_type="event_subscription",
        target_id=request.subscription_id,
        target={
            "subscription_id": request.subscription_id,
            "source_topic": request.source_topic,
            "status": request.status,
            "observer_only": request.observer_only,
            "dry_run": request.dry_run,
        },
        default_reason="Operations event subscription cursor advance",
        risk="dangerous" if not request.dry_run else "normal",
    )
    try:
        result = operations_action_service(
            container
        ).advance_event_subscriptions_to_head(
            subscription_id=request.subscription_id,
            source_topic=request.source_topic,
            status=request.status,
            observer_only=request.observer_only,
            dry_run=request.dry_run,
            reason=reason,
        )
    except Exception as exc:
        _mark_operations_action_failed(container, audit_id, exc)
        raise
    response = OperationsEventSubscriptionAdvanceResponse.from_result(result)
    _mark_operations_action_succeeded(container, audit_id, response)
    return response


@router.post(
    "/events/observers/advance-to-head",
    response_model=OperationsEventSubscriptionAdvanceResponse,
)
def advance_event_observers_to_head(
    request: OperationsEventSubscriptionAdvanceRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OperationsEventSubscriptionAdvanceResponse:
    reason, audit_id = _begin_operations_action_audit(
        container,
        request,
        action_type="events.observers.advance_to_head",
        target_type="event_subscription",
        target_id=request.subscription_id,
        target={
            "subscription_id": request.subscription_id,
            "source_topic": request.source_topic,
            "status": request.status,
            "observer_only": True,
            "dry_run": request.dry_run,
        },
        default_reason="Operations observer cursor advance",
        risk="dangerous" if not request.dry_run else "normal",
    )
    try:
        result = operations_action_service(
            container
        ).advance_event_subscriptions_to_head(
            subscription_id=request.subscription_id,
            source_topic=request.source_topic,
            status=request.status,
            observer_only=True,
            dry_run=request.dry_run,
            reason=reason,
        )
    except Exception as exc:
        _mark_operations_action_failed(container, audit_id, exc)
        raise
    response = OperationsEventSubscriptionAdvanceResponse.from_result(result)
    _mark_operations_action_succeeded(container, audit_id, response)
    return response
