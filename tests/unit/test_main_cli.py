from __future__ import annotations

from types import SimpleNamespace

from crxzipple.interfaces.runtime_container import AppKey
from crxzipple.modules.agent.domain import AgentLlmRoutingPolicy, AgentProfile
from crxzipple.modules.orchestration.domain import (
    InboundInstruction,
    OrchestrationRun,
    OrchestrationRunStage,
    OrchestrationRunStatus,
)
from tests.unit.cli_test_support import *


class _FakeAgentService:
    def __init__(self) -> None:
        self.profile = AgentProfile(
            id="crxzipple",
            name="crxzipple",
            llm_routing_policy=AgentLlmRoutingPolicy(default_llm_id="local-chat"),
        )

    def get_profile(self, agent_id: str) -> AgentProfile:
        if agent_id != self.profile.id:
            raise AssertionError(f"unexpected agent id: {agent_id}")
        return self.profile

    def list_profiles(self) -> tuple[AgentProfile, ...]:
        return (self.profile,)


class _FakeDaemonManager:
    def __init__(self, *, ready: bool) -> None:
        self.ready = ready

    def resolve_reconcile_service_keys(
        self,
        *,
        service_set_keys: tuple[str, ...],
        include_eager: bool,
    ) -> tuple[str, ...]:
        assert service_set_keys == ("orchestration-runtime",)
        assert include_eager is False
        return ("worker:orchestration-scheduler", "worker:orchestration")

    def healthcheck_service(self, service_key: str) -> tuple[SimpleNamespace, ...]:
        if not self.ready:
            return ()
        return (SimpleNamespace(service_key=service_key, status="ready"),)


class _FakeRuntimeContainer:
    def __init__(self, *, runtime_ready: bool = True) -> None:
        self.services = {
            AppKey.AGENT_SERVICE: _FakeAgentService(),
            AppKey.DAEMON_MANAGER: _FakeDaemonManager(ready=runtime_ready),
            AppKey.ORCHESTRATION_SUBMISSION_SERVICE: object(),
            AppKey.ORCHESTRATION_RUN_QUERY_SERVICE: object(),
            AppKey.EVENTS_SERVICE: object(),
        }

    def require(self, key: AppKey):  # noqa: ANN201
        return self.services[key]


def _completed_run(*, output_text: str) -> OrchestrationRun:
    return OrchestrationRun(
        id="run-cli-turn",
        inbound_instruction=InboundInstruction(source="cli", content="hello"),
        status=OrchestrationRunStatus.COMPLETED,
        stage=OrchestrationRunStage.COMPLETED,
        active_session_id="session-cli",
        agent_id="crxzipple",
        lane_key="session:agent:crxzipple:main",
        current_step=1,
        result_payload={"output_text": output_text},
        metadata={"session_key": "agent:crxzipple:main"},
    )


class MainCliTurnTestCase(CliModuleTestCase):
    def _run_with_fake_runtime(
        self,
        args: list[str],
        *,
        input_text: str | None = None,
        runtime_ready: bool = True,
    ):
        calls: list[dict[str, object]] = []

        def _submit_and_wait(
            scheduler_service,  # noqa: ANN001
            run_lookup,  # noqa: ANN001
            events_service,  # noqa: ANN001
            *,
            content,  # noqa: ANN001
            options,  # noqa: ANN001
        ) -> OrchestrationRun:
            calls.append(
                {
                    "scheduler_service": scheduler_service,
                    "run_lookup": run_lookup,
                    "events_service": events_service,
                    "content": content,
                    "options": options,
                },
            )
            return _completed_run(output_text="hello from sample llm")

        with patch(
            "crxzipple.interfaces.cli.crxzipple.ensure_runtime_container",
            return_value=_FakeRuntimeContainer(runtime_ready=runtime_ready),
        ), patch(
            "crxzipple.interfaces.cli.crxzipple.submit_and_wait_for_turn",
            side_effect=_submit_and_wait,
        ):
            result = self.runner.invoke(
                app,
                args,
                env=self.env,
                input=input_text,
            )
        return result, calls

    def test_crxzipple_ask_completes_a_turn_in_one_command(self) -> None:
        ask_result, calls = self._run_with_fake_runtime(
            [
                "ask",
                "hello",
                "--agent",
                "crxzipple",
            ],
        )

        self.assertEqual(ask_result.exit_code, 0)
        self.assertEqual(ask_result.stdout.strip(), "hello from sample llm")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["content"], "hello")
        options = calls[0]["options"]
        self.assertEqual(options.agent_id, "crxzipple")
        self.assertEqual(options.llm_id, "local-chat")

    def test_crxzipple_ask_requires_orchestration_runtime(self) -> None:
        ask_result, calls = self._run_with_fake_runtime(
            [
                "ask",
                "hello",
                "--agent",
                "crxzipple",
            ],
            runtime_ready=False,
        )

        self.assertEqual(ask_result.exit_code, 1)
        self.assertIn(
            "Orchestration runtime is not running",
            ask_result.stderr or ask_result.output,
        )
        self.assertEqual(calls, [])

    def test_crxzipple_chat_completes_a_turn_and_exits(self) -> None:
        chat_result, calls = self._run_with_fake_runtime(
            [
                "chat",
                "--agent",
                "crxzipple",
            ],
            input_text="hello\n/exit\n",
        )

        self.assertEqual(chat_result.exit_code, 0)
        self.assertIn("Chatting with crxzipple. Type /exit to quit.", chat_result.stdout)
        self.assertIn("hello from sample llm", chat_result.stdout)
        self.assertEqual([call["content"] for call in calls], ["hello"])


if __name__ == "__main__":
    unittest.main()
