# LLM Provider Protocol Rendering Boundary Refactor Plan

Date: 2026-06-15

## 背景

最近多轮对比 CRXZipple agent 与 Codex agent 的真实执行链路后，问题已经不再是“某个字段有没有塞进 prompt”，而是边界错位：

- Context Workspace 在维护 Context Tree 的同时，仍承担了过多“prompt body / metadata hint / browser evidence path”职责。
- Orchestration 在推进 run 的同时，仍参与了 request assembly、runtime hint、evidence frontier、loop correction 等 provider 输入附近的逻辑。
- LLM adapter 目前主要负责调用 provider 和解析 provider response；request 侧只做了部分投影，尚未成为完整的 provider/transport/model 协议边界。

用户最新决策：

- Runtime 应维护 Context Tree。
- 渲染层应根据 provider / transport / model 能力，把同一份 runtime canonical context 渲染成最适合 provider 的输入结构。
- 这个 request rendering 与 response parsing 应该是对称的，都属于 LLM provider adapter / renderer 边界。
- 不应把问题简化成“砍掉某个模块的某个字段”，而要重新划清模块是否应该承担该职责。
- 不兼容旧结构，不双轨并行；数据库可清空重建，施工以最佳 agent 效果和清晰边界为目标。
- 一切无法形成准确结论的启发式判断、路线偏置、证据裁判、任务特化策略都不能默认发送给 LLM，避免干扰模型判断。
- Codex 模型适配必须对齐已抓包的 Codex trace 和源码事实；不能凭猜测补 provider 行为。
- 内核保持通用性；任何面向特定任务的流程、判断、验收、重试策略都应进入后续 workflow / skill / evaluator 层，不进入通用 runtime kernel。

因此，本文件定义一次架构级重构：把“如何喂模型”的逻辑从 Context Workspace 和 Orchestration 中收归到 LLM 模块的 provider protocol rendering 边界。

## 一句话目标

**Context Tree 是 runtime canonical context；LLM Provider Adapter 是双向协议边界；Orchestration 只协调 run，不拼 provider prompt；Context Workspace 不生产 provider prompt。**

## 必须遵守的原则

这些原则是施工硬约束，不是建议。后续实现、测试和文档若与本节冲突，以本节为准。

### 1. 不兼容旧结构，不双轨并行

- 不为旧 prompt assembly、旧 context render prompt body、旧 evidence frontier input 路径增加 shim。
- 不保留“新旧都能跑一点”的长期兼容双轨。
- 允许 breaking migration、清空数据库、重建 projection、删除旧字段。
- 测试应改向新边界，而不是用兼容层维持旧断言。

验收口径：

- 同一职责只能有一个 owner 和一个 runtime path。
- provider request rendering 只能走 LLM renderer/router。
- 旧入口未迁移前不得继续新增功能。

### 2. 无法形成准确结论的内容不得发送给 LLM

默认 provider input 只允许包含：

- 用户输入。
- 稳定 runtime / developer instructions。
- provider-neutral canonical transcript。
- 工具调用和工具结果。
- context snapshot ref / compact projection。
- provider-visible tool schema。
- 明确的 owner facts。

默认 provider input 不允许包含：

- 通用 evidence verdict，例如 verified / partial / remaining gap。
- browser path missing / route bias / evidence ladder 这类不可穷举路线判断。
- loop correction / validation lag 等 runtime 启发式建议。
- 任务特化 slot 判断。
- 无法证明完整性或准确性的“应该下一步做什么”提示。

这些内容若需要保留，只能进入：

- Operations。
- Trace。
- Workbench debug inspector。
- baseline metrics。
- workflow / skill evaluator。

### 3. Codex 适配以抓包 trace 和源码事实为准

- Codex WebSocket 是否使用 `previous_response_id`，以实测 trace 和源码为准。
- Codex HTTP 是否全量 `input[]` 回放，以实测 trace 和源码为准。
- 不允许因为“猜测 provider 应该支持”而发送 unsupported 字段。
- 每次 provider 行为变更必须有 trace / fake server / adapter unit test 支撑。

验收口径：

- Codex WebSocket renderer 的测试必须证明 delta request 形态。
- Codex HTTP renderer 的测试必须证明不发送 unsupported `previous_response_id`。
- Operations 必须展示 renderer id、transport、render strategy、wire preview、loss report。

### 4. 内核保持通用性，任务特化进入 Skill / Workflow

通用 runtime kernel 只能负责：

- 上下文管理。
- provider request/response 协议转换。
- tool lifecycle。
- response item lifecycle。
- run scheduling / approval / terminal 状态。

不得在通用 kernel 中加入：

- 专门针对东航、航班、WAF、某网站、某接口的逻辑。
- 专门针对某类网页任务的 evidence gate。
- 任务 slot validator。
- 任务验收策略。
- 业务 retry workflow。

这些能力若需要，进入：

- skill。
- workflow。
- evaluator。
- task-specific tool。
- user-selected policy。

### 5. Provider request rendering 与 response parsing 必须对称

每个 provider/transport/model 的适配必须同时回答：

- runtime canonical request 如何渲染成 provider wire payload。
- provider wire response 如何解析回 runtime canonical response。
- 哪些结构被 native 支持。
- 哪些结构被降级。
- 哪些结构被丢弃。
- 丢失是否影响模型判断。

不允许只在 response 侧对齐，却让 request 侧散落在 Orchestration / Context Workspace / ad hoc helper 中。

## 当前问题

## 1. Context Render 概念过载

当前 `ContextSnapshot` 同时承担：

- Context Tree 当前可见状态。
- runtime contract / agent home / tool surface / session item refs。
- provider attachment mirror。
- prompt body。
- context delta。
- browser investigation metadata。
- token estimate / budget diagnostics。

这些东西都叫 render，导致下游很难判断：

- 哪些是 canonical context facts。
- 哪些是 provider input。
- 哪些只是 Operations / Debug 观察。
- 哪些是旧 prompt 工程启发式。

目标状态：

- Context Workspace 产出 `ContextSnapshot` / `ContextGraphSnapshot`。
- 它是上下文事实快照，不等同于 provider prompt。
- provider prompt/input 只能由 LLM request renderer 生成。

## 2. Evidence / Browser Path 混入通用 agent loop

`evidence_frontier`、`browser_evidence_path_ladder`、`browser_investigation_route_bias`、`runtime_loop_correction` 等结构原本是为解释和调试长链探索而加入。

问题：

- 它们会让 runtime 侧替模型判断“证据够不够 / 路径缺不缺 / 应该怎么探索”。
- 这些判断无法穷举，容易误导通用 agent。
- 它们不属于 provider protocol，也不属于 Context Tree 事实本身。

目标状态：

- 通用 agent loop 不维护默认 evidence gate / evidence frontier judgement。
- 这些结构若保留，只能作为 Operations / Trace / Debug projection。
- 业务强验收交给 workflow / skill evaluator，不进入默认 agent runtime。

## 3. Orchestration 仍有 request assembly 影子

Orchestration 当前已经有 `RuntimeLlmRequest`、`ProviderRequestBuilder`、`RuntimeLlmRequestDraftCollector` 等结构，但边界还不够硬：

- 它知道太多 provider input 形态。
- 它仍处理 context projection、session replay、tool surface、runtime metadata 的组合。
- 它容易继续长出 provider-specific 或 task-specific prompt 逻辑。

目标状态：

- Orchestration 只构造 `RuntimeLlmTurnRequest`：
  - run id / session key / selected llm id。
  - latest user input ref。
  - transcript refs。
  - context snapshot id / tree revision。
  - tool surface snapshot id。
  - provider policy / budget / authorization context。
- Orchestration 不把这些渲染成 provider input。
- LLM module 接收 canonical request 后选择 renderer。

## 4. LLM Adapter Request/Response 不对称

当前 response 侧已经在向统一 `LlmResponseItem` 收敛：

- `assistant_message`
- `reasoning`
- `tool_call`
- `tool_result`
- provider external item / metadata

但 request 侧还没有同等清晰的统一模型和 provider-specific renderer。

目标状态：

```text
Runtime canonical request
  -> provider/transport/model request renderer
  -> provider wire payload

provider wire response
  -> provider/transport/model response parser
  -> Runtime canonical response
```

这两侧必须对称、可观测、可测试。

## 架构目标

## Canonical Runtime Model

新增或重命名一组 LLM module 内部 canonical request model：

```text
RuntimeLlmRequest
  identity:
    invocation_id?
    run_id
    session_key
    llm_id

  instructions:
    stable_system
    developer_contract
    agent_identity
    runtime_policy

  context:
    context_snapshot_ref
    compact_projection
    visible_tree_refs
    artifact_refs
    memory_refs

  transcript:
    LlmInputItem[]
      message
      reasoning
      assistant_message
      tool_call
      tool_result
      provider_external

  tools:
    ToolSurfaceSnapshot
    provider_visible_tool_schemas

  options:
    reasoning_effort
    max_output_tokens
    parallel_tool_calls
    service_tier
    provider_transport
    continuation_policy

  diagnostics:
    render_inputs
    owner refs
    budget estimate
```

要求：

- 这是 runtime canonical data，不是 provider wire payload。
- 不包含 provider-specific key，例如 OpenAI 的 `previous_response_id` 或 Anthropic 的 content block 结构。
- 不包含通用 evidence judgement。
- Context Tree 以 snapshot ref / compact projection / explicit tree tool refs 出现，不默认以完整 XML prompt body 出现。

## Provider Protocol Boundary

LLM 模块新增：

```text
ProviderProtocolRenderer
  render_request(RuntimeLlmRequest) -> ProviderWireRequest

ProviderProtocolParser
  parse_response(ProviderWireResponse) -> RuntimeLlmResponse

ProviderProtocolAdapter
  render_request
  send
  parse_response
```

不同 provider / transport / model 的 renderer 独立实现：

- `OpenAICodexResponsesWebSocketRenderer`
- `OpenAICodexResponsesHttpRenderer`
- `OpenAIResponsesHttpRenderer`
- `AnthropicMessagesRenderer`
- `GeminiGenerateContentRenderer`
- `OpenAIChatCompatibleRenderer`

Renderer 选择由路由器完成：

```text
ProviderProtocolRenderRouter
  input:
    provider kind
    api family
    model capabilities
    transport
    request options

  output:
    concrete renderer
```

规则：

- 通用层只选择 renderer，不写 provider prompt。
- provider renderer 可以决定怎样降级 unsupported item，但必须记录 loss report。
- adapter 负责最终 wire payload 的形状和 response item parsing。

## Provider Capability Matrix

每个 renderer 必须声明 capability：

```text
ProviderRenderCapability
  supports_native_response_items
  supports_reasoning_items
  supports_tool_call_items
  supports_tool_result_items
  supports_previous_response_id
  supports_incremental_input
  supports_websocket_transport
  supports_parallel_tool_calls
  supports_system_developer_split
  supports_artifact_attachment
  max_wire_input_items
  fallback_mode
```

示例：

| Renderer | Transport | Request Strategy | History Strategy |
| --- | --- | --- | --- |
| Codex Responses WebSocket | websocket | `previous_response_id + delta input` | provider-native continuation |
| Codex Responses HTTP | http | full `input[]` | structured replay |
| OpenAI Responses HTTP | http | full `input[]` or supported continuation | structured replay / provider continuation |
| Anthropic Messages | http | `messages[] + tools[]` | projected message replay |
| Gemini Generate Content | http | `contents[] + tools[]` | projected content replay |
| Chat Compatible | http | `messages[] + tools[]` | lossy projected messages |

Capability matrix 应沉淀到：

- `docs/reference/llm-provider-capability-matrix.md`
- LLM profile config。
- LLM Operations detail。
- request render diagnostics。

## 模块职责重划

## Context Workspace

保留职责：

- Context Tree 节点、节点状态、展开/折叠/pin。
- session-bound context snapshot。
- provider attachment mirror 的 canonical ref。
- `context_tree.*` agent-facing 工具。
- token / size estimate。

移出职责：

- provider prompt body 生成。
- provider-specific request input rendering。
- browser evidence path ladder 作为默认 prompt/context metadata。
- evidence frontier / verified / remaining gap judgement。

目标接口：

```text
ContextWorkspaceQueryService
  get_snapshot(session_key, snapshot_id?) -> ContextSnapshot
  get_compact_projection(session_key, policy) -> ContextProjection
  list_agent_visible_tree_tools(session_key) -> ToolRefs
```

## Session

保留职责：

- conversation / item persistence。
- user-visible / model-visible / trace-visible 标记。
- provider response item mirror。
- tool call/result protocol pair refs。

目标接口：

```text
SessionReplayQueryService
  build_replay_window(session_key, policy) -> LlmInputItem[]
```

Session 不负责 provider rendering。

## Tool

保留职责：

- tool catalog。
- tool run lifecycle。
- tool result envelope。
- artifact externalization。

目标接口：

```text
ToolSurfaceQueryService
  get_tool_surface(session_key/run_id/policy) -> ToolSurfaceSnapshot
```

Tool 不负责决定 provider 如何表达 tool schema；它只提供 canonical schema。

## Orchestration

保留职责：

- run lifecycle。
- scheduler / executor / approval wait。
- response item lifecycle 推进：
  - tool call -> tool run。
  - pending approval -> wait。
  - final assistant message -> terminal。
- 构造 runtime LLM turn request 的 owner refs。

移出职责：

- provider input rendering。
- provider-specific continuation encoding。
- context tree XML prompt assembly。
- evidence judgement。

目标接口：

```text
OrchestrationEngine
  collect_runtime_llm_request(run) -> RuntimeLlmRequestDraft
  llm_service.invoke_runtime(request)
  consume RuntimeLlmResponse
```

## LLM

新增核心职责：

- Runtime canonical request model。
- Provider protocol render router。
- Provider-specific request renderer。
- Provider-specific response parser。
- Provider wire payload preview / audit。
- Render loss diagnostics。
- Transport strategy:
  - websocket continuation。
  - http full replay。
  - fallback message projection。

目标接口：

```text
LlmApplicationService.invoke_runtime(RuntimeLlmRequest) -> LlmInvocation
```

## Operations / Workbench / Trace

职责：

- 展示 runtime canonical request。
- 展示 provider wire preview。
- 展示 render strategy / fallback / loss。
- 展示 response item。
- 展示 debug-only runtime metadata。

不要：

- 从 UI 反推 provider input。
- 把 debug metadata 当作模型看见的内容。

## 数据流

## 默认 LLM 调用

```text
Orchestration run
  |
  | collect owner refs
  v
RuntimeLlmRequestDraft
  |
  | LLM service hydrates canonical request from ports
  v
RuntimeLlmRequest
  |
  | ProviderProtocolRenderRouter
  v
ProviderWireRequest
  |
  | Adapter send
  v
ProviderWireResponse
  |
  | ProviderProtocolParser
  v
RuntimeLlmResponse / LlmResponseItem[]
  |
  v
Session records response items
  |
  v
Orchestration consumes response items
```

## Context Tree 使用

默认：

```text
ContextSnapshotRef + CompactProjection -> RuntimeLlmRequest.context
```

模型主动查看：

```text
model calls context_tree.render_current/read_snapshot/diff_since
  -> Tool result
  -> Session tool_result item
  -> replayed in later RuntimeLlmRequest.transcript
```

这意味着完整树内容进入模型的唯一默认路径是：模型显式调用 tree 工具并获得 tool result。

## Provider Rendering 策略

## Codex Responses WebSocket

Renderer:

- instructions 渲染为 Codex-compatible system/developer payload。
- transcript 渲染为 Responses input items。
- tool surface 渲染为 function tools。
- 如果有 previous response state：
  - 使用 `previous_response_id`。
  - 只发送 incremental input items。
- 如果无 previous state：
  - 发送 full input。

Diagnostics:

- `render_strategy=provider_native_delta`
- `transport=websocket`
- `previous_response_id_present=true/false`
- `delta_input_item_count`
- `full_input_item_count`
- `dropped_item_count`

## Codex Responses HTTP

Renderer:

- 不使用 `previous_response_id`，除非源码和实测证明 HTTP path 支持。
- 发送 full `input[]`。
- 使用 structured replay。

Diagnostics:

- `render_strategy=structured_full_replay`
- `transport=http`
- `previous_response_id_present=false`
- `full_input_item_count`

## Anthropic Messages

Renderer:

- instructions 合并为 system/developer messages。
- reasoning item 若 provider 不支持 native reasoning，降级为 assistant-visible summary message 或 metadata-bearing message。
- tool call/result 映射到 Anthropic tool use/result blocks。
- unsupported provider external items 进入 compact diagnostic message 或丢弃并记录 loss。

Diagnostics:

- `render_strategy=message_projection`
- `loss_report.reasoning_native=false`
- `loss_report.provider_external_item_count`

## Gemini Generate Content

Renderer:

- messages / tool protocol 映射为 contents/parts。
- tool schema 映射为 Gemini function declarations。
- reasoning summary 降级为 model-visible context part，或仅 trace-visible，按 capability 决定。

## Chat Compatible

Renderer:

- 所有 structured items 降级为 role messages。
- tool call/result 尽量使用 OpenAI-compatible tool_calls/tool messages。
- 不支持的 reasoning/provider item 必须记录 loss。

## 关键设计决策

## Decision 1. Context Snapshot 不等于 Provider Prompt

`ContextSnapshot.debug_body` 进入退场路径。

短期：

- 保留字段用于 debug / tree tool output。
- provider request 不直接消费它。

中期：

- 重命名为 `rendered_tree_body` 或迁移为 `ContextSnapshot.debug_render_body`。

验收：

- provider wire preview 中不能出现完整 `<context_tree...>` body，除非模型调用 tree 工具。

## Decision 2. Provider Input 只能由 LLM Renderer 生成

禁止：

- Orchestration 拼 provider messages。
- Context Workspace 拼 provider messages。
- Operations 拼 provider messages。

允许：

- Orchestration 传 owner refs / canonical draft。
- Context Workspace 传 snapshot/projection。
- Session 传 replay items。
- Tool 传 tool surface snapshot。

验收：

- 所有 `InvokeLlmInput` 入口最终都走 `LlmApplicationService.invoke_runtime` 或同等 renderer path。

## Decision 3. Evidence / Browser Route Hint 不属于通用 Provider Input

`evidence_frontier`、`browser_evidence_path_ladder`、`browser_investigation_route_bias` 退到 debug。

短期：

- 从 `RuntimeLlmRequest.context` 默认排除。
- 从 provider request metadata 的 model-visible 区域排除。

长期：

- 若 workflow 需要业务验收，单独定义 `WorkflowEvaluator`，不污染通用 agent。

## Decision 4. Renderer 必须报告 Loss

每个 provider renderer 输出：

```text
ProviderRenderReport
  renderer_id
  render_strategy
  transport
  input_item_count
  wire_input_item_count
  dropped_item_count
  projected_item_count
  native_item_count
  loss_reasons[]
```

Operations/Workbench 展示这个 report。

## Decision 5. Request Preview 与 Wire Payload 分离

存储三层：

1. `runtime_request_summary`：canonical runtime facts。
2. `provider_render_report`：渲染策略和 loss。
3. `provider_wire_preview`：脱敏后的真实 provider payload 形状。

不要再用一个大 `request_metadata` 混所有东西。

## Phase Plan

## Phase 0. Boundary Audit

- [x] 列出所有直接构造 `LlmMessage` / `LlmInputItem` / provider metadata 的位置。
- [x] 标记 owner：
  - canonical context。
  - provider rendering。
  - debug projection。
- [x] 标记应删除/迁移的 prompt-like helper。
- [x] 输出 current dependency map。

候选文件：

- `src/crxzipple/modules/orchestration/application/runtime_llm_request_draft.py`
- `src/crxzipple/modules/orchestration/application/runtime_llm_request.py`
- `src/crxzipple/modules/orchestration/application/engine.py`
- `src/crxzipple/modules/context_workspace/application/rendering/*`
- `src/crxzipple/app/integration/context_workspace_orchestration/*`
- `src/crxzipple/modules/llm/infrastructure/adapters/*`

## Phase 1. Introduce RuntimeLlmRequest

- [x] 在 `modules/llm/domain` 或 `modules/llm/application` 新增 canonical request value objects。
- [x] 定义 `RuntimeLlmRequest`、`RuntimeLlmContext`、`RuntimeLlmTranscript`、`RuntimeToolSurfaceRef`。
- [x] 定义 `ProviderRenderReport`。
- [x] 定义 `ProviderWirePreview`。
- [x] 添加 DTO / persistence 字段。
- [x] 单元测试 canonical request serialization。

当前状态：`RuntimeLlmRequest`、`RuntimeLlmContext`、`RuntimeLlmTranscript`、`RuntimeToolSurface`、`RuntimeToolSurfaceRef` 已落地；`RuntimeLlmTranscript.items` 承载 canonical `LlmInputItem[]`。

不考虑历史兼容；允许 migration 重建数据库。

## Phase 2. Move Request Rendering Into LLM

- [x] 新增 `ProviderProtocolRenderRouter`。
- [x] 新增 renderer protocol。
- [x] 把 OpenAI/Codex Responses input item rendering 从 adapter common 中抽为 renderer。
- [x] 把 Anthropic / Gemini / Chat Compatible message projection 移入各自 renderer。
- [x] adapter send 只接受 `ProviderWireRequest`。
- [x] response parsing 保持 adapter 内，但与 renderer 共同归属 protocol adapter。

验收：

- Orchestration 不再调用 provider-specific input item helpers。
- Context Workspace 不再提供 provider prompt body 给 LLM invoke。

当前状态：`ProviderProtocolRenderRouter` 已落地，所有 renderer 暴露统一 `preview(...)` 协议。OpenAI Responses、OpenAI Codex Responses、Anthropic、Gemini、OpenAI Chat Compatible 的真实发送函数都已接收 `ProviderWireRequest` 并从中读取 endpoint/payload；provider wire rendering 与 sending 的边界完成收口。

## Phase 3. Orchestration Slimming

- [x] `RuntimeLlmRequestDraft` / `RuntimeLlmRequestPreview` 改为 `RuntimeLlmRequestDraft` / `RuntimeLlmRequestPreview`。
- [x] `prompt_input.py` 改为 `runtime_llm_request_draft.py`。
- [x] `/prompt-preview` 改为 `/llm-request-preview`。
- [x] 只收集 refs 和 canonical facts。
- [x] 删除/迁移 orchestration provider input rendering。
- [x] LLM execution item summary 记录 render report，而不是自行计算 provider input mode。
- [x] continuation 判断只基于 response items、pending tool/approval、budget。

当前状态：Orchestration 已不再拼 provider wire payload，`RuntimeLlmRequestDraftCollector` 也不再产出 prompt text blocks；它只收集 transcript、agent instruction owner fact、runtime context facts、tool refs 和 policy。原 `provider_request.py` 入口已改为 `runtime_llm_request.py`，明确其职责是把 orchestration facts 映射为 LLM canonical runtime request，不承担 provider wire rendering。原 `RuntimeLlmRequestDraft` / `prompt-preview` 外部表面也已退场，统一使用 Runtime LLM request draft / preview 命名。

保留：

- response item lifecycle。
- tool run creation。
- approval wait。
- terminal run completion。

