<script setup lang="ts">
import { ArrowRight, Copy, GitBranch, KeyRound, LayoutGrid, LayoutList, ListFilter, RefreshCcw, Save, Shield, Zap } from "lucide-vue-next";

import DataTable from "@/shared/ui/DataTable.vue";
import StatusDot from "@/shared/ui/StatusDot.vue";
import UiButton from "@/shared/ui/UiButton.vue";

const assets = [
  { Name: "OpenAI API Key", "Asset ID": "ast_01JKB2PX8VQ7...", Type: "API Key", "Provider / Service": "OpenAI", Environment: "Production", Status: "Active", Validation: "Valid", "Required By": "8 / 12 / 2 / 3", "Last Used": "2 hours ago", "Expires At": "-", Owner: "Jane Doe", Actions: "Edit / Clone" },
  { Name: "Pinecone Vector DB", "Asset ID": "ast_01K2M9Q7YF6...", Type: "API Key", "Provider / Service": "Pinecone", Environment: "Production", Status: "Active", Validation: "Valid", "Required By": "5 / 6 / 1 / 2", "Last Used": "1 day ago", "Expires At": "-", Owner: "Jane Doe", Actions: "Edit / Clone" },
  { Name: "Anthropic Claude", "Asset ID": "ast_01H7R3T6D9Q...", Type: "API Key", "Provider / Service": "Anthropic", Environment: "Production", Status: "Active", Validation: "Valid", "Required By": "4 / 7 / 1 / 2", "Last Used": "5 hours ago", "Expires At": "-", Owner: "Michael Chen", Actions: "Edit / Clone" },
  { Name: "Google Workspace", "Asset ID": "ast_01G9L2V4B1M...", Type: "OAuth", "Provider / Service": "Google", Environment: "Production", Status: "Active", Validation: "Valid", "Required By": "3 / 5 / 2 / 1", "Last Used": "3 hours ago", "Expires At": "2025-06-15", Owner: "Jane Doe", Actions: "Edit / Clone" },
  { Name: "Slack Bot Token", "Asset ID": "ast_01F8W5Y2H6K...", Type: "Token", "Provider / Service": "Slack", Environment: "Staging", Status: "Inactive", Validation: "Invalid", "Required By": "2 / 2 / 1 / 1", "Last Used": "-", "Expires At": "2025-05-20", Owner: "Michael Chen", Actions: "Edit / Clone" },
  { Name: "AWS S3 Access Key", "Asset ID": "ast_01E7N1C9J4R...", Type: "Access Key", "Provider / Service": "AWS", Environment: "Production", Status: "Active", Validation: "Valid", "Required By": "6 / 3 / 1 / 1", "Last Used": "1 hour ago", "Expires At": "-", Owner: "Jane Doe", Actions: "Edit / Clone" },
];

const consumerRows = [
  { Type: "Agent Profiles", Count: "8" },
  { Type: "Retrieval Policies", Count: "12" },
  { Type: "Skill Requirements", Count: "2" },
  { Type: "Channels / Runtimes", Count: "3" },
];

const usageRows = [
  { Metric: "Total Requests", Value: "12,456" },
  { Metric: "Total Tokens", Value: "8.3M" },
  { Metric: "Avg Response Time", Value: "1.24s" },
  { Metric: "Error Rate", Value: "0.02%" },
];
</script>

