from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path
import shlex
from typing import Any

from crxzipple.modules.process.application import ProcessApplicationService
from crxzipple.modules.tool.application.result_envelope import (
    TOOL_RESULT_ENVELOPE_METADATA_KEY,
)
from crxzipple.modules.tool.domain import ToolRunResult
from crxzipple.modules.tool.infrastructure.cli_source_config import (
    CliPromotedFunctionConfig,
    CliToolSourceConfig,
)
from crxzipple.modules.tool.infrastructure.cli_source_config_values import (
    non_negative_int,
    optional_text,
    positive_int,
    required_text,
    text_tuple,
)
from crxzipple.modules.tool.infrastructure.cli_source_credentials import (
    resolve_credential_injection,
)
from crxzipple.modules.tool.infrastructure.cli_source_envelopes import (
    cli_process_result_envelope,
    cli_runtime_facts,
    process_continuation_payload,
    sanitized_argv,
)
from crxzipple.modules.tool.infrastructure.cli_source_process_observer import (
    start_cli_process_output_observer,
)
from crxzipple.modules.tool.infrastructure.cli_source_runtime_help import (
    run_cli_help,
)
from crxzipple.modules.tool.infrastructure.cli_source_runtime_output import (
    process_output_payload_for_display,
)
from crxzipple.shared.content_blocks import describe_content_for_text_fallback


