# Memory Layered Access Upgrade Checklist 2026-05-22

本文是 Memory 下一步施工文档。它接在
[memory-engine-abstraction-upgrade-checklist-20260521.md](memory-engine-abstraction-upgrade-checklist-20260521.md)
之后，用来收口“一个 agent 一个身份 scope，同时可受控读取/写入公共记忆”的设计。

## 目标结论

Agent 仍然只有一个 memory identity scope。这个 scope 是 agent 的身份隔离域，
不是一个可随意切换的检索列表。

Memory 模块在运行时根据 actor、space、policy 生成 access plan：

```text
actor agent_id=assistant
  -> identity scope: assistant
  -> private layer: assistant, read/write
  -> shared layers: common/project/team/system, policy gated
  -> engine recall over allowed layers
  -> remember defaults to private layer unless explicit shared write is allowed
```

Engine 可以支持多 layer recall，但 engine 不决定“agent 能读哪些公共记忆”。
权限、治理和默认写入目标由 Memory application/runtime 解析。

## 非目标

- 不在 Agent Profile 里加入 `recall_scope_refs`、`shared_scope_refs` 这类多 scope 列表。
- 不让前端对多个 `/memory/search` 做并发拼接。
- 不让 Orchestration 理解 memory 的公共/私有存储结构。
- 不把公共记忆当成 agent 的 fallback scope。
- 不保留新旧 runtime 双轨兼容。
- 不恢复旧 automatic memory candidate/review queue。

## 当前状态

当前代码已经落地分层访问设计：

- `MemorySpace.owner_kind` 支持 `agent | shared | project | team | system`。
- `MemoryPolicy.target_kind` 支持 `global | space | agent`。
- `MemoryRuntimeService.recall/remember` 已经成为运行时入口。
- `MemoryRuntimeService` 解析 `MemoryAccessPlan`，由 actor identity scope 推导
  private layer，并按 Memory policy / space metadata 发现可读写公共 layer。
- `MemoryRecallResult` 返回 searched layers，结果项带 source scope / layer。
- `FileMarkdownMemoryEngine` 已支持 multi-layer recall、citation source 读取、
  合并排序、去重与截断。
- Settings runtime test 能显示检索 layer 和命中来源。
- Orchestration / memory tools 只传 actor context，公共 layer 由 Memory runtime
  决定。

本文件后续只作为设计和防回归依据；新增能力应继续保持一个 agent 一个 identity
scope，不把公共记忆列表塞回 Agent Profile。

## 目标边界

### Agent Owns

- agent id、身份、运行 profile。
- memory 是否启用。
- agent 自己的 identity scope 绑定，例如 `auto` 或 `assistant`。

Agent 不拥有公共 scope 列表、不拥有 engine config、不拥有公共记忆写入策略。

### Memory Owns

- MemorySpace / layer 声明。
- scope 自动创建与解析。
- actor -> access plan。
- policy 组合、deny-wins、max recall cap、retention hint。
- runtime recall/remember。
- Settings 中的 Memory owner 治理页面。

### Engine Owns

- 每个 layer 的物理存储、索引、排序、citation、压缩和归档。
- 是否支持 multi-layer recall。
- remember 如何落地。

Engine 只接收已经允许访问的 layers，不接收 agent policy 并自行判断授权。

### Orchestration Owns

- 何时 recall。
- 何时发起 explicit remember / memory maintenance run。
- prompt surface 如何使用 recall 结果。

Orchestration 只传 actor context，不拼公共 scope。

## 目标模型

### MemoryLayerRef

新增 application/domain value object：

```python
@dataclass(frozen=True, slots=True)
class MemoryLayerRef:
    scope_ref: str
    owner_kind: Literal["agent", "shared", "project", "team", "system"]
    layer_kind: Literal["private", "shared", "project", "team", "system"]
    access: Literal["read", "read_write"]
    default_write: bool = False
```

`private` layer 必须来自 actor identity scope。公共 layer 来自 MemorySpace，
是否进入默认 recall 由 Memory policy / metadata 控制。

### MemoryAccessPlan

新增 Memory runtime 解析结果：

```python
@dataclass(frozen=True, slots=True)
class MemoryAccessPlan:
    actor: MemoryActorContext
    identity_scope_ref: str
    private_layer: MemoryLayerRef
    readable_layers: tuple[MemoryLayerRef, ...]
    writable_layers: tuple[MemoryLayerRef, ...]
    default_write_layer: MemoryLayerRef
    policy: MemoryRuntimePolicy
```

关键规则：

