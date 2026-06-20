# Browser Tool Source Contract Convergence Plan 2026-06-10

本文是 Browser agent-facing tool source 扶正施工入口。目标是把当前
`configured.browser` 手写动态 source 收敛为标准 bundled local package source，
让 Browser 和 `workspace`、`command`、`context_tree` 等工具一样走统一
`tools/<namespace>/tool.yaml` contract。

本轮不接受兼容双轨，不保留 alias，不做 `configured.browser` 与
`bundled.local_package.browser` 并存。迁移完成后，Browser agent-facing 工具真相只能来自
`tools/browser/tool.yaml`。

## 背景

当前 Browser 能力已经进入 Tool catalog 和 Context Tree：

```text
app/assembly/tool_sources/browser.py
  -> ToolSourceCatalogRecord(source_id="configured.browser")
  -> ToolFunctionCandidate(function_id="browser.*")
  -> Tool catalog
  -> Context Tree tools.available
  -> provider schema mirror
```

这条链路能运行，也没有绕过 Tool catalog。但是它绕开了 bundled tool package authoring
contract：

- Browser prompt groups、default schema policy、evidence path ladder 写在 Python dict。
- Browser function catalog 由 app assembly 手写 candidate 生成。
- Source id 是 `configured.browser`，和其他 bundled local package source 不一致。
- Tool package manifest 的校验、diff、review、source authoring 规则不能完整覆盖 Browser。
- 后续 Settings / Operations / plugin / package governance 会继续把 Browser 当特例。

本轮判断：这是历史重构中合理过渡，但现在 Tool runtime requirement 已经成熟，Browser 应回到
标准 Tool Source contract。

## 已确认的实现基础

当前代码已经具备 Browser 作为 local package 的必要底座：

- `ToolFunctionRequirements.runtime_requirement_sets` 已存在。
- `ToolSourceCatalogRecord.runtime_requirements` 已存在。
- `ToolSpec.runtime_requirement_sets` 已存在。
- `tools/*/tool.yaml` manifest parser 已读取 function 级
  `runtime_requirement_sets`。
- package dependencies / external requirements 会形成 source 级
  `runtime_requirements`。
- source 级 runtime requirements 会下沉到 function readiness。
- `ToolRuntimePoolService` 构建可用工具池时会检查 runtime readiness。
- `ToolSubmissionService` 执行前会再次检查 runtime readiness。
- `DaemonServiceToolRuntimeReadinessAdapter` 已支持：
  - `browser-profile-runtime`
  - `daemon-group:*`
  - `daemon:*`
  - `cli:*`
- 当前 Browser dynamic source 本身已经声明：
  - source runtime requirement: `browser-profile-runtime`
  - function runtime requirement sets: `(("browser-profile-runtime",),)`

因此，“Browser 需要 daemon-managed browser runtime”不再是保留
`configured.browser` 手写 source 的充分理由。

## 目标状态

目标调用链：

```text
tools/browser/tool.yaml
  -> bundled.local_package.browser
  -> ToolPackageDiscoveryAdapter
  -> ToolSourceCatalogRecord / ToolFunctionCandidate
  -> Tool catalog
  -> Context Workspace tool nodes
  -> provider mirror
```

Browser runtime 真相仍归 owner modules：

```text
modules/browser
  profile / pool / target / page action / network / script / storage / evidence

modules/daemon
  browser service spec / instance / readiness / supervision

modules/tool
  source catalog / function catalog / tool run lifecycle / runtime readiness gate

modules/context_workspace
  tree node state / expand-collapse / schema_enabled / render snapshot
```

## 非目标

- 不修改 Browser profile / pool / daemon / CDP owner 边界。
- 不把 Browser runtime truth 放进 Tool 或 Context Workspace。
- 不恢复 per-profile Tool Source。
- 不恢复 Browser MCP per-profile source。
- 不保留 `configured.browser` alias。
- 不新增 `if configured.browser else bundled.local_package.browser` 长期分支。
- 不用 provider adapter hidden prompt 弥补迁移。
- 不把 Browser raw CDP / raw DOM / raw network body 默认塞进 prompt。

## Source ID 收口

迁移完成后的唯一 Browser source id：

```text
bundled.local_package.browser
```

必须删除：

```text
configured.browser
```

所有引用同步迁移：

- Context Tree node ids:
  - `tools.bundle.configured.browser`
  - `tools.group.configured.browser.*`
- prompt bootstrap policy examples and tests.
- route audit / Workbench / Trace browser source diagnostics.
- Operations / read model labels if they key by source id.
- docs and report examples.

不允许把两个 source id 同时注册到 catalog。

## Manifest 目标结构

新增：

```text
tools/browser/tool.yaml
```

建议结构：

