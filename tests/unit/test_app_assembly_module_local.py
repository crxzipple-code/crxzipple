from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile

from crxzipple.app import AppKey, AssemblyPlan, AssemblyTarget, build_app_container
from crxzipple.app.assembly.access import access_factories
from crxzipple.app.assembly.agent import agent_activation_tasks, agent_factories
from crxzipple.app.assembly.artifacts import artifact_factories
from crxzipple.app.assembly.authorization import authorization_factories
from crxzipple.app.assembly.browser import BrowserInfrastructure, browser_factories
from crxzipple.app.assembly.channels import (
    ChannelInfrastructure,
    channel_control_factories,
    channel_factories,
)
from crxzipple.app.assembly.daemon import daemon_factories, daemon_manager_factories
from crxzipple.app.assembly.database import database_factories
from crxzipple.app.assembly.dispatch import dispatch_factories
from crxzipple.app.assembly.events import events_factories
from crxzipple.app.assembly.llm import llm_factories
from crxzipple.app.assembly.llm import llm_adapter_registry_factories
from crxzipple.app.assembly.memory import memory_factories
from crxzipple.app.assembly.mobile import MobileInfrastructure, mobile_factories
from crxzipple.app.assembly.ocr import ocr_factories
from crxzipple.app.assembly.process import process_factories
from crxzipple.app.assembly.runtime import runtime_plan
from crxzipple.app.assembly.runtime_defaults import runtime_defaults_factories
from crxzipple.app.assembly.settings import settings_factories
from crxzipple.app.assembly.session import session_factories
from crxzipple.app.assembly.skills import skills_factories
from crxzipple.app.assembly.tool import tool_activation_tasks, tool_factories
from crxzipple.app.assembly.unit_of_work import unit_of_work_factories
from crxzipple.core.config import AgentProfileSettings, Settings, load_settings
from crxzipple.core.db import create_schema
from crxzipple.modules.access.application.oauth import DEFAULT_CODEX_OAUTH_PROVIDER_ID
from crxzipple.modules.access.application.services import AccessApplicationService
from crxzipple.modules.artifacts import ArtifactApplicationService
from crxzipple.modules.authorization.application import AuthorizationApplicationService
from crxzipple.modules.channels import (
    ChannelAccountProfile,
    ChannelControlService,
    ChannelProfile,
)
from crxzipple.modules.daemon import (
    DaemonApplicationService,
    DaemonManager,
    DaemonServiceSpec,
)
from crxzipple.modules.dispatch.application import (
    CreateDispatchTaskInput,
    DispatchApplicationService,
)
from crxzipple.modules.llm.application import LlmApplicationService
from crxzipple.modules.llm.domain import LlmApiFamily
from crxzipple.modules.memory.application import (
    FileBackedMemoryService,
    MemorySettingsBootstrapConfig,
)
from crxzipple.modules.ocr import OcrApplicationService, OcrResultSerializer
from crxzipple.modules.process import ProcessApplicationService, derive_process_store_root
from crxzipple.modules.session.application import (
    EnsureSessionInput,
    SessionApplicationService,
    SessionResolutionService,
)
from crxzipple.modules.settings.application import SettingsQueryService
from crxzipple.modules.skills import FilesystemSkillRepository
from crxzipple.modules.skills.application import SkillManager
from crxzipple.modules.tool.application import (
    ExecuteToolInput,
    ToolApplicationService,
    ToolSettingsBootstrapConfig,
)
from crxzipple.modules.tool.domain import ToolMode
from crxzipple.modules.tool.domain.value_objects import ToolRunStatus
from crxzipple.modules.tool.infrastructure import LocalToolRuntimeRegistry, ToolRuntimeRegistry
from crxzipple.shared.domain.events import named_event_topic
from tests.unit.tool_catalog_seed import seed_catalog_tool
from tests.unit.tool_test_support import tool_dependency_bindings


def test_settings_factories_seed_governance_resources() -> None:
    with _assembly_harness() as harness:
        container = build_app_container(
            AssemblyPlan(module_local_factories=database_factories() + settings_factories()),
            target=AssemblyTarget.TEST,
            overrides={AppKey.CORE_SETTINGS: harness.settings},
        )
        try:
            query_service = container.require(AppKey.SETTINGS_QUERY_SERVICE)
            bootstrap_result = container.require(AppKey.SETTINGS_BOOTSTRAP_RESULT)

            assert isinstance(query_service, SettingsQueryService)
            assert bootstrap_result.created > 0
            assert query_service.list_resources()
            assert container.has(AppKey.SETTINGS_MATERIALIZER)
        finally:
            container.require(AppKey.DATABASE_ENGINE).dispose()


