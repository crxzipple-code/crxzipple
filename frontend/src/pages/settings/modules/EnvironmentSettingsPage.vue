<script setup lang="ts">
import { ArrowRight, Box, CheckCircle2, Copy, Download, GitBranch, Info, KeyRound, Lock, MoreVertical, Save, Search, Shield, Upload } from "lucide-vue-next";

import DataTable from "@/shared/ui/DataTable.vue";
import StatusDot from "@/shared/ui/StatusDot.vue";
import UiButton from "@/shared/ui/UiButton.vue";

const environments = [
  { name: "prod-us-east-1", role: "Production", status: "Active", region: "us-east-1", initial: "P" },
  { name: "staging-us-east-1", role: "Staging", status: "Active", region: "us-east-1", initial: "S" },
  { name: "dev-us-west-2", role: "Development", status: "Active", region: "us-west-2", initial: "D" },
  { name: "test-us-west-2", role: "Testing", status: "Inactive", region: "us-west-2", initial: "T" },
  { name: "local", role: "Local", status: "Inactive", region: "local", initial: "L" },
] as const;

const variables = [
  { Key: "RUNTIME_TRACE_LEVEL", Value: "key_events", Source: "Environment", Scope: "Prod", "Last Changed": "2h ago" },
  { Key: "MAX_RUN_CONCURRENCY", Value: "200", Source: "Environment", Scope: "Prod", "Last Changed": "2h ago" },
  { Key: "TOOL_TIMEOUT_MS", Value: "30000", Source: "Runtime Defaults", Scope: "All", "Last Changed": "1d ago" },
];

const secrets = [
  { Name: "OPENAI_API_KEY", Provider: "Access Assets", Rotation: "30 days", Status: "Healthy", "Used By": "LLM Profiles" },
  { Name: "PINECONE_API_KEY", Provider: "Access Assets", Rotation: "60 days", Status: "Healthy", "Used By": "Memory Stores" },
  { Name: "SLACK_BOT_TOKEN", Provider: "Access Assets", Rotation: "Manual", Status: "Warning", "Used By": "Channels" },
];

const groups = [
  { Group: "production-runtime", Members: "12", Scope: "Prod", Status: "Active" },
  { Group: "support-admins", Members: "6", Scope: "Prod", Status: "Active" },
  { Group: "release-observers", Members: "18", Scope: "Read-only", Status: "Active" },
];
</script>

