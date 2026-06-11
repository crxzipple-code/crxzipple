# Orchestration Execution Chain / Dispatch Convergence Plan

日期：2026-06-01

## 背景

当前运行时已经形成了正确的大方向：

- owner module 持有业务事实。
- `dispatch` 提供 durable queue、claim、lease、recover。
- `events` 提供跨进程事件流、唤醒、cursor 和 replay。
- `operations` 侧向观察事件并物化运维 read model。

但 orchestration/tool 的异步执行链还没有完全结构化。LLM 阶段、tool
阶段、approval replay、background tool resume 依赖多处松散字段归并：

- `OrchestrationRun.current_step`
- `OrchestrationRun.pending_tool_run_ids`
- `run.metadata["llm_invocation_id"]`
- `run.metadata["inline_tool_run_ids"]`
- `run.metadata["pending_background_tools"]`
- `tool_call_id`
- `tool_run_id`

这些字段可以支撑当前运行，但在异步场景下会出现归属不清：

- 慢返回的 background tool 已经晚于当前 LLM 轮次。
- approval replay 重新生成 tool run，但原始 tool call 和新的 tool run 关系靠 metadata 拼接。
- 同一个 turn 内多轮 LLM/tool 混杂，Workbench/Operations 只能临时拼 step。
- tool terminal event 被 replay 时，orchestration 要靠 run metadata 判断是否还应该 resume。
- session prompt 需要继续当前 provider protocol 时，边界只能间接依赖 session message window。

本计划的目标是把这些归并语义提升为一等模型，而不是继续塞入
`metadata`。

## 目标

1. 建立明确的 `Turn -> ExecutionChain -> ExecutionStep -> StepItem`
   层次。
2. 让 LLM invocation、tool run、approval request、session message 都有稳定的
   execution step 归属。
3. 让 `dispatch_tasks` 成为唯一 durable work queue。
4. 让 `events` 只承担事实流、唤醒和 replay，不承担 durable task truth。
5. 让 `metadata` 回到辅助信息、trace hint、展示 hint 的位置，不承载归并真相。
6. 让 Workbench、Operations、Trace 使用同一套执行链 read model。
7. 不保留长期兼容双轨；迁移完成后删除旧 ingress/signal/metadata 归并路径。

## 非目标

- 不把 `events` 改成业务状态数据库。
- 不用 Redis queue 替换 Postgres durable dispatch。
- 不让 `dispatch` 理解 orchestration/tool/llm 业务语义。
- 不让 tool 或 llm 模块持有 orchestration 领域概念。
- 不把 memory 纳入当前 session/turn 调度清理。Memory 仍只处理跨 session
  durable knowledge。

## 当前问题清单

### P1. Execution chain 没有真实模型

当前 `OrchestrationRun.current_step` 只能表示粗略 LLM 轮次。实际执行链由
LLM invocation、tool run、session message、run metadata 拼出来。

问题：

- 一轮 LLM 产生多个 tool call 时，没有正式 tool batch step。
- inline tool 和 background tool 的结果归并规则不同，但结构上没有区分。
- Workbench step 是 read model 临时生成，不是领域事实。

### P2. 异步结果归并依赖 metadata

`pending_background_tools` 保存 `{tool_run_id, tool_call_id, tool_name}`。
这本质是执行链归属信息，不应该放在 `metadata`。

问题：

- replay/retry 后 metadata 容易和真实 tool run 状态分叉。
- terminal event 重放时没有一等 idempotency target。
- late result 无法自然标注为 late/orphan/ignored。

### P3. Durable queue 语义没有统一

升级前同时存在：

- `dispatch_tasks`
- `orchestration_ingress_requests`（已退为请求事实，不再负责 claim）
- `orchestration_scheduler_signals`（已退场）

其中后两者承担了类似 queue/signal queue 的职责。

目标是：

- 待 worker claim、lease、retry、recover 的工作统一进入 `dispatch_tasks`。
- orchestration 自己的表只描述 turn/chain/step 业务事实。

### P4. Event reaction 边界不清

有些 event 是事实，有些 event 是 wakeup，有些 event 会触发新的业务推进。

目标是：

```text
event reaction = fact -> enqueue durable work
worker execution = claim durable work -> mutate owner facts
```

不要让 event reaction 直接完成复杂执行链归并。

### P5. UoW commit 后 publish 存在可靠性缝

当前 UoW 先 commit DB，再 publish Redis events。若进程在 commit 后、
publish 前崩溃，事件会丢。

目标是引入 transactional outbox：

```text
owner state + outbox event 同事务落库
outbox publisher 发布到 Redis Streams
发布成功后标记 delivered
```

## 目标概念

### Session

稳定会话容器，由 `session` module 持有。详见
`docs/session-semantics-design.md`。

### SessionSegment

会话内可写消息区间。当前代码里的 `SessionInstance` 应理解为
`SessionSegment`。

### Turn

一次 inbound request。Turn 绑定：

- `session_key`
- `active_session_id`
- `agent_id`
- reply/delivery target
- lane
- priority

当前 `OrchestrationRun` 承担了 Turn 的大部分职责。目标状态应引入明确
`Turn` 聚合，或完成 `OrchestrationRun -> Turn` 的语义重命名。本文以后以
`Turn` 称呼该概念。

### ExecutionChain

Turn 内的 LLM/tool/approval/final loop。

一个 Turn 通常有一个 active chain。特殊情况下可以存在 recovery chain 或
follow-up chain，但必须显式建模，不能藏在 metadata。

### ExecutionStep

ExecutionChain 内的一个可观察阶段。

建议 step kind：

- `intake`
- `prompt_render`
- `llm`
- `tool_batch`
- `approval`
- `tool_resume`
- `final_response`
- `error`
- `maintenance`

### ExecutionStepItem

Step 内的细粒度归并项。

示例：

- `llm_invocation`
- `tool_call`
- `tool_run`
- `tool_result`
- `approval_request`
- `session_message`
- `context_snapshot`

`ExecutionStepItem` 是异步归并的关键。它负责回答：

```text
这个 tool_run 属于哪一个 turn / chain / step / tool_call？
这个 llm_invocation 的结果应该推动哪一个 chain？
这个 session message 是哪个 step 产生的？
这个 approval replay 是恢复哪个 blocked step？
```

## 目标数据模型

字段名称可在落地时微调，但语义不可漂移。

### `orchestration_turns`

Turn 事实表。

建议字段：