class CliGuidedRuntime:
    def __init__(
        self,
        config: CliToolSourceConfig,
        *,
        process_service: ProcessApplicationService,
        credential_provider: Any | None = None,
        events_service: Any | None = None,
    ) -> None:
        self.config = config
        self.process_service = process_service
        self.credential_provider = credential_provider
        self.events_service = events_service
        self._process_redactions: dict[str, tuple[str, ...]] = {}

    def handler_for(self, action: str, *, metadata: Mapping[str, Any] | None = None):
        if action == "cli_promoted_execute":
            promoted_id = optional_text(
                (metadata or {}).get("promoted_function_id"),
            )
            if promoted_id is None:
                return None
            promoted = self.config.promoted_function(promoted_id)
            if promoted is None:
                return None
            return self.promoted_handler_for(promoted)
        return {
            "cli_help": self.cli_help,
            "cli_execute": self.cli_execute,
            "cli_read_output": self.cli_read_output,
            "cli_cancel": self.cli_cancel,
        }.get(action)

    def promoted_handler_for(self, promoted: CliPromotedFunctionConfig):
        async def handler(arguments: dict[str, Any]) -> ToolRunResult:
            return await self.cli_promoted_execute(promoted, arguments)

        return handler

    async def cli_help(self, arguments: dict[str, Any]) -> ToolRunResult:
        return await run_cli_help(
            self.config,
            arguments,
            credential_provider=self.credential_provider,
        )

    async def cli_execute(self, arguments: dict[str, Any]) -> ToolRunResult:
        subcommand = required_text(
            arguments.get("subcommand"),
            field_name="subcommand",
        )
        args = text_tuple(arguments.get("args"))
        argv = self.config.build_execute_argv(subcommand=subcommand, args=args)
        return await self._start_process(
            argv=argv,
            arguments=arguments,
            action="cli_execute",
            initial_output_limit=positive_int(
                arguments.get("initial_output_limit"),
                default=min(self.config.output_limit_bytes, 4000),
            ),
            process_metadata={},
        )

    async def cli_promoted_execute(
        self,
        promoted: CliPromotedFunctionConfig,
        arguments: dict[str, Any],
    ) -> ToolRunResult:
        argv = self.config.build_promoted_argv(promoted, arguments=arguments)
        initial_output_limit = positive_int(
            arguments.get("initial_output_limit"),
            default=(
                promoted.initial_output_limit
                or min(self.config.output_limit_bytes, 4000)
            ),
        )
        return await self._start_process(
            argv=argv,
            arguments=arguments,
            action="cli_promoted_execute",
            initial_output_limit=initial_output_limit,
            process_metadata={
                "promoted_function_id": promoted.function_id,
                "promoted_function_name": promoted.name,
            },
        )

    async def _start_process(
        self,
        *,
        argv: tuple[str, ...],
        arguments: Mapping[str, Any],
        action: str,
        initial_output_limit: int,
        process_metadata: Mapping[str, Any],
    ) -> ToolRunResult:
        command = shlex.join(argv)
        injection = resolve_credential_injection(
            self.config,
            credential_provider=self.credential_provider,
            action=action,
        )
        try:
            session = await asyncio.to_thread(
                self.process_service.start_command,
                command=command,
                shell=self.config.shell,
                working_directory=str(self.config.working_directory),
                session_key=optional_text(arguments.get("session_key")),
                env=injection.env,
                metadata={
                    "owner": "tool.cli_source",
                    "source_id": self.config.source_id,
                    "provider": self.config.provider_name,
                    "cli_action": action,
                    "argv": sanitized_argv(argv),
                    "credential_injections": injection.metadata,
                    **dict(process_metadata),
                },
            )
        except Exception:
            injection.cleanup()
            raise
        self._observe_process_output(
            process_id=session.id,
            session_key=session.session_key,
            cleanup_paths=injection.cleanup_paths,
            redactions=injection.redactions,
        )
        if injection.redactions:
            self._process_redactions[session.id] = injection.redactions
        output = await asyncio.to_thread(
            self.process_service.read_output,
            process_id=session.id,
            limit=min(initial_output_limit, self.config.output_limit_bytes),
        )
        details = process_output_payload_for_display(
            output,
            redactions=injection.redactions,
        ) | {
            "argv": sanitized_argv(argv),
            "working_directory": str(self.config.working_directory),
            "credential_injections": injection.metadata,
            "runtime_facts": cli_runtime_facts(
                self.config,
                action=action,
                argv=argv,
            ),
            "continuation": process_continuation_payload(
                output,
                default_limit=self.config.output_limit_bytes,
            ),
            **dict(process_metadata),
        }
        envelope = cli_process_result_envelope(
            details,
            source_id=self.config.source_id,
            provider_name=self.config.provider_name,
            action=action,
            output=output,
        )
        return ToolRunResult.text(
            describe_content_for_text_fallback(details),
            details=details,
            metadata={
                "source_id": self.config.source_id,
                "provider": self.config.provider_name,
                "cli_action": action,
                "process_id": session.id,
                TOOL_RESULT_ENVELOPE_METADATA_KEY: envelope.to_payload(),
                **dict(process_metadata),
            },
        )

    def _observe_process_output(
        self,
        *,
        process_id: str,
        session_key: str | None,
        cleanup_paths: tuple[Path, ...] = (),
        redactions: tuple[str, ...] = (),
    ) -> None:
        start_cli_process_output_observer(
            config=self.config,
            process_service=self.process_service,
            events_service=self.events_service,
            process_id=process_id,
            session_key=session_key,
            cleanup_paths=cleanup_paths,
            redactions=redactions,
        )

    async def cli_read_output(self, arguments: dict[str, Any]) -> ToolRunResult:
        process_id = required_text(arguments.get("process_id"), field_name="process_id")
        output = await asyncio.to_thread(
            self.process_service.read_output,
            process_id=process_id,
            stdout_offset=non_negative_int(arguments.get("stdout_offset")),
            stderr_offset=non_negative_int(arguments.get("stderr_offset")),
            limit=min(
                positive_int(arguments.get("limit"), default=4000),
                self.config.output_limit_bytes,
            ),
        )
        details = process_output_payload_for_display(
            output,
            redactions=self._process_redactions.get(process_id, ()),
        )
        details["runtime_facts"] = cli_runtime_facts(
            self.config,
            action="cli_read_output",
            argv=(),
        )
        details["continuation"] = process_continuation_payload(
            output,
            default_limit=self.config.output_limit_bytes,
        )
        envelope = cli_process_result_envelope(
            details,
            source_id=self.config.source_id,
            provider_name=self.config.provider_name,
            action="cli_read_output",
            output=output,
        )
        return ToolRunResult.text(
            describe_content_for_text_fallback(details),
            details=details,
            metadata={
                "source_id": self.config.source_id,
                "provider": self.config.provider_name,
                "cli_action": "cli_read_output",
                "process_id": process_id,
                TOOL_RESULT_ENVELOPE_METADATA_KEY: envelope.to_payload(),
            },
        )

    async def cli_cancel(self, arguments: dict[str, Any]) -> ToolRunResult:
        process_id = required_text(arguments.get("process_id"), field_name="process_id")
        session = await asyncio.to_thread(
            self.process_service.terminate_session,
            process_id=process_id,
        )
        details = {
            "process_id": session.id,
            "status": session.status.value,
            "exit_code": session.exit_code,
            "started_at": session.started_at.isoformat(),
            "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        }
        return ToolRunResult.text(
            describe_content_for_text_fallback(details),
            details=details,
            metadata={
                "source_id": self.config.source_id,
                "provider": self.config.provider_name,
                "cli_action": "cli_cancel",
                "process_id": process_id,
            },
        )

__all__ = ["CliGuidedRuntime"]
