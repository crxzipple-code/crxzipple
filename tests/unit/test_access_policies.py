from __future__ import annotations

import unittest

from crxzipple.modules.access.application.actions import (
    AccessActionRequest,
    AccessActionService,
)
from tests.unit.test_access_actions import FakeAccessActionAuditRepository


class AccessPolicyBoundaryTestCase(unittest.TestCase):
    def test_internal_abac_policy_intents_are_not_access_actions(self) -> None:
        audit_repository = FakeAccessActionAuditRepository()
        service = AccessActionService(audit_repository=audit_repository)

        with self.assertRaisesRegex(ValueError, "unsupported access action intent"):
            service.execute(
                AccessActionRequest(
                    action_id="act_create_internal_policy",
                    resource_kind="authorization_policy",
                    target_id="policy_allow_tool",
                    intent="create_authorization_policy",
                    changes={"effect": "allow", "actions": ["tool.run"]},
                    reason="internal ABAC policy belongs to authorization",
                ),
            )

        self.assertEqual(audit_repository.records["audit_1"].status, "failed")
        self.assertEqual(
            audit_repository.records["audit_1"].error["message"],
            "unsupported access action intent 'create_authorization_policy'.",
        )


if __name__ == "__main__":
    unittest.main()