- `id`
- `session_key`
- `active_session_id`
- `agent_id`
- `status`
- `stage`
- `lane_key`
- `lane_lock_key`
- `queue_policy`
- `priority`
- `reply_target_payload`
- `inbound_payload`
- `result_payload`
- `error_payload`
- `created_at`
- `accepted_at`
- `started_at`
- `completed_at`
- `updated_at`

迁移策略：

- 当前 `orchestration_runs` 可整体迁移/重命名为 `orchestration_turns`。
- 若保留表名，代码和 read model 必须把它解释为 Turn，不再泛称 low-level run。

### `orchestration_execution_chains`

建议字段：

- `id`
- `turn_id`
- `status`
- `active_step_id`
- `step_count`
- `created_at`
- `started_at`
- `completed_at`
- `updated_at`
- `error_payload`

状态：

```text
created -> running -> waiting -> completed | failed | cancelled
```

### `orchestration_execution_steps`

建议字段：

- `id`
- `chain_id`
- `turn_id`
- `step_index`
- `kind`
- `status`
- `dispatch_task_id`
- `owner_kind`
- `owner_id`
- `correlation_key`
- `started_at`
- `completed_at`
- `updated_at`
- `error_payload`

说明：

- `owner_kind/owner_id` 指向该 step 的主 owner fact，例如：
  - `llm_invocation / invocation_id`
  - `tool_batch / step_id`
  - `approval_request / request_id`
- `dispatch_task_id` 指向推进该 step 的 durable work。
- `correlation_key` 用于幂等归并，例如 `turn_id:chain_id:step_index:kind`。

### `orchestration_execution_step_items`

建议字段：

- `id`
- `step_id`
- `chain_id`
- `turn_id`
- `item_index`
- `kind`
- `status`
- `owner_kind`
- `owner_id`
- `correlation_key`
- `source_event_id`
- `created_at`
- `completed_at`
- `updated_at`
- `payload_ref`
- `summary_payload`
- `error_payload`

说明：

- `owner_kind/owner_id` 是跨模块 owner fact 的引用，不要求被引用模块反向依赖
  orchestration。
- 不把大段正文塞进 `summary_payload`。正文应由 owner module 或 session message
  持有。
- `payload_ref` 可以指向 session message、artifact、context snapshot 等 owner
  资源。

典型 item：

```text
kind=llm_invocation
owner_kind=llm_invocation
owner_id=<llm_invocation_id>

kind=tool_call
owner_kind=provider_tool_call
owner_id=<tool_call_id>

kind=tool_run
owner_kind=tool_run
owner_id=<tool_run_id>

kind=session_message
owner_kind=session_message
owner_id=<message_id>
```

### `dispatch_tasks`

`dispatch` 继续保持业务无关。

目标规则：

- orchestration 要推进某个 turn/step 时：

```text
owner_kind = orchestration_step
owner_id   = execution_step_id
```

- tool 要执行某个 tool run 时：

```text
owner_kind = tool_run
owner_id   = tool_run_id
```

- 不要求 dispatch 知道 `turn_id`、`chain_id`、`tool_id`。需要观察时通过 owner
  query service 或 orchestration relation table 查询。

当前落地：

- worker lease recovery 不再 fail run，而是保留 active execution step 并重新排队同一
  execution step dispatch task。
- 主执行 dispatch task 已迁移为
  `owner_kind=orchestration_step / task_id=execution_step_id`。
- `OrchestrationDispatchPort` 的 enqueue、claim、heartbeat、wait、complete、fail、cancel、
  recovery 均显式传递或解析 `dispatch_task_id`，不再假设
  `dispatch_task_id == run.id`。
- `orchestration_run` owner 只保留 intake/source 语义，不再作为主执行 dispatch
  owner。

建议增强：

- `idempotency_key`
- `correlation_key`
- `heartbeat_at`
- `lease_expires_at`
- `completed_at`

如果这些已经存在或有等价字段，则只统一命名和 read model 解释。

### Transactional Outbox

新增通用 outbox 表，位于 `events` infrastructure，而不是业务 module。

当前落地：

- Alembic `0067_event_outbox` 创建 `event_outbox_records`。
- `SqlAlchemyUnitOfWork` 在同一事务内写 owner state 与 outbox record。
- `worker:event-outbox` 由 daemon eager 管理，运行
  `event-outbox run`。
- publisher 发布成功后标记 `delivered`，失败后标记 `failed` 并按退避时间重试。
- subscription cursor/replay 继续由 events backend 负责，Operations 不读取 outbox 表。

建议字段：

- `id`
- `topic`
- `event_name`
- `event_payload`
- `status`
- `attempts`
- `available_at`
- `created_at`
- `updated_at`
- `delivered_at`
- `error_message`

状态：

```text
pending -> delivered | failed
```

要求：

- owner module UoW commit 时，同事务写 owner state 和 outbox records。
- outbox publisher 是 daemon 托管进程。
- Redis Streams 仍是 runtime event backend。
- `events` module 仍不拥有 owner business tables。

## 目标运行流

### 新 inbound turn

```text
channel/web/cli input
  -> resolve session_key
  -> resolve active SessionSegment
  -> create Turn
  -> create ExecutionChain
  -> create intake/prompt or first llm ExecutionStep
  -> enqueue dispatch_tasks(owner_kind=orchestration_step, owner_id=step_id)
  -> publish turn accepted / dispatch queued events through outbox
```

### Orchestration worker claim

```text
orchestration worker
  -> claim dispatch task(owner_kind=orchestration_step)
  -> load step
  -> load chain / turn
  -> execute step
  -> create child step/items as needed
  -> complete/requeue/wait/fail dispatch task
```

### LLM step

```text
execute llm step
  -> create step_item(kind=llm_invocation, status=starting)
  -> call llm module
  -> llm_invocation_id returned
  -> update step_item owner_id=llm_invocation_id
  -> stream delta through events payload
  -> final invocation result owned by llm module
  -> parse tool calls/final response
```

LLM stream delta rule：

- live delta 继续走 event payload。
- 不新增逐 token 业务表。
- operations 只记录统计/摘要，不保存大段 streaming 正文。
- final result 由 `llm_invocations` 和 session message 持有。

### Tool batch step

```text
llm result has tool calls
  -> create tool_batch step
  -> for each tool call:
       create item(kind=tool_call, owner_id=tool_call_id)
       create/submit tool_run through tool module
       create item(kind=tool_run, owner_id=tool_run_id, correlation_key=tool_call_id)
       enqueue dispatch task(owner_kind=tool_run, owner_id=tool_run_id)
  -> if all inline completed:
       append tool result messages
       create next llm step
  -> if any background:
       mark tool_batch step waiting
       mark chain waiting
```

