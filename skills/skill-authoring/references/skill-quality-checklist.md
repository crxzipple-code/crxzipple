# Skill Quality Checklist

Use this checklist before validating a skill draft.

## Scope

- The skill has one clear job and one natural trigger.
- It is not a generic "how to be a good assistant" instruction set.
- It is not so narrow that it only repeats a single completed conversation.
- It names anti-patterns when misuse would be likely.

## Trigger Quality

- `description` is short, concrete, and model-facing.
- `when_to_use` describes user intent or task conditions, not implementation internals.
- The trigger does not depend on hidden local paths, private names, or current-run state.

## Instructions

- The main `SKILL.md` is short enough to read in prompt.
- Steps are operational and leave the model room to adapt.
- Long examples, tables, checklists, and templates live in `references/`.
- The workflow tells the model when to stop, validate, or ask for approval.

## Safety And Privacy

- No raw credentials, tokens, cookies, personal data, or private transcripts are included.
- File paths are abstract unless a repo-relative path is part of the reusable contract.
- Write operations name their required Authorization effect.
- External services are represented as Access requirements or bindings, not secret values.

## Verification

- The draft includes at least one validation or acceptance signal.
- Failure examples or edge cases are included when they would prevent common misuse.
- Tool IDs, Access IDs, Authorization effects, surfaces, and platforms are spelled exactly.
- Uncertain dependencies are suggested, not required.
