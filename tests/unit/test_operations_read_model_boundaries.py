from __future__ import annotations

import re
from pathlib import Path

import crxzipple.modules.operations.application.read_models.ports as operations_ports

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
    expected_ports = (
        "OperationsAccessReadinessPort",
        "OperationsAgentProfilePort",
        "OperationsArtifactReadPort",
        "OperationsChannelInteractionPort",
        "OperationsChannelProfilePort",
        "OperationsChannelRuntimePort",
        "OperationsDaemonManagerPort",
        "OperationsDaemonRegistryPort",
        "OperationsEventContractRegistryPort",
        "OperationsEventDefinitionRegistryPort",
        "OperationsEventPublishPort",
        "OperationsEventStreamPort",
        "OperationsLlmQueryPort",
        "OperationsMemoryQueryPort",
        "OperationsObservationReadPort",
        "OperationsProcessQueryPort",
        "OperationsRemoteToolRuntimeRegistryPort",
        "OperationsRuntimeBootstrapConfigPort",
        "OperationsSettingsQueryPort",
        "OperationsSkillCatalogPort",
        "OperationsToolQueryPort",
    )

    for name in expected_ports:
        assert hasattr(operations_ports, name)


def test_operations_read_model_factory_does_not_type_against_owner_services() -> None:
    text = (READ_MODELS_ROOT / "factory.py").read_text(encoding="utf-8")
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

    for name in forbidden:
        assert re.search(rf"\b{re.escape(name)}\b", text) is None


def test_operations_tool_read_model_uses_operations_owned_tool_port() -> None:
    text = (READ_MODELS_ROOT / "tool.py").read_text(encoding="utf-8")

    assert "OperationsToolQueryPort" in text
    assert "from crxzipple.modules.tool.application import ToolQueryPort" not in text
    assert re.search(r"\bToolQueryPort\b", text) is None
