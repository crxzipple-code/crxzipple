from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from crxzipple.modules.process import (
    ProcessApplicationService,
    ProcessNotFoundError,
    ProcessSession,
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
        )
        if background:
            session_key = _resolve_session_key(execution_context)
            process_session = process_service.start_command(
                session_key=session_key,
                command=prepared_command.command,
                shell=prepared_command.shell,
                working_directory=prepared_command.working_directory,
                metadata={
                    "workspace_root": prepared_command.workspace_root,
                    "working_directory_relative": (
                        prepared_command.working_directory_relative
                    ),
                },
            )
            rendered = render_process_started(process_session)
            return ToolRunResult.text(
                rendered.content,
                metadata=_process_metadata(
                    process_session,
                    tool_id=WORKSPACE_EXEC_TOOL_ID,
                    background=True,
                ),
            )
        exec_result = await execute_prepared_workspace_command(prepared_command)
        rendered = render_workspace_exec_result(exec_result)
        return ToolRunResult.text(
            rendered.content,
            metadata={
                "tool": WORKSPACE_EXEC_TOOL_ID,
                "background": False,
                "workspace_dir": exec_result.workspace_root,
                "cwd": exec_result.working_directory_relative or ".",
                "absolute_cwd": exec_result.working_directory,
                "shell": exec_result.shell,
                "command": exec_result.command,
                "exit_code": exec_result.exit_code,
                "stdout": exec_result.stdout,
                "stderr": exec_result.stderr,
                "stdout_truncated": exec_result.stdout_truncated,
                "stderr_truncated": exec_result.stderr_truncated,
                "timeout_seconds": exec_result.timeout_seconds,
            },
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
            return ToolRunResult.text(
                render_process_poll(session, output),
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
        f"- timeout_seconds: {result.timeout_seconds}",
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


def render_process_started(session: ProcessSession) -> RenderedWorkspaceExec:
    lines = [
        "# Background Process Started",
        "",
        f"- process_id: {session.id}",
        f"- command: {session.command}",
        f"- cwd: {_process_cwd(session)}",
        f"- pid: {session.pid}",
        f"- status: {session.status.value}",
        "",
        "Use the `process` tool to list, poll, read logs, kill, or remove this process.",
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
        "command": session.command,
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


def _process_cwd(session: ProcessSession) -> str:
    value = session.metadata.get("working_directory_relative")
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            return normalized
    return "."
