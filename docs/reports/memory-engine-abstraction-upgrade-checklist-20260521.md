# Memory Engine Abstraction Upgrade Checklist 2026-05-21

本文是 Memory Engine 抽象升级的施工与收口记录。目标不是恢复旧的
memory candidate/review queue，也不是把当前 markdown file memory 简单包一层
adapter，而是把 Memory 收敛为：

```text
Agent context / AgentProfile memory scope
  -> Memory module resolve scope
  -> Memory engine recall / remember
  -> Engine-owned storage and indexing
```

后续 agent 施工以本文的目标边界、验收标准和 2026-05-22 收口记录为准；如本文与旧
memory 文档冲突，优先本文。

## 目标结论

Memory 模块应该提供统一的治理和运行抽象：

- Agent 不关心 memory 如何存储、如何索引、如何分层。
- Agent 可以显式或隐式提供 memory 隔离域，例如 `scope_ref=auto` 或
  `scope_ref=project-alpha-shared`。
- Memory 模块负责解析 scope、选择 engine、应用 policy、记录事件和审计。
- Engine 负责具体 recall/remember 能力、物理存储、索引、压缩、归档和检索强度。
- Orchestration 只问 Memory 要两种能力：`recall` 和 `remember`。
- Tool 通过 `ToolExecutionContext` 获得 agent/run/session/workspace 等上下文，通过
  Memory service 执行读写；需要外部凭证时通过 Access credential binding 获取。

当前 file-backed markdown memory 继续作为一个 engine 存在：

```text
engine=file_markdown
truth=MEMORY.md + memory/*.md
index=derived sqlite index
```

但它不再是 Memory 的唯一业务模型。

## 非目标

- 不恢复 automatic turn memory candidates。
- 不恢复 approve/reject memory review queue。
- 不让 Orchestration 直接写 memory truth。
- 不让 Agent 保存 engine、storage root、index backend、credential details。
- 不让前端绕过 Memory/Operations 直接拼文件系统状态。
- 不保留 `.state/memory-binding.json` 作为长期配置机制。
- 不为了兼容旧 memory entry DB 增加长期 shim。

## 原始问题与收口状态

- 新建 Memory space 已由 Memory owner storage root 分配；旧记录可能仍指向历史
  agent home。当前通过显式 `memory migrate-legacy-agent-homes` CLI/action 迁移并报告。
- Agent memory binding 曾存在 sidecar 文件 `.state/memory-binding.json`；当前只作为显式
  migration 输入，不作为长期配置机制。
- `FileMemoryContextResolver` 位于 orchestration adapter，实际承担通用
  agent context -> memory context 解析。当前解析职责已迁到 app integration /
  Memory owner runtime surface。
- 写入路径不完全统一：memory tools、HTTP、Operations action、通用文件工具都可能接触
  memory 文件。当前运行写入统一经 `MemoryRuntimeService.remember`，旧 file-backed HTTP/CLI
  入口保留为 Memory owner 操作面。
- Memory 曾把 `long_term/daily/archive` 绑定在 file layout 上，缺少 engine
  capability 抽象。当前 file markdown 只是 engine，bucket 语义归 engine 内部；
  layer access 由后续分层访问清单治理。
- Index lifecycle 主要依赖 dirty/fingerprint/warm/search，被动同步状态需要更清晰；
  当前通过 Memory owner action、readiness/event 和 Operations projection 暴露。
- Settings memory page 已从 generic `memory-config` JSON 页切换为 Memory owner 治理面，
  读取 `/memory/spaces`、`/memory/policies` 和 `/memory/runtime-defaults`。

## 目标边界

### Agent Owns

- agent id、身份、运行 profile。
- memory 是否启用。
- memory scope 引用：
  - `auto`：由 Memory 根据 agent 上下文创建或解析私有隔离域。
  - explicit scope id：绑定已有 shared/project/team/system scope。
- 可选的读写偏好，但不能包含 engine/storage/index 细节。

示例：

```json
{
  "memory": {
    "enabled": true,
    "scope_ref": "auto",
    "access": "read_write"
  }
}
```

### Memory Owns

- `MemoryScope` / `MemorySpace`。
- scope 解析与自动创建。
- engine 选择与 engine config 归属。
- recall/remember 统一 application surface。
- policy、capability、readiness、audit、events。
- Memory Operations query surface。
- Memory Settings 页面背后的 owner application。

### Memory Engine Owns

- 物理存储位置和格式。
- 索引方式与同步策略。
- 是否区分 long-term/daily/archive/episode/fact 等内部 bucket。
- recall 排序、压缩、引用格式。
- remember 如何落地、是否做 consolidation。

Engine 可以声明 capability，但不能要求 Orchestration 理解自己的内部格式。

### Orchestration Owns

- 什么时候进行 recall。
- 什么时候发起 memory flush/maintenance run。
- Prompt surface 是否允许 memory bootstrap。
- Tool exposure policy。

Orchestration 不拥有 memory 文件、bucket、index、engine 配置。

### Tool Owns

- Tool function 参数和执行逻辑。
- 是否需要 `ToolExecutionContext` 中的 `agent_id`、`workspace_dir`、`session_key` 等。
- 是否需要 Access credential binding。

Tool 不接收模型传入的 `agent_id` 来访问 memory；必须从
`ToolExecutionContext` 取当前运行身份。

### Access Owns

- 外部凭证绑定、OAuth/account/API key source。
- Credential resolution。
- Credential readiness/audit。

Memory engine 或 tool 如需外部 API key，只引用 Access binding，不直接读 secret。

## 目标模型

### MemoryScopeRef

用于 Agent/Run/Tool 表达“我要哪个记忆隔离域”。

字段建议：

