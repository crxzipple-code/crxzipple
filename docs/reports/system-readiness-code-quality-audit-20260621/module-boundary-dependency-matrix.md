# Module Boundary Dependency Matrix

Date: 2026-06-21

This matrix records intended dependencies after the current runtime convergence work. It should be used when splitting code or adding tests so modules do not regain hidden ownership of each other's facts.

## Dependency Rules

- Domain packages stay local to their module.
- Cross-module use goes through application ports, query services, event contracts, or assembly injection.
- Infrastructure adapters do not become cross-module public APIs.
- UI/debug/projection layers consume read models; they do not mutate owner state.
- Provider adapters translate protocol structures; they do not own runtime lifecycle.

## Core Runtime Flow

| Step | Owner | Consumes | Emits/Exposes | Must Not Do |
| --- | --- | --- | --- | --- |
| Run intake and advancement | orchestration | agent/session/context/tool/llm application ports | run lifecycle facts, execution chains | Own LLM/tool/session internals |
| Provider invocation | llm | provider request draft/rendered input | invocation facts, response items | Decide run completion outside contract signals |
| Conversation ledger | session | append/replay requests from orchestration/tool/llm | session/segment/item facts | Render provider protocol directly |
| Context selection | context_workspace | refs to session/tool/memory/agent/skill facts | render snapshots, selected context slices | Store owner facts as duplicate truth |
| Tool execution | tool | catalog/source/runtime target/assignment | tool runs, results, artifacts refs | Complete orchestration run |
| UI timeline | workbench | owner query services/projections | user-facing run/session timeline | Infer hidden facts or feed LLM |
| Operations dashboard | operations | events + owner query services | operations projections | Become business owner |

## Integration Boundaries

| Module | Allowed Upstream Dependencies | Allowed Downstream Consumers | Notes |
| --- | --- | --- | --- |
| access | settings governance models, owner consumer declarations | tool, llm, channels, browser, skills, memory | External credential truth only |
| authorization | internal policy/grant requests | orchestration, tool, llm, settings governance UI | Internal ABAC only, no credential truth |
| settings | owner module action ports, typed config declarations | owner modules through typed effective config | Governance surface, not universal entity store |
| skills | filesystem/persistence repositories, access/tool/auth readiness ports | context_workspace/tool/llm request renderers | Catalog/package truth, not run usage truth |
| memory | storage/index/policy services | tools/context slices/agent recall flows | Retrieval/write capability, not hidden prompt injection |
| channels | access readiness, orchestration turn submission port, session scope port | external transports, operations projection | External ingress/egress owner |
| browser | daemon/process/access/tool capability ports | tool execution, operations/workbench refs | Generic browser capability, no site-specific core logic |
| mobile | artifacts/ocr/process-like device adapters | tool execution | Generic mobile capability |
| artifacts | filesystem store | tool/session/workbench/ocr/mobile refs | Large payload storage by ref |
| daemon | process supervisor | operations, CLI, runtime activation | Long-running service state only |
| dispatch | events wakeup port, SQL repository | workers/orchestration schedulers | Durable queue semantics |
| events | backend/outbox/contract registry | all owner modules and observers | Business-neutral event fabric |
| event_relay | events and narrow observer ports | operations/observation flows | Bridge only; revisit ownership |

## Forbidden Dependency Patterns

- `modules/*/domain` importing another module's domain entity.
- `orchestration` importing provider-specific HTTP/WebSocket adapter internals.
- `workbench` or `operations` mutating owner module state during projection.
- `context_workspace` copying tool/session/memory facts as durable truth instead of refs/control state.
- `settings` directly writing module-owned entities without dispatching to owner application service.
- `access` importing `authorization` or enforcing internal ABAC policy.
- `authorization` resolving external credential files/tokens/accounts.
- `browser` or `mobile` containing task-specific website/app workflows.
- `events` interpreting business semantics.

## Split Guidance For Large Files

| Hotspot | Target Split |
| --- | --- |
| `operations/application/read_models/*.py` | query source, materializer, DTO presenter, diagnostics/cost |
| `workbench/application/timeline_projector.py` | response items, tool interactions, lifecycle merge, visibility policy |
| `session/application/services.py` | command append, query, replay window, compaction, metadata, routing |
| `context_workspace/application/root_nodes.py` | instruction roots, execution roots, agent roots, run roots, planning roots |
| `browser/application/services.py` | profile admin, pool allocation, planning, execution coordination, tab/selection ops |
| `browser/infrastructure/action_engines.py` | CDP session, locator resolution, action execution, snapshot capture, error mapping |
| `channels/application/lark_runtime.py` | Lark service facade and observe loop |
| `channels/application/lark_runtime_delivery.py` | Lark outbound observe delivery payload building, artifact upload, send calls |
| `channels/application/lark_runtime_identity.py` | Lark tenant-token and bot identity lookup/cache |
| `channels/application/lark_runtime_long_connection.py` | Lark long-connection thread/SDK ingress |
| `channels/application/lark_runtime_observation.py` | Lark session-message observation payload projection |
| `channels/application/lark_runtime_submission.py` | Lark message-to-run submission, reply-address construction, interaction binding |
| `channels/application/payload_redaction.py` | Channel observation/read-model payload redaction for projection exits |
| `channels/application/webhook_runtime_submission.py` | Webhook inbound message-to-run submission, idempotency lookup, reply-address construction, interaction binding |
| `access/application/*.py` | OAuth setup/token lifecycle, readiness query, action handlers, settings adapter, audit/redaction |
| `settings/interfaces/http.py` | overview/detail, action execution, runtime defaults, audit, presenters |
| `skills/interfaces/*.py` | router/command shell, DTO presenters, application command handlers |

## Review Questions For New Code

- Which module owns this fact?
- Is this a command, query, projection, renderer, adapter, or observer?
- Does this path run in the LLM request hot path?
- Could this data be stale, synthetic, or debug-only?
- Is this safe under multi-user/concurrent execution?
- Does this introduce a second route to mutate the same truth?
