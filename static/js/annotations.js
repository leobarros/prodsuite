/* Anotações: Enter envia, Shift+Enter quebra linha. */
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
