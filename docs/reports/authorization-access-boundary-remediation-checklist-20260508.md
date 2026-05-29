# Authorization / Access Boundary Remediation Checklist 2026-05-08

本文档是 2026-05-08 之后处理内部授权与外部访问治理边界的权威任务清单。它取代
`docs/archive/reports/access-governance-redesign-checklist-20260506.md` 中关于
“Access owns authorization policy / temporary grant”的阶段性判断，也取代
`docs/archive/reports/settings-integration-dev-checklist-20260506.md` 中把 authorization policy 归入
Access Settings config 的旧口径。

## 结论

Authorization 和 Access 是两套不同边界：

- `authorization` 模块负责内部 ABAC 授权：subject、resource、context、action、effect、
  policy、run/session/agent grant、approval 后的内部权限放行。
- `access` 模块负责外部访问治理：GitHub、Gmail、Hugging Face、Codex、OpenAI 等外部
  provider/account/credential 的创建、绑定、租用、停用、注销、readiness、统计和审计。
- `orchestration` 可以同时注入 `AuthorizationPort` 和 `AccessReadinessPort`，但两个 port
  语义必须分离：内部授权失败是 authorization/approval 问题，外部凭证未就绪是
  `access_not_ready`。
- Settings 可以提供统一治理视图和 action shell，但不能把 ABAC policy 写进 Access，也不能把
  外部 credential 真相写进 Authorization。

当前代码存在真实责任混淆：

- `access` 模块包含 `AccessAuthorizationPolicyRecord`、`access_authorization_policies`、
  `AccessBackedAuthorizationPolicyRepository` 和 ABAC dry-run/evaluator adapter。
- `access` 模块包含用于内部 approval 的 `access_temporary_grants`。
- `container` 通过 Access-backed repository 装配 `AuthorizationApplicationService`。
- `AccessSettingsActionAdapter` 仍暴露 `create/update/enable/disable_authorization_policy`
  这类内部 ABAC policy 写动作。

整改目标是不保留长期兼容逻辑：内部 ABAC policy/grant 迁回 Authorization；Access 只保留外部
访问治理资源。

## P0. 边界约束

- [x] 明确 `authorization` = internal ABAC runtime and governance。
- [x] 明确 `access` = external provider/account/credential governance。
- [x] 在 agent operating contract 中禁止 Access import `modules.authorization.*`。
- [x] 在 agent operating contract 中禁止 Authorization runtime 使用 Access-backed repository。
- [x] 更新旧报告，标记 Access-owned authorization policy / temporary grant 判断已废弃。
- [x] 新增架构扫描测试，防止后续回归。

验收：

```bash
rg -n 'AccessBackedAuthorization|access_authorization_policies|access_temporary_grants|create_authorization_policy' \
  src/crxzipple/modules/access src/crxzipple/bootstrap
rg -n 'modules.authorization|AbacAuthorizationEvaluator|AuthorizationPolicy' src/crxzipple/modules/access
```

## P1. Authorization 接回 policy / grant 持久化

- [x] 在 `modules/authorization` 下新增 SQLAlchemy policy model/repository。
- [x] 使用或恢复 `authorization_temporary_grants` 作为 run/session/agent grant 真相表。
- [x] 新增 `SqlAlchemyAuthorizationPolicyRepository`。
- [x] 新增 `SqlAlchemyTemporaryAuthorizationGrantRepository`。
- [x] 将 `AuthorizationApplicationService` 的 `policy_repository` 和
  `temporary_grant_repository_factory` 装配到 Authorization-owned repository。
- [x] YAML policy 只作为 Authorization bootstrap import 输入，不经过 Access。
- [x] `grant_agent_effect_authorization` / `grant_agent_tool_authorization` 写入
  Authorization-owned policy repository。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_authorization.py
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/authorization
```

## P2. 数据迁移

- [x] 新增 Alembic migration，创建 `authorization_policies`。
- [x] 从 `access_authorization_policies` 一次性迁移内部 ABAC policy 到 `authorization_policies`。
- [x] 从 `access_temporary_grants` 一次性迁移内部 approval grant 到
  `authorization_temporary_grants`。
- [x] 迁移完成后删除 `access_authorization_policies`。
- [x] 迁移完成后删除内部 authorization 用途的 `access_temporary_grants`。
- [x] 不做 runtime 双读；旧 Access 表只允许 migration 读取。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_authorization.py tests/unit/test_access_persistence.py
rg -n 'access_authorization_policies|access_temporary_grants' alembic/versions src/crxzipple \
  | rg -v 'migration|legacy|remediation'
```

## P3. Access 去 ABAC 化

- [x] 删除或迁出 `src/crxzipple/modules/access/application/authorization_repository.py`。
- [x] 删除或迁出 `src/crxzipple/modules/access/application/policies.py` 中对
  `AuthorizationPolicy` / `AbacAuthorizationEvaluator` 的依赖。
- [x] 从 Access domain 移除 `AUTHORIZATION_POLICY` 资源类型。
- [x] 从 Access domain 移除内部 `TEMPORARY_GRANT` 资源类型；若 Access 需要外部 provider lease，
  使用 `provider_lease` / `credential_lease` 命名。
