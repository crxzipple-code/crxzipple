from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from crxzipple.modules.process.domain import ProcessOutputWindow
from crxzipple.modules.tool.application.result_envelope import ToolResultEnvelope


class CliRuntimeConfig(Protocol):
    source_id: str
    provider_name: str
    working_directory: object
    shell: bool
    output_limit_bytes: int


def process_output_payload(output: Any) -> dict[str, Any]:
    return {
        "process_id": output.process_id,
        "status": output.status.value,
        "exit_code": output.exit_code,
        "stdout": output.stdout,
        "stderr": output.stderr,
        "stdout_offset": output.stdout_offset,
        "stderr_offset": output.stderr_offset,
        "next_stdout_offset": output.next_stdout_offset,
        "next_stderr_offset": output.next_stderr_offset,
        "started_at": output.started_at.isoformat(),
        "ended_at": output.ended_at.isoformat() if output.ended_at else None,
    }


def cli_runtime_facts(
    config: CliRuntimeConfig,
    *,
    action: str,
    argv: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "source_id": config.source_id,
        "provider": config.provider_name,
        "cli_action": action,
        "working_directory": str(config.working_directory),
        "shell": config.shell,
        "argv": sanitized_argv(argv) if argv else (),
        "output_limit_bytes": config.output_limit_bytes,
    }


def process_continuation_payload(
    output: ProcessOutputWindow,
    *,
    default_limit: int,
) -> dict[str, Any]:
    arguments = {
        "process_id": output.process_id,
        "stdout_offset": output.next_stdout_offset,
        "stderr_offset": output.next_stderr_offset,
        "limit": max(int(default_limit), 1),
    }
    return {
        "tool_action": "cli_read_output",
        "process_id": output.process_id,
        "status": output.status.value,
        "exit_code": output.exit_code,
        "next_read_arguments": arguments,
        "read_hint": (
            "Call cli_read_output with next_read_arguments to continue reading "
            "stdout/stderr for this process."
        ),
    }


def cli_process_result_envelope(
    details: Mapping[str, Any],
    *,
    source_id: str,
    provider_name: str,
    action: str,
    output: ProcessOutputWindow,
) -> ToolResultEnvelope:
    stdout = str(details.get("stdout") or "")
    stderr = str(details.get("stderr") or "")
    status = _cli_process_envelope_status(output)
    read_handle = _process_read_handle(
        output,
        default_limit=int(details.get("runtime_facts", {}).get("output_limit_bytes") or 4000)
        if isinstance(details.get("runtime_facts"), Mapping)
        else 4000,
    )
    key_facts: dict[str, Any] = {
        "process_id": output.process_id,
        "process_status": output.status.value,
        "exit_code": output.exit_code,
        "stdout_chars": len(stdout),
        "stderr_chars": len(stderr),
        "next_stdout_offset": output.next_stdout_offset,
        "next_stderr_offset": output.next_stderr_offset,
        "working_directory": details.get("working_directory"),
    }
    if stderr.strip():
        key_facts["stderr_preview"] = _short_preview(stderr)
    summary = _cli_process_result_summary(
        provider_name=provider_name,
        action=action,
        output=output,
        stdout=stdout,
        stderr=stderr,
    )
    return ToolResultEnvelope(
        status=status,
        summary=summary,
        output_payload=dict(details),
        key_facts=key_facts,
        read_handles=(read_handle,),
        provider_replay_payload={
            "summary": summary,
            "process_id": output.process_id,
            "status": output.status.value,
            "exit_code": output.exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "continuation": details.get("continuation"),
            "runtime_facts": details.get("runtime_facts"),
            "read_handles": [read_handle],
        },
        user_summary_payload={
            "summary": summary,
            "process_id": output.process_id,
            "status": output.status.value,
            "exit_code": output.exit_code,
        },
        trace_payload={
            "source_id": source_id,
            "provider": provider_name,
            "cli_action": action,
            "process_id": output.process_id,
            "stdout_offset": output.stdout_offset,
            "stderr_offset": output.stderr_offset,
            "next_stdout_offset": output.next_stdout_offset,
            "next_stderr_offset": output.next_stderr_offset,
        },
    )