### Background tool terminal event

```text
tool worker completes tool_run
  -> tool module writes tool_run terminal fact
  -> event published
  -> orchestration event reaction consumes fact
  -> lookup execution_step_items(owner_kind=tool_run, owner_id=tool_run_id)
  -> mark item terminal idempotently
  -> if step all terminal:
       enqueue dispatch task(owner_kind=orchestration_step, owner_id=resume_step_id)
```

关键点：

- 不读 `run.metadata.pending_background_tools`。
- 不猜测当前 run stage。
- late/orphan result 有明确处理分支。

Late result 处理：

```text
if step.status in completed/failed/cancelled:
  mark item late_ignored or late_observed
  publish orchestration.step.item.late
  do not mutate completed chain unless recovery policy explicitly allows
```

### Approval replay

```text
tool call needs approval
  -> create approval step
  -> create item(kind=approval_request, owner_id=request_id)
  -> chain waiting

approval granted
  -> enqueue dispatch task(owner_kind=orchestration_step, owner_id=approval_step_id)
  -> worker claims and replays the approved tool call
  -> produced tool_run is linked to the original approval/tool_call item
```

Approval replay must not depend on run metadata. The approval request stores or
references:

- original step id
- tool_call_id
- tool name
- arguments
- execution target
- authorization/access effect ids

### Final response

```text
llm result has final text
  -> create final_response step
  -> append assistant session message
  -> create item(kind=session_message, owner_id=message_id)
  -> complete chain
  -> complete turn
  -> publish terminal events
```

## Events 边界

`events` 是业务无关的跨进程通讯方案。

它负责：

- publish
- read topic
- wait topic
- subscription cursor
- replay from cursor
- dedupe
- contract/definition registry

它不负责：

- 存储 execution chain truth
- 决定 tool result 应该归到哪一步
- 维护 durable queue
- 读取 owner module 数据库

事件 payload 可以带业务字段，但只是定位线索、事实摘要或 live delta。需要完整状态时，
consumer 必须回 owner module query service 或 orchestration relation table 查询。

## Metadata 使用规则

### 允许放入 metadata

- trace id / correlation id
- UI 展示 hint
- runtime diagnostic
- source label
- 非关键统计快照
- 可丢弃的 prompt/render report summary

### 禁止放入 metadata

- execution step 归属
- background tool pending truth
- LLM invocation 与 step 的唯一关系
- approval replay 的唯一恢复关系
- pending approval request / last approval resolution / recovery contract
- dispatch task truth
- session message 与 execution step 的唯一关系

旧字段退场：

- `run.metadata["pending_background_tools"]`
- `run.metadata["inline_tool_run_ids"]`
- `run.metadata["llm_invocation_id"]` 作为唯一真相
- `run.metadata["tool_call_names"]` 作为唯一真相
- `run.metadata["pending_approval_request"]`
- `run.metadata["last_approval_resolution"]`
- `run.metadata["recovery_contract"]`

这些信息应迁移到 `orchestration_execution_steps` /
`orchestration_execution_step_items`。

## API / Application Surface

### Orchestration application

新增或收口以下 surface：

- `TurnCommandService`
  - submit inbound turn
  - cancel turn
  - retry turn
- `ExecutionChainService`
  - create chain
  - create step
  - complete step
  - wait step
  - fail step
  - link owner item
  - resolve item by owner reference
- `ExecutionStepQueryService`
  - list chain steps
  - get step detail
  - find step item by owner reference
  - provider protocol continuation view
- `OrchestrationWorkerService`
  - claim dispatch task
  - execute orchestration step
  - heartbeat/recover via dispatch

### Dispatch application

Keep generic:

- create/enqueue
- claim next
- heartbeat
- wait
- complete/fail/cancel
- recover abandoned

Dispatch must not import orchestration/tool/llm domain classes.

### Tool application

Tool keeps owning:

- tool function catalog
- tool run
- tool worker
- tool assignment
- tool result/error

Tool does not need to know execution step. Orchestration links tool runs through
`orchestration_execution_step_items`.

### LLM application

LLM keeps owning:

- LLM profile
- invocation
- final result/error
- streaming adapter events

LLM does not need to know execution step. Orchestration links invocations through
`orchestration_execution_step_items`.

## Operations / Workbench / Trace

### Workbench

Workbench should read a real execution chain read model:

```text
Turn
  Chain
    Step 1: LLM invocation
    Step 2: Tool batch
      tool_call -> tool_run -> tool_result
    Step 3: LLM invocation
    Step 4: Final response
```

No more synthetic-only ids such as:

- `llm_{current_step}`
- `tool_wait`

They may remain display labels, but not as backend truth.

### Operations

Operations orchestration page should show:

- active turns
- active execution chains
- waiting steps
- late/orphan tool results
- dispatch lag by owner_kind
- lease/recover facts
- event reaction backlog

Tool page should continue showing tool run truth, but cross-link to execution
step when source is orchestration.

LLM page should continue showing LLM invocation truth, but cross-link to execution
step when source is orchestration.

### Trace

Trace should pivot on:

- turn id
- chain id
- step id
- owner references

instead of trying to infer a trace from event payload only.

## Migration Strategy

不接受长期双轨。允许短暂迁移窗口，但 runtime 主路径必须一次性切到新模型。

### M0. Terminology freeze

- `SessionInstance` 文档术语统一为 `SessionSegment`。
- `OrchestrationRun` 在迁移前解释为 current Turn record。
- `run` 这个词仅作为历史代码名或 UI 泛称，不再作为新架构概念。

### M1. Persistence migration

新增：

- `orchestration_execution_chains`
- `orchestration_execution_steps`
- `orchestration_execution_step_items`
- transactional outbox 表

迁移现有数据：

- 每个 non-terminal/current `orchestration_run` 创建一个 chain。
- 根据 `current_step`、`stage`、`pending_tool_run_ids` 创建 best-effort step。
- 根据 `llm_invocation_id`、`pending_tool_run_ids`、`inline_tool_run_ids`
  创建 step item。

迁移只用于历史可读；新 runtime 不再写旧 metadata 归并字段。

### M2. Orchestration write path cutover

- submit turn 时创建 Turn/Chain/first Step。
- 只 enqueue `dispatch_tasks(owner_kind=orchestration_step)`。
- 停止把新 inbound work 写成可 claim 的 `orchestration_ingress_requests`。
- 停止把 scheduler continuation 写入 `orchestration_scheduler_signals`。
  当前已改为 `dispatch_tasks(owner_kind=orchestration_continuation)`。

