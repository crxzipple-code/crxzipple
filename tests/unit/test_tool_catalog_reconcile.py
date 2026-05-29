from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import unittest

from crxzipple.modules.tool.application import (
    ToolCatalogReconcileService,
    ToolFunctionCandidate,
    ToolFunctionCatalogRecord,
    ToolFunctionRequirements,
    ToolFunctionRuntimeKind,
    ToolFunctionStatus,
    ToolSourceDiscoveryResult,
)
from crxzipple.modules.tool.application.specifications import ToolSpec
from crxzipple.modules.tool.domain import (
    ToolKind,
    ToolParameter,
    ToolDefinitionOrigin,
)
from crxzipple.shared.domain.events import Event


class _FakeToolFunctionCatalogRepository:
    def __init__(
        self,
        functions: tuple[ToolFunctionCatalogRecord, ...] = (),
    ) -> None:
        self.functions: dict[str, ToolFunctionCatalogRecord] = {
            function.stable_key: function for function in functions
        }
        self.added: list[ToolFunctionCatalogRecord] = []
        self.updated: list[ToolFunctionCatalogRecord] = []

    def list_by_source(self, source_id: str) -> tuple[ToolFunctionCatalogRecord, ...]:
        return tuple(
            function
            for function in self.functions.values()
            if function.source_id == source_id
        )

    def add(self, function: ToolFunctionCatalogRecord) -> None:
        self.functions[function.stable_key] = function
        self.added.append(function)

    def update(self, function: ToolFunctionCatalogRecord) -> None:
        self.functions[function.stable_key] = function
        self.updated.append(function)


class _FakeEventPublisher:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def publish(self, event: Event) -> None:
        self.events.append(event)


