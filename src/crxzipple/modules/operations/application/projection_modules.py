from __future__ import annotations

from collections.abc import Iterable

OPERATIONS_PROJECTION_MODULES: tuple[str, ...] = (
    "orchestration",
    "tool",
    "browser",
    "llm",
    "access",
    "channels",
    "memory",
    "context_workspace",
    "skills",
    "events",
    "daemon",
)

_PROJECTION_MODULE_PRIORITY = {
    module: index for index, module in enumerate(OPERATIONS_PROJECTION_MODULES)
}

_EVENT_MODULE_TO_PROJECTION_MODULES: dict[str, tuple[str, ...]] = {
    "orchestration": ("orchestration",),
    "dispatch": ("orchestration",),
    "tool": ("tool",),
    "browser": ("browser", "daemon"),
    "llm": ("llm",),
    "access": ("access",),
    "channels": ("channels",),
    "channel": ("channels",),
    "memory": ("memory",),
    "context_workspace": ("context_workspace",),
    "context": ("context_workspace",),
    "skills": ("skills",),
    "skill": ("skills",),
    "events": ("events",),
    "event_relay": ("events",),
    "daemon": ("daemon", "browser"),
    "process": ("daemon", "browser"),
}


def projection_modules_for_observed_modules(modules: Iterable[str]) -> tuple[str, ...]:
    targets: set[str] = set()
    for module in modules:
        normalized = module.strip().lower()
        targets.update(_EVENT_MODULE_TO_PROJECTION_MODULES.get(normalized, ()))
    return order_projection_modules(targets)


def normalize_modules(modules: Iterable[str]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            module.strip().lower()
            for module in modules
            if isinstance(module, str) and module.strip()
        ),
    )


def order_projection_modules(modules: Iterable[str]) -> tuple[str, ...]:
    return tuple(
        sorted(
            normalize_modules(modules),
            key=lambda module: _PROJECTION_MODULE_PRIORITY.get(
                module,
                len(_PROJECTION_MODULE_PRIORITY),
            ),
        ),
    )
