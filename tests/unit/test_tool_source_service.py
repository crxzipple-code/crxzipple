from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import sys
import tempfile
import time
import unittest
from pathlib import Path

from crxzipple.app import AssemblyTarget
from crxzipple.app.keys import AppKey
from crxzipple.modules.tool.application import (
    ExecuteToolInput,
    ToolDiscoveryAdapter,
    ToolDiscoveryAdapterRegistry,
    ToolFunctionCandidate,
    ToolFunctionRequirements,
    ToolFunctionRuntimeKind,
    ToolDiscoveryService,
    ToolSourceCatalogKind,
    ToolSourceCatalogRecord,
    ToolSourceDiscoveryResult,
)
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.domain import (
    ToolEnvironment,
    ToolFunctionStatus,
    ToolSourceStatus,
)
from crxzipple.modules.tool.infrastructure import (
    ToolPackageDiscoveryAdapter,
    discover_tool_package_plans,
    tool_source_records_from_package_plans,
)
from crxzipple.modules.tool.infrastructure.cli_source import (
    discover_cli_source,
    register_cli_guided_handlers,
)
from crxzipple.modules.tool.infrastructure.cli_source_config import CliToolSourceConfig
from crxzipple.modules.tool.infrastructure.cli_source_runtime import CliGuidedRuntime
from crxzipple.modules.tool.infrastructure.runtimes.registry import ToolRuntimeRegistry
from crxzipple.modules.process.domain import (
    ProcessOutputWindow,
    ProcessSession,
    ProcessStatus,
)
from crxzipple.shared.access import (
    AccessConsumerRef,
    AccessCredentialKind,
    AccessCredentialRequirementDeclaration,
    AccessCredentialRequirementSet,
    AccessCredentialSlotRef,
    CredentialBindingRef,
)
from crxzipple.shared.domain.events import named_event_topic
from crxzipple.shared.event_contracts import TOOL_CLI_EVENT_NAMES
from tests.unit.support import SqliteTestHarness, published_event_bus_events


class ToolSourceServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = SqliteTestHarness()
        self.container = self.harness.build_runtime_container(
            target=AssemblyTarget.TEST,
        )
        self.command_service = self.container.require(
            AppKey.TOOL_SOURCE_COMMAND_SERVICE,
        )
        self.query_service = self.container.require(AppKey.TOOL_SOURCE_QUERY_SERVICE)
        self.uow_factory = self.container.require(AppKey.UNIT_OF_WORK_FACTORY)

    def tearDown(self) -> None:
        self.harness.close()

    def test_sync_bundled_local_package_reconciles_source_and_functions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_demo_tool_package(root)

            plans = discover_tool_package_plans(root)
            sources = tool_source_records_from_package_plans(plans)
            discovery = ToolDiscoveryService(
                ToolDiscoveryAdapterRegistry(
                    {
                        ToolSourceCatalogKind.LOCAL_PACKAGE: (
                            ToolPackageDiscoveryAdapter(plans)
                        ),
                    },
                ),
            )

            result = self.command_service.sync_sources(
                sources,
                discovery_service=discovery,
            )

        self.assertEqual(result.source_count, 1)
        self.assertEqual(result.function_count, 1)
        self.assertEqual(result.error_count, 0)
        self.assertEqual(result.changed_count, 1)
        event_names = _published_event_names(self.container)
        self.assertIn("tool.source.created", event_names)
        self.assertIn("tool.source.discovery_completed", event_names)
        self.assertIn("tool.function.created", event_names)

        source = self.query_service.get_source("bundled.local_package.demo")
        assert source is not None
        self.assertEqual(source.kind, ToolSourceCatalogKind.LOCAL_PACKAGE)
        self.assertEqual(source.status.value, "active")
        self.assertEqual(source.last_discovery_status.value, "completed")
        history = self.query_service.list_discovery_runs(source.source_id)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].status.value, "completed")
        self.assertEqual(history[0].function_count, 1)
        self.assertEqual(history[0].provider_backend_count, 0)
        self.assertEqual(history[0].source_revision, source.revision)
        self.assertEqual(history[0].config_hash, source.config_hash)

        with self.uow_factory() as uow:
            functions = uow.tool_functions.list(
                source_id="bundled.local_package.demo",
                status=ToolFunctionStatus.ACTIVE,
            )
            self.assertEqual(len(functions), 1)
            function = functions[0]
            self.assertEqual(function.function_id, "demo_echo")
            self.assertEqual(function.stable_key, "local_package.demo.demo_echo")
            self.assertEqual(function.handler_ref["ref"], "demo_echo")
            self.assertEqual(function.capability_ids, ("bounded_network.http",))

    def test_query_service_lists_runtime_request_bundles_by_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_demo_tool_package(root)

            plans = discover_tool_package_plans(root)
            sources = tool_source_records_from_package_plans(plans)
            discovery = ToolDiscoveryService(
                ToolDiscoveryAdapterRegistry(
                    {
                        ToolSourceCatalogKind.LOCAL_PACKAGE: (
                            ToolPackageDiscoveryAdapter(plans)
                        ),
                    },
                ),
            )
            self.command_service.sync_sources(sources, discovery_service=discovery)

        bundles = self.query_service.list_runtime_request_bundles(
            ("missing", "demo_echo", "demo_echo"),
        )

        self.assertEqual(len(bundles), 1)
        bundle = bundles[0]
        self.assertEqual(bundle.source_id, "bundled.local_package.demo")
        self.assertEqual(bundle.source_kind, "local_package")
        self.assertEqual(bundle.title, "Demo Tools")
        self.assertEqual(bundle.summary, "Echo and inspect demo tool behavior.")
        self.assertEqual(bundle.function_ids, ("demo_echo",))
        self.assertEqual(bundle.function_count, 1)
        self.assertEqual(len(bundle.groups), 1)
        self.assertEqual(bundle.groups[0].group_key, "echo")
        self.assertEqual(bundle.groups[0].title, "Echo")
        self.assertEqual(bundle.groups[0].function_ids, ("demo_echo",))
        self.assertEqual(bundle.capability_ids, ("bounded_network.http",))
        self.assertEqual(bundle.metadata["source_id"], "bundled.local_package.demo")

        disabled = self.container.require(
            AppKey.TOOL_FUNCTION_COMMAND_SERVICE,
        ).set_function_enabled("demo_echo", enabled=False)
        self.assertTrue(disabled.changed)

        self.assertEqual(self.query_service.list_runtime_request_bundles(("demo_echo",)), ())

    def test_query_service_uses_openapi_source_runtime_request_metadata(self) -> None:
        source = ToolSourceCatalogRecord(
            source_id="configured.openapi.flight_search",
            kind=ToolSourceCatalogKind.OPENAPI,
            display_name="Configured OpenAPI",
            config={
                "source": "configured_tool_provider",
                "package_kind": "openapi",
                "runtime_request": {
                    "title": "Flight Search",
                    "summary": "Search routes, prices, and availability.",
                    "groups": {
                        "search": {
                            "title": "Search",
                            "summary": "Query flight inventory and prices.",
                            "function_ids": ["flight_search.query"],
                            "default_tool_schema_ids": ["flight_search.query"],
                            "default_tool_schema_max_count": 1,
                            "default_tool_schema_source": (
                                "configured.openapi.flight_search.runtime_request_group.search"
                            ),
                        },
                    },
                },
            },
        )
        discovery = ToolDiscoveryService(
            ToolDiscoveryAdapterRegistry(
                {ToolSourceCatalogKind.OPENAPI: _RuntimeRequestBundleDiscoveryAdapter()},
            ),
        )

        result = self.command_service.sync_source(source, discovery_service=discovery)

        self.assertIsNone(result.error_message)
        bundles = self.query_service.list_runtime_request_bundles(("flight_search.query",))
        self.assertEqual(len(bundles), 1)
        self.assertEqual(bundles[0].source_id, source.source_id)
        self.assertEqual(bundles[0].source_kind, "openapi")
        self.assertEqual(bundles[0].title, "Flight Search")
        self.assertEqual(bundles[0].summary, "Search routes, prices, and availability.")
        self.assertEqual(len(bundles[0].groups), 1)
        self.assertEqual(bundles[0].groups[0].group_key, "search")
        self.assertEqual(bundles[0].groups[0].title, "Search")
        self.assertEqual(bundles[0].groups[0].function_ids, ("flight_search.query",))
        self.assertFalse(bundles[0].groups[0].metadata.get("auto_source_group", False))
        self.assertEqual(
            bundles[0].groups[0].metadata["default_tool_schema_ids"],
            ["flight_search.query"],
        )
        self.assertEqual(bundles[0].groups[0].metadata["default_tool_schema_max_count"], 1)
        self.assertEqual(
            bundles[0].groups[0].metadata["default_tool_schema_source"],
            "configured.openapi.flight_search.runtime_request_group.search",
        )
        self.assertIn("Query flight inventory", bundles[0].groups[0].summary)

    def test_create_and_update_configured_source_do_not_discover(self) -> None:
        created = self.command_service.create_source(
            _configured_openapi_source(
                display_name="Sample OpenAPI",
                spec_location="https://example.test/openapi.json",
            ),
        )

        self.assertTrue(created.changed)
        self.assertEqual(created.source.source_id, "configured.openapi.sample")
        self.assertEqual(created.source.status.value, "active")
        self.assertIsNone(created.source.last_discovery_status)
        self.assertEqual(
            self.query_service.list_discovery_runs("configured.openapi.sample"),
            (),
        )

        updated = self.command_service.update_source(
            "configured.openapi.sample",
            _configured_openapi_source(
                display_name="Renamed OpenAPI",
                spec_location="https://example.test/renamed-openapi.json",
            ),
        )

        self.assertTrue(updated.changed)
        self.assertEqual(updated.source.display_name, "Renamed OpenAPI")
        self.assertEqual(
            updated.source.config["provider"]["spec_location"],
            "https://example.test/renamed-openapi.json",
        )
        self.assertEqual(
            self.query_service.list_discovery_runs("configured.openapi.sample"),
            (),
        )

    def test_create_source_accepts_configured_source_golden_shapes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            sources = (
                _configured_openapi_source(
                    display_name="Sample OpenAPI",
                    spec_location="https://example.test/openapi.json",
                ),
                _configured_mcp_source(),
                _configured_cli_source(root=Path(temp_dir)),
            )
            for source in sources:
                created = self.command_service.create_source(source)

                self.assertTrue(created.changed)
                self.assertEqual(created.source.source_id, source.source_id)
                self.assertEqual(created.source.kind, source.kind)
                self.assertEqual(created.source.status.value, "active")
                self.assertEqual(
                    self.query_service.list_discovery_runs(source.source_id),
                    (),
                )

    def test_create_source_rejects_bundled_and_unsupported_sources(self) -> None:
        with self.assertRaises(ToolValidationError):
            self.command_service.create_source(
                ToolSourceCatalogRecord(
                    source_id="bundled.local_package.demo",
                    kind=ToolSourceCatalogKind.LOCAL_PACKAGE,
                    display_name="Bundled Demo",
                    config={
                        "source": "bundled_tool_package",
                        "package_kind": "local_package",
                    },
                ),
            )

        with self.assertRaises(ToolValidationError):
            self.command_service.create_source(
                ToolSourceCatalogRecord(
                    source_id="configured.cli.demo",
                    kind=ToolSourceCatalogKind.CLI,
                    display_name="CLI Demo",
                    config={
                        "source": "configured_tool_provider",
                        "package_kind": "cli",
                        "provider": {"name": "demo"},
                    },
                ),
            )

    def test_create_source_rejects_invalid_configured_source_shapes(self) -> None:
        invalid_sources = (
            ToolSourceCatalogRecord(
                source_id="configured.openapi.mismatch",
                kind=ToolSourceCatalogKind.OPENAPI,
                display_name="Mismatched OpenAPI",
                config={
                    "source": "configured_tool_provider",
                    "package_kind": "cli",
                    "provider": {
                        "name": "sample",
                        "spec_location": "https://example.test/openapi.json",
                    },
                },
            ),
            ToolSourceCatalogRecord(
                source_id="configured.mcp.bad",
                kind=ToolSourceCatalogKind.MCP,
                display_name="Bad MCP",
                config={
                    "source": "configured_tool_provider",
                    "package_kind": "mcp",
                    "provider": {
                        "name": "bad-mcp",
                        "command": "python -m bad_mcp",
                    },
                },
            ),
            ToolSourceCatalogRecord(
                source_id="configured.cli.bad",
                kind=ToolSourceCatalogKind.CLI,
                display_name="Bad CLI",
                config={
                    "source": "configured_tool_provider",
                    "package_kind": "cli",
                    "provider": {
                        "name": "bad-cli",
                        "executable": sys.executable,
                    },
                },
            ),
        )

        for source in invalid_sources:
            with self.subTest(source_id=source.source_id):
                with self.assertRaises(ToolValidationError):
                    self.command_service.create_source(source)

    def test_cli_source_discovers_guided_functions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = _configured_cli_source(root=Path(temp_dir))

            created = self.command_service.create_source(source)
            self.assertEqual(created.source.kind, ToolSourceCatalogKind.CLI)

            result = self.command_service.sync_source(
                source,
                discovery_service=self.container.require(
                    AppKey.TOOL_SOURCE_DISCOVERY_SERVICE,
                ),
            )

        self.assertFalse(result.skipped)
        self.assertIsNone(result.error_message)
        self.assertIsNotNone(result.discovery)
        assert result.discovery is not None
        self.assertEqual(len(result.discovery.candidates), 4)

        functions = self.query_service.list_functions(source_id=source.source_id)
        actions = {str(function.metadata.get("cli_action")) for function in functions}
        self.assertEqual(
            actions,
            {"cli_help", "cli_execute", "cli_read_output", "cli_cancel"},
        )
        self.assertTrue(
            all(
                function.runtime_kind is ToolFunctionRuntimeKind.CLI
                for function in functions
            ),
        )

    def test_cli_source_does_not_autogenerate_functions_from_help(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = _configured_cli_source_with_suggestive_help(root=root)

            self.command_service.create_source(source)
            result = self.command_service.sync_source(
                source,
                discovery_service=self.container.require(
                    AppKey.TOOL_SOURCE_DISCOVERY_SERVICE,
                ),
            )
            self.assertFalse((root / "help_probe_executed").exists())

        self.assertFalse(result.skipped)
        self.assertIsNone(result.error_message)
        assert result.discovery is not None
        actions = {
            str(candidate.metadata.get("cli_action"))
            for candidate in result.discovery.candidates
        }
        self.assertEqual(
            actions,
            {"cli_help", "cli_execute", "cli_read_output", "cli_cancel"},
        )
        generated_names = {
            candidate.name for candidate in result.discovery.candidates
        }
        self.assertNotIn("Extract Media", generated_names)
        self.assertEqual(len(result.discovery.candidates), 4)

    def test_cli_source_guided_execute_persists_process_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = _configured_cli_source(root=Path(temp_dir))
            self.command_service.create_source(source)
            self.command_service.sync_source(
                source,
                discovery_service=self.container.require(
                    AppKey.TOOL_SOURCE_DISCOVERY_SERVICE,
                ),
            )

            runtime_container = self.harness.build_runtime_container(
                target=AssemblyTarget.TEST,
            )
            activator = runtime_container.require(
                AppKey.TOOL_CONFIGURED_RUNTIME_ACTIVATOR,
            )
            activator.activate_source(source.source_id)
            activator.activate_source(source.source_id)
            tool_service = runtime_container.require(AppKey.TOOL_SERVICE)
            functions = runtime_container.require(
                AppKey.TOOL_SOURCE_QUERY_SERVICE,
            ).list_functions(source_id=source.source_id)
            function_ids = {
                str(function.metadata.get("cli_action")): function.function_id
                for function in functions
            }

            execute_run = asyncio.run(
                tool_service.execute(
                    ExecuteToolInput(
                        tool_id=function_ids["cli_execute"],
                        arguments={
                            "subcommand": "-c",
                            "args": ["print('cli source ok')"],
                        },
                        environment=ToolEnvironment.REMOTE,
                    ),
                ),
            )

            self.assertEqual(execute_run.status.value, "succeeded")
            output_payload = execute_run.output_payload
            self.assertIsInstance(output_payload, dict)
            process_id = str(output_payload["process_id"])  # type: ignore[index]
            self.assertIn("runtime_facts", output_payload)
            self.assertEqual(
                Path(output_payload["runtime_facts"]["working_directory"]).resolve(),
                Path(temp_dir).resolve(),
            )
            self.assertIn("continuation", output_payload)
            self.assertEqual(
                output_payload["continuation"]["next_read_arguments"]["process_id"],
                process_id,
            )
            self.assertIsNotNone(execute_run.result_envelope_payload)
            assert execute_run.result_envelope_payload is not None
            self.assertEqual(
                execute_run.result_envelope_payload["read_handles"][0]["process_id"],
                process_id,
            )
            self.assertEqual(
                Path(
                    execute_run.result_envelope_payload["provider_replay_payload"][
                        "runtime_facts"
                    ]["working_directory"],
                ).resolve(),
                Path(temp_dir).resolve(),
            )
            self._wait_for_process_stdout(
                runtime_container.require(AppKey.PROCESS_SERVICE),
                process_id,
                "cli source ok",
            )
            self._wait_for_cli_output_event(
                runtime_container.require(AppKey.EVENTS_SERVICE),
                process_id,
                "cli source ok",
            )

            read_run = asyncio.run(
                tool_service.execute(
                    ExecuteToolInput(
                        tool_id=function_ids["cli_read_output"],
                        arguments={"process_id": process_id},
                        environment=ToolEnvironment.REMOTE,
                    ),
                ),
            )

        self.assertEqual(read_run.status.value, "succeeded")
        self.assertIsInstance(read_run.output_payload, dict)
        self.assertIn("cli source ok", read_run.output_payload["stdout"])
        self.assertIsNotNone(read_run.result_envelope_payload)
        assert read_run.result_envelope_payload is not None
        self.assertEqual(read_run.result_envelope_payload["status"], "ok")
        self.assertEqual(
            read_run.result_envelope_payload["read_handles"][0]["arguments"][
                "process_id"
            ],
            process_id,
        )

    def test_cli_source_failed_process_result_guides_next_reasoning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = _configured_cli_source(root=Path(temp_dir))
            self.command_service.create_source(source)
            self.command_service.sync_source(
                source,
                discovery_service=self.container.require(
                    AppKey.TOOL_SOURCE_DISCOVERY_SERVICE,
                ),
            )

            runtime_container = self.harness.build_runtime_container(
                target=AssemblyTarget.TEST,
            )
            activator = runtime_container.require(
                AppKey.TOOL_CONFIGURED_RUNTIME_ACTIVATOR,
            )
            activator.activate_source(source.source_id)
            tool_service = runtime_container.require(AppKey.TOOL_SERVICE)
            functions = runtime_container.require(
                AppKey.TOOL_SOURCE_QUERY_SERVICE,
            ).list_functions(source_id=source.source_id)
            function_ids = {
                str(function.metadata.get("cli_action")): function.function_id
                for function in functions
            }

            execute_run = asyncio.run(
                tool_service.execute(
                    ExecuteToolInput(
                        tool_id=function_ids["cli_execute"],
                        arguments={
                            "subcommand": "-c",
                            "args": [
                                "import sys; print('bad path', file=sys.stderr); sys.exit(7)",
                            ],
                        },
                        environment=ToolEnvironment.REMOTE,
                    ),
                ),
            )

            self.assertEqual(execute_run.status.value, "succeeded")
            self.assertIsInstance(execute_run.output_payload, dict)
            process_id = str(execute_run.output_payload["process_id"])
            self._wait_for_process_stderr(
                runtime_container.require(AppKey.PROCESS_SERVICE),
                process_id,
                "bad path",
            )

            read_run = asyncio.run(
                tool_service.execute(
                    ExecuteToolInput(
                        tool_id=function_ids["cli_read_output"],
                        arguments={"process_id": process_id},
                        environment=ToolEnvironment.REMOTE,
                    ),
                ),
            )

        self.assertEqual(read_run.status.value, "succeeded")
        self.assertIsInstance(read_run.output_payload, dict)
        self.assertEqual(read_run.output_payload["exit_code"], 7)
        self.assertIn("bad path", read_run.output_payload["stderr"])
        self.assertIsNotNone(read_run.result_envelope_payload)
        assert read_run.result_envelope_payload is not None
        self.assertEqual(read_run.result_envelope_payload["status"], "error")
        self.assertEqual(
            read_run.result_envelope_payload["key_facts"]["exit_code"],
            7,
        )
        self.assertIn(
            "bad path",
            read_run.result_envelope_payload["provider_replay_payload"]["stderr"],
        )

    def test_cli_source_guided_execute_injects_access_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = _configured_cli_source_with_credentials(root=Path(temp_dir))
            self.command_service.create_source(source)
            self.command_service.sync_source(
                source,
                discovery_service=self.container.require(
                    AppKey.TOOL_SOURCE_DISCOVERY_SERVICE,
                ),
            )
            functions = self.query_service.list_functions(source_id=source.source_id)
            function_ids = {
                str(function.metadata.get("cli_action")): function.function_id
                for function in functions
            }
            execute_function = self.query_service.get_function(
                function_ids["cli_execute"],
            )
            assert execute_function is not None
            requirements = execute_function.requirements.credential_requirements
            self.assertEqual(len(requirements), 1)
            self.assertEqual(len(requirements[0].requirements), 2)

            registry = ToolRuntimeRegistry()
            credential_provider = _FakeCredentialProvider(
                {
                    "cli-env-token": "env-secret",
                    "cli-file-token": "file-secret",
                },
            )
            register_cli_guided_handlers(
                registry,
                source=source,
                functions=functions,
                process_service=self.container.require(AppKey.PROCESS_SERVICE),
                credential_provider=credential_provider,
                events_service=self.container.require(AppKey.EVENTS_SERVICE),
            )
            handler = registry.get_handler(
                next(
                    function.handler_ref
                    for function in functions
                    if function.function_id == function_ids["cli_execute"]
                ),
            )
            assert handler is not None

            result = asyncio.run(
                handler(
                    {
                        "subcommand": "-c",
                        "args": [
                            "import os, pathlib; "
                            "print(os.environ['CLI_TOKEN']); "
                            "print(pathlib.Path(os.environ['CLI_TOKEN_FILE']).read_text())"
                        ],
                    },
                ),
            )

            self.assertIsInstance(result.details, dict)
            process_id = str(result.details["process_id"])
            self._wait_for_process_stdout(
                self.container.require(AppKey.PROCESS_SERVICE),
                process_id,
                "env-secret\nfile-secret",
            )
            self._wait_for_cli_output_event(
                self.container.require(AppKey.EVENTS_SERVICE),
                process_id,
                "[credential:redacted]",
            )
            cli_output_topic = named_event_topic(TOOL_CLI_EVENT_NAMES[0])
            cli_output_events = self.container.require(
                AppKey.EVENTS_SERVICE,
            ).read_recent_event_topic(cli_output_topic, limit=20)
            cli_output_text = "\n".join(
                str(record.envelope.payload.get("text") or "")
                for record in cli_output_events
                if record.envelope.payload.get("process_id") == process_id
            )
            self.assertNotIn("env-secret", cli_output_text)
            self.assertNotIn("file-secret", cli_output_text)
            read_handler = registry.get_handler(
                next(
                    function.handler_ref
                    for function in functions
                    if function.function_id == function_ids["cli_read_output"]
                ),
            )
            assert read_handler is not None
            read_result = asyncio.run(read_handler({"process_id": process_id}))
            self.assertIsInstance(read_result.details, dict)
            self.assertIn("[credential:redacted]", read_result.details["stdout"])
            self.assertNotIn("env-secret", read_result.details["stdout"])
            self.assertNotIn("file-secret", read_result.details["stdout"])
            envelope = read_result.metadata.get("tool_result_envelope")
            self.assertIsInstance(envelope, dict)
            provider_replay = envelope["provider_replay_payload"]
            self.assertIn("[credential:redacted]", provider_replay["stdout"])
            self.assertNotIn("env-secret", provider_replay["stdout"])
            self.assertNotIn("file-secret", provider_replay["stdout"])
            metadata_text = str(result.details.get("credential_injections"))
            self.assertIn("cli-env-token", metadata_text)
            self.assertIn("CLI_TOKEN_FILE", metadata_text)
            self.assertNotIn("env-secret", metadata_text)
            self.assertNotIn("file-secret", metadata_text)
            self.assertEqual(
                [call.binding_id for call in credential_provider.calls],
                ["cli-env-token", "cli-file-token"],
            )

    def test_cli_source_rejects_direct_credential_binding_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = _configured_cli_source_with_credentials(root=Path(temp_dir))
            provider = dict(source.config["provider"])
            credential_bindings = [dict(provider["credential_bindings"][0])]
            credential_bindings[0]["binding_id"] = "env:CLI_TOKEN"
            provider["credential_bindings"] = credential_bindings
            source = ToolSourceCatalogRecord(
                source_id=source.source_id,
                kind=source.kind,
                display_name=source.display_name,
                description=source.description,
                config={**source.config, "provider": provider},
                runtime_requirements=source.runtime_requirements,
            )

            with self.assertRaisesRegex(ToolValidationError, "direct credential source"):
                discover_cli_source(source)

    def test_cli_source_promoted_function_uses_source_runtime_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = _configured_ffmpeg_cli_source(root=root)
            media_file = root / "sample.mp4"
            media_file.write_text("fake media", encoding="utf-8")

            self.command_service.create_source(source)
            result = self.command_service.sync_source(
                source,
                discovery_service=self.container.require(
                    AppKey.TOOL_SOURCE_DISCOVERY_SERVICE,
                ),
            )
            assert result.discovery is not None
            self.assertEqual(len(result.discovery.candidates), 5)

            functions = self.query_service.list_functions(source_id=source.source_id)
            promoted = next(
                function
                for function in functions
                if function.metadata.get("promoted_function_id") == "probe"
            )
            self.assertEqual(
                promoted.metadata.get("cli_action"),
                "cli_promoted_execute",
            )
            self.assertEqual(promoted.requirements.runtime_requirement_sets, (("cli:configured.cli.ffmpeg",),))
            self.assertEqual(
                promoted.input_schema["properties"]["input_path"]["type"],
                "string",
            )

            runtime_container = self.harness.build_runtime_container(
                target=AssemblyTarget.TEST,
            )
            runtime_container.require(AppKey.TOOL_CONFIGURED_RUNTIME_ACTIVATOR).activate_source(
                source.source_id,
            )
            tool_service = runtime_container.require(AppKey.TOOL_SERVICE)
            function_ids = {
                str(function.metadata.get("cli_action")): function.function_id
                for function in functions
                if function.metadata.get("cli_action") != "cli_promoted_execute"
            }
            help_run = asyncio.run(
                tool_service.execute(
                    ExecuteToolInput(
                        tool_id=function_ids["cli_help"],
                        arguments={},
                        environment=ToolEnvironment.REMOTE,
                    ),
                ),
            )
            self.assertEqual(help_run.status.value, "succeeded")
            self.assertIsInstance(help_run.output_payload, dict)
            self.assertIn("fake ffmpeg help", help_run.output_payload["stdout"])

            execute_run = asyncio.run(
                tool_service.execute(
                    ExecuteToolInput(
                        tool_id=function_ids["cli_execute"],
                        arguments={
                            "subcommand": "-i",
                            "args": [str(media_file), "-f", "null", "-"],
                        },
                        environment=ToolEnvironment.REMOTE,
                    ),
                ),
            )
            self.assertEqual(execute_run.status.value, "succeeded")
            self.assertIsInstance(execute_run.output_payload, dict)
            self._wait_for_process_stdout(
                runtime_container.require(AppKey.PROCESS_SERVICE),
                str(execute_run.output_payload["process_id"]),
                "Duration: 00:00:01.00",
            )

            run = asyncio.run(
                tool_service.execute(
                    ExecuteToolInput(
                        tool_id=promoted.function_id,
                        arguments={"input_path": str(media_file)},
                        environment=ToolEnvironment.REMOTE,
                    ),
                ),
            )

            self.assertEqual(run.status.value, "succeeded")
            self.assertIsInstance(run.output_payload, dict)
            process_id = str(run.output_payload["process_id"])
            self.assertEqual(run.output_payload["promoted_function_id"], "probe")
            self.assertIn("-i", run.output_payload["argv"])
            self.assertIn(str(media_file), run.output_payload["argv"])
            self._wait_for_process_stdout(
                runtime_container.require(AppKey.PROCESS_SERVICE),
                process_id,
                "Duration: 00:00:01.00",
            )
            self._wait_for_cli_output_event(
                runtime_container.require(AppKey.EVENTS_SERVICE),
                process_id,
                "Duration: 00:00:01.00",
            )

    def test_cli_promoted_function_initial_output_limit_controls_first_read(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = ToolSourceCatalogRecord(
                source_id="configured.cli.promoted.limit",
                kind=ToolSourceCatalogKind.CLI,
                display_name="Promoted CLI",
                description="Promoted CLI output limit test.",
                config={
                    "source": "configured_tool_provider",
                    "package_kind": "cli",
                    "provider": {
                        "name": "promoted",
                        "executable": sys.executable,
                        "allowed_subcommands": ["run"],
                        "working_directory": str(root),
                        "allowed_roots": [str(root)],
                        "output_limit_bytes": 1000,
                        "promoted_functions": [
                            {
                                "id": "probe",
                                "name": "Probe",
                                "description": "Probe.",
                                "subcommand": "run",
                                "args": [],
                                "initial_output_limit": 17,
                            },
                        ],
                    },
                },
            )
            config = CliToolSourceConfig.from_source(source)
            promoted = config.promoted_function("probe")
            assert promoted is not None
            process_service = _RecordingProcessService(root)
            runtime = CliGuidedRuntime(config, process_service=process_service)

            run = asyncio.run(runtime.cli_promoted_execute(promoted, {}))

            self.assertIsInstance(run.details, dict)
            self.assertEqual(process_service.read_limits, [17])

    def _wait_for_cli_output_event(
        self,
        events_service,
        process_id: str,
        expected: str,
    ) -> None:
        topic = named_event_topic(TOOL_CLI_EVENT_NAMES[0])
        for _ in range(50):
            records = events_service.read_recent_event_topic(topic, limit=20)
            for record in records:
                payload = record.envelope.payload
                if (
                    payload.get("process_id") == process_id
                    and payload.get("stream") == "stdout"
                    and expected in str(payload.get("text") or "")
                ):
                    return
            time.sleep(0.02)
        self.fail(f"Process {process_id} did not publish expected CLI output event.")

    def _wait_for_process_stdout(
        self,
        process_service,
        process_id: str,
        expected: str,
    ) -> None:
        for _ in range(50):
            output = process_service.read_output(process_id=process_id)
            if expected in output.stdout:
                return
            time.sleep(0.02)
        self.fail(f"Process {process_id} did not produce expected output.")

    def _wait_for_process_stderr(
        self,
        process_service,
        process_id: str,
        expected: str,
    ) -> None:
        for _ in range(50):
            output = process_service.read_output(process_id=process_id)
            if expected in output.stderr:
                return
            time.sleep(0.02)
        self.fail(f"Process {process_id} did not produce expected stderr.")

    def test_disabled_source_is_not_rediscovered(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_demo_tool_package(root)

            plans = discover_tool_package_plans(root)
            sources = tool_source_records_from_package_plans(plans)
            discovery = ToolDiscoveryService(
                ToolDiscoveryAdapterRegistry(
                    {
                        ToolSourceCatalogKind.LOCAL_PACKAGE: (
                            ToolPackageDiscoveryAdapter(plans)
                        ),
                    },
                ),
            )
            self.command_service.sync_sources(sources, discovery_service=discovery)
            self.command_service.disable_source("bundled.local_package.demo")

            result = self.command_service.sync_sources(
                sources,
                discovery_service=discovery,
            )

        self.assertTrue(result.results[0].skipped)
        self.assertIn("tool.source.disabled", _published_event_names(self.container))
        with self.uow_factory() as uow:
            source = uow.tool_sources.get("bundled.local_package.demo")
            assert source is not None
            self.assertEqual(source.status, ToolSourceStatus.DISABLED)
        history = self.query_service.list_discovery_runs("bundled.local_package.demo")
        self.assertEqual(len(history), 1)

    def test_disabled_function_stays_disabled_after_source_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_demo_tool_package(root)

            plans = discover_tool_package_plans(root)
            sources = tool_source_records_from_package_plans(plans)
            discovery = ToolDiscoveryService(
                ToolDiscoveryAdapterRegistry(
                    {
                        ToolSourceCatalogKind.LOCAL_PACKAGE: (
                            ToolPackageDiscoveryAdapter(plans)
                        ),
                    },
                ),
            )
            self.command_service.sync_sources(sources, discovery_service=discovery)

            function_result = self.container.require(
                AppKey.TOOL_FUNCTION_COMMAND_SERVICE,
            ).set_function_enabled("demo_echo", enabled=False)
            self.assertTrue(function_result.changed)
            self.assertFalse(function_result.function.enabled)
            self.assertIn(
                "tool.function.disabled",
                _published_event_names(self.container),
            )

            self.command_service.sync_sources(sources, discovery_service=discovery)

        function = self.query_service.get_function("demo_echo")
        assert function is not None
        self.assertEqual(function.status, ToolFunctionStatus.ACTIVE)
        self.assertFalse(function.enabled)

    def test_function_policy_update_is_preserved_after_source_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_demo_tool_package(root)

            plans = discover_tool_package_plans(root)
            sources = tool_source_records_from_package_plans(plans)
            discovery = ToolDiscoveryService(
                ToolDiscoveryAdapterRegistry(
                    {
                        ToolSourceCatalogKind.LOCAL_PACKAGE: (
                            ToolPackageDiscoveryAdapter(plans)
                        ),
                    },
                ),
            )
            self.command_service.sync_sources(sources, discovery_service=discovery)

            function_result = self.container.require(
                AppKey.TOOL_FUNCTION_COMMAND_SERVICE,
            ).update_function_policy(
                "demo_echo",
                trust_policy={"level": "trusted"},
                approval_policy={"requires_approval": False},
                credential_binding_overrides={"api_key": "demo-binding"},
                required_effect_overrides=("demo.effect",),
            )
            self.assertTrue(function_result.changed)
            self.assertEqual(function_result.function.trust_policy["level"], "trusted")
            self.assertIn(
                "tool.function.policy_updated",
                _published_event_names(self.container),
            )

            self.command_service.sync_sources(sources, discovery_service=discovery)

        function = self.query_service.get_function("demo_echo")
        assert function is not None
        self.assertEqual(function.trust_policy, {"level": "trusted"})
        self.assertEqual(function.approval_policy, {"requires_approval": False})
        self.assertEqual(
            function.credential_binding_overrides,
            {"api_key": "demo-binding"},
        )
        self.assertEqual(function.required_effect_overrides, ("demo.effect",))

    def test_query_service_preserves_function_credential_requirements(self) -> None:
        source = ToolSourceCatalogRecord(
            source_id="unit.credential.source",
            kind=ToolSourceCatalogKind.LOCAL_PACKAGE,
            display_name="Credential Source",
        )
        discovery = ToolDiscoveryService(
            ToolDiscoveryAdapterRegistry(
                {
                    ToolSourceCatalogKind.LOCAL_PACKAGE: (
                        _CredentialRequirementDiscoveryAdapter()
                    ),
                },
            ),
        )

        result = self.command_service.sync_source(
            source,
            discovery_service=discovery,
        )

        self.assertIsNone(result.error_message)
        function = self.query_service.get_function("credential_tool")
        assert function is not None
        requirements = function.requirements.credential_requirements
        self.assertEqual(len(requirements), 1)
        requirement = requirements[0].requirements[0]
        self.assertEqual(requirement.slot.slot, "api_key")
        self.assertEqual(requirement.slot.expected_kind, AccessCredentialKind.API_KEY)
        self.assertEqual(requirement.provider, "openai")

    def test_sync_package_provider_backends_persists_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_backend_tool_package(root)

            plans = discover_tool_package_plans(root)
            sources = tool_source_records_from_package_plans(plans)
            discovery = ToolDiscoveryService(
                ToolDiscoveryAdapterRegistry(
                    {
                        ToolSourceCatalogKind.LOCAL_PACKAGE: (
                            ToolPackageDiscoveryAdapter(plans)
                        ),
                    },
                ),
            )
            result = self.command_service.sync_sources(
                sources,
                discovery_service=discovery,
            )

        self.assertEqual(result.source_count, 1)
        self.assertEqual(result.function_count, 1)
        assert result.results[0].discovery is not None
        self.assertEqual(
            result.results[0].discovery.provider_backend_candidates[0].backend_id,
            "image_demo.openai",
        )
        history = self.query_service.list_discovery_runs("bundled.local_package.image_demo")
        self.assertEqual(history[0].provider_backend_count, 1)
        with self.uow_factory() as uow:
            backends = uow.tool_provider_backends.list(
                source_id="bundled.local_package.image_demo",
            )
        self.assertEqual(len(backends), 1)
        backend = backends[0]
        self.assertEqual(backend.backend_id, "image_demo.openai")
        self.assertEqual(backend.capability.value, "image_generation")
        self.assertEqual(backend.runtime_ref["ref"], "image_demo_generate")
        self.assertEqual(len(backend.credential_requirements), 1)

    def test_failed_source_discovery_is_recorded_in_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_demo_tool_package(root)

            plans = discover_tool_package_plans(root)
            sources = tool_source_records_from_package_plans(plans)
            discovery = ToolDiscoveryService(
                ToolDiscoveryAdapterRegistry(
                    {
                        ToolSourceCatalogKind.LOCAL_PACKAGE: _FailingDiscoveryAdapter(),
                    },
                ),
            )
            result = self.command_service.sync_sources(
                sources,
                discovery_service=discovery,
            )

        self.assertEqual(result.error_count, 1)
        source = self.query_service.get_source("bundled.local_package.demo")
        assert source is not None
        self.assertEqual(source.status.value, "error")
        self.assertEqual(source.last_discovery_status.value, "failed")
        self.assertIn("tool.source.discovery_failed", _published_event_names(self.container))
        history = self.query_service.list_discovery_runs(source.source_id)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].status.value, "failed")
        self.assertEqual(history[0].function_count, 0)
        self.assertIn("boom", history[0].error_message or "")


def _published_event_names(container: object) -> tuple[str, ...]:
    return tuple(
        event.name
        for event in published_event_bus_events(container)
        if isinstance(getattr(event, "name", None), str) and event.name
    )


class _FailingDiscoveryAdapter(ToolDiscoveryAdapter):
    def discover(self, source):  # noqa: ANN001, ANN201
        return ToolSourceDiscoveryResult.failed(
            source_id=source.source_id,
            error_message="boom during discovery",
            metadata={"source": "unit_test"},
        )


class _CredentialRequirementDiscoveryAdapter(ToolDiscoveryAdapter):
    def discover(self, source):  # noqa: ANN001, ANN201
        consumer = AccessConsumerRef(
            consumer_id="credential_tool",
            module="tool",
            component="unit_test",
        )
        return ToolSourceDiscoveryResult.completed(
            source_id=source.source_id,
            candidates=(
                ToolFunctionCandidate(
                    stable_key="unit.credential_tool",
                    source_id=source.source_id,
                    function_id="credential_tool",
                    name="Credential Tool",
                    description="Requires a Tool-owned API key declaration.",
                    input_schema={"type": "object", "properties": {}},
                    runtime_kind=ToolFunctionRuntimeKind.LOCAL,
                    handler_ref="credential_tool",
                    requirements=ToolFunctionRequirements(
                        credential_requirements=(
                            AccessCredentialRequirementSet(
                                requirement_set_id="credential_tool.default",
                                consumer=consumer,
                                requirements=(
                                    AccessCredentialRequirementDeclaration(
                                        requirement_id="credential_tool.api_key",
                                        consumer=consumer,
                                        slot=AccessCredentialSlotRef(
                                            slot="api_key",
                                            expected_kind=AccessCredentialKind.API_KEY,
                                        ),
                                        provider="openai",
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )


class _RuntimeRequestBundleDiscoveryAdapter(ToolDiscoveryAdapter):
    def discover(self, source):  # noqa: ANN001, ANN201
        return ToolSourceDiscoveryResult.completed(
            source_id=source.source_id,
            candidates=(
                ToolFunctionCandidate(
                    stable_key="openapi.flight_search.query",
                    source_id=source.source_id,
                    function_id="flight_search.query",
                    name="Query Flights",
                    description="Query flight route availability.",
                    input_schema={"type": "object", "properties": {}},
                    runtime_kind=ToolFunctionRuntimeKind.OPENAPI,
                    handler_ref="openapi.flight_search.query",
                    capabilities=("bounded_network.http",),
                ),
            ),
        )


def _write_demo_tool_package(root: Path) -> None:
    package_dir = root / "demo"
    package_dir.mkdir()
    (package_dir / "tool.yaml").write_text(
        """
kind: local_package
namespace: demo
runtime_request:
  title: Demo Tools
  summary: Echo and inspect demo tool behavior.
  groups:
    echo:
      order: 10
      title: Echo
      summary: Echo utilities.
      function_ids:
        - demo_echo
capabilities:
  - bounded_network.http
dependencies:
  - id: demo_service
    kind: service_dependency
    description: Demo application service.
local_tools:
  - id: demo_echo
    name: Demo Echo
    description: Echo input for catalog sync tests.
    provider_name: local_system
    entrypoint: tools.demo.local:echo
    tool_kind: function
    parameters:
      - name: message
        data_type: string
        description: Message to echo.
        required: true
    tags:
      - demo
    required_effect_ids:
      - local_tool_access
    supported_modes:
      - inline
    supported_strategies:
      - async
    supported_environments:
      - local
    runtime_key: demo_echo
""".lstrip(),
        encoding="utf-8",
    )


def _write_backend_tool_package(root: Path) -> None:
    package_dir = root / "image_demo"
    package_dir.mkdir()
    (package_dir / "tool.yaml").write_text(
        """
kind: local_package
namespace: image_demo
provider_backends:
  - id: image_demo.openai
    capability: image_generation
    display_name: Image Demo OpenAI
    runtime_kind: local
    runtime_ref: image_demo_generate
    priority: 10
    credential_requirements:
      - requirement_set_id: image_demo.backend.credentials
        requirements:
          - requirement_id: image_demo.backend.openai_api_key
            slot: openai_api_key
            expected_kind: api_key
            binding_id: openai-api-key
            provider: openai
            transport: runtime_context
local_tools:
  - id: image_demo_generate
    name: Image Demo Generate
    description: Generate an image through a provider backend test function.
    provider_name: local_system
    entrypoint: tools.image_demo.local:generate
    tool_kind: function
    parameters:
      - name: runtime_request
        data_type: string
        description: Prompt.
        required: true
    supported_modes:
      - background
    supported_strategies:
      - async
    supported_environments:
      - local
    runtime_key: image_demo_generate
""".lstrip(),
        encoding="utf-8",
    )


def _configured_openapi_source(
    *,
    display_name: str,
    spec_location: str,
) -> ToolSourceCatalogRecord:
    return ToolSourceCatalogRecord(
        source_id="configured.openapi.sample",
        kind=ToolSourceCatalogKind.OPENAPI,
        display_name=display_name,
        config={
            "source": "configured_tool_provider",
            "package_kind": "openapi",
            "provider": {
                "name": "sample",
                "spec_location": spec_location,
            },
        },
    )


def _configured_cli_source(*, root: Path) -> ToolSourceCatalogRecord:
    return ToolSourceCatalogRecord(
        source_id="configured.cli.python",
        kind=ToolSourceCatalogKind.CLI,
        display_name="Python CLI",
        description="Governed Python CLI source for unit tests.",
        config={
            "source": "configured_tool_provider",
            "package_kind": "cli",
            "provider": {
                "name": "python",
                "executable": sys.executable,
                "allowed_subcommands": ["-c"],
                "denied_flags": ["--unsafe"],
                "working_directory": str(root),
                "allowed_roots": [str(root)],
                "timeout_seconds": 5,
                "output_limit_bytes": 8000,
            },
        },
        runtime_requirements=("cli:configured.cli.python",),
    )


def _configured_mcp_source() -> ToolSourceCatalogRecord:
    return ToolSourceCatalogRecord(
        source_id="configured.mcp.sample",
        kind=ToolSourceCatalogKind.MCP,
        display_name="Sample MCP",
        description="Governed MCP source for unit tests.",
        config={
            "source": "configured_tool_provider",
            "package_kind": "mcp",
            "provider": {
                "name": "sample-mcp",
                "command": [sys.executable, "-m", "sample_mcp_server"],
            },
        },
        runtime_requirements=("mcp:configured.mcp.sample",),
    )


def _configured_cli_source_with_credentials(*, root: Path) -> ToolSourceCatalogRecord:
    return ToolSourceCatalogRecord(
        source_id="configured.cli.python.credentials",
        kind=ToolSourceCatalogKind.CLI,
        display_name="Python CLI Credentials",
        description="Governed Python CLI source with credential injection.",
        config={
            "source": "configured_tool_provider",
            "package_kind": "cli",
            "provider": {
                "name": "python",
                "executable": sys.executable,
                "allowed_subcommands": ["-c"],
                "working_directory": str(root),
                "allowed_roots": [str(root)],
                "credential_bindings": [
                    {
                        "binding_id": "cli-env-token",
                        "injection": "env",
                        "env_name": "CLI_TOKEN",
                        "expected_kind": "api_key",
                        "provider": "demo",
                        "slot": "env_token",
                    },
                    {
                        "binding_id": "cli-file-token",
                        "injection": "file",
                        "file_env_name": "CLI_TOKEN_FILE",
                        "file_name": "token.txt",
                        "expected_kind": "api_key",
                        "provider": "demo",
                        "slot": "file_token",
                    },
                ],
            },
        },
        runtime_requirements=("cli:configured.cli.python.credentials",),
    )


def _configured_cli_source_with_suggestive_help(*, root: Path) -> ToolSourceCatalogRecord:
    help_script = root / "suggestive_cli.py"
    help_script.write_text(
        "\n".join(
            [
                "import pathlib, sys",
                "if '--help' in sys.argv:",
                "    pathlib.Path(sys.argv[0]).with_name('help_probe_executed').write_text('called')",
                "    print('extract-media  Extract Media  --input <path> --output <path>')",
                "    raise SystemExit(0)",
                "print('ok')",
            ],
        ),
        encoding="utf-8",
    )
    return ToolSourceCatalogRecord(
        source_id="configured.cli.suggestive",
        kind=ToolSourceCatalogKind.CLI,
        display_name="Suggestive CLI",
        description="CLI source whose help output should not become ToolFunctions.",
        config={
            "source": "configured_tool_provider",
            "package_kind": "cli",
            "provider": {
                "name": "suggestive-cli",
                "executable": sys.executable,
                "base_args": [str(help_script)],
                "allowed_subcommands": ["--help", "extract-media"],
                "working_directory": str(root),
                "allowed_roots": [str(root)],
                "timeout_seconds": 5,
                "output_limit_bytes": 8000,
            },
        },
        runtime_requirements=("cli:configured.cli.suggestive",),
    )


def _configured_ffmpeg_cli_source(*, root: Path) -> ToolSourceCatalogRecord:
    fake_ffmpeg = root / "fake_ffmpeg.py"
    fake_ffmpeg.write_text(
        "\n".join(
            [
                "import sys",
                "args = sys.argv[1:]",
                "if '--help' in args or '-h' in args:",
                "    print('fake ffmpeg help')",
                "    raise SystemExit(0)",
                "if args[:1] == ['-i'] and len(args) >= 2:",
                "    print(f\"Input #0, fake, from '{args[1]}'\")",
                "    print('Duration: 00:00:01.00')",
                "    raise SystemExit(0)",
                "print('unexpected argv: ' + ' '.join(args), file=sys.stderr)",
                "raise SystemExit(2)",
            ],
        ),
        encoding="utf-8",
    )
    return ToolSourceCatalogRecord(
        source_id="configured.cli.ffmpeg",
        kind=ToolSourceCatalogKind.CLI,
        display_name="FFmpeg CLI",
        description="Governed FFmpeg CLI source for promoted function tests.",
        config={
            "source": "configured_tool_provider",
            "package_kind": "cli",
            "provider": {
                "name": "ffmpeg",
                "executable": sys.executable,
                "base_args": [str(fake_ffmpeg)],
                "allowed_subcommands": ["-h", "-i"],
                "working_directory": str(root),
                "allowed_roots": [str(root)],
                "timeout_seconds": 5,
                "output_limit_bytes": 8000,
                "promoted_functions": [
                    {
                        "id": "probe",
                        "name": "FFmpeg Probe",
                        "description": "Probe a media file through the governed FFmpeg source.",
                        "subcommand": "-i",
                        "args": ["{input_path}", "-f", "null", "-"],
                        "parameters": [
                            {
                                "name": "input_path",
                                "data_type": "string",
                                "description": "Media file path inside allowed roots.",
                            },
                        ],
                    },
                ],
            },
        },
        runtime_requirements=("cli:configured.cli.ffmpeg",),
    )


class _RecordingProcessService:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.read_limits: list[int | None] = []
        self.session = ProcessSession(
            id="process-promoted-limit",
            command="run",
            shell="/bin/zsh",
            working_directory=str(root),
            session_key=None,
        )

    def start_command(
        self,
        *,
        command: str,
        shell: str,
        working_directory: str,
        session_key: str | None = None,
        env: dict[str, str] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ProcessSession:
        self.session = ProcessSession(
            id="process-promoted-limit",
            command=command,
            shell=shell,
            working_directory=working_directory,
            session_key=session_key,
            metadata=dict(metadata or {}),
        )
        return self.session

    def read_output(
        self,
        *,
        process_id: str,
        stdout_offset: int = 0,
        stderr_offset: int = 0,
        limit: int | None = None,
    ) -> ProcessOutputWindow:
        self.read_limits.append(limit)
        now = datetime.now(timezone.utc)
        stdout = "x" * int(limit or 0)
        return ProcessOutputWindow(
            process_id=process_id,
            status=ProcessStatus.RUNNING,
            exit_code=None,
            stdout=stdout,
            stderr="",
            stdout_offset=stdout_offset,
            stderr_offset=stderr_offset,
            next_stdout_offset=stdout_offset + len(stdout),
            next_stderr_offset=stderr_offset,
            started_at=now,
            ended_at=None,
        )


@dataclass(frozen=True, slots=True)
class _CredentialProviderCall:
    binding_id: str
    consumer_id: str


class _FakeCredentialProvider:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = dict(values)
        self.calls: list[_CredentialProviderCall] = []

    def resolve_credential(
        self,
        binding: CredentialBindingRef,
        *,
        consumer,
        **_kwargs,
    ) -> str:
        self.calls.append(
            _CredentialProviderCall(
                binding_id=binding.binding_id,
                consumer_id=consumer.consumer_id,
            ),
        )
        return self.values[binding.binding_id]
