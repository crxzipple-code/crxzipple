# Agent Profiles

`agent sync-profiles` loads YAML/JSON files from this directory by default.

Example:

```yaml
defaults:
  instruction_policy:
    stream_by_default: true
  llm_routing_policy:
    default_llm_id: openai.gpt-5.4-mini
  execution_policy:
    timeout_seconds: 120
    max_turns: 12

profiles:
  - id: writer
    name: Writer
    identity:
      display_name: Writer Agent
    instruction_policy:
      system_prompt: You write concise, structured answers.
```