- `identity_scope_ref = actor.scope_ref or actor.agent_id`。
- private layer 默认 read/write，除非 agent policy 禁止。
- shared/project/team/system layer 默认可读需要显式启用。
- shared layer 写入必须显式允许，默认 remember 仍写 private layer。
- 不同 agent 的 private layer 彼此隔离。

### MemoryRecallItem Source

扩展 recall item：

```python
@dataclass(frozen=True, slots=True)
class MemoryRecallItem:
    source_scope_ref: str
    source_layer_kind: str
    source_owner_kind: str
    path: str
    kind: str
    citation: str
    text: str
    ...
```

Settings / Operations / prompt assembly 可以据此显示命中来源。

### MemoryEngine Port

替换单 scope recall 为 layer-aware recall：

```python
class MemoryEngine(Protocol):
    def recall(
        self,
        *,
        layers: Sequence[MemoryResolvedLayer],
        request: MemoryRecallRequest,
    ) -> MemoryRecallResult:
        ...

    def remember(
        self,
        *,
        layer: MemoryResolvedLayer,
        request: MemoryRememberRequest,
    ) -> MemoryRememberResult:
        ...
```

`MemoryResolvedLayer` 包含 `MemoryUseContext + MemoryLayerRef + engine_id`。
file_markdown 初版可以遍历 allowed layers，分别调用现有 search/get，
合并后按 score 排序并截断。

## Policy 组合规则

当前 “global < space < agent 后覆盖” 要改掉。目标规则：

- 全局 policy 给默认上限。
- space policy 是 layer gate。
- agent policy 是 actor gate。
- deny wins：任意匹配 policy 禁止 recall/remember，则对应动作禁止。
- `max_recall_items` 取匹配 policy 的最小值。
- retention 默认来自最具体允许策略，但 shared 写入时必须满足 layer write gate。

建议新增：

```python
class MemoryAccessPolicyResolver:
    def resolve_plan(actor: MemoryActorContext) -> MemoryAccessPlan:
        ...
```

`MemoryPolicyService.effective_policy_for_scope` 可以退役，或收口为
`MemoryAccessPolicyResolver` 的内部 helper；不要长期保留两套 effective semantics。

## HTTP / CLI / UI

### HTTP

- `POST /memory/runtime/recall` 返回：
  - identity scope
  - searched layers
  - recall items with source scope/layer
  - effective policy summary
- `POST /memory/runtime/remember` 默认写 private layer。
- `POST /memory/runtime/remember` 可选 `target_scope_ref` 或 `target_layer_kind`，
  用于显式写公共记忆；无权限时返回 409。

### Settings UI

Memory Config 页需要表达：

- 当前 spaces，包括 owner kind、engine、status。
- 公共 layer 是否默认参与 recall：通过 Space 编辑器的 `Default Recall Layer`
  控件写入 `metadata.default_recall_enabled`，不要求用户编辑 JSON。
- 公共 layer 是否允许写入：通过 Space 编辑器的 `Allow Shared Writes`
  控件写入 `metadata.shared_write_enabled`，仍需 policy 允许后才能写入。
- Runtime Test 显示 searched layers 和每条命中的 source。
- 新建/编辑 policy 时用治理语言，不暴露 ABAC 式复杂条件。

Agent Profiles 页不新增公共记忆列表，只显示该 agent 的 identity scope 和 memory enabled。

### Orchestration

Orchestration 继续只调用：

```python
memory_runtime.recall(MemoryRecallRequest(actor=...))
memory_runtime.remember(MemoryRememberRequest(actor=...))
```

它不传公共 layer 列表。

## 施工清单

### M1. Domain / Application Contract

- [x] 新增 `MemoryLayerRef`、`MemoryResolvedLayer`、`MemoryAccessPlan`。
- [x] 扩展 `MemoryRecallItem` source fields。
- [x] 扩展 `MemoryRecallResult`，包含 `access_plan` 或 `searched_layers`。
- [x] 扩展 `MemoryRememberRequest`，支持可选 explicit target layer。
- [x] 更新 `MemoryEngine` protocol，收口为 layer-aware recall/remember。
- [x] 删除或改造旧单 scope helper，避免 runtime 双轨。

### M2. Access Plan Resolver

- [x] 新增 access plan resolver 逻辑。
- [x] 私有 layer 从 actor identity scope 解析，不存在时由 MemorySpaceService 创建。
- [x] shared/project/team/system layer 从 MemorySpace owner_kind 发现。
- [x] 用 policy/metadata 决定公共 layer 是否参与 default recall。
- [x] 实现 deny-wins 和 min cap policy 组合。
- [x] 增加不同 agent private scope 隔离测试。

