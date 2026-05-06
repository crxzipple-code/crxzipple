<script setup lang="ts">
import { ArrowRight, CheckCircle2, Copy, GitBranch, LayoutGrid, LayoutList, ListFilter, Package, PackagePlus, Search, Shield } from "lucide-vue-next";

import DataTable from "@/shared/ui/DataTable.vue";
import StatusDot from "@/shared/ui/StatusDot.vue";
import UiButton from "@/shared/ui/UiButton.vue";

const skills = [
  { Name: "Search Knowledge Base", Category: "Retrieval", "Capability Requirements": "3 capabilities", "Access Requirements": "-", "Supported Surfaces": "web_chat agent_plan api_batch", Status: "Active", Version: "1.2.0", "Updated At": "2 hours ago", "Owner / Package": "system/skills/search_kb", Actions: "Edit / Clone" },
  { Name: "Data Analysis", Category: "Analysis", "Capability Requirements": "4 capabilities", "Access Requirements": "-", "Supported Surfaces": "web_chat agent_plan api_batch", Status: "Active", Version: "1.3.1", "Updated At": "1 day ago", "Owner / Package": "system/skills/data_analysis", Actions: "Edit / Clone" },
  { Name: "Document Summarization", Category: "NLP", "Capability Requirements": "2 capabilities", "Access Requirements": "-", "Supported Surfaces": "web_chat agent_plan", Status: "Active", Version: "1.1.0", "Updated At": "1 day ago", "Owner / Package": "system/skills/doc_summary", Actions: "Edit / Clone" },
  { Name: "Code Execution", Category: "Utility", "Capability Requirements": "2 capabilities", "Access Requirements": "Sandbox recommended", "Supported Surfaces": "agent_plan", Status: "Active", Version: "1.0.4", "Updated At": "2 days ago", "Owner / Package": "system/skills/code_exec", Actions: "Edit / Clone" },
  { Name: "Email Processing", Category: "Automation", "Capability Requirements": "3 capabilities", "Access Requirements": "Email Send optional", "Supported Surfaces": "agent_plan api_batch", Status: "Draft", Version: "0.9.0", "Updated At": "5 days ago", "Owner / Package": "acme/skills/email_proc", Actions: "Edit / Clone" },
  { Name: "Web Research", Category: "Research", "Capability Requirements": "4 capabilities", "Access Requirements": "-", "Supported Surfaces": "web_chat agent_plan api_batch", Status: "Inactive", Version: "1.0.0", "Updated At": "1 week ago", "Owner / Package": "system/skills/web_research", Actions: "Edit / Clone" },
];

const capabilityRows = [
  { Capability: "semantic_search", Purpose: "Search knowledge with semantic similarity", Required: "Yes", Fallback: "Yes" },
  { Capability: "text_reranking", Purpose: "Re-rank search results", Required: "Yes", Fallback: "No" },
];

const accessRows = [
  { "Access Type": "knowledge_base_read", Purpose: "Read knowledge content", Required: "Yes", "Scope Hint": "profile/session" },
];

const contractRows = [
  { Check: "Input schema validation", Result: "Pass" },
  { Check: "Output schema validation", Result: "Pass" },
  { Check: "Example I/O validation", Result: "Pass" },
  { Check: "Reference resolution check", Result: "Pass" },
];
</script>

