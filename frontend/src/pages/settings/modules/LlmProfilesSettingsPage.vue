<script setup lang="ts">
import { ArrowRight, Brain, CheckCircle2, Copy, GitBranch, Layers, ListFilter, Save, Search, Shield, Zap } from "lucide-vue-next";

import DataTable from "@/shared/ui/DataTable.vue";
import StatusDot from "@/shared/ui/StatusDot.vue";
import UiButton from "@/shared/ui/UiButton.vue";

const profiles = [
  { Name: "GPT-4o", Provider: "OpenAI", "Access Asset": "OpenAI API (prod) v2", "Adapter Type": "OpenAI Chat Completions", "Model / Version": "gpt-4o-2024-05-13", Status: "Active", "Context Window": "128K", "Rate Limit": "60,000", "Updated At": "2 hours ago", Actions: "Edit / Clone" },
  { Name: "GPT-4o mini", Provider: "OpenAI", "Access Asset": "OpenAI API (prod) v2", "Adapter Type": "OpenAI Chat Completions", "Model / Version": "gpt-4o-mini-2024-07-18", Status: "Active", "Context Window": "128K", "Rate Limit": "100,000", "Updated At": "1 day ago", Actions: "Edit / Clone" },
  { Name: "Claude 3.5 Sonnet", Provider: "Anthropic", "Access Asset": "Anthropic API (prod) v1", "Adapter Type": "Anthropic Messages", "Model / Version": "claude-3-5-sonnet-20240620", Status: "Active", "Context Window": "200K", "Rate Limit": "50,000", "Updated At": "3 days ago", Actions: "Edit / Clone" },
  { Name: "Claude 3 Haiku", Provider: "Anthropic", "Access Asset": "Anthropic API (prod) v1", "Adapter Type": "Anthropic Messages", "Model / Version": "claude-3-haiku-20240307", Status: "Active", "Context Window": "200K", "Rate Limit": "100,000", "Updated At": "5 days ago", Actions: "Edit / Clone" },
  { Name: "Gemini 1.5 Pro", Provider: "Google", "Access Asset": "Vertex AI (prod) v3", "Adapter Type": "Google Vertex AI", "Model / Version": "gemini-1.5-pro-002", Status: "Draft", "Context Window": "1M", "Rate Limit": "30,000", "Updated At": "1 week ago", Actions: "Edit / Clone" },
  { Name: "Mistral Large 2", Provider: "Mistral AI", "Access Asset": "Mistral API (prod) v1", "Adapter Type": "OpenAI Compatible", "Model / Version": "mistral-large-2407", Status: "Inactive", "Context Window": "128K", "Rate Limit": "20,000", "Updated At": "2 weeks ago", Actions: "Edit / Clone" },
];

const capabilityRows = [
  { Capability: "Function Calling", Status: "Supported", Source: "discovered" },
  { Capability: "JSON Mode", Status: "Supported", Source: "tested" },
  { Capability: "Streaming", Status: "Supported", Source: "tested" },
  { Capability: "Vision Input", Status: "Supported", Source: "discovered" },
  { Capability: "Tool Calls", Status: "Supported", Source: "tested" },
];
</script>

