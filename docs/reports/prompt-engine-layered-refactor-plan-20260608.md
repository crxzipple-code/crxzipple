# Prompt Engine 分层重构开发方案

本文是 2026-06-08 后续 prompt engine 收口施工入口。目标不是在现有代码上继续补 patch，而是把已经形成的 Context Workspace / Context Tree 方向整理成清晰、低耦合、可维护的分层结构。

关联文档：

- [../context-workspace-prompt-tree-design.md](../context-workspace-prompt-tree-design.md)
- [../context-workspace-prompt-tree-development.md](../context-workspace-prompt-tree-development.md)
- [prompt-tree-budget-redundancy-remediation-plan-20260608.md](prompt-tree-budget-redundancy-remediation-plan-20260608.md)
- [context-workspace-tree-schema-convergence-plan-20260607.md](context-workspace-tree-schema-convergence-plan-20260607.md)
- [engineering-agent-runtime-upgrade-plan-20260607.md](engineering-agent-runtime-upgrade-plan-20260607.md)

## 核心判断

当前架构方向已经成立：

```text
Owner Modules
  session / tool / memory / skills / artifacts / agent / workspace
        ↓
Context Workspace
  Context Tree / node state / render snapshot / provider mirror / budget
        ↓
Orchestration
  run lifecycle / LLM-tool execution chain / dispatch continuation
        ↓
LLM
  provider request / stream / invocation persistence
```

但代码表达仍不够清晰：

- `RunPromptInput` 名字像旧 prompt 拼装器，但实际已经变成 run input collector 的输出。
- `ContextRenderService` 同时包含 root seed、owner child refresh、XML render、provider mirror、estimate、snapshot metadata，文件过重。
- `ContextWorkspacePromptSnapshotAdapter` 同时做 orchestration metadata 注入、tool schema bootstrap、artifact mirror、snapshot metadata 统计，职责偏胖。
- `engine.py` 仍有 provider request 组装细节，削弱 orchestration run 生命周期主线。

本轮重构要把这些职责拆开，让层级在代码结构上可见。

## 不可妥协约束

1. 不接受兼容双轨。
   - 不新增旧 `PromptAssembler` / `RunPromptInputBuilder` / orchestration 内部 prompt facade。
   - 不保留新旧两套 render path。
   - 不用 wrapper/shim 掩盖旧结构。

2. 不接受补丁式写法。
   - 不在大文件底部继续塞 helper。
   - 不用 metadata 临时字段绕过 domain/application 边界。
   - 不为了单个 browser/tool 场景增加 hidden prompt 或特殊 prompt pipeline。

3. Context Workspace 继续拥有 prompt 主体。
   - Context Tree 是 prompt body。
   - Orchestration 只通过 render snapshot 使用树，不直接拼 session/tool/skill/memory/artifact 文本。
   - Provider tools/images/files 是从树节点派生的 provider attachment mirror，不反过来成为 prompt 真相。

4. Owner module 继续拥有业务真相。
   - session/tool/memory/skills/artifacts/agent/workspace 不把 read model 交给 Context Workspace 持有。
   - Context Workspace 保存节点状态、handle、summary、owner_ref、estimate 和 render snapshot。
   - 深读 owner 内容必须走 owner application/query/tool，而不是 Context Tree 万能代理。

5. Direct transcript 只服务 provider protocol。
   - Direct transcript 保留是因为 provider tool-call/tool-result pairing 需要。
   - 它不是历史上下文治理入口。
   - 历史、证据、能力、skill、memory、artifact 的默认交付归 Context Tree。

## 目标代码层级

目标结构：

```text
src/crxzipple/modules/orchestration/application/
  prompt_input.py
    RunPromptInputCollector
    RunPromptInput
    ResolvedRunPromptInput

  provider_request.py
    ProviderPromptRequestBuilder
    insert_context_tree_message
    attach_context_artifacts
    apply_context_tool_schemas
    filter_resolved_tools_for_mirrored_schema

  engine.py
    only run lifecycle:
      ensure inbound message
      collect run prompt input
      record context render snapshot
      build provider request
      invoke llm
      execute tools / finish message

src/crxzipple/app/integration/context_workspace_orchestration/
  adapter.py
    ContextWorkspacePromptSnapshotAdapter

  run_workspace_metadata.py
    build_run_workspace_metadata
    build_execution_continuation_payload

  tool_schema_bootstrap.py
    resolve_default_tool_schema_metadata

  artifact_mirror.py
    build_artifact_content_blocks
    artifact_content_budget

  snapshot_metadata.py
    build_context_snapshot_metadata

src/crxzipple/modules/context_workspace/application/
  services.py
    ContextWorkspaceService
    ContextTreeService
    ContextRenderService as thin facade

  root_nodes.py
    default root node seeds
    runtime.contract / context.priority / context.tree_usage
    execution.current / session.current / capability roots

  rendering/
    pipeline.py
      ContextRenderPipeline

    xml_renderer.py
      render_context_tree
      render_node_xml

    provider_mirror.py
      mirror tool schemas
      mirror artifact candidates
      tool schema budget

    estimates.py
      rendered estimate
      node aggregate estimate
      top rendered nodes

    snapshot_metadata.py
      render snapshot metadata defaults
      budget metadata extraction
```