def test_access_factory_builds_credential_service_and_codex_provider() -> None:
    with _assembly_harness(create_full_schema=True) as harness:
        container = build_app_container(
            _module_local_plan(
                settings_factories() + events_factories() + access_factories(),
            ),
            target=AssemblyTarget.TEST,
            overrides=harness.base_overrides,
        )

        access_service = container.require(AppKey.ACCESS_SERVICE)
        oauth_service = container.require(AppKey.ACCESS_OAUTH_SERVICE)

        assert isinstance(access_service, AccessApplicationService)
        assert oauth_service.repository.get_oauth_provider(
            DEFAULT_CODEX_OAUTH_PROVIDER_ID,
        )


def test_authorization_factory_builds_abac_service_from_settings() -> None:
    with _assembly_harness(create_full_schema=True) as harness:
        container = build_app_container(
            _module_local_plan(settings_factories() + authorization_factories()),
            target=AssemblyTarget.TEST,
            overrides=harness.base_overrides,
        )

        authorization_service = container.require(AppKey.AUTHORIZATION_SERVICE)
        policy_count = container.require(AppKey.AUTHORIZATION_BOOTSTRAP_POLICY_COUNT)

        assert isinstance(authorization_service, AuthorizationApplicationService)
        assert authorization_service.is_enabled()
        assert isinstance(policy_count, int)


def test_llm_factory_builds_adapter_registry() -> None:
    container = build_app_container(
        AssemblyPlan(module_local_factories=llm_adapter_registry_factories()),
        target=AssemblyTarget.TEST,
    )
    registry = container.require(AppKey.LLM_ADAPTER_REGISTRY)

    assert registry.get(LlmApiFamily.OPENAI_RESPONSES) is not None
    assert registry.get(LlmApiFamily.OPENAI_CODEX_RESPONSES) is not None
    assert registry.get(LlmApiFamily.OPENAI_CHAT_COMPATIBLE) is not None
    assert registry.get(LlmApiFamily.ANTHROPIC_MESSAGES) is not None
    assert registry.get(LlmApiFamily.GEMINI_GENERATE_CONTENT) is not None


def test_events_and_uow_factories_support_llm_service_construction() -> None:
    with _assembly_harness(create_full_schema=True) as harness:
        container = build_app_container(
            _module_local_plan(
                settings_factories()
                + access_factories()
                + events_factories()
                + unit_of_work_factories()
                + llm_factories(),
            ),
            target=AssemblyTarget.TEST,
            overrides=harness.base_overrides,
        )

        assert container.has(AppKey.EVENTS_SERVICE)
        assert container.has(AppKey.EVENT_DEFINITION_REGISTRY)
        assert callable(container.require(AppKey.UNIT_OF_WORK_FACTORY))
        assert isinstance(container.require(AppKey.LLM_SERVICE), LlmApplicationService)


def test_session_factory_builds_session_lifecycle_services() -> None:
    with _assembly_harness(create_full_schema=True) as harness:
        container = build_app_container(
            _module_local_plan(
                settings_factories()
                + events_factories()
                + unit_of_work_factories()
                + agent_factories()
                + session_factories(),
            ),
            target=AssemblyTarget.TEST,
            overrides=harness.base_overrides,
        )

        session_service = container.require(AppKey.SESSION_SERVICE)
        resolution_service = container.require(AppKey.SESSION_RESOLUTION_SERVICE)

        assert isinstance(session_service, SessionApplicationService)
        assert isinstance(resolution_service, SessionResolutionService)
        session = session_service.ensure_session(
            EnsureSessionInput(
                key="session:test",
                agent_id="assistant",
                workspace=str(Path(harness._tempdir.name) / "workspace"),
            ),
        )
        assert session.id == "session:test"
        assert session.agent_id == "assistant"