<template>
  <main class="settings-module skill-settings scroll-area">
    <header class="settings-page-header">
      <div>
        <h1>Skill Catalog</h1>
        <p>Define reusable skills that declare capability requirements and execution guidance. <a>Learn more</a></p>
      </div>
      <div class="settings-header-actions">
        <UiButton size="sm" variant="primary"><PackagePlus :size="14" /> New Skill</UiButton>
      </div>
    </header>

    <section class="skill-tabs-row">
      <nav class="settings-tabs">
        <button class="active" type="button">All Skills</button>
        <button type="button">My Skills</button>
        <button type="button">System Skills</button>
        <button type="button">Deprecated</button>
      </nav>

      <div class="skill-filter-row">
        <select><option>All Categories</option></select>
        <select><option>All Status</option></select>
        <button class="active" type="button"><LayoutList :size="14" /></button>
        <button type="button"><LayoutGrid :size="14" /></button>
      </div>
    </section>

    <section class="skill-search-row">
      <label><Search :size="14" /><input placeholder="Search skills..." /></label>
      <button type="button"><ListFilter :size="14" /></button>
    </section>

    <section class="settings-panel skill-table">
      <DataTable
        :columns="['Name', 'Category', 'Capability Requirements', 'Access Requirements', 'Supported Surfaces', 'Status', 'Version', 'Updated At', 'Owner / Package', 'Actions']"
        :rows="skills"
        section-id="skill-catalog"
      />
      <footer>Showing 1 to 6 of 6 results</footer>
    </section>

    <section class="skill-detail-layout">
      <div class="skill-main-column">
        <article class="settings-panel skill-editor">
          <aside class="skill-editor-tabs">
            <button class="active" type="button">Overview</button>
            <button type="button">SKILL.md Preview</button>
            <button type="button">Input Contract</button>
            <button type="button">Output Contract</button>
            <button type="button">Capability Requirements</button>
            <button type="button">Access Requirements</button>
            <button type="button">Memory & Context</button>
            <button type="button">Supported Surfaces</button>
            <button type="button">Required Files</button>
            <button type="button">Runtime Settings</button>
            <button type="button">Testing & Debug</button>
          </aside>

          <div class="skill-form">
            <header>
              <div class="skill-title">
                <span class="skill-icon"><Search :size="17" /></span>
                <h2>Search Knowledge Base</h2>
                <em><StatusDot tone="success" />Active</em>
                <span>System Skill</span>
              </div>
              <div class="profile-id">ID <code>skill_search_kb</code><Copy :size="13" /></div>
            </header>

            <section class="skill-form-grid">
              <article>
                <h3>Basic Information</h3>
                <div class="settings-form-grid">
                  <label><span>Name</span><input value="Search Knowledge Base" /></label>
                  <label><span>Category</span><select><option>Retrieval</option></select></label>
                  <label class="settings-field-wide"><span>Description</span><textarea>Search and retrieve relevant information from vector databases and knowledge bases using semantic similarity.</textarea></label>
                  <label><span>Tags</span><input value="search, retrieval, knowledge, vector" /></label>
                </div>
              </article>

              <article>
                <div class="settings-panel-heading"><h3>Capability Requirements (2)</h3><a>Manage capability mappings <ArrowRight :size="12" /></a></div>
                <DataTable :columns="['Capability', 'Purpose', 'Required', 'Fallback']" :rows="capabilityRows" section-id="skill-capabilities" />
              </article>

              <article>
                <div class="settings-panel-heading"><h3>Access Requirements (1)</h3><a>View in Access Center <ArrowRight :size="12" /></a></div>
                <DataTable :columns="['Access Type', 'Purpose', 'Required', 'Scope Hint']" :rows="accessRows" section-id="skill-access" />
              </article>

              <article>
                <div class="settings-panel-heading"><h3>Supported Surfaces</h3><a>View surface matrix <ArrowRight :size="12" /></a></div>
                <div class="settings-chip-row"><span>web_chat</span><span>agent_plan</span><span>api_batch</span><span>tool_service</span></div>
              </article>
            </section>
          </div>
        </article>

        <section class="skill-support-grid">
          <article class="settings-panel"><div class="settings-panel-heading"><h3>Required Files / Resources</h3><a>View all files <ArrowRight :size="12" /></a></div><div class="settings-chip-row"><span>prompts/search_prompt.md</span><span>schemas/input.json</span><span>schemas/output.json</span></div></article>
          <article class="settings-panel"><div class="settings-panel-heading"><h3>Compatibility</h3><a>View compatibility matrix <ArrowRight :size="12" /></a></div><dl class="settings-kv"><div><dt>Min Runtime Version</dt><dd>v1.2.0</dd></div><div><dt>Compatible Surfaces</dt><dd>4 surfaces</dd></div><div><dt>Deprecation Status</dt><dd>Active</dd></div></dl></article>
          <article class="settings-panel"><div class="settings-panel-heading"><h3>Skill Package Source</h3><a>Open repository <ArrowRight :size="12" /></a></div><dl class="settings-kv"><div><dt>Source Type</dt><dd>Local Git</dd></div><div><dt>Repository</dt><dd>git@github.com/skills.git</dd></div><div><dt>Path</dt><dd>skills/search_kb</dd></div></dl></article>
          <article class="settings-panel contract-test"><div class="settings-panel-heading"><h3>Contract Test</h3><UiButton size="sm" variant="secondary">Run Contract Tests</UiButton></div><DataTable :columns="['Check', 'Result']" :rows="contractRows" section-id="skill-contract-test" /></article>
        </section>

        <article class="settings-panel effective-preview">
          <div class="settings-panel-heading"><h3>Effective Configuration Preview</h3><a>View full configuration (JSON) <ArrowRight :size="12" /></a></div>
          <dl class="preview-strip">
            <div><dt>Agent Profile</dt><dd>General Assistant</dd></div>
            <div><dt>Surface</dt><dd>web_chat</dd></div>
            <div><dt>Execution Mode</dt><dd>Inline</dd></div>
            <div><dt>Timeout</dt><dd>60s</dd></div>
            <div><dt>Retry Policy</dt><dd>2</dd></div>
            <div><dt>Network Egress</dt><dd>Allowed</dd></div>
            <div><dt>Memory Retrieval</dt><dd>semantic-store</dd></div>
          </dl>
        </article>
      </div>

      <aside class="settings-panel resolution-preview">
        <h2>Resolution Preview</h2>
        <p>For agent profile: General Assistant</p>
        <p>Surface: <strong>web_chat</strong></p>
        <div class="resolution-step"><Shield :size="17" /><span><strong>Declared Requirement</strong><small>2 capabilities declared</small></span></div>
        <div class="resolution-step"><GitBranch :size="17" /><span><strong>Capability Mapping</strong><small>2 mappings found</small></span></div>
        <div class="resolution-step"><Package :size="17" /><span><strong>Resolved Tool / Access / Runtime</strong><small>2 tools, 1 access</small></span></div>
        <div class="resolution-step"><CheckCircle2 :size="17" /><span><strong>Access Authorization</strong><small>All required access available</small></span></div>
        <div class="resolution-step"><CheckCircle2 :size="17" /><span><strong>Execution Readiness</strong><small>Ready</small></span></div>
        <a>View full resolution trace <ArrowRight :size="12" /></a>
      </aside>
    </section>

    <footer class="settings-footer">
      <span><Package :size="14" />Config Source: Skill Package</span>
      <span><GitBranch :size="14" />Inherited From: System Defaults (v2.3)</span>
      <span><Shield :size="14" />Config Version: v12</span>
      <a>Audit History <ArrowRight :size="13" /></a>
    </footer>
  </main>
