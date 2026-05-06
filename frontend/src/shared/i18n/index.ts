import { computed, ref } from "vue";

import { enUS } from "./messages/en-US";
import { zhCN } from "./messages/zh-CN";

export type Locale = "zh-CN" | "en-US";
type MessageKey = keyof typeof zhCN;
const storageKey = "crxzipple.locale";

const messages = {
  "zh-CN": zhCN,
  "en-US": enUS,
};

const locale = ref<Locale>(initialLocale());

export function setLocale(nextLocale: Locale) {
  locale.value = nextLocale;
  if (typeof window !== "undefined") {
    window.localStorage.setItem(storageKey, nextLocale);
  }
  if (typeof document !== "undefined") {
    document.documentElement.lang = nextLocale;
  }
}

function isLocale(value: string | null): value is Locale {
  return value === "zh-CN" || value === "en-US";
}

function initialLocale(): Locale {
  if (typeof window === "undefined") return "zh-CN";
  const saved = window.localStorage.getItem(storageKey);
  if (isLocale(saved)) return saved;
  return "zh-CN";
}

setLocale(locale.value);

export function hasI18nMessage(key: string, targetLocale: Locale = locale.value): boolean {
  const table = messages[targetLocale] as Record<string, string>;
  const fallback = messages["zh-CN"] as Record<string, string>;
  return Boolean(table[key] ?? fallback[key]);
}

export function useI18n() {
  const currentLocale = computed(() => locale.value);

  function t(key: string, params: Record<string, string | number> = {}) {
    const table = messages[locale.value] as Record<string, string>;
    const fallback = messages["zh-CN"] as Record<string, string>;
    const template = table[key] ?? fallback[key] ?? key;

    if (import.meta.env.DEV && !table[key] && !fallback[key]) {
      console.warn(`[i18n] Missing key: ${key}`);
    }

    return Object.entries(params).reduce((value, [name, replacement]) => {
      return value.split(`{${name}}`).join(String(replacement));
    }, template);
  }

  return {
    locale: currentLocale,
    setLocale,
    t: t as (key: MessageKey | string, params?: Record<string, string | number>) => string,
  };
}
