<script setup lang="ts">
import { ArrowRight, Copy, GitBranch, LayoutGrid, LayoutList, ListFilter, Package, Save, Wrench } from "lucide-vue-next";

import DataTable from "@/shared/ui/DataTable.vue";
import StatusDot from "@/shared/ui/StatusDot.vue";
import UiButton from "@/shared/ui/UiButton.vue";

const tools = [
  { Name: "web_search", Source: "Built-in", Type: "HTTP", "Runtime Strategy": "openapi_remote", "Exec Mode": "background", Category: "Search", Status: "Active", "Risk Level": "Low", Version: "1.2.3", "Updated At": "2 hours ago", Actions: "Edit / Clone" },
  { Name: "sql_query", Source: "Built-in", Type: "Database", "Runtime Strategy": "local_async", "Exec Mode": "background", Category: "Data", Status: "Active", "Risk Level": "Low", Version: "1.1.0", "Updated At": "1 day ago", Actions: "Edit / Clone" },
  { Name: "openai_chat", Source: "Built-in", Type: "HTTP", "Runtime Strategy": "openapi_remote", "Exec Mode": "background", Category: "AI / LLM", Status: "Active", "Risk Level": "Medium", Version: "2.0.0", "Updated At": "1 day ago", Actions: "Edit / Clone" },
  { Name: "file_read", Source: "Built-in", Type: "File", "Runtime Strategy": "sandbox", "Exec Mode": "inline", Category: "Utility", Status: "Active", "Risk Level": "Low", Version: "1.0.5", "Updated At": "3 days ago", Actions: "Edit / Clone" },
  { Name: "send_email", Source: "Custom", Type: "SMTP", "Runtime Strategy": "openapi_remote", "Exec Mode": "background", Category: "Communication", Status: "Inactive", "Risk Level": "Medium", Version: "0.9.0", "Updated At": "5 days ago", Actions: "Edit / Clone" },
  { Name: "shell_exec", Source: "Built-in", Type: "System", "Runtime Strategy": "sandbox", "Exec Mode": "inline", Category: "System", Status: "Draft", "Risk Level": "High", Version: "0.3.0", "Updated At": "6 days ago", Actions: "Edit / Clone" },
];

const accessRows = [
  { "Asset Name": "serpapi_api", Type: "API Credential", Scope: "profile/session", Status: "Available" },
];

const testRows = [
  { Check: "Input Schema Validation", Result: "Pass", "Last Run": "2 minutes ago" },
  { Check: "Dry Run", Result: "Pass", "Last Run": "2 minutes ago" },
  { Check: "Auth & Access Check", Result: "Pass", "Last Run": "2 minutes ago" },
  { Check: "Artifact Schema Check", Result: "Pass", "Last Run": "2 minutes ago" },
];
</script>

