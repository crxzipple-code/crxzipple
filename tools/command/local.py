from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from crxzipple.modules.process import (
    ProcessApplicationService,
    ProcessNotFoundError,
    ProcessSession,
)
from crxzipple.modules.tool.application.result_envelope import (
    TOOL_RESULT_ENVELOPE_METADATA_KEY,
    TOOL_RESULT_RAW_OUTPUT_BLOCKS_METADATA_KEY,
    ToolResultEnvelope,
)
from crxzipple.modules.tool.domain import ToolExecutionContext, ToolRunResult
from tools.command.command_exec import (
    DEFAULT_WORKSPACE_EXEC_TIMEOUT_SECONDS,
    WorkspaceCommandExecution,
    execute_prepared_workspace_command,
    prepare_workspace_command,
)
from tools.workspace.fs_safe import resolve_workspace_root


WORKSPACE_EXEC_TOOL_ID = "exec"
PROCESS_TOOL_ID = "process"
_SESSION_KEY_ATTR = "session_key"
_WORKSPACE_DIR_ATTR = "workspace_dir"


class WorkspaceToolWorkspaceResolver(Protocol):
    def resolve(self, execution_context: ToolExecutionContext | None) -> str | None:
        ...


@dataclass(frozen=True, slots=True)
class SessionBoundWorkspaceResolver:
    session_workspace_lookup: Callable[[str], str | None]
    allow_execution_context_fallback: bool = True

    def resolve(self, execution_context: ToolExecutionContext | None) -> str | None:
        if execution_context is None:
            return None
        session_key = execution_context.get_str(_SESSION_KEY_ATTR)
        if session_key is not None:
            return self.session_workspace_lookup(session_key)
        if not self.allow_execution_context_fallback:
            return None
        return execution_context.get_str(_WORKSPACE_DIR_ATTR)


@dataclass(frozen=True, slots=True)
class CommandToolDeps:
    session_workspace_lookup: Callable[[str], str | None]
    process_service: ProcessApplicationService


@dataclass(frozen=True, slots=True)
class RenderedWorkspaceExec:
    content: str


def _coerce_command_deps(value: CommandToolDeps | Any) -> CommandToolDeps | None:
    if isinstance(value, CommandToolDeps):
        return value
    session_workspace_lookup = getattr(value, "session_workspace_lookup", None)
    process_service = getattr(value, "process_service", None)
    if session_workspace_lookup is None or not isinstance(
        process_service,
        ProcessApplicationService,
    ):
        return None
    return CommandToolDeps(
        session_workspace_lookup=session_workspace_lookup,
        process_service=process_service,
    )


def _command_runtime(
    deps: CommandToolDeps | Any,
) -> tuple[SessionBoundWorkspaceResolver, ProcessApplicationService] | None:
    resolved = _coerce_command_deps(deps)
    if resolved is None:
        return None
    workspace_resolver = SessionBoundWorkspaceResolver(
        session_workspace_lookup=resolved.session_workspace_lookup,
    )
    return workspace_resolver, resolved.process_service


