# Requirement Mapping

Map requirements from the reusable workflow, not from incidental implementation details.

## Tool Functions

Use Tool Function IDs when the skill needs the agent to call a specific runtime tool. Prefer required tools only when the workflow cannot work without them.

Use suggested tools when:

- More than one tool could satisfy the workflow.
- The tool was helpful in the original task but not essential.
- The exact runtime provider is uncertain.

## Access

Use Access requirements or binding IDs for external accounts, API keys, OAuth accounts, provider credentials, and service setup. Never write credential values, environment variable contents, token file paths, or SDK cache paths.

Examples:

- `openai-api-key` for an OpenAI API key binding.
- A provider-specific OAuth account requirement for user-authorized APIs.
- A service setup requirement when the account must be connected before the tool can run.

## Authorization Effects

Use Authorization effect IDs when a skill can cause writes or privileged actions.

Common categories:

- Filesystem writes or package installation.
- Remote execution, network calls, or provider-side mutations.
- Sending messages, emails, comments, or notifications.
- Deleting, rejecting, applying, publishing, or changing governance state.

`skill_draft_apply` must require explicit approval and an apply effect because it writes skill owner truth.

## Surfaces And Platforms

Use surfaces for where the skill is valid, such as `interactive`, `background`, or a product-specific surface. Use platforms only when the workflow truly depends on an operating system, runtime, or provider environment.

## Uncertainty

When unsure, mark the dependency as suggested and explain the uncertainty in validation notes or support references. Do not invent requirement IDs.
