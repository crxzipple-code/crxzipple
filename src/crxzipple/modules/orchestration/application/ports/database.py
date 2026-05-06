from __future__ import annotations

from typing import Protocol


class TransientDatabaseErrorClassifier(Protocol):
    def __call__(self, exc: BaseException) -> bool:
        ...


def is_transient_database_lock_error(exc: BaseException) -> bool:
    fragments = (str(exc), str(getattr(exc, "orig", "")))
    return any("database is locked" in fragment.lower() for fragment in fragments)
