export type Theme = "light" | "dark";

const THEME_STORAGE_KEY = "theme";

export function getInitialTheme(): Theme {
  const saved = localStorage.getItem(THEME_STORAGE_KEY);
  if (saved === "light" || saved === "dark") return saved;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyTheme(theme: Theme) {
  const root = document.documentElement;
  root.classList.toggle("light", theme === "light");
  root.classList.toggle("dark", theme === "dark");
  localStorage.setItem(THEME_STORAGE_KEY, theme);
}

export function initTheme() {
  applyTheme(getInitialTheme());
}

export function toggleTheme(): Theme {
  const next: Theme = document.documentElement.classList.contains("light") ? "dark" : "light";
  applyTheme(next);
  return next;
}