允许分阶段落地，但每个阶段完成后只能保留一条真实调用路径。

## 分层职责

### 1. Run Prompt Input 层

Owner：`orchestration/application/prompt_input.py`

职责：

- 读取 agent profile。
- 读取 active session direct transcript。
- 解析 LLM profile。
- 解析 skills catalog 的薄输入。
- 解析可用 tool set。
- 生成 `RunPromptInput`。

不允许：

- 渲染 Context Tree XML。
- 拼接 tool/memory/skill/artifact 历史文本。
- 决定 provider attachment mirror。

### 2. Context Workspace Runtime Adapter 层

Owner：`app/integration/context_workspace_orchestration/*`

职责：

- 把 `RunPromptInput` 和 `OrchestrationRun` 转成 Context Workspace metadata。
- ensure workspace。
- 触发 Context Render。
- 记录 render snapshot。
- 产出 `ContextRenderSnapshotRecord` 给 orchestration。

不允许：

- 自己渲染 XML。
- 直接读取 owner module 内部 repository。
- 写 provider 请求 messages。

### 3. Context Render Pipeline 层

Owner：`context_workspace/application/rendering/*`

职责：

- 刷新可见节点。
- 渲染 XML-like Context Tree。
- 计算 rendered estimate。
- 镜像 provider tool schemas。
- 镜像 artifact candidates。
- 生成 render report。

不允许：

- 知道 orchestration engine 的推进细节。
- 知道 LLM invocation 持久化细节。
- 为 browser、skill、memory 单独创建第二套 prompt 管线。

### 4. Provider Request Builder 层

Owner：`orchestration/application/provider_request.py`

职责：

- 把 Context Tree prompt body 插入 provider messages。
- 把 artifact content blocks 追加为 provider 要求的 message/content block。
- 用 mirrored schemas 替换 provider tool schema surface。
- 过滤 resolved tools，使实际可执行工具与 provider mirrored schemas 对齐。
- 生成 request metadata。

不允许：

- ensure workspace。
- 计算 Context Tree 节点。
- 生成 owner facts。

### 5. LLM 调用层

Owner：`orchestration/application/engine_llm_invoker.py` + `modules/llm`

职责：

- 按 provider API 调用。
- stream fallback。
- 记录 invocation。
- 按 provider 支持设置 tool choice 等 override。

不允许：

- 参与 Context Tree 预算治理。
- 解释 memory/skill/tool 语义。

## 生命周期目标

最终一次 normal turn 应表达为：

```text
OrchestrationEngine.advance_once
  ensure inbound session message
  collect RunPromptInput
  record ContextRenderSnapshot
    ensure ContextWorkspace
    refresh owner provider children
    render Context Tree XML
    mirror provider attachments
    persist snapshot
  build ProviderPromptRequest
    direct transcript protocol tail
    context tree system message
    artifact mirror message
    mirrored tool schemas
    request metadata
  invoke LLM
  if tool calls:
    append assistant/tool protocol facts
    execute tools
    record execution chain consumption
    continue run
  else:
    append final assistant message
    finish run
```

关键点：

- `ContextRenderSnapshot` 必须能复现 LLM 实际看到的 Context Tree。
- `LLM invocation.request_metadata` 必须引用 `context_render_snapshot_id`。
- `direct_transcript_sequence_range` / `llm_transcript_consumption` 继续用于判断 consumed frontier。
- 旧 tool results 默认不再线性进入 prompt；通过 collapsed node + evidence + refs 保留可追溯性。

## 施工计划

### Phase 1：命名收口，不改行为