<template>
  <main class="settings-module environment-settings scroll-area">
    <header class="settings-page-header">
      <div>
        <h1>Environment <a>Docs</a></h1>
        <p>Manage isolated configuration used to deploy and run agents, skills, and integrations.</p>
      </div>
      <div class="settings-header-actions">
        <UiButton size="sm" variant="primary"><Box :size="14" /> New Environment</UiButton>
        <UiButton size="sm" variant="secondary"><MoreVertical :size="14" /></UiButton>
      </div>
    </header>

    <nav class="settings-tabs environment-tabs">
      <button class="active" type="button">Environments</button>
      <button type="button">Variables</button>
      <button type="button">Secrets</button>
      <button type="button">Groups</button>
      <button type="button">Import / Export</button>
    </nav>

    <section class="settings-panel environment-info-band">
      <article><Info :size="16" /><div><span>Environment Role</span><small>Environments provide deployment-scoped configuration and secrets.</small></div></article>
      <article><GitBranch :size="16" /><div><span>Precedence</span><small>Environment overrides System/Platform Defaults.</small><a>View Runtime Defaults <ArrowRight :size="12" /></a></div></article>
      <article><Shield :size="16" /><div><span>Access Assets Scope</span><small>Access Assets can be scoped per environment.</small><a>Manage Access Assets <ArrowRight :size="12" /></a></div></article>
      <article><ArrowRight :size="16" /><div><span>Learn more</span><small>Understand environment model and best practices.</small><a>Environment Guide <ArrowRight :size="12" /></a></div></article>
    </section>

    <section class="environment-layout">
      <aside class="settings-panel environment-picker">
        <div class="environment-picker-head">
          <h2>Environments (5)</h2>
          <button type="button"><MoreVertical :size="14" /></button>
        </div>
        <div class="environment-picker-filter">
          <label><Search :size="14" /><input placeholder="Search environments..." /></label>
          <select><option>All Status</option></select>
        </div>
        <div class="environment-list">
          <button v-for="environment in environments" :key="environment.name" :class="{ active: environment.name === 'prod-us-east-1' }" type="button">
            <span>{{ environment.initial }}</span>
            <strong>{{ environment.name }}<small>{{ environment.role }} / {{ environment.region }}</small></strong>
            <em>{{ environment.status }}</em>
          </button>
        </div>
      </aside>

      <div class="environment-workspace">
        <section class="settings-panel environment-detail">
          <header>
            <div class="environment-title">
              <span><Box :size="19" /></span>
              <div>
                <h2>prod-us-east-1 <em><StatusDot tone="success" />Active</em></h2>
                <p>ID: <code>env_prod_us_east_1</code> <Copy :size="12" /></p>
              </div>
            </div>
            <div class="settings-header-actions">
              <UiButton size="sm" variant="secondary">Set as Default</UiButton>
              <UiButton size="sm" variant="primary"><Save :size="14" /> Edit Environment</UiButton>
              <UiButton size="sm" variant="secondary"><MoreVertical :size="14" /></UiButton>
            </div>
          </header>

          <nav class="environment-detail-tabs">
            <button class="active" type="button">Overview</button>
            <button type="button">Variables (86)</button>
            <button type="button">Secrets (12)</button>
            <button type="button">Groups (4)</button>
            <button type="button">Access Assets (18)</button>
            <button type="button">History</button>
          </nav>

          <div class="environment-overview-grid">
            <article>
              <h3>Environment Information</h3>
              <div class="environment-form-grid">
                <label><span>Name</span><input value="prod-us-east-1" /></label>
                <label><span>Role</span><select><option>Production</option></select></label>
                <label><span>Region</span><input value="us-east-1" /></label>
                <label><span>Owner</span><input value="Platform Team" /></label>
                <label class="wide"><span>Description</span><textarea>Primary production environment with guarded overrides and audited activation.</textarea></label>
              </div>
            </article>
            <article>
              <h3>Override Summary</h3>
              <dl class="settings-kv">
                <div><dt>Runtime Defaults</dt><dd>216 inherited</dd></div>
                <div><dt>Environment Overrides</dt><dd class="settings-tone-warning">7 active</dd></div>
                <div><dt>Conflict Count</dt><dd class="settings-tone-success">0</dd></div>
                <div><dt>Rollback Points</dt><dd>5 available</dd></div>
              </dl>
            </article>
            <article>
              <h3>Configuration Validation</h3>
              <ul class="validation-list">
                <li><CheckCircle2 :size="14" />Variables resolved</li>
                <li><CheckCircle2 :size="14" />Secret metadata valid</li>
                <li><CheckCircle2 :size="14" />Access scope allowed</li>
                <li><Lock :size="14" />Activation requires approval</li>
              </ul>
            </article>
          </div>
        </section>

        <section class="environment-mid-grid">
          <article class="settings-panel precedence-card">
            <div class="settings-panel-heading"><h2>Precedence & Inheritance</h2><a>View resolution trace <ArrowRight :size="12" /></a></div>
            <div class="precedence-flow">
              <span>Runtime Defaults</span><ArrowRight :size="14" /><span>Organization</span><ArrowRight :size="14" /><span class="active">Environment</span><ArrowRight :size="14" /><span>Deployment</span><ArrowRight :size="14" /><span>Run</span>
            </div>
            <dl class="settings-kv">
              <div><dt>Winning Layer</dt><dd>Environment for 7 keys</dd></div>
              <div><dt>Dry-run Impact</dt><dd>18 active runs affected</dd></div>
              <div><dt>Rollback Strategy</dt><dd>Restore previous environment snapshot</dd></div>
            </dl>
          </article>
          <article class="settings-panel">
            <div class="settings-panel-heading"><h2>Access Assets Scope</h2><span>12 assets</span></div>
            <dl class="settings-kv">
              <div><dt>LLM Credentials</dt><dd class="settings-tone-success">4 healthy</dd></div>
              <div><dt>Memory Stores</dt><dd class="settings-tone-success">3 healthy</dd></div>
              <div><dt>Channel Tokens</dt><dd class="settings-tone-warning">1 warning</dd></div>
            </dl>
          </article>
          <article class="settings-panel activation-card">
            <div class="settings-panel-heading"><h2>Environment Activation</h2><span>Guarded</span></div>
            <p>Activation changes require validation, impact preview, and an approval note.</p>
            <button type="button">Run Activation Check</button>
          </article>
        </section>

        <section class="environment-bottom-grid">
          <article class="settings-panel">
            <div class="settings-panel-heading"><h2>Environment Variables</h2><a>Edit variables</a></div>
            <DataTable :columns="['Key', 'Value', 'Source', 'Scope', 'Last Changed']" :rows="variables" section-id="environment-variables" />
          </article>
          <article class="settings-panel">
            <div class="settings-panel-heading"><h2>Secrets</h2><a>Manage secrets</a></div>
            <DataTable :columns="['Name', 'Provider', 'Rotation', 'Status', 'Used By']" :rows="secrets" section-id="environment-secrets" />
          </article>
          <article class="settings-panel">
            <div class="settings-panel-heading"><h2>Groups</h2><a>Manage groups</a></div>
            <DataTable :columns="['Group', 'Members', 'Scope', 'Status']" :rows="groups" section-id="environment-groups" />
          </article>
          <article class="settings-panel">
            <div class="settings-panel-heading"><h2>Import / Export</h2><span>YAML / JSON</span></div>
            <div class="environment-action-row"><button type="button"><Upload :size="14" /> Import Config</button><button type="button"><Download :size="14" /> Export Snapshot</button></div>
          </article>
          <article class="settings-panel">
            <div class="settings-panel-heading"><h2>Change Management</h2><span>Required</span></div>
            <dl class="settings-kv"><div><dt>Reviewer</dt><dd>Platform Admin</dd></div><div><dt>Ticket</dt><dd>REL-2038</dd></div><div><dt>Audit</dt><dd class="settings-tone-success">Enabled</dd></div></dl>
          </article>
        </section>
      </div>
    </section>

    <footer class="settings-footer">
      <span><Box :size="14" />Config Source: Environment</span>
      <span><GitBranch :size="14" />Override layer: deployment</span>
      <span><KeyRound :size="14" />Secrets resolved through Access Assets</span>
      <span><Save :size="14" />Last Saved: 2 minutes ago</span>
      <a>Audit History <ArrowRight :size="13" /></a>
    </footer>
  </main>