<template>
  <main class="settings-module llm-settings scroll-area">
    <header class="settings-page-header">
      <div>
        <h1>LLM Profiles</h1>
        <p>Manage large language model providers and configurations used by agents. <a>Learn more</a></p>
      </div>
      <div class="settings-header-actions">
        <UiButton size="sm" variant="primary"><Layers :size="14" /> New LLM Profile</UiButton>
      </div>
    </header>

    <section class="llm-toolbar">
      <label>
        <Search :size="14" />
        <input placeholder="Search LLM profiles..." />
      </label>
      <select><option>All Providers</option></select>
      <select><option>All Status</option></select>
      <button type="button"><ListFilter :size="14" /></button>
    </section>

    <section class="settings-panel llm-list">
      <DataTable
        :columns="['Name', 'Provider', 'Access Asset', 'Adapter Type', 'Model / Version', 'Status', 'Context Window', 'Rate Limit', 'Updated At', 'Actions']"
        :rows="profiles"
        section-id="llm-profiles"
      />
      <footer>Showing 1 to 6 of 6 results</footer>
    </section>

    <section class="llm-detail-layout">
      <div class="llm-main-column">
        <article class="settings-panel llm-editor">
          <aside class="llm-editor-tabs">
            <button class="active" type="button">Basic Information</button>
            <button type="button">Model Configuration</button>
            <button type="button">Limits & Quotas</button>
            <button type="button">Connection & Auth</button>
            <button type="button">Safety & Filtering</button>
            <button type="button">Capabilities</button>
            <button type="button">Fallback Policy</button>
            <button type="button">Rate Limiter</button>
            <button type="button">Tags & Metadata</button>
          </aside>

          <div class="llm-form">
            <header>
              <div class="profile-title">
                <h2>GPT-4o</h2>
                <em><StatusDot tone="success" />Active</em>
                <span>Default</span>
              </div>
              <div class="profile-actions">
                <UiButton size="sm" variant="danger">Delete</UiButton>
                <UiButton size="sm" variant="primary"><Save :size="14" /> Save Changes</UiButton>
              </div>
            </header>

            <div class="profile-id">ID <code>llm_gpt4o_01h8xk3z</code><Copy :size="13" /> Created by Jane Doe on 2024-05-12</div>

            <section class="llm-form-grid">
              <article>
                <h3><Shield :size="15" />Provider & Access <small>No secrets stored here</small></h3>
                <div class="settings-form-grid">
                  <label><span>Provider</span><select><option>OpenAI</option></select></label>
                  <label><span>Access Asset</span><select><option>OpenAI API (prod) v2</option></select></label>
                  <label><span>Adapter Type</span><select><option>OpenAI Chat Completions</option></select></label>
                  <label><span>Network Egress</span><select><option>internet (default)</option></select></label>
                </div>
                <a>View Access Asset <ArrowRight :size="12" /></a>
              </article>

              <article>
                <h3>Profile Status</h3>
                <div class="settings-form-grid">
                  <label><span>Status</span><select><option>Active</option></select></label>
                  <label><span>Default Profile</span><select><option>Enabled</option></select></label>
                </div>
                <p>Inactive profiles cannot be selected for runs.</p>
              </article>

              <article class="llm-notes">
                <div class="settings-form-grid">
                  <label><span>Description</span><textarea>OpenAI GPT-4o model with advanced capabilities.</textarea></label>
                  <label><span>Tags</span><input value="general, chat, production" /></label>
                </div>
              </article>
            </section>

            <dl class="llm-meta-strip">
              <div><dt>Updated At</dt><dd>2024-05-20 14:32:18 UTC+8</dd></div>
              <div><dt>Last Used</dt><dd>5 minutes ago</dd></div>
              <div><dt>Used By</dt><dd>12 agent profiles</dd></div>
              <div><dt>Runs (24h)</dt><dd>1,842</dd></div>
            </dl>
          </div>
        </article>

        <article class="settings-panel effective-preview">
          <div class="settings-panel-heading"><h3>Effective Configuration Preview</h3><a>View full configuration (JSON) <ArrowRight :size="12" /></a></div>
          <dl class="preview-strip">
            <div><dt>Provider</dt><dd>OpenAI</dd></div>
            <div><dt>Access Asset</dt><dd>OpenAI API (prod) v2</dd></div>
            <div><dt>Adapter Type</dt><dd>OpenAI Chat Completions</dd></div>
            <div><dt>Model</dt><dd>gpt-4o-2024-05-13</dd></div>
            <div><dt>Context Window</dt><dd>128,000 tokens</dd></div>
            <div><dt>Temperature</dt><dd>0.7</dd></div>
            <div><dt>Tool Calling</dt><dd>Enabled</dd></div>
            <div><dt>Streaming</dt><dd>Enabled</dd></div>
          </dl>
        </article>
      </div>

      <aside class="llm-summary-stack">
        <article class="settings-panel">
          <div class="settings-panel-heading"><h2>Summary</h2></div>
          <nav class="summary-tabs"><button class="active" type="button">Overview</button><button type="button">Access</button><button type="button">Capabilities</button><button type="button">Usage</button></nav>
          <dl class="settings-kv">
            <div><dt>Provider</dt><dd>OpenAI</dd></div>
            <div><dt>Access Asset</dt><dd>OpenAI API (prod) v2</dd></div>
            <div><dt>Adapter Type</dt><dd>OpenAI Chat Completions</dd></div>
            <div><dt>Model</dt><dd>gpt-4o-2024-05-13</dd></div>
            <div><dt>Context Window</dt><dd>128,000 tokens</dd></div>
            <div><dt>Rate Limit</dt><dd>60,000</dd></div>
            <div><dt>Status</dt><dd class="settings-tone-success">Active</dd></div>
          </dl>
        </article>

        <article class="settings-panel">
          <div class="settings-panel-heading"><h2>Health & Diagnostics</h2><a>Test Now</a></div>
          <dl class="settings-kv">
            <div><dt>Connection</dt><dd class="settings-tone-success">Healthy</dd></div>
            <div><dt>Last Test</dt><dd>2 hours ago</dd></div>
            <div><dt>Error Rate</dt><dd>0.12%</dd></div>
            <div><dt>Latency (p95)</dt><dd>842 ms</dd></div>
          </dl>
          <a class="panel-link">View diagnostics <ArrowRight :size="12" /></a>
        </article>

        <article class="settings-panel">
          <div class="settings-panel-heading"><h2>Capabilities</h2><span>Source</span></div>
          <DataTable :columns="['Capability', 'Status', 'Source']" :rows="capabilityRows" section-id="llm-capabilities" />
          <a class="panel-link">View capability details <ArrowRight :size="12" /></a>
        </article>
      </aside>
    </section>

    <footer class="settings-footer">
      <span><Brain :size="14" />Config Source: LLM Profile</span>
      <span><GitBranch :size="14" />Inherited From: Runtime Defaults</span>
      <span><Save :size="14" />Last Saved: 2 minutes ago</span>
    </footer>
  </main>
