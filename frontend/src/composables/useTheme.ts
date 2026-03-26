import { computed, ref, watch } from "vue";

type ThemeMode = "dark" | "light";

const STORAGE_KEY = "crxzipple.ui.theme";

function detectSystemTheme(): ThemeMode {
  if (typeof window === "undefined") {
    return "dark";
  }
  return window.matchMedia("(prefers-color-scheme: light)").matches
    ? "light"
    : "dark";
}

function readStoredTheme(): ThemeMode {
  if (typeof window === "undefined") {
    return "dark";
  }
  const value = window.localStorage.getItem(STORAGE_KEY);
  if (value === "dark" || value === "light") {
    return value;
  }
  return detectSystemTheme();
}

function applyTheme(theme: ThemeMode) {
  if (typeof document === "undefined") {
    return;
  }
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
}

export function useTheme() {
  const theme = ref<ThemeMode>(readStoredTheme());

  applyTheme(theme.value);

  watch(theme, (value) => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, value);
    }
    applyTheme(value);
  });

  const toggleTitle = computed(() =>
    theme.value === "dark" ? "Switch to light theme" : "Switch to dark theme",
  );

  function toggleTheme() {
    theme.value = theme.value === "dark" ? "light" : "dark";
  }

  return {
    theme,
    toggleTitle,
    toggleTheme,
  } as const;
}
