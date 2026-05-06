<script setup lang="ts">
import { ArrowRight, Copy, GitBranch, Mail, MessageCircle, Save, Slack, Webhook, Zap } from "lucide-vue-next";

import UiButton from "@/shared/ui/UiButton.vue";

const channels = [
  ["Web Chat", "Web", "Enabled", MessageCircle],
  ["Lark Assistant", "Lark", "Enabled", MessageCircle],
  ["Slack Bot", "Slack", "Enabled", Slack],
  ["WhatsApp Business", "WhatsApp", "Enabled", MessageCircle],
  ["Public Webhook", "Webhook", "Enabled", Webhook],
  ["Email Inbound", "Email", "Enabled", Mail],
] as const;
</script>

<template>
  <main class="settings-module channel-settings scroll-area">
    <header class="channel-page-header">
      <div>
        <p>Settings / <strong>Channel Profiles</strong></p>
        <h1>Web Chat <span><i class="channel-status-dot" />Enabled</span></h1>
        <div class="channel-id">ID: <code>ch_01HZ8S4Y6N9Q2D8K7E3A1B2C</code><Copy :size="13" /></div>
      </div>
      <div class="settings-header-actions">
        <UiButton size="sm" variant="secondary"><Zap :size="14" /> Test Connection</UiButton>
        <UiButton size="sm" variant="secondary">More</UiButton>
        <UiButton size="sm" variant="primary"><Save :size="14" /> Save Changes</UiButton>
      </div>
    </header>

    <section class="channel-layout">
      <aside class="settings-panel channel-picker">
        <label><MessageCircle :size="14" /><input placeholder="Search channels..." /></label>
        <select><option>All Status</option></select>
        <div class="channel-list">
          <button v-for="[name, type, status, icon] in channels" :key="name" :class="{ active: name === 'Web Chat' }" type="button">
            <span><component :is="icon" :size="18" /></span>
            <strong>{{ name }}<small>{{ type }}</small></strong>
            <em>{{ status }}</em>
          </button>
        </div>
        <button class="new-channel" type="button">+ New Channel</button>
      </aside>

      <div class="channel-workspace">
        <nav class="settings-tabs">
          <button class="active" type="button">General</button>
          <button type="button">Authentication</button>
          <button type="button">Configuration</button>
          <button type="button">Runtime Binding</button>
          <button type="button">Message Mapping</button>
          <button type="button">Delivery & Retry</button>
          <button type="button">Permissions</button>
          <button type="button">Monitoring</button>
        </nav>

        <section class="channel-top-grid">
          <article class="settings-panel">
            <div class="settings-panel-heading"><h2>Basic Information</h2></div>
            <div class="settings-form-grid">
              <label><span>Name</span><input value="Web Chat" /></label>
              <label><span>Type</span><select><option>Web Chat</option></select></label>
              <label class="settings-field-wide"><span>Description</span><textarea>Web application chat interface for end users.</textarea></label>
            </div>
          </article>

          <article class="settings-panel">
            <div class="settings-panel-heading"><h2>Surfaces</h2></div>
            <div class="settings-form-grid">
              <label class="settings-field-wide"><span>Intake Surface</span><select><option>HTTPS</option></select><small>https://app.acme.com/chat</small></label>
              <label class="settings-field-wide"><span>Delivery Surface</span><select><option>WebSocket</option></select><small>wss://app.acme.com/ws/chat</small></label>
            </div>
          </article>

          <aside class="settings-panel">
            <div class="settings-panel-heading"><h2>Required Access Assets</h2><span>2 assets</span></div>
            <div class="asset-list"><span>asset_web_chat_public <em>Website</em></span><span>asset_chat_message_service <em>Service</em></span></div>
            <a>Manage in Access Assets <ArrowRight :size="12" /></a>
          </aside>
        </section>

        <section class="channel-mid-grid">
          <article class="settings-panel">
            <div class="settings-panel-heading"><h2>Routing Rules</h2></div>
            <dl class="settings-kv">
              <div><dt>Session Strategy</dt><dd>Reuse active session, otherwise create new</dd></div>
              <div><dt>Agent Profile</dt><dd>Support Agent (v2)</dd></div>
              <div><dt>Tenant Scope</dt><dd>From request: tenant_id</dd></div>
              <div><dt>User Scope</dt><dd>From request: user.id</dd></div>
              <div><dt>Custom Conditions</dt><dd>None</dd></div>
            </dl>
          </article>

          <article class="settings-panel binding-preview">
            <div class="settings-panel-heading"><h2>Run / Turn Binding Preview</h2></div>
            <div class="binding-flow">
              <pre>{ "text": "Hello" }</pre>
              <ArrowRight :size="14" />
              <span><strong>Session</strong>sess_01HZXQ3V2...</span>
              <ArrowRight :size="14" />
              <span><strong>Agent Profile</strong>Support Agent</span>
            </div>
            <button type="button">Test with Sample Payload</button>
          </article>

          <aside class="settings-panel policy-stack">
            <article>
              <h3>Allowed Actions Policy (ABAC)</h3>
              <dl class="settings-kv"><div><dt>Policy Source</dt><dd>channel_web_chat_access</dd></div><div><dt>Scope</dt><dd>Global</dd></div></dl>
              <button type="button">Test Policy</button>
            </article>
            <article>
              <h3>Delivery Policy</h3>
              <dl class="settings-kv"><div><dt>Retry</dt><dd>3 attempts</dd></div><div><dt>Backoff</dt><dd>Exponential</dd></div><div><dt>Dead Letter</dt><dd class="settings-tone-success">Enabled</dd></div></dl>
            </article>
            <article>
              <h3>Callback / Webhook Health</h3>
              <dl class="settings-kv"><div><dt>Status</dt><dd class="settings-tone-success">Healthy</dd></div><div><dt>Last Callback</dt><dd>2 minutes ago</dd></div><div><dt>Failure Rate</dt><dd>0.3%</dd></div></dl>
            </article>
          </aside>
        </section>

        <section class="settings-panel mapping-preview">
          <div class="settings-panel-heading"><h2>Message Mapping Preview</h2><UiButton size="sm" variant="secondary">Edit Mapping</UiButton></div>
          <div class="mapping-grid">
            <article><h3>Incoming: Channel Payload</h3><pre>{ "text": "Hello, I need help.", "user": { "id": "u_123" } }</pre></article>
            <ArrowRight :size="16" />
            <article><h3>Normalized Intake Message</h3><pre>{ "message_id": "msg_01HZX...", "content": "Hello, I need help." }</pre></article>
            <article><h3>Outgoing: Agent Response</h3><pre>{ "text": "Sure, how can I help you?" }</pre></article>
            <ArrowRight :size="16" />
            <article><h3>Channel Payload</h3><pre>{ "type": "message", "text": "Sure, how can I help you?" }</pre></article>
          </div>
        </section>

        <section class="channel-bottom-grid">
          <article class="settings-panel"><div class="settings-panel-heading"><h2>Mapping Contract Test</h2><div class="settings-header-actions"><UiButton size="sm" variant="secondary">Run Intake Test</UiButton><UiButton size="sm" variant="secondary">Run Delivery Test</UiButton></div></div><p>Validate mapping with real payloads before saving.</p></article>
          <article class="settings-panel"><div class="settings-panel-heading"><h2>Sample Payloads</h2></div><div class="settings-chip-row"><span>web_chat_text_message</span><span>web_chat_file_upload</span><span>web_chat_system_event</span><span>+ Add Sample</span></div></article>
        </section>
      </div>
    </section>

    <footer class="settings-footer">
      <span><GitBranch :size="14" />Config Source: Channel Profile</span>
      <span><Save :size="14" />Last Saved: 2 minutes ago</span>
      <a>Audit History <ArrowRight :size="13" /></a>
    </footer>
  </main>
