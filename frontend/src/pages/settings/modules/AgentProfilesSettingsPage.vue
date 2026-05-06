<script setup lang="ts">
import { Archive, ArrowRight, Brain, CheckCircle2, Copy, GitBranch, Save, Shield, SlidersHorizontal } from "lucide-vue-next";

import DataTable from "@/shared/ui/DataTable.vue";
import StatusDot from "@/shared/ui/StatusDot.vue";
import UiButton from "@/shared/ui/UiButton.vue";

const rows = [
  { Name: "General Assistant", Description: "General purpose assistant for common tasks and Q&A", "Default LLM Profile": "gpt-4o", "Fallback LLM Profile": "claude-3.5-sonnet", Status: "Active", Scope: "Prod Staging Dev", "Updated At": "2 hours ago", "Access Grants": "6", "Default Skills": "8", Actions: "Edit / Clone" },
  { Name: "Data Analyst", Description: "Specialized in data analysis, visualization, and insights", "Default LLM Profile": "claude-3.5-sonnet", "Fallback LLM Profile": "gpt-4o", Status: "Active", Scope: "Prod Staging", "Updated At": "1 day ago", "Access Grants": "9", "Default Skills": "12", Actions: "Edit / Clone" },
  { Name: "Code Assistant", Description: "Expert in coding, debugging, and software development", "Default LLM Profile": "gpt-4o", "Fallback LLM Profile": "claude-3.5-sonnet", Status: "Active", Scope: "Prod Dev", "Updated At": "2 days ago", "Access Grants": "5", "Default Skills": "10", Actions: "Edit / Clone" },
  { Name: "Research Assistant", Description: "Web research, information gathering, and report generation", "Default LLM Profile": "gpt-4o", "Fallback LLM Profile": "gpt-4o-mini", Status: "Active", Scope: "Prod Staging", "Updated At": "3 days ago", "Access Grants": "7", "Default Skills": "11", Actions: "Edit / Clone" },
  { Name: "Customer Support", Description: "Customer support and issue resolution specialist", "Default LLM Profile": "gpt-4o-mini", "Fallback LLM Profile": "gpt-4o", Status: "Inactive", Scope: "Staging Dev", "Updated At": "5 days ago", "Access Grants": "4", "Default Skills": "6", Actions: "Edit / Clone" },
  { Name: "Security Analyst", Description: "Security analysis, threat detection, and vulnerability assessment", "Default LLM Profile": "claude-3.5-sonnet", "Fallback LLM Profile": "gpt-4o", Status: "Draft", Scope: "Prod Only", "Updated At": "1 week ago", "Access Grants": "8", "Default Skills": "14", Actions: "Edit / Clone" },
];

const tabs = ["Basic Information", "LLM Configuration", "Runtime Preferences", "Access Grants (ABAC)", "Tool Policy (ABAC)", "Skill Preferences", "Memory & Context", "Run Scope & Limits", "Effective Configuration", "Validation"];

const traceRows = [
  { "Setting Category": "LLM: Default", "Value Used": "gpt-4o", Source: "Agent Profile", Overrides: "-" },
  { "Setting Category": "LLM: Temperature", "Value Used": "0.2", Source: "Runtime Defaults", Overrides: "-" },
  { "Setting Category": "Memory: Retrieval Store", "Value Used": "semantic-store", Source: "Runtime Defaults", Overrides: "Session Override" },
  { "Setting Category": "Tool Policy: openai_api", "Value Used": "Allow", Source: "Agent Profile", Overrides: "-" },
];

const skillRows = [
  { Source: "Default Skills (from profile)", Skills: "8 skills", Result: "8 applied" },
  { Source: "User Specified (session)", Skills: "2 skills", Result: "2 applied" },
  { Source: "Surface Recommendations", Skills: "3 skills", Result: "2 applied" },
  { Source: "Excluded / Not Allowed", Skills: "1 skill", Result: "view" },
];
</script>

