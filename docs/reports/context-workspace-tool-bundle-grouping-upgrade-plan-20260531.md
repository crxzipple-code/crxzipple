# Context Workspace Tool Bundle Grouping Upgrade Plan 2026-05-31

## 背景

当前 Context Workspace 的 `tools.available` 已经不再把所有 tool function 直接铺平给 LLM，而是先通过分组节点收束注意力，再由 agent 按需展开具体工具。

这一轮讨论已经形成共识：

- LLM 并不关心工具来自 local package、OpenAPI、MCP 还是其他 source。
- `capability_ids` 是 ABAC / governance / authorization 语义，不应该作为 prompt attention grouping 的主轴。
- 工具分类不追求精确知识目录，也不做长期维护成本很高的人工联想规则。
- 稳定分类应该来自 Tool Source 的自然边界：
  - 一个 `tools/<namespace>/tool.yaml` 是一个能力包。
  - 一个 OpenAPI source / spec 是一个能力包。
  - 一个 MCP server 是一个能力包。
- 能力包标题和摘要面向 LLM，必须表达业务能力，而不是暴露 `local_package`、`openapi`、`mcp` 这些工程来源。

因此后续目标是把 `tools.available` 从“关键词语义分组”升级为“Source-first Tool Bundle 分组”。

## 目标状态

`tools.available` 下默认只展示能力包节点：

```text
tools.available
  Context Tree Controls
    context_tree.list
    context_tree.expand
  Open-Meteo Weather
    open_meteo_weather.forecast
  Brave Search
    brave_search.web_search
    brave_search.news_search
  Browser Automation
    browser.navigate
    browser.snapshot
```

其中：

- `Context Tree Controls` 的边界来自 `bundled.local_package.context_tree`。
- `Open-Meteo Weather` 的边界来自一个 OpenAPI source。
- `Browser Automation` 的边界来自 `configured.browser`。
- MCP server 暴露的工具按该 MCP source 形成一个能力包。

LLM 首屏只看到：

- 能力包标题
- 能力包摘要
- function 数量
- credential/readiness/runtime requirement 摘要
- 风险和授权提示摘要

具体 tool function 只有在能力包展开后才进入可见 prompt tree，并且只有可见且 schema-enabled 的 `tool_function` 会镜像到 provider tool schema。

## 非目标

- 不按 `local/openapi/mcp` 作为 prompt-facing 分组名。
- 不用 `capability_ids` 进行 prompt 分组。
- 不做全局自动语义聚类，也不尝试把不同 source 的相似工具强行合并。
- 不从 CLI help 自动生成可信 tool function。本计划不改变 CLI 当前治理方向。
- 不恢复旧 `/tools/providers`、`/tools/discover` 或 runtime discovery fallback。

## 设计原则

### Source 是稳定边界，不是展示语义

Tool Source 决定能力包边界，但展示给 LLM 的标题和摘要来自 source 的 prompt metadata：

```yaml
prompt:
  title: Browser Automation
  summary: Operate browser profiles, tabs, pages, DOM snapshots, network traces, downloads, and diagnostics.
```

如果没有显式 `prompt`，则回退到：

1. `ToolSource.display_name`
2. `ToolSource.description`
3. source id 的可读化结果

### Tool Function 是展开后的执行叶子

Source bundle 节点不是 provider tool schema。只有展开后的 `tool_function` 节点才能被镜像到 LLM provider 的工具声明。

### 大 Source 可以声明二级 prompt groups

对超大 source，例如一个 MCP server 暴露 80 个工具，可以允许 source 自己声明二级分组：

```yaml
prompt:
  title: Browser Automation
  summary: Browser operation tools.
  groups:
    navigation:
      title: Navigation
      summary: Open pages, switch tabs, and wait for page state.
    inspection:
      title: Inspection
      summary: Read DOM snapshots, network state, console logs, and storage.
```

系统不靠关键词猜二级目录。没有声明时保持一层 source bundle。

### Governance metadata 保留但不参与注意力目录

Bundle 和 function 节点可以携带：

- `source_id`
- `source_kind`
- `capability_ids`
- `credential_requirements`
- `runtime_requirements`
- `required_effect_ids`

这些用于 Settings / Operations / Authorization / Access / debug，不用于 prompt grouping 命名。

## 数据模型升级

### ToolSourceCatalogRecord

建议在 `ToolSourceCatalogRecord.config` 中规范 prompt metadata：

```json
{
  "prompt": {
    "title": "Open-Meteo Weather",
    "summary": "Call weather and geocoding APIs for forecasts, current weather, and location lookup.",
    "groups": {}
  }
}
```

不新增独立表，避免把 prompt 展示配置拆成另一个真相源。Tool Source 仍是能力包治理入口。

### Local Package Manifest

`tools/*/tool.yaml` 支持：

