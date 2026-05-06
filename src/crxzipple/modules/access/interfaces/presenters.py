from __future__ import annotations

from crxzipple.modules.access.domain import (
    AccessRequirementReadiness,
    AccessSetupFlow,
)


def present_readiness(
    readiness: AccessRequirementReadiness,
    *,
    target_type: str,
) -> dict[str, object]:
    payload = readiness.to_payload()
    payload["target_type"] = target_type
    return payload


def present_setup_flow(flow: AccessSetupFlow) -> dict[str, object]:
    return flow.to_payload()