<template>
  <main class="settings-module agent-settings scroll-area">
    <header class="settings-page-header">
      <div>
        <h1>Agent Profiles</h1>
        <p>Define and manage agent configurations that control behavior, runtime settings, and policy. <a>Learn more</a></p>
      </div>
      <div class="settings-header-actions">
        <UiButton size="sm" variant="primary"><Brain :size="14" /> New Agent Profile</UiButton>
      </div>
    </header>

    <section class="agent-toolbar">
      <input placeholder="Search agent profiles..." />
      <select><option>All Statuses</option></select>
      <select><option>All Scopes</option></select>
      <select><option>Name (A-Z)</option></select>
    </section>

    <section class="settings-panel agent-list">
      <DataTable
        :columns="['Name', 'Description', 'Default LLM Profile', 'Fallback LLM Profile', 'Status', 'Scope', 'Updated At', 'Access Grants', 'Default Skills', 'Actions']"
        :rows="rows"
        section-id="agent-profiles"
      />
      <footer>Showing 1 to 6 of 6 results</footer>
    </section>

    <section class="agent-detail-layout">
      <div class="agent-main-column">
        <div class="agent-editor settings-panel">
        <aside class="agent-editor-tabs">
          <button v-for="(tab, index) in tabs" :key="tab" :class="{ active: index === 0 }" type="button">
            <SlidersHorizontal :size="13" />{{ tab }}
          </button>
        </aside>

        <div class="agent-form">
          <header>
            <div class="profile-title">
              <h2>General Assistant</h2>
              <span>Default</span>
              <em><StatusDot tone="success" />Active</em>
            </div>
            <div class="profile-id">ID <code>agent_general_assistant</code><Copy :size="13" /></div>
          </header>

          <div class="settings-form-grid">
            <label><span>Name</span><input value="General Assistant" /></label>
            <label><span>Category</span><select><option>General Purpose</option></select></label>
            <label class="settings-field-wide"><span>Description</span><textarea>General purpose assistant for handling common tasks, answering questions, and providing helpful assistance.</textarea></label>
            <label><span>Tags</span><input value="general, assistant, default" /></label>
            <label><span>Status</span><select><option>Active</option></select></label>
            <div class="avatar-field">
              <span>Avatar</span>
              <div>
                <span class="avatar-preview"><Brain :size="17" /></span>
                <button type="button">Change Avatar</button>
                <small>JPG, PNG or SVG. Max size 1MB.</small>
              </div>
            </div>
          </div>
        </div>

        <aside class="profile-actions">
          <h3>Profile Actions</h3>
          <button type="button"><Copy :size="14" /> Clone Profile</button>
          <button type="button"><Archive :size="14" /> Export as YAML</button>
          <button type="button"><GitBranch :size="14" /> Compare with...</button>
          <button class="danger" type="button"><Archive :size="14" /> Archive Profile</button>
        </aside>
        </div>

        <section class="agent-support-grid">
          <article class="settings-panel">
            <div class="settings-panel-heading"><h3>Run Scope</h3><a>Manage run scope & limits <ArrowRight :size="12" /></a></div>
            <dl class="settings-kv">
              <div><dt>Environment</dt><dd>Prod, Staging, Dev</dd></div>
              <div><dt>Channels</dt><dd>web_chat, agent_plan</dd></div>
              <div><dt>Session Source</dt><dd>User Session, API / Batch</dd></div>
              <div><dt>Surface</dt><dd>web_chat, api_batch, agent_plan</dd></div>
            </dl>
          </article>
          <article class="settings-panel">
            <div class="settings-panel-heading"><h3>Access Grant Scope</h3><a>Manage approval behavior <ArrowRight :size="12" /></a></div>
            <dl class="settings-kv">
              <div><dt>Profile-level</dt><dd>6 grants</dd></div>
              <div><dt>Session-level</dt><dd>2 grants</dd></div>
              <div><dt>One-time Approval</dt><dd>0 grants</dd></div>
            </dl>
          </article>
          <article class="settings-panel">
            <div class="settings-panel-heading"><h3>Change Impact</h3><a>View impact details <ArrowRight :size="12" /></a></div>
            <dl class="settings-kv">
              <div><dt>Active Sessions</dt><dd>12</dd></div>
              <div><dt>Upcoming Runs</dt><dd>~184</dd></div>
              <div><dt>Dependent Profiles</dt><dd>0</dd></div>
              <div><dt>Risk Level</dt><dd class="settings-tone-warning">Medium</dd></div>
            </dl>
          </article>
          <article class="settings-panel trace-panel">
            <div class="settings-panel-heading"><h3>Profile Resolution Trace</h3><a>View full trace <ArrowRight :size="12" /></a></div>
            <DataTable :columns="['Setting Category', 'Value Used', 'Source', 'Overrides']" :rows="traceRows" section-id="profile-resolution-trace" />
          </article>
          <article class="settings-panel">
            <div class="settings-panel-heading"><h3>Skill Set Resolution</h3><a>View details <ArrowRight :size="12" /></a></div>
            <DataTable :columns="['Source', 'Skills', 'Result']" :rows="skillRows" section-id="skill-set-resolution" />
          </article>
          <article class="settings-panel validation-panel">
            <div class="settings-panel-heading"><h3>Validation Summary</h3></div>
            <ul>
              <li><CheckCircle2 :size="14" />All checks passed</li>
              <li><CheckCircle2 :size="14" />LLM Profiles <strong>2 valid</strong></li>
              <li><CheckCircle2 :size="14" />Access Grants <strong>6 valid</strong></li>
              <li><CheckCircle2 :size="14" />Runtime Settings <strong>Valid</strong></li>
            </ul>
          </article>
        </section>
      </div>

      <aside class="agent-summary settings-panel">
        <div class="settings-panel-heading">
          <h2>Summary</h2>
        </div>
        <nav><button class="active" type="button">Overview</button><button type="button">Access Grants</button><button type="button">Default Skills</button><button type="button">Metadata</button></nav>
        <dl class="settings-kv">
          <div><dt>Status</dt><dd class="settings-tone-success">Active</dd></div>
          <div><dt>Scope</dt><dd>Prod, Staging, Dev</dd></div>
          <div><dt>Default LLM</dt><dd>gpt-4o</dd></div>
          <div><dt>Fallback LLM</dt><dd>claude-3.5-sonnet</dd></div>
          <div><dt>Access Grants</dt><dd>6</dd></div>
          <div><dt>Default Skills</dt><dd>8</dd></div>
          <div><dt>Updated By</dt><dd>Jane Doe</dd></div>
          <div><dt>Last Used</dt><dd>5 minutes ago</dd></div>
        </dl>
        <section>
          <h3>Access Grants (6)</h3>
          <p>openai_api, slack_channel_read, kibana_read</p>
        </section>
        <section>
          <h3>Default Skills (8)</h3>
          <div class="settings-chip-row"><span>search_knowledge</span><span>summarize_text</span><span>data_analysis</span><span>web_search</span></div>
        </section>
      </aside>
    </section>

    <footer class="settings-footer">
      <span><Shield :size="14" />Config Source: Profile</span>
      <span><GitBranch :size="14" />Inherited From: Runtime Defaults (v2.3)</span>
      <span><Save :size="14" />Last Saved: 2 minutes ago</span>
      <a>Audit History <ArrowRight :size="13" /></a>
    </footer>
  </main>