```yaml
kind: local_package
namespace: browser

prompt:
  title: Browser Automation
  summary: Use the Browser for verifiable browser evidence, not just DOM snapshots.
  evidence_path_ladder:
    # from modules/browser/application/evidence_paths.py or generated at package build time
  default_tool_schema_policy:
    priority: 20
  default_tool_schema_group_refs:
    - source_id: bundled.local_package.browser
      group_key: navigation
      reason: browser_starter_navigation
      priority: 10
    - source_id: bundled.local_package.browser
      group_key: observation
      reason: browser_starter_observation
      priority: 20
    - source_id: bundled.local_package.browser
      group_key: code_insight
      reason: browser_engineering_investigation
      priority: 30
    - source_id: bundled.local_package.browser
      group_key: network
      reason: browser_network_truth
      priority: 40
  groups:
    navigation:
      order: 10
      title: Navigation & Tabs
      summary: Open pages and recover tabs; tabs.list is for ambiguity, not repeated preflight.
      function_ids:
        - browser.navigate
        - browser.tabs.list
        - browser.tabs.select
        - browser.tabs.close
      default_tool_schema_ids:
        - browser.navigate
      default_tool_schema_max_count: 1
      default_tool_schema_source: bundled.local_package.browser.prompt_group.navigation

dependencies:
  - id: browser-profile-runtime
    kind: external_requirement
    description: Requires a daemon-managed Browser runtime.
  - id: browser_tool_application
    kind: service_dependency
    description: Browser application service for page actions.
  - id: browser_observation_service
    kind: service_dependency
    description: Browser observation service for combined state inspection.

local_tools:
  - id: browser.navigate
    name: Browser Navigate
    description: Navigate the managed browser target to a URL.
    provider_name: local_system
    entrypoint: tools.browser.local:browser_navigate
    tool_kind: function
    runtime_requirement_sets:
      - [browser-profile-runtime]
    context_requirements:
      - session_key
      - agent_id
    supported_modes: [inline]
    supported_strategies: [async]
    supported_environments: [local]
    runtime_key: browser.navigate
```

说明：

- `browser-profile-runtime` 必须是 manifest dependency 和 function runtime requirement。
- `context_requirements` 至少保留 `session_key`；需要 agent identity 的工具保留
  `agent_id`。
- prompt group metadata 进入 manifest，不再由 app assembly Python dict 生产。
- function schema 参数应来自 manifest；复杂 JSON schema 如当前 Python catalog 已有结构，
  可先机械迁移，后续再瘦身。

## Handler 与依赖

已有 handler / wrapper 应继续复用：

```text
tools/browser/local.py
src/crxzipple/app/assembly/tool_handlers/browser.py
modules/browser/application/*
modules/browser/infrastructure/*
```

收口规则：

- `tools/browser/local.py` 是 local package handler entrypoint。
- Handler factory 只能接收 manifest 声明的 dependency object。
- Handler 不查 container，不直接读 app assembly。
- Browser owner service 继续执行 profile / target / CDP / network / script / storage 逻辑。
- Tool handler 只做参数归一、调用 owner service、结果 envelope / formatting。

## 施工计划

### Phase 1. 固化当前 Browser Source Surface

- [x] 导出现有 `configured.browser` 的 prompt metadata、group metadata、function catalog。
- [x] 形成迁移对照表：
  - function id
  - runtime key
  - handler entrypoint
  - parameters / JSON schema
  - effects
  - context requirements
  - runtime requirement sets
  - execution policy / support
  - capability ids
  - prompt group
- [x] 确认当前 `browser_function_catalog_candidates()` 中每个 function 都能在 manifest 中表达。
- [x] 明确不进入 manifest 的内部/debug 能力，例如 raw CDP 逃生口。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_app_assembly_targets.py::test_browser_function_catalog_uses_profile_context_not_profile_ids
```

该阶段只读/整理，不改 runtime。

### Phase 2. 新增 `tools/browser/tool.yaml`

- [x] 新增 `tools/browser/tool.yaml`。
- [x] 迁移 Browser prompt metadata：
  - title / summary
  - evidence_path_ladder
  - default_tool_schema_policy
  - default_tool_schema_group_refs
  - groups
  - default_tool_schema_ids / max_count / source
- [x] 迁移 Browser function declarations。
- [x] 声明 package dependencies：
  - `browser-profile-runtime` external requirement
  - Browser application / observation / profile / capability dependencies
  - artifact service dependency where needed
- [x] 每个 function 声明 `runtime_requirement_sets: [[browser-profile-runtime]]`。
- [x] 每个 function 声明必要 `context_requirements`。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_tool_capabilities.py tests/unit/test_tool_providers.py
```

### Phase 3. 迁移 Browser Handler Registration