```yaml
prompt:
  title: Context Tree Controls
  summary: Operate the prompt tree itself: list, expand, collapse, pin, estimate, recall memory, and mirror selected schemas.
```

解析后写入 `ToolSourceCatalogRecord.config.prompt`。

### OpenAPI Source

Bundled OpenAPI:

```yaml
kind: openapi
namespace: open_meteo_weather
prompt:
  title: Open-Meteo Weather
  summary: Forecast and current weather tools backed by Open-Meteo.
```

Configured OpenAPI:

- HTTP/API create/update source payload 支持 `config.prompt`。
- Settings UI 不要求用户编辑 JSON，应提供 title/summary 输入。

### MCP Source

Configured MCP:

- source config 支持 `provider.prompt` 或 `config.prompt`。
- 默认标题使用 provider name / description。
- 不把 `MCP` 显示为能力类别。

## Context Workspace 升级

### 当前临时状态

当前 `ToolContextNodeProvider` 已经把 `capability_group` 改为 `semantic_group`，并过滤 `mcp/openapi/cli/provider` 等来源词。但这仍然是关键词分组，属于过渡方案。

### 目标实现

`ToolContextNodeProvider` 应改为：

1. 从 `available_tool_names` 解析对应 active `ToolFunction` / `Tool`。
2. 按 `source_id` 聚合。
3. 查询 `ToolSource` 获取 bundle metadata。
4. 生成 `tool_bundle` 节点。
5. 展开 `tool_bundle` 时列出该 source 下 active function。
6. 如果 source 声明二级 `prompt.groups`，则先生成 `tool_bundle_group`，再展开 function。

建议节点 kind：

- `tool_bundle`
- `tool_bundle_group`
- `tool_function`
- `tool_cli_source` 保持 guide 语义，不作为 provider schema。

建议 owner_ref：

```json
{
  "source_id": "bundled.openapi.open_meteo_weather",
  "bundle_key": "bundled.openapi.open_meteo_weather",
  "function_count": 4
}
```

不再出现：

- `capability_group`
- source-kind prompt group，例如 `tools.group.openapi`

## Tool Application Surface 升级

当前 `ToolContextNodeProvider` 只拿 `ToolContextService.get_tool(tool_id)` 不够，因为 bundle grouping 需要 source metadata。

需要新增或扩展 query surface：

```python
class ToolPromptCatalogQuery(Protocol):
    def list_prompt_tools(self, tool_ids: tuple[str, ...]) -> tuple[ToolPromptFunction, ...]:
        ...

    def get_prompt_bundle(self, source_id: str) -> ToolPromptBundle | None:
        ...
```

建议应用模型：

```python
@dataclass(frozen=True)
class ToolPromptBundle:
    source_id: str
    title: str
    summary: str
    source_kind: str
    function_count: int
    credential_requirement_count: int
    runtime_requirement_count: int
    groups: tuple[ToolPromptBundleGroup, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)
```

Context Workspace 不应直接读 repository，也不应解析 source config 细节；它只消费 Tool module 提供的 prompt catalog query。

## Frontend 升级

Workbench context tree 的工具节点展示应遵循：

- `tools.available` 默认展示 bundle 节点。
- bundle 节点看起来像 DOM/XML 树的元素节点，不做卡片化。
- bundle 节点右侧/tooltip 显示 function count、credential count、runtime requirement。
- 只有展开 bundle 后才显示 function。
- function 的 `enable/disable schema` 继续放右键菜单，不遮挡 XML 行首折叠控件。

Settings Tool 页面可后续补：

- Source prompt title/summary 编辑。
- Source 内二级 group 配置，仅对大 source 开启。
- Source refresh 后预览 prompt bundle。

## 运行与权限

### ABAC

授权过滤发生在生成 `available_tool_names` 之前或 Tool query surface 内。不可见 function 不应进入 bundle function list。

如果某 bundle 中所有 function 都被过滤，则该 bundle 不显示。

### Access

Bundle 节点展示 credential readiness 摘要，但不暴露 secret。

OpenAPI/MCP/local package 的 credential requirement 仍由 Tool Function / Provider Backend 声明，Access 负责 binding/readiness。

### Provider Schema Mirror

只有满足以下条件的 function 会进入 provider attachments：

- 所属 bundle 已展开。
- function 节点可见。
- function 节点 `schema_enabled=True`。
- function 不是 `tool_cli_source` guide。

当前交互约定：bundle / group 展开后生成的 `tool_function` 节点默认
`schema_enabled=True`，因此“展开能力包”就是让该能力包内可见工具进入下一轮
provider schema mirror。`context_tree.disable_tool_schema` /
`context_tree.enable_tool_schema` 用于在已展开工具中临时收回或恢复单个 function
schema，而不是要求 agent 每次展开后再做一次二次启用。

## 迁移计划

### P1. Prompt Metadata Contract

