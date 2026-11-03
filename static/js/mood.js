/* Humor: valores acessíveis dos sliders. */
(() => {
  "use strict";
  document.querySelectorAll("[data-mood-range]").forEach((input) => {
    const output = document.querySelector(
      `[data-mood-output="${input.dataset.moodRange}"]`
    );
    const update = () => {
      if (output) output.textContent = `${input.value}/5`;
      input.style.setProperty(
        "--range-progress",
        `${((Number(input.value) - Number(input.min)) / (Number(input.max) - Number(input.min))) * 100}%`
      );
    };
    input.addEventListener("input", update);
    update();
  });
})();
