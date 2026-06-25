from __future__ import annotations

import re
from pathlib import Path

import crxzipple.modules.operations.application.read_models.ports_access_settings as access_settings_ports
import crxzipple.modules.operations.application.read_models.ports_context as context_ports
import crxzipple.modules.operations.application.read_models.ports_llm_agent as llm_agent_ports
import crxzipple.modules.operations.application.read_models.ports_runtime as runtime_ports
import crxzipple.modules.operations.application.read_models.ports_runtime_sources as runtime_source_ports
import crxzipple.modules.operations.application.read_models.ports_tooling as tooling_ports

REPO_ROOT = Path(__file__).resolve().parents[2]
READ_MODELS_ROOT = (
    REPO_ROOT
    / "src"
    / "crxzipple"
    / "modules"
    / "operations"
    / "application"
    / "read_models"
)


def test_operations_read_model_ports_define_cross_module_read_contracts() -> None:
    expected_ports = {
        access_settings_ports: (
            "OperationsAccessReadinessPort",
            "OperationsSettingsQueryPort",
        ),
        context_ports: (
            "OperationsContextObservationSnapshotPort",
            "OperationsContextSliceBuilderPort",
            "OperationsContextTreePort",
            "OperationsContextWorkspacePort",
            "OperationsMemoryQueryPort",
            "OperationsMemoryWatchRegistryPort",
            "OperationsSkillCatalogPort",
        ),
        llm_agent_ports: (
            "OperationsAgentProfilePort",
            "OperationsLlmQueryPort",
        ),
        runtime_ports: (
            "OperationsEventContractRegistryPort",
            "OperationsEventDefinitionRegistryPort",
            "OperationsEventPublishPort",
            "OperationsEventStreamPort",
            "OperationsObservationReadPort",
            "OperationsObserverRuntimePort",
            "OperationsRuntimeBootstrapConfigPort",
            "OperationsRuntimeMetricsPort",
        ),
        runtime_source_ports: (
            "OperationsBrowserProfilePort",
            "OperationsChannelInteractionPort",
            "OperationsChannelProfilePort",
            "OperationsChannelRuntimePort",
            "OperationsDaemonManagerPort",
            "OperationsDaemonRegistryPort",
            "OperationsProcessQueryPort",
        ),
        tooling_ports: (
            "OperationsArtifactReadPort",
            "OperationsRemoteToolRuntimeRegistryPort",
            "OperationsToolQueryPort",
        ),
    }

    for module, names in expected_ports.items():
        for name in names:
            assert hasattr(module, name)


def test_operations_read_model_factory_does_not_type_against_owner_services() -> None:
    texts = (
        (READ_MODELS_ROOT / "factory.py").read_text(encoding="utf-8"),
        (READ_MODELS_ROOT / "factory_context.py").read_text(encoding="utf-8"),
    )
    forbidden = (
        "AccessApplicationService",
        "AgentApplicationService",
        "ArtifactApplicationService",
        "ChannelInteractionService",
        "ChannelProfileApplicationService",
        "ChannelRuntimeManager",
        "DaemonApplicationService",
        "DaemonManager",
        "EventsApplicationService",
        "FileBackedMemoryService",
        "LlmApplicationService",
        "ProcessApplicationService",
        "SettingsQueryService",
        "SkillManager",
        "ToolQueryPort",
        "ToolRuntimeRegistry",
    )

    for text in texts:
        for name in forbidden:
            assert re.search(rf"\b{re.escape(name)}\b", text) is None


def test_operations_tool_read_model_uses_operations_owned_tool_port() -> None:
    text = (READ_MODELS_ROOT / "tool.py").read_text(encoding="utf-8")

    assert "OperationsToolQueryPort" in text
    assert "from crxzipple.modules.tool.application import ToolQueryPort" not in text
    assert re.search(r"\bToolQueryPort\b", text) is None
