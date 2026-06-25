from __future__ import annotations

from threading import Event

from crxzipple.interfaces.cli.context import AppKey
from crxzipple.modules.browser.infrastructure import BrowserHostProcessRunner

from .cli_helpers import _system_config


def _run_host_loop(
    container,  # noqa: ANN001
    *,
    profile_name: str,
    poll_interval_seconds: float,
    max_cycles: int | None = None,
    stop_event: Event | None = None,
) -> int:
    system_config = _system_config(container)
    browser = container.require(AppKey.BROWSER_INFRASTRUCTURE)
    resolved = browser.profile_resolver.resolve(
        system=system_config,
        profile_name=profile_name,
    )
    capabilities = browser.capabilities_resolver.resolve(profile=resolved)
    runner = BrowserHostProcessRunner(
        daemon_service=container.require(AppKey.DAEMON_SERVICE),
        system=system_config,
        profile=resolved,
        capabilities=capabilities,
        profiles_root=browser.state_root.profiles_dir,
        credential_provider=container.require(AppKey.ACCESS_SERVICE),
        proxy_egress_check_url=getattr(
            container.require(AppKey.CORE_SETTINGS),
            "browser_proxy_egress_check_url",
            None,
        ),
    )
    completed_cycles = 0
    stopper = stop_event or Event()
    try:
        runner.start()
        while not stopper.is_set():
            runner.healthcheck()
            completed_cycles += 1
            if max_cycles is not None and completed_cycles >= max_cycles:
                break
            stopper.wait(poll_interval_seconds)
        return completed_cycles
    finally:
        runner.close()