def exec(deps: CommandToolDeps | Any):
    runtime = _command_runtime(deps)
    if runtime is None:
        return None
    workspace_resolver, process_service = runtime

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        command = _coerce_text_argument(
            arguments,
            keys=("command", "cmd"),
            label="command",
            allow_empty=False,
        )
        cwd = _coerce_optional_path(
            arguments,
            keys=("cwd", "working_directory", "workingDirectory", "dir"),
        )
        timeout_seconds = _coerce_positive_int(
            arguments,
            keys=("timeout_seconds", "timeoutSeconds", "timeout"),
            default=DEFAULT_WORKSPACE_EXEC_TIMEOUT_SECONDS,
            label="exec timeout",
        )
        max_output_tokens = _coerce_positive_int(
            arguments,
            keys=("max_output_tokens", "maxOutputTokens", "max_tokens", "maxTokens"),
            default=None,
            label="exec max_output_tokens",
        )
        yield_time_ms = _coerce_positive_int(
            arguments,
            keys=("yield_time_ms", "yieldTimeMs", "yield_ms", "yieldMs"),
            default=None,
            label="exec yield_time_ms",
        )
        background = _coerce_bool_argument(
            arguments,
            keys=("background", "detached"),
            default=False,
            label="background",
        )
        workspace_dir = workspace_resolver.resolve(execution_context)
        prepared_command = prepare_workspace_command(
            workspace_dir=workspace_dir,
            command=command,
            cwd=cwd,
            timeout_seconds=(
                timeout_seconds
                if timeout_seconds is not None
                else DEFAULT_WORKSPACE_EXEC_TIMEOUT_SECONDS
            ),
            max_output_tokens=max_output_tokens,
        )
        if background:
            session_key = _resolve_session_key(execution_context)
            process_session = _start_prepared_process(
                process_service,
                prepared_command=prepared_command,
                session_key=session_key,
            )
            rendered = render_process_started(process_session)
            metadata = _process_metadata(
                process_session,
                tool_id=WORKSPACE_EXEC_TOOL_ID,
                background=True,
            )
            metadata[TOOL_RESULT_ENVELOPE_METADATA_KEY] = _process_session_envelope(
                process_session,
                tool_id=WORKSPACE_EXEC_TOOL_ID,
                summary="Background process started.",
            ).to_payload()
            return ToolRunResult.text(
                rendered.content,
                metadata=metadata,
            )
        if yield_time_ms is not None:
            return await _execute_with_yield(
                process_service=process_service,
                prepared_command=prepared_command,
                execution_context=execution_context,
                yield_time_ms=yield_time_ms,
            )
        exec_result = await execute_prepared_workspace_command(prepared_command)
        rendered = render_workspace_exec_result(exec_result)
        metadata = {
            "tool": WORKSPACE_EXEC_TOOL_ID,
            "background": False,
            "workspace_dir": exec_result.workspace_root,
            "cwd": exec_result.working_directory_relative or ".",
            "absolute_cwd": exec_result.working_directory,
            "shell": exec_result.shell,
            "command": exec_result.command,
            "exit_code": exec_result.exit_code,
            "timed_out": exec_result.timed_out,
            "wall_time_seconds": exec_result.wall_time_seconds,
            "stdout": exec_result.stdout,
            "stderr": exec_result.stderr,
            "stdout_truncated": exec_result.stdout_truncated,
            "stderr_truncated": exec_result.stderr_truncated,
            "stdout_original_chars": exec_result.stdout_original_chars,
            "stderr_original_chars": exec_result.stderr_original_chars,
            "output_truncated": exec_result.output_truncated,
            "output_budget_chars": exec_result.output_budget_chars,
            "output_budget_tokens": exec_result.output_budget_tokens,
            "output_estimated_tokens": exec_result.output_estimated_tokens,
            "timeout_seconds": exec_result.timeout_seconds,
        }
        raw_blocks = _raw_output_blocks_for_exec_result(exec_result)
        if raw_blocks:
            metadata[TOOL_RESULT_RAW_OUTPUT_BLOCKS_METADATA_KEY] = raw_blocks
        metadata[TOOL_RESULT_ENVELOPE_METADATA_KEY] = _workspace_exec_result_envelope(
            exec_result,
            raw_blocks=raw_blocks,
        ).to_payload()
        return ToolRunResult.text(
            rendered.content,
            metadata=metadata,
        )

    return handler