def test_dispatch_factory_builds_task_queue_service() -> None:
    with _assembly_harness(create_full_schema=True) as harness:
        container = build_app_container(
            _module_local_plan(
                settings_factories()
                + events_factories()
                + unit_of_work_factories()
                + dispatch_factories(),
            ),
            target=AssemblyTarget.TEST,
            overrides=harness.base_overrides,
        )

        dispatch_service = container.require(AppKey.DISPATCH_SERVICE)

        assert isinstance(dispatch_service, DispatchApplicationService)
        task = dispatch_service.create_task(
            CreateDispatchTaskInput(
                task_id="dispatch:test",
                owner_kind="test",
                owner_id="run-1",
                lane_key="lane:test",
            ),
        )
        assert task.id == "dispatch:test"
        assert task.owner_kind == "test"


def test_process_factory_builds_process_service_from_settings() -> None:
    with _assembly_harness() as harness:
        container = build_app_container(
            _module_local_plan(process_factories()),
            target=AssemblyTarget.TEST,
            overrides={AppKey.CORE_SETTINGS: harness.settings},
        )
        service = container.require(AppKey.PROCESS_SERVICE)
        try:
            assert isinstance(service, ProcessApplicationService)
            assert service.repository.root_dir == derive_process_store_root(
                harness.settings.database_url,
            ).resolve()
            assert service.list_sessions() == ()
        finally:
            service.close()


def test_daemon_factory_builds_service_spec_instance_and_lease_management() -> None:
    with _assembly_harness() as harness:
        spec = DaemonServiceSpec(
            key="worker:test",
            display_name="Test Worker",
            role="worker",
            managed_by="internal",
            transport="process",
            service_group="workers",
        )
        container = build_app_container(
            _module_local_plan(
                daemon_factories(bootstrap_specs_provider=lambda _settings: (spec,)),
            ),
            target=AssemblyTarget.TEST,
            overrides={AppKey.CORE_SETTINGS: harness.settings},
        )

        service = container.require(AppKey.DAEMON_SERVICE)

        assert isinstance(service, DaemonApplicationService)
        assert [item.key for item in service.list_service_specs()] == ["worker:test"]
        assert service.list_instances() == ()
        assert service.list_leases() == ()


def test_daemon_manager_factory_builds_daemon_process_integration() -> None:
    with _assembly_harness() as harness:
        container = build_app_container(
            _module_local_plan(
                daemon_factories() + process_factories() + daemon_manager_factories(),
            ),
            target=AssemblyTarget.TEST,
            overrides={AppKey.CORE_SETTINGS: harness.settings},
        )

        manager = container.require(AppKey.DAEMON_MANAGER)
        process_service = container.require(AppKey.PROCESS_SERVICE)

        try:
            assert isinstance(manager, DaemonManager)
            assert manager.process_service is process_service
            assert manager.daemon_service is container.require(AppKey.DAEMON_SERVICE)
        finally:
            process_service.close()


def test_artifact_factory_builds_filesystem_artifact_service() -> None:
    with _assembly_harness() as harness:
        container = build_app_container(
            _module_local_plan(artifact_factories()),
            target=AssemblyTarget.TEST,
            overrides={AppKey.CORE_SETTINGS: harness.settings},
        )

        service = container.require(AppKey.ARTIFACT_SERVICE)

        assert isinstance(service, ArtifactApplicationService)
        artifact = service.create_artifact(
            data=b"hello",
            mime_type="text/plain",
            name="hello.txt",
        )
        binary = service.resolve_variant(artifact.id)
        assert binary.path.read_bytes() == b"hello"


def test_skills_factory_builds_owner_manager_without_settings_materializer() -> None:
    with _assembly_harness() as harness:
        def repository_factory() -> FilesystemSkillRepository:
            return FilesystemSkillRepository(
                global_root=Path(harness._tempdir.name) / "global-skills",
                system_root=Path(harness._tempdir.name) / "system-skills",
            )

        container = build_app_container(
            _module_local_plan(
                skills_factories(
                    repository_factory=repository_factory,
                ),
            ),
            target=AssemblyTarget.TEST,
            overrides=harness.base_overrides,
        )

        manager = container.require(AppKey.SKILL_MANAGER)

        assert isinstance(manager, SkillManager)
        assert manager.list_available(workspace_dir=None, surface="agent") == ()


