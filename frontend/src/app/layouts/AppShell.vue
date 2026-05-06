<script setup lang="ts">
import {
  Bell,
  ChevronDown,
  Languages,
  Moon,
  Search,
  Sun,
} from "lucide-vue-next";
import { computed, ref } from "vue";
import { RouterLink, RouterView, useRoute } from "vue-router";

import { useI18n } from "@/shared/i18n";

const route = useRoute();
const { locale, setLocale, t } = useI18n();
type ThemePreference = "dark" | "light";
const themeStorageKey = "crxzipple.theme";

const navItems = [
  { label: "nav.workbench", to: "/workbench", key: "workbench", count: 0 },
  { label: "nav.operations", to: "/operations/orchestration", key: "operations", count: 2, tone: "danger" },
  { label: "nav.trace", to: "/trace/trc_01H8XK3Q7Y4P8Z2J8S6M1D9F6E", key: "trace", count: 3, tone: "warning" },
  { label: "nav.settings", to: "/settings", key: "settings", count: 0 },
];

const activeRoot = computed(() => {
  const [, root] = route.path.split("/");
  return root || "workbench";
});

const theme = ref<ThemePreference>(initialTheme());

function initialTheme(): ThemePreference {
  if (typeof window === "undefined") return "dark";
  const saved = window.localStorage.getItem(themeStorageKey);
  return saved === "light" ? "light" : "dark";
}

function setTheme(nextTheme: ThemePreference): void {
  theme.value = nextTheme;
  if (typeof document !== "undefined") {
    document.documentElement.dataset.theme = nextTheme;
  }
  if (typeof window !== "undefined") {
    window.localStorage.setItem(themeStorageKey, nextTheme);
  }
}

function toggleTheme(): void {
  setTheme(theme.value === "dark" ? "light" : "dark");
}

function toggleLocale(): void {
  setLocale(locale.value === "zh-CN" ? "en-US" : "zh-CN");
}

setTheme(theme.value);
</script>

<template>
  <div class="runtime-shell">
    <header class="top-nav">
      <RouterLink class="brand" to="/workbench" aria-label="Agent Runtime">
        <span class="brand__mark">
          <span class="brand__mark-leg brand__mark-leg--left" />
          <span class="brand__mark-leg brand__mark-leg--right" />
          <span class="brand__mark-cross" />
        </span>
        <span>{{ t("app.name") }}</span>
      </RouterLink>

      <nav class="top-nav__links" :aria-label="t('nav.primary')">
        <RouterLink
          v-for="item in navItems"
          :key="item.key"
          class="top-nav__link"
          :class="{ 'top-nav__link--active': activeRoot === item.key }"
          :to="item.to"
        >
          <span>{{ t(item.label) }}</span>
          <span
            v-if="item.count"
            class="nav-count"
            :class="`nav-count--${item.tone ?? 'danger'}`"
          >
            {{ item.count }}
          </span>
        </RouterLink>
      </nav>

      <div class="top-nav__tools">
        <label class="search-box">
          <Search :size="16" />
          <input :placeholder="t('common.search')" />
          <kbd>⌘K</kbd>
        </label>

        <button class="icon-button icon-button--alert" type="button" :title="t('common.notifications')">
          <Bell :size="18" />
        </button>

        <button class="preference-button" type="button" :title="t('preferences.toggleTheme')" @click="toggleTheme">
          <Sun v-if="theme === 'light'" :size="15" />
          <Moon v-else :size="15" />
          <span>{{ theme === 'light' ? t('theme.light') : t('theme.dark') }}</span>
        </button>

        <button class="preference-button" type="button" :title="t('preferences.toggleLanguage')" @click="toggleLocale">
          <Languages :size="15" />
          <span>{{ locale === 'zh-CN' ? '中文' : 'EN' }}</span>
        </button>

        <button class="profile-chip" type="button">
          <span class="profile-chip__avatar" />
          <span class="profile-chip__text">
            <strong>Jane Doe</strong>
            <small>{{ t("common.admin") }}</small>
          </span>
          <ChevronDown :size="14" />
        </button>
      </div>
    </header>

    <main class="runtime-shell__content">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.runtime-shell {
  display: grid;
  grid-template-rows: var(--shell-topbar-height) minmax(0, 1fr);
  min-height: 100dvh;
  background: var(--surface-page);
  color: var(--text-primary);
}

