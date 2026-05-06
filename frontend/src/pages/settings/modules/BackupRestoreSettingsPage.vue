<script setup lang="ts">
import { Archive, ArrowRight, CheckCircle2, Download, GitBranch, Lock, RefreshCcw, Save, Search, Shield, Upload } from "lucide-vue-next";

import DataTable from "@/shared/ui/DataTable.vue";
import UiButton from "@/shared/ui/UiButton.vue";

const backups = [
  { Name: "backup-2025-05-18-1132", Type: "Manual backup", Scope: "Full", Environment: "Production", Size: "48.7 GB", Status: "Success", Created: "May 18, 2025 11:32 AM", "Created By": "Jane Doe", Retention: "30 days", Actions: "Download / Restore" },
  { Name: "backup-2025-05-17-0100", Type: "Scheduled backup", Scope: "Full", Environment: "Production", Size: "46.1 GB", Status: "Success", Created: "May 17, 2025 01:00 AM", "Created By": "System", Retention: "30 days", Actions: "Download / Restore" },
  { Name: "backup-2025-05-16-0100", Type: "Scheduled backup", Scope: "Full", Environment: "Production", Size: "45.9 GB", Status: "Success", Created: "May 16, 2025 01:00 AM", "Created By": "System", Retention: "30 days", Actions: "Download / Restore" },
  { Name: "backup-2025-05-15-0100", Type: "Scheduled backup", Scope: "Full", Environment: "Production", Size: "45.6 GB", Status: "Success", Created: "May 15, 2025 01:00 AM", "Created By": "System", Retention: "30 days", Actions: "Download / Restore" },
  { Name: "pre-upgrade-2025-05-14", Type: "Pre-upgrade backup", Scope: "Incremental", Environment: "Production", Size: "12.4 GB", Status: "Success", Created: "May 14, 2025 02:15 PM", "Created By": "Alex Rivera", Retention: "14 days", Actions: "Download / Restore" },
  { Name: "backup-2025-05-14-0100", Type: "Scheduled backup", Scope: "Full", Environment: "Staging", Size: "22.3 GB", Status: "Success", Created: "May 14, 2025 01:00 AM", "Created By": "System", Retention: "14 days", Actions: "Download / Restore" },
  { Name: "backup-2025-05-13-0100", Type: "Scheduled backup", Scope: "Full", Environment: "Production", Size: "44.8 GB", Status: "Failed", Created: "May 13, 2025 01:00 AM", "Created By": "System", Retention: "30 days", Actions: "Download / Restore" },
  { Name: "backup-2025-05-12-0100", Type: "Scheduled backup", Scope: "Full", Environment: "Production", Size: "44.6 GB", Status: "Success", Created: "May 12, 2025 01:00 AM", "Created By": "System", Retention: "30 days", Actions: "Download / Restore" },
];

const restoreAudit = [
  { Time: "2026-04-28 16:20", Action: "config backup created", User: "Jane Doe", Result: "Success" },
  { Time: "2026-04-27 09:12", Action: "restore dry-run", User: "John Smith", Result: "Success" },
  { Time: "2026-04-22 18:04", Action: "restore cancelled", User: "Jane Doe", Result: "Warning" },
];

const scopeItems = [
  ["Configuration", "Agent, LLM, tools, skills, runtime defaults"],
  ["Data", "sessions, events, memory indexes, artifacts"],
  ["Access Metadata", "asset descriptors only; secret values excluded"],
] as const;
</script>

