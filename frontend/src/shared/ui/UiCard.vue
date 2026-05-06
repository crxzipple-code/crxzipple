<template>
  <section class="ui-card">
    <slot />
  </section>
</template>

<style scoped>
.ui-card {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-3);
  background: var(--surface-panel);
  box-shadow: var(--shadow-raised);
}
</style>
