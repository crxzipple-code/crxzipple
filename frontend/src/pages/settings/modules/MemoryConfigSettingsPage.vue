<script setup lang="ts">
import { ArrowRight, Database, GitBranch, LayoutGrid, LayoutList, ListFilter, RefreshCcw, Save, Upload } from "lucide-vue-next";

import DataTable from "@/shared/ui/DataTable.vue";
import StatusDot from "@/shared/ui/StatusDot.vue";
import UiButton from "@/shared/ui/UiButton.vue";

const stores = [
  { Name: "Agent Memory (Default)", Type: "Vector Store", Backend: "Pinecone", Scope: "All Agents Global", Status: "Healthy", Consumers: "Agent Profiles 12 / Retrieval Policies 8 / Skill Requirements 34", "Last Updated": "2 hours ago", Actions: "Edit / Clone" },
  { Name: "Short-term Buffer", Type: "Buffer Memory", Backend: "Redis", Scope: "Session (Ephemeral)", Status: "Healthy", Consumers: "Retrieval Policies 6 / Skill Requirements 12", "Last Updated": "1 day ago", Actions: "Edit / Clone" },
  { Name: "Conversation Store", Type: "Document Store", Backend: "MongoDB Atlas", Scope: "All Agents", Status: "Healthy", Consumers: "Agent Profiles 8 / Skill Requirements 28", "Last Updated": "1 day ago", Actions: "Edit / Clone" },
  { Name: "Analytics Memory", Type: "Vector Store", Backend: "Pinecone", Scope: "Workspace", Status: "Warning", Consumers: "Retrieval Policies 3 / Skill Requirements 5", "Last Updated": "3 days ago", Actions: "Edit / Clone" },
  { Name: "Preferences Store", Type: "Key-Value Store", Backend: "DynamoDB", Scope: "User", Status: "Healthy", Consumers: "Agent Profiles 5", "Last Updated": "2 days ago", Actions: "Edit / Clone" },
  { Name: "Archive Store", Type: "Object Store", Backend: "S3", Scope: "Workspace", Status: "Healthy", Consumers: "Retrieval Policies 2", "Last Updated": "1 week ago", Actions: "Edit / Clone" },
];

const consumerRows = [
  { "Requested By": "Agent Profiles", Count: "12" },
  { "Requested By": "Retrieval Policies", Count: "8" },
  { "Requested By": "Skill Requirements", Count: "34" },
];

const lifecycleRows = [
  { Metric: "Index Latency (p95)", Value: "18 ms" },
  { Metric: "Query Latency (p95)", Value: "42 ms" },
  { Metric: "Error Rate (24h)", Value: "0.02%" },
];
</script>

