/*
 * Aplica o tema antes da primeira pintura para evitar flash.
 * Carregado de forma síncrona no <head> (CSP: script-src 'self').
 */
(() => {
  "use strict";
  const KEY = "prodsuite-theme";
  let theme = null;
  try {
    theme = window.localStorage.getItem(KEY);
  } catch (_error) {
    theme = null;
  }
  // O tema claro é o padrão. O escuro é uma escolha explícita da pessoa.
  if (theme !== "light" && theme !== "dark") {
    theme = "light";
  }
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;

  const themeColor = document.querySelector('meta[name="theme-color"]');
  if (themeColor) {
    themeColor.content = theme === "dark" ? "#1d1921" : "#faf7f2";
  }
  const statusBar = document.querySelector(
    'meta[name="apple-mobile-web-app-status-bar-style"]'
  );
  if (statusBar) {
    statusBar.content = theme === "dark" ? "black-translucent" : "default";
  }
})();