def test_browser_factory_builds_profile_runtime_infrastructure() -> None:
    with _assembly_harness() as harness:
        container = build_app_container(
            _module_local_plan(events_factories() + daemon_factories() + browser_factories()),
            target=AssemblyTarget.TEST,
            overrides={AppKey.CORE_SETTINGS: harness.settings},
        )

        infrastructure = container.require(AppKey.BROWSER_INFRASTRUCTURE)
        try:
            assert isinstance(infrastructure, BrowserInfrastructure)
            assert infrastructure.system_config.profiles
            assert infrastructure.system_config_store.load().profiles
            assert container.require(AppKey.BROWSER_PROFILE_POOL_STORE) is infrastructure.profile_pool_store
            assert container.require(AppKey.BROWSER_PROFILE_ALLOCATION_STORE) is infrastructure.profile_allocation_store
            assert container.require(AppKey.BROWSER_PROFILE_POOL_SERVICE) is infrastructure.profile_pool_service
            assert container.require(AppKey.BROWSER_PROFILE_ALLOCATOR_SERVICE) is infrastructure.profile_allocator_service
            assert container.require(AppKey.BROWSER_QUERY_SERVICE) is infrastructure.profile_query_service
            assert infrastructure.facade is not None
            assert infrastructure.result_serializer is not None
        finally:
            for cleanup in infrastructure.cleanup_callbacks:
                cleanup()


def test_ocr_factory_builds_service_and_serializer() -> None:
    with _assembly_harness() as harness:
        container = build_app_container(
            _module_local_plan(artifact_factories() + ocr_factories()),
            target=AssemblyTarget.TEST,
            overrides={AppKey.CORE_SETTINGS: harness.settings},
        )

        assert isinstance(container.require(AppKey.OCR_SERVICE), OcrApplicationService)
        assert isinstance(
            container.require(AppKey.OCR_RESULT_SERIALIZER),
            OcrResultSerializer,
        )


def test_mobile_factory_builds_device_runtime_infrastructure() -> None:
    with _assembly_harness() as harness:
        container = build_app_container(
            _module_local_plan(
                artifact_factories() + ocr_factories() + mobile_factories(),
            ),
            target=AssemblyTarget.TEST,
            overrides={AppKey.CORE_SETTINGS: harness.settings},
        )

        infrastructure = container.require(AppKey.MOBILE_INFRASTRUCTURE)

        assert isinstance(infrastructure, MobileInfrastructure)
        assert infrastructure.system_config_store.load().devices == ()
        assert infrastructure.facade is not None
        assert infrastructure.result_serializer is not None


def test_channel_factories_build_profile_registry_and_daemon_control() -> None:
    with _assembly_harness() as harness:
        settings = replace(
            harness.settings,
            channel_profiles=(
                ChannelProfile(
                    channel_type="web",
                    accounts=(
                        ChannelAccountProfile(
                            account_id="primary",
                            transport_mode="sse",
                        ),
                    ),
                ),
            ),
        )
        container = build_app_container(
            _module_local_plan(
                daemon_factories() + channel_factories() + channel_control_factories(),
            ),
            target=AssemblyTarget.TEST,
            overrides={AppKey.CORE_SETTINGS: settings},
        )

        infrastructure = container.require(AppKey.CHANNEL_INFRASTRUCTURE)
        control_service = container.require(AppKey.CHANNEL_CONTROL_SERVICE)
        daemon_service = container.require(AppKey.DAEMON_SERVICE)

        assert isinstance(infrastructure, ChannelInfrastructure)
        assert isinstance(control_service, ChannelControlService)
        assert [profile.channel_type for profile in infrastructure.system_config.profiles] == [
            "web",
        ]
        assert infrastructure.runtime_manager.list_runtimes() == ()

        specs = control_service.sync_daemon_specs()

        assert [spec.key for spec in specs] == ["channel:web"]
        assert [spec.key for spec in daemon_service.list_service_specs()] == [
            "channel:web",
        ]


