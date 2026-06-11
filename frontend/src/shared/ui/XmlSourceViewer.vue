<script setup lang="ts">
import { ChevronDown, ChevronRight } from "lucide-vue-next";
import { computed, ref, watch } from "vue";

import { useI18n } from "@/shared/i18n";

const props = withDefaults(
  defineProps<{
    source: string;
    maxHeight?: string;
  }>(),
  {
    maxHeight: "min(60vh, 620px)",
  },
);

const { t } = useI18n();
const foldedLineNumbers = ref<Set<number>>(new Set());

interface SourceLine {
  lineNumber: number;
  text: string;
  foldEndLineNumber: number | null;
}

interface OpenTagFrame {
  tag: string;
  lineNumber: number;
}

interface FoldRange {
  start: number;
  end: number;
}

const sourceLines = computed<SourceLine[]>(() => buildXmlSourceLines(props.source));
const foldableLineNumbers = computed(() => (
  new Set(sourceLines.value.filter((line) => line.foldEndLineNumber !== null).map((line) => line.lineNumber))
));
const hiddenLineNumbers = computed(() => buildHiddenLineNumbers(
  sourceLines.value,
  foldedLineNumbers.value,
));
const visibleSourceLines = computed(() => (
  sourceLines.value.filter((line) => !hiddenLineNumbers.value.has(line.lineNumber))
));
const hasFoldableLines = computed(() => foldableLineNumbers.value.size > 0);
const viewerStyle = computed(() => ({
  "--xml-source-max-height": props.maxHeight,
}));

watch(
  () => props.source,
  () => {
    foldedLineNumbers.value = new Set();
  },
);

function toggleLineFold(lineNumber: number) {
  const next = new Set(foldedLineNumbers.value);
  if (next.has(lineNumber)) {
    next.delete(lineNumber);
  } else {
    next.add(lineNumber);
  }
  foldedLineNumbers.value = next;
}

function collapseAllLines() {
  foldedLineNumbers.value = new Set(foldableLineNumbers.value);
}

function expandAllLines() {
  foldedLineNumbers.value = new Set();
}

function isLineFolded(lineNumber: number) {
  return foldedLineNumbers.value.has(lineNumber);
}

function foldedLineCount(line: SourceLine) {
  if (line.foldEndLineNumber === null || !isLineFolded(line.lineNumber)) return 0;
  return Math.max(line.foldEndLineNumber - line.lineNumber, 0);
}

function sourceLineClasses(line: SourceLine) {
  return {
    "xml-source-viewer__line--foldable": line.foldEndLineNumber !== null,
    "xml-source-viewer__line--folded": isLineFolded(line.lineNumber),
  };
}

function buildXmlSourceLines(source: string): SourceLine[] {
  const rawLines = source.length > 0 ? source.split(/\r?\n/) : [];
  const lines: SourceLine[] = rawLines.map((text, index) => ({
    lineNumber: index + 1,
    text,
    foldEndLineNumber: null,
  }));
  const byLineNumber = new Map(lines.map((line) => [line.lineNumber, line]));
  const stack: OpenTagFrame[] = [];

  for (const line of lines) {
    const closeTags = closingTagsForLine(line.text);
    for (const tag of closeTags) {
      const openFrameIndex = findMatchingOpenFrame(stack, tag);
      if (openFrameIndex === -1) continue;
      const [frame] = stack.splice(openFrameIndex, 1);
      if (!frame || frame.lineNumber >= line.lineNumber) continue;
      const openLine = byLineNumber.get(frame.lineNumber);
      if (openLine) {
        openLine.foldEndLineNumber = line.lineNumber;
      }
    }

    const openTag = openingTagForFold(line.text);
    if (openTag) {
      stack.push({ tag: openTag, lineNumber: line.lineNumber });
    }
  }

  return lines;
}

function buildHiddenLineNumbers(
  lines: SourceLine[],
  foldedLines: Set<number>,
) {
  const ranges = mergeFoldRanges(
    lines
      .filter((line) => (
        line.foldEndLineNumber !== null
        && foldedLines.has(line.lineNumber)
        && line.lineNumber < line.foldEndLineNumber
      ))
      .map((line) => ({
        start: line.lineNumber + 1,
        end: line.foldEndLineNumber as number,
      })),
  );
  const hidden = new Set<number>();
  for (const range of ranges) {
    for (let lineNumber = range.start; lineNumber <= range.end; lineNumber += 1) {
      hidden.add(lineNumber);
    }
  }
  return hidden;
}

function mergeFoldRanges(ranges: FoldRange[]) {
  const sorted = [...ranges].sort((left, right) => (
    left.start === right.start ? left.end - right.end : left.start - right.start
  ));
  const merged: FoldRange[] = [];
  for (const range of sorted) {
    const previous = merged[merged.length - 1];
    if (!previous || range.start > previous.end + 1) {
      merged.push({ ...range });
      continue;
    }
    previous.end = Math.max(previous.end, range.end);
  }
  return merged;
}

function openingTagForFold(line: string) {
  const trimmed = line.trim();
  if (!trimmed || trimmed.startsWith("</") || trimmed.startsWith("<?") || trimmed.startsWith("<!--")) {
    return null;
  }
  const openMatch = /^<([A-Za-z_][\w:.-]*)\b/.exec(trimmed);
  if (!openMatch) return null;
  const tag = openMatch[1];
  if (trimmed.endsWith("/>") || trimmed.includes(`</${tag}>`)) return null;
  return tag;
}

