<script setup lang="ts">
import type { UiMetricCard } from "@/shared/runtime/types";
import UiBadge from "./UiBadge.vue";

defineProps<{
  metric: UiMetricCard;
}>();
</script>

<template>
  <article class="metric-card">
    <div class="metric-card__icon" :class="`metric-card__icon--${metric.tone}`" />
    <div>
      <p>{{ metric.label }}</p>
      <strong>{{ metric.value }}</strong>
      <UiBadge v-if="metric.delta" :tone="metric.tone">{{ metric.delta }}</UiBadge>
    </div>
  </article>
</template>

<style scoped>
.metric-card {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr);
  gap: var(--space-3);
  align-items: center;
  min-height: 92px;
  padding: var(--space-4);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-3);
  background: var(--surface-panel);
}

.metric-card p {
  margin: 0 0 var(--space-1);
  color: var(--text-muted);
  font-size: var(--font-size-1);
}

.metric-card strong {
  display: block;
  margin-bottom: var(--space-2);
  font-size: var(--font-size-6);
  line-height: var(--line-height-tight);
}

.metric-card__icon {
  width: 42px;
  height: 42px;
  border-radius: 999px;
  background: var(--metric-color);
}

.metric-card__icon--neutral {
  --metric-color: var(--color-gray);
}

.metric-card__icon--info {
  --metric-color: var(--color-blue);
}

.metric-card__icon--success {
  --metric-color: var(--color-success);
}

.metric-card__icon--warning {
  --metric-color: var(--color-warning);
}

.metric-card__icon--danger {
  --metric-color: var(--color-danger);
}
</style>
