<script setup lang="ts">
import type { ConversationSummary } from "@/types";

defineProps<{
  open: boolean;
  conversations: ConversationSummary[];
  activeBulkKey: string | null;
  loading: boolean;
}>();

const emit = defineEmits<{
  select: [bulkKey: string];
  fresh: [];
  close: [];
}>();

function formatTime(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    month: "short",
    day: "numeric",
  }).format(new Date(value));
}
</script>

<template>
  <aside class="sidebar-drawer" :class="{ 'sidebar-drawer--open': open }">
    <div class="sidebar shell">
      <div class="sidebar__topline">
        <div>
          <p class="eyebrow">threads</p>
          <h1>Recent threads</h1>
        </div>
        <div class="sidebar__actions">
          <button
            class="ghost-button"
            type="button"
            title="Start new thread"
            @click="emit('fresh')"
          >
            <span class="button-glyph button-glyph--new" aria-hidden="true"></span>
            <span class="sr-only">New thread</span>
          </button>
          <button
            class="ghost-button sidebar__close"
            type="button"
            title="Close thread list"
            @click="emit('close')"
          >
            <span class="button-glyph button-glyph--collapse" aria-hidden="true"></span>
            <span>Close</span>
          </button>
        </div>
      </div>

      <div class="sidebar__meta">
        <span class="meta-chip">{{ conversations.length }} threads</span>
      </div>

      <div v-if="loading" class="sidebar__loading">
        <span class="loader"></span>
        <span>Syncing rail...</span>
      </div>

      <div class="sidebar__list">
        <button
          v-for="conversation in conversations"
          :key="conversation.bulk_key"
          class="conversation-card"
          :class="{ 'conversation-card--active': conversation.bulk_key === activeBulkKey }"
          type="button"
          :aria-current="conversation.bulk_key === activeBulkKey ? 'true' : undefined"
          @click="emit('select', conversation.bulk_key)"
        >
          <div class="conversation-card__stripe"></div>
          <div class="conversation-card__row">
            <strong class="conversation-card__title">
              {{ conversation.title || "New thread" }}
            </strong>
            <span class="conversation-card__time">{{ formatTime(conversation.updated_at) }}</span>
          </div>
          <div class="conversation-card__row conversation-card__row--muted conversation-card__row--runtime">
            <span class="conversation-card__runtime-agent">
              {{ conversation.runtime_binding.agent_id ?? "unbound" }}
            </span>
            <span class="conversation-card__runtime-status">
              {{ conversation.channel ?? "thread" }} ·
              {{
                conversation.display_run_status ??
                  conversation.latest_run_status ??
                  conversation.status
              }}
            </span>
          </div>
          <p class="conversation-card__preview">
            {{ conversation.last_message_preview ?? "No messages yet. Start the thread." }}
          </p>
        </button>
      </div>
    </div>
  </aside>
</template>
