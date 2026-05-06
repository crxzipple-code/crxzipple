from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import hashlib

from crxzipple.modules.browser.domain import (
    BrowserExecutionPlan,
    BrowserValidationError,
)
from crxzipple.modules.daemon import (
    DaemonApplicationService,
    DaemonLease,
    DaemonNotFoundError,
    DaemonValidationError,
)


def host_daemon_enabled(
    *,
    plan: BrowserExecutionPlan,
) -> bool:
    return plan.capabilities.mode == "local-managed"


def host_daemon_service_key(*, profile_name: str) -> str:
    return f"host:browser:{profile_name.strip().lower()}"


def host_daemon_owner_id(
    *,
    profile_name: str,
    user_data_dir: str | None,
) -> str:
    normalized_profile = profile_name.strip().lower()
    normalized_user_data_dir = (user_data_dir or "").strip()
    if not normalized_user_data_dir:
        return normalized_profile
    digest = hashlib.sha1(normalized_user_data_dir.encode("utf-8")).hexdigest()[:8]
    return f"{normalized_profile}:{digest}"


@contextmanager
def host_daemon_lease(
    *,
    daemon_service: DaemonApplicationService,
    plan: BrowserExecutionPlan,
    user_data_dir: str | None,
    ttl_seconds: int = 60,
) -> Iterator[None]:
    if not host_daemon_enabled(plan=plan):
        yield
        return
    lease: DaemonLease | None = None
    try:
        lease = daemon_service.acquire_lease(
            service_key=host_daemon_service_key(profile_name=plan.profile.name),
            owner_kind="browser_profile",
            owner_id=host_daemon_owner_id(
                profile_name=plan.profile.name,
                user_data_dir=user_data_dir,
            ),
            ttl_seconds=ttl_seconds,
            metadata={
                "profile_name": plan.profile.name.strip().lower(),
                **(
                    {"user_data_dir": user_data_dir}
                    if isinstance(user_data_dir, str) and user_data_dir.strip()
                    else {}
                ),
            },
        )
    except (DaemonNotFoundError, DaemonValidationError) as exc:
        raise BrowserValidationError(str(exc)) from exc
    try:
        yield
    finally:
        if lease is not None:
            daemon_service.release_lease(lease.id)
