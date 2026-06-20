# Workbench / Operations ResponseItem Observability Development Plan

Date: 2026-06-14

## 背景

CRXZipple 已经有 Workbench timeline、Operations read model、LLM invocation detail 和 execution chain。最新会话暴露的问题不是“完全看不到数据”，而是 UI/observability 不能快速回答：

- 模型实际看到了什么？
- 哪些 item 是用户可见？
- 哪些 item 是 model-visible replay？
- 哪些 tool result 是任务证据？
- 为什么 run completed 但实际只是问了重复澄清？
- 当前走的是 provider native continuation、structured replay，还是 transcript fallback？

本文件定义 Workbench / Operations 如何展示新的 ResponseItem replay 和 Context Tree projection 形态。

## 目标

1. Workbench timeline 展示用户该看的阶段性内容。
2. Trace/Operations 保留完整可审计 item 链。
3. 明确区分 user-visible、chat-visible、trace-visible、model-visible。
4. 展示 provider request input mode 和 replay结构。
5. 展示 evidence split：context observation vs task evidence。
6. 不让前端绕过 `/operations/*` 直接拼 owner facts。

## 非目标

- 不把 raw reasoning 默认展示给用户。
- 不把 full context tree 默认展示为聊天消息。
- 不让 Workbench 成为 replay 数据真相。
- 不为了历史兼容保留旧 timeline 兜底文案。

## Timeline Item Taxonomy

Workbench timeline should render from a read model with these semantic kinds:

- `user_message`
- `assistant_progress`
- `assistant_final`
- `reasoning_summary`
- `tool_call`
- `tool_result`
- `context_observation`
- `task_evidence`
- `correction`
- `diagnostic`
- `approval`
- `error`

Raw owner kinds can still exist, but UI should display semantic timeline kinds.

## Visibility Matrix

| Item | User visible | Chat visible | Trace visible | Model replay |
| --- | --- | --- | --- | --- |
| user message | yes | yes | yes | yes |
| assistant final | yes | yes | yes | yes |
| assistant progress | yes if policy | yes if policy | yes | yes if model_visible |
| reasoning summary | yes if policy | optional | yes | yes if provider policy |
| raw reasoning | no by default | no | restricted | provider-specific |
| tool call | no by default | no | yes | yes |
| tool result | no by default | no | yes | yes if selected |
| context tree render output | no by default | no | yes | yes as tool output |
| active task state | no by default | no | yes | yes |
| correction item | maybe | maybe | yes | yes |
| diagnostic | yes if actionable | no | yes | no unless corrective |

## Workbench Changes

### 1. Timeline Cards

Display:

- Assistant progress as normal visible progress, not fallback.
- Reasoning summary separately from assistant final.
- Tool call/result collapsed by default, expandable in trace mode.
- Context observations with distinct label: “Context read”, “Tree expanded”.
- Task evidence with stronger label: “Evidence verified”, “Validation failed”.

### 2. Request Inspection Panel

For each LLM step:

- `input_mode`
- `input_item_count`
- item type histogram
- context projection id
- active task state summary
- provider actual payload preview
- tool schema count
- native continuation status
- replay fallback status

### 3. Completion Diagnostics

If run completes after a clarification:

- Show `completion_reason`.
- If `slot_regression_detected=true`, show:
  ```text
  The assistant asked for fields already present in active task state.
  ```
- If corrective continuation was skipped, show why:
  - max steps
  - budget
  - provider error
  - policy disabled

### 4. Evidence View

Split evidence tab:

- Context observations:
  - tree rendered
  - tree expanded
  - snapshot read
- Task evidence:
  - official site output
  - command output
  - API response
  - validation result

Do not count context observations in task evidence totals.

## Operations Changes

### LLM Invocation Detail

Add fields:

- `input_mode`
- `structured_replay_item_count`
- `message_transcript_fallback_used`
- `provider_native_continuation_used`
- `previous_response_id_sent`
- `provider_transport`
- `reasoning_policy`
- `replay_budget_report`

### Orchestration Run Detail

Add:

- active task state snapshot
- correction attempts
- evidence split counts
- slot regression warnings
- context-tree-only loop warning

### Baseline Dashboard

Add metrics:

- `active_task_state_present`
- `known_slot_count`
- `slot_regression_detected`
- `structured_replay_item_count`
- `task_evidence_count`
- `context_observation_count`
- `full_tree_prompt_visible`
- `tree_tool_call_count`

## Read Model Source Rules

- Workbench consumes orchestration/workbench read model.
- Operations consumes `/operations/{module}` projections.
- Frontend must not call `/tools`, `/llms`, `/orchestration` ad hoc to patch missing data.
- Missing display fields should be fixed by owner query service or projection materializer.

## Error and Guidance UX

For actionable failures:

- Authentication / login required:
  - show title, cause, action.
  - include link/button only if approval/action exists.
- Database unreachable:
  - show infra status and start command.
- Provider unsupported parameter:
  - show transport/capability mismatch.
  - say whether fallback is available.
- Slot regression:
  - show “agent lost task state” diagnostic and correction status.

## Test Plan

### Unit

- Timeline semantic kind mapper.
- Visibility matrix for each item kind.
- Evidence split display classifier.
- Request inspection DTO mapping.

### Frontend

- Workbench timeline renders assistant progress.
- Context observations do not display as task evidence.
- LLM step panel shows input mode and item counts.
- Error states have stable layout and actionable guidance.

### Operations

- Projection includes new LLM request/replay fields.
- Baseline dashboard shows new metrics.
- HTML error responses still handled as JSON-safe UI errors.

## Checklist

- [ ] Extend Workbench read model item kinds.
- [ ] Add request inspection fields.
- [ ] Add evidence split projection.
- [ ] Add completion diagnostics projection.
- [ ] Update Operations LLM detail projection.
- [ ] Update Operations Orchestration detail projection.
- [ ] Update frontend timeline rendering.
- [ ] Update frontend i18n.
- [ ] Add frontend typecheck/build verification.
- [ ] Add regression fixture for East China Airlines follow-up.

## Acceptance Criteria

- User sees real assistant progress when policy says visible.
- Trace shows complete structured item chain.
- UI can explain why a run completed/failed/waited.
- Latest LLM step clearly shows whether input was structured replay or tree prompt.
- Context tree reads are visible as trace operations but not mistaken for task evidence.