function closingTagsForLine(line: string) {
  return [...line.matchAll(/<\/([A-Za-z_][\w:.-]*)\s*>/g)].map((match) => match[1]);
}

function findMatchingOpenFrame(stack: OpenTagFrame[], tag: string) {
  for (let index = stack.length - 1; index >= 0; index -= 1) {
    if (stack[index]?.tag === tag) return index;
  }
  return -1;
}
</script>

<template>
  <div class="xml-source-viewer" :style="viewerStyle">
    <div v-if="hasFoldableLines" class="xml-source-viewer__toolbar">
      <button type="button" @click="collapseAllLines">
        <ChevronRight :size="13" />
        <span>{{ t("workbench.context.sourceCollapseAll") }}</span>
      </button>
      <button type="button" @click="expandAllLines">
        <ChevronDown :size="13" />
        <span>{{ t("workbench.context.sourceExpandAll") }}</span>
      </button>
    </div>
    <div
      v-for="line in visibleSourceLines"
      :key="line.lineNumber"
      class="xml-source-viewer__line"
      :class="sourceLineClasses(line)"
    >
      <span class="xml-source-viewer__number">{{ line.lineNumber }}</span>
      <button
        v-if="line.foldEndLineNumber !== null"
        type="button"
        class="xml-source-viewer__toggle"
        :aria-label="isLineFolded(line.lineNumber) ? t('workbench.context.sourceExpandAll') : t('workbench.context.sourceCollapseAll')"
        @click="toggleLineFold(line.lineNumber)"
      >
        <svg
          class="xml-source-viewer__triangle"
          :class="{ 'xml-source-viewer__triangle--open': !isLineFolded(line.lineNumber) }"
          viewBox="0 0 16 16"
          aria-hidden="true"
        >
          <path d="M5.2 2.9c-.76-.5-1.78.04-1.78.95v8.3c0 .91 1.02 1.45 1.78.95l6.28-4.15c.66-.44.66-1.46 0-1.9L5.2 2.9Z" />
        </svg>
      </button>
      <span v-else class="xml-source-viewer__spacer" aria-hidden="true" />
      <code class="xml-source-viewer__code">{{ line.text }}</code>
      <span
        v-if="foldedLineCount(line) > 0"
        class="xml-source-viewer__fold-summary"
        aria-hidden="true"
      >
        …
      </span>
    </div>
  </div>
</template>

<style scoped>
.xml-source-viewer {
  display: grid;
  max-height: var(--xml-source-max-height);
  overflow: auto;
  padding: 6px 0;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-inset);
  color: var(--text-secondary);
  font-family: var(--font-mono);
}

.xml-source-viewer__toolbar {
  position: sticky;
  top: 0;
  left: 0;
  z-index: 2;
  display: flex;
  gap: 6px;
  width: max-content;
  min-width: 100%;
  padding: 0 8px 6px 64px;
  border-bottom: 1px solid color-mix(in srgb, var(--border-subtle) 70%, transparent);
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--surface-raised) 20%, transparent), transparent),
    var(--surface-inset);
}

.xml-source-viewer__toolbar button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  min-height: 22px;
  padding: 0 7px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--surface-raised) 72%, transparent);
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 11px;
  cursor: pointer;
}

.xml-source-viewer__toolbar button:hover {
  border-color: color-mix(in srgb, var(--color-accent) 44%, transparent);
  color: var(--color-accent);
}

.xml-source-viewer__line {
  display: grid;
  grid-template-columns: 42px 22px max-content auto;
  align-items: center;
  width: max-content;
  min-width: 100%;
  min-height: 21px;
  padding-right: 8px;
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.45;
}

.xml-source-viewer__line:hover {
  background: color-mix(in srgb, var(--color-accent) 8%, transparent);
}

.xml-source-viewer__line--folded {
  background: color-mix(in srgb, var(--color-accent) 5%, transparent);
}

.xml-source-viewer__number {
  align-self: stretch;
  padding-right: 8px;
  border-right: 1px solid color-mix(in srgb, var(--border-subtle) 72%, transparent);
  color: color-mix(in srgb, var(--text-muted) 72%, transparent);
  line-height: 21px;
  text-align: right;
  user-select: none;
}

.xml-source-viewer__toggle,
.xml-source-viewer__spacer {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 18px;
}

.xml-source-viewer__toggle {
  border: 0;
  border-radius: var(--radius-1);
  background: transparent;
  color: color-mix(in srgb, var(--color-accent) 86%, var(--text-primary));
  cursor: pointer;
}

.xml-source-viewer__toggle:hover {
  background: color-mix(in srgb, var(--color-accent) 12%, transparent);
  color: var(--color-accent);
}

.xml-source-viewer__triangle {
  display: block;
  width: 15px;
  height: 15px;
  fill: currentColor;
  transform-origin: 50% 50%;
  transition: transform 0.12s ease, color 0.12s ease;
}

.xml-source-viewer__triangle--open {
  transform: rotate(90deg);
}

.xml-source-viewer__code {
  min-width: max-content;
  overflow: visible;
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 21px;
  white-space: pre;
}

.xml-source-viewer__fold-summary {
  padding-left: 8px;
  color: color-mix(in srgb, var(--text-muted) 78%, transparent);
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 21px;
}
</style>