## Phase 4. Context Workspace Reposition

- [x] 将 `ContextSnapshot` 概念收敛为 `ContextSnapshot`。
- [x] prompt body 降级为 debug render / tree tool output。
- [x] compact projection 作为 canonical context 输入。
- [x] full tree 只通过 `context_tree.render_current/read_snapshot` 工具进入 transcript。
- [x] browser evidence path metadata 移出默认 snapshot projection。

验收：

- provider wire preview 默认不包含完整 context tree body。
- `context_tree.*` 工具仍能主动读取树。

## Phase 5. Session Replay As Canonical Transcript

- [x] Session replay query 输出 `LlmInputItem[]`，不输出 provider message。
- [x] replay window policy 移到 LLM renderer 可消费的 canonical policy。
- [x] tool call/result pair normalization 留在 Session/LLM canonical 层，不进入 provider-specific code。
- [x] duplicate/orphan/missing tool protocol diagnostics 作为 render report 输入。

## Phase 6. Tool Surface As Canonical Schema

- [x] Tool module 输出 provider-neutral schema。
- [x] LLM renderer 负责 provider-specific schema mapping。
- [x] request-time tool surface snapshot 继续保存 owner facts。
- [x] provider-visible tool ids 和 dropped tool schemas 进入 render report。

## Phase 7. Operations / Workbench Observability

- [x] LLM invocation detail 展示：
  - runtime request summary。
  - provider renderer id。
  - render strategy。
  - transport。
  - wire preview。
  - loss report。
- [x] Workbench timeline 展示用户可见 item，不展示 debug-only provider metadata。
- [x] Trace 能从 run -> invocation -> provider render report -> response item 串起来。
- [x] Debug 区保留 context snapshot refs、tree revision、tool surface refs。

## Phase 8. Remove Old Prompt Assembly Paths

- [x] 删除或封存 `context_snapshot.content -> LlmMessage(system)` 路径。
- [x] 删除默认 `evidence_frontier` provider input path。
- [x] 删除 browser evidence path 默认 metadata 进入 LLM request 的路径。
- [x] 删除 Orchestration 中 provider-specific request metadata 拼装。
- [x] 文档更新：旧 prompt/render 文档标记为历史或改口径。

## 验收标准

## Functional Acceptance

- [x] Codex WebSocket run 使用 provider-native delta，wire preview 显示 `previous_response_id`。
- [x] Codex HTTP run 使用 full structured replay，wire preview 明确无 `previous_response_id`。
- [x] Anthropic/Gemini/ChatCompatible run 通过 renderer 降级，render report 记录 loss。
- [x] 同一 runtime canonical request 可被不同 renderer 渲染。
- [x] Orchestration 不直接构造 provider wire input。
- [x] Context Workspace 不直接生产 provider prompt。
- [x] full tree 内容只在 tree tool output 或 debug render 中出现。
- [x] final answer / tool call / reasoning summary 都从 response item 生命周期推进。

## Observability Acceptance

- [x] LLM Operations 可看到 renderer id / strategy / transport / loss。
- [x] Workbench 可看到用户应该看的 progress / reasoning summary / tool result excerpt / final。
- [x] Trace 可审计真实 provider input 形状。
- [x] Debug metadata 不被误认为 model-visible input。

## Regression Acceptance

- [ ] 东航任务在无 browser tool 的情况下，模型仍能从 exec 探测本地环境和站点资源。
- [ ] 如果被 WAF 阻断，最终回答能说明已验证路径和阻断原因，不伪造票价。
- [x] tool-only streak 和 validation lag 作为 Operations 指标存在，但不作为默认 runtime gate。
- [x] 不需要历史数据兼容；清库重建后通过迁移和测试。

## Test Plan

## 2026-06-15 首轮施工记录

已完成第一批“污染模型判断的旧路径”收口：

- Orchestration request builder 不再把 Context Workspace full body 或 compact projection 插入 provider messages。
- Context Surface 不再携带 `rendered_context` / prompt body；只保留 snapshot refs、node refs、provider attachment mirror 等可追踪事实。
- Orchestration engine 不再为 LLM request 生成 `runtime_loop_correction` / `runtime_evidence_frontier`。
- 删除通用 kernel 中的 `evidence_frontier_prompt.py` 与 `loop_correction.py` hint 模块及其测试。
- Tool result replay 不再输出 `task_evidence_status`、`open_gaps`、`recommended_next_actions`、`evidence_path` 等任务判断或路线偏置。
- Context Workspace session adapter / XML renderer 不再把 browser evidence path 写入 tree facts、tool result refs 或 prompt body。
- Operations / UI runtime hints 不再展示 loop correction / evidence frontier，只保留确定性的 tool protocol replay 诊断。
- Codex adapter 不再把旧 `context_workspace_projection` / `context_workspace_delta` system block 当作 incremental input。

本轮验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_tool_result_model_text.py tests/unit/test_runtime_transcript.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py tests/unit/test_context_workspace_root_nodes.py tests/unit/test_llm_adapters.py tests/unit/test_llm.py tests/unit/test_ui_http.py tests/unit/test_operations_llm_read_model.py
```

结果：`272 passed`。

额外检查：

```bash
rg -n "runtime_loop_correction|runtime_evidence_frontier|build_evidence_frontier_hint|build_loop_correction_hint|context_workspace_projection|context_workspace_delta|evidence_path:|<evidence_path>|recommended_next_actions|open_gaps|task_evidence_status" src/crxzipple -g '*.py'
```

结果：生产代码无命中。

## 2026-06-15 第二轮施工记录

已开始收敛 request DTO 所有权：

- 新增 `src/crxzipple/modules/llm/application/runtime_request.py`，由 LLM application 拥有：
  - `RuntimeLlmContext`
  - `RuntimeToolSurfaceRef`
  - `RuntimeToolSurface`
  - `RuntimeLlmRequest`
- `llm/application/__init__.py` 对外导出上述 LLM-owned runtime request DTO。
- Orchestration 不再定义这些 request DTO；只保留从 run/context/tool facts 映射到 DTO 的逻辑。
- `ProviderPromptRequestBuilder` 改名为 `RuntimeLlmRequestBuilder`，不保留旧别名，避免继续表达“Orchestration 拼 provider prompt”的旧语义。
- `engine.py` 对 `RuntimeLlmRequest` 的类型引用改为直接从 LLM application 获取。

本轮验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_llm_adapters.py tests/unit/test_llm.py tests/unit/test_ui_http.py tests/unit/test_operations_llm_read_model.py
```

结果：`191 passed`。

## 2026-06-15 第三轮施工记录

已继续收敛 LLM 调用边界：

- `RuntimeLlmRequest` 增加 `request_metadata()` 与 `response_format()`，由 LLM application request surface 统一生成调用 metadata 和 response format。
- `RuntimeLlmContext` 删除 `rendered_context` 字段；Context Tree render body 不再作为通用 request surface 字段暴露。
- `InvokeLlmInput` / `StreamLlmInput` 增加 `from_runtime_request(...)`，由 LLM application 负责把 canonical runtime request envelope 展开为 LLM 调用输入。
- `OrchestrationEngineLlmInvoker.invoke(...)` / `invoke_async(...)` 改为接收 `RuntimeLlmRequest`，不再接收拆散的 `llm_id/messages/input_items/tool_schemas/provider_options/request_metadata`。
- `engine.py` 同步改为只向 invoker 传 envelope、provider continuation、response format 和 require-tool-call policy。
- 删除 Orchestration-local `_llm_request_metadata_from_envelope` 重复实现。

边界结果：

- Orchestration 仍负责 run phase、context snapshot 收集、provider continuation 决策。
- LLM application 负责从 runtime request envelope 到 invoke/stream input 的结构展开。
- Context Tree 仍归 Context Workspace/runtime 管理，不通过 `rendered_context` 之类的泛化字段混入 LLM request surface。

本轮验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_llm.py tests/unit/test_llm_adapters.py tests/unit/test_ui_http.py tests/unit/test_operations_llm_read_model.py
```

结果：`191 passed`。

额外检查：

```bash
python -m compileall -q src/crxzipple/modules/llm/application/runtime_request.py src/crxzipple/modules/llm/application/services.py src/crxzipple/modules/orchestration/application/engine.py src/crxzipple/modules/orchestration/application/engine_llm_invoker.py
git diff --check -- src/crxzipple/modules/llm/application/runtime_request.py src/crxzipple/modules/llm/application/services.py src/crxzipple/modules/orchestration/application/engine.py src/crxzipple/modules/orchestration/application/engine_llm_invoker.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_orchestration_context_workspace_snapshot.py
```

结果：通过。

## 2026-06-15 第四轮施工记录

已继续移除 Orchestration 中的 provider 能力判断：

- 删除 `engine.py` 内未使用的 `_legacy_llm_request_metadata`。
- 删除 `engine.py` 内的 `_provider_continuation_for_prompt`、`_llm_api_family_supports_provider_continuation`、`_provider_transport_from_options`。
- `engine.py` 只从 run metadata 恢复 provider continuation 候选状态，不再根据 api family / transport / capability 判断是否可用。
- `OrchestrationEngineLlmInvoker.provider_continuation(...)` 负责读取 LLM profile，并根据 provider capabilities、api family、transport 过滤 continuation。
- Codex WebSocket continuation 测试已按抓包目标更新：WebSocket provider-native continuation 请求应携带 `previous_response_id` 并进入 input delta mode。
- 旧测试中对 `context_workspace_projection` / `context_workspace_delta` / `rendered_context` 的 model-visible 期望已改为新边界：request 不出现这些 system message 或树正文，只保留 `context_surface.snapshot_id` 等 runtime refs。

边界结果：

- Orchestration 只维护 run state 与 provider continuation state 的引用事实。
- LLM invoker/profile 边界负责判断 provider-native continuation 是否适配当前 profile/transport。
- Context Tree 仍不作为 projection/delta message 或 rendered body 默认进入 provider request。

本轮验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_orchestration_tools.py tests/unit/test_llm.py tests/unit/test_llm_adapters.py
```

结果：`149 passed`。

额外检查：

```bash
rg -n "_llm_api_family_supports_provider_continuation|_provider_continuation_for_prompt|_legacy_llm_request_metadata|rendered_context|context_workspace_projection|context_workspace_delta|runtime_loop_correction|runtime_evidence_frontier|recommended_next_actions|task_evidence_status" src/crxzipple -g '*.py'
git diff --check -- docs/reports/llm-provider-protocol-rendering-boundary-refactor-plan-20260615.md src/crxzipple/modules/llm/application/runtime_request.py src/crxzipple/modules/llm/application/services.py src/crxzipple/modules/orchestration/application/engine.py src/crxzipple/modules/orchestration/application/engine_llm_invoker.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_tools.py
```

结果：通过。

## 2026-06-15 第五轮施工记录

已开始把 provider wire rendering 从网络 adapter 中拆出：

- 新增 `src/crxzipple/modules/llm/infrastructure/adapters/openai_codex_responses_renderer.py`。
- `OpenAICodexResponsesRenderer` 负责：
  - HTTP payload render。
  - WebSocket `response.create` payload render。
  - full input item render。
  - provider-native continuation delta input 计算。
  - request preview payload render。
  - Codex instructions render。
- `OpenAICodexResponsesAdapter` 改为持有 renderer，网络/stream 代码通过 renderer 获取 payload。
- adapter 内旧的 Codex render helper 已移出，包括 provider transport 解析、delta input 计算、websocket create payload 和 reasoning payload merge。
- renderer 层曾临时防御旧 `context_workspace_projection` / `context_workspace_delta` system message；该兼容语义已在第二十轮移除。
- 旧 adapter 测试更新为：生产路径只通过 context surface refs 追踪 Context Tree，不再构造旧 projection message。

边界结果：

- Codex adapter 更接近“renderer/parser/client”拆分：renderer 管 wire request，adapter 管 credential、HTTP/WebSocket、retry、stream event parsing。
- provider/transport/model 差异进一步集中在 LLM infrastructure adapter/renderer 层，没有回流到 Orchestration 或 Context Workspace。

本轮验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py tests/unit/test_orchestration_tools.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_llm.py
```

结果：`149 passed`。

额外检查：

```bash
python -m compileall -q src/crxzipple/modules/llm/infrastructure/adapters/openai_codex_responses.py src/crxzipple/modules/llm/infrastructure/adapters/openai_codex_responses_renderer.py tests/unit/test_llm_adapters.py
git diff --check -- docs/reports/llm-provider-protocol-rendering-boundary-refactor-plan-20260615.md src/crxzipple/modules/llm/infrastructure/adapters/openai_codex_responses.py src/crxzipple/modules/llm/infrastructure/adapters/openai_codex_responses_renderer.py tests/unit/test_llm_adapters.py
```

结果：通过。

## 2026-06-15 第六轮施工记录

已把普通 OpenAI Responses 的 provider wire rendering 也从网络 adapter 中拆出：

- 新增 `src/crxzipple/modules/llm/infrastructure/adapters/openai_responses_renderer.py`。
- `OpenAIResponsesRenderer` 负责：
  - HTTP `/responses` endpoint 和 payload render。
  - provider-native `previous_response_id` 注入。
  - input item render 与 continuation delta-only 选择。
  - tool schema render。
  - reasoning/default params/provider overrides 合并。
  - provider request preview。
- `OpenAIResponsesAdapter` 改为持有 renderer，网络/stream 代码通过 renderer 获取 endpoint/payload。
- adapter 内旧的 render helper 已移除，包括 `_merged_reasoning_payload`、`_apply_provider_continuation`、`_uses_provider_native_continuation`、`_openai_response_request_input_items`。

边界结果：

- OpenAI Responses 与 OpenAI Codex Responses 都进入“renderer 负责 wire request，adapter 负责 transport + response parsing”的形态。
- Orchestration / Context Workspace 不需要理解 OpenAI provider payload 结构。

本轮验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py tests/unit/test_llm.py tests/unit/test_orchestration_tools.py tests/unit/test_orchestration_runtime_llm_request_builder.py
```

结果：`149 passed`。

额外检查：

```bash
python -m compileall -q src/crxzipple/modules/llm/infrastructure/adapters/openai_responses.py src/crxzipple/modules/llm/infrastructure/adapters/openai_responses_renderer.py
rg -n "_merged_reasoning_payload|_apply_provider_continuation|_uses_provider_native_continuation|_openai_response_request_input_items" src/crxzipple/modules/llm/infrastructure/adapters/openai_responses.py
git diff --check -- docs/reports/llm-provider-protocol-rendering-boundary-refactor-plan-20260615.md src/crxzipple/modules/llm/infrastructure/adapters/openai_responses.py src/crxzipple/modules/llm/infrastructure/adapters/openai_responses_renderer.py tests/unit/test_llm_adapters.py
```

结果：通过。

## 2026-06-15 第七轮施工记录

已把 Anthropic Messages 与 Gemini GenerateContent 的 provider wire rendering 拆出：

- 新增 `src/crxzipple/modules/llm/infrastructure/adapters/anthropic_messages_renderer.py`。
- 新增 `src/crxzipple/modules/llm/infrastructure/adapters/gemini_generate_content_renderer.py`。
- `AnthropicMessagesRenderer` 负责：
  - `/messages` endpoint render。
  - Anthropic payload render。
  - system message 合并、message 投影、tool schema、default params、overrides。
- `GeminiGenerateContentRenderer` 负责：
  - `:generateContent` endpoint render。
  - Gemini payload render。
  - contents/system instruction、generationConfig、tool declarations、toolConfig、overrides。
- `AnthropicMessagesAdapter` / `GeminiGenerateContentAdapter` 改为只做：
  - image input support check。
  - credential/header。
  - HTTP / async HTTP。
  - response payload parsing。

边界结果：

- 当前主要 provider adapter 已形成一致方向：renderer 管 provider wire request；adapter 管 transport、credential、retry/HTTP、response parsing。
- Anthropic/Gemini 不再在 adapter 主类里混合 endpoint/payload 规则。

本轮验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py tests/unit/test_llm.py
```

结果：`87 passed`。

额外检查：

```bash
python -m compileall -q src/crxzipple/modules/llm/infrastructure/adapters/anthropic_messages.py src/crxzipple/modules/llm/infrastructure/adapters/anthropic_messages_renderer.py src/crxzipple/modules/llm/infrastructure/adapters/gemini_generate_content.py src/crxzipple/modules/llm/infrastructure/adapters/gemini_generate_content_renderer.py
git diff --check -- docs/reports/llm-provider-protocol-rendering-boundary-refactor-plan-20260615.md src/crxzipple/modules/llm/infrastructure/adapters/anthropic_messages.py src/crxzipple/modules/llm/infrastructure/adapters/anthropic_messages_renderer.py src/crxzipple/modules/llm/infrastructure/adapters/gemini_generate_content.py src/crxzipple/modules/llm/infrastructure/adapters/gemini_generate_content_renderer.py
```

结果：通过。

## 2026-06-15 第八轮施工记录

本轮目标：把 `OpenAIChatCompatibleAdapter` 的请求渲染边界补齐，避免 chat-compatible 路径继续把 provider wire payload 构造逻辑留在 HTTP adapter 内部。

已完成：

- 新增 `OpenAIChatCompatibleRequestRenderer`。
- 将 chat-compatible 的 endpoint 拼接、消息顺序归一化、tool schema 渲染、response format、profile defaults、request overrides、`extra_body` merge 迁出 adapter。
- 同步调用和 SSE 流式调用复用同一个 renderer，差异仅保留 `stream=True`。
- adapter 只保留：
  - credential/header 处理。
  - HTTP/SSE transport。
  - provider response parsing。
  - response item 还原。
- chat-compatible 渲染路径现在同样以 `input_items` 为优先 replay 输入，`messages` 只作为 fallback。

边界结果：

- Orchestration 不感知 OpenAI Chat payload。
- LLM adapter 的 request rendering 与 response parsing 在模块内对称。
- 主要 provider families 均形成 `adapter + renderer` 形态：
  - OpenAI Codex Responses。
  - OpenAI Responses。
  - Anthropic Messages。
  - Gemini GenerateContent。
  - OpenAI Chat Compatible。

本轮验证：

```bash
python -m compileall -q src/crxzipple/modules/llm/infrastructure/adapters/openai_chat_compatible.py src/crxzipple/modules/llm/infrastructure/adapters/openai_chat_compatible_renderer.py
PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py tests/unit/test_llm.py
```

结果：`87 passed`。

## 2026-06-15 第九轮施工记录

本轮目标：清理“证据层”残留命名，避免把事实投影 helper 误解成通用 EvidenceGate / EvidenceOutcomeClassifier。

已完成：

- `tool_result_evidence.py` 重命名为 `tool_result_model_text.py`。
- `render_tool_result_evidence_text` 重命名为 `render_tool_result_model_text`。
- Workbench / PromptTranscript 的导入和调用同步改名。
- 局部 payload helper 从 `_tool_run_evidence_payload` 改为 `_tool_run_model_text_payload`。
- 保留的语义仅为：将 Tool owner facts / result envelope 中明确存在的字段投影为 provider transcript 可读文本。
- 不新增、不保留通用任务结论判断：
  - 不判断任务是否完成。
  - 不判断 gap / next action。
  - 不阻止 terminal。
  - 不为特定网站或特定航班任务写规则。

本轮验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_tool_result_model_text.py tests/unit/test_runtime_transcript.py tests/unit/test_workbench_read_model.py tests/unit/test_llm_adapters.py tests/unit/test_llm.py
```

结果：`109 passed`。

## 2026-06-15 第十轮施工记录

本轮目标：补齐 provider wire preview 边界，避免部分 provider 仍退回 `normalized_fallback`，导致 Operations/Trace 无法准确展示“provider 实际收到什么”。

已完成：

- 新增通用 `provider_wire_request_preview` helper。
- preview 只记录确定事实：
  - provider / api family / model。
  - endpoint / transport。
  - renderer id / render strategy。
  - provider payload keys。
  - message/content/input/tool 数量。
  - system 是否存在。
  - option summary。
  - 脱敏 payload preview。
  - RuntimeLlmContext / RuntimeToolSurface 指纹和 refs。
- `OpenAIChatCompatibleRequestRenderer.preview()` 已接入。
- `AnthropicMessagesRenderer.preview()` 已接入。
- `GeminiGenerateContentRenderer.preview()` 已接入。
- `OpenAIChatCompatibleAdapter`、`AnthropicMessagesAdapter`、`GeminiGenerateContentAdapter` 均新增 `preview_request()`。
- 当前主要 provider adapter 均具备明确 provider adapter preview：
  - OpenAI Responses。
  - OpenAI Codex Responses。
  - OpenAI Chat Compatible。
  - Anthropic Messages。
  - Gemini GenerateContent。

边界说明：

- preview 是 provider wire 形状的脱敏观测，不是给模型的额外输入。
- render report 只包含确定性渲染事实；本轮不引入推断性 loss。
- 对不支持或不确定的 provider 能力，不在 preview 中假装无损。

本轮验证：

```bash
python -m compileall -q src/crxzipple/modules/llm/infrastructure/adapters/common.py src/crxzipple/modules/llm/infrastructure/adapters/openai_chat_compatible.py src/crxzipple/modules/llm/infrastructure/adapters/openai_chat_compatible_renderer.py src/crxzipple/modules/llm/infrastructure/adapters/anthropic_messages.py src/crxzipple/modules/llm/infrastructure/adapters/anthropic_messages_renderer.py src/crxzipple/modules/llm/infrastructure/adapters/gemini_generate_content.py src/crxzipple/modules/llm/infrastructure/adapters/gemini_generate_content_renderer.py
PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py tests/unit/test_llm.py
```

结果：`90 passed`。

## 2026-06-15 第十一轮施工记录

本轮目标：让 Operations/HTTP detail 能直接展示 provider renderer 和 render report，避免使用者必须展开 `provider_request_payload_preview` JSON 才能确认渲染边界。

已完成：

- LLM Operations invocation detail 的 request context 新增：
  - `Provider Renderer`
  - `Provider Render Strategy`
  - `Provider Render Report`
- `Provider Render Report` 只展示确定性字段：
  - renderer id。
  - transport。
  - render strategy。
  - loss report 是否为空。
- 未提供 render report 的旧/异常调用显示 `-`，不生成推断性结论。
- 补充 Operations read model 单测，验证 render report 作为可读行暴露。

本轮验证：

```bash
python -m compileall -q src/crxzipple/modules/operations/application/read_models/llm.py
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_read_model.py tests/unit/test_ui_http.py
```

结果：`51 passed`。

## 2026-06-15 第十二轮施工记录

本轮目标：把 LLM owner HTTP/DTO surface 中的 provider render 事实显式化，避免只有 `provider_request_payload_preview` 一坨 JSON。

已完成：

- `LlmInvocationResponse` 新增：
  - `provider_render_report`
  - `provider_wire_preview`
- `LlmInvocationDTO` 新增同名字段。
- `provider_render_report` 从 `provider_request_payload_preview.render_report` 提取；缺失时为空 dict。
- `provider_wire_preview` 保留 provider wire preview 摘要，但移除 `render_report`，让调用方能区分：
  - provider 渲染报告。
  - provider wire preview。
  - 原始 preview payload。