- `enabled: bool`
- `scope_ref: "auto" | string`
- `access: "read" | "read_write"`
- `policy_ref?: string`

### MemorySpace

Memory 模块中的一等资源。

字段建议：

- `space_id`
- `scope_key`
- `owner_kind`: `agent | project | team | system | imported`
- `owner_id`
- `engine_id`
- `status`: `active | disabled | migrating | error`
- `policy_id`
- `created_at`
- `updated_at`

### MemoryEngineBinding

绑定 space 与 engine。

字段建议：

- `space_id`
- `engine_id`
- `engine_config`
- `readiness`
- `last_synced_at`
- `last_error`

### MemoryPolicy

治理层策略，不泄露 engine 内部结构。

字段建议：

- `recall_enabled`
- `remember_enabled`
- `default_retention`
- `write_requires_tool`
- `shared_write_policy`
- `max_recall_tokens`
- `auto_bootstrap_enabled`

### MemoryIntent

`remember` 的上层意图。它不强制 engine 分桶，只提供治理 hint。

建议初始枚举：

- `fact`
- `preference`
- `episode`
- `project_note`
- `skill_learning`
- `freeform`

### MemoryRetentionHint

- `engine_default`
- `durable`
- `session`
- `temporary`

## Target Application Surface

Memory 面向运行时的最小稳定 surface：

```python
class MemoryRuntimeService:
    def resolve_scope(self, context: MemoryActorContext) -> MemoryResolvedScope:
        ...

    def recall(self, request: MemoryRecallRequest) -> MemoryRecallResult:
        ...

    def remember(self, request: MemoryRememberRequest) -> MemoryRememberResult:
        ...
```

请求对象建议：

```python
MemoryActorContext(
    agent_id=str | None,
    run_id=str | None,
    session_key=str | None,
    workspace_dir=str | None,
)

MemoryRecallRequest(
    actor=MemoryActorContext,
    query=str | None,
    intent=str | None,
    max_items=int,
    max_tokens=int | None,
)

MemoryRememberRequest(
    actor=MemoryActorContext,
    content=str,
    intent=MemoryIntent,
    retention=MemoryRetentionHint,
    metadata=dict,
)
```

Engine-facing contract:

```python
class MemoryEngine:
    def capabilities(self) -> MemoryEngineCapabilities:
        ...

    def ensure_space(self, space: MemorySpace, config: Mapping[str, object]) -> None:
        ...

    def recall(self, request: EngineRecallRequest) -> EngineRecallResult:
        ...

    def remember(self, request: EngineRememberRequest) -> EngineRememberResult:
        ...

    def rebuild(self, space_id: str) -> EngineRebuildResult:
        ...
```

## Engine Capability Contract

每个 engine 必须声明 capability，供 Settings、Operations 和 readiness 使用：

- `supports_recall`
- `supports_remember`
- `supports_citations`
- `supports_vector_search`
- `supports_keyword_search`
- `supports_streaming_index`
- `supports_rebuild`
- `supports_shared_space`
- `requires_credentials`
- `credential_requirement_ids`

file markdown engine 的初始能力：

```text
supports_recall=true
supports_remember=true
supports_citations=true
supports_keyword_search=true
supports_vector_search=depends on embedding provider
supports_rebuild=true
supports_shared_space=true when storage_root is shared
requires_credentials=false by default; true for openai-compatible embedding
```

## Access Credential Rule

Memory engine 或 tool 如需外部凭证：

- 必须声明 credential requirement。
- 必须通过 Access credential binding resolution 获取。
- 不允许直接读固定环境变量名。
- 不允许在 Memory/Tool/LLM 配置中保存 raw secret。

例子：

```text
file_markdown engine + local hashed embedding:
  no credential

file_markdown engine + openai compatible embedding:
  credential_binding_id -> Access resolves API key
```

## ToolExecutionContext Rule

所有 agent-scoped tool，包括 memory tool，必须通过 runtime 注入的
`ToolExecutionContext` 取得上下文。

当前 runtime 已统一传入 context；升级后 tool catalog 应补治理元数据：

```yaml
context_requirements:
  - agent_id
  - session_key
```

该声明用于 readiness、UI 展示和启用前检查，不用于让模型传入这些字段。

## Orchestration Contract

Orchestration-facing memory port 应收敛为：

- `recall`
- `remember` 或 `request_remember`

原则：

- 普通 run 不隐式写 memory。
- Prompt bootstrap 只能调用受限 recall。
- Memory flush 是一个显式 maintenance run。
- Memory flush 成功必须产生 `memory.remember.*` 或 `memory.remember.skipped` 事件。
- Orchestration 不知道 engine 内部 bucket 或 file path。

## Settings / Operations UI Requirements

### Settings Memory Page

Settings 页面不再是 generic `memory-config` JSON 资源页，而是 Memory owner
治理页。

需要支持：

- Space 列表。
- Engine 选择。
- Engine readiness。
- Agent scope binding。
- Shared scope 管理。
- Policy 管理。
- Rebuild / rescan / export / disable actions。
- Access credential binding 选择和 readiness。

### Operations Memory Page

Operations 只展示运行状态，不做 owner 配置。

需要展示：

- recall latency / hit count / empty recall count。
- remember count / skipped count / failed count。
- engine readiness。
- stale index / rebuild state。
- recent memory events。
- per-space health。

## Migration Plan

### M1: Model and Contracts

- [x] 新增 Memory runtime/engine contract 与 dataclass model：
      `MemoryActorContext`、`MemoryResolvedScope`、`MemoryRecallRequest`、
      `MemoryRememberRequest`、`MemoryRecallResult`、`MemoryRememberResult`。
