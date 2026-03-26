from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.memory.application import CreateMemoryCandidateInput
from crxzipple.modules.orchestration.domain import OrchestrationRun


@dataclass(frozen=True, slots=True)
class ExtractedMemoryCandidate:
    create_input: CreateMemoryCandidateInput


def extract_memory_candidate(
    run: OrchestrationRun,
    *,
    result_payload: dict[str, object] | None,
) -> ExtractedMemoryCandidate | None:
    if run.agent_id is None or not run.agent_id.strip():
        return None

    output_text = _normalized_text(result_payload.get("output_text") if result_payload else None)
    inbound_text = _normalized_text(run.inbound_instruction.content)
    if output_text is None:
        return None

    title = _build_title(inbound_text, output_text)
    content = _build_content(inbound_text, output_text)
    summary = _build_summary(output_text)
    tags = _build_tags(run)
    metadata: dict[str, object] = {
        "kind": "turn_completion",
        "source": run.inbound_instruction.source,
    }
    if inbound_text is not None:
        metadata["user_instruction"] = inbound_text
    if result_payload is not None:
        llm_id = result_payload.get("llm_id")
        if isinstance(llm_id, str) and llm_id.strip():
            metadata["llm_id"] = llm_id.strip()
        assistant_message_id = result_payload.get("assistant_message_id")
        if isinstance(assistant_message_id, str) and assistant_message_id.strip():
            metadata["assistant_message_id"] = assistant_message_id.strip()
    prompt_mode = run.metadata.get("prompt_mode")
    if isinstance(prompt_mode, str) and prompt_mode.strip():
        metadata["prompt_mode"] = prompt_mode.strip()
    workspace_context_files = run.metadata.get("workspace_context_files")
    if isinstance(workspace_context_files, list):
        metadata["workspace_context_files"] = list(workspace_context_files)
    workspace_context_workspace = run.metadata.get("workspace_context_workspace")
    if (
        isinstance(workspace_context_workspace, str)
        and workspace_context_workspace.strip()
    ):
        metadata["workspace_context_workspace"] = workspace_context_workspace.strip()

    return ExtractedMemoryCandidate(
        create_input=CreateMemoryCandidateInput(
            agent_id=run.agent_id,
            title=title,
            content=content,
            summary=summary,
            session_key=_normalized_text(run.metadata.get("session_key")),
            run_id=run.id,
            tags=tags,
            metadata=metadata,
        ),
    )


def _normalized_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _build_title(inbound_text: str | None, output_text: str) -> str:
    if inbound_text is not None:
        return inbound_text[:120]
    first_line = output_text.splitlines()[0].strip() if output_text.splitlines() else output_text
    return first_line[:120] or "Turn memory"


def _build_content(inbound_text: str | None, output_text: str) -> str:
    if inbound_text is None:
        return output_text
    return "\n".join(
        [
            f"User request: {inbound_text}",
            "",
            "Assistant response:",
            output_text,
        ],
    ).strip()


def _build_summary(output_text: str) -> str:
    lines = [line.strip() for line in output_text.splitlines() if line.strip()]
    if not lines:
        return output_text[:240]
    return lines[0][:240]


def _build_tags(run: OrchestrationRun) -> tuple[str, ...]:
    tags: list[str] = ["turn", "candidate"]
    source = run.inbound_instruction.source.strip().lower()
    if source:
        tags.append(source)
    prompt_mode = run.metadata.get("prompt_mode")
    if isinstance(prompt_mode, str) and prompt_mode.strip():
        tags.append(prompt_mode.strip().lower())
    return tuple(dict.fromkeys(tags))
