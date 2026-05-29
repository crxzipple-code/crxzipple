"""Application container facade for assembled registries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from crxzipple.app.keys import AppKey
from crxzipple.app.lifecycle import run_runtime_cleanup_tasks
from crxzipple.app.plan import AssemblyPlan, AssemblyTarget
from crxzipple.app.registry import ApplicationRegistry, build_application_registry


@dataclass(frozen=True, slots=True)
class AppContainer:
    """Thin runtime lookup facade over an assembled application registry."""

    target: AssemblyTarget
    registry: ApplicationRegistry

    def has(self, key: str) -> bool:
        return self.registry.has(key)

    def get(self, key: str, default: object | None = None) -> object | None:
        return self.registry.get(key, default)

    def require(self, key: str) -> object:
        return self.registry.require(key)

    def snapshot(self) -> Mapping[str, object]:
        return self.registry.snapshot()

    def close(self) -> None:
        """Release process-level resources owned by assembled applications."""

        run_runtime_cleanup_tasks(
            self.registry.get(AppKey.RUNTIME_CLEANUP_TASKS, ()) or (),
        )


def build_app_container(
    plan: AssemblyPlan,
    *,
    target: AssemblyTarget | str,
    overrides: Mapping[str, object] | None = None,
) -> AppContainer:
    resolved_target = AssemblyTarget.parse(target)
    return AppContainer(
        target=resolved_target,
        registry=build_application_registry(
            plan,
            target=resolved_target,
            overrides=overrides,
        ),
    )


__all__ = ["AppContainer", "build_app_container"]