<template>
  <main class="settings-module tool-settings scroll-area">
    <header class="settings-page-header">
      <div>
        <h1>Tool Catalog</h1>
        <p>Discover, register, and manage tools that agents can use during execution. <a>Learn more</a></p>
      </div>
      <div class="settings-header-actions">
        <UiButton size="sm" variant="secondary"><Package :size="14" /> Import Tool Package</UiButton>
        <UiButton size="sm" variant="primary"><Wrench :size="14" /> Register Tool</UiButton>
      </div>
    </header>

    <section class="tool-tabs-row">
      <nav class="settings-tabs">
        <button class="active" type="button">All Tools</button>
        <button type="button">Built-in Tools</button>
        <button type="button">Custom Tools</button>
        <button type="button">Imported Packages</button>
        <button type="button">Deprecated</button>
      </nav>

      <div class="tool-filter-row">
        <select><option>All Categories</option></select>
        <select><option>All Status</option></select>
        <button type="button"><ListFilter :size="14" /></button>
        <button class="active" type="button"><LayoutList :size="14" /></button>
        <button type="button"><LayoutGrid :size="14" /></button>
      </div>
    </section>

    <section class="settings-panel tool-list">
      <DataTable :columns="['Name', 'Source', 'Type', 'Runtime Strategy', 'Exec Mode', 'Category', 'Status', 'Risk Level', 'Version', 'Updated At', 'Actions']" :rows="tools" section-id="tool-catalog" />
      <footer>Showing 1 to 6 of 6 results</footer>
    </section>

    <section class="tool-detail-layout">
      <article class="settings-panel tool-editor">
        <aside class="tool-tabs">
          <button class="active" type="button">Basic Information</button>
          <button type="button">Input Schema</button>
          <button type="button">Output Schema</button>
          <button type="button">Runtime Strategy</button>
          <button type="button">Authentication & Access</button>
          <button type="button">Effects & Requirements</button>
          <button type="button">Capabilities Provided</button>
          <button type="button">Risk & Approval</button>
          <button type="button">Testing & Debug</button>
        </aside>

        <div class="tool-form">
          <header>
            <h2><Wrench :size="18" />web_search <span><StatusDot tone="success" />Active</span></h2>
            <div><UiButton size="sm" variant="secondary">Cancel</UiButton><UiButton size="sm" variant="primary"><Save :size="14" /> Save Changes</UiButton></div>
          </header>
          <div class="settings-form-grid">
            <label><span>Name</span><input value="web_search" /></label>
            <label><span>Display Name</span><input value="Web Search" /></label>
            <label><span>Type</span><select><option>HTTP</option></select></label>
            <label><span>Category</span><select><option>Search</option></select></label>
            <label class="settings-field-wide"><span>Description</span><textarea>Search the web for information using a search engine and return relevant results.</textarea></label>
          </div>
          <div class="tool-meta-grid">
            <span><strong>Source</strong>Built-in</span>
            <span><strong>Owner / Package</strong>system/builtin</span>
            <span><strong>Version</strong>1.2.3</span>
            <span><strong>Provider / Adapter</strong>OpenAPI</span>
            <span><strong>Base Spec / URL</strong>https://serpapi.com/openapi.yaml</span>
            <span><strong>Created At</strong>2024-04-10 10:15 UTC+8</span>
          </div>
        </div>
      </article>

      <aside class="tool-summary-stack">
        <article class="settings-panel">
          <div class="settings-panel-heading"><h2>Summary</h2></div>
          <nav class="tool-summary-tabs">
            <button class="active" type="button">Summary</button>
            <button type="button">Access</button>
            <button type="button">Effects</button>
            <button type="button">Runtime</button>
          </nav>
          <dl class="settings-kv">
            <div><dt>Status</dt><dd class="settings-tone-success">Active</dd></div>
            <div><dt>Risk Level</dt><dd class="settings-tone-success">Low</dd></div>
            <div><dt>Exec Mode</dt><dd>Background</dd></div>
            <div><dt>Runtime Strategy</dt><dd>openapi_remote</dd></div>
            <div><dt>Runtime Backend</dt><dd>Remote API (HTTP)</dd></div>
            <div><dt>Default Version</dt><dd>1.2.3</dd></div>
          </dl>
        </article>
        <article class="settings-panel">
          <div class="settings-panel-heading"><h2>Required Access Assets (1)</h2><a>View in Access Center</a></div>
          <DataTable :columns="['Asset Name', 'Type', 'Scope', 'Status']" :rows="accessRows" section-id="tool-access-assets" />
        </article>
        <article class="settings-panel">
          <div class="settings-panel-heading"><h2>Used by Skills (4)</h2><a>View in Skill Catalog</a></div>
          <div class="settings-chip-row"><span>web_search</span><span>news_summary</span><span>research_assistant</span><span>competitive_intel</span></div>
        </article>
      </aside>
    </section>

    <section class="tool-support-grid">
      <article class="settings-panel"><div class="settings-panel-heading"><h3>Capabilities Provided</h3><a>View capability contract <ArrowRight :size="12" /></a></div><div class="settings-chip-row"><span>web_search</span><span>search_results</span><span>url_fetch</span><span>snippet_extract</span></div></article>
      <article class="settings-panel"><div class="settings-panel-heading"><h3>Required Effects</h3><a>View effect guidelines <ArrowRight :size="12" /></a></div><div class="settings-chip-row"><span>network:outbound</span><span>read:web</span></div></article>
      <article class="settings-panel"><div class="settings-panel-heading"><h3>Risk & Approval</h3><a>View risk policy <ArrowRight :size="12" /></a></div><dl class="settings-kv"><div><dt>Effect Level</dt><dd class="settings-tone-success">Low</dd></div><div><dt>Approval Required</dt><dd>No</dd></div><div><dt>Allow Session Grant</dt><dd>Yes</dd></div></dl></article>
      <article class="settings-panel"><div class="settings-panel-heading"><h3>Supported Surfaces</h3><a>View surface matrix</a></div><div class="settings-chip-row"><span>web_chat</span><span>agent_plan</span><span>api_batch</span></div></article>
      <article class="settings-panel"><div class="settings-panel-heading"><h3>Artifact Output</h3><a>View artifact schema <ArrowRight :size="12" /></a></div><div class="settings-chip-row"><span>search_results</span><span>web_page_snapshot</span></div></article>
      <article class="settings-panel effective-preview">
        <div class="settings-panel-heading"><h3>Effective Configuration Preview</h3><a>View full resolution trace <ArrowRight :size="12" /></a></div>
        <dl class="preview-strip">
          <div><dt>Runtime Strategy</dt><dd>openapi_remote</dd></div>
          <div><dt>Exec Mode</dt><dd>background</dd></div>
          <div><dt>Timeout</dt><dd>30s</dd></div>
          <div><dt>Retry Policy</dt><dd>2 attempts</dd></div>
          <div><dt>Rate Limit</dt><dd>60,000 TPM</dd></div>
          <div><dt>Output Limit</dt><dd>2 MB</dd></div>
        </dl>
      </article>
      <article class="settings-panel contract-test"><div class="settings-panel-heading"><h3>Contract Test</h3><UiButton size="sm" variant="primary">Run Full Test</UiButton></div><DataTable :columns="['Check', 'Result', 'Last Run']" :rows="testRows" section-id="tool-contract-test" /></article>
    </section>

    <footer class="settings-footer">
      <span><Wrench :size="14" />Config Source: Tool Catalog</span>
      <span><GitBranch :size="14" />Inherited From: System Defaults</span>
      <span><Copy :size="14" />Config Version: v12</span>
      <a>Audit History <ArrowRight :size="13" /></a>
    </footer>
  </main>
