# Examples

## New Skill Draft

User asks: "Turn this recurring PR review workflow into a skill."

Draft intent:

- `intent`: `create`
- `skill_name`: `pr-review`
- `description`: Review pull requests for correctness, tests, regressions, and maintainability.
- Required tools: repository inspection tools that are truly required.
- Suggested tools: GitHub or CI tools if they are helpful but not always available.
- Required effects: only include write effects if the skill will post reviews, change branches, or modify files.

Instruction outline:

1. Read the user request and repository context.
2. Inspect diffs and tests before commenting.
3. Lead with findings and file references.
4. Treat missing tests as risk, not a style nit.
5. Do not post externally without explicit approval.

## Update Existing Skill Draft

User asks: "Update the memory recall skill with the new rule we learned."

Flow:

1. Call `skill_read` for the current `SKILL.md`.
2. Build a focused patch rather than rewriting the whole skill.
3. Call `skill_draft_update` with the changed manifest fields, instructions, or support files.
4. Validate and diff.
5. Wait for explicit approval before apply.

## Rejecting A Draft

If validation shows the draft is one-off, too broad, or contains private data:

1. Explain the issue briefly.
2. Ask whether to revise or abandon.
3. If the user rejects it, call `skill_draft_reject` with the reason.
