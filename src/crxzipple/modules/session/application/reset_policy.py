from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from crxzipple.modules.session.domain.exceptions import SessionValidationError
from crxzipple.modules.session.domain.value_objects import (
    SessionResetDecision,
    SessionResetPolicy,
)


def evaluate_session_reset(
    *,
    updated_at: datetime,
    policy: SessionResetPolicy | None,
    now: datetime,
) -> SessionResetDecision:
    if policy is None:
        return SessionResetDecision(should_reset=False)

    candidates: list[tuple[str, datetime]] = []
    if policy.idle_minutes is not None:
        if policy.idle_minutes <= 0:
            raise SessionValidationError(
                "Session idle_minutes must be greater than zero.",
            )
        candidates.append(("idle", idle_expiry(updated_at, policy.idle_minutes)))
    if policy.daily_reset_hour_utc is not None:
        if not 0 <= policy.daily_reset_hour_utc <= 23:
            raise SessionValidationError(
                "Session daily_reset_hour_utc must be between 0 and 23.",
            )
        candidates.append(
            ("daily", daily_expiry(updated_at, policy.daily_reset_hour_utc)),
        )

    if not candidates:
        return SessionResetDecision(should_reset=False)

    reason, expires_at = min(candidates, key=lambda item: item[1])
    if now >= expires_at:
        return SessionResetDecision(
            should_reset=True,
            reason=reason,
            expires_at=expires_at,
        )
    return SessionResetDecision(
        should_reset=False,
        expires_at=expires_at,
    )


def idle_expiry(updated_at: datetime, idle_minutes: int) -> datetime:
    return updated_at + timedelta(minutes=idle_minutes)


def daily_expiry(updated_at: datetime, daily_reset_hour_utc: int) -> datetime:
    normalized = updated_at.astimezone(timezone.utc)
    boundary = datetime.combine(
        normalized.date(),
        time(hour=daily_reset_hour_utc, tzinfo=timezone.utc),
    )
    if normalized >= boundary:
        boundary += timedelta(days=1)
    return boundary