- 不新增兼容分支；字段由当前 invocation truth 直接派生。

本轮验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_llm.py tests/unit/test_llm_http.py tests/unit/test_llm_adapters.py
```

结果：`98 passed`。

## Unit Tests

当前覆盖已经先落在既有测试文件中；下面的专门测试文件仍是后续整理目标。

- [x] Existing coverage: Codex renderer websocket delta / HTTP full replay / no HTTP `previous_response_id`
  - `tests/unit/test_llm_adapters.py`
- [x] Existing coverage: context snapshot refs 不作为 provider prompt / full tree body 不进默认 provider input
  - `tests/unit/test_orchestration_runtime_llm_request_builder.py`
  - `tests/unit/test_orchestration_context_workspace_snapshot.py`
  - `tests/unit/test_orchestration_tools.py`
- [x] Existing coverage: LLM Operations render report / wire preview / runtime request summary
  - `tests/unit/test_operations_llm_read_model.py`
  - `tests/unit/test_ui_http.py`
- [x] Existing coverage: provider render report 与 wire preview 分离
  - `tests/unit/test_llm.py`
  - `tests/unit/test_llm_adapters.py`
- [x] Existing coverage: provider request renderer preview protocol
  - `tests/unit/test_provider_request_renderer_protocol.py`

- [x] `test_runtime_llm_request.py`
  - canonical request serialization。
  - context snapshot refs。
  - transcript item preservation。

- [x] `test_provider_protocol_render_router.py`
  - profile capability -> renderer selection。
  - unsupported transport fallback。

- [x] `test_openai_codex_renderer.py`
  - websocket delta。
  - http full replay。
  - no HTTP `previous_response_id` unless explicitly supported。

- [x] `test_anthropic_renderer.py`
  - reasoning downgrade。
  - tool call/result mapping。
  - loss report。

- [x] `test_orchestration_runtime_llm_request.py`
  - Orchestration only builds draft/refs。
  - no provider-specific wire input in orchestration summary。

- [x] `test_context_workspace_snapshot_boundary.py`
  - snapshot != provider prompt。
  - full tree body not default provider input。

- [x] `test_operations_llm_render_report.py`
  - render report exposed。
  - wire preview distinct from runtime metadata。

## Integration Tests

- [x] Codex WebSocket fake server records `previous_response_id + delta input` after first call。
- [x] Codex HTTP fake server records full `input[]` and no `previous_response_id`。
- [x] Same canonical request rendered by Codex and Anthropic renderers has expected loss differences。
- [x] Workbench latest run timeline does not expose debug-only context tree body as chat content.

## Manual / Real Run Checks

- [ ] Run 东航 query with `openai_codex.gpt-5.5` WebSocket.
- [ ] Run same input with HTTP fallback.
- [ ] Compare:
  - model-visible transcript item count。
  - wire input item count。
  - tool call count。
  - time to first endpoint discovery。
  - time to first validation。
  - final answer fidelity。

## Migration Notes

用户已明确接受历史数据不兼容：

- 可以新增 breaking migration。
- 可以清空/rebuild LLM invocation input item 存储。
- 可以重建 Operations projection。
- 可以删除旧 prompt preview 字段。

但必须保留：

- owner module truth 边界。
- run/session/tool/llm 基本生命周期事实。
- frontend API 不显示假数据。

## 第十三轮施工记录：Operations Detail Provider 边界显性化

目标：

- 让 LLM Operations detail 不再只能从旧 `request_payload.provider_request_payload_preview` 间接观察 provider 输入。
- 将 provider renderer report 和 provider wire preview 作为一等字段暴露给 UI。
- 修正 Operations HTTP detail 缺少 `policy_trace` 的合同不一致，避免前端 drawer 依赖不存在字段。

落地：

- `LlmInvocationDetailModel` 新增：
  - `provider_render_report`
  - `provider_wire_preview`
- Operations HTTP `LlmInvocationDetailResponse` 同步暴露：
  - `provider_render_report`
  - `provider_wire_preview`
  - `policy_trace`
- 前端 runtime contract 新增同名字段。
- LLM Operations drawer 新增：
  - Provider Render Report
  - Provider Wire Preview
- i18n 同步补齐英文/中文文案。

边界说明：

- `provider_render_report` 只描述 renderer、transport、strategy、loss report 等适配层事实。
- `provider_wire_preview` 是去掉 `render_report` 后的 provider 请求预览。
- UI 不解析 Context Tree，不从 runtime hint 推断 provider 输入。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_operations_llm_read_model.py tests/unit/test_ui_http.py`
  - 51 passed
- `cd frontend && npm run typecheck`
  - passed

## 第十四轮施工记录：runtime_hints 退场为 runtime_observations

目标：

- 清理 `runtime_hints` 命名造成的边界误导。
- 明确这类数据不是给模型的提示，也不是 workflow/evidence 判断，而是给 UI/Operations 的确定性运行观察。
- 保持“不兼容、不双轨、不提供旧字段别名”的原则。

落地：

- Workbench / Trace linked LLM detail payload：
  - `runtime_hints` -> `runtime_observations`
  - `hint_count` -> `observation_count`
- Operations LLM detail：
  - `runtime_hints` -> `runtime_observations`
  - section id 改为 `runtime_observations`
- Operations HTTP response / 前端 runtime contract 同步破坏式改名。
- LLM Operations drawer 新增 Runtime Observations 区块，展示确定性的 replay/protocol/window 观察。
- 前端文案从 “Replay and loop observations” 改为 “Deterministic replay and protocol observations”。

边界说明：

- `runtime_observations` 只包含可验证运行事实，例如 tool protocol replay 诊断、response event retention policy。
- 不包含 `runtime_loop_correction`、`evidence_frontier`、browser route bias、任务结论或模型下一步建议。
- 不进入 LLM provider request；它只服务用户可见/运维可见的观察面。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_operations_llm_read_model.py tests/unit/test_ui_http.py`
  - 51 passed
- `cd frontend && npm run typecheck`
  - passed
- `rg -n "runtime_hints|runtimeHints|runtimeHint|hint_count" src/crxzipple frontend/src tests/unit/test_ui_http.py tests/unit/test_operations_llm_read_model.py -g '*.{py,ts,vue}'`
  - no matches

## 第十五轮施工记录：Context Snapshot 移除 browser/evidence route bias

目标：

- 避免 Context Snapshot metadata 继续把 `browser_evidence_path_ladder`、`browser_investigation_route_bias`、`final_response_suggests_evidence_path` 等无法形成通用准确结论的字段提升为 runtime 事实。
- 让 Context Snapshot 只记录 tree/session/tool schema/artifact/budget 等确定事实。
- 保持 browser owner 自己的 evidence metadata 不被本轮误删；本轮只处理通用 Context Workspace -> Orchestration snapshot 边界。

落地：

- `build_context_snapshot_metadata` 不再读取/提升 `estimate_breakdown["evidence"]` 到 snapshot metadata。
- 删除未使用的 `browser_investigation_affordance_metadata` 和 `_browser_evidence_path_ladder` helper。
- 删除 snapshot payload 中 `**browser_affordance` 展开。
- 相关测试改为断言 snapshot metadata 不包含 evidence/browser route bias 字段。
- 保留 `provider_request` 测试：即便外部传入旧 browser/evidence 字段，LLM request metadata 也不能携带这些字段。

边界说明：

- Context Render estimates 内部仍可统计节点类型和预算，但不会把这些推断字段提升为 orchestration snapshot runtime metadata。
- Browser/tool 模块自己的 evidence payload 是 owner 事实；是否继续保留由 Browser/Tool owner 边界单独处理。
- LLM request 仍只接收 renderer/provider 所需的确定 request metadata。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_orchestration_context_workspace_snapshot.py`
  - 51 passed
- `rg -n "browser_affordance|browser_investigation_affordance_metadata|_browser_evidence_path_ladder|browser_evidence_path_ladder|browser_investigation_route_bias|final_response_suggests_evidence_path|observed_evidence_path_count|browser_observed_evidence_path_count|uncertain_evidence_paths" src/crxzipple/app/integration/context_workspace_orchestration/snapshot_metadata.py`
  - no matches

## 第十六轮施工记录：Runtime Contract 去固定 evidence path 术语

目标：

- 清理 model-visible runtime contract / execution guide 中残留的固定 `evidence path` 术语。
- 保留“基于证据行动”的通用要求，但不把 agent 引向某个固定 browser/evidence workflow。
- 不修改 Browser owner 自己的 tool prompt；Browser 工具描述仍可表达自身能力边界。

落地：

- `runtime_contract.md`：
  - `evidence path that can make progress` -> `verifiable source that can make progress`
  - `best available evidence path` -> `best available verifiable route`
  - `materially different evidence path` -> `materially different verifiable route`
  - `materially different path or argument` -> `materially different route, argument, or source`
  - `report the evidence path` -> `report the evidence source`
- `root_nodes.py` execution guide：
  - `evidence-producing paths` -> `evidence-producing sources`
  - `switch evidence paths` -> `switch verifiable routes`
  - `materially different path` -> `materially different route`

边界说明：

- Runtime contract 仍要求 inspect / verify / report observed evidence。
- Runtime contract 不再暴露 browser-specific path ladder、route bias、terminal evidence gap 等模型可见默认指导。
- Browser/tool owner prompt 的 `verifiable browser evidence` 不在本轮删除范围；它属于工具能力说明，不属于 runtime kernel 的通用决策层。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_root_nodes.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_orchestration_context_workspace_snapshot.py`
  - 71 passed
- `rg -n "evidence path|Evidence path|browser_evidence_path_ladder|browser_investigation_route_bias|final_response_suggests_evidence_path|runtime_loop_correction|runtime_evidence_frontier|runtime_hints|hint_count" src/crxzipple/modules/orchestration src/crxzipple/modules/llm src/crxzipple/app/integration/context_workspace_orchestration src/crxzipple/modules/context_workspace/application/prompts/runtime_contract.md src/crxzipple/modules/context_workspace/application/root_nodes.py -g '*.{py,md}'`
  - no matches

## 第十七轮施工记录：Context Render / UI 移除旧证据路线推断

目标：

- 继续落实“无法形成准确结论的内容不要发送给 LLM，也不要在运维面暗示它是 runtime 事实”。
- 移除 Context Render estimate、Operations Context Workspace read model、Workbench/Trace UI 中围绕 `final evidence`、browser route、browser warning、evidence path ladder 的旧推断展示。
- 保留通用、确定的事实统计：session evidence 数量、verified evidence refs、uncertain evidence refs。

落地：

- `context_workspace/application/rendering/estimates.py`：
  - `evidence_path_breakdown` 改为 `evidence_observation_breakdown`。
  - 输出字段收敛为：
    - `session_evidence_count`
    - `observed_evidence_count`
    - `observed_evidence_refs`
    - `uncertain_evidence_count`
    - `uncertain_evidence_refs`
  - 删除 browser investigation warning helper 和旧 `__all__` 暴露。
- Operations Context Workspace read model：
  - 删除 `investigation_warnings` section。
  - 删除 render snapshot 表格中的 `browser_warnings`、`browser_warning_types`、`terminal_fact_gap` 列。
  - 删除 `Investigation Warnings` metric。
- Workbench / Trace：
  - 删除 Route Diagnostics 中 `Browser Route` / `Browser Warnings` / `Final Evidence` 卡片。
  - 删除 Trace 中 `Evidence Path Ladder` 和 browser warning 明细表。
  - 用户可见的默认能力组文案改为“默认工具组 / Default Tool Groups”，不再绑定 browser。
- 测试：
  - 用新的 evidence observation 统计测试替换旧 final-response suggestion 测试。
  - Operations module section 测试移除 `investigation_warnings`。

边界说明：

- Browser owner 内部的 `browser_evidence_path_ladder_payload` 暂不在本轮删除范围；它属于 browser 工具自身能力描述，不属于 Context Render / provider request / Operations Context Workspace 的通用事实层。
- 本轮不新增 workflow/evidence gate，不引入任务特化判断。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_context_snapshot_metadata.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_operations_context_workspace_read_model.py tests/unit/test_ui_http.py`
  - 108 passed
- `cd frontend && npm run typecheck`
  - passed
- `python -m compileall -q src/crxzipple/modules/context_workspace/application/rendering/estimates.py src/crxzipple/modules/operations/application/read_models/context_workspace.py`
  - passed
- `rg -n "final_response_suggests_evidence_path|observed_evidence_path_count|observed_evidence_paths|browser_observed_evidence|uncertain_evidence_paths|browser_evidence_path_no_terminal_fact|browser_investigation_route_bias|browser_investigation_affordance|browser_investigation_warning_count|browser_investigation_warning_types|evidence_path_breakdown|routeFinalEvidence|routeEvidencePath|routeBrowserAffordance|routeBrowserWarnings|routePresentPathsShort|routeMissingPathsShort|routeSchemasVisibleShort|investigation_warnings" src/crxzipple/modules/context_workspace src/crxzipple/app/integration src/crxzipple/modules/orchestration src/crxzipple/modules/operations frontend tests/unit/test_context_snapshot_metadata.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_ui_http.py -g '*.{py,ts,vue,md}'`
  - no matches

## 第十八轮施工记录：拆除 Orchestration evidence frontier 账本

目标：

- 按最新原则继续去掉“无法准确形成结论的流程”：Orchestration 不再把工具结果二次归纳成 `evidence_frontier`。
- 让工具结果只通过 owner 事实进入后续上下文：
  - tool run truth
  - tool result session item
  - execution step item
  - tool run link
  - provider transcript renderer
- Baseline 不再依赖 evidence frontier 兜底判断 discovery / validation / tool result contract。

落地：

- `engine.py`：
  - `EngineAdvanceOutcome` 删除 `evidence_frontier`。
  - `_advance_outcome_from_tool_execution` 不再 merge tool result evidence items。
  - 删除 `evidence_frontier_for_tool_runs` 和 `_merge_evidence_frontier`。
- `engine_tool_executor.py`：
  - `ToolExecutionBatchOutcome` 删除 `evidence_frontier_items`。
  - 工具执行完成后不再调用 `tool_run_evidence_frontier_item`。
  - 删除 `tool_run_evidence_frontier_item` 及只服务该结构的摘要/status helper。
- `execution.py` / `waiting.py` / `tool_resume.py`：
  - run metadata 不再写入 `evidence_frontier`。
  - background tool resume 不再携带 evidence frontier metadata。
- `loop_regression_baseline.py`：
  - 删除对 `run.metadata.evidence_frontier` 的读取。
  - 删除 evidence frontier count / verified / gap / failed path 指标。
  - discovery / validation 只从 execution step item summary payload 读取；没有事实则 `metrics_missing` 暴露缺口。
- 测试：
  - 删除旧 `runtime_evidence_frontier` / `evidence_frontier` negative tests 和 fixtures。
  - 工具结果测试改为断言 tool run link 与 model-visible tool result session item。

边界说明：

- 本轮不改变 tool result envelope、session item replay、response item replay。
- 本轮不新增 EvidenceGate、workflow evaluator 或任务特化判断。
- Runtime 不再维护通用 evidence ledger；具体任务的证据组织后续属于 skill / workflow / domain 层，而不是 agent loop 内核。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_orchestration_tools.py tests/unit/test_orchestration_loop_regression_baseline.py`
  - 42 passed
- `PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_ui_http.py tests/unit/test_orchestration_loop_regression_baseline.py`
  - 103 passed
- `PYTHONPATH=src pytest -q tests/unit/test_orchestration_tools.py::OrchestrationToolsTestCase::test_tool_result_session_item_uses_result_envelope_payload tests/unit/test_orchestration_tools.py::OrchestrationToolsTestCase::test_background_tool_completion_event_resumes_run_and_allows_next_turn`
  - 2 passed
- `python -m compileall -q src/crxzipple/modules/orchestration/application/engine.py src/crxzipple/modules/orchestration/application/engine_tool_executor.py src/crxzipple/modules/orchestration/application/execution.py src/crxzipple/modules/orchestration/application/coordinators/waiting.py src/crxzipple/modules/orchestration/application/tool_resume.py src/crxzipple/modules/orchestration/application/loop_regression_baseline.py`
  - passed
- `rg -n "runtime_evidence_frontier|evidence_frontier|tool_run_evidence_frontier_item|evidence_frontier_items|_merge_evidence_frontier|_evidence_frontier_for_tool_runs" src tests/unit -g '*.py'`
  - no matches

## 第十九轮施工记录：清理 loop correction 残留

目标：

- 继续落实“不要让无法穷举的阈值流程干扰 LLM 判断”。
- 既然 `runtime_loop_correction` 已不再由生产代码生成，也不再进入 provider input / Operations runtime observations，测试和 fixture 不应继续围绕它写负向兼容断言。
- 保留 `llm_loop_diagnostic`：它是单次 LLM terminal response 缺少有效 final/tool action 时的确定失败原因，不是跨轮探索策略。

落地：

- `root_nodes.py`：
  - Current Execution summary 删除 `evidence frontier`，改为 `tool results`。
- `test_orchestration_runtime_llm_request_builder.py`：
  - 删除 `runtime_loop_correction` 旧 snapshot metadata 负向测试。
- `test_orchestration_context_workspace_snapshot.py`：
  - 删除 `runtime_loop_correction` 旧 prompt block 负向测试。
- `test_ui_http.py`：
  - linked LLM detail fixture 删除 `runtime_loop_correction`。
  - 删除 `runtime_observations` 中不包含 loop correction 的旧负向断言。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_ui_http.py tests/unit/test_context_workspace_root_nodes.py`
  - 99 passed
- `python -m compileall -q src/crxzipple/modules/context_workspace/application/root_nodes.py`
  - passed
- `rg -n "runtime_loop_correction|loop_correction|runtime_evidence_frontier|evidence_frontier" src tests/unit frontend -g '*.{py,ts,vue}'`
  - no matches

## 第二十轮施工记录：Codex Renderer 移除旧 Context Projection Block 兼容语义

目标：

- 继续贯彻“不兼容旧结构、不双轨并行”。
- Codex provider renderer 不再识别 `context_workspace_projection` / `context_workspace_delta` 这类旧 prompt block。
- Context Tree 的 provider 可观测引用只通过 `RuntimeLlmContext` / request metadata / render report 表达；不再通过额外 system message 进入 Codex instructions。
- Provider preview / Operations surface 不把 `rendered_context` / prompt body 纳入 context surface fingerprint。

落地：

- `openai_codex_responses_renderer.py`：
  - 删除 `system_message_is_provider_instruction`。
  - `resolve_instructions(...)` 只合并当前 request 中真实的 system messages。
  - renderer 不再包含旧 context projection / delta block 特判。
- `test_llm_adapters.py`：
  - 将旧 “context projection metadata does not create input item” 测试改为 “context surface metadata does not create input item”。
  - 测试不再构造 `context_workspace_projection` system message；改为通过 `request_metadata.context_surface` 验证 Context Tree ref 不会进入 Responses `input[]`。
- `llm.application.runtime_request`：
  - 新增 `context_surface_preview_payload(...)`，作为 context surface preview/fingerprint 的唯一 allow-list helper。
- `llm.infrastructure.adapters.common` 与 `llm.application.services`：
  - `context_surface_fingerprint` 改为基于 allow-list 后的 preview surface 计算。
  - 两处 preview 路径共用 `context_surface_preview_payload(...)`，不再各自维护一套字段判断。
  - allow-list 只保留 snapshot/ref/estimate/provider attachment/diagnostics 等结构化字段。
  - 显式不把 `rendered_context`、`debug_body` 这类树正文纳入 preview fingerprint。
- 相关测试：
  - 删除测试 fixture 中主动塞入 `rendered_context` 的数据。
  - 将旧 projection/delta 负向断言改为检查 provider messages 中没有 `<context_tree>` 正文。

边界结果：

- Codex renderer 只处理当前 canonical request item 与 provider wire payload。
- 旧 Context Workspace projection/delta system block 不再作为合法 provider input 形态存在。
- Context Tree 仍由 runtime 维护；provider/transport 渲染层只消费明确的 request item、tool schema、metadata ref 和 adapter options。
- Context surface preview 是可审计 refs，而不是树正文或 prompt body 的旁路承载。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py -k 'openai_codex_context_surface_metadata or openai_codex'`
  - 25 passed
- `PYTHONPATH=src pytest -q tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_llm_adapters.py -k 'context or codex'`
  - 56 passed
- `PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py tests/unit/test_llm.py tests/unit/test_operations_llm_read_model.py`
  - 91 passed
- `PYTHONPATH=src pytest -q tests/unit/test_ui_http.py -k 'llm or context_surface or linked'`
  - 11 passed, 39 deselected
- `PYTHONPATH=src pytest -q tests/unit/test_turns_http.py`
  - 10 passed
- `python -m compileall -q src/crxzipple/modules/llm/infrastructure/adapters/openai_codex_responses_renderer.py tests/unit/test_llm_adapters.py`
  - passed
- `python -m compileall -q src/crxzipple/modules/llm/infrastructure/adapters/common.py src/crxzipple/modules/llm/application/services.py src/crxzipple/modules/llm/infrastructure/adapters/openai_codex_responses_renderer.py tests/unit/test_llm_adapters.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_tools.py tests/unit/test_ui_http.py tests/unit/test_turns_http.py`
  - passed
- `rg -n "context_workspace_projection|context_workspace_delta|system_message_is_provider_instruction" src/crxzipple/modules/llm tests/unit/test_llm_adapters.py -g '*.py'`
  - no matches

## 第二十一轮施工记录：Runtime Request Summary 成为一等观测字段

目标：

- 继续把“模型输入相关事实”从万能 `request_metadata` 中拆出来。
- Operations / event consumer 不再只能通过解析大块 metadata 理解 invocation 的 runtime request 形态。
- Runtime request summary 只包含确定摘要和 refs，不包含树正文、prompt body 或 provider wire payload。

落地：

- `llm.application.services`：
  - 新增 `_runtime_request_summary(invocation)`。
  - `llm.invocation_started` event 增加 `runtime_request_summary`。
  - `llm.invocation_provider_request_prepared` event 增加 `runtime_request_summary`。
  - summary 包含 message/input/tool 计数、input item kinds、context snapshot id、input mode、runtime contract hash/version、tool protocol refs、context surface refs、tool surface摘要。
  - context surface summary 复用 `context_surface_preview_payload(...)`，不会携带 `rendered_context` / `debug_body`。
- `operations.application.read_models.llm`：
  - `LlmInvocationDetailModel` 增加 `runtime_request_summary`。
  - detail 构造时生成 runtime request summary。
  - context surface summary 复用 LLM request model 的 allow-list helper。
- `operations.interfaces.http_models` / `frontend`：
  - LLM invocation detail HTTP response 增加 `runtime_request_summary`。
  - frontend runtime contract 增加字段。
  - LLM Operations drawer 增加 Runtime Request Summary 区块。
  - i18n 增加中英文文案。

边界结果：

- Operations drawer 现在分为三层：
  - Runtime Request Summary：runtime canonical 摘要和 refs。
  - Provider Render Report：renderer/transport/strategy/loss。
  - Provider Wire Preview：脱敏后的 provider wire 形状。
- `request_metadata` 仍作为底层持久化事实保留，但不再是唯一可观察入口。
- 本轮不新增 provider/task 特化逻辑，也不把不可结论化的 evidence/route 判断送给 LLM。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_llm.py -k 'provider_request_prepared_event'`
  - 1 passed, 19 deselected