<template>
  <main class="settings-module backup-settings scroll-area">
    <header class="backup-page-header">
      <div>
        <h1>Backup & Restore</h1>
        <p>Protect your platform data and recover from any failure with confidence.</p>
      </div>
      <aside>
        <span><Lock :size="13" />Encrypted storage</span>
        <span><Shield :size="13" />Dry-run required</span>
      </aside>
      <div class="settings-header-actions">
        <UiButton size="sm" variant="secondary"><RefreshCcw :size="14" /> Restore Dry Run</UiButton>
        <UiButton size="sm" variant="primary"><Archive :size="14" /> Create Backup</UiButton>
      </div>
    </header>

    <nav class="settings-tabs backup-tabs">
      <button class="active" type="button">Backups</button>
      <button type="button">Restore</button>
      <button type="button">Schedules</button>
      <button type="button">Storage</button>
      <button type="button">Audit</button>
    </nav>

    <section class="backup-summary-grid">
      <article class="settings-panel"><span><CheckCircle2 :size="15" />Last Successful Backup</span><strong>May 18, 2025 11:32 AM</strong><small>Full Backup / Success</small></article>
      <article class="settings-panel"><span><Archive :size="15" />Total Backups</span><strong>24</strong><small>Across all environments</small></article>
      <article class="settings-panel"><span><Shield :size="15" />Total Data Protected</span><strong>256.8 GB</strong><small>Compressed size</small></article>
      <article class="settings-panel"><span><RefreshCcw :size="15" />Next Scheduled Backup</span><strong>May 19, 2025 01:00 AM</strong><small>Daily at 01:00 AM (UTC)</small></article>
    </section>

    <section class="backup-filter-row">
      <label><Search :size="14" /><input placeholder="Search backups..." /></label>
      <select><option>All Environments</option></select>
      <select><option>All Types</option></select>
      <select><option>All Status</option></select>
      <select><option>All Retention</option></select>
      <button type="button"><Download :size="14" /> Export</button>
    </section>

    <section class="settings-panel backup-list">
      <DataTable
        :columns="['Name', 'Type', 'Scope', 'Environment', 'Size', 'Status', 'Created', 'Created By', 'Retention', 'Actions']"
        :rows="backups"
        section-id="backup-list"
      />
      <footer>Showing 1 to 8 of 24 backups <span>1 2 3</span></footer>
    </section>

    <section class="backup-detail-grid">
      <article class="settings-panel backup-scope-card">
        <div class="settings-panel-heading"><h2>Backup Scope</h2><span>Full runtime</span></div>
        <div class="scope-list">
          <section v-for="[title, body] in scopeItems" :key="title">
            <strong>{{ title }}</strong>
            <p>{{ body }}</p>
          </section>
        </div>
      </article>

      <article class="settings-panel restore-safety-card">
        <div class="settings-panel-heading"><h2>Restore Safety</h2><span>Required</span></div>
        <ol>
          <li><CheckCircle2 :size="14" />Compatibility check</li>
          <li><CheckCircle2 :size="14" />Restore dry-run</li>
          <li><Lock :size="14" />Admin approval</li>
          <li><RefreshCcw :size="14" />Rollback point created</li>
        </ol>
        <button type="button">Start Restore Flow</button>
      </article>

      <article class="settings-panel">
        <div class="settings-panel-heading"><h2>Encryption & Retention</h2><span>AES-256</span></div>
        <dl class="settings-kv">
          <div><dt>Storage</dt><dd>s3://runtime-backups/prod</dd></div>
          <div><dt>KMS Key</dt><dd>backup-prod-kms</dd></div>
          <div><dt>Default Retention</dt><dd>30 days</dd></div>
          <div><dt>Legal Hold</dt><dd>Off</dd></div>
        </dl>
      </article>

      <article class="settings-panel quick-actions-card">
        <div class="settings-panel-heading"><h2>Quick Actions</h2><span>Production</span></div>
        <button type="button"><Archive :size="14" /> Create Config Backup</button>
        <button type="button"><RefreshCcw :size="14" /> Run Restore Dry-run</button>
        <button type="button"><Upload :size="14" /> Upload Backup Manifest</button>
        <button type="button"><Download :size="14" /> Download Latest</button>
      </article>
    </section>

    <section class="settings-panel restore-audit-panel">
      <div class="settings-panel-heading"><h2>Restore Audit Log</h2><a>View all restore events <ArrowRight :size="12" /></a></div>
      <DataTable :columns="['Time', 'Action', 'User', 'Result']" :rows="restoreAudit" section-id="restore-audit" />
    </section>

    <footer class="settings-footer">
      <span><Archive :size="14" />Config Source: Backup & Restore</span>
      <span><GitBranch :size="14" />Backup manifest is restorable</span>
      <span><Shield :size="14" />Secrets are metadata-only</span>
      <span><Save :size="14" />Last Saved: 2 minutes ago</span>
      <a>Audit History <ArrowRight :size="13" /></a>
    </footer>
  </main>
</template>

<style scoped>
.backup-page-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  gap: 16px;
  align-items: start;
  margin-bottom: 12px;
}

.backup-page-header h1,
.backup-page-header p {
  margin: 0;
}

.backup-page-header h1 {
  font-size: 20px;
  line-height: 1.15;
}

.backup-page-header p {
  margin-top: 4px;
  color: var(--text-muted);
  font-size: 12px;
}

.backup-page-header aside {
  display: flex;
  gap: 8px;
}

.backup-page-header aside span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 28px;
  padding: 0 9px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  color: var(--text-secondary);
  font-size: 11px;
}

.backup-tabs {
  margin-bottom: 8px;
}

.backup-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 10px;
}

.backup-summary-grid article {
  min-height: 78px;
  padding: 12px;
}

.backup-summary-grid span,
.backup-summary-grid small {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--text-muted);
  font-size: 11px;
}

.backup-summary-grid strong {
  display: block;
  margin: 8px 0 5px;
  color: var(--text-primary);
  font-size: 18px;
  line-height: 1;
}

.backup-filter-row {
  display: grid;
  grid-template-columns: minmax(240px, 1fr) 150px 120px 120px 130px 86px;
  gap: 8px;
  margin-bottom: 10px;
}

.backup-filter-row label {
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

.backup-filter-row input,
.backup-filter-row select,
.backup-filter-row button {
  min-height: 30px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  font-size: 12px;
}

.backup-filter-row input {
  border: 0;
  outline: 0;
  background: transparent;
}

.backup-filter-row select {
  padding: 0 8px;
}

.backup-filter-row button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 0 8px;
}

.backup-list {
  padding: 0;
  overflow: hidden;
}

.backup-list footer {
  display: flex;
  justify-content: space-between;
  min-height: 30px;
  padding: 7px 12px;
  border-top: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 11px;
}

.backup-detail-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(0, 0.9fr) minmax(0, 0.9fr) minmax(0, 0.8fr);
  gap: 10px;
  margin-top: 10px;
}

.scope-list {
  display: grid;
  gap: 8px;
}

.scope-list section {
  padding: 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
}

.scope-list strong,
.scope-list p {
  margin: 0;
}

.scope-list strong {
  color: var(--text-primary);
  font-size: 12px;
}

.scope-list p {
  margin-top: 3px;
  color: var(--text-muted);
  font-size: 11px;
  line-height: 1.35;
}

.restore-safety-card ol {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.restore-safety-card li {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 12px;
}

.restore-safety-card li svg {
  color: var(--color-success);
}

.restore-safety-card li:nth-child(3) svg {
  color: var(--color-warning);
}

.restore-safety-card button,
.quick-actions-card button {
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

.restore-safety-card button {
  width: 100%;
  margin-top: 12px;
}

.quick-actions-card {
  display: grid;
  align-content: start;
  gap: 8px;
}

.quick-actions-card .settings-panel-heading {
  margin-bottom: 0;
}

.quick-actions-card button {
  width: 100%;
}

.restore-audit-panel {
  margin-top: 10px;
  padding-bottom: 0;
}
</style>