</template>

<style scoped>
.llm-toolbar {
  display: grid;
  grid-template-columns: minmax(300px, 1fr) 150px 150px 34px;
  gap: 10px;
  align-items: center;
  margin-bottom: 10px;
}

.llm-toolbar label {
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

.llm-toolbar input,
.llm-toolbar select,
.llm-toolbar button {
  min-height: 30px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  font-size: 12px;
}

.llm-toolbar input {
  border: 0;
  outline: 0;
  background: transparent;
}

.llm-toolbar select {
  padding: 0 10px;
}

.llm-toolbar button {
  display: grid;
  place-items: center;
  padding: 0;
}

.llm-list {
  padding: 0;
  overflow: hidden;
}

.llm-list :deep(tbody tr:first-child) {
  background: color-mix(in srgb, var(--color-blue) 10%, transparent);
}

.llm-list :deep(td:first-child) {
  position: relative;
  padding-left: 38px;
  color: var(--text-primary);
  font-weight: 750;
}

.llm-list :deep(td:first-child)::before {
  content: "";
  position: absolute;
  top: 50%;
  left: 12px;
  width: 18px;
  height: 18px;
  transform: translateY(-50%);
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--color-gray) 22%, transparent);
}

.llm-list footer {
  min-height: 28px;
  padding: 7px 12px;
  border-top: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 11px;
}

.llm-detail-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 10px;
  align-items: start;
  margin-top: 10px;
}

.llm-main-column {
  display: grid;
  gap: 10px;
  min-width: 0;
}

.llm-editor {
  display: grid;
  grid-template-columns: 160px minmax(0, 1fr);
  padding: 0;
  overflow: hidden;
}

.llm-editor-tabs {
  display: grid;
  align-content: start;
  gap: 1px;
  padding: 6px;
  border-right: 1px solid var(--border-subtle);
  background: color-mix(in srgb, var(--surface-sidebar) 72%, transparent);
}

.llm-editor-tabs button {
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

.llm-editor-tabs .active {
  background: var(--surface-active);
  color: var(--text-primary);
}

.llm-form {
  display: grid;
  gap: 10px;
  padding: 12px;
}

.llm-form header,
.profile-title,
.profile-actions,
.profile-id,
.llm-form-grid h3,
.panel-link {
  display: flex;
  align-items: center;
}

.llm-form header {
  justify-content: space-between;
  gap: 10px;
}

.profile-title {
  gap: 8px;
}

.profile-title h2 {
  font-size: 16px;
}

.profile-title span,
.profile-title em {
  min-height: 20px;
  padding: 3px 7px;
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--color-accent) 18%, transparent);
  color: var(--color-accent);
  font-size: 11px;
  font-style: normal;
}

.profile-title em {
  display: inline-flex;
  gap: 5px;
  background: transparent;
  color: var(--color-success);
}

.profile-actions {
  gap: 8px;
}

.profile-id {
  gap: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 11px;
}

.llm-form-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 330px;
  gap: 10px;
}

.llm-form-grid article,
.llm-meta-strip,
.preview-strip {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel-soft) 74%, transparent);
}

.llm-form-grid article {
  display: grid;
  gap: 10px;
  padding: 12px;
}

.llm-form-grid article:first-child {
  min-width: 0;
}

.llm-notes {
  grid-column: 1 / -1;
}

.llm-form-grid h3 {
  gap: 7px;
  font-size: 13px;
}

.llm-form-grid small {
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 500;
}

.llm-form-grid a {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--color-accent);
  font-size: 11px;
  text-decoration: none;
}

.llm-form-grid p {
  color: var(--text-muted);
  font-size: 11px;
}

.llm-meta-strip,
.preview-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.preview-strip {
  grid-template-columns: repeat(8, minmax(0, 1fr));
}

.llm-meta-strip div,
.preview-strip div {
  display: grid;
  gap: 4px;
  min-height: 42px;
  padding: 8px 10px;
  border-right: 1px solid var(--border-subtle);
}

.llm-meta-strip dt,
.preview-strip dt {
  color: var(--text-muted);
  font-size: 10.5px;
}

.llm-meta-strip dd,
.preview-strip dd {
  margin: 0;
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 800;
}

.llm-summary-stack {
  display: grid;
  align-content: start;
  gap: 8px;
}

.llm-summary-stack .settings-panel {
  padding: 10px 12px;
}

.summary-tabs {
  display: flex;
  gap: 22px;
  margin-bottom: 8px;
  border-bottom: 1px solid var(--border-subtle);
}

.summary-tabs button {
  height: 28px;
  padding: 0;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 11px;
}

.summary-tabs .active {
  border-color: var(--color-accent);
  color: var(--text-primary);
}

.panel-link {
  gap: 5px;
  margin-top: 8px;
  color: var(--color-accent);
  font-size: 11px;
  text-decoration: none;
}

.llm-summary-stack :deep(th),
.llm-summary-stack :deep(td) {
  padding-block: 4px;
  font-size: 10.5px;
}
</style>