</template>

<style scoped>
.tool-tabs-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 14px;
  align-items: end;
  margin-bottom: 8px;
  border-bottom: 1px solid var(--border-subtle);
}

.tool-tabs-row .settings-tabs {
  min-height: 40px;
  margin-bottom: 0;
  border-bottom: 0;
}

.tool-filter-row {
  display: grid;
  grid-template-columns: 150px 150px 34px 34px 34px;
  gap: 8px;
  align-items: center;
  margin-bottom: 5px;
}

.tool-filter-row select,
.tool-filter-row button {
  min-height: 30px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  font-size: 12px;
}

.tool-filter-row select {
  padding: 0 10px;
}

.tool-filter-row button {
  display: grid;
  place-items: center;
  padding: 0;
  cursor: pointer;
}

.tool-filter-row button.active {
  border-color: color-mix(in srgb, var(--color-accent) 70%, var(--border-subtle));
  background: var(--surface-active);
  color: var(--color-accent);
}

.tool-list {
  padding: 0;
  overflow: hidden;
}

.tool-list :deep(tbody tr:first-child) {
  background: color-mix(in srgb, var(--color-blue) 10%, transparent);
}

.tool-list :deep(td:first-child) {
  position: relative;
  padding-left: 38px;
  color: var(--text-primary);
  font-weight: 750;
}