- `PYTHONPATH=src pytest -q tests/unit/test_operations_llm_read_model.py`
  - 1 passed
- `PYTHONPATH=src pytest -q tests/unit/test_ui_http.py -k 'llm or context_surface or linked'`
  - 11 passed, 39 deselected
- `cd frontend && npm run typecheck`
  - passed

## 第二十二轮施工记录：补齐 Runtime LLM Request Canonical Serialization 测试

目标：

- 把已落地的 canonical request DTO 变成有独立测试保护的边界。
- 先用当前真实类型 `RuntimeLlmRequest` / `RuntimeLlmContext` / `RuntimeToolSurface` 固化行为，不提前做未完成的 `RuntimeLlmRequest*` 命名迁移。
- 为后续正式重命名和 ProviderWireRequest 强类型化提供回归网。

落地：

- 新增 `tests/unit/test_runtime_llm_request.py`：
  - 验证 `RuntimeLlmRequest.to_payload()` 能序列化 messages、input_items、tool_schemas、context surface、tool surface、blocked tool access。
  - 验证 `RuntimeLlmRequest.request_metadata()` 把 runtime refs / surfaces / options 合成调用 metadata，但不变成 provider wire payload。
  - 验证 `context_surface_preview_payload(...)` 会过滤 `rendered_context` / `debug_body`，只保留 snapshot/ref/attachment 等 allow-list 字段。
- Phase 1 checklist 更新：
  - `单元测试 canonical request serialization` 已完成。
  - `test_runtime_llm_request.py` 已完成。

边界结果：

- 当前 canonical request surface 有独立测试，不再只靠 orchestration builder 间接覆盖。
- 树正文不进入 context surface preview 的规则有专门单测。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_runtime_llm_request.py`
  - 3 passed
- `python -m compileall -q tests/unit/test_runtime_llm_request.py src/crxzipple/modules/llm/application/runtime_request.py`
  - passed

## 第二十三轮施工记录：Provider Request Renderer Protocol 与 OpenAI Preview Report 统一

目标：

- 让 provider request renderer 不只是文件命名一致，而有一个最小统一 protocol。
- 先定义所有 renderer 都已经具备的 `preview(profile, request)` 边界，不强行把 Codex HTTP/WebSocket 和 Chat stream 的 `render(...)` 差异塞进过宽接口。
- 让 OpenAI Responses / Codex Responses preview 与 Anthropic/Gemini/ChatCompatible 一样，稳定输出 `renderer_id`、`render_strategy`、`render_report`。

落地：

- 新增 `llm.infrastructure.adapters.provider_protocol.ProviderRequestPreviewRenderer`。
  - 要求 renderer 暴露 `renderer_id`。
  - 要求 renderer 暴露 `preview(profile, request)`。
- `OpenAICodexResponsesRenderer`：
  - 新增 `renderer_id="openai_codex_responses"`。
  - preview 调用显式传入 renderer id。
- `OpenAIResponsesRenderer`：
  - 新增 `renderer_id="openai_responses"`。
  - preview 调用显式传入 renderer id。
- `openai_provider_request_preview(...)`：
  - 增加 `renderer_id` / `render_strategy` 参数。
  - 输出统一 `renderer_id`、`render_strategy`、`render_report`。
  - provider-native delta 时 render strategy 自动反映为 `provider_native_delta`。
- 新增 `tests/unit/test_provider_request_renderer_protocol.py`。
- `test_llm_adapters.py` 增加 OpenAI/Codex preview render report 断言。

边界结果：

- Provider renderer 的最小共同面明确为 preview protocol。
- Operations 读取 OpenAI/Codex preview 时不再需要特殊处理缺失 renderer report 的情况。
- 本轮没有引入 router，也没有强行统一所有 provider wire request 的 render 方法；这些仍留给后续 `ProviderProtocolRenderRouter` / `ProviderWireRequest` 阶段。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_provider_request_renderer_protocol.py`
  - 2 passed
- `PYTHONPATH=src pytest -q tests/unit/test_provider_request_renderer_protocol.py tests/unit/test_llm_adapters.py -k 'preview_includes_surface_fingerprints or previews_provider_request or provider_request_renderers'`
  - 3 passed, 69 deselected
- `python -m compileall -q src/crxzipple/modules/llm/infrastructure/adapters/provider_protocol.py src/crxzipple/modules/llm/infrastructure/adapters/common.py src/crxzipple/modules/llm/infrastructure/adapters/openai_codex_responses_renderer.py src/crxzipple/modules/llm/infrastructure/adapters/openai_responses_renderer.py tests/unit/test_provider_request_renderer_protocol.py tests/unit/test_llm_adapters.py`
  - passed

## 第二十四轮施工记录：Provider Protocol Render Router 最小落地

目标：

- 把 provider/transport/model 渲染选择收束到 LLM adapter 基础设施层，而不是让 orchestration 或 context workspace 判断 provider wire 形状。
- 先落最小 router：按 `LlmApiFamily` 选择 provider renderer，并复用 renderer 自己的 `preview(profile, request)`。
- 不在 router 里加入任务特化、证据判断、站点规则或 workflow gate。

落地：

- 新增 `llm.infrastructure.adapters.provider_router.ProviderProtocolRenderRouter`。
  - `OPENAI_RESPONSES -> OpenAIResponsesRenderer`
  - `OPENAI_CODEX_RESPONSES -> OpenAICodexResponsesRenderer`
  - `ANTHROPIC_MESSAGES -> AnthropicMessagesRenderer`
  - `GEMINI_GENERATE_CONTENT -> GeminiGenerateContentRenderer`
  - `OPENAI_CHAT_COMPATIBLE -> OpenAIChatCompatibleRequestRenderer`
- `adapters.__init__` 导出 `ProviderProtocolRenderRouter`。
- 新增 `tests/unit/test_provider_protocol_render_router.py`：
  - 验证不同 `api_family` 会选中对应 renderer。
  - 验证 router preview 输出统一 `renderer_id` / `render_report`。
  - 验证 Codex websocket transport 仍由 Codex renderer 处理。
  - 验证不支持的 `OLLAMA_NATIVE` 明确失败。

边界结果：

- Renderer selection 有了单一入口。
- Router 不持有 Context Tree，不生产 prompt，不解释 evidence。
- 后续 adapter send 改成只接受 `ProviderWireRequest` 时，可以复用这个路由入口继续向下收束。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_provider_protocol_render_router.py`
  - 7 passed
- `python -m compileall -q src/crxzipple/modules/llm/infrastructure/adapters/provider_router.py tests/unit/test_provider_protocol_render_router.py`
  - passed

## 第二十五轮施工记录：Codex Renderer 独立边界测试

目标：

- 把 Codex provider wire 形状从大 adapter 测试中拆出独立 renderer 测试。
- 直接验证 renderer 行为：HTTP 全量回放、WebSocket provider-native delta、delta 不安全时回退全量 replay。
- 保持内核通用，不加入东航、浏览器、站点或 evidence 特化判断。

落地：

- 新增 `tests/unit/test_openai_codex_renderer.py`：
  - `test_openai_codex_renderer_http_uses_full_replay_without_previous_response_id`
  - `test_openai_codex_renderer_websocket_uses_provider_native_delta`
  - `test_openai_codex_renderer_websocket_falls_back_to_full_replay_when_delta_is_not_safe`
- Test plan 中 `test_openai_codex_renderer.py` 勾选完成。

边界结果：

- Codex HTTP 路径明确不发送 `previous_response_id`。
- Codex WebSocket 仅在 continuation baseline 安全匹配时发送 `previous_response_id + delta input`。
- 当 continuation 缺少可验证 baseline 时，WebSocket renderer 回退为 full wire payload，不向模型发送不可靠增量。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_openai_codex_renderer.py`
  - 3 passed
- `python -m compileall -q tests/unit/test_openai_codex_renderer.py`
  - passed

## 第二十六轮施工记录：Anthropic Renderer 独立边界测试与 Reasoning Summary 降级修正

目标：

- 把 Anthropic Messages wire 形状从 adapter 测试中拆出独立 renderer 测试。
- 固化 provider-neutral `LlmInputItem[]` 到 Anthropic messages 的降级行为。
- 不在 renderer 中加入任务特化，只验证通用 tool/reasoning 映射。

落地：

- 新增 `tests/unit/test_anthropic_renderer.py`：
  - 验证 projected tool call/result 映射为 Anthropic `tool_use` / `tool_result`。
  - 验证 reasoning item 降级为 assistant text。
  - 验证 preview 输出 `renderer_id`、`render_report`、wire shape，并且 context surface preview 不包含 debug prompt body。
- 修正 `messages_from_projected_input_items(...)` 的 reasoning summary list 降级：
  - 以前会把 `{"type":"summary_text","text":"..."}` 直接 `str(dict)` 进 assistant 文本。
  - 现在优先抽取 `text` 字段，再拼接为干净 summary text。
- Test plan 中 `test_anthropic_renderer.py` 勾选完成。

边界结果：

- Anthropic renderer 的 tool/reasoning 降级行为有独立回归测试。
- Reasoning summary replay 进入非 Responses provider 时不再污染为 Python dict 字符串。
- `render_report.loss_report` 当前仍只记录为空对象；后续若要记录具体降级损失，需要基于 renderer 可证明事实补充，不提前猜测。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_anthropic_renderer.py tests/unit/test_openai_codex_renderer.py`
  - 6 passed
- `python -m compileall -q src/crxzipple/modules/llm/infrastructure/adapters/common.py tests/unit/test_anthropic_renderer.py`
  - passed

## 第二十七轮施工记录：Operations LLM Render Report 专门测试

目标：

- 把 Operations detail 中的 `provider_render_report` / `provider_wire_preview` 分离行为做成独立测试。
- 避免只依赖大综合 read model 测试来保护调试边界。
- 固定用户可观察的 request context label：renderer、render strategy、render report、input delta。

落地：

- 新增 `tests/unit/test_operations_llm_render_report.py`：
  - 构造最小 `LlmInvocation.provider_request_payload_preview`。
  - 验证 `provider_render_report` 原样提取 `render_report`。
  - 验证 `provider_wire_preview` 移除 `render_report`，但保留 wire 预览事实。
  - 验证 request context 中 provider renderer / strategy / delta label 可读。
- Test plan 中 `test_operations_llm_render_report.py` 勾选完成。

边界结果：

- Operations detail 不再把 render report 和 wire payload preview 混成一个调试对象。

### 2026-06-16: Provider Input Item Mapping

- Provider renderer preview now records `render_report.input_item_mapping` when
  canonical `LlmInputItem` records are present.
- Mapping rows are deterministic renderer facts:
  - `provider_payload_index`
  - `input_item_index`
  - `input_item_kind`
  - `input_item_source`
  - optional `context_slice_item_id`
  - optional `context_slice_node_id`
  - optional owner/session/tool refs carried by `LlmInputItem.metadata`
- Operations LLM detail projects the mapping as `Provider Context Mapping`.
- This is a renderer/Operations projection only. Orchestration does not inspect
  provider payload structure, and no task-specific evidence logic is introduced.
- Empty mappings are omitted from render report to avoid noisy provider previews.

### 2026-06-16: Response Runtime Mapping

- Operations LLM detail now exposes `Response Runtime Mapping`.
- The table links normalized provider response facts to runtime semantics:
  - provider item id/type
  - `LlmResponseItem` id/sequence/kind/phase
  - `runtime_semantic_kind`
  - role, tool name, call id, model/user visibility
- Runtime semantic labels reuse the Session runtime response projector contract via
  `runtime_semantic_kind_from_llm_response_item`; Operations does not duplicate
  provider-specific parsing rules.
- The mapping starts from provider-neutral `LlmResponseItem` records, not raw
  stream events. Raw provider event inspection remains the responsibility of the
  response event table.
- UI/HTTP 层后续可以稳定展示“模型/Provider 实际看到的 wire shape”和“适配层如何渲染”的两类事实。
- 本轮没有改变 runtime 判断逻辑，也没有增加任何任务特化。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_operations_llm_render_report.py`
  - 1 passed
- `python -m compileall -q tests/unit/test_operations_llm_render_report.py`
  - passed

## 第二十八轮施工记录：Context Snapshot Provider Boundary 专门测试

目标：

- 把 “Context Snapshot 不是 provider prompt” 做成独立测试。
- 验证 Context Workspace 可以持有完整 `debug_body` / tree body，但默认 provider request preview 不包含这些正文。
- 保持 Context Tree 是 runtime 管理对象，provider-visible 内容由 LLM renderer 输出。

落地：

- 新增 `tests/unit/test_context_workspace_snapshot_boundary.py`：
  - 构造包含明显 `<context_tree>...` marker 的 `ContextSnapshotRecord`。
  - 通过 `RuntimeLlmRequestBuilder.request_envelope(...)` 生成 canonical envelope。
  - 验证 `envelope.messages`、`envelope.transcript.items`、`context_surface.to_payload()` 都不包含 tree body。
  - 再通过 `OpenAIResponsesRenderer.preview(...)` 验证 provider wire preview 中也不包含 tree body。
- Test plan 中 `test_context_workspace_snapshot_boundary.py` 勾选完成。

边界结果：

- Context snapshot refs 可以进入 runtime metadata/context surface。
- Full tree body 不会作为默认 provider prompt 或 provider preview 发送给模型。
- Tree 当前状态需要模型主动查看时，应通过 `context_tree.*` 工具，而不是默认塞入 provider input。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_snapshot_boundary.py`
  - 1 passed
- `python -m compileall -q tests/unit/test_context_workspace_snapshot_boundary.py`
  - passed

## 第二十九轮施工记录：Orchestration Runtime Request Boundary 专门测试

目标：

- 把 orchestration 只构造 runtime canonical request / refs 的约束做成独立测试。
- 防止 provider wire 字段重新混入 orchestration request summary 或 metadata。
- 保持 provider wire payload 只由 LLM renderer/adapter 生成。

落地：

- 新增 `tests/unit/test_orchestration_runtime_llm_request.py`：
  - 通过 `RuntimeLlmRequestBuilder.request_envelope(...)` 构造 canonical envelope。
  - 验证 context surface / tool surface / reasoning config / output contract / provider options 均作为 runtime facts 保存。
  - 验证 `input`、`tools`、`previous_response_id`、`stream`、`model`、`payload_preview`、`render_report` 等 provider wire/debug 字段不进入 orchestration metadata/provider options/context surface。
  - 验证 Context Tree debug body 不进入 envelope payload。
- Test plan 中 `test_orchestration_runtime_llm_request.py` 勾选完成。

边界结果：

- Orchestration 的职责进一步固定为收集 facts 和 refs。
- Provider-specific wire assembly 继续留在 LLM renderer/adapter。
- 这一步没有增加兼容层，也没有引入任何任务特化判断。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_orchestration_runtime_llm_request.py`
  - 1 passed
- `python -m compileall -q tests/unit/test_orchestration_runtime_llm_request.py`
  - passed

## 第三十轮施工记录：同一 Canonical Request 跨 Renderer 集成测试

目标：

- 验证同一份 provider-neutral canonical request 可以由不同 provider renderer 渲染成各自最合适的 wire shape。
- 固化 Codex Responses 与 Anthropic Messages 对 reasoning input item 的差异：
  - Codex 保留 native reasoning item。
  - Anthropic 降级为 assistant text。
- 只记录可证明的 loss，不推断任务成功率或站点能力。

落地：

- `provider_wire_request_preview(...)` 增加 `loss_report` 参数，默认仍为空对象。
- `AnthropicMessagesRenderer.preview(...)` 在存在 canonical `REASONING` input item 时记录：
  - `loss_report.reasoning.input_item_count`
  - `loss_report.reasoning.strategy = assistant_text_downgrade`
- 新增 `tests/unit/test_provider_renderer_canonical_request_integration.py`：
  - 用同一份 `LlmAdapterRequest.input_items` 同时渲染 Codex 和 Anthropic。
  - 验证 Codex wire payload 包含 native `type=reasoning` item，loss 为空。
  - 验证 Anthropic wire payload 将 reasoning 转为 assistant text，并记录 loss report。
- `tests/unit/test_anthropic_renderer.py` 增加 reasoning downgrade loss report 断言。
- Integration checklist 中 “Same canonical request rendered by Codex and Anthropic renderers...” 勾选完成。

边界结果：

- Provider render loss report 开始承载 renderer 能准确证明的降级事实。
- Runtime canonical request 不需要为 provider 差异分叉；差异集中在 renderer。
- 仍不引入任务特化、workflow gate 或 evidence 判断。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_provider_renderer_canonical_request_integration.py tests/unit/test_anthropic_renderer.py tests/unit/test_openai_codex_renderer.py`
  - 8 passed
- `python -m compileall -q src/crxzipple/modules/llm/infrastructure/adapters/common.py src/crxzipple/modules/llm/infrastructure/adapters/anthropic_messages_renderer.py tests/unit/test_provider_renderer_canonical_request_integration.py tests/unit/test_anthropic_renderer.py`
  - passed

## 第三十一轮施工记录：Codex Transport Wire Contract Fake Server 测试

目标：

- 不只验证 preview，也验证 adapter 实际发送给 provider transport 的 JSON。
- 用 fake WebSocket / fake HTTP stream server 固化 Codex WebSocket delta 与 HTTP full replay 的差异。
- 保持测试在 provider transport 层，不引入任何业务任务特化。

落地：

- 新增 `tests/unit/test_openai_codex_transport_wire_contract.py`：
  - `test_codex_websocket_fake_server_records_previous_response_id_and_delta_input`
    - 真实走 `OpenAICodexResponsesAdapter.invoke(...)` 的 websocket 分支。
    - fake websocket 捕获发送 payload。
    - 验证 `type=response.create`、`previous_response_id=resp_previous`、`input[]` 只有 `function_call_output` delta。
  - `test_codex_http_fake_server_records_full_input_without_previous_response_id`
    - 真实走 `OpenAICodexResponsesAdapter.invoke(...)` 的 HTTP stream 分支。
    - fake HTTP stream 捕获 `requests.post(... json=payload)`。
    - 验证 HTTP payload 不包含 `previous_response_id`，并发送完整 `input[]`。
- Integration checklist 中两项 Codex transport fake server 验证勾选完成。

边界结果：

- WebSocket provider-native continuation 与 HTTP full replay 的行为由实际 adapter 发送路径保护。
- Codex HTTP 继续不发送 `previous_response_id`。
- Codex WebSocket 只有在 baseline 可验证时发送 `previous_response_id + delta input`。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_openai_codex_transport_wire_contract.py`
  - 2 passed
- `python -m compileall -q tests/unit/test_openai_codex_transport_wire_contract.py`
  - passed

## 第三十二轮施工记录：Workbench Timeline Debug Payload 隔离

目标：

- 确保 Workbench latest run timeline 展示用户可见的 assistant/progress/reasoning/tool result 内容。
- 防止 debug-only context tree body、provider request preview、runtime request summary 被当成聊天内容展示。
- 收口 Integration checklist 最后一项。

落地：

- `workbench._timeline_content_from_response_item(...)` 增加 timeline payload sanitizer。
  - 移除 `debug_body`、`rendered_context`、`provider_request_payload_preview`、`provider_wire_preview`、`runtime_request_summary`、`render_report` 等 debug-only 字段。
  - 保留用户可见 `text/summary` 等内容。
- `tests/unit/test_workbench_read_model.py` 新增 `test_workbench_timeline_hides_debug_only_context_tree_payload`：
  - 构造带 `<context_tree>...` debug body 的 assistant response item。
  - 构造 hidden reasoning item。
  - 验证 timeline 只展示 assistant text 和 hidden reasoning placeholder。
  - 验证 timeline 中不出现 `<context_tree>`。
- Integration checklist 中 Workbench timeline 项勾选完成。

边界结果：

- Workbench timeline 不再把 provider/debug payload 误当成用户聊天消息。
- Debug metadata 仍可在 debug/operations/trace 面板观察，但不会污染 timeline。
- 没有改变模型输入，也没有加入任务特化。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_workbench_read_model.py`
  - 6 passed
- `python -m compileall -q src/crxzipple/modules/orchestration/application/read_models/workbench.py tests/unit/test_workbench_read_model.py`
  - passed

## 第三十三轮施工记录：ProviderWireRequest 最小边界对象

目标：

- 给 renderer/router 的真实 provider wire output 一个统一承载对象。
- 为后续“adapter send 只接受 ProviderWireRequest”提供可测试入口。
- 回填已经由测试覆盖的顶层 acceptance checklist，避免进度表失真。

落地：

- `ProviderWireRequest` 新增到 `llm.infrastructure.adapters.provider_protocol`。
  - 统一承载 `renderer_id`、`endpoint`、`payload`、`transport`、`render_strategy`、`render_report`、`tool_name_aliases`。
  - 通过 `from_rendered(...)` 从现有 provider renderer 的真实 rendered request 生成，不伪造 wire payload。
- `ProviderProtocolRenderRouter.render_request(...)` 新增。
  - Codex HTTP 使用 `OpenAICodexResponsesRenderer.render_http(...)`。
  - Codex WebSocket 使用 `render_websocket_create(...)`，保持 `response.create` wire payload。
  - 其他 provider 使用对应 renderer 的 `render(...)`。
- `tests/unit/test_provider_protocol_render_router.py` 新增 router wire request 覆盖。
- Functional / Observability 顶层 checklist 回填：
  - 同一 canonical request 跨 renderer 渲染已由第三十轮集成测试覆盖。
  - Orchestration 不直接构造 provider wire input 已由第二十九轮边界测试覆盖。
  - Workbench 用户可见 timeline/debug 隔离已由第三十二轮测试覆盖。

边界结果：

- 现在可以从 provider router 取得统一的 provider wire request 对象。
- adapter send 改签名尚未完成；该项仍保留在 Phase 2 checklist 中。
- 没有引入旧结构兼容、双轨发送路径或任务特化判断。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_provider_protocol_render_router.py tests/unit/test_provider_request_renderer_protocol.py tests/unit/test_openai_codex_renderer.py`
  - 13 passed

## 第三十四轮施工记录：OpenAI Responses Adapter 发送入口样板

目标：

- 先让一个真实 provider adapter 从 renderer 生成 `ProviderWireRequest`，再由发送路径读取 endpoint/payload。
- 验证“renderer/adapter 对称边界”可以落到实际发送链路，而不是只停留在 preview/router。
- 不改变上层 `LlmAdapter.invoke(...)` 协议，避免一次性牵动全部 provider。

落地：

- `OpenAIResponsesAdapter._wire_request(...)` 新增。
  - 内部调用 `OpenAIResponsesRenderer.render(...)` 得到真实 rendered request。
  - 使用 `ProviderWireRequest.from_rendered(...)` 包装 endpoint/payload/render report/tool aliases。
- `OpenAIResponsesAdapter._stream_request(...)` 改为从 `_wire_request(...)` 读取 endpoint 和 payload。
  - credential/header 解析仍留在 adapter 发送层。
  - payload 结构仍由 renderer 唯一生成。
