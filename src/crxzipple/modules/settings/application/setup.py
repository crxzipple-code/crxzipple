from __future__ import annotations

from crxzipple.modules.settings.application.service_bundle import (
    SettingsServices,
    create_in_memory_settings_services,
)
from crxzipple.modules.settings.application.setup_importer import (
    import_core_settings_resources,
)
from crxzipple.modules.settings.application.setup_resources import (
    SETTINGS_GOVERNANCE_RESOURCE_KINDS,
    collect_core_settings_resources,
)
from crxzipple.modules.settings.application.setup_results import (
    SettingsBootstrapImportResult,
)
from crxzipple.modules.settings.application.setup_seeder import (
    seed_core_settings_resources,
)


def create_bootstrap_settings_services(settings: object) -> SettingsServices:
    services = create_in_memory_settings_services()
    seed_core_settings_resources(settings, services=services)
    return services


__all__ = [
    "SETTINGS_GOVERNANCE_RESOURCE_KINDS",
    "SettingsBootstrapImportResult",
    "collect_core_settings_resources",
    "create_bootstrap_settings_services",
    "import_core_settings_resources",
    "seed_core_settings_resources",
]
