<script setup lang="ts">
import { ArrowRight, Brain, CheckCircle2, Download, GitBranch, History, Save, Shield, SlidersHorizontal, Users, Wrench, Zap } from "lucide-vue-next";

import UiButton from "@/shared/ui/UiButton.vue";

const impactRows = [
  ["Agents", "42"],
  ["Skills", "18"],
  ["Channels", "11"],
  ["Environments", "6"],
] as const;
</script>

<template>
  <main class="settings-module runtime-settings scroll-area">
    <header class="settings-page-header runtime-header">
      <div>
        <h1>Runtime Defaults (System/Platform)</h1>
        <p><span>Editing: System/Platform Defaults</span> This is the lowest precedence layer. These values are inherited and can be overridden by upper layers.</p>
      </div>
      <div class="settings-header-actions">
        <UiButton size="sm" variant="secondary"><Shield :size="14" /> Validation / Dry Run</UiButton>
        <UiButton size="sm" variant="secondary"><Download :size="14" /> Export Contract</UiButton>
        <UiButton size="sm" variant="secondary"><History :size="14" /> Change History</UiButton>
        <UiButton size="sm" variant="primary"><Save :size="14" /> Save Changes</UiButton>
      </div>
    </header>

    <nav class="settings-tabs runtime-tabs">
      <button class="active" type="button">General</button>
      <button type="button">Execution</button>
      <button type="button">Limits & Quotas</button>
      <button type="button">Guardrails</button>
      <button type="button">Observability</button>
      <button type="button">Security</button>
      <button type="button">Advanced</button>
    </nav>

    <section class="runtime-summary-grid">
      <article class="settings-panel summary-card">
        <span><SlidersHorizontal :size="20" /></span>
        <div><small>Configuration Scope</small><strong>All Environments</strong><p>Applies to all environments unless overridden.</p><a>Manage Environments <ArrowRight :size="12" /></a></div>
      </article>
      <article class="settings-panel summary-card">
        <span><Users :size="20" /></span>
        <div><small>Inherited By</small><strong>42 Agents</strong><p>18 Skills, 11 Channels, 6 Environments.</p><a>View Dependencies <ArrowRight :size="12" /></a></div>
      </article>
      <article class="settings-panel summary-card">
        <span><GitBranch :size="20" /></span>
        <div><small>Precedence</small><strong>Lowest</strong><p>Lower layers override upper layers; Turn/Run has highest priority.</p><a>View Precedence Details <ArrowRight :size="12" /></a></div>
      </article>
      <article class="settings-panel summary-card">
        <span class="success"><Shield :size="20" /></span>
        <div><small>Validation Status</small><strong>Valid</strong><p>No issues found with current defaults.</p><a>Run Validation <ArrowRight :size="12" /></a></div>
      </article>
    </section>

    <section class="runtime-body-grid">
      <div class="runtime-main-column">
        <article class="settings-panel precedence-card">
          <div class="settings-panel-heading"><h2>Runtime Configuration Precedence</h2></div>
          <p>Values flow from left (lowest) to right (highest). Higher layers override lower layers when values conflict.</p>
          <div class="precedence-flow">
            <span class="active"><em>1</em><strong>Runtime Defaults</strong><small>System/Platform</small></span>
            <ArrowRight :size="15" />
            <span><em>2</em><strong>Environment</strong><small>prod-us-east</small></span>
            <ArrowRight :size="15" />
            <span><em>3</em><strong>Agent Profile</strong><small>sales-bot</small></span>
            <ArrowRight :size="15" />
            <span><em>4</em><strong>Session</strong><small>abc123</small></span>
            <ArrowRight :size="15" />
            <span><em>5</em><strong>Turn / Run</strong><small>run_001</small></span>
          </div>
          <p class="hint">If a value is not set in a higher layer, the value from the nearest lower layer will be used.</p>
        </article>

        <section class="defaults-grid">
          <article class="settings-panel">
            <div class="settings-panel-heading"><h3><Wrench :size="16" />Tool Execution Defaults</h3></div>
            <div class="settings-form-grid">
              <label><span>Execution Mode</span><select><option>Background (default)</option></select></label>
              <label><span>Timeout</span><select><option>30s</option></select></label>
              <label><span>Retry Policy</span><select><option>2 attempts, Exponential</option></select></label>
              <label><span>Max Concurrency</span><select><option>5</option></select></label>
            </div>
            <div class="warning-note">Inline only for short, local tools. Avoid inline for long-running or I/O tools.</div>
            <a>View All Tool Settings <ArrowRight :size="12" /></a>
          </article>

          <article class="settings-panel">
            <div class="settings-panel-heading"><h3><Brain :size="16" />LLM Defaults</h3></div>
            <div class="settings-form-grid">
              <label><span>Default LLM Profile</span><select><option>gpt-4o</option></select></label>
              <label><span>Fallback Profiles</span><input value="gpt-4o-mini, claude-3.5-haiku" /></label>
              <label><span>Rate Limiter</span><select><option>Platform Default</option></select></label>
              <label><span>Max Output Tokens</span><input value="1024" /></label>
            </div>
            <a>View All LLM Settings <ArrowRight :size="12" /></a>
          </article>

          <article class="settings-panel">
            <div class="settings-panel-heading"><h3><Zap :size="16" />Observability Defaults</h3></div>
            <div class="settings-form-grid">
              <label><span>Event Retention</span><select><option>30 days</option></select></label>
              <label><span>Verbose Trace Sampling</span><select><option>20%</option></select></label>
              <label><span>Key Event Sampling</span><select><option>100%</option></select></label>
              <label><span>Log Retention</span><select><option>30 days</option></select></label>
            </div>
            <a>View All Observability Settings <ArrowRight :size="12" /></a>
          </article>
        </section>

        <section class="runtime-utility-grid">
          <article class="settings-panel"><div class="settings-panel-heading"><h3>Effective Defaults Contract</h3></div><div class="runtime-button-row"><button type="button">View JSON</button><button type="button">View YAML</button><button type="button">Download</button></div></article>
          <article class="settings-panel"><div class="settings-panel-heading"><h3>Environment Overrides</h3></div><p>See which environments override these defaults.</p><button type="button">View Overrides (6 environments)</button></article>
          <article class="settings-panel"><div class="settings-panel-heading"><h3>Validation / Dry Run</h3></div><p>Simulate how these defaults resolve for a target.</p><button type="button">Run Simulation</button></article>
        </section>

        <article class="settings-panel defaults-preview">
          <div class="settings-panel-heading"><h3>Preview (New Run with No Overrides)</h3></div>
          <p>Preview effective configuration for a new run when no overrides are set in higher layers.</p>
          <dl class="preview-strip">
            <div><dt>Execution Mode</dt><dd>Background</dd></div>
            <div><dt>Tool Timeout</dt><dd>30s</dd></div>
            <div><dt>LLM Profile</dt><dd>gpt-4o</dd></div>
            <div><dt>Max Output Tokens</dt><dd>1024</dd></div>
            <div><dt>Event Retention</dt><dd>30 days</dd></div>
            <div><dt>Trace Sampling</dt><dd>Key 100% / Verbose 20%</dd></div>
            <div><dt>More</dt><dd>18 items</dd></div>
          </dl>
        </article>
      </div>

      <aside class="runtime-side-column">
        <article class="settings-panel impact-panel">
          <div class="settings-panel-heading"><h2>Change Impact Preview</h2></div>
          <p>Shows estimated impact of changing values in this layer.</p>
          <nav><button class="active" type="button">Summary</button><button type="button">By Setting</button></nav>
          <dl>
            <div v-for="[label, count] in impactRows" :key="label"><dt>{{ label }}</dt><dd>{{ count }} <span>Will be affected</span></dd></div>
          </dl>
          <strong>Impact Level <em>High</em></strong>
          <a>View Detailed Impact Report <ArrowRight :size="12" /></a>
        </article>

        <article class="settings-panel guardrail-panel">
          <div class="settings-panel-heading"><h2>Safety & Guardrail Defaults</h2></div>
          <dl class="settings-kv">
            <div><dt>PII Redaction Policy</dt><dd>Default Policy</dd></div>
            <div><dt>Safety Guardrail Policy</dt><dd>Default Policy</dd></div>
            <div><dt>Toxicity Filter Policy</dt><dd>Default Policy</dd></div>
            <div><dt>Prompt Injection Guard Policy</dt><dd>Default Policy</dd></div>
          </dl>
          <a>View All Guardrail Settings <ArrowRight :size="12" /></a>
        </article>

        <article class="settings-panel">
          <div class="settings-panel-heading"><h2>Change Management</h2></div>
          <p>Review history and rollback if needed.</p>
          <button type="button">Change History & Rollback</button>
        </article>

        <article class="settings-panel audit-panel">
          <div class="settings-panel-heading"><h2>Audit Requirement</h2></div>
          <p>A reason is required to save changes to system defaults.</p>
          <input placeholder="Enter reason for this change..." />
          <div class="settings-header-actions"><UiButton size="sm" variant="secondary">Cancel</UiButton><UiButton size="sm" variant="primary">Save Changes</UiButton></div>
          <a>Audit Logs <ArrowRight :size="12" /></a>
        </article>
      </aside>
    </section>

    <footer class="settings-footer">
      <span><SlidersHorizontal :size="14" />Config Source: Runtime Defaults</span>
      <span><GitBranch :size="14" />Lowest precedence</span>
      <span><CheckCircle2 :size="14" />Validation: Valid</span>
    </footer>
  </main>