<template>
  <main class="settings-module access-settings scroll-area">
    <header class="settings-page-header">
      <div>
        <h1>Access Assets</h1>
        <p>Manage API keys, tokens, credentials, and other external access assets used across the platform.</p>
      </div>
      <div class="settings-header-actions">
        <UiButton size="sm" variant="primary"><KeyRound :size="14" /> New Asset</UiButton>
        <UiButton size="sm" variant="secondary"><RefreshCcw :size="14" /> Import Asset</UiButton>
      </div>
    </header>

    <section class="access-tabs-row">
      <nav class="settings-tabs">
        <button class="active" type="button">All Assets</button>
        <button type="button">API Keys</button>
        <button type="button">OAuth Connections</button>
        <button type="button">Secrets</button>
        <button type="button">Certificates</button>
      </nav>
    </section>

    <section class="access-filter-row">
      <label><KeyRound :size="14" /><input placeholder="Search assets..." /></label>
      <select><option>All Types</option></select>
      <select><option>All Status</option></select>
      <select><option>All Environments</option></select>
      <select><option>All Owners</option></select>
      <button type="button"><ListFilter :size="14" /></button>
      <button class="active" type="button"><LayoutList :size="14" /></button>
      <button type="button"><LayoutGrid :size="14" /></button>
    </section>

    <section class="settings-panel access-list">
      <DataTable
        :columns="['Name', 'Asset ID', 'Type', 'Provider / Service', 'Environment', 'Status', 'Validation', 'Required By', 'Last Used', 'Expires At', 'Owner', 'Actions']"
        :rows="assets"
        section-id="access-assets"
      />
      <footer>Showing 1 to 6 of 6 results</footer>
    </section>

    <section class="access-detail-layout">
      <div class="access-main-column">
        <article class="settings-panel access-editor">
          <aside class="access-editor-tabs">
            <button class="active" type="button">Overview</button>
            <button type="button">Credentials</button>
            <button type="button">Permissions & Scope</button>
            <button type="button">Usage & Invocations</button>
            <button type="button">Rotation & Expiry</button>
            <button type="button">Validation & Health</button>
            <button type="button">Setup & Integration</button>
            <button type="button">Audit Logs</button>
          </aside>

          <div class="access-form">
            <header>
              <span class="asset-icon"><Shield :size="20" /></span>
              <div>
                <h2>OpenAI API Key <em><StatusDot tone="success" />Active</em><span>API Key</span></h2>
                <p>Key for OpenAI API access</p>
              </div>
            </header>

            <section class="asset-info-grid">
              <article>
                <dl class="settings-kv">
                  <div><dt>Asset ID</dt><dd>ast_01JKB2PX8VQ7M9TSY2C1D8E</dd></div>
                  <div><dt>Provider / Service</dt><dd>OpenAI</dd></div>
                  <div><dt>Type</dt><dd>API Key</dd></div>
                  <div><dt>Environment</dt><dd class="settings-tone-success">Production</dd></div>
                  <div><dt>Secret Storage</dt><dd>AWS Secrets Manager</dd></div>
                  <div><dt>Asset Owner</dt><dd>Jane Doe</dd></div>
                  <div><dt>Created At</dt><dd>2024-12-01 09:30:21 UTC+8</dd></div>
                  <div><dt>Last Updated</dt><dd>2025-05-18 10:15:42 UTC+8</dd></div>
                </dl>
              </article>

              <article>
                <h3>Secret Version & Fingerprint</h3>
                <dl class="settings-kv">
                  <div><dt>Version</dt><dd>7</dd></div>
                  <div><dt>Fingerprint</dt><dd>b7e1...9c2a <Copy :size="12" /></dd></div>
                  <div><dt>Last Rotated</dt><dd>2025-05-10 08:45:12 UTC+8</dd></div>
                </dl>
              </article>

              <article>
                <h3>Setup Method</h3>
                <dl class="settings-kv">
                  <div><dt>Created With</dt><dd>Manual API Key</dd></div>
                  <div><dt>Environment Scope</dt><dd>us-east-1, us-west-2</dd></div>
                </dl>
              </article>

              <article>
                <h3>Tags</h3>
                <div class="settings-chip-row"><span>ai</span><span>llm</span><span>production</span><span>critical</span></div>
              </article>
            </section>
          </div>
        </article>

        <section class="access-support-grid">
          <article class="settings-panel"><div class="settings-panel-heading"><h3>Permissions / Capabilities</h3><span>Granted by provider</span></div><div class="settings-chip-row"><span>models.invoke</span><span>chat.completions.create</span><span>embeddings.create</span><span>images.generate</span><span>files.upload</span></div></article>
          <article class="settings-panel policy-preview">
            <div class="settings-panel-heading"><h3>Policy Resolution Preview</h3><a>View details <ArrowRight :size="12" /></a></div>
            <div class="policy-flow"><span>Runtime Defaults</span><ArrowRight :size="12" /><span>Environment</span><ArrowRight :size="12" /><span>Agent Profile</span><ArrowRight :size="12" /><span>Session</span><ArrowRight :size="12" /><span>Access Grants</span></div>
            <strong>Result: Allowed</strong>
          </article>
          <article class="settings-panel"><div class="settings-panel-heading"><h3>Affected Runs / Blocked Consumers</h3><a>View details</a></div><dl class="settings-kv"><div><dt>Potentially Affected Runs</dt><dd>3</dd></div><div><dt>Blocked Consumers</dt><dd>1</dd></div></dl></article>
          <article class="settings-panel danger-zone"><div class="settings-panel-heading"><h3>Danger Zone</h3><span>Access Actions</span></div><button type="button">Rotate Secret Now</button><button type="button">Revoke Asset</button><button type="button">Disable Asset</button><button type="button">Delete Asset Reference</button></article>
        </section>
      </div>

      <aside class="access-summary-stack">
        <div class="settings-header-actions">
          <UiButton size="sm" variant="secondary"><Zap :size="14" /> Test Connection</UiButton>
          <UiButton size="sm" variant="secondary"><RefreshCcw :size="14" /> Rotate</UiButton>
          <UiButton size="sm" variant="danger">Revoke</UiButton>
        </div>

        <article class="settings-panel">
          <div class="settings-panel-heading"><h2>Consumers</h2><a>View all <ArrowRight :size="12" /></a></div>
          <DataTable :columns="['Type', 'Count']" :rows="consumerRows" section-id="access-consumers" />
          <p>Click any count in the table above to filter assets by consumer type.</p>
        </article>

        <article class="settings-panel">
          <div class="settings-panel-heading"><h2>Usage</h2><a>View details <ArrowRight :size="12" /></a></div>
          <DataTable :columns="['Metric', 'Value']" :rows="usageRows" section-id="access-usage-summary" />
        </article>

        <article class="settings-panel">
          <div class="settings-panel-heading"><h2>Validation & Health</h2></div>
          <dl class="settings-kv">
            <div><dt>Connection Test</dt><dd class="settings-tone-success">Passed</dd></div>
            <div><dt>Permission Check</dt><dd class="settings-tone-success">Passed</dd></div>
            <div><dt>Last Validation</dt><dd>2025-05-18 10:14:52</dd></div>
            <div><dt>Next Validation</dt><dd>in 12 hours</dd></div>
          </dl>
        </article>
      </aside>
    </section>

    <footer class="settings-footer">
      <span><Shield :size="14" />Config Source: Access Asset</span>
      <span><GitBranch :size="14" />Secret value remains server-side</span>
      <span><Save :size="14" />Last Saved: 2 minutes ago</span>
      <a>Audit History <ArrowRight :size="13" /></a>
    </footer>
  </main>