</template>

<style scoped>
.settings-page-header h1 {
  display: inline-flex;
  gap: 10px;
  align-items: center;
}

.settings-page-header h1 a {
  color: var(--color-blue);
  font-size: 12px;
  font-weight: 600;
  text-decoration: none;
}

.environment-tabs {
  margin-bottom: 8px;
}

.environment-info-band {
  display: grid;
  grid-template-columns: 0.8fr 1.2fr 0.85fr 1fr;
  gap: 0;
  margin-bottom: 10px;
  padding: 0;
  overflow: hidden;
}

.environment-info-band article {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  gap: 10px;
  min-height: 88px;
  padding: 18px 20px;
  border-right: 1px solid var(--border-subtle);
}

.environment-info-band article:last-child {
  border-right: 0;
}

.environment-info-band article > svg {
  color: var(--color-blue);
  margin-top: 2px;
}

.environment-info-band span,
.environment-info-band small {
  display: block;
  color: var(--text-muted);
  font-size: 11px;
}

.environment-info-band span {
  color: var(--text-primary);
  font-weight: 750;
}

.environment-info-band a {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-top: 10px;
  color: var(--color-accent);
  font-size: 11px;
  text-decoration: none;
}

.environment-layout {
  display: grid;
  grid-template-columns: 310px minmax(0, 1fr);
  gap: 12px;
}

.environment-picker {
  display: grid;
  align-content: start;
  gap: 10px;
  padding: 10px;
}

.environment-picker-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 28px;
}

.environment-picker-head h2 {
  font-size: 13px;
}

.environment-picker-head button {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-muted);
}

.environment-picker-filter {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 84px;
  gap: 8px;
}

.environment-picker label {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  min-height: 30px;
  padding: 0 9px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-muted);
}

