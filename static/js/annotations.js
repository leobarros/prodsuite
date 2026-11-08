/* Caixa de entrada: Enter envia, Shift+Enter quebra linha. */
(() => {
  "use strict";
  document.querySelectorAll("[data-annotation-composer]").forEach((form) => {
    const field = form.querySelector("textarea");
    if (!field) return;
    field.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
      event.preventDefault();
      form.requestSubmit();
    });
  });
})();

/* Modo foco: uma decisão por vez, com atalhos de teclado. */
(() => {
  "use strict";
  const focus = document.querySelector("[data-focus-mode]");
  if (!focus) return;

  const actions = {
    "1": '[data-focus-action="now"]',
    "2": '[data-focus-action="schedule"]',
    "3": '[data-focus-action="note"]',
    "4": '[data-focus-action="someday"]',
  };

  document.addEventListener("keydown", (event) => {
    const target = event.target;
    if (
      target instanceof HTMLElement &&
      (target.matches("input, textarea, select") || target.isContentEditable)
    ) {
      return;
    }
    if (event.altKey || event.ctrlKey || event.metaKey) return;

    if (event.key === "Backspace") {
      const dismiss = focus.querySelector('[data-focus-action="dismiss"]');
      if (dismiss) {
        event.preventDefault();
        dismiss.click();
      }
      return;
    }

    const selector = actions[event.key];
    if (!selector) return;
    const action = focus.querySelector(selector);
    if (!action) return;
    event.preventDefault();
    action.click();
  });
})();

/* Menu de mais ações da fila: fecha ao clicar fora, trocar de menu ou Esc. */
(() => {
  "use strict";
  const menus = Array.from(document.querySelectorAll(".inbox-more"));
  if (!menus.length) return;

  const closeAll = (except = null) => {
    menus.forEach((menu) => {
      if (menu !== except) menu.open = false;
    });
  };

  document.addEventListener("click", (event) => {
    const target = event.target;
    const current = target instanceof Element ? target.closest(".inbox-more") : null;
    closeAll(current);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    const open = menus.find((menu) => menu.open);
    if (!open) return;
    open.open = false;
    const summary = open.querySelector("summary");
    if (summary instanceof HTMLElement) summary.focus();
  });
})();