<template>
  <main class="settings-module memory-settings scroll-area">
    <header class="settings-page-header">
      <div>
        <h1>Memory Config</h1>
        <p>Configure memory stores, sources, indexing, policies, and retrieval strategies.</p>
      </div>
      <div class="settings-header-actions">
        <UiButton size="sm" variant="primary"><Database :size="14" /> New Memory Store</UiButton>
        <UiButton size="sm" variant="secondary"><Upload :size="14" /> Import Config</UiButton>
      </div>
    </header>

    <section class="memory-tabs-row">
      <nav class="settings-tabs">
        <button class="active" type="button">Memory Stores</button>
        <button type="button">Retrieval Strategies</button>
        <button type="button">Memory Policies</button>
        <button type="button">Embedding Models</button>
      </nav>
      <div class="memory-filter-row">
        <select><option>All Types</option></select>
        <select><option>All Status</option></select>
        <button class="active" type="button"><LayoutList :size="14" /></button>
        <button type="button"><LayoutGrid :size="14" /></button>
      </div>
    </section>

    <section class="memory-search-row">
      <label><Database :size="14" /><input placeholder="Search memory stores..." /></label>
      <button type="button"><ListFilter :size="14" /></button>
    </section>

    <section class="memory-list-layout">
      <section class="settings-panel memory-list">
        <DataTable
          :columns="['Name', 'Type', 'Backend', 'Scope', 'Status', 'Consumers', 'Last Updated', 'Actions']"
          :rows="stores"
          section-id="memory-config"
        />
        <footer>Showing 1 to 6 of 6 results</footer>
      </section>

      <aside class="memory-side-stack">
        <article class="settings-panel">
          <div class="settings-panel-heading"><h2>Consumers</h2><a>View all <ArrowRight :size="12" /></a></div>
          <DataTable :columns="['Requested By', 'Count']" :rows="consumerRows" section-id="memory-consumers" />
          <p>Skills declare memory needs. Resolver decides which store to use.</p>
        </article>
        <article class="settings-panel">
          <div class="settings-panel-heading"><h2>Memory Injection Impact</h2><span>Last 24h</span></div>
          <dl class="side-metrics">
            <div><dt>Tokens Injected</dt><dd>1,245,678</dd></div>
            <div><dt>Runs Affected</dt><dd>3,456</dd></div>
            <div><dt>Avg. Top-K</dt><dd>6.2</dd></div>
            <div><dt>Truncation Events</dt><dd>312</dd></div>
          </dl>
          <a>View usage analytics <ArrowRight :size="12" /></a>
        </article>
      </aside>
    </section>

    <section class="memory-detail-layout">
      <div class="memory-main-column">
        <article class="settings-panel memory-editor">
          <aside class="memory-editor-tabs">
            <button class="active" type="button">Basic Information</button>
            <button type="button">Source Configuration</button>
            <button type="button">Indexer Configuration</button>
            <button type="button">Retrieval & Query</button>
            <button type="button">Retention & TTL</button>
            <button type="button">Namespace / Partitioning</button>
            <button type="button">Access & Security</button>
            <button type="button">Lifecycle</button>
            <button type="button">Monitoring & Usage</button>
            <button type="button">Consumers & Requests</button>
            <button type="button">Advanced Options</button>
          </aside>

          <div class="memory-form">
            <header>
              <div class="memory-title">
                <span><Database :size="18" /></span>
                <div><h2>Agent Memory (Default) <em><StatusDot tone="success" />Healthy</em></h2><p>Primary long-term memory store used by agents.</p></div>
              </div>
              <div class="settings-header-actions">
                <UiButton size="sm" variant="secondary">Rebuild Index</UiButton>
                <UiButton size="sm" variant="secondary">Rescan Sources</UiButton>
                <UiButton size="sm" variant="primary"><Save :size="14" /> Save Changes</UiButton>
              </div>
            </header>

            <section class="memory-form-grid">
              <label><span>Name</span><input value="Agent Memory (Default)" /></label>
              <label><span>Type</span><select><option>Vector Store</option></select></label>
              <label><span>Backend</span><select><option>Pinecone</option></select></label>
              <label><span>Status</span><select><option>Healthy</option></select></label>
              <label><span>Description</span><textarea>Primary long-term memory store used by agents to persist knowledge and experiences.</textarea></label>
              <label><span>Scope</span><select><option>All Agents</option></select></label>
            </section>

            <section class="memory-config-cards">
              <article><h3>Embedding Model</h3><dl class="settings-kv"><div><dt>Profile</dt><dd>text-embedding-3-large</dd></div><div><dt>Dimensions</dt><dd>3072</dd></div></dl></article>
              <article><h3>Access Asset</h3><dl class="settings-kv"><div><dt>Asset</dt><dd class="settings-tone-success">pinecone_agent_memory</dd></div><div><dt>Type</dt><dd>API Credential</dd></div></dl><a>View in Access Center <ArrowRight :size="12" /></a></article>
              <article><h3>Index / Namespace</h3><dl class="settings-kv"><div><dt>Index</dt><dd>agent-memory</dd></div><div><dt>Region</dt><dd>us-west-2</dd></div></dl></article>
              <article><h3>Lifecycle</h3><dl class="settings-kv"><div><dt>Enabled</dt><dd class="settings-tone-success">Yes</dd></div><div><dt>Write Allowed</dt><dd class="settings-tone-success">Yes</dd></div><div><dt>Read-only</dt><dd>No</dd></div></dl></article>
            </section>
          </div>
        </article>

        <section class="memory-actions-grid">
          <article class="settings-panel">
            <div class="settings-panel-heading"><h3>Quick Actions</h3><span>Safe maintenance operations</span></div>
            <button type="button"><RefreshCcw :size="14" /> Rescan Sources</button>
            <button type="button"><Database :size="14" /> Rebuild Index</button>
          </article>
          <article class="settings-panel danger-zone">
            <div class="settings-panel-heading"><h3>Danger Zone</h3><span>High Risk</span></div>
            <p>These actions are destructive and require confirmation and permission.</p>
            <button type="button">Delete Store Data (Prod)</button>
          </article>
        </section>
      </div>

      <aside class="memory-side-stack">
        <article class="settings-panel resolution-preview">
          <div class="settings-panel-heading"><h2>Policy Resolution Preview</h2></div>
          <p>Preview how this store is resolved for a given context.</p>
          <select><option>Agent: General Assistant</option></select>
          <div class="resolution-step"><span>1</span><strong>Declared Requirement</strong><small>semantic_search, long_term_memory</small></div>
          <div class="resolution-step"><span>2</span><strong>Capability Mapping</strong><small>semantic_search -> agent_memory_default</small></div>
          <div class="resolution-step active"><span>3</span><strong>Resolved Memory Store</strong><small>Agent Memory (Default)</small></div>
          <div class="resolution-step"><span>4</span><strong>Access Evaluation</strong><small>Allowed</small></div>
          <strong>Status <em>Resolvable</em></strong>
          <a>View full resolution trace <ArrowRight :size="12" /></a>
        </article>

        <article class="settings-panel">
          <div class="settings-panel-heading"><h2>Store Lifecycle & Health</h2></div>
          <DataTable :columns="['Metric', 'Value']" :rows="lifecycleRows" section-id="memory-lifecycle-health" />
          <a>View health dashboard <ArrowRight :size="12" /></a>
        </article>
      </aside>
    </section>

    <footer class="settings-footer">
      <span><Database :size="14" />Config Source: Memory Config</span>
      <span><GitBranch :size="14" />Inherited From: Runtime Defaults</span>
      <span><Save :size="14" />Last Saved: 2 minutes ago</span>
      <a>Audit History <ArrowRight :size="13" /></a>
    </footer>
  </main>
