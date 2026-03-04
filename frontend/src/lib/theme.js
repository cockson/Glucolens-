const THEME_KEY = "glucolens_theme";

export function getTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  if (saved === "light" || saved === "dark") return saved;
  return "dark";
}

export function applyTheme(theme = getTheme()) {
  document.documentElement.setAttribute("data-theme", theme);
}

export function toggleTheme() {
  const next = getTheme() === "dark" ? "light" : "dark";
  localStorage.setItem(THEME_KEY, next);
  applyTheme(next);
  return next;
}
