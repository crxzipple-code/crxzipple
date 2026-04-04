# Memory Recall

Use this skill when earlier project decisions, user preferences, prior commitments, or durable workspace context may affect the current answer.

## Goal

Recall relevant memory before answering, and write durable memory when the user explicitly asks you to remember something worth keeping.

## Workflow

1. If the current task may depend on prior context, call `memory_search` first instead of guessing.
2. Review the returned `path`, `citation`, `kind`, and `snippet` to decide which result is worth reading.
3. Call `memory_read` with the returned `citation` for the most relevant hit.
4. Only after reading the source excerpt, answer the user's request.
5. If the user explicitly asks you to remember a durable fact, preference, decision, or ongoing commitment, call `memory_write_daily` with a concise markdown note instead of waiting for a later maintenance run.

## Rules

- Treat `memory_search` as a locator, not as the final answer.
- Prefer the smallest relevant read before doing more searching.
- If memory results are weak or missing, say so instead of inventing prior context.
- Re-check memory when the answer depends on earlier decisions, preferences, or commitments.
- Only write durable memory that should survive into future sessions.
- Do not write transient chatter, one-off pleasantries, or low-signal turn details.
- If you need to avoid duplicating or contradicting an existing memory, search/read first, then write.

## Typical Cases

- "What did we decide earlier?"
- "What preferences does this user have?"
- "Did we already choose an approval model?"
- "What does this project memory say about the expected workflow?"
- "Remember that my birthday is October 5."
- "Please remember we decided to use approval-only remote tools."
