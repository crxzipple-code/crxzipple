<script setup lang="ts">
import { ArrowRight, CalendarDays, Download, FileClock, GitBranch, ListFilter, MoreVertical, Save, Search, User, X } from "lucide-vue-next";

const logs = [
  { time: "May 19, 2025 10:15:42 AM", actor: "Jane Doe", role: "Admin", initials: "JD", action: "Updated", resourceType: "Environment", resource: "Production", status: "Success", ip: "203.0.113.24" },
  { time: "May 19, 2025 10:12:18 AM", actor: "Michael Chen", role: "Developer", initials: "MC", action: "Created", resourceType: "Agent Profile", resource: "Support Agent", status: "Success", ip: "203.0.113.41" },
  { time: "May 19, 2025 09:58:07 AM", actor: "Alex Rivera", role: "Admin", initials: "AR", action: "Deleted", resourceType: "Channel Profile", resource: "Legacy Webhook", status: "Success", ip: "198.51.100.17" },
  { time: "May 19, 2025 09:45:33 AM", actor: "Priya Shah", role: "Developer", initials: "PS", action: "Updated", resourceType: "LLM Profile", resource: "GPT-4o Profile", status: "Success", ip: "203.0.113.55" },
  { time: "May 19, 2025 09:30:21 AM", actor: "Jane Doe", role: "Admin", initials: "JD", action: "Updated", resourceType: "Runtime Defaults", resource: "General Settings", status: "Success", ip: "203.0.113.24" },
  { time: "May 19, 2025 09:15:12 AM", actor: "Michael Chen", role: "Developer", initials: "MC", action: "Created", resourceType: "Tool", resource: "Web Search", status: "Success", ip: "203.0.113.41" },
  { time: "May 19, 2025 08:47:55 AM", actor: "System", role: "System", initials: "SY", action: "Login", resourceType: "Authentication", resource: "User Login", status: "Success", ip: "203.0.113.1" },
  { time: "May 19, 2025 08:22:10 AM", actor: "Alex Rivera", role: "Admin", initials: "AR", action: "Updated", resourceType: "Access Asset", resource: "OpenAI API Key", status: "Success", ip: "198.51.100.17" },
  { time: "May 19, 2025 07:59:44 AM", actor: "Priya Shah", role: "Developer", initials: "PS", action: "Failed", resourceType: "Environment", resource: "Test", status: "Failed", ip: "203.0.113.55" },
  { time: "May 19, 2025 07:42:31 AM", actor: "Jane Doe", role: "Admin", initials: "JD", action: "Created", resourceType: "Event", resource: "agent.run.completed", status: "Success", ip: "203.0.113.24" },
] as const;
</script>

<template>
  <main class="settings-module audit-settings scroll-area">
    <header class="settings-page-header">
      <div>
        <h1>Audit Logs</h1>
        <p>View and search audit logs for system activity and changes across the platform.</p>
      </div>
    </header>

    <section class="audit-filter-row">
      <button class="date-range" type="button">May 18, 2025 <span>-</span> May 19, 2025 <CalendarDays :size="14" /></button>
      <select><option>All Actions</option></select>
      <select><option>All Resources</option></select>
      <select><option>All Users</option></select>
      <select><option>All Status</option></select>
      <label><Search :size="14" /><input placeholder="Search logs..." /></label>
      <button type="button"><ListFilter :size="14" /> Filters</button>
      <button type="button"><Download :size="14" /> Export</button>
    </section>

    <section class="audit-layout">
      <article class="settings-panel audit-list-panel">
        <div class="audit-table">
          <div class="audit-table-head">
            <span>Time</span><span>User</span><span>Action</span><span>Resource Type</span><span>Resource</span><span>Status</span><span>IP Address</span><span></span>
          </div>
          <button v-for="log in logs" :key="`${log.time}-${log.resource}`" :class="{ active: log.resource === 'Production' }" type="button" class="audit-row">
            <span>{{ log.time }}</span>
            <span class="audit-user"><em>{{ log.initials }}</em><strong>{{ log.actor }}<small>{{ log.role }}</small></strong></span>
            <span :class="['audit-action', log.action.toLowerCase()]">{{ log.action }}</span>
            <span>{{ log.resourceType }}</span>
            <span class="audit-resource">{{ log.resource }}</span>
            <span :class="['audit-status', log.status.toLowerCase()]">{{ log.status }}</span>
            <span>{{ log.ip }}</span>
            <span class="audit-menu"><MoreVertical :size="15" /></span>
          </button>
        </div>
        <footer>
          <span>Showing 1 to 10 of 2,431 logs</span>
          <nav><button type="button">1</button><button type="button">2</button><button type="button">3</button><button type="button">4</button><span>...</span><button type="button">244</button><ArrowRight :size="13" /></nav>
        </footer>
      </article>

      <aside class="settings-panel audit-detail-panel">
        <header>
          <h2>Log Details</h2>
          <button type="button"><X :size="15" /></button>
        </header>

        <section class="detail-block">
          <h3>Time</h3>
          <p>May 19, 2025 10:15:42 AM (UTC)</p>
        </section>

        <section class="detail-block">
          <h3>User</h3>
          <div class="detail-user"><em>JD</em><strong>Jane Doe <span>(jane.doe@acme.com)</span><small>Admin</small></strong></div>
        </section>

        <section class="detail-block compact">
          <h3>Action</h3>
          <p>Updated</p>
          <h3>Resource</h3>
          <p>Environment <a>Production</a></p>
          <h3>Status</h3>
          <p class="success-dot">Success</p>
          <h3>IP Address</h3>
          <p>203.0.113.24</p>
          <h3>User Agent</h3>
          <p>Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36</p>
        </section>

        <section class="detail-block changes">
          <h3>Changes</h3>
          <pre>{
  "name": {
    "before": "Production",
    "after": "Production"
  },
  "description": {
    "before": "Primary production environment",
    "after": "Production environment for live workloads"
  }
}</pre>
        </section>
      </aside>
    </section>

    <footer class="settings-footer">
      <span><FileClock :size="14" />Config Source: Audit Logs</span>
      <span><GitBranch :size="14" />Records are immutable</span>
      <span><User :size="14" />Selected Actor: Jane Doe</span>
      <span><Save :size="14" />Filter saved locally</span>
      <a>Audit History <ArrowRight :size="13" /></a>
    </footer>
  </main>