def test_memory_factory_builds_file_memory_service_from_settings() -> None:
    with _assembly_harness(create_full_schema=True) as harness:
        container = build_app_container(
            _module_local_plan(
                settings_factories()
                + events_factories()
                + access_factories()
                + memory_factories(),
            ),
            target=AssemblyTarget.TEST,
            overrides=harness.base_overrides,
        )

        bootstrap_config = container.require(AppKey.MEMORY_BOOTSTRAP_CONFIG)
        memory_service = container.require(AppKey.FILE_MEMORY_SERVICE)
        events_service = container.require(AppKey.EVENTS_SERVICE)

        assert isinstance(bootstrap_config, MemorySettingsBootstrapConfig)
        assert bootstrap_config.retrieval_backend == "hybrid"
        assert bootstrap_config.storage_root == harness.settings.memory_storage_root
        assert isinstance(memory_service, FileBackedMemoryService)
        assert container.get(AppKey.MEMORY_WATCH_REGISTRY) is None
        readiness_events = events_service.read_recent_event_topic(
            named_event_topic("memory.engine.readiness_observed"),
            limit=5,
        )
        assert len(readiness_events) == 1
        readiness_payload = readiness_events[0].envelope.payload
        assert readiness_payload["engine_id"] == "file_markdown"
        assert readiness_payload["readiness_status"] == "ready"
        assert readiness_payload["vector_provider"] == "local"


