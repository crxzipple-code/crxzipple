from __future__ import annotations

from crxzipple.modules.tool.infrastructure.package_catalog import (
    ToolPackageDiscoveryAdapter,
    tool_source_records_from_package_plans,
)
from crxzipple.modules.tool.infrastructure.tool_packages import load_tool_package_plan


def browser_package_plan():
    return load_tool_package_plan("tools/browser/tool.yaml")


def browser_source_records_from_package() -> tuple[object, ...]:
    return tool_source_records_from_package_plans((browser_package_plan(),))


def browser_function_catalog_candidates() -> tuple[object, ...]:
    source = browser_source_records_from_package()[0]
    return ToolPackageDiscoveryAdapter((browser_package_plan(),)).discover(
        source,
    ).candidates
