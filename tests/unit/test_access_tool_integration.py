from __future__ import annotations

import unittest

from crxzipple.modules.access.application.inventory import (
    AccessInventoryInput,
    AccessReadinessCheckSpec,
    collect_access_inventory_from_read_models,
)
from crxzipple.modules.access.application.migration import (
    AccessMigrationSnapshot,
    build_access_migration_plan,
)
from crxzipple.modules.access.application.query import AccessControlPlaneQueryProvider
from crxzipple.modules.access.application.read_models import (
    AccessConsumerBindingReadModel,
)
from crxzipple.modules.access.application.repositories import AccessAssetRecord
from crxzipple.modules.access.domain.resources import AccessResourceKind
from crxzipple.modules.tool.domain.entities import Tool


class AccessToolIntegrationTests(unittest.TestCase):
    def test_tool_requirements_are_import_input_for_access_consumer_binding(self) -> None:
        tool = Tool(
            id="search.docs",
            name="Search Docs",
            description="Search private docs.",
            access_requirement_sets=(
                ("openai:api_key(env:TOOL_TOKEN)", "openai:api_key(env:TOOL_TOKEN)"),
            ),
        )
        plan = build_access_migration_plan(
            AccessMigrationSnapshot(tool_specs=(tool,), source="unit-test"),
        )

        tool_consumers = tuple(
            item
            for item in plan.consumer_bindings
            if item.consumer_module == "tool" and item.consumer_id == tool.id
        )

        self.assertEqual(len(tool_consumers), 1)
        self.assertEqual(
            tool_consumers[0].requirement_sets,
            (("openai:api_key(env:TOOL_TOKEN)",),),
        )
        self.assertEqual(
            tool_consumers[0].metadata["source_path"],
            "tool.access_requirement_sets",
        )

    def test_inventory_checks_tool_readiness_from_consumer_binding_only(self) -> None:
        observed_specs: list[tuple[AccessReadinessCheckSpec, ...]] = []

        def check_readiness(
            specs: tuple[AccessReadinessCheckSpec, ...],
        ) -> tuple[dict[str, object], ...]:
            observed_specs.append(specs)
            return tuple(
                {
                    "target_type": target_type,
                    "requirement": requirement,
                    "status": "setup_needed",
                    "ready": False,
                    "setup_available": True,
                }
                for target_type, requirement, _allow_literal in specs
            )

        inventory = collect_access_inventory_from_read_models(
            AccessInventoryInput(
                consumer_bindings=(
                    AccessConsumerBindingReadModel(
                        binding_id="consumer_binding:tool:tool:search-docs",
                        consumer_module="tool",
                        consumer_kind="tool",
                        consumer_id="search.docs",
                        display_name="Search Docs",
                        requirement_sets=(
                            ("openai:api_key(env:TOOL_TOKEN)",),
                        ),
                    ),
                ),
            ),
            check_readiness=check_readiness,
        )

        self.assertEqual(inventory["counts"]["blocked"], 1)
        self.assertEqual(
            observed_specs,
            [(("credential_binding", "env:TOOL_TOKEN", False),)],
        )
        target = inventory["targets"][0]
        self.assertEqual(target["metadata"]["tool_ids"], ["search.docs"])
        self.assertEqual(
            target["metadata"]["declared_requirements"],
            ["openai:api_key(env:TOOL_TOKEN)"],
        )

    def test_access_query_does_not_rebuild_tool_binding_from_asset_policy(self) -> None:
        class LegacyAssetOnlyRepository:
            def list_assets(self) -> tuple[AccessAssetRecord, ...]:
                return (
                    AccessAssetRecord(
                        asset_id="access_asset:requirement:legacy-tool",
                        asset_kind=AccessResourceKind.ACCESS_REQUIREMENT.value,
                        display_name="Legacy tool requirement",
                        governance_scope="module",
                        consumer_modules=("tool",),
                        readiness_policy={
                            "requirement_sets": [["env:SHADOW_TOOL_TOKEN"]],
                        },
                    ),
                )

            def list_credential_bindings(self) -> tuple[object, ...]:
                return ()

        provider = AccessControlPlaneQueryProvider(
            governance_repository=LegacyAssetOnlyRepository(),
        )

        payload = provider.overview().to_payload()

        self.assertEqual(payload["consumer_bindings"], [])


if __name__ == "__main__":
    unittest.main()
