from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from crxzipple.modules.session.application.reset_policy import evaluate_session_reset
from crxzipple.modules.session.domain import SessionResetPolicy
from crxzipple.modules.session.domain.exceptions import SessionValidationError


class SessionResetPolicyTestCase(unittest.TestCase):
    def test_idle_policy_resets_after_expiry(self) -> None:
        started_at = datetime(2026, 6, 21, 1, 0, tzinfo=timezone.utc)

        decision = evaluate_session_reset(
            updated_at=started_at,
            policy=SessionResetPolicy(idle_minutes=30),
            now=started_at + timedelta(minutes=31),
        )

        self.assertTrue(decision.should_reset)
        self.assertEqual(decision.reason, "idle")

    def test_daily_policy_picks_next_utc_boundary(self) -> None:
        updated_at = datetime(2026, 6, 21, 1, 0, tzinfo=timezone.utc)

        decision = evaluate_session_reset(
            updated_at=updated_at,
            policy=SessionResetPolicy(daily_reset_hour_utc=2),
            now=datetime(2026, 6, 21, 1, 30, tzinfo=timezone.utc),
        )

        self.assertFalse(decision.should_reset)
        self.assertEqual(
            decision.expires_at,
            datetime(2026, 6, 21, 2, 0, tzinfo=timezone.utc),
        )

    def test_invalid_policy_is_rejected(self) -> None:
        with self.assertRaises(SessionValidationError):
            evaluate_session_reset(
                updated_at=datetime(2026, 6, 21, 1, 0, tzinfo=timezone.utc),
                policy=SessionResetPolicy(idle_minutes=0),
                now=datetime(2026, 6, 21, 1, 0, tzinfo=timezone.utc),
            )


if __name__ == "__main__":
    unittest.main()