</template>

<style scoped>
.memory-tabs-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 14px;
  align-items: end;
  border-bottom: 1px solid var(--border-subtle);
}

.memory-tabs-row .settings-tabs {
  margin-bottom: 0;
  border-bottom: 0;
}

.memory-filter-row,
.memory-search-row {
  display: grid;
  gap: 8px;
  align-items: center;
}

.memory-filter-row {
  grid-template-columns: 130px 130px 34px 34px;
  margin-bottom: 5px;
}

.memory-search-row {
  grid-template-columns: minmax(260px, 300px) 34px;
  margin: 8px 0;
}

.memory-search-row label {
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

.memory-search-row input,
.memory-filter-row select,
.memory-filter-row button,
.memory-search-row button,
.resolution-preview select {
  min-height: 30px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  font-size: 12px;
}

.memory-search-row input {
  border: 0;
  outline: 0;
  background: transparent;
}

.memory-filter-row select,
.resolution-preview select {
  padding: 0 8px;
}

.memory-filter-row button,
.memory-search-row button {
  display: grid;
  place-items: center;
  padding: 0;
}

.memory-filter-row button.active {
  border-color: color-mix(in srgb, var(--color-accent) 70%, var(--border-subtle));
  background: var(--surface-active);
  color: var(--color-accent);
}

.memory-list-layout,
.memory-detail-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 10px;
  align-items: start;
}

.memory-list,
.memory-editor {
  padding: 0;
  overflow: hidden;
}

.memory-list :deep(tbody tr:first-child) {
  background: color-mix(in srgb, var(--color-blue) 10%, transparent);
}

.memory-list :deep(td:first-child) {
  position: relative;
  padding-left: 38px;
  color: var(--text-primary);
  font-weight: 750;
}

.memory-list :deep(td:first-child)::before {
  content: "";
  position: absolute;
  top: 50%;
  left: 12px;
  width: 18px;
  height: 18px;
  transform: translateY(-50%);
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--color-accent) 70%, var(--surface-raised));
}