def test_tool_factory_builds_catalog_runtime_and_queue_services() -> None:
    with _assembly_harness(create_full_schema=True) as harness:
        container = build_app_container(
                _module_local_plan(
                    settings_factories()
                    + runtime_defaults_factories()
                    + access_factories()
                    + events_factories()
                    + unit_of_work_factories()
                    + dispatch_factories()
                    + process_factories()
                    + tool_factories(),
                ),
            target=AssemblyTarget.TEST,
            overrides=harness.base_overrides,
        )

        bootstrap_config = container.require(AppKey.TOOL_BOOTSTRAP_CONFIG)
        tool_service = container.require(AppKey.TOOL_SERVICE)
        local_catalog = container.require(AppKey.TOOL_LOCAL_RUNTIME_REGISTRY)
        remote_registry = container.require(AppKey.TOOL_REMOTE_RUNTIME_REGISTRY)
        package_plans = container.require(AppKey.TOOL_PACKAGE_PLANS)
        capability_bindings = container.require(AppKey.TOOL_CAPABILITY_BINDINGS)

        assert isinstance(bootstrap_config, ToolSettingsBootstrapConfig)
        assert isinstance(tool_service, ToolApplicationService)
        assert isinstance(local_catalog, LocalToolRuntimeRegistry)
        assert isinstance(remote_registry, ToolRuntimeRegistry)
        package_namespaces = [plan.namespace for plan in package_plans]
        assert package_namespaces[0] == "brave_search"
        assert "command" in package_namespaces
        assert set(container.require(AppKey.TOOL_CAPABILITY_CATALOG).capability_ids)
        assert sorted(capability_bindings) == [
            "credential_provider",
            "settings",
        ]
        assert not hasattr(tool_service, "list_discovery_providers")

        seed_catalog_tool(
            container,
            tool_id="test.background",
            name="Background Test Tool",
            description="A queued test tool.",
            supported_modes=(ToolMode.BACKGROUND,),
        )
        run = asyncio.run(
            tool_service.execute(
                ExecuteToolInput(
                    tool_id="test.background",
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )

        assert run.status is ToolRunStatus.QUEUED
        assert tool_service.get_tool_run(run.id).status is ToolRunStatus.QUEUED


def test_tool_activation_task_applies_manifest_packages_from_bindings() -> None:
    with _assembly_harness(create_full_schema=True) as harness:
        bindings = tool_dependency_bindings(
            {
                "credential_provider": object(),
                "artifact_service": object(),
                "browser_tool_application": object(),
                "browser_system_config_store": object(),
                "browser_profile_resolver": object(),
                "browser_capabilities_resolver": object(),
                "mobile_facade": object(),
                "mobile_result_serializer": object(),
                "memory_runtime_service": object(),
                "process_service": object(),
                "session_service": object(),
                "session_runtime_control": object(),
                "session_workspace_lookup": lambda _session_key: "/tmp/workspace",
                "skill_manager": object(),
                "skill_authoring_service": object(),
            },
        )
        container = build_app_container(
            AssemblyPlan(
                module_local_factories=(
                    settings_factories()
                    + runtime_defaults_factories()
                    + access_factories()
                    + events_factories()
                    + unit_of_work_factories()
                    + dispatch_factories()
                    + process_factories()
                    + tool_factories()
                ),
                activation_tasks=tool_activation_tasks(),
            ),
            target=AssemblyTarget.TEST,
            overrides={
                **harness.base_overrides,
                AppKey.TOOL_CAPABILITY_BINDINGS: bindings,
            },
        )

        local_catalog = container.require(AppKey.TOOL_LOCAL_RUNTIME_REGISTRY)
        remote_registry = container.require(AppKey.TOOL_REMOTE_RUNTIME_REGISTRY)
        assert local_catalog.get_handler("sessions_spawn") is not None
        assert local_catalog.get_handler("openai_image_generate") is not None
        assert remote_registry.get_handler("remote.echo") is not None
        assert (
            remote_registry.get_handler("openapi.open_meteo_weather.forecast_weather")
            is not None
        )


def test_runtime_plan_builds_executable_orchestration_and_tool_runtime() -> None:
    with _assembly_harness(create_full_schema=True) as harness:
        container = build_app_container(
            runtime_plan(enable_memory_watchers=False),
            target=AssemblyTarget.TEST,
            overrides=harness.base_overrides,
        )
        try:
            tool_service = container.require(AppKey.TOOL_SERVICE)
            local_catalog = container.require(AppKey.TOOL_LOCAL_RUNTIME_REGISTRY)
            remote_registry = container.require(AppKey.TOOL_REMOTE_RUNTIME_REGISTRY)

            assert container.has(AppKey.ORCHESTRATION_EXECUTOR_SERVICE)
            assert container.has(AppKey.ORCHESTRATION_SCHEDULER_SERVICE)
            assert container.has(AppKey.ORCHESTRATION_SCHEDULER_RUNTIME_EVENT_SERVICE)
            assert container.has(AppKey.TOOL_RUNTIME_EVENT_SERVICE)
            assert container.has(AppKey.EVENT_RELAY_RUNTIME_EVENT_SERVICE)
            assert container.has(AppKey.OPERATIONS_OBSERVER_RUNTIME_EVENT_SERVICE)
            assert container.has(AppKey.OPERATIONS_PROJECTION_MATERIALIZER)
            assert container.has(AppKey.LARK_CHANNEL_RUNTIME_SERVICE)
            assert container.has(AppKey.SESSION_RUNTIME_CONTROL)
            assert container.has(AppKey.MEMORY_RUNTIME_SERVICE)
            assert tool_service.submission_service.runtime_readiness is not None
            assert (
                tool_service.submission_service.artifact_service
                is container.require(AppKey.ARTIFACT_SERVICE)
            )
            assert local_catalog.get_handler("sessions_spawn") is not None
            assert local_catalog.get_handler("openai_image_generate") is not None
            assert remote_registry.get_handler("remote.echo") is not None
        finally:
            container.close()


def test_runtime_worker_targets_build_with_scoped_sidecar_surfaces() -> None:
    expectations = {
        AssemblyTarget.DAEMON_SUPERVISOR: {
            AppKey.DAEMON_MANAGER,
            AppKey.CHANNEL_CONTROL_SERVICE,
        },
        AssemblyTarget.ORCHESTRATION_SCHEDULER: {
            AppKey.ORCHESTRATION_SCHEDULER_SERVICE,
            AppKey.ORCHESTRATION_SCHEDULER_RUNTIME_EVENT_SERVICE,
            AppKey.TOOL_ORCHESTRATION_PORT,
            AppKey.TOOL_QUERY_SERVICE,
        },
        AssemblyTarget.ORCHESTRATION_EXECUTOR: {
            AppKey.ORCHESTRATION_EXECUTOR_SERVICE,
            AppKey.ORCHESTRATION_RUN_QUERY_SERVICE,
            AppKey.ORCHESTRATION_SUBMISSION_SERVICE,
            AppKey.ORCHESTRATION_INGRESS_PROCESSING_SERVICE,
            AppKey.ORCHESTRATION_CANCELLATION_SERVICE,
            AppKey.SESSION_RUNTIME_CONTROL,
            AppKey.TOOL_ORCHESTRATION_PORT,
            AppKey.TOOL_SERVICE,
            AppKey.TOOL_QUERY_SERVICE,
        },
        AssemblyTarget.TOOL_SCHEDULER: {
            AppKey.TOOL_QUERY_SERVICE,
            AppKey.TOOL_SCHEDULER_SERVICE,
            AppKey.TOOL_WORKER_REGISTRY_SERVICE,
        },
        AssemblyTarget.TOOL_WORKER: {
            AppKey.TOOL_QUERY_SERVICE,
            AppKey.TOOL_RUN_CONTROL_SERVICE,
            AppKey.TOOL_ORCHESTRATION_PORT,
            AppKey.TOOL_WORKER_REGISTRY_SERVICE,
            AppKey.TOOL_WORKER_SERVICE,
            AppKey.TOOL_RUNTIME_EVENT_SERVICE,
            AppKey.SESSION_RUNTIME_CONTROL,
            AppKey.ORCHESTRATION_RUN_QUERY_SERVICE,
            AppKey.ORCHESTRATION_SUBMISSION_SERVICE,
            AppKey.ORCHESTRATION_INGRESS_PROCESSING_SERVICE,
            AppKey.ORCHESTRATION_CANCELLATION_SERVICE,
        },
        AssemblyTarget.OPERATIONS_OBSERVER: {
            AppKey.OPERATIONS_PROJECTION_MATERIALIZER,
            AppKey.OPERATIONS_OBSERVER_RUNTIME_EVENT_SERVICE,
            AppKey.ORCHESTRATION_RUN_QUERY_SERVICE,
            AppKey.TOOL_QUERY_SERVICE,
        },
        AssemblyTarget.EVENT_RELAY_WORKER: {
            AppKey.ORCHESTRATION_RUN_QUERY_SERVICE,
            AppKey.EVENT_RELAY_RUNTIME_EVENT_SERVICE,
            AppKey.TOOL_QUERY_SERVICE,
        },
        AssemblyTarget.CHANNEL_RUNTIME: {
            AppKey.LARK_CHANNEL_RUNTIME_SERVICE,
            AppKey.WEB_CHANNEL_RUNTIME_SERVICE,
            AppKey.WEBHOOK_CHANNEL_RUNTIME_SERVICE,
            AppKey.ORCHESTRATION_SUBMISSION_SERVICE,
            AppKey.ORCHESTRATION_RUN_QUERY_SERVICE,
            AppKey.TOOL_QUERY_SERVICE,
        },
    }
    forbidden = {
        AssemblyTarget.TOOL_WORKER: {
            "orchestration.runtime",
            AppKey.ORCHESTRATION_EXECUTOR_SERVICE,
            AppKey.ORCHESTRATION_SCHEDULER_SERVICE,
            AppKey.EVENT_RELAY_RUNTIME_EVENT_SERVICE,
            AppKey.OPERATIONS_PROJECTION_MATERIALIZER,
        },
        AssemblyTarget.EVENT_RELAY_WORKER: {
            "orchestration.runtime",
            AppKey.ORCHESTRATION_EXECUTOR_SERVICE,
            AppKey.ORCHESTRATION_SCHEDULER_SERVICE,
            AppKey.TOOL_SERVICE,
            AppKey.TOOL_ORCHESTRATION_PORT,
            AppKey.TOOL_RUNTIME_EVENT_SERVICE,
            AppKey.OPERATIONS_PROJECTION_MATERIALIZER,
            AppKey.TOOL_WORKER_SERVICE,
        },
        AssemblyTarget.OPERATIONS_OBSERVER: {
            "orchestration.runtime",
            AppKey.ORCHESTRATION_EXECUTOR_SERVICE,
            AppKey.ORCHESTRATION_SCHEDULER_SERVICE,
            AppKey.TOOL_SERVICE,
            AppKey.TOOL_ORCHESTRATION_PORT,
            AppKey.EVENT_RELAY_RUNTIME_EVENT_SERVICE,
            AppKey.TOOL_RUNTIME_EVENT_SERVICE,
            AppKey.TOOL_WORKER_SERVICE,
        },
        AssemblyTarget.CHANNEL_RUNTIME: {
            "orchestration.runtime",
            AppKey.ORCHESTRATION_EXECUTOR_SERVICE,
            AppKey.ORCHESTRATION_SCHEDULER_SERVICE,
            AppKey.TOOL_SERVICE,
            AppKey.TOOL_ORCHESTRATION_PORT,
            AppKey.TOOL_WORKER_SERVICE,
        },
        AssemblyTarget.TOOL_SCHEDULER: {
            AppKey.TOOL_SERVICE,
            AppKey.TOOL_ORCHESTRATION_PORT,
            AppKey.TOOL_WORKER_SERVICE,
        },
        AssemblyTarget.ORCHESTRATION_SCHEDULER: {
            "orchestration.runtime",
            AppKey.ORCHESTRATION_EXECUTOR_SERVICE,
            AppKey.SESSION_RUNTIME_CONTROL,
            AppKey.TOOL_SERVICE,
            AppKey.TOOL_WORKER_SERVICE,
        },
        AssemblyTarget.ORCHESTRATION_EXECUTOR: {
            "orchestration.runtime",
            AppKey.ORCHESTRATION_SCHEDULER_SERVICE,
            AppKey.ORCHESTRATION_SCHEDULER_RUNTIME_EVENT_SERVICE,
        },
    }

    with _assembly_harness(create_full_schema=True) as harness:
        for target, required_keys in expectations.items():
            container = build_app_container(
                runtime_plan(enable_memory_watchers=False),
                target=target,
                overrides=harness.base_overrides,
            )
            try:
                for key in required_keys:
                    assert container.has(key), f"{target.value} missing {key}"
                for key in forbidden.get(target, ()):
                    assert not container.has(key), f"{target.value} leaked {key}"
            finally:
                container.close()


def test_agent_factory_bootstraps_profiles_without_orchestration_dependency() -> None:
    with _assembly_harness(create_full_schema=True) as harness:
        home_dir = Path(harness._tempdir.name) / "assistant-home"
        settings = replace(
            harness.settings,
            agent_profiles=(
                AgentProfileSettings(
                    id="assistant",
                    name="Assistant",
                    identity={"display_name": "Assistant"},
                    instruction_policy={"system_prompt": "Be useful."},
                    llm_routing_policy={"default_llm_id": "openai.gpt-5.4-mini"},
                    runtime_preferences={
                        "home_dir": str(home_dir),
                    },
                    memory={"scope_ref": "assistant-memory"},
                ),
            ),
        )
        container = build_app_container(
            AssemblyPlan(
                module_local_factories=(
                    settings_factories()
                    + events_factories()
                    + unit_of_work_factories()
                    + agent_factories()
                ),
                activation_tasks=agent_activation_tasks(),
            ),
            target=AssemblyTarget.TEST,
            overrides={**harness.base_overrides, AppKey.CORE_SETTINGS: settings},
        )

        agent_service = container.require(AppKey.AGENT_SERVICE)
        profile = agent_service.get_profile("assistant")

        assert profile.name == "Assistant"
        assert profile.memory.scope_ref == "assistant-memory"
        assert not (home_dir / ".state" / "memory-binding.json").exists()


def _module_local_plan(factories):
    return AssemblyPlan(module_local_factories=factories)


class _assembly_harness:
    def __init__(self, *, create_full_schema: bool = False) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        root = Path(self._tempdir.name)
        self.database_url = f"sqlite:///{root / 'test.db'}"
        self.settings = _test_settings(root, self.database_url)
        self.engine = None
        self.session_factory = None
        self.base_overrides = {}
        self._create_full_schema = create_full_schema

    def __enter__(self) -> "_assembly_harness":
        from crxzipple.core.db import build_engine, build_session_factory

        self.engine = build_engine(self.settings)
        self.session_factory = build_session_factory(self.engine)
        if self._create_full_schema:
            create_schema(self.engine)
        self.base_overrides = {
            AppKey.CORE_SETTINGS: self.settings,
            AppKey.DATABASE_ENGINE: self.engine,
            AppKey.DATABASE_SESSION_FACTORY: self.session_factory,
        }
        return self

    def __exit__(self, *_exc_info) -> None:
        if self.engine is not None:
            self.engine.dispose()
        self._tempdir.cleanup()


def _test_settings(root: Path, database_url: str) -> Settings:
    return replace(
        load_settings(),
        database_url=database_url,
        access_state_dir=str(root / "access"),
        authorization_policy_paths=(),
        authorization_runtime_policy_path=str(root / "authorization_runtime.yaml"),
        events_backend="file",
        events_redis_url=None,
        events_state_dir=str(root / "events"),
        operations_state_dir=str(root / "operations"),
        channels_state_dir=str(root / "channels"),
        daemon_state_dir=str(root / "daemon"),
        memory_storage_root=str(root / "memory"),
        browser_state_dir=str(root / "browser"),
        mobile_state_dir=str(root / "mobile"),
        artifact_store_dir=str(root / "artifacts"),
        channel_profiles=(),
        agent_profiles=(),
        llm_profiles=(),
    )