- [x] 新增 `MemoryRuntimeService` application surface。
- [x] 新增 `MemoryEngine` protocol 与 `MemoryEngineCapabilities`。
- [x] 将当前 file-backed service 包装为 `file_markdown` engine。
- [x] 保持 markdown files 作为 file engine truth。
- [x] 保持 sqlite index 作为 file engine derived index。
- [x] 补齐 MemorySpace 持久化 owner model。
- [x] 补齐 MemoryPolicy 持久化 owner model。

### M2: Agent Binding Cutover

- [x] AgentProfile 增加正式 `memory` 字段。
- [x] 支持 `scope_ref=auto`。
- [x] 支持 explicit shared scope id。
- [x] 移除新写入 `.state/memory-binding.json` 的路径。
- [x] 迁移旧 sidecar 到 AgentProfile.memory 或 MemorySpace。
- [x] 删除长期 sidecar fallback；migration/一次性导入之外不保留兼容。

### M3: Scope Resolver Ownership

- [x] 将 `FileMemoryContextResolver` 从 orchestration adapter 收回到 Memory/Agent
      integration application。
- [x] Runtime surface 输入 `MemoryActorContext`，输出 `MemoryResolvedScope`。
- [x] Resolver 能自动创建 agent-private space。
- [x] Resolver 能解析 project/team scope。
- [x] Resolver 能解析 explicit shared scope。
- [x] Resolver 不暴露 engine/storage detail 给 Agent。

### M4: Tool Contract

- [x] Memory tools 改为调用 `MemoryRuntimeService.recall/remember`。
- [x] Tool 参数中不允许出现 `agent_id`。
- [x] `tool.yaml` 增加 `context_requirements`。
- [x] Memory tool runtime 缺 `ToolExecutionContext.agent_id` 时 fail fast。
- [x] Tool readiness 缺 `agent_id` 时提前标记不可用。
- [x] 阻止 workspace/file 工具绕过 Memory service 写 memory-managed path。
- [x] 阻止 Agent Home scaffold/editor/migration 继续创建或搬运 memory 文件。
- [x] Memory write tool 统一经 `MemoryRuntimeService.remember` 写入。
- [x] Memory remember 事件统一为 engine-neutral `memory.remember.*`。

### M5: Access Integration

- [x] Engine credential requirement 进入 Access requirement catalog。
- [x] Memory Settings 只选择 Access binding id。
- [x] Engine 初始化/readiness 通过 Access credential provider 检查凭证。
- [x] 无 binding 时明确失败，不 fallback 到 env/raw secret。

### M6: Orchestration Cutover

- [x] Orchestration recall 只调用 Memory runtime surface。
- [x] Memory flush 只产生显式 remember/skip。
- [x] Orchestration 不直接处理 `MEMORY.md`、`daily`、`archive`。
- [x] Prompt bootstrap 改为受 policy 控制的 recall。
- [x] MemoryRuntimeService.recall/remember 应用 MemoryPolicy。
- [x] 移除 Orchestration 中 file-memory-specific 适配逻辑。

### M7: Settings UI

- [x] 重做 Memory Settings 页面为 owner governance 页面。
- [x] 后端暴露 Memory owner space/policy 查询与 space/policy action API。
- [x] Space/engine/policy 一屏内可读。
- [x] Access credential binding 在 Memory Settings owner 页内可读/可选。
- [x] 迁移通过 Memory owner action。
- [x] Space/policy 新建、保存、禁用、删除通过 Memory owner action。
- [x] Rebuild/export 通过 Memory owner action。
- [x] 不展示 generic `memory-config` JSON 编辑作为主交互。
- [x] Memory Settings owner 页新增文案进入 i18n。

### M8: Operations Read Model

- [x] Memory 模块发出 scope/retrieval/remember/index events，并进入
      Operations observer 订阅范围。
- [x] Memory 模块补齐 engine/readiness events。
- [x] Operations observer 物化 per-space projection。
- [x] Operations observer 物化 Memory file detail projection，`/operations/memory`
      page 不再携带重详情。
- [x] `/operations/memory` 优先读 projection。
- [x] 不让前端调用 Memory/Agent/Settings 多接口拼运行状态。
- [x] 补充 stale/rebuild/error/credential readiness 指标。

### M9: Data Migration

- [x] 扫描现有 AgentProfile home。
- [x] 为每个 agent 创建默认 MemorySpace。
- [x] 导入 `.state/memory-binding.json` 为正式 memory binding。
- [x] 记录 migration report。
- [x] migration 完成后禁止继续依赖 sidecar。
- [x] 保持现有 markdown 文件原地可读，不强制搬迁。

### M10: Verification

- [x] 单测：auto scope 创建。
- [x] 单测：explicit shared scope 解析。
- [x] 单测：MemoryRuntimeService.recall 调用 file engine。
- [x] 单测：MemoryRuntimeService.remember 调用 file engine。
- [x] 单测：MemoryPolicy 持久化模型/service 与 runtime enforcement。
- [x] 单测：Access credential binding 缺失或类型错误时，Access catalog/readiness
      与 engine 构建明确失败。
- [x] 单测：memory tool 不接受 agent_id 参数。
- [x] 单测：ToolExecutionContext 缺 agent_id 时 memory tool fail fast。
- [x] 单测：Tool readiness/runtime pool 缺 agent_id 时提前排除 memory tool。
- [x] 单测：orchestration memory flush 不直接写 agent workspace 文件。
- [x] 集成：两个 child sessions 同 agent 共享 memory。
- [x] 集成：不同 agent 默认隔离 memory。
- [x] 集成：两个 agent 显式绑定同一 shared scope 后共享 recall。
- [x] 前端：Memory Settings 页面 skeleton/data/error 不跳版。
- [x] 前端：Operations Memory 页面只消费 Operations projection API：
      `/operations/memory` 与 `/operations/memory/files/{file_id}/detail`。