.environment-picker input,
.environment-picker select,
.environment-form-grid input,
.environment-form-grid select,
.environment-form-grid textarea {
  width: 100%;
  min-height: 30px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  font-size: 12px;
}

.environment-picker input {
  border: 0;
  outline: 0;
  background: transparent;
}

.environment-picker select,
.environment-form-grid input,
.environment-form-grid select,
.environment-form-grid textarea {
  padding: 0 9px;
}

.environment-form-grid textarea {
  min-height: 58px;
  padding-top: 7px;
  resize: vertical;
}

.environment-list {
  display: grid;
  gap: 6px;
}

.environment-list button {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  min-height: 54px;
  padding: 8px;
  border: 1px solid transparent;
  border-radius: var(--radius-2);
  background: transparent;
  color: var(--text-secondary);
  text-align: left;
}

.environment-list button.active {
  border-color: color-mix(in srgb, var(--color-accent) 54%, var(--border-subtle));
  background: var(--surface-active);
}

.environment-list button > span {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--color-blue) 18%, transparent);
  color: var(--color-blue);
}

.environment-list strong,
.environment-list small {
  display: block;
  min-width: 0;
}

.environment-list strong {
  overflow: hidden;
  color: var(--text-primary);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.environment-list small,
.environment-list em {
  color: var(--text-muted);
  font-size: 10.5px;
  font-style: normal;
}

.environment-workspace {
  display: grid;
  gap: 10px;
  min-width: 0;
}

.environment-detail {
  padding: 0;
  overflow: hidden;
}

.environment-detail > header,
.environment-title,
.environment-title h2,
.environment-title p {
  display: flex;
  align-items: center;
}

.environment-detail > header {
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
  border-bottom: 1px solid var(--border-subtle);
}

.environment-title {
  gap: 10px;
}

.environment-title > span {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--color-accent) 22%, transparent);
  color: var(--color-accent);
}

.environment-title h2 {
  gap: 9px;
  font-size: 16px;
}

.environment-title h2 em {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 7px;
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--color-success) 16%, transparent);
  color: var(--color-success);
  font-size: 11px;
  font-style: normal;
}

.environment-title p {
  gap: 6px;
  margin-top: 4px;
  color: var(--text-muted);
  font-size: 11px;
}

.environment-detail-tabs {
  display: flex;
  gap: 22px;
  min-height: 38px;
  padding: 0 12px;
  border-bottom: 1px solid var(--border-subtle);
}

.environment-detail-tabs button {
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
}

.environment-detail-tabs .active {
  border-color: var(--color-accent);
  color: var(--text-primary);
}

.environment-overview-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(220px, 0.85fr) minmax(220px, 0.85fr);
  gap: 10px;
  padding: 12px;
}

.environment-overview-grid article {
  min-width: 0;
  padding: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-elevated) 70%, transparent);
}

.environment-overview-grid h3 {
  margin-bottom: 9px;
  font-size: 13px;
}

.environment-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.environment-form-grid label {
  display: grid;
  gap: 4px;
}

.environment-form-grid span {
  color: var(--text-muted);
  font-size: 10.5px;
}

.environment-form-grid .wide {
  grid-column: 1 / -1;
}

.validation-list {
  display: grid;
  gap: 8px;
  padding: 0;
  list-style: none;
}

.validation-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 12px;
}

.validation-list svg {
  color: var(--color-success);
}

.environment-mid-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(230px, 0.7fr) minmax(230px, 0.7fr);
  gap: 10px;
}

.precedence-flow {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
}

.precedence-flow span {
  padding: 6px 9px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  color: var(--text-secondary);
  font-size: 11px;
}

.precedence-flow .active {
  border-color: color-mix(in srgb, var(--color-accent) 62%, var(--border-subtle));
  background: var(--surface-active);
  color: var(--text-primary);
}

.activation-card p {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.45;
}

.activation-card button,
.environment-action-row button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  min-height: 30px;
  padding: 0 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  font-size: 12px;
}

.activation-card button {
  margin-top: 10px;
}

.environment-bottom-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr) minmax(0, 0.8fr);
  gap: 10px;
}

.environment-bottom-grid article:nth-child(4),
.environment-bottom-grid article:nth-child(5) {
  min-height: 110px;
}

.environment-action-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}
</style>