### M3. Runtime Service

- [x] `MemoryRuntimeService.resolve_scope` 改为 `resolve_access_plan`。
- [x] `recall` 使用 access plan 的 readable layers。
- [x] `remember` 默认写 default private layer。
- [x] explicit shared remember 需要 writable layer gate。
- [x] 错误返回保持清晰：scope missing、recall disabled、remember disabled、target not writable。

### M4. File Markdown Engine

- [x] 支持 multi-layer query recall。
- [x] 支持 citation recall 时根据 citation source scope 精确读取。
- [x] 每个 hit 标注 `source_scope_ref` / `source_layer_kind`。
- [x] 多 layer 结果合并后统一排序、去重、截断。
- [x] remember 仍写目标 layer 的 daily file。

### M5. API / Frontend

- [x] 更新 `/memory/runtime/recall` response schema。
- [x] 更新 `/memory/runtime/remember` request/response schema。
- [x] Settings Runtime Test 显示 searched layers。
- [x] Recall result 表示命中来源，避免用户误判“没搜到”还是“搜错 scope”。
- [x] Memory policy 编辑 UI 改为 read/write gates、default recall、max items。
- [x] 所有新增文案进入 i18n。

### M6. Orchestration / Tool Integration

- [x] Orchestration memory recall 只传 actor context。
- [x] Memory tools 只从 `ToolExecutionContext` 取 agent/run/session，不接受模型传入 agent id。
- [x] Memory write tool 默认写 actor private layer。
- [x] 如需公共写入，工具参数必须显式 target，并由 Memory runtime gate。

### M7. Tests

- [x] `agent_a` recall 返回 `agent_a private + common`。
- [x] `agent_b` recall 不返回 `agent_a private`。
- [x] common recall disabled 时不进入 searched layers。
- [x] common remember disabled 时 explicit shared remember 返回 409。
- [x] agent/global max cap 按 min cap 生效。
- [x] file_markdown multi-layer recall 保留 citation/source 信息。
- [x] HTTP runtime recall/remember 覆盖成功和拒绝路径。
- [x] 前端 typecheck/build 通过。

### M8. Cleanup

- [x] 清理旧 `effective_policy_for_scope` 单 scope 语义或改为私有 helper。
- [x] 清理文档中“agent 绑定公共 scope 列表”的表述。
- [x] 更新 `docs/README.md`。
- [x] 更新 Settings 页面说明，明确公共记忆由 Memory 管理，不由 Agent Profile 管理。

## 验收场景

### 私有 + 公共召回

1. `assistant` 有私有记忆：`用户生日是 5 月 1 日`。
2. `common` 有公共记忆：`公司假期规则`。
3. `assistant` recall `生日 假期`。
4. 返回结果包含 assistant private 和 common shared。
5. 结果项能显示来源 layer。

### 私有隔离

1. `assistant` 写入私有生日记忆。
2. `lazy` recall `生日`。
3. `lazy` 不应看到 `assistant` 私有记忆。
4. `lazy` 可以看到 common 记忆。

### 公共写入受控

1. common recall enabled、remember disabled。
2. `assistant` 默认 remember 写入 assistant private。
3. `assistant` explicit remember target common 返回 409。
4. 开启 common write policy 后 explicit remember target common 成功。

## 代码落点

- `src/crxzipple/modules/memory/domain/*`
- `src/crxzipple/modules/memory/application/runtime.py`
- `src/crxzipple/modules/memory/application/policies.py`
- `src/crxzipple/modules/memory/application/spaces.py`
- `src/crxzipple/modules/memory/infrastructure/engines/file_markdown.py`
- `src/crxzipple/modules/memory/interfaces/http.py`
- `src/crxzipple/modules/orchestration/application/memory_context.py`
- `tools/*memory*` 或当前 memory tool source
- `frontend/src/pages/settings/modules/MemoryConfigSettingsPage.vue`
- `frontend/src/pages/settings/ownerApis/memory.ts`
- `frontend/src/shared/i18n/messages/*.ts`
- `tests/unit/test_memory_*.py`

## 送审口径

本轮升级完成后，Memory 的对外语义应是：

> Agent 只声明自己的 memory identity；Memory runtime 决定它当前能读取哪些 layer、
> 默认写到哪里、是否允许写公共记忆。Engine 只执行已授权的 recall/remember。

这能解决“生日记忆搜不到是因为搜错 scope”这类问题，同时不把 Agent Profile
变成公共记忆授权表，也不让 Orchestration 或前端承担 memory 拼接逻辑。
