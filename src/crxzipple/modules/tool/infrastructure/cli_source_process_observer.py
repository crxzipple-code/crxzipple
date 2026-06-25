from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Thread
import time
from typing import Any, Protocol

from crxzipple.core.logger import get_logger
from crxzipple.modules.process.application import ProcessApplicationService
from crxzipple.modules.process.domain import ProcessOutputWindow
from crxzipple.modules.tool.infrastructure.cli_source_credentials import (
    CliCredentialInjection,
)
from crxzipple.modules.tool.infrastructure.cli_source_redaction import (
    redact_cli_output,
)
from crxzipple.shared.domain.events import Event
from crxzipple.shared.event_contracts import TOOL_CLI_EVENT_NAMES


logger = get_logger(__name__)
TOOL_CLI_OUTPUT_OBSERVED_EVENT = TOOL_CLI_EVENT_NAMES[0]
CLI_OUTPUT_POLL_INTERVAL_SECONDS = 0.1
CLI_OUTPUT_EVENT_CHUNK_BYTES = 4000


class CliProcessObserverConfig(Protocol):
    source_id: str
    provider_name: str
    output_limit_bytes: int


def start_cli_process_output_observer(
    *,
    config: CliProcessObserverConfig,
    process_service: ProcessApplicationService,
    events_service: Any | None,
    process_id: str,
    session_key: str | None,
    cleanup_paths: tuple[Path, ...] = (),
    redactions: tuple[str, ...] = (),
) -> None:
    if events_service is None and not cleanup_paths:
        return
    _CliProcessOutputObserver(
        config=config,
        process_service=process_service,
        events_service=events_service,
        process_id=process_id,
        session_key=session_key,
        cleanup_paths=cleanup_paths,
        redactions=redactions,
    ).start()


@dataclass(slots=True)
class _CliProcessOutputObserver:
    config: CliProcessObserverConfig
    process_service: ProcessApplicationService
    events_service: Any | None
    process_id: str
    session_key: str | None
    cleanup_paths: tuple[Path, ...] = ()
    redactions: tuple[str, ...] = ()
    poll_interval_seconds: float = CLI_OUTPUT_POLL_INTERVAL_SECONDS

    def start(self) -> None:
        thread = Thread(
            target=self._run,
            name=f"tool-cli-output-{self.process_id[:8]}",
            daemon=True,
        )
        thread.start()

    def _run(self) -> None:
        stdout_offset = 0
        stderr_offset = 0
        while True:
            try:
                output = self.process_service.read_output(
                    process_id=self.process_id,
                    stdout_offset=stdout_offset,
                    stderr_offset=stderr_offset,
                    limit=min(
                        self.config.output_limit_bytes,
                        CLI_OUTPUT_EVENT_CHUNK_BYTES,
                    ),
                )
            except Exception:
                logger.exception(
                    "failed to observe CLI process output",
                    extra={
                        "process_id": self.process_id,
                        "source_id": self.config.source_id,
                    },
                )
                self._cleanup()
                return

            self._publish_output(output, stream="stdout")
            self._publish_output(output, stream="stderr")
            stdout_offset = output.next_stdout_offset
            stderr_offset = output.next_stderr_offset
            if output.status.value != "running":
                self._publish_status(output)
                self._cleanup()
                return
            time.sleep(max(float(self.poll_interval_seconds), 0.02))

    def _publish_output(
        self,
        output: ProcessOutputWindow,
        *,
        stream: str,
    ) -> None:
        if stream == "stdout":
            text = output.stdout
            offset = output.stdout_offset
            next_offset = output.next_stdout_offset
        else:
            text = output.stderr
            offset = output.stderr_offset
            next_offset = output.next_stderr_offset
        if not text:
            return
        self._publish(
            stream=stream,
            text=text,
            offset=offset,
            next_offset=next_offset,
            output=output,
        )

    def _publish_status(self, output: ProcessOutputWindow) -> None:
        self._publish(
            stream="status",
            text="",
            offset=0,
            next_offset=0,
            output=output,
        )

    def _publish(
        self,
        *,
        stream: str,
        text: str,
        offset: int,
        next_offset: int,
        output: ProcessOutputWindow,
    ) -> None:
        if self.events_service is None:
            return
        event_text = redact_cli_output(text, self.redactions)
        try:
            self.events_service.publish(
                Event(
                    name=TOOL_CLI_OUTPUT_OBSERVED_EVENT,
                    kind="live",
                    ordering_key=self.process_id,
                    payload={
                        "event_name": TOOL_CLI_OUTPUT_OBSERVED_EVENT,
                        "source_id": self.config.source_id,
                        "provider": self.config.provider_name,
                        "process_id": self.process_id,
                        "session_key": self.session_key,
                        "stream": stream,
                        "offset": offset,
                        "next_offset": next_offset,
                        "text": event_text,
                        "text_length": len(event_text),
                        "status": output.status.value,
                        "exit_code": output.exit_code,
                        "level": _cli_output_event_level(stream, output),
                        "summary": _cli_output_event_summary(
                            stream,
                            event_text,
                            output,
                        ),
                        "display_label": _cli_output_event_label(stream),
                        "display_summary": _cli_output_event_summary(
                            stream,
                            event_text,
                            output,
                        ),
                        "display_tone": _cli_output_event_tone(stream, output),
                        "entity_type": "tool_cli_process",
                        "entity_id": self.process_id,
                    },
                ),
            )
        except Exception:
            logger.exception(
                "failed to publish CLI process output event",
                extra={
                    "process_id": self.process_id,
                    "source_id": self.config.source_id,
                    "stream": stream,
                },
            )

    def _cleanup(self) -> None:
        CliCredentialInjection(
            env={},
            cleanup_paths=self.cleanup_paths,
            metadata=(),
        ).cleanup()


def _cli_output_event_label(stream: str) -> str:
    if stream == "status":
        return "CLI process status"
    return f"CLI {stream}"


def _cli_output_event_summary(
    stream: str,
    text: str,
    output: ProcessOutputWindow,
) -> str:
    if stream == "status":
        if output.exit_code is None:
            return f"CLI process {output.process_id} is {output.status.value}."
        return (
            f"CLI process {output.process_id} ended with exit code "
            f"{output.exit_code}."
        )
    preview = text.strip().replace("\n", " ")
    if len(preview) > 120:
        preview = f"{preview[:117]}..."
    return preview or f"Observed {len(text)} characters on {stream}."


def _cli_output_event_level(
    stream: str,
    output: ProcessOutputWindow,
) -> str:
    if stream == "stderr":
        return "warning"
    if output.exit_code not in {None, 0}:
        return "error"
    return "info"


def _cli_output_event_tone(
    stream: str,
    output: ProcessOutputWindow,
) -> str:
    level = _cli_output_event_level(stream, output)
    if level == "error":
        return "danger"
    if level == "warning":
        return "warning"
    if stream == "status" and output.exit_code == 0:
        return "success"
    return "info"


__all__ = ["start_cli_process_output_observer"]