</template>

<style scoped>
.agent-toolbar {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) 150px 150px 150px;
  gap: 10px;
  margin-bottom: 8px;
}

.agent-toolbar input,
.agent-toolbar select {
  min-height: 30px;
  padding: 0 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  font-size: 12px;
}

.agent-list {
  padding: 0;
  overflow: hidden;
}

.agent-list :deep(tbody tr:first-child) {
  background: color-mix(in srgb, var(--color-accent) 11%, transparent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--color-accent) 78%, transparent);
}

.agent-list :deep(td:first-child) {
  position: relative;
  padding-left: 38px;
  color: var(--text-primary);
  font-weight: 750;
}

.agent-list :deep(td:first-child)::before {
  content: "";
  position: absolute;
  top: 50%;
  left: 12px;
  width: 17px;
  height: 17px;
  transform: translateY(-50%);
  border-radius: var(--radius-1);
  background: linear-gradient(135deg, var(--color-accent), color-mix(in srgb, var(--color-accent) 38%, var(--surface-raised)));
}

.agent-list :deep(tbody tr:nth-child(2) td:first-child)::before {
  background: linear-gradient(135deg, var(--color-success), var(--color-teal));
}

.agent-list :deep(tbody tr:nth-child(3) td:first-child)::before {
  background: linear-gradient(135deg, var(--color-blue), var(--color-teal));
}