</template>

<style scoped>
.access-tabs-row {
  border-bottom: 1px solid var(--border-subtle);
}

.access-tabs-row .settings-tabs {
  margin-bottom: 0;
  border-bottom: 0;
}

.access-filter-row {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) 130px 130px 150px 130px 34px 34px 34px;
  gap: 8px;
  align-items: center;
  margin: 8px 0;
}

.access-filter-row label {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  min-height: 30px;
  padding: 0 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-muted);
}

.access-filter-row input,
.access-filter-row select,
.access-filter-row button {
  min-height: 30px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  font-size: 12px;
}

.access-filter-row input {
  border: 0;
  outline: 0;
  background: transparent;
}

.access-filter-row select {
  padding: 0 8px;
}

.access-filter-row button {
  display: grid;
  place-items: center;
  padding: 0;
}

.access-filter-row button.active {
  border-color: color-mix(in srgb, var(--color-accent) 70%, var(--border-subtle));
  background: var(--surface-active);
  color: var(--color-accent);
}

.access-list {
  padding: 0;
  overflow: hidden;
}

.access-list :deep(tbody tr:first-child) {
  background: color-mix(in srgb, var(--color-blue) 9%, transparent);
}

.access-list :deep(td:first-child) {
  position: relative;
  padding-left: 38px;
  color: var(--text-primary);
  font-weight: 750;
}