- [x] 新增 `orchestration/application/prompt_input.py`。
- [x] `PromptSurface` 改名为 `RunPromptInput`。
- [x] `PromptInputCollector` 改名为 `RunPromptInputCollector`。
- [x] engine 内部 `_PromptSurface` 改名为 `_ResolvedRunPromptInput`。
- [x] metric `prompt_assemble` 改为 `prompt_input_collect`。
- [x] 删除旧名字导出；不保留长期 alias。
- [x] 更新测试命名和文档引用。
- [x] 架构守卫已固定旧 import path 退场：
  `orchestration/application/prompt_surface.py` 与旧单文件
  `app/integration/context_workspace_orchestration.py` 不允许返回；新 adapter 只能通过
  `app.integration.context_workspace_orchestration.adapter` 等 package 子模块引用。

验收：

- 行为不变。
- 代码里不再出现旧 `RunPromptInput` 作为公共模型名。
- 没有兼容 alias。

### Phase 2：Provider Request Builder 抽出

- [x] 新增 `orchestration/application/provider_request.py`。
- [x] 抽出 `_prompt_with_context_snapshot()`。
- [x] 抽出 context render report 注入。
- [x] 抽出 context tree system message 插入。
- [x] 抽出 artifact mirror message 追加。
- [x] 抽出 tool schema mirror 应用。
- [x] 抽出 resolved tools 过滤。
- [x] 抽出 request metadata builder。
- [x] `engine.py` 只调用 builder，不保留重复 helper。

验收：

- `engine.py` 只表达 run lifecycle。
- provider request 组装细节集中在一个文件。
- 现有 preview / real invoke 行为一致。

### Phase 3：Context Workspace Orchestration Adapter 拆包

- [x] 将 `app/integration/context_workspace_orchestration.py` 改为 package。
- [x] `adapter.py` 保留主流程。
- [x] `run_workspace_metadata.py` 收拢 workspace metadata / execution continuation payload。
- [x] `tool_schema_bootstrap.py` 收拢 default schema ids / group refs 解析。
- [x] `artifact_mirror.py` 收拢 artifact content block / budget 计算。
- [x] `snapshot_metadata.py` 收拢 snapshot metadata 统计。
- [x] 删除原单文件 helper 重复实现。

验收：

- Adapter 主流程不超过一屏能看清。
- Metadata、schema bootstrap、artifact mirror 互不穿透。
- 不新增旧 facade。

### Phase 4：Context Render Service 拆分

- [x] 新增 `context_workspace/application/root_nodes.py`。
- [x] 迁移默认 root node seed。
- [x] 新增 `context_workspace/application/rendering/xml_renderer.py`。
- [x] 迁移 Context Tree XML render。
- [x] 新增 `rendering/provider_mirror.py`。
- [x] 迁移 tool schema mirror、artifact candidate mirror、schema budget。
- [x] 新增 `rendering/estimates.py`。
- [x] 迁移 text/node/rendered estimate。
- [x] 新增 `rendering/snapshot_metadata.py`。
- [x] 迁移 render snapshot metadata defaults。
- [x] 新增 `rendering/pipeline.py`。
- [x] `ContextRenderService` 改为 thin facade。

验收：

- `services.py` 只保留 service 编排。
- root seed、XML、provider mirror、estimate 不再混在一个大文件。
- `ContextRenderService.render_prompt_body()` 的主流程清晰可读。

### Phase 5：Owner Provider 边界统一

- [x] 检查 `context_workspace_session.py` 是否只产出 session handles / current evidence / tool interaction nodes。
- [x] 检查 `context_workspace_tool.py` 是否只产出 source-first bundle/group/function nodes。
- [x] 检查 `context_workspace_artifacts.py` 是否只产出 artifact handles，不决定 provider message 结构。
- [x] 检查 `context_workspace_memory.py` 是否只产出 visible memory scope handles 和 recall/read hints。
- [x] 检查 `context_workspace_skills.py` 是否只产出 skill handles 和 `skill.md` 摘要。
- [x] 检查 `context_workspace_agent.py` 是否只产出 agent home handles。
- [x] 删除任何 owner provider 内部 provider-request 拼接逻辑。

验收：

- Owner provider 不知道 LLM provider 细节。
- Owner provider 不直接读取其他 owner module repository。
- Owner provider 只通过 owner application/query service。

### Phase 6：预算治理 API 固化