## Progress Log

### 2026-05-22

- Added `MemoryRuntimeService`, actor/scope/recall/remember request-result
  models, `MemoryEngine` protocol, and engine capabilities.
- Added `FileMarkdownMemoryEngine` as the first engine over existing
  `FileBackedMemoryService`.
- Added `AppKey.MEMORY_RUNTIME_SERVICE` and assembled it from the current
  scope resolver plus file markdown engine.
- Changed memory local tools to depend on `memory_runtime_service` instead of
  composing `file_memory_service` and `memory_context_resolver` directly.
- Updated module-lifecycle dependency docs to reflect the narrower memory tool
  dependency surface.
- Added formal `AgentProfile.memory` binding with `enabled/scope_ref/access`.
- Stopped writing `.state/memory-binding.json` from settings import, HTTP/CLI
  profile sync, agent home scaffold, and application service persistence.
- Changed memory context resolution to use `AgentProfile.memory.scope_ref`
  instead of runtime attrs or sidecar files.
- Removed the long-term memory sidecar infrastructure export/file.
- Updated Agent Profiles settings UI API/types to write memory binding through
  `profile.memory` instead of legacy runtime attrs.
- Added `MemorySpace`, `MemorySpaceService`, SQLAlchemy repository, and
  `memory_spaces` migration as the Memory owner truth for scope/runtime storage.
- Moved agent-to-memory scope resolution into app integration via
  `AgentMemoryScopeResolver`; orchestration no longer exports or owns
  `FileMemoryContextResolver`.
- Added automatic agent-private scope creation and deterministic explicit shared
  scope reuse.
- Existing disabled MemorySpace records stay disabled during agent resolution;
  agent binding does not implicitly re-enable Memory owner state.
- Added `MemoryPolicy`, `MemoryPolicyService`, SQLAlchemy repository, and
  `memory_policies` migration as the Memory owner truth for recall/remember
  governance.
- Added `AppKey.MEMORY_POLICY_SERVICE` and wired policy evaluation into
  `MemoryRuntimeService.recall/remember`.
- Added Memory owner HTTP/CLI surfaces for listing spaces, listing policies,
  upserting policies, disabling policies, and deleting policies.
- Runtime recall now clamps `max_items` by effective policy; runtime remember
  fails fast when the effective policy disables writes.
- Replaced orchestration `MemoryPort` with the Memory runtime contract
  (`resolve_scope/recall/remember`) and removed the old
  `FileBackedMemoryPortAdapter`.
- Prompt bootstrap memory now calls `MemoryRuntimeService.recall`; `MEMORY.md`
  is no longer loaded through workspace project context.
- Added `Tool.context_requirements`, local package manifest parsing, catalog
  metadata persistence, `/tools/{tool_id}/readiness` context query checks, and
  runtime pool exclusion for missing required context.
- Declared `agent_id` as the required runtime context for all bundled memory
  tools; the declaration is exposed through Tool owner APIs and Settings Tool
  catalog types.
- Blocked workspace write/edit/apply_patch writes to memory-managed paths
  (`MEMORY.md`, `memory/*.md`) so durable memory updates must go through Memory
  tools/runtime instead of generic workspace file mutation.
- Replaced low-level `memory.write.*` operation events with engine-neutral
  `memory.remember.*` events for memory mutation facts.
- Fixed orchestration unit test skill-root isolation so test containers do not
  capture the real repository `skills/` directory before patched roots are
  applied.
- Removed Agent-owned memory retrieval backend from AgentProfile domain,
  HTTP/CLI DTOs, Agent Profiles settings UI, and Workbench agent runtime
  projection; retrieval backend is now only Memory/Settings owner
  configuration.
- Added `APP_MEMORY_STORAGE_ROOT` / `memory_storage_root` bootstrap support and
  changed `MemorySpaceService` to allocate storage roots per scope from Memory
  owner configuration instead of deriving them from Agent runtime home/workspace.
- Added explicit owner-kind classification for `project:<id>`, `team:<id>`,
  and `system:<id>` memory scopes; other explicit scopes remain shared.
- Updated orchestration memory tests so durable memory fixtures are written to
  resolved Memory scope storage, and test harnesses isolate Memory storage under
  their temp directories.
- Confirmed memory flush runs expose only `memory_write_daily` and
  `memory_flush_skip`; text replies fail with
  `memory_flush_protocol_violation`, and writes are executed through
  `MemoryRuntimeService.remember`.
- Removed `MEMORY.md` and `memory/` from Agent Home scaffold, editable file
  list, and home migration copies. Agent Home now keeps identity/instruction
  files only; durable facts are written through Memory tools/runtime.
- Removed legacy Agent `memory_space` / `memory_space_id` mapping from settings,
  home config, and `AgentMemoryBinding.from_payload`; Agent memory binding now
  accepts only the formal `memory.scope_ref` payload.
- Added explicit `memory migrate-legacy-agent-homes` CLI migration. It scans
  registered Agent homes, imports `.state/memory-binding.json` into formal
  `AgentProfile.memory`, ensures Memory owner spaces, copies legacy
  `MEMORY.md`/`memory/*.md` into Memory owner storage without moving source
  files, optionally deletes imported sidecars, and emits a migration report.
- Projected openai-compatible Memory vector embedding credentials into the
  Access requirement catalog as a Memory engine consumer. Access UI/inventory can
  now see the Memory `embedding_api_key` requirement and its bound Access
  credential id.
- Tightened Memory embedding construction: openai-compatible embedding now
  requires `vector_credential_binding_id`, validates that the Access binding
  exists, is active, and is an `api_key`, and still resolves the secret only
  through Access at embedding time.