def process(deps: CommandToolDeps | Any):
    runtime = _command_runtime(deps)
    if runtime is None:
        return None
    workspace_resolver, process_service = runtime

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        action = _coerce_text_argument(
            arguments,
            keys=("action",),
            label="action",
            allow_empty=False,
        ).strip().lower()
        action = {
            "status": "poll",
            "logs": "log",
            "terminate": "kill",
        }.get(action, action)
        workspace_dir = workspace_resolver.resolve(execution_context)
        workspace_root = str(resolve_workspace_root(workspace_dir))
        session_key = _resolve_session_key(execution_context)
        if action == "list":
            sessions = tuple(
                session
                for session in process_service.list_sessions()
                if _is_visible_process(
                    session,
                    session_key=session_key,
                    workspace_root=workspace_root,
                )
            )
            return ToolRunResult.text(
                render_process_list(sessions),
                metadata={
                    "tool": PROCESS_TOOL_ID,
                    "action": action,
                    "count": len(sessions),
                    "processes": [_process_metadata(session) for session in sessions],
                },
            )

        process_id = _coerce_text_argument(
            arguments,
            keys=("process_id", "processId", "id"),
            label="process_id",
            allow_empty=False,
        ).strip()
        if action == "poll":
            stdout_offset = _coerce_nonnegative_int(
                arguments,
                keys=("stdout_offset", "stdoutOffset"),
                default=0,
                label="stdout_offset",
            )
            stderr_offset = _coerce_nonnegative_int(
                arguments,
                keys=("stderr_offset", "stderrOffset"),
                default=0,
                label="stderr_offset",
            )
            limit = _coerce_positive_int(
                arguments,
                keys=("limit",),
                default=4000,
                label="limit",
            ) or 4000
            session = _get_visible_process(
                process_service,
                process_id=process_id,
                session_key=session_key,
                workspace_root=workspace_root,
            )
            output = process_service.read_output(
                process_id=process_id,
                stdout_offset=stdout_offset,
                stderr_offset=stderr_offset,
                limit=limit,
            )
            metadata = {
                **_process_metadata(session, tool_id=PROCESS_TOOL_ID),
                "action": action,
                "stdout": output.stdout,
                "stderr": output.stderr,
                "stdout_offset": output.stdout_offset,
                "stderr_offset": output.stderr_offset,
                "next_stdout_offset": output.next_stdout_offset,
                "next_stderr_offset": output.next_stderr_offset,
            }
            metadata[TOOL_RESULT_ENVELOPE_METADATA_KEY] = _process_output_envelope(
                session,
                output,
                action=action,
                tool_id=PROCESS_TOOL_ID,
            ).to_payload()
            return ToolRunResult.text(
                render_process_poll(session, output),
                metadata=metadata,
            )
        if action == "log":
            stdout_offset = _coerce_nonnegative_int(
                arguments,
                keys=("stdout_offset", "stdoutOffset", "offset"),
                default=0,
                label="stdout_offset",
            )
            stderr_offset = _coerce_nonnegative_int(
                arguments,
                keys=("stderr_offset", "stderrOffset"),
                default=0,
                label="stderr_offset",
            )
            limit = _coerce_positive_int(
                arguments,
                keys=("limit",),
                default=8000,
                label="limit",
            ) or 8000
            session = _get_visible_process(
                process_service,
                process_id=process_id,
                session_key=session_key,
                workspace_root=workspace_root,
            )
            output = process_service.read_output(
                process_id=process_id,
                stdout_offset=stdout_offset,
                stderr_offset=stderr_offset,
                limit=limit,
            )
            return ToolRunResult.text(
                render_process_log(session, output),
                metadata={
                    **_process_metadata(session, tool_id=PROCESS_TOOL_ID),
                    "action": action,
                    "stdout": output.stdout,
                    "stderr": output.stderr,
                    "stdout_offset": output.stdout_offset,
                    "stderr_offset": output.stderr_offset,
                    "next_stdout_offset": output.next_stdout_offset,
                    "next_stderr_offset": output.next_stderr_offset,
                },
            )
        if action == "kill":
            _get_visible_process(
                process_service,
                process_id=process_id,
                session_key=session_key,
                workspace_root=workspace_root,
            )
            session = process_service.terminate_session(
                process_id=process_id,
            )
            return ToolRunResult.text(
                render_process_state("Process termination requested.", session),
                metadata={
                    **_process_metadata(session, tool_id=PROCESS_TOOL_ID),
                    "action": action,
                },
            )
        if action == "remove":
            session = _get_visible_process(
                process_service,
                process_id=process_id,
                session_key=session_key,
                workspace_root=workspace_root,
            )
            process_service.remove_session(process_id=process_id)
            return ToolRunResult.text(
                render_process_state("Process removed.", session),
                metadata={
                    **_process_metadata(session, tool_id=PROCESS_TOOL_ID),
                    "action": action,
                    "removed": True,
                },
            )
        raise ValueError(
            "process action must be one of: list, poll, log, kill, remove.",
        )

    return handler