</template>

<style scoped>
.channel-page-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}

.channel-page-header p {
  margin: 0 0 6px;
  color: var(--text-muted);
  font-size: 12px;
}

.channel-page-header h1,
.channel-page-header h1 span,
.channel-id {
  display: flex;
  align-items: center;
}

.channel-page-header h1 {
  gap: 10px;
  margin: 0;
  font-size: 20px;
}

.channel-page-header h1 span {
  gap: 6px;
  min-height: 21px;
  padding: 3px 8px;
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--color-success) 18%, transparent);
  color: var(--color-success);
  font-size: 11px;
}

.channel-id {
  gap: 8px;
  margin-top: 6px;
  color: var(--text-muted);
  font-size: 11px;
}

.channel-layout {
  display: grid;
  grid-template-columns: 210px minmax(0, 1fr);
  gap: 12px;
}

.channel-picker {
  display: grid;
  align-content: start;
  gap: 10px;
  padding: 10px;
}

.channel-picker label {
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

.channel-picker input,
.channel-picker select {
  width: 100%;
  min-height: 30px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  font-size: 12px;
}

.channel-picker input {
  min-height: 0;
  border: 0;
  outline: 0;
  background: transparent;
}

.channel-picker select {
  padding: 0 8px;
}

.channel-list {
  display: grid;
  gap: 4px;
}

.channel-list button {
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  min-height: 58px;
  padding: 8px;
  border: 0;
  border-radius: var(--radius-2);
  background: transparent;
  color: var(--text-primary);
  cursor: pointer;
  text-align: left;
}

.channel-list button.active {
  background: var(--surface-active);
}

.channel-list button > span {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border: 1px solid var(--color-blue);
  border-radius: var(--radius-2);
  color: var(--color-blue);
}

.channel-list strong {
  display: grid;
  gap: 3px;
  font-size: 12px;
}

.channel-list small {
  color: var(--text-muted);
  font-size: 11px;
}

.channel-list em {
  color: var(--color-success);
  font-size: 10.5px;
  font-style: normal;
}

.new-channel {
  min-height: 34px;
  border: 0;
  background: transparent;
  color: var(--color-accent);
  cursor: pointer;
}

.channel-workspace {
  min-width: 0;
}

.channel-top-grid,
.channel-mid-grid,
.channel-bottom-grid {
  display: grid;
  gap: 10px;
}

.channel-top-grid {
  grid-template-columns: 0.9fr 1.05fr 1.05fr;
}

.channel-mid-grid {
  grid-template-columns: 1fr 1fr 330px;
  margin-top: 10px;
}

.channel-bottom-grid {
  grid-template-columns: 1fr 1.2fr;
  margin-top: 10px;
}

.settings-form-grid small {
  color: var(--text-muted);
  font-size: 10.5px;
}

.asset-list {
  display: grid;
  gap: 8px;
  margin: 10px 0 20px;
}

.asset-list span {
  display: flex;
  justify-content: space-between;
  min-height: 34px;
  padding: 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-secondary);
  font-size: 11px;
}