- `tests/unit/test_llm_adapters.py` 新增 `test_openai_responses_adapter_builds_provider_wire_request`。

边界结果：

- OpenAI Responses adapter 发送路径已经具备 `ProviderWireRequest` 内部入口。
- Phase 2 的“adapter send 只接受 ProviderWireRequest”仍未勾选；其他 provider 还需要按同样模式迁移。
- 没有新增兼容 shim、双轨 provider payload 或任务特化逻辑。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py -k "openai_responses"`
  - 19 passed, 52 deselected

## 第三十五轮施工记录：Codex Responses Adapter Wire Request 发送入口

目标：

- 将 Codex HTTP/SSE 与 WebSocket 两条真实发送路径也接入 `ProviderWireRequest`。
- 保护 Codex HTTP full replay 不发送 `previous_response_id`。
- 保护 Codex WebSocket provider-native delta 继续发送 `response.create + previous_response_id`。

落地：

- `OpenAICodexResponsesAdapter._wire_request(...)` 新增。
  - 使用 `OpenAICodexResponsesRenderer.render_http(...)` 生成真实 HTTP wire payload。
  - `_stream_request(...)` 从 `ProviderWireRequest` 读取 endpoint/payload。
- `OpenAICodexResponsesAdapter._websocket_wire_request(...)` 新增。
  - 使用 `OpenAICodexResponsesRenderer.render_websocket_create(...)` 生成 WebSocket `response.create` payload。
  - `_stream_websocket_invoke(...)` 从 wire request payload 执行 `ws.send(...)`。
- `tests/unit/test_llm_adapters.py` 新增：
  - Codex HTTP provider wire request 不含 `previous_response_id`。
  - Codex WebSocket provider wire request 含 `type=response.create` 与 `previous_response_id`。

边界结果：

- OpenAI Responses 与 OpenAI Codex Responses 两个 adapter 的真实发送路径已经通过 `ProviderWireRequest` 承载 endpoint/payload。
- 仍未改变 public `LlmAdapter.invoke/stream_invoke` 协议；Phase 2 “adapter send 只接受 ProviderWireRequest”继续保持未完成，等待 Anthropic/Gemini/ChatCompatible 按同一模式迁移后统一收口。
- 没有新增任务特化 evidence/workflow 判断。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py -k "openai_codex_responses"`
  - 11 passed, 62 deselected

## 第三十六轮施工记录：非 OpenAI Responses Provider 发送路径接入 Wire Request

目标：

- 将 Anthropic、Gemini、OpenAI Chat Compatible 的真实发送路径接入 `ProviderWireRequest`。
- 继续保持 provider adapter public `invoke/stream_invoke` 协议不变，只收敛 provider wire payload 生成职责。
- 确保所有 provider endpoint/payload 均由 renderer 生成，再由 `ProviderWireRequest` 承载。

落地：

- `AnthropicMessagesAdapter._wire_request(...)` 新增。
  - `_invoke_request(...)` 从 wire request 读取 endpoint/payload。
- `GeminiGenerateContentAdapter._wire_request(...)` 新增。
  - `_invoke_request(...)` 从 wire request 读取 endpoint/payload。
- `OpenAIChatCompatibleAdapter._wire_request(...)` 新增。
  - 同步 invoke 使用 `stream=False` wire request。
  - stream invoke 使用 `stream=True` wire request，wire request transport 为 `sse`。
  - tool alias restore 从 `ProviderWireRequest.tool_name_aliases` 推导。
- `tests/unit/test_llm_adapters.py` 新增三个 provider wire request 覆盖：
  - Anthropic Messages。
  - Gemini GenerateContent。
  - OpenAI Chat Compatible HTTP/SSE。

边界结果：