### M3. Executor cutover

- orchestration worker claim dispatch task。
- worker 按 step kind 调用执行器。
- LLM/tool/approval/final 都通过 step service 记录。
- `RunExecutionService` 中直接写 metadata 的地方改为 step/item 写入。

### M4. Tool terminal reaction cutover

- tool terminal event reaction 只做：

```text
tool_run_id -> execution_step_item -> update item -> enqueue resume step
```

- 删除基于 `run.pending_tool_run_ids` / `pending_background_tools` 的归并主路径。

### M5. Prompt continuation cutover

- Provider-native continuation messages 从 execution chain query 生成。
- 不再以 session message sequence window 作为主要边界。
- Context Workspace 继续负责历史 tree delivery。

### M6. Outbox cutover

- UoW commit 不再直接 publish Redis events。
- UoW 同事务写 outbox。
- 新增 daemon service `worker:event-outbox`，职责独立于 event relay。
- Operations 观察 Redis events，不观察 outbox 表。

### M7. Read model / UI cutover

- Workbench steps 改读 execution chain read model。
- Operations orchestration 页使用 turn/chain/step/dispatch 聚合。
- Trace 支持 step pivot。
- Tool/LLM 页面增加 execution step cross-link。

### M8. Delete retired paths

删除或退役：

- `orchestration_ingress_requests` runtime claim path
- `orchestration_scheduler_signals` runtime queue path（已删除）
- `RunSchedulerSignalCoordinator` 主路径（已改为 `RunContinuationCoordinator`）
- `RunIngressCoordinator.claim_next_request` 旧命名入口
- run metadata background tool relation 主路径
- Workbench synthetic-only step truth

旧表可通过 alembic 后续 migration drop，或先只读保留一个版本窗口；代码不得继续双写双读。

## Implementation Checklist

### Progress Update 2026-06-01

本轮已把 LLM/tool 执行归属从仅靠 run metadata 向 execution chain
正式写入推进一层：

- `EngineAdvanceOutcome` 现在携带结构化 `tool_run_links`，记录
  `tool_call_id -> tool_run_id -> result_message_id` 关系。
- `RunProgressCoordinator` 在 LLM 结束后写入 `llm_invocation` item，并在
  TOOL 阶段物化 `tool_batch` step。
- 每个 tool call/tool run 分别落成 `ExecutionStepItem`，background tool
  run 进入 `WAITING`，inline tool run 进入 `COMPLETED`。
- background tool terminal 被观察到后，会通过
  `owner_kind=tool_run / owner_id=<tool_run_id>` 找回 step item 并更新终态；
  当 tool batch 全部 item 终态后闭合该 step。正常 terminal signal 和
  recovery contract 续跑都会执行这条 item terminal 更新。
- pending approval 现在会物化 `approval` step 和 `approval_request` item；
  approval resolution 会关闭该 item/step。
- approval replay 产出的 tool run 会重新通过 `tool_run_links` 物化到
  execution chain，并用原始 `request_id/tool_call_id` 建立归属。
- background tool terminal 或 approval resolution 触发 run resume 时，会写入
  `tool_resume` step，给后续 LLM 继续执行留下正式边界。
- late background tool result 会标记原 item 为 `late_observed`，不再反向推进
  已经闭合的 step/chain。
- session tool result message 回写不再读取
  `run.metadata.pending_background_tools`；它通过
  `owner_kind=tool_run / owner_id=<tool_run_id>` 找回 execution step item 中的
  `tool_call_id/tool_name`。
- inline 和 background tool result message 现在都会落成
  `ExecutionStepItem(kind=tool_result, owner_kind=session_message)`，链上可以直接
  看到 tool result 写入 session 的事实。
- run complete 时会创建 `final_response` step，并把 assistant message 落成
  `ExecutionStepItem(kind=session_message, owner_kind=session_message)`。
- execution chain/step/item repositories 在同一个 UoW 内复用 pending ORM model；
  maintenance run 这类首次执行时才 bootstrap chain 的路径，不会因为同事务内多次
  `add` 同一 aggregate 造成重复 insert。
- approval/recovery 运行状态不再藏在 `run.metadata`；
  `pending_approval_request`、`last_approval_resolution`、`recovery_contract`
  已落为 `orchestration_runs` 显式字段。approval resolution 从 recovery contract
  字段读取对应 invocation，并继续物化 replay tool batch。
- `pending_background_tools` 已停止写入；当前仍保留的 `pending_tool_run_ids`
  只表达 run 处于等待哪些 tool run 的运行状态，不再承担
  `tool_call_id -> tool_run_id` 关系真相。
- execution write path 不再把 `llm_invocation_id/tool_call_names/tool_run_links`
  写入 `run.metadata`；这些字段只通过 `execution_payload` 进入 execution chain
  materializer。`run.result_payload` 仍可保留最终输出展示字段，但 Workbench
  不再把它当作 step 归并真相。
- `CompleteAssignmentInput` / HTTP complete API 已把 `execution_payload` 和
  `result_payload` 分离：`llm_invocation_id/tool_run_links/tool_call_names` 只走
  execution payload，`run.result_payload` 不再写入
  `inline_tool_run_ids/tool_run_links/llm_invocation_id` 这类归并字段。
- Workbench steps 已切为 execution chain 优先：LLM invocation、tool run、
  tool result、final response 都从 `ExecutionStep/ExecutionStepItem` 读取；
  只有旧数据没有 chain 时才回退到 run metadata 推断。
- orchestration-owned background tool run 进入 terminal 后，如果找不到
  `owner_kind=tool_run` 的 execution step item，会发布
  `orchestration.execution.orphan_tool_result_observed` operational event；
  Operations observer 会订阅该风险事实，但不会推进 chain 或恢复 run。
- terminal tool event replay 已覆盖：第一次 terminal event 会恢复 waiting run；
  `orchestration_waits` 被清除后，同一 tool terminal 重放只做 item 幂等更新，
  不会再次 append tool result 或重复 resume。
- provider transcript 现在可接收 execution chain 产出的 completed tool-call id
  作为 continuation truth：当当前 turn 的 execution chain 已经出现
  `tool_call/tool_run/tool_result` 协议 item 时，function_call/tool result 成对过滤
  不再只依赖 session message metadata；没有 tool 协议 item 的旧/测试数据仍回退
  到 session pair 逻辑。
