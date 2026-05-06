from __future__ import annotations

from importlib.util import find_spec
import unittest

from crxzipple.bootstrap import AppContainer
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


class OrchestrationServiceSurfaceTests(unittest.TestCase):
    def test_control_facade_module_is_removed(self) -> None:
        self.assertIsNone(
            find_spec(
                "crxzipple.modules.orchestration.application.control_service",
            ),
        )

    def test_container_does_not_expose_control_facade(self) -> None:
        fields = AppContainer.__dataclass_fields__

        self.assertNotIn("orchestration_control_service", fields)
        self.assertNotIn("legacy_orchestration_control_service", fields)

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
        self.assertTrue(hasattr(runtime_ports, "OrchestrationSchedulerIntakePort"))

        self.assertIn(
            "OrchestrationSchedulerRuntimePort",
            orchestration_application.__all__,
        )
        self.assertIn(
            "OrchestrationSchedulerMaintenancePort",
            orchestration_application.__all__,
        )
        self.assertNotIn(
            "OrchestrationSchedulerIntakePort",
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

    def test_container_exposes_internal_intake_service_separately(self) -> None:
        fields = AppContainer.__dataclass_fields__

        self.assertIn("orchestration_intake_service", fields)
        self.assertIn("orchestration_scheduler_service", fields)
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


if __name__ == "__main__":
    unittest.main()