- 所有当前主要 provider adapter 的真实发送路径都已从 renderer -> `ProviderWireRequest` 获取 provider wire payload。
- Phase 2 的“adapter send 只接受 ProviderWireRequest”尚未勾选；下一步需要清理 `_invoke_request/_stream_request` tuple 返回层，让内部发送函数直接以 wire request 为参数。
- 没有新增兼容路径、双轨 prompt assembly 或任务特化 evidence 判断。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py tests/unit/test_anthropic_renderer.py -k "anthropic or gemini"`
  - 20 passed, 59 deselected
- `PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py -k "openai_chat_compatible"`
  - 14 passed, 62 deselected
- `PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py -k "openai_responses or openai_codex_responses or openai_chat_compatible or anthropic or gemini" tests/unit/test_provider_protocol_render_router.py tests/unit/test_provider_request_renderer_protocol.py tests/unit/test_provider_renderer_canonical_request_integration.py`
  - 70 passed, 21 deselected

## 第三十七轮施工记录：Adapter Send Tuple 薄层退场

目标：

- 删除 provider adapter 内部 `_invoke_request/_stream_request -> (url, headers, payload)` 的散装 tuple 薄层。
- 让真实发送函数直接接收 `ProviderWireRequest`。
- 勾选 Phase 2 “adapter send 只接受 ProviderWireRequest”。

落地：

- Anthropic / Gemini：
  - 删除 `_invoke_request(...)`。
  - 新增 `_request_headers(...)`、`_send_wire_request(...)`、`_send_wire_request_async(...)`。
  - 同步/异步 invoke 均先生成 `ProviderWireRequest`，再交给发送函数。
- OpenAI Chat Compatible：
  - 删除 `_stream_request(...)` tuple 返回层。
  - 新增 `_request_headers(...)`、`_send_wire_request(...)`、`_send_stream_wire_request(...)`。
  - 同步 invoke、stream invoke、async stream 均从 `ProviderWireRequest` 读取 endpoint/payload。
- OpenAI Responses / OpenAI Codex Responses：
  - 删除 `_stream_request(...)` tuple 返回层。
  - 新增或复用 `_request_headers(...)`、`_send_stream_wire_request(...)`。
  - 同步/异步 stream 均从 `ProviderWireRequest` 读取 endpoint/payload。
- `rg` 验证 `def _invoke_request|def _stream_request|_invoke_request(|_stream_request(` 在 provider adapters 中无残留。

边界结果：

- Provider renderer 负责生成 provider wire payload。
- Provider adapter send 负责鉴权/header/HTTP 或 WebSocket 传输。
- 两者之间用 `ProviderWireRequest` 传递，不再传散装 provider payload tuple。
- Public `LlmAdapter.invoke/stream_invoke` 仍接收 canonical `LlmAdapterRequest`，没有改变上层 application 协议。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py tests/unit/test_anthropic_renderer.py -k "anthropic or gemini"`
  - 20 passed, 60 deselected
- `PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py -k "openai_chat_compatible"`
  - 14 passed, 62 deselected
- `PYTHONPATH=src pytest -q tests/unit/test_openai_codex_transport_wire_contract.py tests/unit/test_llm_adapters.py -k "openai_responses or openai_codex_responses"`
  - 30 passed, 48 deselected
- `PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py -k "openai_responses or openai_codex_responses or openai_chat_compatible or anthropic or gemini" tests/unit/test_openai_codex_transport_wire_contract.py tests/unit/test_provider_protocol_render_router.py tests/unit/test_provider_request_renderer_protocol.py tests/unit/test_provider_renderer_canonical_request_integration.py`
  - 70 passed, 23 deselected

## 第三十八轮施工记录：Tool Surface Render Report 可审计化

目标：

- 让 provider 实际可见的 tool 名称进入 render report。
- 让 dropped tool schema count 成为确定性观测字段。
- 不把该信息作为模型输入，也不引入任务特化判断。

落地：

- `provider_tool_render_report(...)` 新增到 adapter common。
  - 从 provider wire payload 的 `tools` 字段提取 provider-visible tool names。
  - 支持 OpenAI Responses、OpenAI Chat Compatible、Anthropic、Gemini 的工具 schema 形态。
  - 从 request metadata 的 `tool_surface.functions` / `mirrored_schema_names` / `tool_surface_function_count` 推导 source tool schema count。
  - 输出 `source_tool_schema_count`、`provider_visible_tool_count`、`provider_visible_tool_names`、`dropped_tool_schema_count`。
- `openai_provider_request_preview(...)` 与 `provider_wire_request_preview(...)` 的 `render_report.tool_surface` 写入该报告。
- 单元测试补充：
  - OpenAI tool `command.exec` 被 provider-visible alias 为 `command_exec`。
  - Anthropic tool `search_docs` 原样 provider-visible。
  - 无工具时 dropped count 为 0。

边界结果：

- Tool owner 仍输出 provider-neutral schema。
- Renderer 仍负责 provider-specific schema mapping。
- Render report 现在能解释 provider 实际收到哪些工具名，以及是否有 schema 被丢弃。
- 没有新增 workflow/evidence gate，也没有把观测 report 注入 model-visible transcript。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py tests/unit/test_anthropic_renderer.py tests/unit/test_provider_request_renderer_protocol.py tests/unit/test_provider_renderer_canonical_request_integration.py`
  - 83 passed

## 第三十九轮施工记录：Tool Protocol Diagnostics 进入 Render Report

目标：

- 将 duplicate/orphan/missing tool protocol diagnostics 作为 provider render report 的观测输入。
- 不生成自然语言提示，不进入 model-visible transcript。
- 不把协议诊断变成 runtime gate。

落地：

- `provider_tool_protocol_render_report(...)` 新增到 adapter common。
  - 从 `request_metadata.direct_tool_protocol_health` 读取确定性协议健康字段。
  - 输出 source/replay 是否有 protocol breaks。
  - 输出 replay orphan/missing/duplicate call/duplicate output 计数。
  - 输出 dropped orphan/missing/duplicate call/duplicate output 计数。
  - metadata 不存在时输出全 0 的空报告。
- `openai_provider_request_preview(...)` 与 `provider_wire_request_preview(...)` 写入 `render_report.tool_protocol`。
- 单元测试补充：
  - OpenAI preview 携带 dropped orphan/missing 计数。
  - Anthropic 空协议报告字段稳定。

边界结果：

- Session/Orchestration 继续负责 canonical replay normalization。
- LLM renderer 只把既有诊断挂到 render report，供 Operations/Trace 审计。
- 没有把不完整或推断性结论发送给 LLM。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py tests/unit/test_anthropic_renderer.py tests/unit/test_provider_request_renderer_protocol.py tests/unit/test_provider_renderer_canonical_request_integration.py`
  - 83 passed

## 第四十轮施工记录：Phase 7 Workbench Checklist 回填

目标：

- 修正进度表失真：Workbench timeline debug payload 隔离已在第三十二轮落地，但 Phase 7 顶层 checklist 未勾选。
- 保持施工计划和测试覆盖一致。

依据：

- `tests/unit/test_workbench_read_model.py::test_workbench_timeline_hides_debug_only_context_tree_payload`
  已验证 timeline 不展示 `<context_tree>`、provider request preview、runtime request summary 等 debug-only payload。
- Observability Acceptance 中 “Workbench 可看到用户应该看的 progress / reasoning summary / tool result excerpt / final” 已勾选。

落地：

- Phase 7 勾选 `Workbench timeline 展示用户可见 item，不展示 debug-only provider metadata`。

边界结果：

- 本轮只同步文档真相，不改模型输入、不改 provider rendering、不新增任务特化逻辑。

## 第四十一轮施工记录：Trace Linked LLM Provider Input 审计闭环

目标：

- 让 Trace 页面从事件链上的 `llm_invocation_id` 直接打开 LLM invocation detail。
- 在 linked entity detail 中拆出 provider render report 与 provider wire preview。
- 只展示 renderer/transport/strategy/endpoint/tool count/continuation 等稳定事实，不生成证据结论。

落地：

- `src/crxzipple/interfaces/http/ui.py`
  - `llm_invocation` linked entity payload 新增 `provider_render_report`。
  - `llm_invocation` linked entity payload 新增 `provider_wire_preview`。
  - `provider_wire_preview` 明确剥离 `render_report`，避免 UI 把 report 和真实 wire shape 混在一起。
- `frontend/src/pages/trace/TracePage.vue`
  - `llm_invocation` / `llm_invocation_id` 支持作为可打开 linked entity。
  - Entity detail 新增 Provider Input 摘要区。
  - 原始 payload JSON 仍保留，供 Trace 调试深入查看。
- `frontend/src/shared/i18n/messages/{zh-CN,en-US}.ts`
  - 新增 Provider Input 摘要区文案。
- `tests/unit/test_ui_http.py`
  - LLM linked entity detail 覆盖 provider render report 与 provider wire preview。
  - 确认 wire preview 不包含 `render_report`。

边界结果：

- Trace 现在能从 run/step 事件中的 `llm_invocation_id` 串到 provider input shape。
- `llm_response_item_id` 仍通过同一 linked entity/event trace 机制串联。
- 本轮没有把 provider report 注入 LLM 输入，也没有新增任务特化逻辑。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_ui_http.py -k "llm_page_uses_runtime_state_and_events or trace_summary_and_events_use_event_read_model"`
  - 2 passed, 48 deselected
- `cd frontend && npm run typecheck`
  - passed

## 第四十二轮施工记录：Provider Options 退出 Request Metadata 侧通道

目标：

- 保留 `provider_options` 作为 canonical LLM request options，由 renderer/adapter 正式消费。
- 删除 `request_metadata.provider_options` 的重复暴露，避免 Orchestration metadata 被误读成 provider wire 拼装。
- 不删除 service tier、verbosity、parallel tool calls 等模型请求选项能力。

落地：

- `src/crxzipple/modules/llm/application/runtime_request.py`
  - `RuntimeLlmRequest.request_metadata()` 不再写入 `provider_options`。
  - `RuntimeLlmRequest.to_payload()` 继续保留 `provider_options`，作为 canonical request envelope 字段。
- `tests/unit/test_orchestration_runtime_llm_request.py`
  - 更新边界断言：metadata 不含 `provider_options`，payload 仍含 canonical request options。

边界结果：

- Renderer 继续从 adapter request overrides / envelope provider options 读取请求选项。
- request metadata 只承载 context/tool/runtime facts，不承载 provider option side channel。
- 本轮不引入兼容字段，不新增双轨。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_orchestration_runtime_llm_request.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_provider_renderer_canonical_request_integration.py tests/unit/test_llm_adapters.py`
  - 99 passed
- `python -m compileall -q src/crxzipple/modules/llm/application/runtime_request.py tests/unit/test_orchestration_runtime_llm_request.py`
  - passed

## 第四十三轮施工记录：Prompt Collector 改口径为 Runtime LLM Request Draft Collector

目标：

- 消除 `RuntimeLlmRequestDraftCollector` 这个旧命名对边界的误导。
- 明确该组件只收集 canonical runtime LLM request draft 所需事实。
- 不让 Orchestration 继续被理解成 provider prompt/input renderer。

落地：

- `RuntimeLlmRequestDraftCollector` 直接改名为 `RuntimeLlmRequestDraftCollector`。
- 同步更新 assembly、orchestration engine、application exports、事件 contract producer name 和相关测试 fake。
- 更新 collector docstring：
  - 不渲染 provider input。
  - Context Workspace 拥有 tree snapshot / attachment mirror。
  - LLM renderer 拥有 provider wire rendering。

边界结果：

- `RuntimeLlmRequestDraft` 数据结构暂不重命名；它仍是 draft collector 的返回事实对象，后续可并入 `RuntimeLlmRequest` 命名收敛。
- 没有新增兼容 alias。
- 没有改变模型输入行为。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_turn_submission_prompt_bootstrap.py tests/unit/test_app_assembly_architecture.py tests/unit/test_orchestration_context_workspace_snapshot.py -k "runtime_request_draft_collector or RuntimeLlmRequestDraftCollector or context_workspace_snapshot or orchestration_uses"`
  - 37 passed, 25 deselected
- `python -m compileall -q src/crxzipple/modules/orchestration/application/runtime_llm_request_draft.py src/crxzipple/modules/orchestration/application/engine.py src/crxzipple/app/assembly/orchestration.py tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_turn_submission_prompt_bootstrap.py`
  - passed

## 第四十四轮施工记录：LlmRequestEnvelope 改名为 RuntimeLlmRequest

目标：

- 让 LLM application 的一等请求对象直接表达 runtime canonical request。
- 避免 `Envelope` 继续暗示它只是 provider 调用前的临时包装。
- 不保留旧类型别名，遵守不兼容旧结构的原则。

落地：

- `src/crxzipple/modules/llm/application/runtime_request.py`
  - `LlmRequestEnvelope` 改名为 `RuntimeLlmRequest`。
- 同步更新：
  - LLM service invoke / stream 类型。
  - Orchestration request builder / engine / invoker 类型。
  - runtime request、orchestration provider request、tool orchestration 相关测试。
- 本轮未改动 tool module owner fact：
  - tool module 的 `ToolSurface` / `ToolSurfaceSnapshot` 仍是 owner fact。
  - LLM request 中的 `RuntimeToolSurface` / `RuntimeToolSurfaceRef` 是 runtime request surface。

边界结果：

- 真实 provider wire 仍只由 renderer/adapter 生成。
- `RuntimeLlmRequest.to_payload()` 是 canonical request envelope，不等于 provider payload。
- `RuntimeLlmRequest.request_metadata()` 不含 `provider_options` side channel。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_runtime_llm_request.py tests/unit/test_orchestration_runtime_llm_request.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_llm.py tests/unit/test_orchestration_tools.py -k "runtime_llm_request or RuntimeLlmRequest or request_envelope or provider_request or llm_invoker or provider_native"`
  - 29 passed, 53 deselected
- `python -m compileall -q src/crxzipple/modules/llm/application/runtime_request.py src/crxzipple/modules/llm/application/services.py src/crxzipple/modules/orchestration/application/runtime_llm_request.py src/crxzipple/modules/orchestration/application/engine.py src/crxzipple/modules/orchestration/application/engine_llm_invoker.py tests/unit/test_runtime_llm_request.py`
  - passed

## 第四十五轮施工记录：RuntimeLlmContext / RuntimeToolSurfaceRef 命名收敛

目标：

- 将 LLM runtime request 内部的 context/tool surface 类型从通用名改为 runtime request 专属名。
- 避免与 tool module owner fact `ToolSurface` / `ToolSurfaceSnapshot` 混淆。
- 不改变 provider wire payload，也不改变模型输入。

落地：

- `src/crxzipple/modules/llm/application/runtime_request.py`
  - `ContextSurface` 改为 `RuntimeLlmContext`。
  - `ToolSurface` 改为 `RuntimeToolSurface`。
  - `ToolSurfaceFunction` 改为 `RuntimeToolSurfaceRef`。
- 同步更新：
  - LLM application exports。
  - Orchestration `RuntimeLlmRequestBuilder`。
  - runtime request / provider request / tool orchestration 相关测试。
- 修正文档中被机械替换误伤的 tool owner fact 名称：
  - `ToolSurfaceQueryService`
  - `ToolSurfaceSnapshot`

边界结果：

- LLM request 中的 `RuntimeToolSurface` 是模型请求的工具面。
- Tool module 中的 `ToolSurface` / `ToolSurfaceSnapshot` 仍是 owner fact。
- payload 字段 `context_surface` / `tool_surface` 继续保留为稳定审计字段，不作为旧结构兼容层。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_runtime_llm_request.py tests/unit/test_orchestration_runtime_llm_request.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_orchestration_tools.py -k "RuntimeLlmContext or RuntimeToolSurface or RuntimeToolSurfaceRef or runtime_llm_request or request_envelope or provider_native"`
  - 16 passed, 46 deselected
- `python -m compileall -q src/crxzipple/modules/llm/application/runtime_request.py src/crxzipple/modules/llm/application/__init__.py src/crxzipple/modules/orchestration/application/runtime_llm_request.py tests/unit/test_runtime_llm_request.py`
  - passed

## 第四十六轮施工记录：RuntimeLlmTranscript 成为 RuntimeLlmRequest 一等字段

目标：

- 将 runtime request 中的 transcript 从裸 `input_items` 字段收敛为 `RuntimeLlmTranscript`。
- 保持 provider adapter request 的 `input_items` 不变，因为 adapter request 是 renderer 输入 DTO，不是 runtime request owner 对象。
- 不改变 HTTP invoke DTO、LLM invocation 持久化和 provider wire payload。

落地：

- `src/crxzipple/modules/llm/application/runtime_request.py`
  - 新增 `RuntimeLlmTranscript`。
  - `RuntimeLlmRequest` 使用 `transcript: RuntimeLlmTranscript`。
  - `RuntimeLlmRequest.to_payload()` 输出 `transcript.items`。
- `src/crxzipple/modules/llm/application/services.py`
  - `InvokeLlmInput.from_runtime_request(...)` / `StreamLlmInput.from_runtime_request(...)` 从 `request.transcript.items` 降级为 adapter request 的 `input_items`。
- `src/crxzipple/modules/orchestration/application/runtime_llm_request.py`
  - `RuntimeLlmRequestBuilder` 构造 `RuntimeLlmTranscript(items=input_items)`。
- 测试更新：
  - runtime request serialization 断言 `payload.transcript.items`。
  - orchestration provider request builder 断言 `envelope.transcript.items`。

边界结果：

- Runtime LLM request 现在完整具备 `RuntimeLlmRequest` / `RuntimeLlmContext` / `RuntimeLlmTranscript` / `RuntimeToolSurfaceRef`。
- adapter request 仍保留 provider renderer 需要的扁平 `input_items`，作为下游 DTO，不是旧 runtime 结构兼容。
- 没有新增任务特化逻辑。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_runtime_llm_request.py tests/unit/test_orchestration_runtime_llm_request.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_llm.py tests/unit/test_orchestration_tools.py -k "runtime_llm_request or RuntimeLlmTranscript or RuntimeLlmContext or RuntimeToolSurface or request_envelope or provider_native"`
  - 16 passed, 66 deselected
- `python -m compileall -q src/crxzipple/modules/llm/application/runtime_request.py src/crxzipple/modules/llm/application/services.py src/crxzipple/modules/orchestration/application/runtime_llm_request.py tests/unit/test_runtime_llm_request.py tests/unit/test_orchestration_runtime_llm_request_builder.py`
  - passed

补充验证：

- `PYTHONPATH=src pytest -q tests/unit/test_runtime_llm_request.py tests/unit/test_orchestration_runtime_llm_request.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_context_workspace_snapshot_boundary.py tests/unit/test_provider_renderer_canonical_request_integration.py tests/unit/test_llm_adapters.py -k "runtime_llm_request or RuntimeLlmTranscript or RuntimeLlmContext or RuntimeToolSurface or request_envelope or context_workspace_snapshot_refs or provider_request or renderer"`
  - 31 passed, 72 deselected
- `python -m compileall -q src/crxzipple/modules/llm/application/runtime_request.py src/crxzipple/modules/llm/application/services.py src/crxzipple/modules/orchestration/application/runtime_llm_request.py tests/unit/test_runtime_llm_request.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_context_workspace_snapshot_boundary.py`
  - passed

## 第四十七轮施工记录：RuntimeLlmRequestDraftCollector 去 PromptBlock 化

目标：

- Phase 3 继续瘦身 orchestration draft collector。
- 去掉 `RuntimeLlmRequestDraftCollector` 中直接构造 `PromptBlock(content=...)` 的路径。
- 让 draft collector 只收集 owner facts / refs；Context Workspace 集成再把 facts 材料化为 Context Tree 节点。

落地：

- `src/crxzipple/modules/orchestration/application/runtime_llm_request_draft.py`
  - `RuntimeLlmRequestDraft` 删除 `context_blocks` 字段。
  - 新增 `agent_instruction` 和 `runtime_context` canonical facts。
  - `RuntimeLlmRequestDraftCollector` 不再调用 `build_agent_instruction_block`、`build_runtime_context_block`、`apply_system_prompt_budget`。
  - runtime request report 中不再记录 collector 生成的 context block 文本。
- `src/crxzipple/app/integration/context_workspace_orchestration/run_workspace_metadata.py`
  - `agent.identity` 节点从 `prompt.agent_instruction` 生成。
  - `run.environment` 节点从 `prompt.runtime_context` facts 生成。
  - 不再访问 `prompt.context_blocks`。
- `src/crxzipple/app/integration/context_workspace_orchestration/snapshot_metadata.py`
  - provider attachment summary 不再记录 `context_block_count`。
  - 改为记录 `runtime_context_fact_count` 和 `has_agent_instruction`。
- `tests/unit/test_orchestration_context_workspace_snapshot.py`
  - 测试 fixture 改为新的 canonical facts。

边界结果：

- Orchestration draft 不再携带 prompt-rendered text block。
- Context Workspace 仍负责把 canonical facts 写入 Context Tree。
- Provider wire input 仍只由 LLM provider renderer 产生。
- 没有加入任何任务特化判断、evidence gate 或 browser 路线偏置。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_runtime_llm_request.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_context_workspace_snapshot_boundary.py tests/unit/test_runtime_llm_request_draft_collector.py -k "context_workspace_snapshot or runtime_llm_request or provider_request or runtime_request_draft_collector"`
  - 58 passed
- `PYTHONPATH=src pytest -q tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_context_workspace_snapshot_boundary.py tests/unit/test_runtime_llm_request.py tests/unit/test_provider_renderer_canonical_request_integration.py tests/unit/test_llm_adapters.py`
  - 137 passed

## 第四十八轮施工记录：Orchestration provider_request 入口退场

目标：

- 消除 orchestration 侧 `provider_request.py` / `provider_request_builder` 旧命名造成的边界误读。
- 保留 orchestration 对 run/context/tool owner facts 的 canonical request mapping。
- 明确 provider wire input rendering 只能由 LLM provider renderer/router 执行。

落地：

- `src/crxzipple/modules/orchestration/application/provider_request.py`
  - 改名为 `src/crxzipple/modules/orchestration/application/runtime_llm_request.py`。
- `tests/unit/test_orchestration_provider_request_builder.py`
  - 改名为 `tests/unit/test_orchestration_runtime_llm_request_builder.py`。
- `src/crxzipple/modules/orchestration/application/engine.py`
  - `provider_request_builder` 字段改名为 `runtime_llm_request_builder`。
- 同步更新所有当前代码和测试 import。
- 不新增旧模块 alias，不做双轨兼容。

边界结果：

- Orchestration 仍可将 run facts、Context Snapshot refs、tool surface refs 映射为 `RuntimeLlmRequest`。
- Provider/transport/model 的 wire payload 仍由 LLM renderer 负责。
- 当前源码中不再存在 `orchestration.application.provider_request` 入口。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_orchestration_runtime_llm_request.py tests/unit/test_context_workspace_snapshot_boundary.py tests/unit/test_orchestration_context_workspace_snapshot.py`
  - 48 passed
- `rg -n "orchestration\\.application\\.provider_request|from \\.provider_request|provider_request\\.py|test_orchestration_provider_request_builder" src tests`
  - no matches

## 第四十九轮施工记录：Replay Window Policy 进入 RuntimeLlmTranscript

目标：

- Phase 5 收敛 session replay 策略位置。
- 不再把 replay window policy 塞在 `RuntimeRequestReport.transcript_budget` 里作为 prompt/report 侧道。
- 让 LLM renderer 可从 canonical `RuntimeLlmTranscript` 直接读取 replay policy。

落地：

- `src/crxzipple/modules/llm/application/runtime_request.py`
  - `RuntimeLlmTranscript` 新增 `policy` 字段。
  - `RuntimeLlmTranscript.to_payload()` 输出 `policy`。
- `src/crxzipple/modules/orchestration/application/runtime_llm_request_draft.py`
  - `RuntimeLlmRequestDraft` 新增 `transcript_policy`。
  - `RuntimeLlmRequestDraftCollector` 将 `session_replay_window` 写入 `transcript_policy`。
  - `RuntimeRequestReport.transcript_budget` 不再写入 `session_replay_window`。
- `src/crxzipple/modules/orchestration/application/runtime_llm_request.py`
  - 构造 `RuntimeLlmTranscript(items=..., policy=...)`。
- 测试更新：
  - runtime request serialization 覆盖 transcript policy。
  - prompt collector 断言 replay window 不再进入 report budget。
  - runtime request builder 断言 transcript policy 穿透到 envelope。

边界结果：

- 模型请求侧的 replay window policy 进入 LLM canonical request。
- 事件 payload 仍保留 `session_replay_window` 作为 routing/observability fact，不作为模型输入侧道。
- provider renderer 后续可基于 `RuntimeLlmTranscript.policy` 做 provider/transport 级 replay 渲染。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_runtime_llm_request.py tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_orchestration_runtime_llm_request.py tests/unit/test_context_workspace_snapshot_boundary.py`
  - 37 passed
- `PYTHONPATH=src pytest -q tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_orchestration_runtime_llm_request.py tests/unit/test_context_workspace_snapshot_boundary.py tests/unit/test_runtime_llm_request.py tests/unit/test_provider_renderer_canonical_request_integration.py tests/unit/test_llm_adapters.py`
  - 139 passed
- `python -m compileall -q src/crxzipple/modules/llm/application/runtime_request.py src/crxzipple/modules/orchestration/application/runtime_llm_request_draft.py src/crxzipple/modules/orchestration/application/runtime_llm_request.py tests/unit/test_runtime_llm_request.py tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_orchestration_runtime_llm_request_builder.py`
  - passed

## 第五十轮施工记录：Orchestration Context Snapshot Port 去 Render 命名

目标：

- Phase 4 开始收敛 Context Snapshot 概念。
- 先从 orchestration 边界去掉 `Render` 暴露名，让 orchestration 只看到 context snapshot record/port。
- 不在本轮改 Context Workspace 内部实体/服务名，避免一次性机械替换混入持久化和 API 重命名风险。

落地：

- `src/crxzipple/modules/orchestration/application/ports/context.py`
  - `ContextSnapshotRecord` 改为 `ContextSnapshotRecord`。
  - `ContextSnapshotPort` 改为 `ContextSnapshotPort`。
- 同步更新：
  - orchestration engine。
  - runtime LLM request builder。
  - Context Workspace orchestration adapter。
  - 相关测试 imports / fakes。
- 不保留旧 port alias。

边界结果：

- Orchestration 侧不再以 `ContextSnapshot*` 命名感知 Context Workspace 输出。
- Context Workspace 内部仍暂时使用 `ContextSnapshot` / `ContextRenderService`，留待下一轮集中迁移。
- Provider request 路径不受影响；snapshot `debug_body` 仍不会进入 provider wire input。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_orchestration_runtime_llm_request.py tests/unit/test_context_workspace_snapshot_boundary.py`
  - 49 passed
- `python -m compileall -q src/crxzipple/modules/orchestration/application/ports/context.py src/crxzipple/modules/orchestration/application/ports/__init__.py src/crxzipple/modules/orchestration/application/engine.py src/crxzipple/modules/orchestration/application/runtime_llm_request.py src/crxzipple/app/integration/context_workspace_orchestration/adapter.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_orchestration_runtime_llm_request.py tests/unit/test_context_workspace_snapshot_boundary.py`
  - passed

## 第五十一轮施工记录：Context Workspace Python 层 ContextSnapshot 命名收敛

目标：

- Phase 4 继续把 Context Workspace 内部 owner 类型从 render snapshot 口径收敛到 context snapshot 口径。
- 先处理 Python 类型、repository、service、assembly key，不在同轮重写 DB table 和 debug `debug_body` 字段。
- 不保留旧类型 alias。

落地：

- Context Workspace domain/application/infrastructure：
  - `ContextSnapshot` 改为 `ContextSnapshot`。
  - `ContextSnapshotRepository` 改为 `ContextSnapshotRepository`。
  - `ContextSnapshotNotFoundError` 改为 `ContextSnapshotNotFoundError`。
  - `ContextRenderService` 改为 `ContextSnapshotService`。
  - `RecordContextSnapshotInput` 改为 `RecordContextSnapshotInput`。
  - `InMemoryContextSnapshotRepository` 改为 `InMemoryContextSnapshotRepository`。
  - `SqlAlchemyContextSnapshotRepository` 改为 `SqlAlchemyContextSnapshotRepository`。
- App assembly：
  - `AppKey.CONTEXT_RENDER_SERVICE` 改为 `AppKey.CONTEXT_SNAPSHOT_SERVICE`。
  - key value 改为 `context_workspace.snapshot_service`。
- Context Tree tool local package：
  - 类型导入改为 `ContextSnapshotService`。
  - 依赖注入 id `context_snapshot_service` 暂时保留，避免本轮同时变更 tool package contract。

边界结果：

- `src/tests/tools` 中不再引用 `ContextSnapshot*` / `ContextRenderService` / `RecordContextSnapshotInput` 旧 Python 类型名。
- Context Workspace Python 层 owner 概念已转向 `ContextSnapshot`。
- 尚未完成：
  - DB table / migration 从 `context_snapshots` 收敛到 `context_snapshots`。
  - HTTP/CLI 的 `render_debug_body` debug endpoint 是否改名。
  - snapshot 中 `debug_body` 字段是否改为 `debug_render_body` 或仅作为 debug artifact。

验证：

- `python -m compileall -q src/crxzipple/modules/context_workspace src/crxzipple/app/integration/context_workspace_orchestration src/crxzipple/app/assembly/context_workspace.py tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py tests/unit/test_orchestration_context_workspace_snapshot.py`
  - passed
- `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_operations_context_workspace_read_model.py`
  - 105 passed after fixing `tools/context_tree/local.py` import.
- `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_context_workspace_artifact_adapter.py tests/unit/test_context_workspace_agent_adapter.py`
  - 57 passed

已知非本轮失败：

- `tests/unit/test_app_assembly_architecture.py::test_frontend_prompt_snapshot_uses_context_workspace_surface_only`
  - 当前 frontend 中仍有 `/llms/calls/.../llm-request-preview` 字符串，触发架构 guard。
- `tests/unit/test_tool_providers.py::ToolProvidersTestCase::test_scanned_tool_packages_register_system_tools_without_bootstrap_hardcoding`
  - 当前 context_tree local binding 数量为 12，测试期望 9；这来自现有 tool surface 变更，不是本轮 ContextSnapshot 命名改动。

## 第五十二轮施工记录：Context Snapshot 持久化与运行引用去 Render 命名

目标：

- Phase 4 完成 `ContextSnapshot` 概念收敛，不保留旧表名、旧 revision id 或旧 API metadata 字段。
- 按“不要兼容结构、不要双轨并行”的原则直接重写迁移与测试口径。
- 保持 Context Workspace 只维护 Context Snapshot 事实；provider wire 由 LLM renderer/adapter 负责。

落地：

- Alembic / DB：
  - `context_snapshots` 表名收敛为 `context_snapshots`。
  - 相关 index / constraint 名收敛为 `ix_context_snapshots_*` / `context_snapshots_run_id_key`。
  - 迁移文件和 revision id 收敛：
    - `0070_context_snapshot_run_history`
    - `0074_context_snapshot_refs`
    - `0078_context_snapshot_parent`
  - 下游 `down_revision` 与 CLI test HEAD revision 同步更新。
- ORM：
  - `ContextSnapshotModel.__tablename__ = "context_snapshots"`。
- Runtime / API / UI：
  - `context_snapshot_id` 统一改为 `context_snapshot_id`。
  - `context_snapshot_metadata` / `context_render_metadata` 统一改为 `context_snapshot_metadata`。
  - 前端 Workbench / Trace / shared runtime 类型同步使用 `context_snapshot_id`。
  - Context Workspace snapshot HTTP 路由从 `/render-snapshot(s)` 收敛为 `/snapshot` / `/snapshots`。
  - Context Workspace service 记录入口从 `record_render_snapshot` 收敛为 `record_snapshot`。
  - Operations Context Workspace section id 从 `render_snapshots` 收敛为 `snapshots`，用户可见文案改为 Context Snapshots / 上下文快照。
- 测试：
  - Context Workspace HTTP 旧证据/告警测试改为验证不再把 browser/tool 结果提升为 `session_evidence` 或 `investigation_warning` 节点。
  - Turns / Operations fixture 同步 RuntimeLlmRequest 与 LLM detail 当前结构。

边界结果：

- `src/tests/frontend` 中不再引用 `context_snapshot*` 或 `context_render_metadata`。
- `alembic/src/tests/frontend/tools` 中不再引用 `ContextSnapshot*`、旧表名、旧 revision id 或 `render-snapshot(s)` 路由。
- Browser owner 内部 `browser_evidence` 仍作为工具自身返回 metadata 保留；Context Workspace 不再把它提升为通用判断节点。

验证：

- `python -m compileall -q alembic/versions/0063_context_workspace_tables.py alembic/versions/0070_context_snapshot_run_history.py alembic/versions/0071_delete_configured_browser_tool_source.py alembic/versions/0074_context_snapshot_refs.py alembic/versions/0075_tool_run_surface_call_refs.py alembic/versions/0078_context_snapshot_parent.py alembic/versions/0079_llm_invocation_input_items.py src/crxzipple/modules/context_workspace/infrastructure/persistence/models.py src/crxzipple/modules/context_workspace/infrastructure/persistence/repositories.py`
  - passed
- `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_operations_context_workspace_read_model.py tests/unit/test_context_workspace_artifact_adapter.py tests/unit/test_context_workspace_agent_adapter.py tests/unit/test_context_workspace_http.py tests/unit/test_orchestration_runtime_llm_request.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_context_workspace_snapshot_boundary.py tests/unit/test_llm.py tests/unit/test_llm_http.py tests/unit/test_llm_adapters.py tests/unit/test_runtime_llm_request.py tests/unit/test_turns_http.py::TurnsHttpTestCase::test_turns_endpoint_submits_async_turn_without_exposing_orchestration tests/unit/test_ui_http.py::UiHttpTestCase::test_operations_detail_endpoints_read_independent_projections`
  - 250 passed
- `cd frontend && npm run typecheck`
  - passed

已知后续测试债：

- `tests/unit/test_orchestration_context.py` 仍有多处旧断言要求 direct system/context message、`runtime_request_report.context_blocks` 或 context artifact prompt block；这些断言需要按 RuntimeLlmRequest / renderer 边界继续迁移。

## 第五十三轮施工记录：Orchestration Context 测试迁移到 RuntimeLlmRequest 边界

目标：

- 消除 `tests/unit/test_orchestration_context.py` 对旧 prompt block / synthetic system context message 的依赖。
- 测试改为验证当前边界事实：
  - `LlmAdapterRequest.input_items` 承载 structured replay。
  - `request_metadata.context_surface` 承载 Context Snapshot 引用和 included nodes。
  - `tool_schemas` 承载 agent 可调用工具面。
  - 当前用户输入仍作为 provider-facing user message。

落地：

- `test_normal_turn_delivers_history_through_context_tree_not_direct_transcript`
  - 不再查找 `prompt_block_kind=context_workspace` 的 system message。
  - 改为验证 `input_mode=structured_replay`、历史 assistant response 出现在 `input_items`、当前 user message 在 `messages[-1]`。
- `test_followup_turn_delivers_prior_tool_history_as_context_tree_interaction`
  - 不再要求 tool history 被压进 Context Tree XML。
  - 改为验证 tool call/result 历史出现在 structured replay input items。
- `test_process_next_orchestration_assignment_downgrades_image_history_for_explicit_non_vision_model`
  - 不再要求 `context_artifacts` prompt block。
  - 改为验证非视觉模型 provider-facing request 中不包含 image ref / screenshot 文件名。
- workspace/context tree handle 相关测试：
  - 不再要求 `messages` 里出现 system Context Tree body。
  - 改为验证 `context_surface.snapshot_id`、`included_node_ids`、context tree tool schemas 和 run metadata。
- small context window 测试：
  - 不再要求 `runtime_request_report.context_blocks` 中出现被截断 block。
  - 改为验证 prompt budget 缩放、`context_blocks=[]` 与 snapshot id 存在。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_orchestration_context.py`
  - 17 passed
- `PYTHONPATH=src pytest -q tests/unit/test_orchestration_runtime_llm_request.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_context_workspace_snapshot_boundary.py tests/unit/test_llm.py tests/unit/test_llm_http.py tests/unit/test_llm_adapters.py tests/unit/test_runtime_llm_request.py tests/unit/test_turns_http.py tests/unit/test_ui_http.py tests/unit/test_operations_llm_read_model.py tests/unit/test_orchestration_execution_chain.py tests/unit/test_orchestration_tools.py tests/unit/test_orchestration_context.py`
  - 295 passed

## 第五十四轮施工记录：RuntimeRequestReport Context Snapshot 命名收敛

目标：

- 继续清理 Orchestration / HTTP preview 中的 `context_render` 命名，避免把 Context Snapshot summary 与 provider render report 混在一起。
- 保持 provider render report 只属于 LLM renderer / adapter 边界。

落地：

- Orchestration runtime request report：
  - `ContextRenderReport` 改为 `ContextSnapshotReport`。
  - `RuntimeRequestReport.context_render` 改为 `RuntimeRequestReport.context_snapshot`。
  - `RuntimeRequestReport.to_payload()` 输出 `context_snapshot`，不再输出 `context_render`。
- HTTP preview / frontend：
  - `RuntimeLlmRequestPreviewDTO.context_render` 改为 `context_snapshot`。
  - frontend `RuntimeLlmRequestPreview.context_render` 改为 `context_snapshot`。
  - Workbench preview consumer 同步读取 `context_snapshot`。
- shared helper：
  - `context_render_budget.py` 改为 `context_snapshot_budget.py`。
  - `context_render_budget_metadata` 改为 `context_snapshot_budget_metadata`。

验证：

- `python -m compileall -q src/crxzipple/shared/context_snapshot_budget.py src/crxzipple/modules/context_workspace/application/rendering/snapshot_metadata.py src/crxzipple/app/integration/context_workspace_orchestration/snapshot_metadata.py src/crxzipple/modules/orchestration/application/runtime_llm_request.py tests/unit/test_context_snapshot_metadata.py`
  - passed
- `PYTHONPATH=src pytest -q tests/unit/test_context_snapshot_metadata.py tests/unit/test_turns_http.py::TurnsHttpTestCase::test_turns_endpoint_submits_async_turn_without_exposing_orchestration tests/unit/test_llm_http.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_context.py tests/unit/test_orchestration_runtime_llm_request.py tests/unit/test_orchestration_runtime_llm_request_builder.py`
  - 79 passed
- `cd frontend && npm run typecheck`
  - passed

## 第五十五轮施工记录：Context Snapshot Service 依赖 id 与 Operations Port 命名收敛

目标：

- 清理 tool package / assembly / Operations read model 中残留的 `context_render_service` 与 `OperationsContextRenderPort` 命名。
- 保持 `render_debug_body` 作为显式 debug tree render 方法，不把它误认为 provider request 入口。

落地：

- `tools/context_tree`：
  - dependency id 从 `context_render_service` 改为 `context_snapshot_service`。
  - local dependency field 同步改名。
- assembly：
  - orchestration / operations / tool package 注入参数同步使用 `context_snapshot_service`。
- Operations read model：
  - `OperationsContextRenderPort` 改为 `OperationsContextSnapshotPort`。
- tool provider 测试：
  - 同步 context_tree 当前 12 个 local binding。
  - expected registered ids 补入 `context_tree.diff_since`、`context_tree.read_snapshot`、`context_tree.render_current`。

验证：

- `python -m compileall -q src/crxzipple/app/assembly/operations.py src/crxzipple/app/assembly/orchestration.py src/crxzipple/app/assembly/tool_packages.py src/crxzipple/modules/operations/application/read_models/factory.py src/crxzipple/modules/operations/application/read_models/context_workspace.py src/crxzipple/modules/operations/application/read_models/ports.py tools/context_tree/local.py tests/unit/test_context_tree_tool.py tests/unit/test_tool_providers.py`
  - passed
- `PYTHONPATH=src pytest -q tests/unit/test_context_tree_tool.py tests/unit/test_operations_context_workspace_read_model.py tests/unit/test_tool_providers.py::ToolProvidersTestCase::test_scanned_tool_packages_register_system_tools_without_bootstrap_hardcoding`
  - 14 passed

## 第五十六轮施工记录：Context Debug Render 命名收敛

目标：

- 清理 Context Workspace 内部 `RenderContextPrompt*` / `ContextRenderPipeline` 命名。
- 明确这一路径只是 Context Tree 的显式 debug render / tool output，不是 provider prompt assembly。

落地：

- application models：
  - `RenderContextPromptInput` 改为 `ContextDebugRenderInput`。
  - `RenderContextPromptResult` 改为 `ContextDebugRenderResult`。
  - `RenderContextDeltaInput` 改为 `ContextDebugDeltaInput`。
  - `RenderContextDeltaResult` 改为 `ContextDebugDeltaResult`。
- rendering pipeline：
  - `ContextRenderPipeline` 改为 `ContextTreeRenderPipeline`。
  - `render_debug_body(...)` 改为 `render_debug_body(...)`。
  - `render_context_delta_body(...)` 改为 `render_context_debug_delta_body(...)`。
- interfaces / adapters / tools：
  - HTTP `/by-session/{session_key}/render` 和 CLI `render` 保留为用户显式 debug 动作。
  - 内部调用统一使用 `ContextDebugRenderInput` / `render_debug_body(...)`。
  - `tools/context_tree` 调用同步更新。

验证：

- `python -m compileall -q src/crxzipple/modules/context_workspace src/crxzipple/app/integration/context_workspace_orchestration tools/context_tree/local.py tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py`
  - passed
- `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_context_workspace_artifact_adapter.py tests/unit/test_context_workspace_agent_adapter.py tests/unit/test_operations_context_workspace_read_model.py tests/unit/test_context_workspace_http.py`
  - 92 passed
- `PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_runtime_llm_request.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_context_workspace_snapshot_boundary.py tests/unit/test_orchestration_context.py tests/unit/test_turns_http.py::TurnsHttpTestCase::test_turns_endpoint_submits_async_turn_without_exposing_orchestration`
  - 67 passed

## 第五十七轮施工记录：Context Snapshot Debug Body 字段收敛

目标：

- 清理 Context Snapshot 和 debug render payload 中残留的 `prompt_body` / `rendered_prompt`。
- 明确 Context Workspace 持有的是 `debug_body`：只用于显式调试、Context Tree 工具读取和 UI 展示，不是 provider prompt。
- 同步 DB column、HTTP payload、tool details、Operations/Workbench/Trace 读模型和预算 metadata。

落地：

- Context Workspace：
  - `ContextSnapshot.debug_body` 替代 `ContextSnapshot.prompt_body`。
  - `ContextDebugRenderResult.debug_body` / `ContextDebugDeltaResult.debug_body` 替代旧字段。
  - `RecordContextSnapshotInput.debug_body` / HTTP `RecordSnapshotRequest.debug_body` 同步改名。
- persistence / migrations：
  - `context_snapshots.debug_body` 替代 `context_snapshots.prompt_body`。
  - 0063 / 0070 migration 直接写新结构，不保留兼容列。
- metadata：
  - `debug_body_estimate`、`debug_body_chars`、`debug_body_estimated_tokens` 替代 `rendered_prompt_*`。
  - `node_estimate_breakdown.debug_body` 替代 `node_estimate_breakdown.rendered_prompt`。
  - `context_snapshot_budget_metadata(...)` 只输出新 canonical 字段。
- tools / UI：
  - `context_tree.render_current` / `context_tree.read_snapshot` details 输出 `debug_body`。
  - Workbench / Trace context snapshot 类型和展示读取 `debug_body`。
- tests：
  - 更新所有 Context Workspace、Orchestration、LLM renderer、Workbench、HTTP 测试 fixture 和断言。
  - 增加残留扫描，确认 `prompt_body` / `rendered_prompt` 不再存在于 `src` / `frontend` / `tests` / `tools` / `alembic`。

验证：

- `python -m compileall -q src/crxzipple/modules/context_workspace src/crxzipple/app/integration/context_workspace_orchestration src/crxzipple/modules/orchestration src/crxzipple/modules/llm src/crxzipple/modules/operations src/crxzipple/interfaces/http tools/context_tree/local.py`
  - passed
- `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_context_workspace_artifact_adapter.py tests/unit/test_context_workspace_agent_adapter.py tests/unit/test_operations_context_workspace_read_model.py tests/unit/test_context_workspace_http.py`
  - 92 passed
- `PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_runtime_llm_request.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_context_workspace_snapshot_boundary.py tests/unit/test_orchestration_context.py tests/unit/test_turns_http.py::TurnsHttpTestCase::test_turns_endpoint_submits_async_turn_without_exposing_orchestration tests/unit/test_llm.py tests/unit/test_llm_http.py tests/unit/test_runtime_llm_request.py tests/unit/test_llm_adapters.py tests/unit/test_anthropic_renderer.py tests/unit/test_operations_llm_read_model.py tests/unit/test_workbench_read_model.py tests/unit/test_context_snapshot_metadata.py tests/unit/test_tool_providers.py::ToolProvidersTestCase::test_scanned_tool_packages_register_system_tools_without_bootstrap_hardcoding`
  - 282 passed
- `cd frontend && npm run typecheck`
  - passed
- `rg -n "prompt_body|rendered_prompt|debug_body_body" src frontend tests tools alembic || true`
  - no output
- `git diff --check`
  - passed

## 第五十八轮施工记录：Orchestration Runtime Request Draft 命名收敛

目标：

- 清理 Orchestration 中残留的 `RuntimeLlmRequestDraft` / `RuntimeLlmRequestPreview` / `prompt_input.py` / `/prompt-preview` 命名。
- 明确 Orchestration 收集的是 Runtime LLM Request Draft，不是 provider prompt，也不是 provider wire payload。
- 区分两个不同语义：
  - `runtime_request_draft`：Context Snapshot provider attachments 中的 draft 摘要对象。
  - `runtime_request_surface`：LLM request metadata 中的 surface 字符串。

落地：

- Orchestration：
  - `prompt_input.py` 改为 `runtime_llm_request_draft.py`。
  - `RuntimeLlmRequestDraft` 改为 `RuntimeLlmRequestDraft`。
  - `RuntimeLlmRequestPreview` 改为 `RuntimeLlmRequestPreview`。
  - `OrchestrationEngine.prompt_inputs` 改为 `runtime_request_drafts`。
  - `preview_prompt(...)` 改为 `preview_runtime_llm_request(...)`。
  - `_build_prompt_input(...)` 改为 `_build_runtime_request_draft(...)`。
- HTTP / CLI / frontend：
  - `/turns/{run_id}/prompt-preview` 改为 `/turns/{run_id}/llm-request-preview`。
  - `/llms/calls/{invocation_id}/prompt-preview` 改为 `/llms/calls/{invocation_id}/llm-request-preview`。
  - orchestration CLI `prompt-preview` 改为 `llm-request-preview`。
  - frontend `promptPreview.ts` 改为 `runtimeRequestPreview.ts`，Workbench / Trace loader 和 state 同步改名。
- Context Snapshot / request metadata：
  - provider attachments 顶层 key 从 `prompt_input` 改为 `runtime_request_draft`。
  - runtime request metadata 字段从 `prompt_input` 改为 `runtime_request_surface`。
  - Context Workspace skill surface metadata 读取 `runtime_request_surface`。
- tests：
  - `test_prompt_input_collector.py` 改为 `test_runtime_llm_request_draft_collector.py`。
  - 更新 HTTP、LLM、Workbench、Context Snapshot、runtime request builder 测试断言。

验证：

- `python -m compileall -q src/crxzipple/modules/orchestration src/crxzipple/app src/crxzipple/interfaces src/crxzipple/modules/llm tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_turns_http.py tests/unit/test_llm_http.py`
  - passed
- `PYTHONPATH=src pytest -q tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_turn_submission_prompt_bootstrap.py tests/unit/test_app_assembly_architecture.py tests/unit/test_orchestration_service_surface.py tests/unit/test_turns_http.py tests/unit/test_llm_http.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_runtime_llm_request.py`
  - 121 passed
- `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_operations_context_workspace_read_model.py tests/unit/test_context_workspace_artifact_adapter.py tests/unit/test_context_workspace_agent_adapter.py tests/unit/test_context_workspace_http.py tests/unit/test_orchestration_runtime_llm_request.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_context_workspace_snapshot_boundary.py tests/unit/test_llm.py tests/unit/test_llm_http.py tests/unit/test_llm_adapters.py tests/unit/test_anthropic_renderer.py tests/unit/test_runtime_llm_request.py tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_turns_http.py::TurnsHttpTestCase::test_turns_endpoint_submits_async_turn_without_exposing_orchestration tests/unit/test_orchestration_context.py tests/unit/test_context_snapshot_metadata.py tests/unit/test_workbench_read_model.py tests/unit/test_tool_providers.py::ToolProvidersTestCase::test_scanned_tool_packages_register_system_tools_without_bootstrap_hardcoding`
  - 292 passed
- `cd frontend && npm run typecheck`
  - passed
- `rg -n "RuntimeLlmRequestDraft|RuntimeLlmRequestPreview|prompt_input\\.py|prompt-preview|PromptPreview|promptPreview|contextPromptPreview|load.*PromptPreview|prompt_inputs|_build_prompt_input|preview_prompt" src frontend tests tools alembic || true`
  - no output
- `git diff --check`
  - passed

## 第五十九轮施工记录：Runtime Request Report 命名收敛

目标：

- 清理 Orchestration / HTTP / frontend / tests 中残留的 `PromptReport` / `prompt_report` 命名。
- 明确该报告描述的是 runtime request draft 的预算、transcript、context snapshot，不是 provider prompt。
- 迁移旧测试中“Context Workspace 会作为 system prompt block 进入模型输入”的断言，改为验证 Context Snapshot debug body。

落地：

- Orchestration prompting report：
  - `PromptReport` 改为 `RuntimeRequestReport`。
  - `PromptReportBlock` 改为 `RuntimeRequestReportBlock`。
  - `prompt_report` payload key 改为 `runtime_request_report`。
  - `prompt_report_build` phase 改为 `runtime_request_report_build`。
- Engine / DTO / HTTP / frontend：
  - `EngineAdvanceOutcome.runtime_request_report` 替代旧字段。
  - `RuntimeLlmRequestPreview.runtime_request_report` 替代旧字段。
  - turns / LLM preview response 输出 `runtime_request_report`。
  - frontend runtime request preview 类型同步读取 `runtime_request_report`。
- Tests：
  - `test_orchestration_memory.py` 不再查找 `prompt_block_kind=context_workspace` 的 system message。
  - 相关断言改为通过 run `context_snapshot_id` 读取 Context Snapshot `debug_body`。
  - runtime request report 的 `context_blocks` 断言更新为当前边界：默认不再携带旧 prompt context blocks。

验证：

- `python -m compileall -q src/crxzipple/modules/orchestration src/crxzipple/app src/crxzipple/interfaces src/crxzipple/modules/llm tests/unit/test_runtime_transcript.py tests/unit/test_runtime_llm_request_draft_collector.py`
  - passed
- `PYTHONPATH=src pytest -q tests/unit/test_orchestration_memory.py`
  - 19 passed
- `PYTHONPATH=src pytest -q tests/unit/test_runtime_transcript.py tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_turns_http.py tests/unit/test_llm_http.py tests/unit/test_orchestration_context.py tests/unit/test_orchestration_memory.py tests/unit/test_orchestration_tools.py tests/unit/test_orchestration_cli.py`
  - 191 passed
- `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_operations_context_workspace_read_model.py tests/unit/test_context_workspace_artifact_adapter.py tests/unit/test_context_workspace_agent_adapter.py tests/unit/test_context_workspace_http.py tests/unit/test_orchestration_runtime_llm_request.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_context_workspace_snapshot_boundary.py tests/unit/test_llm.py tests/unit/test_llm_http.py tests/unit/test_llm_adapters.py tests/unit/test_anthropic_renderer.py tests/unit/test_runtime_llm_request.py tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_turns_http.py::TurnsHttpTestCase::test_turns_endpoint_submits_async_turn_without_exposing_orchestration tests/unit/test_orchestration_context.py tests/unit/test_context_snapshot_metadata.py tests/unit/test_workbench_read_model.py tests/unit/test_tool_providers.py::ToolProvidersTestCase::test_scanned_tool_packages_register_system_tools_without_bootstrap_hardcoding`
  - 292 passed
- `cd frontend && npm run typecheck`
  - passed
- `rg -n "PromptReport|PromptReportBlock|prompt_report|prompt report|Prompt report" src frontend tests tools alembic || true`
  - no output
- `git diff --check`
  - passed

## 第六十轮施工记录：旧 PromptBlock 组装面退场

目标：

- 清理 Orchestration 中最后一条旧 prompt block / prompt budget 组装路径。
- 让 runtime request report 不再暴露空的 `context_blocks`，避免旧 PromptBlock 概念继续污染链路观察。
- 保留必要的文本 token 粗估能力，但把它从 `prompting` 包迁到中性的 runtime estimate helper。

落地：

- Orchestration：
  - 新增 `token_estimates.py`，承载 `estimate_text_tokens(...)`。
  - `runtime_llm_request_draft.py`、`prompt_transcript.py`、`maintenance.py` 改为从 `token_estimates` 导入估算函数。
  - `prompting.blocks` 删除 `PromptBlockPolicy`、`PromptBlock`、`RuntimeRequestReportBlock`。
  - `RuntimeRequestReport` 删除 `context_blocks` 字段和 payload 输出。
  - 删除旧 `prompting/budget.py` 与 `prompting/producers.py`。
- Tests：
  - 删除旧 `tests/unit/test_prompting.py`。
  - `RuntimeRequestReport(...)` fixture 删除 `context_blocks=()` 构造参数。
  - 运行链路、HTTP、memory、tool 相关断言改为确认 `runtime_request_report` 不再暴露 `context_blocks`。

验证：

- `python -m compileall -q src/crxzipple/modules/orchestration src/crxzipple/app src/crxzipple/interfaces tests/unit/test_runtime_transcript.py tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_orchestration_context.py tests/unit/test_orchestration_memory.py tests/unit/test_orchestration_tools.py tests/unit/test_turns_http.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_runtime_llm_request_builder.py`
  - passed
- `PYTHONPATH=src pytest -q tests/unit/test_runtime_transcript.py tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_runtime_llm_request_builder.py`
  - 68 passed
- `PYTHONPATH=src pytest -q tests/unit/test_orchestration_context.py tests/unit/test_orchestration_memory.py tests/unit/test_orchestration_tools.py tests/unit/test_turns_http.py`
  - 83 passed
- `cd frontend && npm run typecheck`
  - passed
- `rg -n "PromptBlock|PromptBlockPolicy|RuntimeRequestReportBlock|apply_system_prompt_budget|build_agent_instruction_block|build_runtime_context_block|DEFAULT_SYSTEM_PROMPT|prompting\\.budget|prompting\\.producers" src frontend tests tools alembic -g '*.{py,ts,tsx,vue}' || true`
  - no output
- `git diff --check`
  - passed

## 第六十一轮施工记录：Orchestration Prompting 包退场

目标：

- 清理 `orchestration.application.prompting` 包本身，避免旧 “prompting/PromptMode” 命名继续暗示 Orchestration 拥有 provider prompt 组装职责。
- 把仍然有效的 runtime request mode、surface policy、runtime request report 移到明确的 runtime request 边界。
- 把 Context Workspace orchestration integration 使用的 runtime context 文本 helper 移回 integration 自己名下。

落地：

- Orchestration：
  - `prompting/modes.py` 改为 `runtime_request_mode.py`。
  - `PromptMode` 改为 `RuntimeRequestMode`。
  - `prompting/blocks.py` 改为 `runtime_request_report.py`。
  - `RunSurfacePolicy`、`resolve_run_surface_policy`、`ContextSnapshotReport`、`RuntimeRequestReport` 改由 `runtime_request_report.py` 提供。
  - 删除 `prompting/__init__.py` 并移除空 `prompting/` 目录。
- Context Workspace integration：
  - `prompting/runtime_context.py` 移为 `app/integration/context_workspace_orchestration/runtime_context_message.py`。
  - `run_workspace_metadata.py` 改为从 integration-local helper 导入。
- Tests：
  - 所有 `PromptMode` 引用改为 `RuntimeRequestMode`。
  - 所有 `application.prompting` import 改为 runtime request mode/report 直接 import。
  - 架构测试的 retired prompt helper 清单移除当前合法的 `runtime_llm_request_draft.py`，只禁止真正退场的旧 helper。

验证：

- `python -m compileall -q src/crxzipple/modules/orchestration src/crxzipple/app src/crxzipple/interfaces tests/unit/test_runtime_transcript.py tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_orchestration_runtime_llm_request.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_context_workspace_snapshot_boundary.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_module_lifecycle_architecture.py`
  - passed
- `PYTHONPATH=src pytest -q tests/unit/test_runtime_transcript.py tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_orchestration_runtime_llm_request.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_context_workspace_snapshot_boundary.py tests/unit/test_module_lifecycle_architecture.py`
  - 66 passed
- `PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_context.py tests/unit/test_orchestration_memory.py tests/unit/test_turns_http.py`
  - 71 passed
- `rg -n "application\\.prompting|PromptMode|prompting/|prompting\\." src tests -g '*.py' || true`
  - no output
- `cd frontend && npm run typecheck`
  - passed
- `git diff --check`
  - passed

## 第六十二轮施工记录：Run Context Snapshot Port 命名收敛

目标：

- 清理 Context Workspace orchestration adapter / port 中残留的 `run_prompt_snapshot` 命名。
- 明确该 adapter 记录的是 run 绑定的 Context Snapshot，不是 provider prompt，也不是 prompt render。

落地：

- Context Workspace integration：
  - `ContextWorkspacePromptSnapshotAdapter` 改为 `ContextWorkspaceRunSnapshotAdapter`。
  - `record_run_prompt_snapshot(...)` 改为 `record_run_context_snapshot(...)`。
  - `preview_run_prompt_snapshot(...)` 改为 `preview_run_context_snapshot(...)`。
  - `get_recorded_run_prompt_snapshot(...)` 改为 `get_recorded_run_context_snapshot(...)`。
  - `_render_run_prompt_snapshot(...)` 改为 `_render_run_context_snapshot(...)`。
  - adapter docstring 改为返回 `ContextSnapshotRecord`，不再描述为 provider delivery 的 rendered prompt body。
- Orchestration：
  - `ContextSnapshotPort` protocol 同步改名。
  - `OrchestrationEngine` 调用和错误信息同步改为 context snapshot wording。
- Tests：
  - Context Workspace snapshot adapter tests / fake ports 同步改名。

验证：

- `python -m compileall -q src/crxzipple/app/integration/context_workspace_orchestration src/crxzipple/modules/orchestration tests/unit/test_orchestration_context_workspace_snapshot.py`
  - passed
- `PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_context_workspace_snapshot_boundary.py`
  - 48 passed
- `PYTHONPATH=src pytest -q tests/unit/test_app_assembly_architecture.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_context.py tests/unit/test_turns_http.py`
  - 75 passed
- `rg -n "ContextWorkspacePromptSnapshotAdapter|record_run_prompt_snapshot|preview_run_prompt_snapshot|get_recorded_run_prompt_snapshot|_render_run_prompt_snapshot|prompt snapshot|prompt snapshots|prompt render|prompt preview|recent prompt renders|rendered prompt body" src tests -g '*.py' || true`
  - no output
- `cd frontend && npm run typecheck`
  - passed
- `rg -n "ContextWorkspacePromptSnapshotAdapter|record_run_prompt_snapshot|preview_run_prompt_snapshot|get_recorded_run_prompt_snapshot|_render_run_prompt_snapshot|prompt snapshot|prompt snapshots|prompt render|prompt preview|recent prompt renders|rendered prompt body" src frontend tests -g '*.{py,ts,tsx,vue}' || true`
  - no output
- `git diff --check`
  - passed

## 第六十三轮施工记录：Runtime Request Mode / Flow Hint Metadata 收敛

目标：

- 清理运行 metadata 和 request metadata 中残留的 `prompt_mode` / `prompt_flow_hint` / `prompt_bootstrap` 命名。
- 明确这些字段描述的是 runtime request mode、runtime request flow hint 和 runtime request bootstrap policy，不是 provider prompt。
- 不保留旧 key 兼容；历史数据可重建。

落地：

- Orchestration metadata：
  - `prompt_mode` 改为 `runtime_request_mode`。
  - `prompt_flow_hint` 改为 `runtime_request_flow_hint`。
  - `prompt_bootstrap_policy` 改为 `runtime_request_bootstrap_policy`。
  - `prompt_bootstrap_metadata_for_content(...)` 改为 `runtime_request_bootstrap_metadata_for_content(...)`。
- Orchestration application：
  - `SessionRunPreparationWorkflow.prompt_flow_hint_factory` 改为 `runtime_request_flow_hint_factory`。
  - `session_start_prompt_flow_hint(...)` 改为 `session_start_runtime_request_flow_hint(...)`。
  - `prompt_flow_hint_from_input(...)` 改为 `runtime_request_flow_hint_from_input(...)`。
  - `RuntimeLlmRequestDraftCollector._prompt_flow_hint_payload(...)` 改为 `_runtime_request_flow_hint_payload(...)`。
  - `_prompt_bootstrap_hint_from_metadata(...)` 改为 `_runtime_request_bootstrap_hint_from_metadata(...)`。
  - Tool resolver 的 `_coerce_prompt_mode(...)` 改为 `_coerce_runtime_request_mode(...)`。
  - assignment lifecycle / execution / service graph 的 clear hook 改为 `clear_runtime_request_flow_hint(...)`。
- HTTP / LLM / Context Workspace / Workbench：
  - HTTP turn submission 使用 `runtime_request_bootstrap_metadata_for_content(...)`。
  - LLM request metadata 读取 `runtime_request_mode`。
  - Context Workspace root metadata 读取 `runtime_request_mode`。
  - Workbench key-value label 改为 `Runtime request mode`。
- Tests：
  - `test_turn_submission_prompt_bootstrap.py` 改为 `test_turn_submission_runtime_request_bootstrap.py`。
  - 相关断言改为新 key；测试函数名同步改为 runtime request bootstrap/mode wording。

验证：

- `python -m compileall -q src/crxzipple/modules/orchestration src/crxzipple/app src/crxzipple/interfaces tests/unit/test_turn_submission_runtime_request_bootstrap.py tests/unit/test_orchestration_memory.py tests/unit/test_turns_http.py tests/unit/test_orchestration_context_workspace_snapshot.py`
  - passed
- `PYTHONPATH=src pytest -q tests/unit/test_turn_submission_runtime_request_bootstrap.py tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_turns_http.py tests/unit/test_orchestration_memory.py`
  - 43 passed
- `PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_context.py tests/unit/test_orchestration_tools.py tests/unit/test_orchestration_http.py`
  - 88 passed
- `rg -n "prompt_mode|prompt_flow_hint|prompt_bootstrap|Prompt mode|turn_submission_prompt_bootstrap" src tests frontend -g '*.{py,ts,tsx,vue}' || true`
  - no output
- `cd frontend && npm run typecheck`
  - passed
- `git diff --check`
  - passed

## 第六十四轮施工记录：Runtime Request Draft / Tool Runtime Request Surface 命名收敛

目标：

- 清理 Orchestration、Tool Source、Context Workspace integration 中仍残留的 `prompt` 语义命名。
- 明确 Orchestration 只持有 runtime request draft 和 context snapshot refs，不生产 provider prompt。
- 明确 Tool module 输出的是 runtime request 工具面策略，不是 prompt bundle。
- 保留图像工具自身业务参数 `prompt`，因为它是 OpenAI image API 的领域参数，不属于 runtime request assembly。

落地：

- Orchestration runtime request：
  - `prompt_with_context_snapshot(...)` 改为 `draft_with_context_snapshot(...)`。
  - `resolved_tools_for_prompt(...)` 改为 `resolved_tools_for_draft(...)`。
  - `ContextSnapshotPort` 的 `prompt` 参数改为 `draft`。
  - `_input_items_for_prompt_messages(...)` 改为 `_input_items_for_draft_messages(...)`。
  - `OrchestrationEngine` 内部 `_ResolvedRuntimeLlmRequestDraft.prompt` / `_AdvanceContext.prompt` 改为 `draft`。
- Context Workspace orchestration integration：
  - `resolve_prompt_tool_schema_metadata(...)` 改为 `resolve_draft_tool_schema_metadata(...)`。
  - tool source policy metadata 从 `prompt` 改为 `runtime_request`。
  - `source_prompt.default_tool_schema_group_refs` 改为 `source_runtime_request.default_tool_schema_group_refs`。
  - budget summary 文案改为 runtime request 口径。
- Tool module：
  - `ToolPromptBundle` 改为 `ToolRuntimeRequestBundle`。
  - `ToolPromptBundleGroup` 改为 `ToolRuntimeRequestBundleGroup`。
  - `ToolSourceQueryService.list_prompt_bundles(...)` 改为 `list_runtime_request_bundles(...)`。
  - tool package manifest 顶层 `prompt:` 改为 `runtime_request:`。
  - tool source id 中的 `prompt_group` 改为 `runtime_request_group`。
  - persistence / catalog / activation / surface read model 同步改为 `runtime_request_metadata`。
- LLM canonical runtime context：
  - `RuntimeLlmContext` 新增 `debug_body`。
  - Context Snapshot debug body 进入 `context_surface.debug_body`，作为 provider renderer 的可选输入事实。
  - debug body 不再作为 system message、transcript item 或 provider-visible prompt body 直接发送。
- Tests：
  - approval fake adapter 和 approval tests 改为从 `request_metadata["context_surface"]["debug_body"]` 读取 Context Tree debug body。
  - boundary tests 明确断言 full tree debug body 不进入 `messages` 或 `transcript`。
  - tool source / catalog / adapter tests 改为 runtime request metadata 口径。

验证：

- `python -m compileall -q src/crxzipple/modules/tool src/crxzipple/app/integration/context_workspace_tool.py src/crxzipple/app/assembly/context_workspace.py tests/unit/test_tool_source_service.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_tool_providers.py tests/unit/test_app_assembly_targets.py tests/unit/test_tool_catalog.py`
  - passed
- `python -m compileall -q src/crxzipple/modules/orchestration/application src/crxzipple/app/integration/context_workspace_orchestration src/crxzipple/modules/llm/application/runtime_request.py tests/unit/orchestration_test_support.py tests/unit/test_orchestration_approval.py`
  - passed
- `PYTHONPATH=src pytest -q tests/unit/test_tool_source_service.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_tool_providers.py tests/unit/test_app_assembly_targets.py tests/unit/test_tool_catalog.py`
  - 98 passed
- `PYTHONPATH=src pytest -q tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_context_workspace_snapshot_boundary.py tests/unit/test_orchestration_runtime_llm_request.py`
  - 49 passed
- `PYTHONPATH=src pytest -q tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_context_workspace_snapshot_boundary.py tests/unit/test_orchestration_runtime_llm_request.py tests/unit/test_orchestration_approval.py::OrchestrationApprovalTestCase::test_process_next_orchestration_assignment_includes_approval_resume_flow_node tests/unit/test_orchestration_approval.py::OrchestrationApprovalTestCase::test_process_next_orchestration_assignment_includes_approval_denied_flow_node`
  - 51 passed
- `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tool_adapter.py::test_core_default_schemas_come_from_tool_source_runtime_request_policy tests/unit/test_tool_catalog.py::ToolCatalogTestCase::test_build_tool_surface_can_persist_request_time_snapshot tests/unit/test_tool_source_service.py::ToolSourceServiceTestCase::test_query_service_uses_openapi_source_runtime_request_metadata`
  - 3 passed
- `rg -n '"prompt"|^prompt:|prompt_group|source_prompt|ToolPrompt|list_prompt_bundles|prompt_block_kind|_input_items_for_prompt|\.prompt\b|plan\.prompt|\["prompt"\]|prompt_metadata|context_tree\.prompt|context\.prompt\.rendered|_prompt_metadata_from_outcome' ...`
  - only `tools/openai_image/local.py` image prompt argument remains
- `git diff --check`
  - passed

## 第六十五轮施工记录：Runtime Transcript 与 Context Tree 文档边界收敛

目标：

- 清理 Orchestration 中最后一个真实代码入口 `prompt_transcript.py` 的旧命名。
- 明确 transcript/replay window 是 provider-neutral runtime transcript，不是 prompt assembly。
- 修正 Context Workspace 主文档中“树就是 prompt / tree prompt body”的旧目标，防止后续施工继续把 Context Tree 当 provider prompt 发送。

落地：

- Orchestration：
  - `prompt_transcript.py` 改为 `runtime_transcript.py`。
  - `PromptTranscript` 改为 `RuntimeTranscript`。
  - `build_model_visible_session_item_prompt_window(...)` 改为 `build_model_visible_session_item_runtime_window(...)`。
  - `runtime_llm_request_draft.py` 改为从 `runtime_transcript` 导入 runtime transcript window。
- Tests：
  - `test_prompt_transcript.py` 改为 `test_runtime_transcript.py`。
  - `PromptTranscriptTestCase` 改为 `RuntimeTranscriptTestCase`。
  - Operations LLM read model 测试名改为 runtime transcript budget metadata。
  - `tests/unit/README.md` 同步改为 `test_runtime_transcript.py`。
- Docs：
  - `docs/orchestration-design.md` 的模块结构从 `prompt_input.py` 改为 `runtime_llm_request_draft.py` / `runtime_llm_request.py`。
  - `docs/agents/hosted-agent-operating-contract.md` 的 Tool surface 和 Context Snapshot 约束改为 `runtime_request.groups` / `context_snapshot_id` 口径。
  - `docs/context-workspace-prompt-tree-design.md` 明确：Context Tree 是 runtime canonical context，不是 provider prompt；provider wire input 由 LLM renderer 生成。
  - `docs/context-workspace-prompt-tree-development.md` 明确：Context Snapshot 记录 runtime context 状态和 debug body；XML-like tree render 只用于 debug body 或显式 `context_tree.*` 工具输出，不作为默认 provider input。

验证：

- `python -m compileall -q src/crxzipple/modules/orchestration/application/runtime_transcript.py src/crxzipple/modules/orchestration/application/runtime_llm_request_draft.py tests/unit/test_runtime_transcript.py tests/unit/test_operations_llm_read_model.py`
  - passed
- `PYTHONPATH=src pytest -q tests/unit/test_runtime_transcript.py tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_operations_llm_read_model.py::test_llm_operations_page_exposes_runtime_transcript_budget_metadata`
  - 22 passed
- `rg -n 'prompt_transcript|test_prompt_transcript|prompt_input|RunPromptInput|PromptInput|ContextRenderSnapshot|context_render_snapshot|context_render_snapshots' src/crxzipple tests/unit docs/README.md docs/agents docs/orchestration-design.md docs/context-workspace-prompt-tree-design.md docs/context-workspace-prompt-tree-development.md -g '*.{py,md}'`
  - no output

## 第六十六轮施工记录：Workbench / Trace / Operations 可见口径收敛

目标：

- 清理 Workbench、Trace、Operations 中仍然向用户展示的 `Prompt XML`、`Prompt Budget`、`Provider Prompt Tokens`、`Prompt Tree` 等旧口径。
- 移除前端从 runtime request preview messages 中查找 `prompt_block_kind=context_workspace` 的旧 fallback。
- 明确用户界面展示的是 Context Snapshot debug body、runtime request preview 和 provider wire preview，而不是把 Context Tree 当 provider prompt。

落地：

- Workbench：
  - Context request card title 从 `Recorded Request` 改为 `Recorded Context Snapshot`。
  - `Prompt XML` 改为 `Context Debug XML`。
  - `Rendered Prompt Tokens` 改为 `Debug Body Tokens`。
  - `Provider Prompt Tokens` 改为 `Provider Input Tokens`。
  - `contextPreviewPromptBody` fallback 删除；没有 recorded `contextSnapshot.debug_body` 时不再从 messages 里反推旧 context prompt block。
- Trace：
  - 同步删除 `contextPreviewPromptBody` fallback。
  - Context snapshot rows 改为 `Debug Body Tokens` / `Provider Input Tokens`。
  - XML 面板标题改为 `Context Debug XML`。
- Operations Context Workspace：
  - page subtitle 从 Prompt Tree 改为 Context Tree。
  - section title 从 `Prompt Budget` 改为 `Context Budget`。
  - metric label 从 `Provider Prompt Tokens` 改为 `Provider Input Tokens`。
  - snapshot-visible 节点数说明不再显示 `prompt-visible`。
- i18n：
  - `en-US` / `zh-CN` 用户可见文案同步改为 Context Snapshot / Debug Body / Provider Input 口径。

验证：

- `cd frontend && npm run typecheck`
  - passed
- `PYTHONPATH=src pytest -q tests/unit/test_operations_context_workspace_read_model.py`
  - 2 passed
- `rg -n 'Prompt Tree|Prompt Budget|Provider Prompt Tokens|Prompt XML|renderedPromptTokens|providerPromptTokens|actualPromptSnapshot|promptXml|promptChars|contextPreviewPromptBody|prompt_block_kind' frontend/src/pages/workbench/WorkbenchPage.vue frontend/src/pages/trace/TracePage.vue frontend/src/shared/i18n/messages/en-US.ts frontend/src/shared/i18n/messages/zh-CN.ts frontend/src/pages/operations/modules/ContextWorkspaceOperationsPage.vue src/crxzipple/modules/operations/application/read_models/context_workspace.py tests/unit/test_operations_context_workspace_read_model.py`
  - only internal i18n key `operations.contextWorkspace.metric.providerPromptTokens` remains; rendered value is `Provider Input Tokens`
- `git diff --check`
  - passed

## 第六十七轮施工记录：Context Snapshot 命名与 Provider Input 口径收敛

目标：

- 清掉 Context Tree 状态、Operations read model、Workbench/Trace 和维护流程中会把树误读成 prompt 的旧命名。
- 保持核心原则：Context Tree 是 runtime canonical context；provider/model 实际输入由 LLM provider renderer 生成。
- 不保留旧字段兼容，不引入双轨 fallback。

落地：

- Context Workspace：
  - `ContextNodeState.prompt_visible` 改为 `snapshot_visible`。
  - `tree_prompt_visible_nodes(...)` 改为 `tree_snapshot_visible_nodes(...)`。
  - Context render pipeline 和 provider mirror 改为按 `snapshot_visible` 判断 snapshot/debug body 可见性。
  - runtime contract/root guide 改为说明 Context Tree 是 runtime context state，不是 provider prompt。
- Tool runtime request：
  - 测试和 mock adapter 中 `ToolPromptBundle` / `list_prompt_bundles` 旧口径改为 `ToolRuntimeRequestBundle` / `list_runtime_request_bundles`。
  - Context Tree 工具说明改为读取当前 tree debug body，而不是“full current prompt text”。
- Operations / UI：
  - Context Workspace section id 从 `prompt_budget` 改为 `context_budget`。
  - Operations rows 中 `prompt_nodes` 改为 `snapshot_nodes`。
  - `Provider Prompt Tokens` / `provider_prompt_tokens` 改为 `Provider Input Tokens` / `provider_input_tokens`。
  - snapshot metadata key 从 `estimated_provider_prompt_tokens` 改为 `estimated_provider_input_tokens`。
- Orchestration maintenance：
  - preflight maintenance 预算命名从 prompt budget/threshold 改为 context budget/threshold。
  - compaction trigger basis 从 `prompt_budget` 改为 `context_budget`。
  - compaction reason 从 `auto_compaction_prompt_budget_exceeded` 改为 `auto_compaction_context_budget_exceeded`。
  - runtime request preview 构建错误不再称为 prompt surface preview。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_context_render_xml_renderer.py tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py tests/unit/test_operations_context_workspace_read_model.py`
  - 39 passed
- `PYTHONPATH=src pytest -q tests/unit/test_tool_source_service.py tests/unit/test_context_workspace_tool_adapter.py::test_source_kind_tags_do_not_become_runtime_request_bundle_titles`
  - 19 passed
- `PYTHONPATH=src pytest -q tests/unit/test_operations_context_workspace_read_model.py tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_operations_module_pages_expose_named_sections`
  - 3 passed
- `PYTHONPATH=src pytest -q tests/unit/test_orchestration_memory.py::OrchestrationMemoryTestCase::test_preflight_maintenance_runs_inline_before_followup_when_context_budget_is_exceeded tests/unit/test_orchestration_memory.py::OrchestrationMemoryTestCase::test_preflight_maintenance_fails_run_when_compaction_cannot_recover_context_budget tests/unit/test_context_workspace_session_adapter.py::test_session_adapter_keeps_long_browser_tool_chain_under_context_budget`
  - 3 passed
- `PYTHONPATH=src pytest -q tests/unit/test_context_snapshot_metadata.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_operations_context_workspace_read_model.py tests/unit/test_operations_llm_read_model.py`
  - 55 passed
- `cd frontend && npm run typecheck`
  - passed
- `python -m compileall -q ...`
  - passed
- `rg -n 'prompt_visible|tree_prompt_visible_nodes|ToolPromptBundle|list_prompt_bundles|prompt_bundle|PromptBundle|prompt surface|Context Tree is the prompt|current prompt surface|Prompt surface budget|full current prompt text|prompt context tree|prompt_budget|prompt_threshold|auto_compaction_prompt|provider_prompt_tokens|Provider Prompt|estimated_provider_prompt_tokens' ...`
  - no output
- `git diff --check`
  - passed

## 第六十八轮施工记录：Skills Runtime Request Catalog 迁移

目标：

- 清理 Skills 模块向 Orchestration 暴露的 `prompt_catalog` / `SkillPromptResolution` 旧边界。
- 保持 Skills 作为 runtime request 供料模块，而不是 prompt 拼装模块。
- 不保留旧别名或兼容方法。

落地：

- Skills：
  - `SkillCatalogPrompt` 改为 `SkillRuntimeRequestCatalog`。
  - `build_skill_catalog_prompt(...)` 改为 `build_skill_runtime_request_catalog(...)`。
  - `prompt_resolver.py` 改为 `runtime_request_resolver.py`。
  - `SkillPromptResolutionContext` 改为 `SkillRuntimeRequestResolutionContext`。
  - `SkillPromptResolution` 改为 `SkillRuntimeRequestResolution`。
  - `SkillPromptResolver` 改为 `SkillRuntimeRequestResolver`。
  - `prompt_catalog` 属性改为 `runtime_request_catalog`。
  - `build_prompt_catalog(...)` / `resolve_prompt_catalog(...)` 改为 `build_runtime_request_catalog(...)` / `resolve_runtime_request_catalog(...)`。
  - owner state 持久化入口从 `persist_prompt_readiness_snapshots(...)` 改为 `persist_runtime_request_readiness_snapshots(...)`。
- App integration / assembly：
  - `skill_prompt_resolution.py` 改为 `skill_runtime_request_resolution.py`。
  - Skills assembly 构造 `SkillRuntimeRequestResolver`。
- Orchestration：
  - Skills port 改为 runtime request catalog 口径。
  - `RuntimeLlmRequestDraftCollector` 使用 `resolve_runtime_request_catalog(...)` 和 `runtime_request_catalog`。
- Tests：
  - Skills、runtime request draft collector、assembly architecture 测试同步改为 runtime request catalog 口径。
  - 测试 fake 中的局部 `prompt` 改为 `catalog`，避免未来 grep 误判。

验证：

- `PYTHONPATH=src pytest -q tests/unit/test_skills_context.py tests/unit/test_skills_owner_catalog_persistence.py tests/unit/test_runtime_llm_request_draft_collector.py`
  - 49 passed
- `PYTHONPATH=src pytest -q tests/unit/test_app_assembly_architecture.py::test_orchestration_does_not_own_skill_runtime_request_resolution tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_skills_owner_catalog_persistence.py`
  - 19 passed
- `python -m compileall -q src/crxzipple/modules/skills src/crxzipple/app/assembly/skills.py src/crxzipple/app/integration/skill_runtime_request_resolution.py src/crxzipple/modules/orchestration/application/runtime_llm_request_draft.py tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_skills_owner_catalog_persistence.py`
  - passed
- `rg -n 'SkillCatalogPrompt|build_skill_catalog_prompt|SkillPromptResolution|SkillPromptResolver|prompt_resolver|prompt_catalog|build_prompt_catalog|resolve_prompt_catalog|persist_prompt_readiness_snapshots|skill_prompt_resolution' src/crxzipple tests/unit -g '*.py'`
  - no output

## 第六十九轮施工记录：Context Surface 退场为 Context Snapshot

目标：

- 移除 `context_surface` / `ContextSurface` 旧命名，避免把 Context Tree/Context Snapshot 误读成 provider-visible prompt surface。
- 保留 Context Workspace 的 runtime truth：Context Tree 和 Context Snapshot 是状态与审计事实；provider wire input 由 LLM renderer 生成。
- 不提供旧 `context_surface` 字段兼容。

落地：

- LLM runtime request：
  - `RuntimeLlmContext` 改为 `RuntimeLlmContextSnapshot`。
  - `RuntimeLlmRequest.context_surface` 改为 `context_snapshot`。
  - request metadata key 从 `context_surface` 改为 `context_snapshot`。
  - `context_surface_preview_payload(...)` 改为 `context_snapshot_preview_payload(...)`。
- Orchestration：
  - `RuntimeLlmRequestPreview.context_surface` 改为 `context_snapshot`。
  - `_context_surface_from_snapshot(...)` 改为 `_context_snapshot_from_snapshot(...)`。
  - `_context_surface_diagnostics(...)` 改为 `_context_snapshot_diagnostics(...)`。
  - DTO/HTTP preview response 只保留一个 `context_snapshot` 字段；runtime request report 内部仍自带自己的 report payload。
- Provider adapter / LLM owner：
  - provider request preview 摘要字段从 `context_surface_*` 改为 `context_snapshot_*`。
  - provider render preview 只输出 snapshot id、tree schema version、included node count、fingerprint，不泄露 debug body。
- Operations / Workbench：
  - LLM detail payload 从 `model_visible_surface` 改为 `provider_input_summary`。
  - linked LLM invocation detail 前端改读 `provider_input_summary.context_snapshot_*`。
  - Operations LLM runtime request summary 使用 `context_snapshot`。
- Tests：
  - Runtime request、provider adapters、Operations、Workbench/UI HTTP 测试同步改为 context snapshot 口径。

验证：

- `python -m compileall -q src/crxzipple/modules/llm/application/runtime_request.py src/crxzipple/modules/llm/application/services.py src/crxzipple/modules/llm/infrastructure/adapters/common.py src/crxzipple/modules/orchestration/application/runtime_llm_request.py src/crxzipple/modules/orchestration/application/engine.py src/crxzipple/modules/orchestration/interfaces/dto.py src/crxzipple/interfaces/http/turns.py src/crxzipple/interfaces/http/ui.py src/crxzipple/modules/operations/application/read_models/llm.py`
  - passed
- `PYTHONPATH=src pytest -q tests/unit/test_runtime_llm_request.py tests/unit/test_orchestration_runtime_llm_request.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_context_workspace_snapshot_boundary.py tests/unit/test_turns_http.py tests/unit/test_operations_llm_read_model.py`
  - 38 passed
- `PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py tests/unit/test_anthropic_renderer.py tests/unit/test_openai_codex_renderer.py tests/unit/test_provider_renderer_canonical_request_integration.py`
  - 84 passed
- `PYTHONPATH=src pytest -q tests/unit/test_ui_http.py tests/unit/test_workbench_read_model.py`
  - 56 passed
- `cd frontend && npm run typecheck`
  - passed
- `rg -n 'context_surface|ContextSurface|RuntimeLlmContext\\b|model_visible_surface' src/crxzipple tests/unit frontend/src -g '*.{py,ts,tsx,vue,md}'`
  - no output

## 第七十轮施工记录：Provider Input Preview 命名收敛

目标：

- 清理 `context_surface` 迁移后残留的运行时代码口径。
- 避免 LLM routing、provider preview helper 和 Workbench timeline 继续暗示旧 prompt/surface assembly。
- 不保留旧 debug 字段过滤兼容。

落地：

- Orchestration events：
  - `orchestration.llm_resolved` topic/definition 描述从 `Prompt assembly LLM routing` 改为 `Runtime request LLM routing`。
- Workbench read model：
  - timeline debug payload 过滤列表删除旧 `rendered_context`。
  - 去掉重复的 `context_snapshot` key。
- LLM adapter / owner preview：
  - `surface_preview_from_request_metadata(...)` / `_surface_preview_from_request_metadata(...)` 改为 `provider_input_preview_from_request_metadata(...)` / `_provider_input_preview_from_request_metadata(...)`。
  - 协议字段保持 `context_snapshot_*` 与 `tool_surface_*`，不新增兼容别名。
- Dashboard：
  - 当前总览中的 `prompt input`、`context_render_snapshot_id`、`context surface` 口径改为 runtime request / context snapshot。

验证：

- `python -m compileall -q src/crxzipple/modules/orchestration/application/event_contracts.py src/crxzipple/modules/orchestration/application/read_models/workbench.py src/crxzipple/modules/llm/application/services.py src/crxzipple/modules/llm/infrastructure/adapters/common.py`
  - passed
- `PYTHONPATH=src pytest -q tests/unit/test_runtime_llm_request.py tests/unit/test_llm.py tests/unit/test_turns_http.py tests/unit/test_operations_llm_read_model.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_orchestration_context_workspace_snapshot.py`
  - 81 passed
- `PYTHONPATH=src pytest -q tests/unit/test_workbench_read_model.py tests/unit/test_llm_adapters.py tests/unit/test_anthropic_renderer.py tests/unit/test_openai_codex_renderer.py tests/unit/test_provider_renderer_canonical_request_integration.py`
  - 90 passed
- `cd frontend && npm run typecheck`
  - passed
- `rg -n 'Prompt assembly|prompt assembly|PromptInput|Prompt input|prompt input|PromptTranscript|prompt transcript|ContextSurface|context_surface|model_visible_surface|surface_preview_from_request_metadata|rendered_context|context_render_snapshot|ContextRenderSnapshot|render snapshot|render_snapshot|prompt-preview|promptPreview' src/crxzipple frontend/src tools -g '*.{py,ts,tsx,vue,md}'`
  - no output

## Open Decisions

1. `RuntimeToolSurface` 是否需要进一步拆成 `RuntimeToolSurface` 与 `RuntimeToolSurfaceRefSet`？
   - 推荐：暂不拆；当前 `RuntimeToolSurface.functions: RuntimeToolSurfaceRef[]` 已能表达 runtime request 工具面和 refs。

2. `ProviderWireRequest` 是否持久化完整 payload？
   - 推荐：只存脱敏 preview + fingerprints；raw payload 仅在显式 debug 开关下短期保存。

3. Renderer 是否属于 adapter 文件还是独立目录？
   - 推荐：`modules/llm/infrastructure/adapters/<provider>_renderer.py` 或 `protocols/` 子包，adapter 组合 renderer/parser/client。

4. Workflow evaluator 何时引入？
   - 推荐：不在本轮默认 agent loop 做；等 provider boundary 收敛后单独设计。

## 风险

- 如果过早删除 Context Render prompt body，某些旧测试会失败；本轮不做兼容，直接改测试到新边界。
- Chat-compatible provider 会有结构损失，必须通过 loss report 显示，而不是假装无损。
- Operations/Workbench 需要同时展示 runtime request 和 provider wire preview，否则调试会倒退。
- 如果 renderer 仍散落在 Orchestration，重构会失败；必须用 import/test 防止反向依赖。

## 完成定义

本重构完成时，应满足：

1. Runtime 维护 Context Tree，但不把 Tree 等同于 Prompt。
2. LLM adapter request rendering 与 response parsing 对称。
3. provider/transport/model 差异集中在 renderer/parser/adapter。
4. Orchestration 只协调 run 和 response item 生命周期。
5. Context Workspace 只提供 canonical context snapshot/projection/tree tools。
6. Evidence/browser route hints 不再作为通用 agent loop 默认输入。
7. Operations 能清楚说明模型实际看见了什么、provider 实际收到了什么、渲染损失是什么。
8. 不存在旧 request assembly 与新 renderer 双轨并行。
9. Codex renderer 的 wire payload 与已抓包 Codex trace 对齐，并有测试防回归。
10. 通用 runtime kernel 不包含任何面向单一测试任务、单一网站或单一业务域的特化判断。