- scheduler continuation queue 已从 `orchestration_scheduler_signals` 表切到
  `dispatch_tasks(owner_kind=orchestration_continuation)`：
  tool terminal 和 session spawn follow-up 都写入 dispatch task，scheduler worker
  从 dispatch claim/recover/complete/fail，不再从旧 signal 表领取工作。
- inbound ingress request queue 已从 `orchestration_ingress_requests.claim_*`
  切到 `dispatch_tasks(owner_kind=orchestration_ingress)`：
  `orchestration_ingress_requests` 继续保存请求 payload、状态和审计事实，
  但 scheduler 的 claim/lease/recover/complete/fail 由 dispatch task 承担。
- `OrchestrationIngressRequestRepository` 的 `claim_next/claim_for_run` API 和
  SQL 实现已删除，避免后续代码重新把 ingress 表当队列使用。
- `RunIngressCoordinator.submit_*` 不再接受 submit-time claimed worker；inline
  处理也必须先通过 dispatch-backed claim，再执行 ingress prepare/enqueue。
- `RunIngressCoordinator.claim_next_request` 旧命名入口已改为
  `claim_next_dispatch_request`；指定 run 的 inline claim 入口已改为
  `claim_dispatch_request_for_run`，避免旧命名掩盖 dispatch task 语义。
- 单元测试里如果要让 scheduler 观察 tool terminal/runtime event，必须先调用
  `publish_outbox_events(container)` 模拟 `worker:event-outbox` daemon 发布事件；
  scheduler 只消费 events backend，不直接读取 outbox 表。
- Operations orchestration read model 已接入 dispatch task query surface；run
  queue / ingress queue 会显示 dispatch status、owner kind、worker 与 lease，
  不再只从 run/request 业务状态推断队列真相。
- Operations orchestration page/read model 已增加 `execution_chains` 表区，按最近
  active/recent run 展示 `chain_id/status/active_step/last_step/item_count`，
  与 dispatch 状态、Workbench route、Trace route 形成同页串联。
- Operations LLM/Tool detail 已改为从 execution step item owner 查找执行归属：
  `owner_kind=llm_invocation/tool_run` 会反链到 turn/chain/step，LLM/Tool 主表和
  详情摘要都显示 turn、chain、step，不再从 LLM `result_payload` 或 tool run
  metadata 猜测执行关系。
- Trace UI/read model 支持 `step_id` pivot：`/ui/trace/{trace_id}` 与
  `/ui/trace/{trace_id}/events` 可按 execution step 过滤；Operations 中从
  execution item 反链出来的 trace route 会携带 `?step_id=...`。
- Workbench step view 保留前端选中用的稳定 view step id，同时
  `trace.step_id` 改为 execution step 原始 id；Workbench 中所有 View Trace
  入口都会携带 `?step_id=...`，和 Operations/Trace 的 step pivot 对齐。
- 前端 DataTable/i18n 已补齐 execution step/item、dispatch owner 和 late tool
  result 新状态，Operations 表格默认继续 humanize event/topic/metric raw key。
- Trace 页面事件名展示收口为“已知事件 i18n、未知 raw key humanize”，详情面板不再把
  display label 反向转成 dotted raw key。
- 旧 `RunSchedulerSignalCoordinator` 命名壳已退场，当前主路径是
  `RunContinuationCoordinator` / `OrchestrationContinuationTask`。
- worker CLI 已从 `process-next-signal` 改为
  `process-next-continuation`，避免把 continuation task 继续伪装成
  scheduler signal。
- scheduler wait watches 不再订阅
  `orchestration.scheduler.signal.requested`，而是等待
  `dispatch.wakeup.orchestration_ingress`、
  `dispatch.wakeup.orchestration_step` 和
  `dispatch.wakeup.orchestration_continuation`。
- `orchestration.scheduler.signal.*` operational event family 已从当前事件契约和
  Operations observer 订阅中移除；Operations 的 continuation 统计现在从
  dispatch-backed query view 读取，事件观察由 `dispatch.task.*` 表达唤醒事实。
- 旧 scheduler signal repository 不再从 domain/persistence/UoW 导出，运行时
  container 已不再暴露 `orchestration_scheduler_signals` queue repository；旧
  domain entity/enums、SQLAlchemy model 已删除，并新增
  `0066_drop_orchestration_scheduler_signals` schema drop migration。
- Operations orchestration read model 在计算最近更新时间时统一 UTC datetime，
  避免 dispatch task 与 observed event 混合时出现 aware/naive 比较错误。
- dispatch worker lease 过期后不再把 RUNNING run 直接 fail 掉；
  `dispatch.task.recovered` 会把同一个 run 重新排队、释放旧 executor 容量，
  并保留原 execution chain active step，下一次 worker claim 会继续同一执行步。
- 新增 `orchestration.run.worker_lease_recovered` 观察事件，Operations observer
  可侧向看到 lease recovery，而不是只看到一次失败。
- Operations observer 重启后会读取已持久化 subscription cursor，只 replay
  cursor 之后的新事件；已用单测覆盖，避免观察者重启造成重复投影。
- background tool terminal 结果经由 `OrchestrationToolResumeCoordinator` 进入时，
  如果目标 execution chain 已完成，会把原 tool_run item 标记为
  `late_observed`，不 append session message、不 resume run、不发布 orphan 风险。
- Prompt/Session 边界已用现有测试复核：session message 仍由 session module
  提供和保存；Context Workspace 历史 tree 只负责历史披露，不承担当前 provider
  protocol continuation 的 message 数组。
- Operations 布局 audit 新增 `--block-operations-api`，可阻断
  `/api/operations*` 来验证 loading/error/empty 状态下仍没有内部滚动、横向溢出
  或首屏外卡片。