</template>

<style scoped>
.skill-tabs-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 14px;
  align-items: end;
  margin-bottom: 8px;
  border-bottom: 1px solid var(--border-subtle);
}

.skill-tabs-row .settings-tabs {
  min-height: 40px;
  margin-bottom: 0;
  border-bottom: 0;
}

.skill-filter-row,
.skill-search-row {
  display: grid;
  gap: 8px;
  align-items: center;
}

.skill-filter-row {
  grid-template-columns: 150px 150px 34px 34px;
  margin-bottom: 5px;
}

.skill-search-row {
  grid-template-columns: minmax(280px, 300px) 34px;
  margin-bottom: 8px;
}

.skill-search-row label {
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

.skill-search-row input,
.skill-filter-row select,
.skill-filter-row button,
.skill-search-row button {
  min-height: 30px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  font-size: 12px;
}

.skill-search-row input {
  border: 0;
  outline: 0;
  background: transparent;
}

.skill-filter-row select {
  padding: 0 10px;
}

.skill-filter-row button,
.skill-search-row button {
  display: grid;
  place-items: center;
  padding: 0;
}

.skill-filter-row button.active {
  border-color: color-mix(in srgb, var(--color-accent) 70%, var(--border-subtle));
  background: var(--surface-active);
  color: var(--color-accent);
}

.skill-table {
  padding: 0;
  overflow: hidden;
}

.skill-table :deep(tbody tr:first-child) {
  background: color-mix(in srgb, var(--color-success) 8%, transparent);
}

.skill-table :deep(td:first-child) {
  position: relative;
  padding-left: 38px;
  color: var(--text-primary);
  font-weight: 750;
}

.skill-table :deep(td:first-child)::before {
  content: "";
  position: absolute;
  top: 50%;
  left: 12px;
  width: 18px;
  height: 18px;
  transform: translateY(-50%);
  border: 1px solid var(--color-success);
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--color-success) 18%, transparent);
}