- [x] 删除 `AccessResourceDefinition.authorization_policy` 字段，或改成外部访问语义的
  `provider_scope_policy`，不能复用内部 ABAC。
- [x] Access action 删除 `create/update/enable/disable/delete/import_authorization_policy*`
  intents。
- [x] Access query/read model 不再展示内部 ABAC policy。
- [x] Access setup/readiness/audit 继续保留外部访问治理职责。

验收：

```bash
rg -n 'AuthorizationPolicy|AbacAuthorizationEvaluator|authorization_policy|temporary_grant' \
  src/crxzipple/modules/access
PYTHONPATH=src pytest -q tests/unit/test_access_http.py tests/unit/test_access_actions.py tests/unit/test_access_persistence.py
```

## P4. Authorization governance API / Settings 接入

- [x] `/authorization/policies` 保留 list/check，并补齐 create/update/enable/disable/delete。
- [x] 补齐 import/export/dry-run/impact preview，但实现放在 Authorization 模块。
- [x] 如果 Settings UI 需要展示内部授权，只能通过 Authorization application/query port。
- [x] Agent-tool 授权业务视图通过 Agent + Tool + Authorization ports 编排，不直接写 Access。
- [x] 内部授权审计归 Authorization audit；外部凭证操作审计归 Access audit。

落地状态：

- Authorization 策略治理入口统一放在 `/authorization/policies` 下：`POST` 创建、
  `PUT /{policy_id}` 更新、`POST /{policy_id}/enable|disable` 启停、
  `DELETE /{policy_id}` 删除。
- 策略导入导出、干跑与影响预览分别为 `/authorization/policies/import`、
  `/authorization/policies/export`、`/authorization/policies/dry-run`、
  `/authorization/policies/impact`。
- 内部授权治理审计表为 `authorization_action_audits`，查询入口为
  `/authorization/audits`；policy CRUD/import/dry-run/impact preview 以及 run/session/agent
  authorization grant 都记录在 Authorization audit 中。Access audit 继续只记录外部
  provider/account/credential 操作。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_authorization.py tests/unit/test_auth_http.py
```

## P5. Orchestration 命名收口

- [x] `grant_run_access` 改为 `grant_run_authorization`。
- [x] `grant_session_access` 改为 `grant_session_authorization`。
- [x] `grant_agent_effect_access` 改为 `grant_agent_effect_authorization`。
- [x] `grant_agent_tool_access` 改为 `grant_agent_tool_authorization`。
- [x] `tool.access_tool` 改为内部授权语义名称，例如 `tool.visible` / `tool.authorize`。
- [x] `tool.access_effect` 改为 `tool.effect.authorize`。
- [x] `remote_tool_access` 改为 `remote_tool_execution`。
- [x] `sensitive_access` 改为 `sensitive_operation_confirmation`。
- [x] `access_not_ready` 只用于外部凭证/provider 未就绪。

验收：

```bash
rg -n 'grant_.*_access|tool\\.access_|remote_tool_access|sensitive_access' \
  src/crxzipple/modules/orchestration src/crxzipple/modules/authorization tests/unit
PYTHONPATH=src pytest -q tests/unit/test_orchestration_approval.py tests/unit/test_orchestration_tools.py
```

## P6. UI / 文案对齐

- [x] Access Operations/Settings 页面移除内部 ABAC policy 管理入口。
- [x] Access 页面聚焦 external provider/account/credential binding/setup session/lease/readiness/audit。
- [x] Workbench “missing access” 只表示外部访问未就绪。
- [x] 内部 ABAC deny / approval required 显示为 authorization 问题。
- [x] i18n 清理 `access authorization policy` 等混淆文案。

验收：

```bash
rg -n 'access.*authorization|authorization.*access|Access authorization policy' frontend/src
cd frontend && npm run typecheck
```

## P7. 架构扫描与回归测试

- [x] 新增 `tests/unit/test_authorization_access_boundary.py`。
- [x] 扫描 Access 不得引用 `crxzipple.modules.authorization`。
- [x] 扫描 bootstrap 不得引用 `AccessBackedAuthorization*`。
- [x] 扫描 Access action 不得暴露内部 ABAC policy intents。
- [x] 扫描 Orchestration 内部授权 grant 命名不再使用 `_access`。
- [x] 更新 OpenAPI/API tests。

验收：

```bash
PYTHONPATH=src pytest -q \
  tests/unit/test_authorization.py \
  tests/unit/test_authorization_access_boundary.py \
  tests/unit/test_access_http.py \
  tests/unit/test_access_actions.py \
  tests/unit/test_orchestration_approval.py \
  tests/unit/test_orchestration_tools.py
```

## 分工建议

- Worker A：Authorization-owned persistence、container 装配、policy/grant migration。
- Worker B：Access 去 ABAC 化、Access action/query/read model 清理、Access tests。
- Worker C：Orchestration 命名收口、approval/tool resolver 调用链和相关 tests。
- Worker D：前端 Access/Authorization UI 文案和 Settings/Operations 接入口清理。
- Maintainer：集成冲突、迁移顺序、最终架构扫描和全量测试。
