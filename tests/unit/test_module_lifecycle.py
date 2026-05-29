import unittest

from crxzipple.app.module_lifecycle import (
    DependencyKind,
    DuplicatePortExportError,
    MissingServiceDependencyError,
    ModuleActivationPlan,
    ModuleDependency,
    ModulePortExport,
    PortRegistry,
    ReadinessStatus,
)


class ModuleLifecycleTestCase(unittest.TestCase):
    def test_port_registry_registers_and_resolves_exports(self) -> None:
        registry = PortRegistry()
        port_value = object()
        registry.register(
            ModulePortExport(
                name="tool.execution",
                provider_module="tool",
                value=port_value,
            )
        )

        resolved = registry.resolve(
            ModuleActivationPlan(
                module_name="orchestration",
                dependencies=(
                    ModuleDependency(
                        port_name="tool.execution",
                        kind=DependencyKind.SERVICE_DEPENDENCY,
                    ),
                ),
            )
        )

        self.assertIs(resolved.dependencies["tool.execution"], port_value)
        self.assertEqual(resolved.readiness.status, ReadinessStatus.READY)
        self.assertTrue(resolved.readiness.is_ready)

    def test_port_registry_rejects_duplicate_exports(self) -> None:
        registry = PortRegistry()
        registry.register(
            ModulePortExport(
                name="tool.execution",
                provider_module="tool",
                value=object(),
            )
        )

        with self.assertRaises(DuplicatePortExportError):
            registry.register(
                ModulePortExport(
                    name="tool.execution",
                    provider_module="other-tool",
                    value=object(),
                )
            )

    def test_missing_required_service_dependency_fails_resolution(self) -> None:
        registry = PortRegistry()
        plan = ModuleActivationPlan(
            module_name="orchestration",
            dependencies=(
                ModuleDependency(
                    port_name="tool.execution",
                    kind=DependencyKind.SERVICE_DEPENDENCY,
                ),
            ),
        )

        with self.assertRaises(MissingServiceDependencyError) as raised:
            registry.resolve(plan)

        self.assertEqual(raised.exception.module_name, "orchestration")
        self.assertEqual(raised.exception.dependency_name, "tool.execution")

    def test_missing_optional_dependency_degrades_readiness(self) -> None:
        registry = PortRegistry()
        resolved = registry.resolve(
            ModuleActivationPlan(
                module_name="tool",
                dependencies=(
                    ModuleDependency(
                        port_name="memory.context",
                        kind=DependencyKind.OPTIONAL_DEPENDENCY,
                        reason="memory-backed tools disabled",
                    ),
                ),
            )
        )

        self.assertEqual(resolved.dependencies, {})
        self.assertEqual(resolved.readiness.status, ReadinessStatus.DEGRADED)
        self.assertFalse(resolved.readiness.is_ready)
        self.assertEqual(len(resolved.readiness.issues), 1)
        issue = resolved.readiness.issues[0]
        self.assertEqual(issue.kind, DependencyKind.OPTIONAL_DEPENDENCY)
        self.assertEqual(issue.status, ReadinessStatus.DEGRADED)
        self.assertEqual(issue.message, "memory-backed tools disabled")

    def test_external_requirement_reports_setup_required(self) -> None:
        registry = PortRegistry()
        resolved = registry.resolve(
            ModuleActivationPlan(
                module_name="tool",
                dependencies=(
                    ModuleDependency(
                        port_name="access.openai-credential",
                        kind=DependencyKind.EXTERNAL_REQUIREMENT,
                    ),
                ),
            )
        )

        self.assertEqual(resolved.readiness.status, ReadinessStatus.SETUP_REQUIRED)
        issue = resolved.readiness.issues[0]
        self.assertEqual(issue.dependency_name, "access.openai-credential")
        self.assertEqual(issue.kind, DependencyKind.EXTERNAL_REQUIREMENT)
        self.assertEqual(issue.status, ReadinessStatus.SETUP_REQUIRED)

    def test_readiness_report_prefers_setup_required_over_degraded(self) -> None:
        registry = PortRegistry()
        resolved = registry.resolve(
            ModuleActivationPlan(
                module_name="tool",
                dependencies=(
                    ModuleDependency(
                        port_name="memory.context",
                        kind=DependencyKind.OPTIONAL_DEPENDENCY,
                    ),
                    ModuleDependency(
                        port_name="access.openai-credential",
                        kind=DependencyKind.EXTERNAL_REQUIREMENT,
                    ),
                ),
            )
        )

        self.assertEqual(resolved.readiness.status, ReadinessStatus.SETUP_REQUIRED)
        self.assertEqual(len(resolved.readiness.issues), 2)


if __name__ == "__main__":
    unittest.main()
