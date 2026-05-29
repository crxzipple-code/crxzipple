"""Runtime lifecycle primitives."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from crxzipple.core.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RuntimeCleanupTask:
    """One ordered process-resource cleanup task."""

    key: str
    order: int
    callback: Callable[[], None]


@dataclass(frozen=True, slots=True)
class RuntimeCleanupFailure:
    """Failure captured while running a cleanup task."""

    key: str
    order: int
    error: BaseException


class RuntimeCleanupError(RuntimeError):
    """Raised after all cleanup tasks have run when any task failed."""

    def __init__(self, failures: tuple[RuntimeCleanupFailure, ...]) -> None:
        self.failures = failures
        details = ", ".join(
            f"{failure.key}: {type(failure.error).__name__}"
            for failure in failures[:5]
        )
        suffix = "" if len(failures) <= 5 else f", +{len(failures) - 5} more"
        super().__init__(
            f"runtime cleanup failed for {len(failures)} task(s): {details}{suffix}"
        )


def run_runtime_cleanup_tasks(
    tasks: Iterable[RuntimeCleanupTask],
) -> tuple[RuntimeCleanupFailure, ...]:
    """Run cleanup tasks in order, isolating failures until all have run."""

    failures: list[RuntimeCleanupFailure] = []
    for task in sorted(tuple(tasks), key=lambda item: item.order):
        try:
            task.callback()
        except Exception as exc:
            failures.append(
                RuntimeCleanupFailure(
                    key=task.key,
                    order=task.order,
                    error=exc,
                ),
            )
            logger.exception(
                "runtime cleanup task failed",
                extra={
                    "cleanup_key": task.key,
                    "cleanup_order": task.order,
                },
            )
    if failures:
        raise RuntimeCleanupError(tuple(failures))
    return ()


__all__ = [
    "RuntimeCleanupError",
    "RuntimeCleanupFailure",
    "RuntimeCleanupTask",
    "run_runtime_cleanup_tasks",
]