</template>

<style scoped>
.runtime-header {
  align-items: start;
}

.runtime-header p span {
  display: inline-flex;
  min-height: 18px;
  margin-right: 10px;
  padding: 2px 7px;
  border: 1px solid color-mix(in srgb, var(--color-warning) 50%, transparent);
  border-radius: var(--radius-1);
  color: var(--color-warning);
  font-size: 11px;
}

.runtime-tabs {
  margin-bottom: 10px;
}

.runtime-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 10px;
}

.summary-card {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr);
  gap: 12px;
  align-items: center;
  min-height: 108px;
}

.summary-card > span {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: var(--radius-3);
  background: color-mix(in srgb, var(--color-accent) 24%, transparent);
  color: var(--color-accent);
}

.summary-card > span.success {
  background: color-mix(in srgb, var(--color-success) 18%, transparent);
  color: var(--color-success);
}

.summary-card small,
.summary-card p,
.runtime-main-column p,
.runtime-side-column p {
  color: var(--text-muted);
  font-size: 11px;
}

.summary-card strong {
  display: block;
  margin: 4px 0;
  font-size: 17px;
}

.summary-card a,
.defaults-grid a,
.runtime-side-column a {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-top: 8px;
  color: var(--color-accent);
  font-size: 11px;
  text-decoration: none;
}