def cli_help_result_envelope(
    details: Mapping[str, Any],
    *,
    source_id: str,
    provider_name: str,
) -> ToolResultEnvelope:
    stdout = str(details.get("stdout") or "")
    stderr = str(details.get("stderr") or "")
    exit_code = details.get("exit_code")
    status = "error" if isinstance(exit_code, int) and exit_code != 0 else "ok"
    summary = (
        f"{provider_name} cli_help exited with code {exit_code}."
        if exit_code is not None
        else f"{provider_name} cli_help completed."
    )
    return ToolResultEnvelope(
        status=status,
        summary=summary,
        output_payload=dict(details),
        key_facts={
            "source_id": source_id,
            "provider": provider_name,
            "exit_code": exit_code,
            "stdout_chars": len(stdout),
            "stderr_chars": len(stderr),
            "working_directory": details.get("working_directory"),
        },
        provider_replay_payload={
            "summary": summary,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "runtime_facts": details.get("runtime_facts"),
        },
        user_summary_payload={
            "summary": summary,
            "exit_code": exit_code,
        },
        trace_payload={
            "source_id": source_id,
            "provider": provider_name,
            "cli_action": "cli_help",
        },
    )


def render_cli_output(details: Mapping[str, Any]) -> str:
    stdout = str(details.get("stdout") or "").strip()
    stderr = str(details.get("stderr") or "").strip()
    if stdout and stderr:
        return f"{stdout}\n\nstderr:\n{stderr}"
    return stdout or stderr or f"CLI exited with code {details.get('exit_code')}."


def sanitized_argv(argv: tuple[str, ...]) -> list[str]:
    return list(argv)


def _process_read_handle(
    output: ProcessOutputWindow,
    *,
    default_limit: int,
) -> dict[str, Any]:
    continuation = process_continuation_payload(
        output,
        default_limit=default_limit,
    )
    return {
        "kind": "tool_call",
        "tool_action": "cli_read_output",
        "process_id": output.process_id,
        "status": output.status.value,
        "exit_code": output.exit_code,
        "arguments": continuation["next_read_arguments"],
    }


def _cli_process_envelope_status(output: ProcessOutputWindow) -> str:
    if output.status.value == "running":
        return "running"
    if output.exit_code not in (None, 0):
        return "error"
    if output.status.value in {"failed", "killed"}:
        return "error"
    return "ok"


def _cli_process_result_summary(
    *,
    provider_name: str,
    action: str,
    output: ProcessOutputWindow,
    stdout: str,
    stderr: str,
) -> str:
    if output.status.value == "running":
        return (
            f"{provider_name} {action} started process {output.process_id}; "
            "read more output with cli_read_output."
        )
    if output.exit_code not in (None, 0):
        preview = _short_preview(stderr or stdout)
        if preview:
            return (
                f"{provider_name} {action} process {output.process_id} exited "
                f"with code {output.exit_code}: {preview}"
            )
        return (
            f"{provider_name} {action} process {output.process_id} exited "
            f"with code {output.exit_code}."
        )
    preview = _short_preview(stdout or stderr)
    if preview:
        return (
            f"{provider_name} {action} process {output.process_id} completed: "
            f"{preview}"
        )
    return (
        f"{provider_name} {action} process {output.process_id} is "
        f"{output.status.value}."
    )


def _short_preview(text: str, *, limit: int = 160) -> str:
    preview = text.strip().replace("\n", " ")
    if len(preview) <= limit:
        return preview
    return f"{preview[: max(limit - 3, 0)]}..."


__all__ = [
    "cli_help_result_envelope",
    "cli_process_result_envelope",
    "cli_runtime_facts",
    "process_continuation_payload",
    "process_output_payload",
    "render_cli_output",
    "sanitized_argv",
]