class ToolCatalogReconcileTestCase(unittest.TestCase):
    def test_candidate_from_tool_spec_carries_discovery_contract(self) -> None:
        spec = ToolSpec(
            id="sample.echo",
            name="Echo",
            description="Echoes input.",
            provider_name="sample",
            kind=ToolKind.MCP,
            parameters=(
                ToolParameter(
                    name="message",
                    data_type="string",
                    description="Message to echo.",
                ),
            ),
            required_effect_ids=("tool.call",),
            runtime_requirement_sets=(("mcp:sample",),),
            capability_ids=("text.echo",),
            definition_origin=ToolDefinitionOrigin.REMOTE_DISCOVERY,
            runtime_key="mcp.sample.echo",
        )

        candidate = ToolFunctionCandidate.from_tool_spec(spec)

        self.assertEqual(candidate.stable_key, "mcp.sample.echo")
        self.assertEqual(candidate.source_id, "sample")
        self.assertEqual(candidate.function_id, "sample.echo")
        self.assertEqual(candidate.name, "Echo")
        self.assertEqual(candidate.description, "Echoes input.")
        self.assertEqual(candidate.runtime_kind, ToolFunctionRuntimeKind.MCP)
        self.assertEqual(candidate.handler_ref, "mcp.sample.echo")
        self.assertEqual(candidate.capabilities, ("text.echo",))
        self.assertEqual(candidate.requirements.required_effect_ids, ("tool.call",))
        self.assertEqual(
            candidate.requirements.runtime_requirement_sets,
            (("mcp:sample",),),
        )
        self.assertEqual(
            candidate.input_schema["properties"]["message"]["type"],
            "string",
        )
        self.assertTrue(candidate.schema_hash.startswith("sha256:"))

    def test_reconcile_creates_new_function_records_and_events(self) -> None:
        repository = _FakeToolFunctionCatalogRepository()
        publisher = _FakeEventPublisher()
        service = ToolCatalogReconcileService(
            repository,
            event_publisher=publisher,
        )
        candidate = _candidate("list_pets")

        result = service.reconcile(
            source_id="petstore",
            candidates=(candidate,),
            observed_at=_time(1),
        )

        self.assertEqual(len(result.created), 1)
        self.assertEqual(result.created[0].stable_key, candidate.stable_key)
        self.assertEqual(result.created[0].status, ToolFunctionStatus.ACTIVE)
        self.assertEqual(repository.added, [result.created[0]])
        self.assertEqual([event.name for event in publisher.events], ["tool.function.created"])

    def test_reconcile_updates_schema_and_preserves_governance_fields(self) -> None:
        existing = ToolFunctionCatalogRecord.from_candidate(
            _candidate("list_pets"),
            observed_at=_time(1),
        )
        governed = replace(
            existing,
            enabled=False,
            trust_policy={"trust": "workspace"},
            approval_policy={"mode": "manual"},
            credential_binding_overrides={"api_key": "petstore-api-key"},
            required_effect_overrides=("pets.read.approved",),
        )
        repository = _FakeToolFunctionCatalogRepository((governed,))
        publisher = _FakeEventPublisher()
        service = ToolCatalogReconcileService(
            repository,
            event_publisher=publisher,
        )
        candidate = _candidate(
            "list_pets",
            description="Lists pets with a page size.",
            input_schema={
                "type": "object",
                "properties": {"limit": {"type": "integer"}},
                "required": ["limit"],
                "additionalProperties": False,
            },
            capabilities=("pets.read", "pets.page"),
        )

        result = service.reconcile(
            source_id="petstore",
            candidates=(candidate,),
            observed_at=_time(2),
        )

        self.assertEqual(len(result.updated), 1)
        updated = repository.functions["openapi.petstore.list_pets"]
        self.assertNotEqual(updated.schema_hash, governed.schema_hash)
        self.assertEqual(updated.description, "Lists pets with a page size.")
        self.assertEqual(updated.capabilities, ("pets.read", "pets.page"))
        self.assertFalse(updated.enabled)
        self.assertEqual(updated.trust_policy, {"trust": "workspace"})
        self.assertEqual(updated.approval_policy, {"mode": "manual"})
        self.assertEqual(
            updated.credential_binding_overrides,
            {"api_key": "petstore-api-key"},
        )
        self.assertEqual(updated.required_effect_overrides, ("pets.read.approved",))
        self.assertEqual(updated.revision, governed.revision + 1)
        self.assertEqual([event.name for event in publisher.events], ["tool.function.updated"])
        self.assertIn("schema_hash", publisher.events[0].payload["changed_fields"])

    def test_reconcile_marks_missing_candidates_stale_then_deprecated(self) -> None:
        keep = ToolFunctionCatalogRecord.from_candidate(
            _candidate("list_pets"),
            observed_at=_time(1),
        )
        missing = replace(
            ToolFunctionCatalogRecord.from_candidate(
                _candidate("delete_pet", capabilities=("pets.write",)),
                observed_at=_time(1),
            ),
            enabled=False,
            approval_policy={"mode": "manual"},
        )
        repository = _FakeToolFunctionCatalogRepository((keep, missing))
        publisher = _FakeEventPublisher()
        service = ToolCatalogReconcileService(
            repository,
            event_publisher=publisher,
        )

        first = service.reconcile(
            source_id="petstore",
            candidates=(_candidate("list_pets"),),
            observed_at=_time(2),
        )
        second = service.reconcile(
            source_id="petstore",
            candidates=(_candidate("list_pets"),),
            observed_at=_time(3),
            deprecate_stale=True,
        )

        self.assertEqual(len(first.stale), 1)
        self.assertEqual(first.stale[0].status, ToolFunctionStatus.STALE)
        self.assertEqual(len(second.deprecated), 1)
        deprecated = repository.functions["openapi.petstore.delete_pet"]
        self.assertEqual(deprecated.status, ToolFunctionStatus.DEPRECATED)
        self.assertFalse(deprecated.enabled)
        self.assertEqual(deprecated.approval_policy, {"mode": "manual"})
        self.assertEqual(
            [event.name for event in publisher.events],
            ["tool.function.stale", "tool.function.deprecated"],
        )

    def test_dry_run_returns_preview_without_persisting_or_publishing(self) -> None:
        repository = _FakeToolFunctionCatalogRepository()
        publisher = _FakeEventPublisher()
        service = ToolCatalogReconcileService(
            repository,
            event_publisher=publisher,
        )

        result = service.reconcile_discovery_result(
            ToolSourceDiscoveryResult.completed(
                source_id="petstore",
                candidates=(_candidate("list_pets"),),
                discovered_at=_time(1),
            ),
            dry_run=True,
        )

        self.assertTrue(result.dry_run)
        self.assertEqual(len(result.created), 1)
        self.assertEqual(repository.functions, {})
        self.assertEqual(publisher.events, [])


def _candidate(
    name: str,
    *,
    description: str | None = None,
    input_schema: dict[str, object] | None = None,
    capabilities: tuple[str, ...] = ("pets.read",),
) -> ToolFunctionCandidate:
    return ToolFunctionCandidate(
        stable_key=f"openapi.petstore.{name}",
        source_id="petstore",
        function_id=f"petstore.{name}",
        name=name.replace("_", " ").title(),
        description=description or f"{name.replace('_', ' ').title()} operation.",
        input_schema=input_schema
        or {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        runtime_kind=ToolFunctionRuntimeKind.OPENAPI,
        handler_ref=f"openapi.petstore.{name}",
        requirements=ToolFunctionRequirements(
            access_requirement_sets=(("petstore-api-key",),),
            runtime_requirement_sets=(("http:petstore",),),
            required_effect_ids=("pets.read",),
        ),
        capabilities=capabilities,
        metadata={"operation_id": name},
    )


def _time(second: int) -> datetime:
    return datetime(2026, 5, 19, 0, 0, second, tzinfo=timezone.utc)


if __name__ == "__main__":
    unittest.main()