def render_workspace_exec_result(
    result: WorkspaceCommandExecution,
) -> RenderedWorkspaceExec:
    lines = [
        "# Workspace Command Execution",
        "",
        f"- command: {result.command}",
        f"- cwd: {result.working_directory_relative or '.'}",
        f"- shell: {result.shell}",
        f"- exit_code: {result.exit_code}",
        f"- timed_out: {str(result.timed_out).lower()}",
        f"- wall_time_seconds: {result.wall_time_seconds:g}",
        f"- timeout_seconds: {result.timeout_seconds}",
        f"- output_budget_tokens: {result.output_budget_tokens or '(default)'}",
        f"- output_estimated_tokens: {result.output_estimated_tokens}",
        f"- output_truncated: {str(result.output_truncated).lower()}",
        "",
        "## stdout",
        "```text",
        result.stdout or "(empty)",
        "```",
    ]
    if result.stdout_truncated:
        lines.extend(
            [
                "",
                "stdout was truncated to fit the tool response.",
            ],
        )
    lines.extend(
        [
            "",
            "## stderr",
            "```text",
            result.stderr or "(empty)",
            "```",
        ],
    )
    if result.stderr_truncated:
        lines.extend(
            [
                "",
                "stderr was truncated to fit the tool response.",
            ],
        )
    return RenderedWorkspaceExec(content="\n".join(lines).strip())