.memory-list footer {
  min-height: 28px;
  padding: 7px 12px;
  border-top: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 11px;
}

.memory-side-stack,
.memory-main-column {
  display: grid;
  gap: 10px;
  min-width: 0;
}

.memory-side-stack {
  align-content: start;
}

.memory-side-stack .settings-panel {
  padding: 10px 12px;
}

.memory-side-stack p,
.memory-form p,
.danger-zone p {
  color: var(--text-muted);
  font-size: 11px;
}

.side-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin: 0;
}

.side-metrics div {
  display: grid;
  gap: 3px;
}

.side-metrics dt {
  color: var(--text-muted);
  font-size: 10.5px;
}

.side-metrics dd {
  margin: 0;
  color: var(--text-primary);
  font-size: 15px;
  font-weight: 800;
}

.memory-detail-layout {
  margin-top: 10px;
}

.memory-editor {
  display: grid;
  grid-template-columns: 164px minmax(0, 1fr);
}

.memory-editor-tabs {
  display: grid;
  align-content: start;
  gap: 1px;
  padding: 6px;
  border-right: 1px solid var(--border-subtle);
  background: color-mix(in srgb, var(--surface-sidebar) 72%, transparent);
}

.memory-editor-tabs button {
  min-height: 27px;
  padding: 0 9px;
  border: 0;
  border-radius: var(--radius-2);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 11px;
  text-align: left;
}

.memory-editor-tabs .active {
  background: var(--surface-active);
  color: var(--text-primary);
}

.memory-form {
  display: grid;
  gap: 10px;
  padding: 12px;
}

.memory-form header,
.memory-title,
.memory-title h2,
.memory-actions-grid button {
  display: flex;
  align-items: center;
}

.memory-form header {
  justify-content: space-between;
  gap: 12px;
}

.memory-title {
  gap: 10px;
}

.memory-title > span {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--color-accent) 72%, var(--surface-raised));
}

.memory-title h2 {
  gap: 8px;
  font-size: 16px;
}

.memory-title em {
  display: inline-flex;
  gap: 5px;
  color: var(--color-success);
  font-size: 11px;
  font-style: normal;
}

.memory-form-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.memory-form-grid label:nth-child(5),
.memory-form-grid label:nth-child(6) {
  grid-column: span 2;
}

.memory-form-grid label {
  display: grid;
  gap: 4px;
  color: var(--text-secondary);
  font-size: 11px;
}

.memory-form-grid input,
.memory-form-grid textarea,
.memory-form-grid select {
  width: 100%;
  min-height: 30px;
  padding: 5px 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  font-size: 12px;
}

.memory-form-grid textarea {
  min-height: 58px;
}

.memory-config-cards,
.memory-actions-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.memory-config-cards article {
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel-soft) 72%, transparent);
}

.memory-config-cards h3 {
  margin-bottom: 8px;
  font-size: 13px;
}

.memory-actions-grid {
  grid-template-columns: 1fr 1fr;
}

.memory-actions-grid button {
  gap: 8px;
  min-height: 36px;
  padding: 0 12px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  cursor: pointer;
}

.danger-zone {
  border-color: color-mix(in srgb, var(--color-danger) 54%, var(--border-subtle));
}

.danger-zone button {
  color: var(--color-danger);
}

.resolution-preview {
  display: grid;
  gap: 9px;
}

.resolution-step {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  gap: 8px;
  min-height: 54px;
  padding: 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel-soft) 72%, transparent);
}

.resolution-step span {
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-blue) 18%, transparent);
  color: var(--color-blue);
  font-weight: 800;
}

.resolution-step.active span {
  background: color-mix(in srgb, var(--color-success) 18%, transparent);
  color: var(--color-success);
}

.resolution-step small {
  grid-column: 2;
  color: var(--text-muted);
  font-size: 10.5px;
}

.resolution-preview strong {
  display: flex;
  justify-content: space-between;
  color: var(--text-secondary);
  font-size: 12px;
}

.resolution-preview em {
  color: var(--color-success);
  font-style: normal;
}

.memory-side-stack a,
.memory-config-cards a {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--color-accent);
  font-size: 11px;
  text-decoration: none;
}
</style>