- Removed runtime `MemoryActorContext.from_attrs` fallback for legacy
  `memory_space` / `memory_space_id`; current runtime context accepts
  `memory_scope_ref` / `scope_ref` only.
- Added Memory runtime event names to the Operations observer static
  subscription set. Observer-driven projection invalidation now reacts to
  `memory.context.*`, `memory.index.*`, `memory.retrieval.*`, and
  `memory.remember.*` events even when no dynamic event definition registry is
  injected.
- Updated Memory Operations write/flush projection to recognize
  `memory.remember.*` events, matching the engine-neutral write event contract.
- Added `memory.engine.readiness_observed` and `memory.engine.readiness_failed`
  events. Memory service assembly now reports file markdown engine readiness,
  vector provider/model, credential binding id, and clear failure reason for
  invalid embedding configuration.
- Confirmed Operations Memory frontend consumes only Operations routes
  (`/operations/memory`, the Memory detail endpoint, and the operation action
  route); it does not call Memory/Agent/Settings owner APIs to assemble runtime
  state.
- Split Memory Operations file detail payloads into separate
  `memory_file_detail` projections. The page projection now strips
  `file_details`, and the frontend loads selected file details through the
  Operations detail endpoint instead of carrying all file excerpts in the first
  payload.
- Replaced the Memory Settings frontend from generic `/ui/settings/memory-config`
  resource inspection with a Memory owner governance page. The page now reads
  `/memory/spaces` and `/memory/policies`, supports space/policy create-update,
  disable, and delete actions, and keeps newly added UI copy in i18n.
- Added a compact Memory Settings runtime defaults panel that reads Access
  credential bindings, filters API-key bindings for the OpenAI-compatible
  embedding provider, and saves only the selected Memory vector binding/defaults
  instead of exposing generic config JSON.
- Moved Memory runtime defaults UI traffic behind `/memory/runtime-defaults`.
  The Memory owner endpoint still persists through Settings governance
  internally, but the frontend no longer calls the generic Settings resource API
  or knows `memory-config/default`.
- Added a Memory owner query service for scope inventory, file summaries,
  excerpts, search, index path/count, and dirty-state facts. Operations read
  models now depend on that query service instead of receiving
  `FILE_MEMORY_SERVICE` plus `MEMORY_CONTEXT_RESOLVER` directly.
- Changed the Operations long-term memory action to call
  `MemoryRuntimeService.remember` instead of resolving a file-backed context and
  writing the long-term file itself.
- Removed remaining module-to-`crxzipple.app` imports from Memory/Access
  interfaces. Memory legacy migration is now exposed to module interfaces via an
  assembled app key, and the Memory credential consumer projection lives under
  Access application code instead of `app.integration`.
- Removed the duplicate `AppKey.MEMORY_PORT` alias and orchestration-owned
  `MemoryPort` protocol. Orchestration now depends on the Memory module's
  exported `MemoryRuntimePort` contract and the assembled
  `MEMORY_RUNTIME_SERVICE`.
- Moved long-term memory file-name knowledge behind `MemoryQueryService`; the
  Operations module overview no longer hardcodes `MEMORY.md` / `memory.md`.
- Added Memory owner actions for per-space index rebuild and export manifest;
  Settings UI now calls those owner actions from the selected space panel.
- Added a Memory owner legacy migration action endpoint for agent-home sidecar
  migration dry-runs/applies, reusing the existing migration service behind CLI.
- Added Memory Operations per-space detail projections and metric indicators for
  stale indexes, forced rebuild events, observed errors, and engine credential
  readiness.
- Added Memory runtime coverage for same-agent child-session sharing, default
  per-agent isolation, and explicit shared scope recall.
- Stabilized Memory Settings loading/empty states with fixed panel heights and
  localized loading copy so initial data load does not collapse the page layout.