.access-list :deep(td:first-child)::before {
  content: "";
  position: absolute;
  top: 50%;
  left: 12px;
  width: 18px;
  height: 18px;
  transform: translateY(-50%);
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--color-gray) 30%, transparent);
}

.access-list footer {
  min-height: 28px;
  padding: 7px 12px;
  border-top: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 11px;
}

.access-detail-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 380px;
  gap: 10px;
  align-items: start;
  margin-top: 10px;
}

.access-main-column,
.access-summary-stack {
  display: grid;
  gap: 10px;
  min-width: 0;
}

.access-summary-stack {
  align-content: start;
}

.access-editor {
  display: grid;
  grid-template-columns: 166px minmax(0, 1fr);
  padding: 0;
  overflow: hidden;
}

.access-editor-tabs {
  display: grid;
  align-content: start;
  gap: 1px;
  padding: 6px;
  border-right: 1px solid var(--border-subtle);
  background: color-mix(in srgb, var(--surface-sidebar) 72%, transparent);
}

.access-editor-tabs button {
  min-height: 31px;
  padding: 0 9px;
  border: 0;
  border-radius: var(--radius-2);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 11px;
  text-align: left;
}

.access-editor-tabs .active {
  background: var(--surface-active);
  color: var(--text-primary);
}

.access-form {
  display: grid;
  gap: 10px;
  padding: 12px;
}

.access-form header,
.access-form h2,
.policy-flow {
  display: flex;
  align-items: center;
}

.access-form header {
  gap: 12px;
}

.asset-icon {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--color-gray) 24%, transparent);
}

.access-form h2 {
  gap: 8px;
  font-size: 16px;
}

.access-form h2 em,
.access-form h2 span {
  min-height: 20px;
  padding: 3px 7px;
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--color-blue) 18%, transparent);
  color: var(--color-blue);
  font-size: 11px;
  font-style: normal;
}

.access-form h2 em {
  display: inline-flex;
  gap: 5px;
  background: transparent;
  color: var(--color-success);
}

.access-form p,
.access-summary-stack p {
  color: var(--text-muted);
  font-size: 11px;
}

.asset-info-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr);
  gap: 10px;
}

.asset-info-grid article {
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel-soft) 72%, transparent);
}

.asset-info-grid article:first-child {
  grid-row: span 3;
}

.asset-info-grid h3 {
  margin-bottom: 10px;
  font-size: 13px;
}

.access-support-grid {
  display: grid;
  grid-template-columns: 1fr 1.25fr 0.8fr 1fr;
  gap: 10px;
}

.policy-flow {
  flex-wrap: wrap;
  gap: 7px;
  margin-bottom: 10px;
}

.policy-flow span {
  padding: 7px 9px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-raised);
  color: var(--text-secondary);
  font-size: 10.5px;
}

.policy-preview strong {
  color: var(--color-success);
  font-size: 12px;
}

.danger-zone {
  border-color: color-mix(in srgb, var(--color-danger) 54%, var(--border-subtle));
}

.danger-zone button {
  display: block;
  width: 100%;
  min-height: 25px;
  border: 0;
  background: transparent;
  color: var(--color-danger);
  cursor: pointer;
  font-size: 11px;
  font-weight: 800;
  text-align: left;
}

.access-summary-stack .settings-header-actions {
  justify-content: end;
}

.access-summary-stack .settings-panel {
  padding: 10px 12px;
}

.access-summary-stack :deep(th),
.access-summary-stack :deep(td) {
  padding-block: 4px;
  font-size: 10.5px;
}
</style>