- [x] 将预算 metadata 统一归口到 render snapshot metadata。
- [x] 新增 `shared/context_render_budget.py` 作为跨模块预算字段契约，避免 orchestration 反向依赖 Context Workspace。
- [x] 固定字段：
  - `rendered_prompt_estimated_tokens`
  - `direct_transcript_estimated_tokens`
  - `mirrored_tool_schema_estimated_tokens`
  - `artifact_content_estimated_tokens`
  - `estimated_provider_prompt_tokens`
  - `tool_schema_mirror_budget_status`
  - `artifact_content_budget`
  - `top_rendered_nodes`
- [x] Workbench / Trace / Operations 只读 snapshot metadata，不重算。
- [x] 移除 provider request 内重复预算字段拼接路径。

验收：

- 同一次 invocation 在 Workbench、Trace、Operations 看到同一份预算事实。
- 大 browser/tool 结果不会绕过预算进入 prompt。

## 测试计划

新增或重组测试：

- [x] `tests/unit/test_prompt_input_collector.py`
- [x] `tests/unit/test_orchestration_provider_request_builder.py`
- [x] `tests/unit/test_context_workspace_root_nodes.py`
- [x] `tests/unit/test_context_render_xml_renderer.py`
- [x] `tests/unit/test_context_provider_mirror.py`
- [x] `tests/unit/test_context_snapshot_metadata.py`

保留并迁移现有回归：

- [x] `tests/unit/test_context_workspace_session_adapter.py`
- [x] `tests/unit/test_context_workspace_tree_service.py`
- [x] `tests/unit/test_orchestration_context_workspace_snapshot.py`
- [x] `tests/unit/test_turns_http.py`
- [x] `tests/unit/test_orchestration_context.py`
- [x] `tests/unit/test_operations_llm_read_model.py`
- [x] `tests/unit/test_app_assembly_targets.py`
- [x] `tests/unit/test_app_assembly_module_local.py`

推荐阶段验证命令：

```bash
PYTHONPATH=src pytest -q \
  tests/unit/test_context_workspace_tree_service.py \
  tests/unit/test_context_workspace_session_adapter.py \
  tests/unit/test_orchestration_context_workspace_snapshot.py \
  tests/unit/test_turns_http.py \
  tests/unit/test_orchestration_context.py \
  tests/unit/test_operations_llm_read_model.py \
  tests/unit/test_app_assembly_targets.py \
  tests/unit/test_app_assembly_module_local.py
```

前端受影响时追加：

```bash
cd frontend
npm run typecheck
npm run build
```

## 删除与禁止项

施工完成后必须检查并删除：

- [x] 旧公共 `PromptSurface` 命名。
- [x] Context render 相关的重复 helper。
- [x] Adapter package 拆分后的旧单文件导出残留。
- [x] Engine 内 provider message 拼接 helper。
- [x] 任何 browser-specific hidden prompt。
- [x] 任何 `if old_path else new_path` 的长期兼容分支。
- [x] 任何为了测试保留的旧 shim。

说明：以上删除项按本轮 prompt engine / Context Workspace / orchestration
scope 扫描验收，不代表整个仓库历史词汇已全部清空。

明确禁止：

- 不允许用 re-export 维持旧 import path。
- 不允许新增 "legacy" 命名模块。
- 不允许用 `metadata["compat_*"]` 传递核心结构。
- 不允许让 frontend 或 Operations 反向推断 prompt 预算。

## 验收标准

1. 读 `engine.py` 能只看到 orchestration 生命周期，不会被 prompt render 细节打断。
2. 读 `prompt_input.py` 能只看到 run 输入收集，不会看到 XML / provider attachment。
3. 读 `context_workspace/application/rendering/*` 能完整理解树如何渲染、预算如何计算、provider mirror 如何产生。
4. 读 `app/integration/context_workspace_orchestration/*` 能理解 orchestration 如何接入 Context Workspace。
5. 只有一条真实 prompt render path。
6. LLM invocation 可通过 `context_render_snapshot_id` 追溯实际 prompt body。
7. Tool schema / artifact / direct transcript 的预算可观测、可复现。
8. 没有兼容双轨、没有补丁式 helper 堆积、没有 owner module 越界。

## 完成定义

本轮完成后，prompt engine 应该呈现为：

```text
RunPromptInputCollector
  -> ContextWorkspacePromptSnapshotAdapter
  -> ContextRenderPipeline
  -> ContextRenderSnapshot
  -> ProviderPromptRequestBuilder
  -> OrchestrationEngineLlmInvoker
```

每一层只知道下一层需要的稳定 port/model，不知道下一层内部实现。新的能力，例如 browser evidence、skill guidance、memory layer、artifact attachment，只能通过 owner provider 节点和 provider mirror 扩展，不能破坏这条主线。