- Verification:
  - `ruff check src/crxzipple/modules/memory/interfaces/http.py tests/unit/test_memory_http.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_memory_http.py tests/unit/test_memory_legacy_migration.py tests/unit/test_memory_runtime_service.py tests/unit/test_operations_observation.py`
  - `ruff check src/crxzipple/modules/memory/application/query.py src/crxzipple/modules/memory/application/__init__.py src/crxzipple/app/keys.py src/crxzipple/app/assembly/memory.py src/crxzipple/app/assembly/operations.py src/crxzipple/modules/operations/application/read_models/ports.py src/crxzipple/modules/operations/application/read_models/factory.py src/crxzipple/modules/operations/application/read_models/modules.py src/crxzipple/modules/operations/application/read_models/memory.py tests/unit/test_operations_observation.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py tests/unit/test_app_assembly_module_local.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_memory_http.py tests/unit/test_memory_runtime_service.py tests/unit/test_operations_observation.py`
  - `ruff check src/crxzipple/modules/operations/application/actions.py src/crxzipple/modules/operations/interfaces/http.py src/crxzipple/modules/memory/application/query.py src/crxzipple/modules/operations/application/read_models/memory.py src/crxzipple/modules/operations/application/read_models/modules.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py tests/unit/test_memory_http.py`
  - `ruff check tests/unit/test_ui_http.py tests/unit/test_operations_read_model_boundaries.py src/crxzipple/modules/operations/application/read_models/memory.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_operations_memory_page_uses_file_memory_runtime_state tests/unit/test_operations_read_model_boundaries.py`
  - `ruff check src/crxzipple/app/keys.py src/crxzipple/app/assembly/memory.py src/crxzipple/app/integration/__init__.py src/crxzipple/modules/memory/interfaces/http.py src/crxzipple/modules/memory/interfaces/cli.py src/crxzipple/modules/access/application/memory_consumers.py src/crxzipple/modules/access/application/__init__.py src/crxzipple/modules/access/interfaces/inventory.py src/crxzipple/modules/access/interfaces/ui_http.py tests/unit/test_memory_access_requirements.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_module_lifecycle_architecture.py::test_modules_do_not_import_app_assembly_layer tests/unit/test_memory_access_requirements.py tests/unit/test_memory_http.py tests/unit/test_memory_cli.py tests/unit/test_memory_legacy_migration.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_module_lifecycle_architecture.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_app_assembly_architecture.py tests/unit/test_application_port_boundaries.py`
  - `ruff check src/crxzipple/app/keys.py src/crxzipple/app/assembly/memory.py src/crxzipple/app/assembly/orchestration.py src/crxzipple/app/integration/context_workspace_memory.py src/crxzipple/modules/memory/application/runtime.py src/crxzipple/modules/memory/application/__init__.py src/crxzipple/modules/orchestration/application/ports/__init__.py src/crxzipple/modules/orchestration/application/prompt_surface.py src/crxzipple/modules/orchestration/application/engine.py src/crxzipple/modules/orchestration/application/service_graph.py src/crxzipple/modules/orchestration/application/__init__.py src/crxzipple/modules/orchestration/__init__.py tests/unit/test_app_assembly_module_local.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_app_assembly_module_local.py tests/unit/test_orchestration_memory.py tests/unit/test_orchestration_tools.py::OrchestrationToolsTestCase::test_process_next_orchestration_assignment_completes_inline_tool_loop`
  - `ruff check src/crxzipple/modules/memory/application/query.py src/crxzipple/modules/operations/application/read_models/ports.py src/crxzipple/modules/operations/application/read_models/modules.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_operations_memory_page_uses_file_memory_runtime_state tests/unit/test_operations_read_model_boundaries.py tests/unit/test_operations_observation.py`
  - `cd frontend && npm run typecheck`
  - `cd frontend && npm run build`
  - `PYTHONPATH=src pytest -q tests/unit/test_memory_runtime_service.py tests/unit/test_file_backed_memory.py tests/unit/test_tool_catalog.py tests/unit/test_module_lifecycle_architecture.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_memory_http.py tests/unit/test_memory_cli.py tests/unit/test_app_assembly_module_local.py tests/unit/test_tool_providers.py tests/unit/test_tool_execution.py::ToolExecutionTestCase::test_tool_service_surface_prefers_assignment_runtime_over_queue_execution_helpers`
  - `PYTHONPATH=src pytest -q tests/unit/test_orchestration_memory.py tests/unit/test_orchestration_tools.py::OrchestrationToolsTestCase::test_process_next_orchestration_assignment_completes_inline_tool_loop`
  - `PYTHONPATH=src pytest -q tests/unit/test_agent_settings_integration.py tests/unit/test_agent_home_scaffold.py tests/unit/test_app_assembly_module_local.py tests/unit/test_agent_http.py tests/unit/test_agent_cli.py tests/unit/test_orchestration_memory.py tests/unit/test_memory_runtime_service.py`
  - `ruff check src/crxzipple/core/config.py src/crxzipple/modules/agent/domain/value_objects.py src/crxzipple/modules/agent/domain/entities.py src/crxzipple/modules/agent/domain/__init__.py src/crxzipple/modules/agent/application/services.py src/crxzipple/modules/agent/application/settings_integration.py src/crxzipple/modules/agent/infrastructure/home_config.py src/crxzipple/modules/agent/infrastructure/home_scaffold.py src/crxzipple/modules/agent/infrastructure/home_files.py src/crxzipple/modules/agent/infrastructure/__init__.py src/crxzipple/modules/agent/interfaces/dto.py src/crxzipple/modules/agent/interfaces/http.py src/crxzipple/modules/agent/interfaces/cli.py src/crxzipple/modules/orchestration/infrastructure/adapters/file_memory.py src/crxzipple/app/assembly/agent.py src/crxzipple/app/assembly/memory.py tests/unit/test_agent_settings_integration.py tests/unit/test_agent_home_scaffold.py tests/unit/test_app_assembly_module_local.py`
  - `cd frontend && npm run typecheck`
  - `PYTHONPATH=src pytest -q tests/unit/test_memory_spaces.py tests/unit/test_memory_runtime_service.py tests/unit/test_orchestration_memory.py tests/unit/test_app_assembly_module_local.py tests/unit/test_agent_settings_integration.py tests/unit/test_agent_http.py tests/unit/test_agent_cli.py`
  - `ruff check src/crxzipple/modules/memory/domain/entities.py src/crxzipple/modules/memory/domain/value_objects.py src/crxzipple/modules/memory/domain/__init__.py src/crxzipple/modules/memory/application/spaces.py src/crxzipple/modules/memory/application/__init__.py src/crxzipple/modules/memory/infrastructure/persistence/models.py src/crxzipple/modules/memory/infrastructure/persistence/repositories.py src/crxzipple/modules/memory/infrastructure/persistence/__init__.py src/crxzipple/modules/memory/infrastructure/__init__.py src/crxzipple/modules/memory/__init__.py src/crxzipple/app/integration/memory_scope_resolution.py src/crxzipple/app/assembly/memory.py src/crxzipple/app/keys.py src/crxzipple/core/db.py src/crxzipple/modules/orchestration/infrastructure/adapters/file_memory.py src/crxzipple/modules/orchestration/infrastructure/adapters/__init__.py src/crxzipple/modules/orchestration/__init__.py src/crxzipple/modules/memory/application/event_contracts.py src/crxzipple/modules/agent/domain/value_objects.py tests/unit/test_memory_spaces.py alembic/versions/0057_memory_spaces.py`
  - `ruff check src/crxzipple/modules/memory/application/runtime.py src/crxzipple/modules/memory/application/policies.py src/crxzipple/modules/memory/domain/entities.py src/crxzipple/modules/memory/domain/value_objects.py src/crxzipple/modules/memory/domain/__init__.py src/crxzipple/modules/memory/infrastructure/persistence/models.py src/crxzipple/modules/memory/infrastructure/persistence/repositories.py src/crxzipple/modules/memory/infrastructure/persistence/__init__.py src/crxzipple/modules/memory/infrastructure/__init__.py src/crxzipple/modules/memory/interfaces/http.py src/crxzipple/modules/memory/interfaces/cli.py src/crxzipple/modules/memory/application/__init__.py src/crxzipple/modules/memory/__init__.py src/crxzipple/app/assembly/memory.py src/crxzipple/app/keys.py tests/unit/test_memory_policies.py tests/unit/test_memory_http.py alembic/versions/0058_memory_policies.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_memory_policies.py tests/unit/test_memory_spaces.py tests/unit/test_memory_runtime_service.py tests/unit/test_memory_http.py tests/unit/test_app_assembly_module_local.py tests/unit/test_orchestration_memory.py`
  - `ruff check src/crxzipple/app/integration/context_workspace_memory.py src/crxzipple/modules/orchestration/application/prompt_surface.py src/crxzipple/app/assembly/memory.py src/crxzipple/app/assembly/orchestration.py src/crxzipple/modules/orchestration/infrastructure/adapters/__init__.py src/crxzipple/modules/orchestration/__init__.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_orchestration_memory.py tests/unit/test_memory_runtime_service.py tests/unit/test_memory_policies.py tests/unit/test_app_assembly_module_local.py`
  - `ruff check src/crxzipple/modules/tool/application/context_requirements.py src/crxzipple/modules/tool/domain/entities.py src/crxzipple/modules/tool/application/specifications.py src/crxzipple/modules/tool/application/catalog_models.py src/crxzipple/modules/tool/infrastructure/tool_packages.py src/crxzipple/modules/tool/application/service_support.py src/crxzipple/modules/tool/application/runtime_pool_service.py src/crxzipple/modules/tool/application/services.py src/crxzipple/modules/tool/interfaces/dto.py src/crxzipple/modules/tool/interfaces/http.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_tool_catalog.py tests/unit/test_tool_http.py tests/unit/test_tool_source_service.py tests/unit/test_tool_source_catalog_persistence.py tests/unit/test_tool_catalog_reconcile.py tests/unit/test_tool_providers.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_orchestration_tools.py tests/unit/test_orchestration_memory.py tests/unit/test_tool_execution.py tests/unit/test_memory_runtime_service.py tests/unit/test_memory_policies.py`
  - `cd frontend && npm run typecheck`
  - `ruff check tools/workspace/fs_safe.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_tool_workspace.py tests/unit/test_tool_catalog.py tests/unit/test_tool_http.py`
  - `ruff check src/crxzipple/modules/memory/__init__.py src/crxzipple/modules/memory/application/events.py src/crxzipple/modules/memory/application/services.py src/crxzipple/modules/memory/application/__init__.py tests/unit/test_memory_runtime_service.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_memory_runtime_service.py tests/unit/test_file_backed_memory.py tests/unit/test_memory_http.py tests/unit/test_memory_policies.py tests/unit/test_tool_workspace.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py tests/unit/test_app_assembly_module_local.py tests/unit/test_module_lifecycle_architecture.py`
  - `ruff check src/crxzipple/modules/agent/domain/value_objects.py src/crxzipple/modules/agent/application/services.py src/crxzipple/modules/agent/interfaces/dto.py src/crxzipple/modules/agent/interfaces/http.py src/crxzipple/modules/agent/interfaces/cli.py src/crxzipple/modules/agent/infrastructure/home_config.py src/crxzipple/app/integration/memory_scope_resolution.py src/crxzipple/modules/orchestration/application/read_models/workbench.py tests/unit/test_memory_spaces.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_agent_settings_integration.py tests/unit/test_agent_http.py tests/unit/test_agent_cli.py tests/unit/test_memory_spaces.py tests/unit/test_orchestration_memory.py tests/unit/test_app_assembly_module_local.py`
  - `cd frontend && npm run typecheck`
  - `ruff check src/crxzipple/core/config.py src/crxzipple/modules/settings/application/setup.py src/crxzipple/modules/memory/application/settings_integration.py src/crxzipple/modules/memory/application/spaces.py src/crxzipple/app/assembly/memory.py src/crxzipple/app/integration/memory_scope_resolution.py tests/unit/test_memory_spaces.py tests/unit/test_settings_materialization.py tests/unit/test_app_assembly_module_local.py tests/unit/support.py`
  - `ruff check src/crxzipple/modules/operations/application/projections.py src/crxzipple/modules/operations/interfaces/http.py src/crxzipple/modules/operations/application/read_models/memory.py tests/unit/test_operations_observation.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py`
  - `cd frontend && npm run typecheck`
  - `PYTHONPATH=src pytest -q tests/unit/test_orchestration_memory.py::OrchestrationMemoryTestCase::test_request_memory_flush_records_durable_memory_without_transcript_reply`
  - `ruff check src/crxzipple/modules/memory/application/spaces.py src/crxzipple/modules/memory/interfaces/http.py tests/unit/test_memory_http.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_memory_http.py::MemoryHttpTestCase::test_memory_space_and_policy_owner_endpoints`
  - `PYTHONPATH=src pytest -q tests/unit/test_memory_http.py`
  - `cd frontend && npm run typecheck`
  - `cd frontend && npm run build`
  - `PYTHONPATH=src pytest -q tests/unit/test_memory_http.py tests/unit/test_memory_spaces.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_memory_spaces.py tests/unit/test_settings_materialization.py tests/unit/test_app_assembly_module_local.py tests/unit/test_memory_runtime_service.py tests/unit/test_orchestration_memory.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_agent_settings_integration.py tests/unit/test_agent_http.py tests/unit/test_agent_cli.py tests/unit/test_tool_workspace.py`
  - `cd frontend && npm run typecheck`
  - `ruff check src/crxzipple/modules/memory/domain/value_objects.py src/crxzipple/modules/memory/domain/entities.py src/crxzipple/app/integration/memory_scope_resolution.py tests/unit/test_memory_spaces.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_memory_spaces.py tests/unit/test_memory_runtime_service.py tests/unit/test_orchestration_memory.py`
  - `ruff check src/crxzipple/modules/agent/infrastructure/home_files.py src/crxzipple/modules/agent/infrastructure/home_scaffold.py src/crxzipple/modules/agent/infrastructure/home_migration.py src/crxzipple/modules/agent/interfaces/cli.py tests/unit/test_agent_home_scaffold.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_agent_http.py tests/unit/test_agent_home_scaffold.py tests/unit/test_agent_settings_integration.py tests/unit/test_app_assembly_module_local.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_tool_workspace.py tests/unit/test_memory_spaces.py tests/unit/test_orchestration_memory.py`
  - `cd frontend && npm run typecheck`
  - `ruff check src/crxzipple/modules/agent/domain/value_objects.py src/crxzipple/modules/agent/application/settings_integration.py src/crxzipple/modules/agent/infrastructure/home_config.py src/crxzipple/modules/agent/infrastructure/home_files.py src/crxzipple/modules/agent/infrastructure/home_scaffold.py src/crxzipple/modules/agent/infrastructure/home_migration.py src/crxzipple/modules/agent/interfaces/cli.py tests/unit/test_agent_settings_integration.py tests/unit/test_agent_home_scaffold.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_agent_settings_integration.py tests/unit/test_agent_http.py tests/unit/test_agent_cli.py tests/unit/test_app_assembly_module_local.py tests/unit/test_agent_home_scaffold.py`
  - `ruff check src/crxzipple/app/integration/memory_legacy_migration.py src/crxzipple/app/integration/memory_scope_resolution.py src/crxzipple/app/integration/__init__.py src/crxzipple/modules/memory/interfaces/cli.py tests/unit/test_memory_legacy_migration.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_memory_cli.py tests/unit/test_memory_legacy_migration.py tests/unit/test_memory_spaces.py tests/unit/test_agent_settings_integration.py`
  - `ruff check src/crxzipple/app/assembly/memory.py src/crxzipple/app/integration/memory_access_requirements.py src/crxzipple/app/integration/__init__.py src/crxzipple/modules/access/interfaces/ui_http.py src/crxzipple/modules/access/interfaces/inventory.py src/crxzipple/modules/memory/application/runtime.py tests/unit/test_memory_access_requirements.py tests/unit/test_memory_runtime_service.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_memory_access_requirements.py tests/unit/test_memory_runtime_service.py tests/unit/test_file_backed_memory.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_access_read_models.py tests/unit/test_access_tool_integration.py`
  - `ruff check src/crxzipple/modules/operations/application/runtime.py src/crxzipple/modules/operations/application/read_models/memory.py tests/unit/test_operations_observation.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py`
  - `ruff check src/crxzipple/app/assembly/memory.py src/crxzipple/modules/memory/application/events.py src/crxzipple/modules/memory/application/event_contracts.py src/crxzipple/modules/memory/application/__init__.py src/crxzipple/modules/operations/application/runtime.py tests/unit/test_app_assembly_module_local.py tests/unit/test_operations_observation.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_app_assembly_module_local.py tests/unit/test_operations_observation.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_memory_access_requirements.py tests/unit/test_memory_runtime_service.py tests/unit/test_file_backed_memory.py tests/unit/test_access_read_models.py tests/unit/test_access_tool_integration.py`
  - `rg -n "(/memory|/agent|/settings|loadMemory|loadAgent|loadSettings|fetch\\()" frontend/src/pages/operations frontend/src/shared`