- [x] 让 Browser handlers 通过 package activation 注册。
- [x] `src/crxzipple/app/assembly/tool_handlers/browser.py` 只保留 handler factory / dependency wiring，
  不再生产 source/function catalog。
- [x] `tools/browser/local.py` 作为 manifest entrypoint 的唯一 handler surface。
- [x] 删除 app assembly 中 Browser function candidate generation 对 Tool catalog 的写入路径。

禁止：

- 不允许 `configured.browser` 与 `bundled.local_package.browser` 同时注册。
- 不允许为了测试保留旧 function candidate generator。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_tool_providers.py tests/unit/test_app_assembly_module_local.py
```

### Phase 4. 删除 `configured.browser` Source

- [x] 删除 `src/crxzipple/app/assembly/tool_sources/browser.py` 中
  `ToolSourceCatalogRecord(source_id="configured.browser")` 生产逻辑。
- [x] 删除 browser-specific source refresh activation task。
- [x] 从 assembly target 计划中移除 `configured.browser` source expectations。
- [x] 确认 catalog 只出现 `bundled.local_package.browser`。
- [x] 更新 tests：
  - `test_app_assembly_targets.py`
  - `test_context_workspace_tool_adapter.py`
  - `test_context_provider_mirror.py`
  - Browser prompt surface tests

验收：

```bash
PYTHONPATH=src pytest -q \
  tests/unit/test_app_assembly_targets.py \
  tests/unit/test_app_assembly_module_local.py \
  tests/unit/test_context_workspace_tool_adapter.py \
  tests/unit/test_context_provider_mirror.py
```

### Phase 5. 更新 Prompt Bootstrap 与 Context Tree 引用

- [x] 将默认 Browser group refs 从 `configured.browser` 改为
  `bundled.local_package.browser`。
- [x] 更新 Context Tree node expectations：
  - `tools.bundle.bundled.local_package.browser`
  - `tools.group.bundled.local_package.browser.network`
  - `tools.group.bundled.local_package.browser.code_insight`
- [x] 更新 route audit / prompt preview diagnostics 中的 browser source id。
- [x] 更新 Workbench / Trace / Operations browser investigation display。
- [x] 确认 schema mirror budget 仍保留：
  - context_tree controls 优先
  - Browser starter group schemas
  - skipped reason / group refs / priorities

验收：

```bash
PYTHONPATH=src pytest -q \
  tests/unit/test_context_workspace_tree_service.py \
  tests/unit/test_context_tree_tool.py \
  tests/unit/test_orchestration_context_workspace_snapshot.py \
  tests/unit/test_orchestration_runtime_llm_request_builder.py \
  tests/unit/test_turn_submission_prompt_bootstrap.py
```

前端受影响时：

```bash
cd frontend
npm run typecheck
npm run build
```

### Phase 6. Persistence / Existing Catalog Cleanup

不保留双路，但本地开发和用户数据库可能已有 `configured.browser` rows。迁移必须显式清理：

- [x] 新增 Alembic data migration：
  - 删除或标记 `configured.browser` source row。
  - 删除或标记 source_id 为 `configured.browser` 的 browser function rows。
  - 不把旧 row alias 到新 source。
  - 新 source/function rows 由 bundled package sync 重新生成。
- [x] 确保 stale `ContextNode` 中的 `tools.bundle.configured.browser` 不会继续参与 render。
  推荐方式：
  - Context Workspace owner refresh 用新 owner seed revision 覆盖 visible tool nodes。
  - 对旧 browser node ids 做 prune/orphan cleanup。
- [x] Operations / prompt preview 读取旧历史 snapshot 时保持历史可读，但不参与新 render。

验收：

```bash
source scripts/dev/infra-env.sh
PYTHONPATH=src python -m crxzipple.main db upgrade head

APP_DATABASE_URL="sqlite:////tmp/crxzipple-browser-source-convergence-$RANDOM.db" \
  PYTHONPATH=src python -m crxzipple.main db upgrade head
