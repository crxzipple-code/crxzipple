from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.modules.channels.application.payload_redaction import (
    redact_channel_payload,
)
from crxzipple.modules.channels.domain import channel_dead_letter_topic
from crxzipple.modules.channels.interfaces.http_models import (
    ChannelDeadLetterRecordResponse,
    ChannelDeadLetterReplayRequest,
    ChannelDeadLetterReplayResponse,
)


router = APIRouter()


@router.get("/dead-letters/{channel_type}")
def list_channel_dead_letters(
    channel_type: str,
    container: Annotated[AppContainer, Depends(get_container)],
    runtime_id: str | None = Query(default=None),
    after_cursor: str | None = Query(default=None),
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[ChannelDeadLetterRecordResponse]:
    events_service = container.require(AppKey.EVENTS_SERVICE)
    if events_service is None:
        raise HTTPException(
            status_code=503,
            detail="Event service is not available for dead-letter queries.",
        )
    topic = channel_dead_letter_topic(channel_type, runtime_id=runtime_id)
    records = events_service.read_event_topic(
        topic,
        after_cursor=(
            after_cursor.strip()
            if isinstance(after_cursor, str) and after_cursor.strip()
            else None
        ),
        limit=limit,
    )
    return [
        ChannelDeadLetterRecordResponse(
            cursor=record.cursor,
            topic=record.envelope.topic,
            event_id=record.envelope.id,
            kind=record.envelope.kind,
            created_at=record.envelope.created_at.isoformat(),
            payload=redact_channel_payload(dict(record.envelope.payload)),
            target=(
                record.envelope.target.to_payload()
                if record.envelope.target is not None
                else {}
            ),
        )
        for record in records
    ]


@router.post("/dead-letters/{channel_type}/replay")
def replay_channel_dead_letter(
    channel_type: str,
    payload: ChannelDeadLetterReplayRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ChannelDeadLetterReplayResponse:
    if channel_type.strip().lower() == "webhook":
        try:
            result = container.require(
                AppKey.WEBHOOK_CHANNEL_RUNTIME_SERVICE,
            ).replay_dead_letter_record(
                runtime_id=payload.runtime_id,
                cursor=payload.cursor,
                event_id=payload.event_id,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return ChannelDeadLetterReplayResponse(
            replayed=bool(result["replayed"]),
            dead_letter_topic=str(result["dead_letter_topic"]),
            dead_letter_cursor=str(result["dead_letter_cursor"]),
            dead_letter_event_id=str(result["dead_letter_event_id"]),
            outbound_id=str(result["outbound_id"]),
            replay_mode=str(result["replay_mode"]),
            callback_status=(
                str(result["callback_status"])
                if result.get("callback_status") is not None
                else None
            ),
        )
    raise HTTPException(
        status_code=409,
        detail=(
            "Dead-letter replay no longer requeues generic legacy outbound events. "
            "Use the owning channel runtime replay path."
        ),
    )
