<script setup lang="ts">
import { ArrowRight, CheckCircle2, Copy, FileClock, GitBranch, LayoutGrid, LayoutList, Lock, Save } from "lucide-vue-next";

import DataTable from "@/shared/ui/DataTable.vue";
import StatusDot from "@/shared/ui/StatusDot.vue";
import UiButton from "@/shared/ui/UiButton.vue";

const events = [
  { "Event Name": "agent.run.started", "Owner ID": "orchestration", surface_id: "run_service", "Display Name": "Run Service", "Topic Pattern": "run_service.agent.run.started", "Publication Mode": "source", "Schema Version": "1.0.0", Compatibility: "Backward", Consumers: "3", Observers: "1", "Read-only": "Yes", "Sensitivity / PII": "Low", Updated: "2h ago" },
  { "Event Name": "agent.message.received", "Owner ID": "orchestration", surface_id: "run_service", "Display Name": "Run Service", "Topic Pattern": "run_service.agent.message.received", "Publication Mode": "source", "Schema Version": "1.2.0", Compatibility: "Backward", Consumers: "4", Observers: "1", "Read-only": "Yes", "Sensitivity / PII": "Low", Updated: "2h ago" },
  { "Event Name": "tool.call.started", "Owner ID": "tool", surface_id: "tool_service", "Display Name": "Tool Service", "Topic Pattern": "tool_service.tool.call.started", "Publication Mode": "source", "Schema Version": "1.1.0", Compatibility: "Backward", Consumers: "2", Observers: "1", "Read-only": "Yes", "Sensitivity / PII": "Medium", Updated: "1d ago" },
  { "Event Name": "tool.call.completed", "Owner ID": "tool", surface_id: "tool_service", "Display Name": "Tool Service", "Topic Pattern": "tool_service.tool.call.completed", "Publication Mode": "source", "Schema Version": "1.1.0", Compatibility: "Backward", Consumers: "2", Observers: "1", "Read-only": "Yes", "Sensitivity / PII": "Medium", Updated: "1d ago" },
  { "Event Name": "chat.message.received", "Owner ID": "channel", surface_id: "web_chat", "Display Name": "Web Chat", "Topic Pattern": "web_chat.message.received", "Publication Mode": "source", "Schema Version": "1.0.0", Compatibility: "Backward", Consumers: "3", Observers: "1", "Read-only": "Yes", "Sensitivity / PII": "Low", Updated: "1d ago" },
  { "Event Name": "billing.usage.recorded", "Owner ID": "billing", surface_id: "billing_service", "Display Name": "Billing Service", "Topic Pattern": "billing_service.usage.recorded", "Publication Mode": "reduced", "Schema Version": "1.0.0", Compatibility: "Backward", Consumers: "1", Observers: "1", "Read-only": "Yes", "Sensitivity / PII": "High", Updated: "2d ago" },
  { "Event Name": "analytics.session.observed", "Owner ID": "analytics", surface_id: "analytics_service", "Display Name": "Analytics Service", "Topic Pattern": "analytics_service.session.observed", "Publication Mode": "observed", "Schema Version": "1.0.0", Compatibility: "Backward", Consumers: "0", Observers: "2", "Read-only": "Yes", "Sensitivity / PII": "Medium", Updated: "2d ago" },
];

const cards = [
  ["Subscribers", "run_service", "audit_service", "metrics_service"],
  ["Consumers", "run_state_store", "trace_service", "alert_service"],
  ["Observers", "analytics_service.session", "", ""],
] as const;
</script>