.tool-list :deep(td:first-child)::before {
  content: "";
  position: absolute;
  top: 50%;
  left: 12px;
  width: 17px;
  height: 17px;
  transform: translateY(-50%);
  border: 1px solid color-mix(in srgb, var(--color-success) 70%, transparent);
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--color-success) 18%, transparent);
}

.tool-list :deep(tbody tr:nth-child(2) td:first-child)::before {
  border-color: var(--color-warning);
  background: color-mix(in srgb, var(--color-warning) 18%, transparent);
}

.tool-list :deep(tbody tr:nth-child(3) td:first-child)::before {
  border-color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 18%, transparent);
}

.tool-list :deep(tbody tr:nth-child(4) td:first-child)::before {
  border-color: var(--color-blue);
  background: color-mix(in srgb, var(--color-blue) 18%, transparent);
}

.tool-list :deep(tbody tr:nth-child(5) td:first-child)::before {
  border-color: var(--color-danger);
  background: color-mix(in srgb, var(--color-danger) 18%, transparent);
}

.tool-list :deep(tbody tr:nth-child(6) td:first-child)::before {
  border-color: var(--color-warning);
  background: color-mix(in srgb, var(--color-warning) 18%, transparent);
}

.tool-list footer {
  padding: 7px 12px;
  border-top: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 11px;
}

.tool-detail-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 390px;
  gap: 10px;
  align-items: start;
  margin-top: 10px;
}

.tool-editor {
  display: grid;
  grid-template-columns: 154px minmax(0, 1fr);
  padding: 0;
  overflow: hidden;
}

.tool-tabs {
  display: grid;
  align-content: start;
  gap: 1px;
  padding: 6px;
  border-right: 1px solid var(--border-subtle);
  background: color-mix(in srgb, var(--surface-sidebar) 72%, transparent);
}

.tool-tabs button {
  min-height: 27px;
  padding: 0 8px;
  border: 0;
  border-radius: var(--radius-2);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 11px;
  text-align: left;
}

.tool-tabs .active {
  background: var(--surface-active);
  color: var(--text-primary);
}

.tool-form {
  display: grid;
  gap: 10px;
  padding: 12px;
}

.tool-form header,
.tool-form h2,
.tool-form header div {
  display: flex;
  align-items: center;
}

.tool-form header {
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-subtle);
}

.tool-form h2 {
  gap: 8px;
  font-size: 16px;
}

.tool-form h2 span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--color-success);
  font-size: 11px;
}

.tool-form header div {
  gap: 8px;
}

.tool-meta-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
}

.tool-meta-grid span {
  display: grid;
  gap: 4px;
  min-height: 48px;
  padding: 8px;
  border-right: 1px solid var(--border-subtle);
  color: var(--text-secondary);
  font-size: 11px;
}

.tool-meta-grid strong {
  color: var(--text-muted);
  font-weight: 600;
}

.tool-summary-stack {
  display: grid;
  align-content: start;
  gap: 8px;
}

.tool-summary-stack .settings-panel {
  padding: 10px 12px;
}

.tool-summary-stack .settings-kv {
  gap: 6px;
}

.tool-summary-stack :deep(th),
.tool-summary-stack :deep(td) {
  padding-block: 4px;
  font-size: 10.5px;
}

.tool-summary-tabs {
  display: flex;
  gap: 24px;
  margin-bottom: 8px;
  border-bottom: 1px solid var(--border-subtle);
}

.tool-summary-tabs button {
  height: 26px;
  padding: 0;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 11px;
}

.tool-summary-tabs .active {
  border-color: var(--color-accent);
  color: var(--text-primary);
}

.tool-support-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  margin-top: 10px;
}

.effective-preview {
  grid-column: span 3;
}

.preview-strip {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 0;
}

.preview-strip div {
  display: grid;
  gap: 3px;
  min-height: 40px;
  padding: 7px 10px;
  border-right: 1px solid var(--border-subtle);
}

.preview-strip dt {
  color: var(--text-muted);
  font-size: 10.5px;
}

.preview-strip dd {
  margin: 0;
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 800;
}

.contract-test {
  grid-column: span 2;
}
</style>