.top-nav {
  display: grid;
  grid-template-columns: auto minmax(360px, 1fr) auto;
  align-items: center;
  gap: 18px;
  height: var(--shell-topbar-height);
  padding: 0 16px;
  border-bottom: 1px solid var(--border-subtle);
  background: var(--surface-nav);
}

.brand,
.top-nav__link {
  color: inherit;
  text-decoration: none;
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  min-width: 176px;
  font-weight: 700;
  font-size: 13px;
}

.brand__mark {
  position: relative;
  display: block;
  width: 24px;
  height: 24px;
  color: var(--text-primary);
}

.brand__mark-leg,
.brand__mark-cross {
  position: absolute;
  display: block;
  border-radius: 3px;
  background: currentColor;
}

.brand__mark-leg {
  bottom: 2px;
  width: 7px;
  height: 20px;
}

.brand__mark-leg--left {
  left: 4px;
  transform: skewX(-24deg);
}

.brand__mark-leg--right {
  right: 4px;
  transform: skewX(24deg);
}

.brand__mark-cross {
  left: 8px;
  bottom: 8px;
  width: 8px;
  height: 6px;
}

.top-nav__links,
.top-nav__tools {
  display: flex;
  align-items: center;
  gap: 14px;
}

.top-nav__link {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-height: var(--shell-topbar-height);
  padding: 0 11px;
  color: var(--text-secondary);
  border-bottom: 2px solid transparent;
  font-size: 12px;
}

.top-nav__link--active {
  color: var(--color-accent);
  background: transparent;
  border-bottom-color: var(--color-accent);
}

.nav-count {
  display: inline-grid;
  place-items: center;
  min-width: 18px;
  height: 18px;
  padding: 0 6px;
  border-radius: 999px;
  background: var(--count-color);
  color: var(--text-on-danger);
  font-size: 11px;
  font-weight: 700;
}

.nav-count--danger {
  --count-color: var(--color-danger);
}

.nav-count--warning {
  --count-color: #ff7a1a;
}

.top-nav__tools {
  justify-content: end;
  gap: 10px;
}

.search-box {
  display: grid;
  grid-template-columns: auto minmax(110px, 1fr) auto;
  align-items: center;
  gap: var(--space-2);
  width: clamp(240px, 17vw, 260px);
  min-height: 28px;
  padding: 0 10px;
  color: var(--text-muted);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-2);
  background: var(--surface-input);
}

.search-box input {
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text-primary);
}

kbd {
  padding: 1px var(--space-2);
  border-radius: var(--radius-1);
  background: var(--surface-raised);
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: var(--font-size-0);
}

.icon-button {
  position: relative;
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
}

.icon-button--alert::after {
  position: absolute;
  top: 4px;
  right: 5px;
  width: 7px;
  height: 7px;
  border: 1px solid var(--surface-nav);
  border-radius: 999px;
  background: var(--color-danger);
  content: "";
}

.preference-button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 28px;
  padding: 0 9px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 11px;
  white-space: nowrap;
}

.preference-button:hover {
  color: var(--text-primary);
  border-color: var(--border-strong);
}

.profile-chip {
  display: grid;
  grid-template-columns: auto auto auto;
  align-items: center;
  gap: 8px;
  min-height: 30px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--text-primary);
  cursor: pointer;
}

.profile-chip__avatar {
  width: 28px;
  height: 28px;
  border-radius: 999px;
  background-image: url("/workbench-avatar.png");
  background-size: cover;
  background-position: center;
}

.profile-chip__text {
  display: grid;
  gap: 1px;
  text-align: left;
}

.profile-chip__text strong {
  font-size: 11px;
}

.profile-chip__text small {
  color: var(--text-muted);
  font-size: 10px;
}

.runtime-shell__content {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

@media (max-width: 1100px) {
  .top-nav {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .top-nav__tools {
    display: none;
  }
}

@media (max-width: 760px) {
  .top-nav {
    grid-template-columns: auto minmax(0, 1fr);
    gap: 10px;
    height: var(--shell-topbar-height);
    min-height: 0;
    overflow: hidden;
    padding: 0 10px;
  }

  .brand {
    flex: 0 0 auto;
    min-width: 0;
  }

  .brand > span:not(.brand__mark) {
    display: none;
  }

  .top-nav__links {
    min-width: 0;
    overflow-x: auto;
    scrollbar-width: none;
  }

  .top-nav__links::-webkit-scrollbar {
    display: none;
  }

  .top-nav__link {
    flex: 0 0 auto;
    padding: 0 9px;
  }
}
</style>