<template>
  <main class="settings-module event-settings scroll-area">
    <header class="settings-page-header">
      <div>
        <h1>Event Contracts <a>Docs</a></h1>
        <p>Central registry of event contracts that define what is published, by whom, and who consumes or observes them.</p>
      </div>
      <div class="settings-header-actions">
        <a class="learn-link">Learn more <ArrowRight :size="12" /></a>
        <UiButton size="sm" variant="primary"><FileClock :size="14" /> Create Extension Contract</UiButton>
      </div>
    </header>

    <section class="event-tabs-row">
      <nav class="settings-tabs">
        <button class="active" type="button">All Contracts</button>
        <button type="button">System Contracts</button>
        <button type="button">Custom Events</button>
        <button type="button">Extension Surfaces</button>
      </nav>
    </section>

    <section class="event-filter-row">
      <label><FileClock :size="14" /><input placeholder="Search contracts..." /></label>
      <select><option>All Owners</option></select>
      <select><option>All surface_id</option></select>
      <select><option>All Publication Modes</option></select>
      <select><option>All Compatibility</option></select>
      <select><option>All Sensitivity</option></select>
      <button class="active" type="button"><LayoutList :size="14" /></button>
      <button type="button"><LayoutGrid :size="14" /></button>
    </section>

    <section class="settings-panel event-list">
      <DataTable
        :columns="['Event Name', 'Owner ID', 'surface_id', 'Display Name', 'Topic Pattern', 'Publication Mode', 'Schema Version', 'Compatibility', 'Consumers', 'Observers', 'Read-only', 'Sensitivity / PII', 'Updated']"
        :rows="events"
        section-id="event-contracts"
      />
      <footer>Showing 1 to 7 of 142 results <span>1 2 3 4 ... 15</span></footer>
    </section>

    <section class="settings-panel event-detail">
      <header>
        <div class="event-title">
          <span><FileClock :size="18" /></span>
          <h2>agent.run.started</h2>
          <em>System</em>
          <em>Source</em>
          <strong><StatusDot tone="success" />Active</strong>
        </div>
        <div class="settings-header-actions">
          <span class="readonly"><Lock :size="14" /> Read-only</span>
          <UiButton size="sm" variant="secondary">View as JSON</UiButton>
        </div>
      </header>

      <section class="event-info-layout">
        <aside class="event-editor-tabs">
          <button class="active" type="button">Overview</button>
          <button type="button">Payload Schema</button>
          <button type="button">Example Payloads</button>
          <button type="button">Metadata</button>
          <button type="button">Subscribers (3)</button>
          <button type="button">Consumers (3)</button>
          <button type="button">Observers (1)</button>
          <button type="button">Version History (5)</button>
          <button type="button">Compatibility Report</button>
        </aside>

        <div class="event-info-grid">
          <article><h3>Identity</h3><dl class="settings-kv"><div><dt>Event Name</dt><dd>agent.run.started</dd></div><div><dt>Owner ID</dt><dd>orchestration</dd></div><div><dt>surface_id</dt><dd>run_service <Copy :size="12" /></dd></div><div><dt>Display Name</dt><dd>Run Service</dd></div><div><dt>Topic Pattern</dt><dd>run_service.agent.run.started</dd></div></dl></article>
          <article><h3>Publication</h3><dl class="settings-kv"><div><dt>Publication Mode</dt><dd>source</dd></div><div><dt>Producer</dt><dd>run_service</dd></div><div><dt>Payload Completeness</dt><dd>Full</dd></div><div><dt>Determinism</dt><dd>Event-Driven</dd></div><div><dt>Delivery Guarantees</dt><dd>At-least-once</dd></div></dl></article>
          <article><h3>Contract</h3><dl class="settings-kv"><div><dt>Schema Version</dt><dd>1.0.0</dd></div><div><dt>Compatibility</dt><dd class="settings-tone-success">Backward Compatible</dd></div><div><dt>Status</dt><dd class="settings-tone-success">Active</dd></div><div><dt>Read-only</dt><dd>Yes (System)</dd></div><div><dt>Created By</dt><dd>system</dd></div></dl></article>
          <article><h3>Governance</h3><dl class="settings-kv"><div><dt>Sensitivity / PII</dt><dd class="settings-tone-success">Low</dd></div><div><dt>Default Redaction</dt><dd>None</dd></div><div><dt>Classification</dt><dd>Operational</dd></div><div><dt>Access Policy</dt><dd>orchestration_read_policy</dd></div></dl><div class="settings-chip-row"><span>agent</span><span>run</span><span>lifecycle</span></div></article>
        </div>
      </section>
    </section>

    <section class="event-support-grid">
      <article v-for="[title, one, two, three] in cards" :key="title" class="settings-panel">
        <div class="settings-panel-heading"><h3>{{ title }}</h3></div>
        <dl class="settings-kv"><div v-if="one"><dt>{{ one }}</dt><dd class="settings-tone-success">Active</dd></div><div v-if="two"><dt>{{ two }}</dt><dd class="settings-tone-success">Active</dd></div><div v-if="three"><dt>{{ three }}</dt><dd class="settings-tone-success">Active</dd></div></dl>
        <a>View all {{ title.toLowerCase() }} <ArrowRight :size="12" /></a>
      </article>
      <article class="settings-panel"><div class="settings-panel-heading"><h3>Compatibility Report</h3></div><ul><li><CheckCircle2 :size="14" />consumers on latest schema</li><li><CheckCircle2 :size="14" />no breaking changes</li></ul><a>View full report <ArrowRight :size="12" /></a></article>
      <article class="settings-panel"><div class="settings-panel-heading"><h3>Publication Mode Guide</h3></div><dl class="settings-kv"><div><dt>source</dt><dd>Original fact event</dd></div><div><dt>reduced</dt><dd>Filtered downstream event</dd></div><div><dt>observed</dt><dd>Derived observation</dd></div></dl><a>Learn more about modes <ArrowRight :size="12" /></a></article>
    </section>

    <footer class="settings-footer">
      <span><FileClock :size="14" />Config Source: Event Contracts</span>
      <span><GitBranch :size="14" />System contracts are read-only</span>
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