.runtime-body-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 10px;
  align-items: start;
}

.runtime-main-column,
.runtime-side-column {
  display: grid;
  gap: 10px;
  min-width: 0;
}

.precedence-card {
  min-height: 186px;
}

.precedence-card p {
  margin-bottom: 14px;
}

.precedence-card .hint {
  margin-top: 14px;
  color: var(--color-blue);
}

.precedence-flow {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr) auto minmax(0, 1fr) auto minmax(0, 1fr) auto minmax(0, 1fr);
  gap: 10px;
  align-items: center;
}

.precedence-flow span {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 3px 9px;
  min-height: 72px;
  padding: 12px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-raised) 72%, transparent);
}

.precedence-flow span.active {
  border-color: color-mix(in srgb, var(--color-accent) 70%, var(--border-subtle));
  background: color-mix(in srgb, var(--color-accent) 12%, var(--surface-raised));
}

.precedence-flow em {
  grid-row: span 2;
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: var(--radius-1);
  background: var(--surface-input);
  color: var(--color-accent);
  font-style: normal;
  font-weight: 800;
}

.precedence-flow strong {
  font-size: 13px;
}

.precedence-flow small {
  color: var(--text-muted);
  font-size: 10.5px;
}

.defaults-grid {
  display: grid;
  grid-template-columns: 0.9fr 0.9fr 1.2fr;
  gap: 10px;
}

.defaults-grid h3 {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}

.warning-note {
  margin-top: 10px;
  padding: 8px 10px;
  border: 1px solid color-mix(in srgb, var(--color-warning) 45%, transparent);
  border-radius: var(--radius-2);
  color: var(--color-warning);
  font-size: 11px;
}

.runtime-utility-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 10px;
}

.runtime-utility-grid button,
.runtime-button-row button,
.runtime-side-column button,
.audit-panel input {
  min-height: 30px;
  padding: 0 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  font-size: 12px;
}

.runtime-button-row {
  display: flex;
  gap: 8px;
}

.defaults-preview {
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
  min-height: 46px;
  padding: 8px 10px;
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

.impact-panel nav {
  display: flex;
  gap: 22px;
  margin: 10px 0;
  border-bottom: 1px solid var(--border-subtle);
}

.impact-panel nav button {
  height: 30px;
  padding: 0;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 11px;
}

.impact-panel nav .active {
  border-color: var(--color-accent);
  color: var(--text-primary);
}

.impact-panel dl {
  display: grid;
  gap: 10px;
  margin: 0;
}

.impact-panel dl div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: var(--text-secondary);
  font-size: 12px;
}

.impact-panel dt {
  color: var(--text-secondary);
}

.impact-panel dd {
  display: inline-flex;
  gap: 8px;
  align-items: center;
  margin: 0;
  font-weight: 800;
}

.impact-panel dd span,
.impact-panel em {
  min-height: 18px;
  padding: 2px 6px;
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--color-success) 18%, transparent);
  color: var(--color-success);
  font-size: 10.5px;
  font-style: normal;
}

.impact-panel strong {
  display: flex;
  justify-content: space-between;
  margin-top: 14px;
  color: var(--text-secondary);
  font-size: 12px;
}

.impact-panel em {
  background: color-mix(in srgb, var(--color-danger) 18%, transparent);
  color: var(--color-danger);
}

.guardrail-panel .settings-kv {
  gap: 10px;
}

.audit-panel {
  display: grid;
  gap: 10px;
}

.audit-panel .settings-header-actions {
  justify-content: end;
}
</style>
