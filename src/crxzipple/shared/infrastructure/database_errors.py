from __future__ import annotations

from sqlalchemy.exc import OperationalError


def is_transient_database_lock_error(exc: BaseException) -> bool:
    if not isinstance(exc, OperationalError):
        return False
    fragments = (str(exc), str(getattr(exc, "orig", "")))
    return any("database is locked" in fragment.lower() for fragment in fragments)