.settings-page-header h1 a,
.learn-link {
  color: var(--color-blue);
  font-size: 12px;
  font-weight: 600;
  text-decoration: none;
}

.event-tabs-row {
  border-bottom: 1px solid var(--border-subtle);
}

.event-tabs-row .settings-tabs {
  margin-bottom: 0;
  border-bottom: 0;
}

.event-filter-row {
  display: grid;
  grid-template-columns: minmax(240px, 300px) 130px 140px 160px 150px 140px 34px 34px;
  gap: 8px;
  align-items: center;
  margin: 10px 0;
}

.event-filter-row label {
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

.event-filter-row input,
.event-filter-row select,
.event-filter-row button {
  min-height: 30px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  font-size: 12px;
}

.event-filter-row input {
  border: 0;
  outline: 0;
  background: transparent;
}

.event-filter-row select {
  padding: 0 8px;
}

.event-filter-row button {
  display: grid;
  place-items: center;
  padding: 0;
}

.event-filter-row button.active {
  border-color: color-mix(in srgb, var(--color-accent) 70%, var(--border-subtle));
  background: var(--surface-active);
  color: var(--color-accent);
}

.event-list {
  padding: 0;
  overflow: hidden;
}

.event-list footer {
  display: flex;
  justify-content: space-between;
  min-height: 30px;
  padding: 7px 12px;
  border-top: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 11px;
}

.event-detail {
  margin-top: 10px;
  padding: 0;
  overflow: hidden;
}

.event-detail > header,
.event-title {
  display: flex;
  align-items: center;
}

.event-detail > header {
  justify-content: space-between;
  gap: 10px;
  padding: 12px;
  border-bottom: 1px solid var(--border-subtle);
}

.event-title {
  gap: 9px;
}

.event-title > span {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--color-blue) 24%, transparent);
  color: var(--color-blue);
}

.event-title h2 {
  font-size: 16px;
}

.event-title em {
  min-height: 20px;
  padding: 3px 7px;
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--color-accent) 18%, transparent);
  color: var(--color-accent);
  font-size: 11px;
  font-style: normal;
}

.event-title strong,
.readonly {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  color: var(--color-success);
  font-size: 11px;
}

.readonly {
  color: var(--text-muted);
}

.event-info-layout {
  display: grid;
  grid-template-columns: 140px minmax(0, 1fr);
}

.event-editor-tabs {
  display: grid;
  align-content: start;
  gap: 1px;
  padding: 6px;
  border-right: 1px solid var(--border-subtle);
  background: color-mix(in srgb, var(--surface-sidebar) 72%, transparent);
}

.event-editor-tabs button {
  min-height: 28px;
  padding: 0 9px;
  border: 0;
  border-radius: var(--radius-2);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 11px;
  text-align: left;
}

.event-editor-tabs .active {
  background: var(--surface-active);
  color: var(--text-primary);
}

.event-info-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0;
  padding: 12px;
}

.event-info-grid article {
  min-width: 0;
  padding: 0 14px;
  border-right: 1px solid var(--border-subtle);
}

.event-info-grid h3 {
  margin: 0 0 12px;
  font-size: 13px;
}

.event-support-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  margin-top: 10px;
}

.event-support-grid ul {
  display: grid;
  gap: 9px;
  padding: 0;
  color: var(--text-secondary);
  font-size: 12px;
  list-style: none;
}

.event-support-grid li {
  display: flex;
  gap: 7px;
  align-items: center;
}

.event-support-grid a {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-top: 10px;
  color: var(--color-blue);
  font-size: 11px;
  text-decoration: none;
}
</style>
