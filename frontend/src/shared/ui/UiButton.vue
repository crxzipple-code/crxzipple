<script setup lang="ts">
defineProps<{
  variant?: "primary" | "secondary" | "danger" | "ghost";
  size?: "sm" | "md";
  type?: "button" | "submit" | "reset";
}>();
</script>

<template>
  <button
    class="ui-button"
    :class="[`ui-button--${variant ?? 'secondary'}`, `ui-button--${size ?? 'md'}`]"
    :type="type ?? 'button'"
  >
    <slot />
  </button>
</template>

<style scoped>
.ui-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  min-width: 0;
  border: 1px solid var(--button-border);
  border-radius: var(--radius-2);
  background: var(--button-bg);
  color: var(--button-text);
  cursor: pointer;
  font-weight: 700;
  white-space: nowrap;
}

.ui-button--sm {
  min-height: 32px;
  padding: 0 var(--space-3);
  font-size: var(--font-size-1);
}

.ui-button--md {
  min-height: 40px;
  padding: 0 var(--space-4);
  font-size: var(--font-size-2);
}

.ui-button--primary {
  --button-bg: var(--color-accent);
  --button-border: var(--color-accent);
  --button-text: var(--text-on-accent);
}

.ui-button--secondary {
  --button-bg: var(--surface-raised);
  --button-border: var(--border-default);
  --button-text: var(--text-primary);
}

.ui-button--danger {
  --button-bg: color-mix(in srgb, var(--color-danger) 18%, transparent);
  --button-border: color-mix(in srgb, var(--color-danger) 54%, transparent);
  --button-text: var(--color-danger);
}

.ui-button--ghost {
  --button-bg: transparent;
  --button-border: transparent;
  --button-text: var(--text-secondary);
}

.ui-button:disabled {
  cursor: not-allowed;
  opacity: 0.56;
}
</style>