- [x] 在 `tools/README.md` 补充 `prompt.title` / `prompt.summary` / `prompt.groups` authoring contract。
- [x] 在 `tool_packages.py` 解析 local/openapi manifest 的 `prompt` 字段。
- [x] configured OpenAPI/MCP source 继续通过通用 `config.prompt` / `config.provider.prompt` 持久化 prompt metadata。
- [x] 给现有 bundled sources 补齐 prompt metadata。

### P2. Tool Query Surface

- [x] 新增 Tool prompt catalog application model：`ToolPromptBundle`。
- [x] 新增 `ToolSourceQueryService.list_prompt_bundles(function_ids)`。
- [x] 该 query service 聚合 active/enabled `ToolFunction` 与 active owner `ToolSource`。
- [x] query service 只接收已授权可见的 function id 列表，Context Workspace 不解释权限规则。

### P3. Context Workspace Bundle Nodes

- [x] 把 `ToolContextNodeProvider` 从 keyword semantic grouping 改为 source bundle grouping。
- [x] 删除 `_GROUP_KEYWORDS`、`_SOURCE_KIND_TAGS`、`semantic_group` 关键词分组逻辑。
- [x] 新增 `tool_bundle` 节点生成；`tool_bundle_group` 留给 P4 source-level optional groups。
- [x] 保持 `tool_function` schema mirror 行为。
- [x] 保持 `tool_cli_source` guide 不进入 provider schema。

### P4. Source-Level Optional Groups

- [x] 实现 source prompt groups 数据结构：`ToolPromptBundleGroup`。
- [x] 支持 source `prompt.groups.<group>.function_ids` 显式声明二级目录。
- [x] 支持 source group `order`，避免稳定化 config 后 prompt 顺序退化为字母序。
- [x] 没有进入任何 group 的 function 保持在 bundle 默认区。
- [x] 不做系统关键词自动分类。
- [x] Browser `configured.browser` 已声明真实二级能力组，并覆盖全部 `browser.*` function。

### P5. Frontend Tree Rendering

- [x] Workbench context tree 的通用 XML/DOM 树行渲染覆盖 `tool_bundle` 和 `tool_bundle_group`。
- [x] bundle 展开后先显示 groups / 未分组 functions；group 展开后再显示 functions。
- [x] bundle / group metadata summary 已由 backend node metadata 提供。
- [x] 右键菜单与折叠箭头沿用当前 XML line renderer，不引入内联操作遮挡。

### P6. Tests

- [x] 单测：一个 local package source 生成一个 bundle。
- [x] 单测：一个 OpenAPI source 生成一个 bundle，标题来自 prompt metadata。
- [x] 单测：一个 MCP source 生成一个 bundle，标题不显示 MCP source kind。
- [x] 单测：同类不同 source 不自动合并。
- [x] 单测：bundle 未展开时 provider schema mirror 为空。
- [x] 单测：bundle 展开后仅 visible/schema-enabled functions 进入 provider schema mirror。
- [x] 单测：capability ids 保留为 metadata，但不参与 grouping。
- [x] 单测：source 全部 function 不可见时 bundle 不显示。
- [x] 单测：source prompt groups 展开后再披露 function。
- [x] 单测：Browser prompt groups 覆盖全部 `browser.*` function，且 query service 按 `order` 输出。

### P7. Cutover

- [x] 删除过渡 keyword semantic grouping。
- [x] 更新 docs/context-workspace-prompt-tree-development.md。
- [x] 更新 docs/README.md 当前施工入口。
- [x] 跑相关单测。
- [x] 跑 frontend typecheck。
- [x] 重启 dev app 验证 Workbench context tree 可加载到新代码。

## 验收标准

- `tools.available` 下不直接铺 100+ function。
- `tools.available` 下不出现 `OpenAPI`、`MCP`、`Local Package` 这类工程来源分组。
- 一个 source 默认就是一个 prompt-facing ability bundle。
- Bundle 标题/摘要稳定来自 source prompt metadata，不靠关键词猜测。
- ABAC/access/runtime metadata 保留，但不污染 prompt grouping。
- Provider schema mirror 仍由上下文树可见性控制。
- CLI source 保持 guide，不自动转可信 provider tool function。
- 展开 bundle / group 后可见 `tool_function` 默认进入 provider schema mirror；
  对单个 function 的收回和恢复使用 `disable_tool_schema` /
  `enable_tool_schema`。

## 风险

- 现有 `ToolContextNodeProvider` 只有 `get_tool(tool_id)`，需要扩展 Tool query surface，否则会诱导 Context Workspace 直接读 Tool repository。
- OpenAPI/MCP configured source 的 UI 如果继续暴露 JSON，会降低可用性；Settings 应提供表单编辑 prompt metadata。
- 大 MCP source 如果没有 source-level groups，展开后仍可能很长；但这是 source owner 的 authoring 问题，不应由系统关键词兜底。
