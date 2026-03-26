from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.llm.domain import ToolCallIntent, ToolSchema
from crxzipple.modules.orchestration.application.skills_context import (
    AvailableSkill,
    load_skill_content,
)
from crxzipple.modules.orchestration.domain import OrchestrationValidationError


SKILL_REQUEST_TOOL_NAME = "open_skill"


def is_skill_request_tool_name(name: str) -> bool:
    return name == SKILL_REQUEST_TOOL_NAME


@dataclass(frozen=True, slots=True)
class SkillRequestSurface:
    available_skills: tuple[AvailableSkill, ...]
    tool_name: str = SKILL_REQUEST_TOOL_NAME

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.tool_name,
            description=(
                "Load the full SKILL.md for one relevant skill before following that skill's workflow."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "skill": {
                        "type": "string",
                        "enum": [item.name for item in self.available_skills],
                        "description": "Skill name to open.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why this skill is relevant to the current task.",
                    },
                },
                "required": ["skill"],
                "additionalProperties": False,
            },
        )

    def by_name(self, skill_name: str) -> AvailableSkill | None:
        for item in self.available_skills:
            if item.name == skill_name:
                return item
        return None

    def extract_requested_skill(
        self,
        tool_calls: tuple[ToolCallIntent, ...],
    ) -> AvailableSkill | None:
        skill_requests = [
            tool_call
            for tool_call in tool_calls
            if is_skill_request_tool_name(tool_call.name)
        ]
        if not skill_requests:
            return None
        if len(skill_requests) > 1 or len(skill_requests) != len(tool_calls):
            raise OrchestrationValidationError(
                "Skill requests cannot be combined with other tool calls.",
            )
        tool_call = skill_requests[0]
        skill_name = str(tool_call.arguments.get("skill", "")).strip()
        if not skill_name:
            raise OrchestrationValidationError(
                "Skill request tool call must include a skill name.",
            )
        skill = self.by_name(skill_name)
        if skill is None:
            raise OrchestrationValidationError(
                f"Skill request '{skill_name}' is not available in this run.",
            )
        return skill

    def render_tool_result(self, skill: AvailableSkill) -> str:
        content = load_skill_content(skill)
        lines = [
            f"# Skill: {skill.name}",
            "",
            f"- Source: {skill.source}",
            f"- Path: {skill.path}",
            "",
            content,
        ]
        return "\n".join(lines).strip()
