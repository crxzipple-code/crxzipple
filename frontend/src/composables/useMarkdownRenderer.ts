import { computed, ref, watch, type Ref } from "vue";

type MarkdownRenderer = (source: string) => string;

function escapeHtml(source: string) {
  return source
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderPlainText(source: string) {
  return escapeHtml(source).replace(/\n/g, "<br />");
}

let cachedRenderer: MarkdownRenderer | null = null;
let cachedLoader: Promise<MarkdownRenderer> | null = null;

async function loadMarkdownRenderer() {
  if (cachedRenderer) {
    return cachedRenderer;
  }
  if (!cachedLoader) {
    cachedLoader = import("@/lib/markdown").then((module) => {
      cachedRenderer = module.renderMarkdown;
      return cachedRenderer;
    });
  }
  return cachedLoader;
}

export function useMarkdownRenderer(sourceCount: Ref<number>) {
  const renderer = ref<MarkdownRenderer>(cachedRenderer ?? renderPlainText);

  async function ensureMarkdownRenderer() {
    const loaded = await loadMarkdownRenderer();
    renderer.value = loaded;
  }

  watch(
    sourceCount,
    (count) => {
      if (count > 0) {
        void ensureMarkdownRenderer();
      }
    },
    { immediate: true },
  );

  return {
    markdownReady: computed(() => renderer.value !== renderPlainText),
    renderMarkdown: (source: string) => renderer.value(source),
    ensureMarkdownRenderer,
  };
}
