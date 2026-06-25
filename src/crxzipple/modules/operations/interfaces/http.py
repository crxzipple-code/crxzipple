from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.events import EventTopicWatch
from crxzipple.modules.operations.interfaces.http_models import (
    OperationsRuntimeStatusResponse,
)
from crxzipple.modules.operations.interfaces.http_runtime import _runtime_status
from crxzipple.modules.operations.interfaces.http_stream_payloads import (
    format_operations_sse_event,
    operations_stream_record_payload,
)
from crxzipple.modules.operations.interfaces.http_action_routes import (
    router as action_router,
)
from crxzipple.modules.operations.interfaces.http_projection_routes import (
    router as projection_router,
)



router = APIRouter()

_OPERATIONS_STREAM_TOPIC = "events.named.operations.projection.invalidated"
_OPERATIONS_STREAM_DISCOVERY_INTERVAL_SECONDS = 0.25


@router.get("/runtime", response_model=OperationsRuntimeStatusResponse)
def get_operations_runtime_status(
    container: Annotated[AppContainer, Depends(get_container)],
) -> OperationsRuntimeStatusResponse:
    return _runtime_status(container)


@router.get("/stream")
def stream_operations_refresh_feed(
    container: Annotated[AppContainer, Depends(get_container)],
    snapshot_limit: Annotated[int, Query(ge=0, le=50)] = 0,
    timeout_seconds: Annotated[float, Query(gt=0.0, le=300.0)] = 120.0,
) -> StreamingResponse:
    events_service = container.require(AppKey.EVENTS_SERVICE)
    if events_service is None:
        raise HTTPException(status_code=503, detail="Event service is not available.")

    def event_stream():
        cursor = events_service.snapshot_event_topic(_OPERATIONS_STREAM_TOPIC)
        yield format_operations_sse_event(
            "connected",
            {
                "event_type": "connected",
                "modules": [],
                "stream_role": "operations",
                "stream_scope": "projection_refresh",
            },
        )
        if snapshot_limit > 0:
            records = events_service.read_recent_event_topic(
                _OPERATIONS_STREAM_TOPIC,
                limit=snapshot_limit,
            )
            yield format_operations_sse_event(
                "snapshot",
                {
                    "event_type": "snapshot",
                    "modules": [],
                    "records": [
                        operations_stream_record_payload(record) for record in records
                    ],
                },
            )

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            records = events_service.read_event_topic(
                _OPERATIONS_STREAM_TOPIC,
                after_cursor=cursor,
                limit=100,
            )
            if records:
                cursor = records[-1].cursor
                for record in records:
                    yield format_operations_sse_event(
                        "projection_updated",
                        operations_stream_record_payload(record),
                    )
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            events_service.wait_for_event_topics(
                (
                    EventTopicWatch(
                        topic=_OPERATIONS_STREAM_TOPIC,
                        after_cursor=cursor,
                    ),
                ),
                timeout_seconds=min(
                    remaining,
                    _OPERATIONS_STREAM_DISCOVERY_INTERVAL_SECONDS,
                ),
            )
        yield format_operations_sse_event(
            "timeout",
            {
                "event_type": "timeout",
                "modules": [],
            },
        )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Crx-Stream-Role": "operations",
            "X-Crx-Stream-Scope": "projection_refresh",
        },
    )


router.include_router(action_router)
router.include_router(projection_router)
