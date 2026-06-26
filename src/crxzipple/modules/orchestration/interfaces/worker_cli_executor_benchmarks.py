from __future__ import annotations

import typer


def _execute_executor_runtime_benchmark(**kwargs: object) -> None:
    from crxzipple.modules.orchestration.interfaces.worker_cli_benchmark import (
        _execute_executor_runtime_benchmark as execute_benchmark,
    )

    execute_benchmark(**kwargs)


def _execute_tool_io_benchmark(**kwargs: object) -> None:
    from crxzipple.modules.orchestration.interfaces.worker_cli_benchmark import (
        _execute_tool_io_benchmark as execute_benchmark,
    )

    execute_benchmark(**kwargs)


def _execute_daemon_runtime_benchmark(**kwargs: object) -> None:
    from crxzipple.modules.orchestration.interfaces.worker_cli_benchmark import (
        _execute_daemon_runtime_benchmark as execute_benchmark,
    )

    execute_benchmark(**kwargs)


def register_executor_benchmark_commands(app: typer.Typer) -> None:
    @app.command("benchmark-runtime")
    def benchmark_runtime(
        agent_id: str = typer.Argument(..., help="Agent profile identifier."),
        llm_id: str = typer.Argument(..., help="LLM profile identifier."),
        content: str = typer.Argument(..., help="Prompt content for each benchmark run."),
        run_count: int = typer.Option(
            8,
            "--run-count",
            min=1,
            help="Number of orchestration runs to create and process.",
        ),
        run_id_prefix: str | None = typer.Option(
            None,
            "--run-id-prefix",
            help="Optional deterministic run id prefix.",
        ),
        source: str = typer.Option(
            "cli",
            "--source",
            help="Inbound instruction source.",
        ),
        channel: str | None = typer.Option(
            "benchmark",
            "--channel",
            help="Session route channel.",
        ),
        chat_type: str = typer.Option(
            "direct",
            "--chat-type",
            help="Session route chat type.",
        ),
        main_key: str = typer.Option(
            "benchmark",
            "--main-key",
            help="Base session main key used for benchmark lane construction.",
        ),
        unique_lanes: bool = typer.Option(
            True,
            "--unique-lanes/--same-lane",
            help="Use one session lane per run, or force all runs through one lane.",
        ),
        queue_policy: str | None = typer.Option(
            None,
            "--queue-policy",
            help="Queue policy for created runs.",
        ),
        priority: int = typer.Option(
            100,
            "--priority",
            min=0,
            help="Run priority.",
        ),
        max_steps: int = typer.Option(
            99,
            "--max-steps",
            min=1,
            help="Maximum orchestration steps per run.",
        ),
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Stable orchestration executor identifier.",
        ),
        scheduler_worker_id: str | None = typer.Option(
            None,
            "--scheduler-worker-id",
            help="Stable orchestration scheduler identifier.",
        ),
        max_concurrent_assignments: int = typer.Option(
            4,
            "--max-concurrent-assignments",
            "--max-inflight-assignments",
            min=1,
            help="Maximum assigned runs this executor advances concurrently.",
        ),
        poll_interval_seconds: float = typer.Option(
            0.05,
            "--poll-interval-seconds",
            min=0.01,
            help="Executor idle wait time between queue polls.",
        ),
        scheduler_poll_interval_seconds: float = typer.Option(
            0.05,
            "--scheduler-poll-interval-seconds",
            min=0.01,
            help="Scheduler assignment wait time between polls.",
        ),
        max_idle_cycles: int | None = typer.Option(
            20,
            "--max-idle-cycles",
            min=1,
            help="Executor idle cycle limit before exiting.",
        ),
        allow_shared_executors: bool = typer.Option(
            False,
            "--allow-shared-executors/--require-exclusive-executor",
            help="Allow scheduler assignments to be spread across online executors.",
        ),
    ) -> None:
        _execute_executor_runtime_benchmark(
            agent_id=agent_id,
            llm_id=llm_id,
            content=content,
            run_count=run_count,
            run_id_prefix=run_id_prefix,
            source=source,
            channel=channel,
            chat_type=chat_type,
            main_key=main_key,
            unique_lanes=unique_lanes,
            queue_policy=queue_policy,
            priority=priority,
            max_steps=max_steps,
            worker_id=worker_id,
            scheduler_worker_id=scheduler_worker_id,
            max_concurrent_assignments=max_concurrent_assignments,
            poll_interval_seconds=poll_interval_seconds,
            scheduler_poll_interval_seconds=scheduler_poll_interval_seconds,
            max_idle_cycles=max_idle_cycles,
            allow_shared_executors=allow_shared_executors,
        )

    @app.command("benchmark-tool-io")
    def benchmark_tool_io(
        agent_id: str = typer.Option(
            "assistant",
            "--agent-id",
            help="Agent profile identifier to use, created if missing.",
        ),
        run_count: int = typer.Option(
            4,
            "--run-count",
            min=1,
            help="Number of orchestration runs to create and process.",
        ),
        tool_calls_per_run: int = typer.Option(
            2,
            "--tool-calls-per-run",
            min=1,
            help="Synthetic inline IO tool calls emitted by each run's first LLM step.",
        ),
        tool_sleep_seconds: float = typer.Option(
            0.2,
            "--tool-sleep-seconds",
            min=0.0,
            help="Async sleep duration for each synthetic tool call.",
        ),
        llm_latency_seconds: float = typer.Option(
            0.0,
            "--llm-latency-seconds",
            min=0.0,
            help="Optional synthetic LLM latency per invocation.",
        ),
        run_id_prefix: str | None = typer.Option(
            None,
            "--run-id-prefix",
            help="Optional deterministic run id prefix.",
        ),
        source: str = typer.Option(
            "benchmark",
            "--source",
            help="Inbound instruction source.",
        ),
        channel: str | None = typer.Option(
            "benchmark",
            "--channel",
            help="Session route channel.",
        ),
        chat_type: str = typer.Option(
            "direct",
            "--chat-type",
            help="Session route chat type.",
        ),
        main_key: str = typer.Option(
            "tool-io-benchmark",
            "--main-key",
            help="Base session main key used for benchmark lane construction.",
        ),
        unique_lanes: bool = typer.Option(
            True,
            "--unique-lanes/--same-lane",
            help="Use one session lane per run, or force all runs through one lane.",
        ),
        queue_policy: str | None = typer.Option(
            None,
            "--queue-policy",
            help="Queue policy for created runs.",
        ),
        priority: int = typer.Option(
            100,
            "--priority",
            min=0,
            help="Run priority.",
        ),
        max_steps: int = typer.Option(
            8,
            "--max-steps",
            min=2,
            help="Maximum orchestration steps per run.",
        ),
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Stable orchestration executor identifier.",
        ),
        scheduler_worker_id: str | None = typer.Option(
            None,
            "--scheduler-worker-id",
            help="Stable orchestration scheduler identifier.",
        ),
        max_concurrent_assignments: int = typer.Option(
            4,
            "--max-concurrent-assignments",
            "--max-inflight-assignments",
            min=1,
            help="Maximum assigned runs this executor advances concurrently.",
        ),
        poll_interval_seconds: float = typer.Option(
            0.02,
            "--poll-interval-seconds",
            min=0.01,
            help="Executor idle wait time between queue polls.",
        ),
        scheduler_poll_interval_seconds: float = typer.Option(
            0.02,
            "--scheduler-poll-interval-seconds",
            min=0.01,
            help="Scheduler assignment wait time between polls.",
        ),
        max_idle_cycles: int | None = typer.Option(
            20,
            "--max-idle-cycles",
            min=1,
            help="Executor idle cycle limit before exiting.",
        ),
        allow_shared_executors: bool = typer.Option(
            False,
            "--allow-shared-executors/--require-exclusive-executor",
            help=(
                "Allow other online executors. Unsafe for this synthetic benchmark "
                "because the synthetic runtime exists only in this process."
            ),
        ),
    ) -> None:
        _execute_tool_io_benchmark(
            agent_id=agent_id,
            run_count=run_count,
            tool_calls_per_run=tool_calls_per_run,
            tool_sleep_seconds=tool_sleep_seconds,
            llm_latency_seconds=llm_latency_seconds,
            run_id_prefix=run_id_prefix,
            source=source,
            channel=channel,
            chat_type=chat_type,
            main_key=main_key,
            unique_lanes=unique_lanes,
            queue_policy=queue_policy,
            priority=priority,
            max_steps=max_steps,
            worker_id=worker_id,
            scheduler_worker_id=scheduler_worker_id,
            max_concurrent_assignments=max_concurrent_assignments,
            poll_interval_seconds=poll_interval_seconds,
            scheduler_poll_interval_seconds=scheduler_poll_interval_seconds,
            max_idle_cycles=max_idle_cycles,
            allow_shared_executors=allow_shared_executors,
        )

    @app.command("benchmark-daemon-runtime")
    def benchmark_daemon_runtime(
        agent_id: str = typer.Argument(..., help="Agent profile identifier."),
        llm_id: str = typer.Argument(..., help="LLM profile identifier."),
        content: str = typer.Argument(..., help="Prompt content for each benchmark run."),
        run_count: int = typer.Option(
            8,
            "--run-count",
            min=1,
            help="Number of orchestration runs to create and wait for.",
        ),
        run_id_prefix: str | None = typer.Option(
            None,
            "--run-id-prefix",
            help="Optional deterministic run id prefix.",
        ),
        source: str = typer.Option(
            "cli",
            "--source",
            help="Inbound instruction source.",
        ),
        channel: str | None = typer.Option(
            "daemon-benchmark",
            "--channel",
            help="Session route channel.",
        ),
        chat_type: str = typer.Option(
            "direct",
            "--chat-type",
            help="Session route chat type.",
        ),
        main_key: str = typer.Option(
            "daemon-benchmark",
            "--main-key",
            help="Base session main key used for benchmark lane construction.",
        ),
        unique_lanes: bool = typer.Option(
            True,
            "--unique-lanes/--same-lane",
            help="Use one session lane per run, or force all runs through one lane.",
        ),
        queue_policy: str | None = typer.Option(
            None,
            "--queue-policy",
            help="Queue policy for created runs.",
        ),
        priority: int = typer.Option(
            100,
            "--priority",
            min=0,
            help="Run priority.",
        ),
        max_steps: int = typer.Option(
            99,
            "--max-steps",
            min=1,
            help="Maximum orchestration steps per run.",
        ),
        timeout_seconds: float = typer.Option(
            120.0,
            "--timeout-seconds",
            min=0.1,
            help="Maximum time to wait for daemon-processed runs to reach terminal state.",
        ),
        poll_interval_seconds: float = typer.Option(
            0.25,
            "--poll-interval-seconds",
            min=0.01,
            help="Run status polling interval while daemon runtimes process work.",
        ),
        require_ready_daemons: bool = typer.Option(
            True,
            "--require-ready-daemons/--allow-missing-daemons",
            help="Require scheduler and executor daemon services to be ready before creating runs.",
        ),
        allow_shared_runtime: bool = typer.Option(
            False,
            "--allow-shared-runtime/--require-isolated-queue",
            help="Allow benchmark runs to share the orchestration queue with existing queued runs.",
        ),
    ) -> None:
        _execute_daemon_runtime_benchmark(
            agent_id=agent_id,
            llm_id=llm_id,
            content=content,
            run_count=run_count,
            run_id_prefix=run_id_prefix,
            source=source,
            channel=channel,
            chat_type=chat_type,
            main_key=main_key,
            unique_lanes=unique_lanes,
            queue_policy=queue_policy,
            priority=priority,
            max_steps=max_steps,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            require_ready_daemons=require_ready_daemons,
            allow_shared_runtime=allow_shared_runtime,
        )