.asset-list em {
  color: var(--text-muted);
  font-style: normal;
}

.binding-flow,
.mapping-grid {
  display: grid;
  align-items: center;
  gap: 10px;
}

.binding-flow {
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr) auto minmax(0, 1fr);
}

.binding-flow span {
  display: grid;
  gap: 4px;
  min-height: 70px;
  padding: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  font-size: 11px;
}

pre {
  min-height: 70px;
  margin: 0;
  padding: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 10.5px;
  white-space: pre-wrap;
}

.binding-preview button,
.policy-stack button {
  min-height: 30px;
  margin-top: 10px;
  padding: 0 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--color-accent);
  cursor: pointer;
}

.policy-stack {
  display: grid;
  gap: 10px;
}

.policy-stack article + article {
  padding-top: 10px;
  border-top: 1px solid var(--border-subtle);
}

.policy-stack h3 {
  margin: 0 0 8px;
  font-size: 13px;
}

.mapping-preview {
  margin-top: 10px;
}

.mapping-grid {
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr) minmax(0, 1fr) auto minmax(0, 1fr);
}

.mapping-grid h3 {
  margin: 0 0 8px;
  font-size: 12px;
}

.channel-bottom-grid p {
  color: var(--text-muted);
  font-size: 11px;
}

.channel-status-dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: var(--color-success);
}
</style>
