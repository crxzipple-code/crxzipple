from __future__ import annotations

import unittest

from crxzipple.shared.access import (
    AccessConsumerRef,
    AccessCredentialKind,
    AccessCredentialRequirementDeclaration,
    AccessCredentialRequirementSet,
    AccessCredentialSlotRef,
    AccessCredentialTransport,
    AccessSetupFlowHint,
    AccessSetupFlowKind,
)


class AccessCredentialRequirementContractTestCase(unittest.TestCase):
    def test_requirement_declaration_normalizes_identity_and_slot_fields(self) -> None:
        consumer = AccessConsumerRef(
            consumer_id=" tool.openapi:weather.search ",
            module=" tool ",
            component=" openapi_remote ",
            runtime_ref=" openapi.weather.search ",
        )
        declaration = AccessCredentialRequirementDeclaration(
            requirement_id=" weather.search.api_key ",
            consumer=consumer,
            slot=AccessCredentialSlotRef(
                slot=" api_key ",
                expected_kind=AccessCredentialKind.API_KEY,
                binding_id=" weather-api-key ",
                display_name=" Weather API key ",
                scopes=(" forecast ", "", " current "),
            ),
            provider=" weather ",
            transport=AccessCredentialTransport.HEADER,
            parameter_name=" X-API-Key ",
            setup_flow_hint=AccessSetupFlowHint(
                flow_kind=AccessSetupFlowKind.ENV_BINDING,
                provider=" weather ",
            ),
        )

        self.assertEqual(declaration.requirement_id, "weather.search.api_key")
        self.assertEqual(declaration.consumer.consumer_id, "tool.openapi:weather.search")
        self.assertEqual(declaration.consumer.module, "tool")
        self.assertEqual(declaration.slot.slot, "api_key")
        self.assertEqual(declaration.slot.binding_id, "weather-api-key")
        self.assertEqual(declaration.slot.scopes, ("forecast", "current"))
        self.assertEqual(declaration.provider, "weather")
        self.assertEqual(declaration.parameter_name, "X-API-Key")
        self.assertEqual(declaration.setup_flow_hint.flow_kind, AccessSetupFlowKind.ENV_BINDING)

    def test_requirement_set_groups_declarations_for_one_consumer(self) -> None:
        consumer = AccessConsumerRef(consumer_id="channel.lark:default", module="channels")
        declaration = AccessCredentialRequirementDeclaration(
            requirement_id="channel.lark.default.app_secret",
            consumer=consumer,
            slot=AccessCredentialSlotRef(
                slot="lark_app_secret",
                expected_kind=AccessCredentialKind.APP_SECRET,
            ),
            provider="lark",
        )

        requirement_set = AccessCredentialRequirementSet(
            requirement_set_id="channel.lark.default.credentials",
            consumer=consumer,
            requirements=(declaration,),
        )

        self.assertEqual(requirement_set.requirement_set_id, "channel.lark.default.credentials")
        self.assertEqual(requirement_set.consumer.module, "channels")
        self.assertEqual(requirement_set.requirements, (declaration,))

    def test_blank_required_fields_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            AccessCredentialSlotRef(
                slot=" ",
                expected_kind=AccessCredentialKind.API_KEY,
            )

        with self.assertRaises(ValueError):
            AccessCredentialRequirementSet(
                requirement_set_id=" ",
                consumer=AccessConsumerRef(consumer_id="tool.test", module="tool"),
            )


if __name__ == "__main__":
    unittest.main()
