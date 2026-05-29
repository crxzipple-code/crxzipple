---
name: skill-authoring
description: Create or update reusable CRXZipple skills from completed work, workflows, domain knowledge, or tool usage patterns.
version: 1
tags:
  - skill
  - authoring
  - governance
when_to_use: When the user asks to turn experience, a repeated workflow, lessons learned, domain knowledge, or tool usage into a reusable skill.
required_tools:
  - skill_draft_create
  - skill_draft_update
  - skill_draft_validate
  - skill_draft_diff
suggested_tools:
  - skill_read
  - skill_draft_apply
  - skill_draft_reject
surfaces:
  - interactive
---

# Skill Authoring

Use this skill when the user wants reusable experience turned into a CRXZipple skill, or when an existing skill should be revised through the governed draft flow.

## Decide First

Create or update a skill only when the knowledge is reusable, has a clear trigger, lowers future context cost, and can be written without private secrets or one-off conversation detail. If the request is only a transcript summary, summarize it instead of creating a skill.

## Extract The Reusable Pattern

Identify the task goal, constraints, steps that worked, failed paths, required tools or services, approval needs, and verification signals. Keep project-specific facts only when they are essential to future use.

## Draft Shape

Produce a compact package:

1. `manifest` with `name`, `description`, `when_to_use`, tags, requirements, surfaces, and platforms.
2. `instructions_body` with short operational guidance, not a long report.
3. `support_files` only for larger examples, checklists, templates, or reference material.
4. `requirements` using Tool Function IDs, Access requirement or binding IDs, Authorization effect IDs, surfaces, and platforms.

Do not write environment variable values, raw credentials, absolute local secrets, or private user data into the draft.

## Requirements

Map dependencies conservatively. Mark uncertain tools or access as suggested rather than required. Use Authorization effects for writes, remote execution, network calls, privileged local actions, or irreversible changes.

## Tool Flow

1. For a new skill, call `skill_draft_create`.
2. For an existing skill, read the current package when useful, then call `skill_draft_update`.
3. Always call `skill_draft_validate`.
4. Always call `skill_draft_diff` before asking for apply.
5. Call `skill_draft_apply` only after explicit user approval. If the user rejects the draft, call `skill_draft_reject`.

Use `references/skill-quality-checklist.md`, `references/requirement-mapping.md`, and `references/examples.md` when the draft needs more structure.