## Acceptance Criteria

升级完成后必须满足：

- Agent profile 不保存 storage root/engine/index/credential 细节。
- Agent profile 只保存 memory enabled/scope/access/policy 引用。
- MemorySpace 是 Memory owner 的一等资源。
- file markdown 只是一个 engine。
- sqlite index 只是 file markdown engine 的派生索引。
- Orchestration 不知道 `MEMORY.md`、`memory/YYYY-MM-DD.md`。
- Tool 不让模型传 agent_id 访问 memory。
- Memory tool 通过 `ToolExecutionContext` 取 agent_id。
- 外部凭证统一通过 Access binding。
- Settings 管 Memory owner action，不再是 generic JSON wrapper。
- Operations 通过 events/projection 观察 memory，不拥有 memory truth。

## Historical Implementation Order

1. M1 + M3：先建立 Memory runtime surface 和 resolver ownership。
2. M2：把 AgentProfile.memory 正式化，迁出 sidecar。
3. M4 + M6：切 tool/orchestration 调用面。
4. M5：接 Access credential requirement。
5. M8：补 Operations events/projection。
6. M7：改 Settings UI。
7. M9 + M10：迁移和全链路验收。

## Open Decisions

- `remember` 是否直接暴露给普通 run，还是只允许 memory tool / maintenance run 调用。
- `MemoryIntent` 初始枚举是否保留，还是只传 freeform + metadata。
- file markdown engine 是否保留 `long_term/daily/archive` 作为内部 bucket。
- shared scope 的默认写权限是所有绑定 agent 可写，还是 owner-only。
- 是否需要 MemorySpace export/import 标准包格式。