.skill-table footer {
  min-height: 28px;
  padding: 7px 12px;
  border-top: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 11px;
}

.skill-detail-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 330px;
  gap: 10px;
  align-items: start;
  margin-top: 10px;
}

.skill-main-column {
  display: grid;
  gap: 10px;
  min-width: 0;
}

.skill-editor {
  display: grid;
  grid-template-columns: 154px minmax(0, 1fr);
  padding: 0;
  overflow: hidden;
}

.skill-editor-tabs {
  display: grid;
  align-content: start;
  gap: 1px;
  padding: 6px;
  border-right: 1px solid var(--border-subtle);
  background: color-mix(in srgb, var(--surface-sidebar) 72%, transparent);
}

.skill-editor-tabs button {
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

.skill-editor-tabs .active {
  background: var(--surface-active);
  color: var(--text-primary);
}

.skill-form {
  display: grid;
  gap: 10px;
  padding: 12px;
}

.skill-form header,
.skill-title,
.profile-id,
.resolution-step,
.resolution-preview a {
  display: flex;
  align-items: center;
}

.skill-form header {
  justify-content: space-between;
  gap: 10px;
}

.skill-title {
  gap: 8px;
}

.skill-icon {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border: 1px solid var(--color-success);
  border-radius: var(--radius-2);
  color: var(--color-success);
}

.skill-title h2 {
  font-size: 16px;
}

.skill-title span:not(.skill-icon),
.skill-title em {
  min-height: 20px;
  padding: 3px 7px;
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--color-accent) 18%, transparent);
  color: var(--color-accent);
  font-size: 11px;
  font-style: normal;
}

.skill-title em {
  display: inline-flex;
  gap: 5px;
  background: transparent;
  color: var(--color-success);
}

.profile-id {
  gap: 8px;
  color: var(--text-muted);
  font-size: 11px;
}

.skill-form-grid {
  display: grid;
  grid-template-columns: 0.85fr 1fr 1fr;
  gap: 10px;
}

.skill-form-grid article {
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel-soft) 72%, transparent);
}

.skill-form-grid h3 {
  margin-bottom: 10px;
  font-size: 13px;
}

.skill-support-grid {
  display: grid;
  grid-template-columns: 0.9fr 0.9fr 0.9fr 1.2fr;
  gap: 10px;
}

.contract-test :deep(th),
.contract-test :deep(td) {
  padding-block: 4px;
}

.effective-preview {
  min-width: 0;
}

.preview-strip {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
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

.resolution-preview {
  display: grid;
  gap: 10px;
  align-content: start;
}

.resolution-preview h2 {
  font-size: 14px;
}

.resolution-preview p {
  color: var(--text-muted);
  font-size: 11px;
}

.resolution-step {
  gap: 10px;
  min-height: 56px;
  padding: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel-soft) 78%, transparent);
}

.resolution-step svg {
  color: var(--color-success);
}

.resolution-step span {
  display: grid;
  gap: 3px;
}

.resolution-step small {
  color: var(--text-muted);
  font-size: 10.5px;
}

.resolution-preview a {
  gap: 5px;
  color: var(--color-accent);
  font-size: 11px;
  text-decoration: none;
}
</style>
