from __future__ import annotations

from types import SimpleNamespace

from crxzipple.modules.tool.infrastructure.adapters.daemon import (
    DaemonServiceToolRuntimeReadinessAdapter,
)


class _DaemonService:
    def __init__(
        self,
        *,
        proxy_mode: str = "access_binding",
        proxy_binding_id: str = "proxy-basic",
        proxy_credential_kind: str | None = None,
    ) -> None:
        self.proxy_mode = proxy_mode
        self.proxy_binding_id = proxy_binding_id
        self.proxy_credential_kind = proxy_credential_kind

    def list_service_specs(self, *, service_group: str | None = None):  # noqa: ANN201
        assert service_group == "browser"
        metadata = {
            "profile_name": "work",
            "proxy_mode": self.proxy_mode,
            "proxy_binding_id": self.proxy_binding_id,
        }
        if self.proxy_credential_kind is not None:
            metadata["proxy_credential_kind"] = self.proxy_credential_kind
        return (
            SimpleNamespace(
                key="host:browser:work",
                display_name="Managed Browser (work)",
                service_group="browser",
                role="host",
                start_policy="ensure",
                desired_replicas=1,
                metadata=metadata,
            ),
        )

    def list_instances(self, *, service_key: str):  # noqa: ANN201
        assert service_key == "host:browser:work"
        return ()


class _AccessReadiness:
    def to_payload(self):
        return {
            "ready": False,
            "status": "setup_needed",
            "reason": "environment variable 'BROWSER_PROXY_AUTH' is not configured.",
        }


class _AccessService:
    def __init__(self) -> None:
        self.checked: list[tuple[str, str | None]] = []

    def check_credential_binding(self, binding_id: str, *, expected_kind: str | None = None):
        self.checked.append((binding_id, expected_kind))
        return _AccessReadiness()


def test_daemon_group_browser_readiness_explains_proxy_credential_setup_needed() -> None:
    access = _AccessService()
    adapter = DaemonServiceToolRuntimeReadinessAdapter(
        _DaemonService(),
        access_service=access,
    )

    readiness = adapter.check_tool_runtime(
        SimpleNamespace(
            id="browser.snapshot",
            runtime_requirement_sets=(("browser-profile-runtime",),),
        ),
    )

    payload = readiness.to_payload()
    assert payload["ready"] is False
    assert payload["status"] == "setup_needed"
    check = payload["checks"][0]
    assert check["requirement"] == "browser-profile-runtime"
    assert "Browser proxy credential 'proxy-basic' is setup_needed" in check["reason"]
    assert check["metadata"]["proxy_readiness"][0]["binding_id"] == "proxy-basic"
    assert check["metadata"]["proxy_readiness"][0]["expected_kind"] == "basic"
    assert check["metadata"]["proxy_readiness"][0]["ready"] is False
    assert access.checked == [("proxy-basic", "basic")]


def test_browser_profile_runtime_is_ready_when_host_can_launch_on_demand() -> None:
    adapter = DaemonServiceToolRuntimeReadinessAdapter(
        _DaemonService(proxy_mode="none"),
    )

    readiness = adapter.check_tool_runtime(
        SimpleNamespace(
            id="browser.navigate",
            runtime_requirement_sets=(("browser-profile-runtime",),),
        ),
    )

    payload = readiness.to_payload()
    assert payload["ready"] is True
    assert payload["status"] == "ready"
    check = payload["checks"][0]
    assert check["requirement"] == "browser-profile-runtime"
    assert check["status"] == "launchable"
    assert check["ready"] is True


def test_daemon_group_browser_readiness_uses_proxy_credential_kind() -> None:
    access = _AccessService()
    adapter = DaemonServiceToolRuntimeReadinessAdapter(
        _DaemonService(
            proxy_binding_id="proxy-token",
            proxy_credential_kind="bearer",
        ),
        access_service=access,
    )

    readiness = adapter.check_tool_runtime(
        SimpleNamespace(
            id="browser.snapshot",
            runtime_requirement_sets=(("browser-profile-runtime",),),
        ),
    )

    payload = readiness.to_payload()
    check = payload["checks"][0]
    assert check["metadata"]["proxy_readiness"][0]["binding_id"] == "proxy-token"
    assert check["metadata"]["proxy_readiness"][0]["expected_kind"] == "bearer_token"
    assert access.checked == [("proxy-token", "bearer_token")]