已验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_orchestration_execution_chain.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_queue.py tests/unit/test_orchestration_tools.py tests/unit/test_orchestration_approval.py tests/unit/test_orchestration_execution_chain.py
ruff check src/crxzipple/modules/orchestration/application/execution_chain_lifecycle.py src/crxzipple/modules/orchestration/application/coordinators/progress.py src/crxzipple/modules/orchestration/application/coordinators/waiting.py src/crxzipple/modules/orchestration/application/execution.py src/crxzipple/modules/orchestration/application/engine_tool_executor.py src/crxzipple/modules/orchestration/application/engine.py src/crxzipple/modules/orchestration/application/tool_resume.py tests/unit/test_orchestration_execution_chain.py
PYTHONPATH=src pytest -q tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_workbench_reads_llm_trace_from_execution_chain_without_run_metadata tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_workbench_reads_tool_runs_from_execution_chain_without_run_metadata
PYTHONPATH=src pytest -q tests/unit/test_events.py::EventsModuleTestCase::test_event_definition_registry_describes_registered_events tests/unit/test_events.py::EventsModuleTestCase::test_event_definition_registry_covers_operations_observer_subscriptions tests/unit/test_events.py::EventsModuleTestCase::test_turn_event_subscriber_publishes_run_and_session_topics
ruff check src/crxzipple/modules/orchestration/application/tool_resume.py src/crxzipple/modules/orchestration/application/event_contracts.py src/crxzipple/modules/operations/application/orchestration_observation.py tests/unit/test_orchestration_execution_chain.py
PYTHONPATH=src pytest -q tests/unit/test_prompt_transcript.py tests/unit/test_orchestration_context.py::OrchestrationContextTestCase::test_normal_turn_delivers_history_through_context_tree_not_direct_transcript tests/unit/test_orchestration_context.py::OrchestrationContextTestCase::test_prompt_preview_filters_orphan_function_calls_from_transcript tests/unit/test_orchestration_tools.py::OrchestrationToolsTestCase::test_background_tool_completion_event_resumes_run_and_allows_next_turn
ruff check src/crxzipple/modules/orchestration/application/prompt_transcript.py src/crxzipple/modules/orchestration/application/prompt_surface.py src/crxzipple/app/assembly/orchestration.py tests/unit/test_prompt_transcript.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_queue.py tests/unit/test_orchestration_execution_chain.py tests/unit/test_prompt_transcript.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_tools.py::OrchestrationToolsTestCase::test_background_tool_completion_event_resumes_run_and_allows_next_turn tests/unit/test_orchestration_approval.py::OrchestrationApprovalTestCase::test_background_tool_call_can_wait_for_approval_then_transition_to_tool_wait tests/unit/test_sessions_tool_http.py::SessionsToolHttpTestCase::test_sessions_spawn_child_completion_enqueues_requester_followup tests/unit/test_ui_operations_orchestration_http.py tests/unit/test_operations_observation.py::OperationsObservationTestCase::test_file_backed_store_records_orchestration_module_observation tests/unit/test_operations_observation.py::OperationsObservationTestCase::test_operations_observer_subscribes_raw_orchestration_events tests/unit/test_events.py::EventsModuleTestCase::test_event_definition_registry_describes_registered_events tests/unit/test_events.py::EventsModuleTestCase::test_event_definition_registry_covers_operations_observer_subscriptions
ruff check src/crxzipple/modules/orchestration/application/coordinators/continuation_tasks.py src/crxzipple/modules/orchestration/application/scheduler_service.py src/crxzipple/modules/orchestration/application/query.py src/crxzipple/modules/orchestration/application/dispatch_owner_kinds.py src/crxzipple/modules/orchestration/application/event_contracts.py src/crxzipple/modules/operations/application/orchestration_observation.py src/crxzipple/modules/operations/application/read_models/orchestration.py tests/unit/test_operations_observation.py tests/unit/test_events.py tests/unit/test_ui_operations_orchestration_http.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_queue.py tests/unit/test_ui_operations_orchestration_http.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_tools.py::OrchestrationToolsTestCase::test_background_tool_completion_event_resumes_run_and_allows_next_turn tests/unit/test_orchestration_approval.py::OrchestrationApprovalTestCase::test_background_tool_call_can_wait_for_approval_then_transition_to_tool_wait tests/unit/test_sessions_tool_http.py::SessionsToolHttpTestCase::test_sessions_spawn_child_completion_enqueues_requester_followup tests/unit/test_events.py::EventsModuleTestCase::test_event_definition_registry_describes_registered_events tests/unit/test_events.py::EventsModuleTestCase::test_event_definition_registry_covers_operations_observer_subscriptions
ruff check src/crxzipple/modules/orchestration/application/unit_of_work.py src/crxzipple/shared/infrastructure/sqlalchemy_uow.py src/crxzipple/modules/orchestration/domain/repositories.py src/crxzipple/modules/orchestration/domain/__init__.py src/crxzipple/modules/orchestration/infrastructure/persistence/repositories.py src/crxzipple/modules/orchestration/infrastructure/persistence/__init__.py src/crxzipple/modules/orchestration/infrastructure/__init__.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_queue.py tests/unit/test_ui_operations_orchestration_http.py tests/unit/test_app_assembly_architecture.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_tools.py::OrchestrationToolsTestCase::test_background_tool_completion_event_resumes_run_and_allows_next_turn tests/unit/test_orchestration_approval.py::OrchestrationApprovalTestCase::test_background_tool_call_can_wait_for_approval_then_transition_to_tool_wait tests/unit/test_sessions_tool_http.py::SessionsToolHttpTestCase::test_sessions_spawn_child_completion_enqueues_requester_followup tests/unit/test_orchestration_execution_chain.py tests/unit/test_orchestration_cli.py::OrchestrationCliTestCase::test_orchestration_scheduler_help_only_exposes_scheduler_commands tests/unit/test_orchestration_cli.py::OrchestrationCliTestCase::test_orchestration_executor_help_only_exposes_executor_commands tests/unit/test_db_cli.py::DbCliTestCase::test_db_commands_apply_and_report_revisions tests/unit/test_events.py::EventsModuleTestCase::test_event_definition_registry_describes_registered_events tests/unit/test_events.py::EventsModuleTestCase::test_event_definition_registry_covers_operations_observer_subscriptions
ruff check src/crxzipple/modules/orchestration/application/coordinators/ingress.py src/crxzipple/modules/orchestration/application/scheduler_service.py src/crxzipple/modules/orchestration/application/ingress_runtime.py src/crxzipple/modules/orchestration/application/dispatch_owner_kinds.py src/crxzipple/modules/orchestration/application/__init__.py src/crxzipple/modules/orchestration/domain/repositories.py src/crxzipple/modules/orchestration/infrastructure/persistence/repositories.py
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_orchestration_http.py tests/unit/test_turns_http.py tests/unit/test_orchestration_http.py
ruff check src/crxzipple/modules/orchestration/application/query.py src/crxzipple/modules/operations/application/read_models/factory.py src/crxzipple/modules/operations/application/read_models/orchestration.py tests/unit/http_test_support.py tests/unit/test_ui_operations_orchestration_http.py
ruff check --ignore F403,F405 tests/unit/test_turns_http.py
cd frontend && npm run typecheck
PYTHONPATH=src pytest -q tests/unit/test_orchestration_memory.py tests/unit/test_orchestration_execution_chain.py
PYTHONPATH=src pytest -q tests/unit/test_turns_http.py tests/unit/test_orchestration_http.py tests/unit/test_ui_operations_orchestration_http.py
ruff check src/crxzipple/modules/orchestration/application/commands.py src/crxzipple/modules/orchestration/interfaces/http_models.py src/crxzipple/modules/orchestration/application/worker.py src/crxzipple/modules/orchestration/application/execution.py src/crxzipple/modules/orchestration/application/coordinators/progress.py src/crxzipple/modules/orchestration/application/coordinators/waiting.py src/crxzipple/modules/orchestration/application/read_models/workbench.py
ruff check --ignore F401,F403,F405,F841 tests/unit/orchestration_test_support.py tests/unit/http_test_support.py tests/unit/test_turns_http.py tests/unit/test_orchestration_memory.py tests/unit/test_orchestration_execution_chain.py
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_orchestration_http.py
ruff check src/crxzipple/modules/operations/application/read_models/orchestration.py src/crxzipple/modules/operations/interfaces/http_models.py tests/unit/test_ui_operations_orchestration_http.py
cd frontend && npm run typecheck
PYTHONPATH=src pytest -q tests/unit/test_ui_http.py -k "operations_tool_page or operations_llm_page"
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_read_model.py tests/unit/test_ui_operations_orchestration_http.py
ruff check src/crxzipple/modules/operations/application/read_models/tool.py src/crxzipple/modules/operations/application/read_models/llm.py src/crxzipple/modules/operations/application/read_models/factory.py tests/unit/test_ui_http.py
cd frontend && npm run typecheck
PYTHONPATH=src pytest -q tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_trace_summary_and_events_use_event_read_model tests/unit/test_operations_tool_read_model.py tests/unit/test_ui_operations_orchestration_http.py
PYTHONPATH=src pytest -q tests/unit/test_ui_http.py -k "operations_tool_page or operations_llm_page"
ruff check src/crxzipple/modules/events/application/read_models/trace.py src/crxzipple/interfaces/http/ui.py src/crxzipple/modules/operations/application/read_models/tool.py src/crxzipple/modules/operations/application/read_models/llm.py tests/unit/test_ui_http.py
cd frontend && npm run typecheck
```

### A. Domain / Persistence

- [x] 新增 ExecutionChain entity/value objects。
- [x] 新增 ExecutionStep entity/value objects。
- [x] 新增 ExecutionStepItem entity/value objects。
- [x] 新增 repositories 和 SQLAlchemy models。
- [x] 新增 Alembic migration。
- [x] 新增 execution chain application query surface。
- [x] 新增 owner reference lookup index：
  `(owner_kind, owner_id)` where owner id exists.
- [x] 新增 step order unique index：`(chain_id, step_index)`。
- [x] 新增 idempotency/correlation constraints。

### B. Dispatch convergence

- [x] 定义 orchestration dispatch owner kinds：
  - `orchestration_ingress`
  - `orchestration_continuation`
  - `orchestration_step`
  - optionally `orchestration_turn_maintenance`
- [x] submit/accept materialize active execution chain and intake step.
- [x] enqueue completes intake step and materializes dispatch-linked LLM step.
- [x] submit turn 写入 ingress request fact，并 enqueue
  `dispatch_tasks(owner_kind=orchestration_ingress)`。
- [x] orchestration scheduler 不再 claim ingress table。
- [x] orchestration scheduler 分配主执行工作时以
  `dispatch_tasks(owner_kind=orchestration_step, status=queued)` 为候选入口；
  run 表只用于 owner fact 校验和 lane guard。
- [x] scheduler continuation 主路径转为 dispatch-backed continuation task。
- [x] tool 继续使用 `owner_kind=tool_run`。
- [x] Operations dispatch read model 按 owner_kind 展示队列。

### C. Execution write path

- [x] LLM step 开始前创建并标记 execution step running。
- [x] LLM invocation id 返回后绑定 `llm_invocation` item。
- [x] tool call 解析后创建 tool batch step。
- [x] 每个 tool call 创建 tool_call item。
- [x] 每个 tool run 创建 tool_run item。
- [x] approval request 创建 approval step / approval_request item。
- [x] inline tool result 创建 tool_result/session_message item。
- [x] background tool step 进入 waiting。
- [x] resume 创建 tool_resume step。
- [x] final response 创建 final/session_message item。

### D. Async merge / resume

- [x] tool terminal reaction 使用 owner reference 查 step item。
- [x] step item terminal 更新必须幂等。
- [x] all-items-terminal 时闭合 waiting tool batch step。
- [x] all-items-terminal 时创建 resume step。
- [x] late result 进入 `late_observed` 或 `late_ignored`。
- [x] orphan result 进入 Operations risk/event，不推进 chain。
- [x] approval replay 绑定原始 step/item。

### E. Metadata cleanup

- [x] 停写 `pending_background_tools`。
- [x] 停写 `inline_tool_run_ids` 作为归并真相。
- [x] engine outcome 内部字段改为 `completed_inline_tool_run_ids`，
  只表达本轮执行结果，不再沿用旧 persisted-field 风格命名。
- [x] 停写 `llm_invocation_id` 作为当前 LLM step 真相。
- [x] 停写 `tool_call_names` 作为 tool batch 真相。
- [x] pending approval request / last approval resolution / recovery contract
  从 `run.metadata` 迁移到 `orchestration_runs` 显式字段，并由 migration 一次性搬迁
  旧 metadata。
- [x] 保留 trace/display metadata，但测试保证归并不依赖 metadata。

### F. Prompt / Session boundary

- [x] provider-native continuation view 从 execution chain query 构建。
- [x] session messages 继续由 session module 持有。
- [x] Context Workspace 历史 tree 不承担 current protocol continuation。
- [x] tool result message 与 execution step item 建立 owner reference。

### G. Events / Outbox

- [x] 新增 outbox model/repository。
- [x] UoW collect events 改为写 outbox。
- [x] outbox publisher daemon 发布 Redis events。
- [x] outbox publisher 发布前先 claim `event_outbox_records`，通过
  `publisher_id/claim_expires_at` 避免多 publisher 重复领取；claim 过期后可重试。
- [x] publish 成功后标记 delivered。
- [x] publisher 支持 retry/backoff。
- [x] 保持 subscription cursor/replay 仍在 events backend。
- [x] 测试契约明确：runtime event 处理前由 test helper drain outbox，生产职责由
  `worker:event-outbox` daemon 承担。

### H. Operations / UI / Trace

- [x] Workbench steps 改为真实 chain/step read model。
- [x] Operations orchestration 页面显示 turn/chain/step/dispatch。
- [x] Operations tool/llm detail 增加 execution step link。
- [x] Trace 支持 step pivot。
- [x] i18n 补齐新状态。
- [x] Skeleton 和 empty 状态保持布局稳定。

### I. Deletion

- [x] 删除 ingress claim 主路径。
- [x] 删除 `RunIngressCoordinator.claim_next_request` 旧命名入口，并把指定 run
  claim 改名为 `claim_dispatch_request_for_run`。
- [x] 删除旧 scheduler signal queue 主路径。
- [x] 删除旧 scheduler signal repository/UoW 属性。
- [x] 删除旧 scheduler signal 命名壳和旧表 migration。
- [x] 删除 runtime 对 old metadata relation 的依赖。
- [x] 删除旧 tests 中鼓励 metadata 归并的断言。
- [x] docs/archive 过时方案，不作为当前施工依据。

### J. Step-owner dispatch migration

- [x] 主执行 dispatch task 从 `orchestration_run` owner 迁移到
  `orchestration_step` owner。
- [x] OrchestrationDispatchPort 不再隐式假设 `dispatch_task_id == run.id`。
- [x] 删除 `RunDispatchPort` / `OrchestrationRunDispatchAdapter` 命名，
  统一改为 `OrchestrationDispatchPort` / `OrchestrationDispatchAdapter`。
- [x] claim/heartbeat/wait/complete/fail/recovery 均从 active execution step
  解析 dispatch task。
- [x] run 从 tool/approval wait resume 时会关闭上一段 WAITING dispatch task，再创建并
  enqueue 新的 execution step dispatch task，避免旧等待任务长期占用 lane。
- [x] scheduler wait watch 订阅 `dispatch.wakeup.orchestration_step`，并移除主执行
  对 `dispatch.wakeup.orchestration_run` 的依赖。
- [x] Operations dispatch/read model 可显示 `orchestration_step` owner，dispatch task
  通过 `payload_ref` 反链 turn，通过 `owner_id/dispatch_task_id` 反链 step。

说明：

- `orchestration_run` 只保留为 execution chain 的 intake/source owner string，
  不再导出为 dispatch owner kind，也不在 `ORCHESTRATION_DISPATCH_OWNER_KINDS`
  集合中。
- 主执行 dispatch task 的 `task_id == owner_id == execution_step.id`，`payload_ref`
  保存 run/turn id。

### K. Concurrent Runtime Hygiene

- [x] skill readiness snapshot upsert 支持并发 insert 竞态恢复，避免多个 executor
  同时构建 prompt/readiness 时因 `skill_readiness.skill_id` 唯一键冲突导致 run 失败。

## Test Plan

### Unit

- [x] ExecutionStep state transition。
- [x] StepItem owner reference 幂等绑定。
- [x] Tool terminal event 重放不重复 resume。
- [x] Late tool result 不推进 completed chain。
- [x] Approval replay 绑定原始 tool_call item。
- [x] Dispatch owner_kind selection。
- [x] Outbox write 同事务。

### Integration

- [x] normal LLM-only turn。
- [x] inline tool turn。
- [x] multiple inline tool calls。
- [x] background tool wait/resume。
- [x] background tool late result。
- [x] approval required -> approve -> replay -> resume。
- [x] worker lease expired -> recover same step。
- [x] outbox publisher crash/restart。
- [x] operations observer replay after cursor。

### UI / Read model

- [x] Workbench chain shows stable step ids。
- [x] Operations orchestration queue uses dispatch truth。
- [x] Tool detail links back to turn/chain/step。
- [x] LLM detail links back to turn/chain/step。
- [x] No user-visible raw event key leaks without i18n。

### Regression commands

按改动范围执行，至少覆盖：

```bash
PYTHONPATH=src pytest -q tests/unit/test_orchestration_queue.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_tools.py
PYTHONPATH=src pytest -q tests/unit/test_tool_background.py
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py
PYTHONPATH=src pytest -q tests/unit/test_events_http.py
cd frontend && npm run typecheck && npm run build
```

新增迁移后必须至少跑：

```bash
source scripts/dev/infra-env.sh
python -m crxzipple.main db upgrade head
```

## Acceptance Criteria

- 一个异步 tool result 可以通过 `tool_run_id` 精确找到所属
  turn/chain/step/item。
- 不需要读取 `run.metadata.pending_background_tools` 就能 resume background
  tool。
- 一次 LLM invocation 可以通过 `llm_invocation_id` 精确找到所属 step。
- approval replay 不依赖 metadata 恢复原始 tool call。
- Orchestration 待执行工作统一在 `dispatch_tasks` 中 claim。
- `orchestration_ingress_requests` 和 `orchestration_scheduler_signals` 不再作为
  runtime queue 主路径。
- Workbench/Operations/Trace 展示同一套 execution chain。
- Redis events 仍可 replay，但 replay 只驱动观察/反应，不作为业务真相。
- UoW commit 后事件不会因为进程崩溃永久丢失。
- 新代码没有长期兼容双轨或隐藏 shim。

## Decision Status

已定案并落地：

- Outbox 属于 `events` module 的 infrastructure。`SqlAlchemyUnitOfWork` 只作为通用
  UoW 在同一事务内写 `EventOutboxRecord`，publisher 由
  `worker:event-outbox` daemon service 承担。
- Outbox publisher 支持多实例安全领取：record 进入 `publishing` 状态并带
  `publisher_id/claim_expires_at`，发布成功或失败都会释放 claim，崩溃后 claim
  过期可由其他 publisher 重领。
- `ExecutionStepItem.summary_payload` 允许保存脱敏小摘要和协议归并所需的小型
  hint；归并真相仍是 owner reference、chain/step/item id。
- Late background tool result 默认 `late_observed` + operational risk，不自动
  resume 已闭合 chain。
- 现阶段保留 `orchestration_scheduler` 和 `orchestration_executor` 两个进程：
  scheduler 负责 ingress/continuation 分发和 executor lease 分配，executor 只 claim
  `orchestration_step` 并执行。

仍保留为后续结构性决策：

- `orchestration_runs` 是否物理重命名为 `orchestration_turns`。当前代码语义已按
  Turn 收口，但表名和部分 DTO 字段仍沿用历史 `run` 命名；后续应作为独立命名迁移处理，
  不应和本轮 dispatch/execution-chain 收口混在一起。