```

### Phase 7. 文档收口

- [x] 更新 `tools/README.md`，把 `browser` 加入 bundled namespace notes。
- [x] 更新 `docs/README.md`，本文作为当前 Browser Tool Source 施工入口。
- [x] 更新 `docs/agents/hosted-agent-operating-contract.md`：
  - 不再说默认 Browser Tool Source 是 `configured.browser`。
  - 明确 Browser 是 bundled local package source + browser runtime requirement。
- [x] 更新历史报告中仍作为当前施工依据的 `configured.browser` 表述。
- [x] 保留 archive / historical report 原文，只在当前 docs 里说明 superseded。

## 删除清单

完成后仓库中不应再有：

```text
ToolSourceCatalogRecord(source_id="configured.browser")
_BROWSER_SOURCE_ID = "configured.browser"
tools.bundle.configured.browser
tools.group.configured.browser.*
default_tool_schema_source: configured.browser.*
configured.mcp.browser_{profile}
```

允许历史文档、迁移注释、旧 snapshot fixture 中出现，但不能作为当前 runtime 代码路径、
测试 expectation 或 docs 当前约束。

## 风险

### Source ID 变更风险

Context Tree node id、prompt bootstrap policy、Operations diagnostics 可能直接依赖
`configured.browser`。本轮不做 alias，因此必须一次性同步更新引用。

控制方式：

- 用 `rg "configured.browser|tools.bundle.configured.browser"` 做收口扫描。
- 新增架构测试禁止 runtime 代码重新引入 `configured.browser`。

### Handler dependency 风险

当前 app assembly 对 Browser dependencies 注入较多。迁入 manifest 后，handler factories
必须通过 declared dependencies 拿到服务。

控制方式：

- activation tests 覆盖缺依赖失败。
- 不允许 handler 查 container。

### Existing DB 风险

旧开发数据库会残留 `configured.browser` rows。不能靠双路兼容。

控制方式：

- data migration 显式删除旧 source/function rows。
- package sync 生成新 source/function rows。
- Context Workspace refresh/prune 清理旧 tool nodes。

### Prompt Surface 回归风险

Browser route audit 依赖 starter schemas。迁移 manifest 后要确保 network/code/runtime starter
仍然进入 provider mirror。

控制方式：

- 保留 browser route regression fixture。
- prompt preview / request metadata 校验：
  - visible browser groups。
  - default group refs。
  - mirrored browser schema names。
  - `browser_investigation_affordance_status=ok`。

## 最终验收命令

```bash
PYTHONPATH=src pytest -q \
  tests/unit/test_tool_capabilities.py \
  tests/unit/test_tool_providers.py \
  tests/unit/test_app_assembly_targets.py \
  tests/unit/test_app_assembly_module_local.py \
  tests/unit/test_context_workspace_tool_adapter.py \
  tests/unit/test_context_provider_mirror.py \
  tests/unit/test_context_workspace_tree_service.py \
  tests/unit/test_context_tree_tool.py \
  tests/unit/test_orchestration_context_workspace_snapshot.py \
  tests/unit/test_turn_submission_prompt_bootstrap.py \
  tests/unit/test_browser_tool_application.py \
  tests/unit/test_browser_observation.py \
  tests/unit/test_browser_evidence_metadata.py

cd frontend
npm run typecheck
npm run build
```

## 完成定义

- Browser agent-facing tool source 只来自 `tools/browser/tool.yaml`。
- Tool catalog 中 Browser source id 只剩 `bundled.local_package.browser`。
- Browser functions 的 runtime requirement 通过 manifest / catalog / readiness gate 表达。
- Context Tree 中 Browser bundle/group/function 由通用 ToolContextNodeProvider 生成。
- Provider mirror 仍能按 source/group policy 暴露 starter schemas。
- Workbench / Trace / Operations 能解释 Browser route surface 和 prompt budget。
- 没有 `configured.browser` runtime 路径、alias、compat branch 或双 source 注册。

## 2026-06-10 落地记录

- 已新增 `tools/browser/tool.yaml`，65 个 `browser.*` functions 由 bundled local package source
  `bundled.local_package.browser` 进入 Tool catalog。
- 已删除 Browser-specific app assembly source/handler 注册路径；`tool.register_browser_source_catalog`
  不再存在。
- 已将 Browser handler entrypoint 收为 `tools.browser.local:create_browser_manifest_handler`，
  由 manifest `tool_id` 分派到 Browser owner services。
- 已补 Tool package parser：prompt metadata passthrough、parameter `json_schema`、execution policy
  `supports_parallel/resource_scope/serial_group_key`、按 `factory_deps` 参数注入完整 factory context。
- 已新增 Alembic `0071_delete_configured_browser_tool_source`，硬删除旧
  `configured.browser` catalog rows、stale Context Workspace nodes 和 Operations projections。
- 已更新 prompt bootstrap、Context Tree tests、Operations read model、authorization source id、
  module lifecycle / tool engineering checklist。

验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_tool_capabilities.py tests/unit/test_tool_providers.py tests/unit/test_app_assembly_targets.py tests/unit/test_app_assembly_module_local.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_context_provider_mirror.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_turn_submission_prompt_bootstrap.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_operations_tool_read_model.py tests/unit/test_module_lifecycle_architecture.py

PYTHONPATH=src pytest -q tests/unit/test_browser_tool_source_migration.py

APP_DATABASE_URL="sqlite:////tmp/crxzipple-browser-source-convergence-$RANDOM.db" PYTHONPATH=src python -m crxzipple.main db upgrade head
```
