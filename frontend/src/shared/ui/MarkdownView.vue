<script setup lang="ts">
import DOMPurify from "dompurify";
import { marked } from "marked";
import { computed } from "vue";

const props = defineProps<{
  source: string;
}>();

const html = computed(() => {
  const rendered = marked.parse(props.source, {
    async: false,
    breaks: false,
    gfm: true,
  }) as string;
  return DOMPurify.sanitize(rendered, {
    USE_PROFILES: { html: true },
  });
});
</script>

<template>
  <div class="markdown-view" v-html="html" />
</template>

<style scoped>
.markdown-view {
  margin-top: 6px;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.5;
  min-width: 0;
  overflow-wrap: anywhere;
}

.markdown-view :deep(*) {
  min-width: 0;
}

.markdown-view :deep(h1),
.markdown-view :deep(h2),
.markdown-view :deep(h3),
.markdown-view :deep(h4),
.markdown-view :deep(h5),
.markdown-view :deep(h6) {
  margin: 10px 0 5px;
  color: var(--text-primary);
  font-size: 14px;
  line-height: 1.35;
}

.markdown-view :deep(p),
.markdown-view :deep(ul),
.markdown-view :deep(ol),
.markdown-view :deep(blockquote),
.markdown-view :deep(pre) {
  margin: 6px 0 0;
}

.markdown-view :deep(ul),
.markdown-view :deep(ol) {
  padding-left: 18px;
}

.markdown-view :deep(li + li) {
  margin-top: 4px;
}

.markdown-view :deep(blockquote) {
  padding-left: 10px;
  border-left: 2px solid var(--border-strong);
  color: var(--text-muted);
}

.markdown-view :deep(pre) {
  max-width: 100%;
  overflow: auto;
  padding: 10px;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  background: color-mix(in srgb, var(--surface-base) 72%, black);
  color: var(--text-primary);
}

.markdown-view :deep(code) {
  border-radius: 4px;
  background: color-mix(in srgb, var(--surface-raised) 82%, var(--color-blue));
  color: var(--text-primary);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 12px;
}

.markdown-view :deep(:not(pre) > code) {
  padding: 1px 4px;
}

.markdown-view :deep(pre code) {
  background: transparent;
  padding: 0;
  white-space: pre;
}

.markdown-view :deep(a) {
  color: var(--color-blue);
  text-decoration: none;
}

.markdown-view :deep(a:hover) {
  text-decoration: underline;
}
</style>
