<script setup lang="ts">
defineProps<{
  tone?: "neutral" | "info" | "success" | "warning" | "danger";
}>();
</script>

<template>
  <span class="ui-badge" :class="`ui-badge--${tone ?? 'neutral'}`">
    <slot />
  </span>
</template>

<style scoped>
.ui-badge {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 var(--space-2);
  border: 1px solid var(--badge-border);
  border-radius: var(--radius-1);
  background: var(--badge-bg);
  color: var(--badge-text);
  font-size: var(--font-size-1);
  font-weight: 650;
  gap: var(--space-1);
  white-space: nowrap;
}

.ui-badge--neutral {
  --badge-bg: var(--surface-raised);
  --badge-border: var(--border-default);
  --badge-text: var(--text-secondary);
}

.ui-badge--info {
  --badge-bg: color-mix(in srgb, var(--color-blue) 16%, transparent);
  --badge-border: color-mix(in srgb, var(--color-blue) 34%, transparent);
  --badge-text: var(--color-blue);
}

.ui-badge--success {
  --badge-bg: color-mix(in srgb, var(--color-success) 16%, transparent);
  --badge-border: color-mix(in srgb, var(--color-success) 34%, transparent);
  --badge-text: var(--color-success);
}

.ui-badge--warning {
  --badge-bg: color-mix(in srgb, var(--color-warning) 16%, transparent);
  --badge-border: color-mix(in srgb, var(--color-warning) 34%, transparent);
  --badge-text: var(--color-warning);
}

.ui-badge--danger {
  --badge-bg: color-mix(in srgb, var(--color-danger) 16%, transparent);
  --badge-border: color-mix(in srgb, var(--color-danger) 34%, transparent);
  --badge-text: var(--color-danger);
}
</style>
