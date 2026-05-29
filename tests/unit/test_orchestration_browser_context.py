from __future__ import annotations

from types import SimpleNamespace
import unittest

from crxzipple.app.assembly.orchestration import _run_context_provider_factory


class _AgentService:
    def get_profile(self, profile_id: str):  # noqa: ANN201
        if profile_id != "assistant":
            raise KeyError(profile_id)
        return SimpleNamespace(
            runtime_preferences=SimpleNamespace(
                attrs={"default_browser_profile": "user"},
            ),
        )


class _SessionService:
    def get_session(self, session_key: str):  # noqa: ANN201
        del session_key
        return None


class _MemoryPort:
    def resolve_access_plan(self, context):  # noqa: ANN001, ANN201
        del context
        return object()


class OrchestrationBrowserContextTestCase(unittest.TestCase):
    def test_run_context_includes_agent_default_browser_profile(self) -> None:
        provider = _run_context_provider_factory(
            agent_service=_AgentService(),
            session_service=_SessionService(),
            memory_port=_MemoryPort(),
        )
        run = SimpleNamespace(
            id="run-browser-context",
            agent_id="assistant",
            active_session_id="session-1",
            metadata={},
        )

        attrs = provider(run)

        self.assertEqual(attrs["agent_default_browser_profile"], "user")
        self.assertIn("memory_context", attrs["available_scopes"])


if __name__ == "__main__":
    unittest.main()