def _raw_output_blocks_for_exec_result(
    result: WorkspaceCommandExecution,
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if result.stdout_truncated and result.stdout_raw:
        blocks.append(
            {
                "name": "stdout",
                "text": result.stdout_raw,
                "mime_type": "text/plain",
            },
        )
    if result.stderr_truncated and result.stderr_raw:
        blocks.append(
            {
                "name": "stderr",
                "text": result.stderr_raw,
                "mime_type": "text/plain",
            },
        )
    return blocks


def _workspace_exec_result_envelope(
    result: WorkspaceCommandExecution,
    *,
    raw_blocks: list[dict[str, Any]],
) -> ToolResultEnvelope:
    status = "error" if result.timed_out or result.exit_code not in (None, 0) else "ok"
    raw_block_names = tuple(
        str(block.get("name") or "").strip()
        for block in raw_blocks
        if str(block.get("name") or "").strip()
    )
    warnings: list[str] = []
    if result.output_truncated:
        warnings.append("stdout/stderr was truncated; full raw output was externalized.")
    if result.timed_out:
        warnings.append("command timed out")
    read_handles = tuple(
        {
            "kind": "raw_output_block",
            "name": name,
            "tool": WORKSPACE_EXEC_TOOL_ID,
        }
        for name in raw_block_names
    )
    key_facts = {
        "workspace_dir": result.workspace_root,
        "cwd": result.working_directory_relative or ".",
        "absolute_cwd": result.working_directory,
        "shell": result.shell,
        "command": result.command,
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
        "wall_time_seconds": result.wall_time_seconds,
        "stdout_chars": len(result.stdout),
        "stderr_chars": len(result.stderr),
        "stdout_original_chars": result.stdout_original_chars,
        "stderr_original_chars": result.stderr_original_chars,
        "output_truncated": result.output_truncated,
        "output_budget_chars": result.output_budget_chars,
        "output_budget_tokens": result.output_budget_tokens,
        "output_estimated_tokens": result.output_estimated_tokens,
        "timeout_seconds": result.timeout_seconds,
    }
    return ToolResultEnvelope(
        status=status,
        summary=_workspace_exec_result_summary(result),
        output_payload={
            **key_facts,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "stdout_truncated": result.stdout_truncated,
            "stderr_truncated": result.stderr_truncated,
            "raw_output_blocks": list(raw_block_names),
        },
        key_facts=key_facts,
        warnings=tuple(warnings),
        read_handles=read_handles,
        model_visible_payload={
            "summary": _workspace_exec_result_summary(result),
            "tool": WORKSPACE_EXEC_TOOL_ID,
            "workspace_dir": result.workspace_root,
            "cwd": result.working_directory_relative or ".",
            "absolute_cwd": result.working_directory,
            "shell": result.shell,
            "command": result.command,
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "stdout_truncated": result.stdout_truncated,
            "stderr_truncated": result.stderr_truncated,
            "read_handles": list(read_handles),
        },
        user_visible_payload={
            "summary": _workspace_exec_result_summary(result),
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
        },
        trace_payload={
            "tool": WORKSPACE_EXEC_TOOL_ID,
            "workspace_dir": result.workspace_root,
            "cwd": result.working_directory_relative or ".",
            "absolute_cwd": result.working_directory,
            "command": result.command,
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
            "raw_output_blocks": list(raw_block_names),
        },
        omitted_count=len(raw_block_names),
        omitted_chars=sum(
            result.stdout_original_chars if name == "stdout" else result.stderr_original_chars
            for name in raw_block_names
        ),
        truncated=result.output_truncated,
    )


def _workspace_exec_result_summary(result: WorkspaceCommandExecution) -> str:
    if result.timed_out:
        return (
            f"exec timed out after {result.timeout_seconds}s: "
            f"{_short_preview(result.stderr or result.stdout)}"
        ).strip()
    if result.exit_code not in (None, 0):
        preview = _short_preview(result.stderr or result.stdout)
        if preview:
            return f"exec exited with code {result.exit_code}: {preview}"
        return f"exec exited with code {result.exit_code}."
    preview = _short_preview(result.stdout or result.stderr)
    if preview:
        return f"exec completed with code {result.exit_code}: {preview}"
    return f"exec completed with code {result.exit_code}."


def _process_session_envelope(
    session: ProcessSession,
    *,
    tool_id: str,
    summary: str,
) -> ToolResultEnvelope:
    metadata = _process_metadata(session, tool_id=tool_id)
    read_handle = _process_read_handle(
        session,
        stdout_offset=0,
        stderr_offset=0,
        limit=4000,
    )
    return ToolResultEnvelope(
        status="running" if session.is_running else _process_status_for_envelope(session),
        summary=summary,
        output_payload=dict(metadata),
        key_facts=dict(metadata),
        read_handles=(read_handle,),
        model_visible_payload={
            "summary": summary,
            **metadata,
            "read_handles": [read_handle],
        },
        user_visible_payload={
            "summary": summary,
            "process_id": session.id,
            "status": session.status.value,
            "exit_code": session.exit_code,
        },
        trace_payload=dict(metadata),
    )


def _process_output_envelope(
    session: ProcessSession,
    output: Any,
    *,
    action: str,
    tool_id: str,
) -> ToolResultEnvelope:
    metadata = {
        **_process_metadata(session, tool_id=tool_id),
        "action": action,
        "stdout": output.stdout,
        "stderr": output.stderr,
        "stdout_offset": output.stdout_offset,
        "stderr_offset": output.stderr_offset,
        "next_stdout_offset": output.next_stdout_offset,
        "next_stderr_offset": output.next_stderr_offset,
    }
    read_handle = _process_read_handle(
        session,
        stdout_offset=output.next_stdout_offset,
        stderr_offset=output.next_stderr_offset,
        limit=4000,
    )
    return ToolResultEnvelope(
        status=_process_status_for_envelope(session),
        summary=_process_output_summary(session, output, action=action),
        output_payload=metadata,
        key_facts={
            key: value
            for key, value in metadata.items()
            if key not in {"stdout", "stderr"}
        },
        read_handles=(read_handle,),
        model_visible_payload={
            "summary": _process_output_summary(session, output, action=action),
            **metadata,
            "read_handles": [read_handle],
        },
        user_visible_payload={
            "summary": _process_output_summary(session, output, action=action),
            "process_id": session.id,
            "status": session.status.value,
            "exit_code": session.exit_code,
        },
        trace_payload={
            key: value
            for key, value in metadata.items()
            if key not in {"stdout", "stderr"}
        },
    )


def _process_read_handle(
    session: ProcessSession,
    *,
    stdout_offset: int,
    stderr_offset: int,
    limit: int,
) -> dict[str, Any]:
    return {
        "kind": "tool_call",
        "tool": PROCESS_TOOL_ID,
        "action": "poll",
        "process_id": session.id,
        "status": session.status.value,
        "exit_code": session.exit_code,
        "arguments": {
            "action": "poll",
            "process_id": session.id,
            "stdout_offset": stdout_offset,
            "stderr_offset": stderr_offset,
            "limit": limit,
        },
    }


def _process_status_for_envelope(session: ProcessSession) -> str:
    if session.is_running:
        return "running"
    if session.exit_code not in (None, 0):
        return "error"
    if session.status.value in {"failed", "killed"}:
        return "error"
    return "ok"


def _process_output_summary(session: ProcessSession, output: Any, *, action: str) -> str:
    if session.is_running:
        return f"process {session.id} is running; call process poll to continue."
    if session.exit_code not in (None, 0):
        preview = _short_preview(str(output.stderr or output.stdout or ""))
        if preview:
            return f"process {session.id} exited with code {session.exit_code}: {preview}"
        return f"process {session.id} exited with code {session.exit_code}."
    preview = _short_preview(str(output.stdout or output.stderr or ""))
    if preview:
        return f"process {session.id} {action} returned: {preview}"
    return f"process {session.id} is {session.status.value}."


def _short_preview(text: str, *, limit: int = 160) -> str:
    preview = text.strip().replace("\n", " ")
    if len(preview) <= limit:
        return preview
    return f"{preview[: max(limit - 3, 0)]}..."


async def _execute_with_yield(
    *,
    process_service: ProcessApplicationService,
    prepared_command: Any,
    execution_context: ToolExecutionContext | None,
    yield_time_ms: int,
) -> ToolRunResult:
    session_key = _resolve_session_key(execution_context)
    process_session = _start_prepared_process(
        process_service,
        prepared_command=prepared_command,
        session_key=session_key,
    )
    wait_seconds = min(
        max(yield_time_ms, 1) / 1000,
        max(prepared_command.timeout_seconds, 1),
    )
    await asyncio.sleep(wait_seconds)
    session = process_service.get_session(process_id=process_session.id)
    output = process_service.read_output(
        process_id=session.id,
        stdout_offset=0,
        stderr_offset=0,
        limit=prepared_command.max_output_chars,
    )
    if session.is_running:
        rendered = render_process_yielded(session, output, yield_time_ms=yield_time_ms)
        metadata = {
            **_process_metadata(
                session,
                tool_id=WORKSPACE_EXEC_TOOL_ID,
                background=True,
            ),
            "yielded": True,
            "yield_time_ms": yield_time_ms,
            "stdout": output.stdout,
            "stderr": output.stderr,
            "stdout_offset": output.stdout_offset,
            "stderr_offset": output.stderr_offset,
            "next_stdout_offset": output.next_stdout_offset,
            "next_stderr_offset": output.next_stderr_offset,
            "output_budget_chars": prepared_command.max_output_chars,
            "output_budget_tokens": prepared_command.max_output_tokens,
        }
        metadata[TOOL_RESULT_ENVELOPE_METADATA_KEY] = _process_output_envelope(
            session,
            output,
            action="yield",
            tool_id=WORKSPACE_EXEC_TOOL_ID,
        ).to_payload()
        return ToolRunResult.text(
            rendered.content,
            metadata=metadata,
        )
    rendered = render_process_completed_after_yield(
        session,
        output,
        yield_time_ms=yield_time_ms,
    )
    metadata = {
        **_process_metadata(
            session,
            tool_id=WORKSPACE_EXEC_TOOL_ID,
            background=False,
        ),
        "yielded": False,
        "yield_time_ms": yield_time_ms,
        "stdout": output.stdout,
        "stderr": output.stderr,
        "stdout_offset": output.stdout_offset,
        "stderr_offset": output.stderr_offset,
        "next_stdout_offset": output.next_stdout_offset,
        "next_stderr_offset": output.next_stderr_offset,
        "output_budget_chars": prepared_command.max_output_chars,
        "output_budget_tokens": prepared_command.max_output_tokens,
    }
    metadata[TOOL_RESULT_ENVELOPE_METADATA_KEY] = _process_output_envelope(
        session,
        output,
        action="yield",
        tool_id=WORKSPACE_EXEC_TOOL_ID,
    ).to_payload()
    return ToolRunResult.text(
        rendered.content,
        metadata=metadata,
    )


def _start_prepared_process(
    process_service: ProcessApplicationService,
    *,
    prepared_command: Any,
    session_key: str | None,
) -> ProcessSession:
    return process_service.start_command(
        session_key=session_key,
        command=prepared_command.shell_command,
        shell=prepared_command.shell,
        working_directory=prepared_command.working_directory,
        env=prepared_command.env,
        metadata={
            "workspace_root": prepared_command.workspace_root,
            "working_directory_relative": prepared_command.working_directory_relative,
            "command": prepared_command.command,
            "crxzipple_python": (
                (prepared_command.env or {}).get("CRXZIPPLE_PYTHON")
                if prepared_command.env
                else None
            ),
        },
    )


def render_process_started(session: ProcessSession) -> RenderedWorkspaceExec:
    lines = [
        "# Background Process Started",
        "",
        f"- process_id: {session.id}",
        f"- command: {_process_command(session)}",
        f"- cwd: {_process_cwd(session)}",
        f"- pid: {session.pid}",
        f"- status: {session.status.value}",
        "",
        "Use the `process` tool to list, poll, read logs, kill, or remove this process.",
    ]
    return RenderedWorkspaceExec(content="\n".join(lines).strip())


def render_process_yielded(
    session: ProcessSession,
    output: Any,
    *,
    yield_time_ms: int,
) -> RenderedWorkspaceExec:
    lines = [
        "# Workspace Command Yielded",
        "",
        f"- process_id: {session.id}",
        f"- command: {session.command}",
        f"- cwd: {_process_cwd(session)}",
        f"- pid: {session.pid}",
        f"- status: {session.status.value}",
        f"- yield_time_ms: {yield_time_ms}",
        f"- next_stdout_offset: {output.next_stdout_offset}",
        f"- next_stderr_offset: {output.next_stderr_offset}",
        "",
        "The command is still running. Use the `process` tool to poll, read logs, kill, or remove it.",
        "",
        "## stdout",
        "```text",
        output.stdout or "(empty)",
        "```",
        "",
        "## stderr",
        "```text",
        output.stderr or "(empty)",
        "```",
    ]
    return RenderedWorkspaceExec(content="\n".join(lines).strip())


def render_process_completed_after_yield(
    session: ProcessSession,
    output: Any,
    *,
    yield_time_ms: int,
) -> RenderedWorkspaceExec:
    lines = [
        "# Workspace Command Completed",
        "",
        f"- process_id: {session.id}",
        f"- command: {session.command}",
        f"- cwd: {_process_cwd(session)}",
        f"- status: {session.status.value}",
        f"- exit_code: {session.exit_code}",
        f"- yield_time_ms: {yield_time_ms}",
        f"- next_stdout_offset: {output.next_stdout_offset}",
        f"- next_stderr_offset: {output.next_stderr_offset}",
        "",
        "## stdout",
        "```text",
        output.stdout or "(empty)",
        "```",
        "",
        "## stderr",
        "```text",
        output.stderr or "(empty)",
        "```",
    ]
    return RenderedWorkspaceExec(content="\n".join(lines).strip())


def render_process_list(sessions: tuple[ProcessSession, ...]) -> str:
    lines = ["# Background Processes", ""]
    if not sessions:
        lines.append("(none)")
        return "\n".join(lines)
    for session in sessions:
        lines.extend(
            [
                f"- process_id: {session.id}",
                f"  status: {session.status.value}",
                f"  command: {session.command}",
                f"  cwd: {_process_cwd(session)}",
                f"  pid: {session.pid}",
            ],
        )
    return "\n".join(lines)


def render_process_poll(session: ProcessSession, output: Any) -> str:
    lines = [
        "# Background Process Poll",
        "",
        f"- process_id: {session.id}",
        f"- status: {session.status.value}",
        f"- exit_code: {session.exit_code if session.exit_code is not None else '(running)'}",
        f"- next_stdout_offset: {output.next_stdout_offset}",
        f"- next_stderr_offset: {output.next_stderr_offset}",
        "",
        "## stdout",
        "```text",
        output.stdout or "(empty)",
        "```",
        "",
        "## stderr",
        "```text",
        output.stderr or "(empty)",
        "```",
    ]
    return "\n".join(lines).strip()


def render_process_log(session: ProcessSession, output: Any) -> str:
    lines = [
        "# Background Process Log",
        "",
        f"- process_id: {session.id}",
        f"- status: {session.status.value}",
        f"- stdout_offset: {output.stdout_offset}",
        f"- stderr_offset: {output.stderr_offset}",
        f"- next_stdout_offset: {output.next_stdout_offset}",
        f"- next_stderr_offset: {output.next_stderr_offset}",
        "",
        "## stdout",
        "```text",
        output.stdout or "(empty)",
        "```",
        "",
        "## stderr",
        "```text",
        output.stderr or "(empty)",
        "```",
    ]
    return "\n".join(lines).strip()


def render_process_state(prefix: str, session: ProcessSession) -> str:
    lines = [
        prefix,
        "",
        f"- process_id: {session.id}",
        f"- status: {session.status.value}",
        f"- exit_code: {session.exit_code if session.exit_code is not None else '(running)'}",
    ]
    return "\n".join(lines)


def _coerce_optional_path(
    arguments: dict[str, Any],
    *,
    keys: tuple[str, ...],
) -> str | None:
    for key in keys:
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _coerce_bool_argument(
    arguments: dict[str, Any],
    *,
    keys: tuple[str, ...],
    default: bool,
    label: str,
) -> bool:
    for key in keys:
        if key not in arguments or arguments[key] is None:
            continue
        value = arguments[key]
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and value in {0, 1}:
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return True
            if normalized in {"false", "0", "no", "off"}:
                return False
        raise ValueError(f"{label} must be a boolean.")
    return default


def _coerce_text_argument(
    arguments: dict[str, Any],
    *,
    keys: tuple[str, ...],
    label: str,
    allow_empty: bool,
) -> str:
    for key in keys:
        if key not in arguments:
            continue
        value = arguments[key]
        if isinstance(value, str):
            if value or allow_empty:
                return value
            raise ValueError(f"{label} must be a non-empty string.")
        if isinstance(value, dict):
            text = value.get("text")
            if not isinstance(text, str):
                raise ValueError(f"{label} text content blocks require a text field.")
            if text or allow_empty:
                return text
            raise ValueError(f"{label} must be a non-empty string.")
        if isinstance(value, list):
            fragments: list[str] = []
            for item in value:
                if not isinstance(item, dict):
                    raise ValueError(f"{label} content blocks must be mappings.")
                block_type = str(item.get("type", "text")).strip() or "text"
                if block_type != "text":
                    raise ValueError(f"{label} only supports text content blocks.")
                text = item.get("text")
                if not isinstance(text, str):
                    raise ValueError(f"{label} text content blocks require a text field.")
                fragments.append(text)
            joined = "".join(fragments)
            if joined or allow_empty:
                return joined
            raise ValueError(f"{label} must be a non-empty string.")
        raise ValueError(f"{label} must be a string or text content block list.")
    raise ValueError(f"{label} is required.")


def _coerce_positive_int(
    arguments: dict[str, Any],
    *,
    keys: tuple[str, ...],
    default: int | None,
    label: str,
) -> int | None:
    raw_value = None
    for key in keys:
        if key in arguments and arguments[key] is not None:
            raw_value = arguments[key]
            break
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer.") from exc
    if value < 1:
        raise ValueError(f"{label} must be at least 1.")
    return value


def _coerce_nonnegative_int(
    arguments: dict[str, Any],
    *,
    keys: tuple[str, ...],
    default: int,
    label: str,
) -> int:
    raw_value = None
    for key in keys:
        if key in arguments and arguments[key] is not None:
            raw_value = arguments[key]
            break
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer.") from exc
    if value < 0:
        raise ValueError(f"{label} must be at least 0.")
    return value


def _resolve_session_key(execution_context: ToolExecutionContext | None) -> str | None:
    if execution_context is None:
        return None
    return execution_context.get_str(_SESSION_KEY_ATTR)


def _get_visible_process(
    process_service: ProcessApplicationService,
    *,
    process_id: str,
    session_key: str | None,
    workspace_root: str,
) -> ProcessSession:
    session = process_service.get_session(process_id=process_id)
    if _is_visible_process(
        session,
        session_key=session_key,
        workspace_root=workspace_root,
    ):
        return session
    raise ProcessNotFoundError(f"Process '{process_id}' was not found.")


def _is_visible_process(
    session: ProcessSession,
    *,
    session_key: str | None,
    workspace_root: str,
) -> bool:
    if session_key is not None and session_key.strip():
        return session.session_key == session_key.strip()
    return _process_workspace_root(session) == workspace_root


def _process_metadata(
    session: ProcessSession,
    *,
    tool_id: str = PROCESS_TOOL_ID,
    background: bool | None = None,
) -> dict[str, Any]:
    workspace_root = _process_workspace_root(session)
    metadata: dict[str, Any] = {
        "tool": tool_id,
        "process_id": session.id,
        "workspace_dir": workspace_root,
        "cwd": _process_cwd(session),
        "absolute_cwd": session.working_directory,
        "command": _process_command(session),
        "shell": session.shell,
        "pid": session.pid,
        "status": session.status.value,
        "exit_code": session.exit_code,
        "session_key": session.session_key,
    }
    if background is not None:
        metadata["background"] = background
    return metadata


def _process_workspace_root(session: ProcessSession) -> str | None:
    value = session.metadata.get("workspace_root")
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            return normalized
    return None


def _process_command(session: ProcessSession) -> str:
    value = session.metadata.get("command")
    if isinstance(value, str) and value.strip():
        return value
    return session.command


def _process_cwd(session: ProcessSession) -> str:
    value = session.metadata.get("working_directory_relative")
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            return normalized
    return "."
