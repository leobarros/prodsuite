/* Anexos: cola/arrasta um print direto na tarefa, sem upload manual. */
(() => {
  "use strict";

  const section = document.querySelector("[data-task-attachments]");
  if (!section) return;

  const list = section.querySelector("[data-attachment-list]");
  const empty = section.querySelector("[data-attachment-empty]");
  const count = section.querySelector("[data-attachment-count]");
  const status = section.querySelector("[data-attachment-status]");
  const zone = section.querySelector("[data-attachment-paste-zone]");
  const button = section.querySelector("[data-paste-attachment]");
  const uploadUrl = section.dataset.uploadUrl;
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const maxBytes = 8 * 1024 * 1024;
  let busy = false;

  function toast(message, type = "success") {
    if (window.PSUITE?.toast) {
      window.PSUITE.toast(message, type);
    } else if (status) {
      status.textContent = message;
    }
  }

  function setStatus(message) {
    if (status) status.textContent = message;
  }

  function extensionFor(type) {
    return ({ "image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif" })[type] || "png";
  }

  function makeFile(blob, type) {
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    return new File([blob], `print-${stamp}.${extensionFor(type)}`, { type });
  }

  function updateCount(total) {
    if (!count) return;
    const value = Number(total) || 0;
    count.textContent = `${value} arquivo${value === 1 ? "" : "s"}`;
  }

  async function upload(file) {
    if (busy) return;
    if (!file || !file.type.startsWith("image/")) {
      toast("Cole ou arraste uma imagem.", "error");
      return;
    }
    if (file.size > maxBytes) {
      toast("O print pode ter no máximo 8 MB.", "error");
      return;
    }
    busy = true;
    setStatus("Anexando print…");
    if (button) button.disabled = true;
    try {
      const form = new FormData();
      form.append("files", file, file.name || "print.png");
      const response = await fetch(uploadUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "X-CSRFToken": csrf,
          "X-Requested-With": "fetch",
          Accept: "application/json",
        },
        body: form,
      });
      const data = await response.json().catch(() => null);
      if (!response.ok || !data?.ok) {
        throw new Error(data?.error || "Não foi possível anexar o print.");
      }
      if (list) {
        list.hidden = false;
        list.insertAdjacentHTML("afterbegin", data.html);
      }
      if (empty) empty.hidden = true;
      updateCount(data.count);
      setStatus("");
      toast("Print anexado à tarefa.");
    } catch (error) {
      setStatus("");
      toast(error.message || "Não foi possível anexar o print.", "error");
    } finally {
      busy = false;
      if (button) button.disabled = false;
    }
  }

  async function pasteFromClipboard() {
    if (!navigator.clipboard?.read) {
      toast("Use Ctrl/⌘+V para colar o print.", "error");
      return;
    }
    try {
      const items = await navigator.clipboard.read();
      for (const item of items) {
        const type = item.types.find((value) => value.startsWith("image/"));
        if (!type) continue;
        const blob = await item.getType(type);
        await upload(makeFile(blob, type));
        return;
      }
      toast("Nenhuma imagem encontrada na área de transferência.", "error");
    } catch (_error) {
      toast("Não foi possível ler a área de transferência. Use Ctrl/⌘+V.", "error");
    }
  }

  // Ctrl/⌘+V em qualquer lugar da página de detalhe da tarefa.
  document.addEventListener("paste", (event) => {
    const item = Array.from(event.clipboardData?.items || []).find(
      (value) => value.kind === "file" && value.type.startsWith("image/")
    );
    if (!item) return;
    const file = item.getAsFile();
    if (!file) return;
    event.preventDefault();
    upload(file);
  });

  button?.addEventListener("click", pasteFromClipboard);
  zone?.addEventListener("click", (event) => {
    if (event.target.closest("button")) return;
    pasteFromClipboard();
  });
  zone?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      pasteFromClipboard();
    }
  });
  zone?.addEventListener("dragover", (event) => {
    event.preventDefault();
    zone.classList.add("is-dragging");
  });
  zone?.addEventListener("dragleave", () => zone.classList.remove("is-dragging"));
  zone?.addEventListener("drop", (event) => {
    event.preventDefault();
    zone.classList.remove("is-dragging");
    const file = Array.from(event.dataTransfer?.files || []).find((value) =>
      value.type.startsWith("image/")
    );
    if (file) upload(file);
  });
})();
