from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import unittest

from crxzipple.core.config import load_settings
from crxzipple.core.db import build_engine, build_session_factory
from crxzipple.modules.tool.application import (
    ToolCatalogReconcileService,
    ToolFunctionCandidate,
    ToolFunctionRequirements,
    ToolSourceDiscoveryRunRecord,
    ToolSourceDiscoveryResult,
)
from crxzipple.modules.tool.domain import (
    ToolCatalogSourceKind,
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolExecutionSupport,
    ToolExecutionTarget,
    ToolFunction,
    ToolFunctionRuntimeKind,
    ToolFunctionStatus,
    ToolMode,
    ToolProviderBackend,
    ToolProviderBackendStatus,
    ToolProviderCapability,
    ToolRun,
    ToolSource,
    ToolSourceStatus,
)
from crxzipple.modules.tool.infrastructure.persistence import (
    SqlAlchemyToolFunctionCatalogRepository,
    SqlAlchemyToolFunctionRepository,
    SqlAlchemyToolProviderBackendRepository,
    SqlAlchemyToolRunRepository,
    SqlAlchemyToolSourceDiscoveryRunRepository,
    SqlAlchemyToolSourceRepository,
)
from tests.unit.support import SqliteTestHarness


class ToolSourceCatalogPersistenceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = SqliteTestHarness()
        self.settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
        )
        self.harness.initialize_schema(settings=self.settings)
        self.engine = build_engine(self.settings)
        self.session_factory = build_session_factory(self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.harness.close()

    def test_source_function_and_backend_repositories_round_trip(self) -> None:
        now = datetime(2026, 5, 19, 8, 0, tzinfo=timezone.utc)

        with self.session_factory() as session:
            source_repository = SqlAlchemyToolSourceRepository(session)
            discovery_repository = SqlAlchemyToolSourceDiscoveryRunRepository(session)
            function_repository = SqlAlchemyToolFunctionRepository(session)
            backend_repository = SqlAlchemyToolProviderBackendRepository(session)

            source_repository.upsert(
                ToolSource(
                    id="source.local.weather",
                    kind=ToolCatalogSourceKind.LOCAL_PACKAGE,
                    display_name="Weather tools",
                    description="Bundled weather tools.",
                    config={"namespace": "open_meteo_weather"},
                    credential_requirements=({"slot": "weather_api_key"},),
                    runtime_requirements=({"runtime": "local_package"},),
                    status=ToolSourceStatus.ACTIVE,
                    revision=1,
                    config_hash="sha256:source-v1",
                    last_discovered_at=now,
                    last_discovery_status="succeeded",
                    created_at=now,
                    updated_at=now,
                ),
            )
            discovery_repository.add(
                ToolSourceDiscoveryRunRecord(
                    discovery_run_id="discovery.source.local.weather.1",
                    source_id="source.local.weather",
                    source_revision=1,
                    config_hash="sha256:source-v1",
                    status="completed",
                    discovered_at=now,
                    function_count=1,
                    provider_backend_count=1,
                    metadata={"provider_name": "weather"},
                ),
            )
            function_repository.upsert(
                ToolFunction(
                    id="function.weather.forecast",
                    source_id="source.local.weather",
                    stable_key="local_package.open_meteo_weather.forecast",
                    name="forecast",
                    display_name="Forecast",
                    description="Fetch a forecast.",
                    input_schema={"type": "object", "properties": {"city": {}}},
                    runtime_kind=ToolFunctionRuntimeKind.LOCAL,
                    handler_ref={"handler": "weather.local:forecast"},
                    capability_ids=("weather", "weather"),
                    credential_requirements=({"slot": "weather_api_key"},),
                    runtime_requirements=({"runtime": "local_package"},),
                    required_effect_ids=("network_request",),
                    execution_support=ToolExecutionSupport(
                        supported_modes=(ToolMode.INLINE, ToolMode.BACKGROUND),
                        supported_strategies=(ToolExecutionStrategy.ASYNC,),
                        supported_environments=(ToolEnvironment.LOCAL,),
                    ),
                    enabled=True,
                    trust_policy={"level": "trusted"},
                    approval_policy={"requires_approval": False},
                    schema_hash="sha256:function-v1",
                    status=ToolFunctionStatus.ACTIVE,
                    revision=1,
                    created_at=now,
                    updated_at=now,
                ),
            )
            backend_repository.upsert(
                ToolProviderBackend(
                    id="backend.openai.image",
                    source_id="source.local.weather",
                    capability=ToolProviderCapability.IMAGE_GENERATION,
                    display_name="OpenAI image",
                    credential_requirements=({"slot": "openai_api_key"},),
                    runtime_ref={"adapter": "openai_image"},
                    priority=10,
                    enabled=True,
                    status=ToolProviderBackendStatus.ACTIVE,
                    created_at=now,
                    updated_at=now,
                ),
            )
            session.commit()

        with self.session_factory() as session:
            source_repository = SqlAlchemyToolSourceRepository(session)
            discovery_repository = SqlAlchemyToolSourceDiscoveryRunRepository(session)
            function_repository = SqlAlchemyToolFunctionRepository(session)
            backend_repository = SqlAlchemyToolProviderBackendRepository(session)

            source = source_repository.get("source.local.weather")
            assert source is not None
            self.assertEqual(source.source_id, "source.local.weather")
            self.assertEqual(source.kind, ToolCatalogSourceKind.LOCAL_PACKAGE)
            self.assertEqual(source.config["namespace"], "open_meteo_weather")
            self.assertEqual(source.last_discovery_status, "succeeded")
            discovery_runs = discovery_repository.list_by_source(source.source_id)
            self.assertEqual(len(discovery_runs), 1)
            self.assertEqual(
                discovery_runs[0].discovery_run_id,
                "discovery.source.local.weather.1",
            )
            self.assertEqual(discovery_runs[0].status.value, "completed")
            self.assertEqual(discovery_runs[0].function_count, 1)
            self.assertEqual(discovery_runs[0].metadata["provider_name"], "weather")

            function = function_repository.get_by_stable_key(
                "local_package.open_meteo_weather.forecast",
            )
            assert function is not None
            self.assertEqual(function.function_id, "function.weather.forecast")
            self.assertEqual(function.source_id, source.source_id)
            self.assertEqual(function.capability_ids, ("weather",))
            self.assertEqual(function.runtime_kind, ToolFunctionRuntimeKind.LOCAL)
            self.assertEqual(
                function.execution_support.supported_modes,
                (ToolMode.INLINE, ToolMode.BACKGROUND),
            )

            backend = backend_repository.get("backend.openai.image")
            assert backend is not None
            self.assertEqual(backend.backend_id, "backend.openai.image")
            self.assertEqual(
                backend.capability,
                ToolProviderCapability.IMAGE_GENERATION,
            )
            self.assertEqual(backend.priority, 10)

            source.status = ToolSourceStatus.DISABLED
            source.revision = 2
            source_repository.upsert(source)
            function.enabled = False
            function.status = ToolFunctionStatus.DISABLED
            function.revision = 2
            function_repository.upsert(function)
            backend.priority = 20
            backend.status = ToolProviderBackendStatus.DISABLED
            backend_repository.upsert(backend)
            session.commit()

        with self.session_factory() as session:
            source_repository = SqlAlchemyToolSourceRepository(session)
            function_repository = SqlAlchemyToolFunctionRepository(session)
            backend_repository = SqlAlchemyToolProviderBackendRepository(session)

            self.assertEqual(
                [source.source_id for source in source_repository.list(
                    status=ToolSourceStatus.DISABLED,
                )],
                ["source.local.weather"],
            )
            self.assertEqual(
                [function.function_id for function in function_repository.list(
                    source_id="source.local.weather",
                    status=ToolFunctionStatus.DISABLED,
                )],
                ["function.weather.forecast"],
            )
            self.assertEqual(
                [backend.backend_id for backend in backend_repository.list(
                    capability=ToolProviderCapability.IMAGE_GENERATION,
                    status=ToolProviderBackendStatus.DISABLED,
                )],
                ["backend.openai.image"],
            )

    def test_tool_run_catalog_reference_fields_round_trip(self) -> None:
        target = ToolExecutionTarget(
            mode=ToolMode.BACKGROUND,
            strategy=ToolExecutionStrategy.ASYNC,
            environment=ToolEnvironment.REMOTE,
        )
        run = ToolRun.create(
            run_id="run.catalog-ref",
            tool_id="legacy.weather.forecast",
            function_id="function.weather.forecast",
            function_revision=7,
            source_id="source.local.weather",
            source_revision=3,
            schema_hash="sha256:function-v7",
            input_payload={"city": "Shanghai"},
            metadata={"caller": "test"},
            target=target,
        )

        with self.session_factory() as session:
            repository = SqlAlchemyToolRunRepository(session)
            repository.add_new(run)
            session.commit()

        with self.session_factory() as session:
            repository = SqlAlchemyToolRunRepository(session)
            persisted = repository.get("run.catalog-ref")

            assert persisted is not None
            self.assertEqual(persisted.tool_id, "legacy.weather.forecast")
            self.assertEqual(persisted.function_id, "function.weather.forecast")
            self.assertEqual(persisted.function_revision, 7)
            self.assertEqual(persisted.source_id, "source.local.weather")
            self.assertEqual(persisted.source_revision, 3)
            self.assertEqual(persisted.schema_hash, "sha256:function-v7")

    def test_function_catalog_repository_supports_reconcile_service(self) -> None:
        observed_at = datetime(2026, 5, 19, 10, 0, tzinfo=timezone.utc)
        candidate = ToolFunctionCandidate(
            stable_key="local_package.weather.forecast",
            source_id="source.local.weather",
            function_id="function.weather.forecast",
            name="forecast",
            description="Fetch a forecast.",
            input_schema={
                "type": "object",
                "properties": {"city": {"type": "string"}},
            },
            runtime_kind="local",
            handler_ref="tools.weather.local:forecast",
            requirements=ToolFunctionRequirements(
                access_requirement_sets=(("network_request",),),
                runtime_requirement_sets=(("daemon:weather",),),
                required_effect_ids=("network_request",),
            ),
            capabilities=("weather",),
            metadata={"provider_name": "local_system"},
        )

        with self.session_factory() as session:
            catalog_repository = SqlAlchemyToolFunctionCatalogRepository(session)
            service = ToolCatalogReconcileService(catalog_repository)
            result = service.reconcile_discovery_result(
                ToolSourceDiscoveryResult.completed(
                    source_id="source.local.weather",
                    candidates=(candidate,),
                    discovered_at=observed_at,
                ),
            )
            session.commit()

        self.assertEqual(
            [function.function_id for function in result.created],
            ["function.weather.forecast"],
        )

        with self.session_factory() as session:
            catalog_repository = SqlAlchemyToolFunctionCatalogRepository(session)
            records = catalog_repository.list_by_source("source.local.weather")
            self.assertEqual(len(records), 1)
            record = records[0]
            self.assertEqual(record.handler_ref, "tools.weather.local:forecast")
            self.assertEqual(
                record.requirements.access_requirement_sets,
                (("network_request",),),
            )
            self.assertEqual(
                record.requirements.runtime_requirement_sets,
                (("daemon:weather",),),
            )
            self.assertEqual(record.status.value, "active")

            service = ToolCatalogReconcileService(catalog_repository)
            stale_result = service.reconcile(
                source_id="source.local.weather",
                candidates=(),
                observed_at=observed_at,
            )
            session.commit()

        self.assertEqual(
            [function.function_id for function in stale_result.stale],
            ["function.weather.forecast"],
        )