</template>

<style scoped>
.audit-settings {
  padding-top: 38px;
}

.audit-filter-row {
  display: grid;
  grid-template-columns: 234px 130px 142px 130px 130px minmax(210px, 1fr) 86px 86px;
  gap: 12px;
  align-items: center;
  margin: 30px 0 18px;
}

.audit-filter-row label,
.audit-filter-row button,
.audit-filter-row select {
  min-height: 32px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  font-size: 12px;
}

.audit-filter-row label {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  padding: 0 10px;
  color: var(--text-muted);
}

.audit-filter-row input {
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text-primary);
}

.audit-filter-row select {
  padding: 0 10px;
}

.audit-filter-row button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 0 10px;
}

.date-range {
  justify-content: space-between !important;
}

.date-range span {
  color: var(--text-muted);
}

.audit-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 328px;
  gap: 18px;
  align-items: start;
}

.audit-list-panel,
.audit-detail-panel {
  padding: 0;
  overflow: hidden;
}

.audit-table {
  overflow: auto;
}

.audit-table-head,
.audit-row {
  display: grid;
  grid-template-columns: 170px 144px 88px 146px 128px 98px 102px 34px;
  align-items: center;
  min-width: 910px;
}

.audit-table-head {
  min-height: 46px;
  padding: 0 14px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 650;
}

.audit-row {
  width: 100%;
  min-height: 61px;
  padding: 0 14px;
  border: 0;
  border-bottom: 1px solid var(--border-subtle);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
  text-align: left;
}

.audit-row.active {
  background: color-mix(in srgb, var(--color-blue) 10%, transparent);
}

.audit-row > span {
  min-width: 0;
  overflow: hidden;
  padding-right: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.audit-user,
.detail-user {
  display: flex;
  align-items: center;
  gap: 9px;
}

.audit-user em,
.detail-user em {
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: color-mix(in srgb, var(--color-blue) 22%, transparent);
  color: var(--color-blue);
  font-size: 10px;
  font-style: normal;
  font-weight: 750;
}

.audit-user strong,
.audit-user small,
.detail-user strong,
.detail-user small {
  display: block;
  min-width: 0;
}

.audit-user small,
.detail-user small,
.detail-user span {
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 500;
}

.audit-action.deleted,
.audit-action.failed {
  color: var(--color-danger);
}

.audit-resource {
  color: var(--color-accent);
}

.audit-status {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  min-height: 20px;
  padding: 0 8px;
  border-radius: var(--radius-1);
  font-size: 11px;
  font-weight: 650;
}

.audit-status.success {
  background: color-mix(in srgb, var(--color-success) 16%, transparent);
  color: var(--color-success);
}

.audit-status.failed {
  background: color-mix(in srgb, var(--color-danger) 16%, transparent);
  color: var(--color-danger);
}

.audit-menu {
  display: grid;
  place-items: center;
  color: var(--text-muted);
}

.audit-list-panel footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 62px;
  padding: 0 16px;
  color: var(--text-muted);
  font-size: 12px;
}

.audit-list-panel footer nav {
  display: flex;
  align-items: center;
  gap: 13px;
}

.audit-list-panel footer button {
  width: 26px;
  height: 26px;
  border: 1px solid transparent;
  border-radius: var(--radius-1);
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
}

.audit-list-panel footer button:first-child {
  border-color: color-mix(in srgb, var(--color-accent) 70%, var(--border-subtle));
  background: var(--surface-active);
  color: var(--text-primary);
}

.audit-detail-panel {
  min-height: 786px;
}

.audit-detail-panel > header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 54px;
  padding: 0 14px;
}

.audit-detail-panel h2 {
  font-size: 14px;
}

.audit-detail-panel header button {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border: 0;
  background: transparent;
  color: var(--text-muted);
}

.detail-block {
  padding: 10px 14px;
}

.detail-block h3 {
  margin-bottom: 7px;
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 650;
}

.detail-block p {
  color: var(--text-primary);
  font-size: 12px;
  line-height: 1.42;
}

.detail-block a {
  display: block;
  margin-top: 3px;
  color: var(--color-accent);
}

.detail-block.compact {
  display: grid;
  gap: 6px;
}

.success-dot {
  color: var(--color-success) !important;
}

.changes pre {
  margin: 0;
  min-height: 196px;
  padding: 14px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-input) 88%, transparent);
  color: var(--color-success);
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.55;
  white-space: pre-wrap;
}
</style>
