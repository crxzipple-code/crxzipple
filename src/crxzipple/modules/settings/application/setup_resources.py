from __future__ import annotations

from crxzipple.modules.settings.application.bootstrap import BootstrapSettingsResource
from crxzipple.modules.settings.application.setup_access_resources import (
    access_config_resources,
)
from crxzipple.modules.settings.application.setup_core_resources import (
    core_config_resources,
)


SETTINGS_GOVERNANCE_RESOURCE_KINDS = (
    "agent-profiles",
    "llm-profiles",
    "tool-catalog",
    "skill-catalog",
    "memory-config",
    "access-assets",
    "channel-profiles",
    "event-registry",
    "runtime-defaults",
    "environment",
    "audit-logs",
    "backup-restore",
)


def collect_core_settings_resources(settings: object) -> tuple[BootstrapSettingsResource, ...]:
    seeds: list[BootstrapSettingsResource] = []
    seeds.extend(core_config_resources(settings))
    seeds.extend(access_config_resources(settings))
    return tuple(seeds)