.agent-list :deep(tbody tr:nth-child(4) td:first-child)::before {
  background: linear-gradient(135deg, var(--color-warning), var(--color-danger));
}

.agent-list :deep(tbody tr:nth-child(5) td:first-child)::before {
  background: linear-gradient(135deg, var(--color-accent), var(--color-blue));
}

.agent-list :deep(tbody tr:nth-child(6) td:first-child)::before {
  background: linear-gradient(135deg, var(--color-teal), var(--color-success));
}

.agent-list footer {
  min-height: 28px;
  padding: 7px 12px;
  border-top: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 11px;
}

.agent-detail-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 380px;
  gap: 10px;
  align-items: start;
  margin-top: 10px;
}

.agent-main-column {
  display: grid;
  gap: 10px;
  min-width: 0;
}

.agent-editor {
  display: grid;
  grid-template-columns: 154px minmax(0, 1fr) 168px;
  min-width: 0;
  padding: 0;
  overflow: hidden;
}

.agent-editor-tabs {
  display: grid;
  align-content: start;
  gap: 1px;
  padding: 6px;
  border-right: 1px solid var(--border-subtle);
  background: color-mix(in srgb, var(--surface-sidebar) 72%, transparent);
}

.agent-editor-tabs button {
  display: flex;
  align-items: center;
  gap: 7px;
  min-height: 27px;
  padding: 0 7px;
  border: 0;
  border-radius: var(--radius-2);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 11px;
  text-align: left;
}

.agent-editor-tabs .active {
  background: var(--surface-active);
  color: var(--text-primary);
}

.agent-form {
  display: grid;
  align-content: start;
  gap: 10px;
  padding: 12px;
}

.agent-form header,
.profile-title,
.profile-id {
  display: flex;
  align-items: center;
}

.agent-form header {
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-subtle);
}

.profile-title {
  flex-wrap: wrap;
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

.profile-id {
  gap: 7px;
  color: var(--text-muted);
  font-size: 11px;
}

.avatar-field {
  display: grid;
  gap: 4px;
  color: var(--text-secondary);
  font-size: 11px;
}

.avatar-field > div {
  display: grid;
  grid-template-columns: 36px auto minmax(0, 1fr);
  gap: 9px;
  align-items: center;
}

.avatar-preview {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--color-accent) 70%, var(--surface-raised));
  color: var(--text-on-accent);
}

.avatar-field button {
  min-height: 28px;
  padding: 0 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-raised);
  color: var(--text-primary);
  cursor: pointer;
  font-size: 11px;
  font-weight: 700;
}

.avatar-field small {
  color: var(--text-muted);
  font-size: 10.5px;
}

.profile-actions {
  padding: 12px;
  border-left: 1px solid var(--border-subtle);
}

.profile-actions h3 {
  margin-bottom: 12px;
  font-size: 13px;
}

.profile-actions button {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 32px;
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
  text-align: left;
}

.profile-actions .danger {
  color: var(--color-danger);
}

.agent-summary {
  align-self: start;
}

.agent-summary nav {
  display: flex;
  gap: 20px;
  margin-bottom: 10px;
  border-bottom: 1px solid var(--border-subtle);
}

.agent-summary nav button {
  height: 32px;
  padding: 0;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 11px;
}

.agent-summary nav .active {
  border-color: var(--color-accent);
  color: var(--text-primary);
}

.agent-summary section {
  margin-top: 16px;
}

.agent-summary h3 {
  margin-bottom: 7px;
  font-size: 13px;
}

.agent-summary p {
  color: var(--text-muted);
  font-size: 11px;
}

.agent-support-grid {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  gap: 10px;
}

.agent-support-grid > article {
  grid-column: span 4;
}

.trace-panel {
  grid-column: span 5 !important;
}

.validation-panel {
  grid-column: span 3 !important;
}

.validation-panel ul {
  display: grid;
  gap: 7px;
  padding: 0;
  color: var(--text-secondary);
  font-size: 12px;
  list-style: none;
}

.validation-panel li {
  display: flex;
  align-items: center;
  gap: 7px;
}

.validation-panel svg,
.validation-panel strong {
  color: var(--color-success);
}
</style>
