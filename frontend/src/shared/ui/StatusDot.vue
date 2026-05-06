<script setup lang="ts">
defineProps<{
  tone?: "neutral" | "info" | "success" | "warning" | "danger";
  animated?: boolean;
}>();
</script>

<template>
  <span
    class="status-dot"
    :class="[
      `status-dot--${tone ?? 'neutral'}`,
      { 'status-dot--animated': animated },
    ]"
  />
</template>

<style scoped>
.status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: var(--dot-color);
}

.status-dot--animated {
  animation: status-dot-breathe 1.55s ease-in-out infinite;
  box-shadow: 0 0 0 0 color-mix(in srgb, var(--dot-color) 22%, transparent);
}

.status-dot--neutral {
  --dot-color: var(--color-gray);
}

.status-dot--info {
  --dot-color: var(--color-blue);
}

.status-dot--success {
  --dot-color: var(--color-success);
}

.status-dot--warning {
  --dot-color: var(--color-warning);
}

.status-dot--danger {
  --dot-color: var(--color-danger);
}

@keyframes status-dot-breathe {
  0%,
  100% {
    opacity: 0.72;
    transform: scale(0.88);
    box-shadow: 0 0 0 0 color-mix(in srgb, var(--dot-color) 18%, transparent);
  }

  50% {
    opacity: 1;
    transform: scale(1);
    box-shadow: 0 0 0 5px color-mix(in srgb, var(--dot-color) 12%, transparent);
  }
}

@media (prefers-reduced-motion: reduce) {
  .status-dot--animated {
    animation: none;
  }
}
</style>
