from __future__ import annotations

from importlib.util import find_spec
from pathlib import Path
import unittest

from crxzipple.interfaces.runtime_container import AppKey
import crxzipple.modules.orchestration as orchestration_public
import crxzipple.modules.orchestration.application as orchestration_application
import crxzipple.modules.orchestration.application.commands as orchestration_commands
import crxzipple.modules.orchestration.application.intake_commands as orchestration_intake_commands
import crxzipple.modules.orchestration.application.ports as orchestration_ports
import crxzipple.modules.orchestration.application.ports.runtime as runtime_ports
from crxzipple.modules.orchestration.application.coordinators.intake import (
    RunIntakeCoordinator,
)
from crxzipple.modules.orchestration.application.scheduler_service import (
    OrchestrationSchedulerService,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


class OrchestrationServiceSurfaceTests(unittest.TestCase):
    def test_control_facade_module_is_removed(self) -> None:
        self.assertIsNone(
            find_spec(
                "crxzipple.modules.orchestration.application.control_service",
            ),
        )

    def test_container_does_not_expose_control_facade(self) -> None:
        keys = {item.value for item in AppKey}

        self.assertNotIn("orchestration.control_service", keys)
        self.assertNotIn("orchestration.legacy_control_service", keys)
        self.assertNotIn("orchestration.service_graph", keys)
        self.assertNotIn("orchestration.runtime", keys)

    def test_control_legacy_types_are_removed_from_public_surfaces(self) -> None:
        self.assertFalse(hasattr(runtime_ports, "OrchestrationControlPort"))
        self.assertFalse(hasattr(orchestration_application, "OrchestrationControlService"))
        self.assertFalse(hasattr(orchestration_application, "OrchestrationControlPort"))
        self.assertFalse(hasattr(orchestration_ports, "OrchestrationControlPort"))
        self.assertFalse(hasattr(orchestration_public, "OrchestrationControlService"))
        self.assertFalse(hasattr(orchestration_public, "OrchestrationControlPort"))

        self.assertNotIn("OrchestrationControlService", orchestration_application.__all__)
        self.assertNotIn("OrchestrationControlPort", orchestration_application.__all__)
        self.assertNotIn("OrchestrationControlPort", orchestration_ports.__all__)
        self.assertNotIn("OrchestrationControlService", orchestration_public.__all__)
        self.assertNotIn("OrchestrationControlPort", orchestration_public.__all__)

    def test_service_graph_is_not_a_public_orchestration_surface(self) -> None:
        self.assertFalse(hasattr(orchestration_application, "OrchestrationServiceGraph"))
        self.assertFalse(hasattr(orchestration_public, "OrchestrationServiceGraph"))
        self.assertNotIn("OrchestrationServiceGraph", orchestration_application.__all__)
        self.assertNotIn("OrchestrationServiceGraph", orchestration_public.__all__)

    def test_runtime_assembly_does_not_expose_service_graph(self) -> None:
        from crxzipple.app.assembly.orchestration import OrchestrationRuntimeAssembly

        self.assertNotIn(
            "service_graph",
            OrchestrationRuntimeAssembly.__dataclass_fields__,
        )

    def test_session_runtime_control_is_not_orchestration_owned_surface(self) -> None:
        self.assertIsNone(
            find_spec(
                "crxzipple.modules.orchestration.application.session_runtime_control",
            ),
        )
        forbidden = (
            "IngressBackedSessionRuntimeControl",
            "SchedulerBackedSessionRuntimeControl",
        )
        for name in forbidden:
            self.assertFalse(hasattr(orchestration_application, name))
            self.assertFalse(hasattr(orchestration_public, name))
            self.assertNotIn(name, orchestration_application.__all__)
            self.assertNotIn(name, orchestration_public.__all__)

    def test_scheduler_control_port_is_not_part_of_public_surface(self) -> None:
        self.assertFalse(hasattr(orchestration_application, "OrchestrationSchedulerControlPort"))
        self.assertFalse(hasattr(orchestration_ports, "OrchestrationSchedulerControlPort"))
        self.assertFalse(hasattr(orchestration_public, "OrchestrationSchedulerControlPort"))

        self.assertNotIn(
            "OrchestrationSchedulerControlPort",
            orchestration_application.__all__,
        )
        self.assertNotIn(
            "OrchestrationSchedulerControlPort",
            orchestration_ports.__all__,
        )
        self.assertNotIn(
            "OrchestrationSchedulerControlPort",
            orchestration_public.__all__,
        )

    def test_scheduler_runtime_ports_define_public_and_internal_boundary(self) -> None:
        self.assertTrue(hasattr(runtime_ports, "OrchestrationSchedulerRuntimePort"))
        self.assertTrue(hasattr(runtime_ports, "OrchestrationSchedulerMaintenancePort"))
        self.assertTrue(hasattr(runtime_ports, "OrchestrationSubmissionPort"))
        self.assertTrue(hasattr(runtime_ports, "OrchestrationIngressProcessingPort"))
        self.assertTrue(hasattr(runtime_ports, "OrchestrationSchedulerIntakePort"))
        self.assertFalse(hasattr(runtime_ports, "OrchestrationSchedulerSubmitPort"))
        self.assertFalse(
            hasattr(runtime_ports.OrchestrationSubmissionPort, "process_run_request"),
        )

        self.assertIn(
            "OrchestrationSchedulerRuntimePort",
            orchestration_application.__all__,
        )
        self.assertIn(
            "OrchestrationSchedulerMaintenancePort",
            orchestration_application.__all__,
        )
        self.assertIn(
            "OrchestrationSubmissionPort",
            orchestration_application.__all__,
        )
        self.assertNotIn(
            "OrchestrationSchedulerIntakePort",
            orchestration_application.__all__,
        )
        self.assertNotIn(
            "OrchestrationSchedulerSubmitPort",
            orchestration_application.__all__,
        )

    def test_session_resolution_types_are_not_part_of_orchestration_public_surface(self) -> None:
        internalized = (
            "ResolveSessionBundleInput",
            "SessionBundle",
            "SessionResolver",
            "SessionRoutingDecision",
            "OrchestrationRouter",
        )

        for name in internalized:
            self.assertFalse(hasattr(orchestration_application, name))
            self.assertFalse(hasattr(orchestration_public, name))
            self.assertNotIn(name, orchestration_application.__all__)
            self.assertNotIn(name, orchestration_public.__all__)

        self.assertFalse(
            hasattr(runtime_ports.OrchestrationInspectionPort, "resolve_session_bundle"),
        )

    def test_scheduler_runtime_service_does_not_expose_low_level_intake_methods(self) -> None:
        self.assertFalse(hasattr(OrchestrationSchedulerService, "accept"))
        self.assertFalse(hasattr(OrchestrationSchedulerService, "route"))
        self.assertFalse(hasattr(OrchestrationSchedulerService, "bind_session"))
        self.assertFalse(hasattr(OrchestrationSchedulerService, "prepare_session_run"))
        self.assertFalse(hasattr(OrchestrationSchedulerService, "enqueue"))

    def test_submission_service_does_not_process_ingress_requests(self) -> None:
        self.assertFalse(
            hasattr(
                orchestration_application.OrchestrationIngressSubmissionService,
                "process_run_request",
            ),
        )

    def test_container_exposes_internal_intake_service_separately(self) -> None:
        self.assertEqual(
            AppKey.ORCHESTRATION_INTAKE_SERVICE.value,
            "orchestration.intake_service",
        )
        self.assertEqual(
            AppKey.ORCHESTRATION_SCHEDULER_SERVICE.value,
            "orchestration.scheduler_service",
        )
        self.assertFalse(hasattr(orchestration_application, "OrchestrationIntakeService"))
        self.assertFalse(hasattr(orchestration_public, "OrchestrationIntakeService"))

    def test_low_level_intake_commands_are_not_public_exports(self) -> None:
        internal_only = (
            "AcceptOrchestrationRunInput",
            "BindSessionInput",
            "EnqueueOrchestrationRunInput",
            "PrepareSessionRunInput",
            "RouteOrchestrationRunInput",
        )

        for name in internal_only:
            self.assertTrue(hasattr(orchestration_intake_commands, name))
            self.assertFalse(hasattr(orchestration_commands, name))
            self.assertFalse(hasattr(orchestration_application, name))
            self.assertFalse(hasattr(orchestration_public, name))
            self.assertNotIn(name, orchestration_application.__all__)
            self.assertNotIn(name, orchestration_public.__all__)

    def test_intake_coordinator_depends_on_preparation_workflow_plan(self) -> None:
        fields = RunIntakeCoordinator.__dataclass_fields__

        self.assertIn("plan_prepared_session_run", fields)
        self.assertNotIn("resolve_session_bundle", fields)
        self.assertNotIn("resolve_session_bundle_input_factory", fields)
        self.assertNotIn("session_start_prompt_flow_hint", fields)

    def test_prompt_and_turn_submission_depend_on_outbound_ports(self) -> None:
        self.assertTrue(hasattr(orchestration_ports, "AgentProfileCatalogPort"))
        self.assertTrue(hasattr(orchestration_ports, "ArtifactVariantReadPort"))
        self.assertTrue(hasattr(orchestration_ports, "EventBusPort"))
        self.assertTrue(hasattr(orchestration_ports, "EventPublishPort"))
        self.assertTrue(hasattr(orchestration_ports, "EventPublishManyPort"))
        self.assertTrue(hasattr(orchestration_ports, "EventSubscriptionStreamPort"))
        self.assertTrue(hasattr(orchestration_ports, "EventTopicWaitPort"))
        self.assertTrue(hasattr(orchestration_ports, "OrchestrationSessionPort"))
        self.assertTrue(hasattr(orchestration_ports, "SessionResolutionPort"))
        self.assertTrue(hasattr(orchestration_ports, "SessionTranscriptPort"))

        files = (
            REPO_ROOT
            / "src"
            / "crxzipple"
            / "modules"
            / "orchestration"
            / "application"
            / "prompt_input.py",
            REPO_ROOT
            / "src"
            / "crxzipple"
            / "modules"
            / "orchestration"
            / "application"
            / "turn_submission.py",
        )
        forbidden = (
            "AgentApplicationService",
            "ArtifactApplicationService",
            "EventsApplicationService",
            "SessionApplicationService",
        )
        for path in files:
            text = path.read_text(encoding="utf-8")
            for name in forbidden:
                self.assertNotIn(name, text, path.name)

    def test_orchestration_application_does_not_type_against_owner_services(self) -> None:
        root = (
            REPO_ROOT
            / "src"
            / "crxzipple"
            / "modules"
            / "orchestration"
            / "application"
        )
        forbidden = (
            "AgentApplicationService",
            "ArtifactApplicationService",
            "EventsApplicationService",
            "SessionApplicationService",
            "SessionTreeLookupPort",
        )
        violations: list[str] = []
        for path in sorted(root.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for name in forbidden:
                if name in text:
                    violations.append(f"{path.relative_to(REPO_ROOT)}: {name}")

        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()
