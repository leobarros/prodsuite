/* PRD//SUITE — interações globais (sem dependências externas). */
(() => {
  "use strict";

  const root = document.body;
  const csrf = document.querySelector('meta[name="csrf-token"]');
  const csrfToken = csrf ? csrf.content : "";
  const toastStack = document.getElementById("toast-stack");

  function toast(message, type = "success", timeout = 4200) {
    if (!toastStack) return;
    const node = document.createElement("div");
    node.className = `ps-toast${type === "error" ? " is-error" : ""}`;
    node.setAttribute("role", "status");
    const icon = document.createElement("i");
    icon.className = `bi ${type === "error" ? "bi-exclamation-octagon" : "bi-check2-circle"}`;
    const span = document.createElement("span");
    span.textContent = message;
    node.append(icon, span);
    toastStack.appendChild(node);
    window.setTimeout(() => node.remove(), timeout);
  }

  async function parseJson(response) {
    try {
      return await response.json();
    } catch (_error) {
      return null;
    }
  }

  function updateCharCounts() {
    document.querySelectorAll("[data-char-count]").forEach((counter) => {
      const container = counter.closest("form") || document;
      const field = container.querySelector("textarea[maxlength]");
      if (!field) return;
      counter.textContent = `${field.value.length}/${field.maxLength}`;
    });
  }

  // ------------------------------------------------------- flash messages
  document.querySelectorAll("[data-dismiss-flash]").forEach((button) => {
    button.addEventListener("click", () => button.closest(".flash")?.remove());
  });
  document.querySelectorAll(".flash-success, .flash-info").forEach((flash) => {
    window.setTimeout(() => flash.remove(), 7000);
  });

  // --------------------------------------------------------- confirmações
  const confirmDialog = document.getElementById("confirm-dialog");
  const confirmMessage = document.getElementById("confirm-message");
  const confirmAccept = confirmDialog?.querySelector("[data-confirm-accept]");
  let pendingForm = null;
  let pendingSubmitter = null;
  let confirmReturnFocus = null;

  function closeConfirm({ restoreFocus = true } = {}) {
    if (!confirmDialog) return;
    confirmDialog.hidden = true;
    document.body.classList.remove("confirm-open");
    pendingForm = null;
    pendingSubmitter = null;
    if (restoreFocus) confirmReturnFocus?.focus?.();
    confirmReturnFocus = null;
  }

  function openConfirm(form, submitter) {
    if (!confirmDialog || !confirmMessage || !confirmAccept) return;
    pendingForm = form;
    pendingSubmitter = submitter || null;
    confirmReturnFocus = document.activeElement;
    confirmMessage.textContent = form.dataset.confirm || "Confirmar ação?";
    const text = (form.dataset.confirm || "").trim().toLowerCase();
    confirmAccept.textContent = text.startsWith("desconectar")
      ? "Desconectar"
      : /^(excluir|remover)/.test(text)
        ? "Remover"
        : "Confirmar";
    confirmDialog.hidden = false;
    document.body.classList.add("confirm-open");
    window.requestAnimationFrame(() => confirmAccept.focus());
  }

  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (form.dataset.confirmed === "1") {
        delete form.dataset.confirmed;
        return;
      }
      event.preventDefault();
      openConfirm(form, event.submitter);
    });
  });

  confirmAccept?.addEventListener("click", () => {
    const form = pendingForm;
    const submitter = pendingSubmitter;
    if (!form) return;
    closeConfirm({ restoreFocus: false });
    form.dataset.confirmed = "1";
    form.requestSubmit(submitter || undefined);
  });

  confirmDialog?.querySelectorAll("[data-confirm-cancel]").forEach((button) => {
    button.addEventListener("click", () => closeConfirm());
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && confirmDialog && !confirmDialog.hidden) {
      closeConfirm();
    }
  });

  // ------------------------------------------------------ captura rápida
  document.querySelectorAll("form[data-ajax-capture]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = form.querySelector('button[type="submit"]');
      const field = form.querySelector("textarea[name='content']");
      if (!field || !field.value.trim()) {
        toast("Escreva algo antes de capturar.", "error");
        return;
      }
      if (button) button.disabled = true;
      try {
        const response = await fetch(form.action, {
          method: "POST",
          body: new FormData(form),
          credentials: "same-origin",
          headers: {
            "X-Requested-With": "fetch",
            "X-CSRFToken": csrfToken,
            Accept: "application/json",
          },
        });
        const data = await parseJson(response);
        if (!response.ok || !data?.ok) {
          const firstError = data?.errors
            ? Object.values(data.errors).flat()[0]
            : data?.error;
          toast(firstError || "Não foi possível capturar.", "error");
          return;
        }
        field.value = "";
        updateCharCounts();
        toast("Captura registrada em Rascunhos.");
        const preview = document.querySelector("[data-scratch-preview]");
        if (preview && data.scratchpad) {
          const row = document.createElement("div");
          row.className = "recent-scratch-item";
          const icon = document.createElement("i");
          icon.className = "bi bi-dash";
          const text = document.createElement("span");
          text.textContent = data.scratchpad.preview;
          row.append(icon, text);
          preview.prepend(row);
        }
        const modal = form.closest(".modal");
        if (modal && window.bootstrap) {
          window.bootstrap.Modal.getOrCreateInstance(modal).hide();
        }
      } catch (_error) {
        toast("Não conseguimos conectar. Tente novamente.", "error");
      } finally {
        if (button) button.disabled = false;
      }
    });
  });

  document.querySelectorAll("textarea").forEach((field) => {
    field.addEventListener("input", updateCharCounts);
  });
  updateCharCounts();

  // --------------------------------------------------------------- tema
  const THEME_KEY = "prodsuite-theme";
  const themeColorMeta = document.querySelector('meta[name="theme-color"]');
  const statusBarMeta = document.querySelector(
    'meta[name="apple-mobile-web-app-status-bar-style"]'
  );

  const currentTheme = () =>
    document.documentElement.dataset.theme === "dark" ? "dark" : "light";

  function syncThemeControls() {
    const theme = currentTheme();
    const nextLabel = theme === "dark" ? "Ativar tema claro" : "Ativar tema escuro";
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
      button.setAttribute("aria-label", nextLabel);
      button.setAttribute("title", nextLabel);
      const icon = button.querySelector("i");
      if (icon) {
        icon.className = `bi ${theme === "dark" ? "bi-sun" : "bi-moon-stars"}`;
      }
    });
    document.querySelectorAll("[data-theme-set]").forEach((button) => {
      const active = button.dataset.themeSet === theme;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  function applyTheme(theme, persist = true) {
    const normalized = theme === "dark" ? "dark" : "light";
    document.documentElement.dataset.theme = normalized;
    document.documentElement.style.colorScheme = normalized;
    if (themeColorMeta) {
      themeColorMeta.content = normalized === "dark" ? "#1d1921" : "#faf7f2";
    }
    if (statusBarMeta) {
      statusBarMeta.content =
        normalized === "dark" ? "black-translucent" : "default";
    }
    if (persist) {
      try {
        window.localStorage.setItem(THEME_KEY, normalized);
      } catch (_error) {
        /* modo privado: aplica só nesta sessão */
      }
    }
    syncThemeControls();
  }

  document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      applyTheme(currentTheme() === "dark" ? "light" : "dark");
    });
  });
  document.querySelectorAll("[data-theme-set]").forEach((button) => {
    button.addEventListener("click", () => applyTheme(button.dataset.themeSet));
  });
  syncThemeControls();

  // ----------------------------------------------------------- senhas
  document.querySelectorAll("[data-toggle-password]").forEach((button) => {
    button.addEventListener("click", () => {
      const input = button.closest(".password-wrap")?.querySelector("input");
      if (!input) return;
      const visible = input.type === "text";
      input.type = visible ? "password" : "text";
      button.setAttribute("aria-label", visible ? "Mostrar senha" : "Ocultar senha");
      const icon = button.querySelector("i");
      if (icon) {
        icon.className = `bi ${visible ? "bi-eye" : "bi-eye-slash"}`;
      }
    });
  });

  // -------------------------------------------------- modal auto-aberto
  const autoOpen = root.dataset.autoOpen;
  if (autoOpen && window.bootstrap) {
    const element = document.querySelector(autoOpen);
    if (element) window.bootstrap.Modal.getOrCreateInstance(element).show();
  }

  // ------------------------------------------------------ tutorial inicial
  const onboardingModal = document.getElementById("onboardingModal");
  if (onboardingModal && root.dataset.onboarding === "1" && window.bootstrap) {
    window.setTimeout(() => {
      window.bootstrap.Modal.getOrCreateInstance(onboardingModal).show();
    }, 180);
  }
  if (onboardingModal) {
    let onboardingSaved = false;
    onboardingModal.addEventListener("hidden.bs.modal", () => {
      const url = new URL(window.location.href);
      if (url.searchParams.get("tour") === "1") {
        url.searchParams.delete("tour");
        window.history.replaceState(
          {},
          "",
          `${url.pathname}${url.search}${url.hash}`
        );
      }
      if (onboardingSaved) return;
      onboardingSaved = true;
      fetch("/bem-vindo/concluir", {
        method: "POST",
        credentials: "same-origin",
        keepalive: true,
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
          "X-Requested-With": "fetch",
          Accept: "application/json",
        },
        body: "{}",
      }).catch(() => {
        onboardingSaved = false;
      });
    });
  }

  // ------------------------------------------------ converter rascunho
  document.querySelectorAll("[data-convert-url]").forEach((button) => {
    button.addEventListener("click", () => {
      const form = document.querySelector("[data-convert-form]");
      if (!form) return;
      form.action = button.dataset.convertUrl;
      const title = form.querySelector("#convertTitle");
      if (title) title.value = button.dataset.convertTitle || "";
    });
  });

  // ---------------------------------------------------- editor markdown
  const editor = document.querySelector("[data-note-editor]");
  if (editor) {
    const body = editor.querySelector("#noteBody");
    const preview = editor.querySelector("[data-note-preview]");
    const counter = editor.querySelector("[data-note-count]");
    const previewUrl = editor.dataset.previewUrl;
    let debounce = null;
    let lastRequest = 0;

    const refreshPreview = async () => {
      if (!body || !preview || !previewUrl) return;
      const requestId = ++lastRequest;
      try {
        const response = await fetch(previewUrl, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrfToken,
            "X-Requested-With": "fetch",
            Accept: "application/json",
          },
          body: JSON.stringify({ body: body.value }),
        });
        const data = await parseJson(response);
        if (requestId === lastRequest && response.ok && data?.ok) {
          preview.innerHTML = data.html;
        }
      } catch (_error) {
        /* preview silencioso: o conteúdo principal continua no textarea */
      }
    };

    const schedulePreview = () => {
      if (counter) counter.textContent = `${body.value.length} / 40000`;
      window.clearTimeout(debounce);
      debounce = window.setTimeout(refreshPreview, 380);
    };

    if (body) {
      body.addEventListener("input", schedulePreview);
      schedulePreview();
    }

    editor.querySelectorAll("[data-md-insert]").forEach((button) => {
      button.addEventListener("click", () => {
        if (!body) return;
        const template = button.dataset.mdInsert || "";
        const pipe = template.indexOf("|");
        const before = pipe >= 0 ? template.slice(0, pipe) : template;
        const after = pipe >= 0 ? template.slice(pipe + 1) : "";
        const start = body.selectionStart;
        const end = body.selectionEnd;
        const selected = body.value.slice(start, end);
        body.setRangeText(`${before}${selected}${after}`, start, end, "end");
        if (!selected) {
          const cursor = start + before.length;
          body.setSelectionRange(cursor, cursor);
        }
        body.focus();
        schedulePreview();
      });
    });
  }

  // ---------------------------------------------------- kanban drag/drop
  const board = document.querySelector("[data-kanban]");
  if (board) {
    let dragged = null;

    board.querySelectorAll(".task-card").forEach((card) => {
      card.addEventListener("dragstart", (event) => {
        dragged = card;
        card.classList.add("dragging");
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", card.dataset.taskId);
      });
      card.addEventListener("dragend", () => {
        card.classList.remove("dragging");
        board.querySelectorAll(".is-dragover").forEach((column) =>
          column.classList.remove("is-dragover")
        );
        dragged = null;
      });
    });

    board.querySelectorAll("[data-dropzone]").forEach((column) => {
      column.addEventListener("dragover", (event) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
        column.classList.add("is-dragover");
      });
      column.addEventListener("dragleave", (event) => {
        if (!column.contains(event.relatedTarget)) {
          column.classList.remove("is-dragover");
        }
      });
      column.addEventListener("drop", async (event) => {
        event.preventDefault();
        column.classList.remove("is-dragover");
        const card = dragged;
        if (!card) return;
        const columnId = column.dataset.columnId;
        const taskId = card.dataset.taskId;
        if (!columnId || card.dataset.columnId === columnId) return;
        const sourceColumn = card.closest(".kanban-col");
        try {
          const response = await fetch(`/tarefas/${taskId}/coluna`, {
            method: "POST",
            credentials: "same-origin",
            headers: {
              "Content-Type": "application/json",
              "X-CSRFToken": csrfToken,
              "X-Requested-With": "fetch",
              Accept: "application/json",
            },
            body: JSON.stringify({ column_id: Number(columnId) }),
          });
          const data = await parseJson(response);
          if (!response.ok || !data?.ok) {
            toast(data?.error || "Não foi possível mover a tarefa.", "error");
            return;
          }
          const targetList = column.querySelector(".kanban-list");
          const addButton = targetList?.querySelector(".kanban-add");
          targetList?.insertBefore(card, addButton || null);
          card.dataset.columnId = String(data.task.column_id);
          card.classList.toggle("is-done", Boolean(data.task.is_done));
          const select = card.querySelector("[data-column-select]");
          if (select) select.value = String(data.task.column_id);

          const sourceCounter = sourceColumn?.querySelector("[data-count-for]");
          const targetCounter = column.querySelector("[data-count-for]");
          if (sourceCounter && targetCounter && sourceColumn !== column) {
            sourceCounter.textContent = String(
              Math.max(0, Number(sourceCounter.textContent || 0) - 1)
            );
            targetCounter.textContent = String(
              Number(targetCounter.textContent || 0) + 1
            );
          }
          toast("Tarefa movida.");
        } catch (_error) {
          toast("Não conseguimos conectar. Tente novamente.", "error");
        }
      });
    });
  }

  document.querySelectorAll("[data-add-task-column]").forEach((button) => {
    button.addEventListener("click", () => {
      const select = document.getElementById("taskColumnSelect");
      if (select) select.value = button.dataset.addTaskColumn;
    });
  });

  document.querySelectorAll("[data-column-select]").forEach((select) => {
    select.addEventListener("change", () => {
      const form = select.closest("form");
      if (form) form.requestSubmit();
    });
  });

  // -------------------------------------------------------- quick focus
  document.querySelectorAll("[data-quick-focus]").forEach((button) => {
    button.addEventListener("click", () => {
      const timer = window.PSUITE?.timer;
      if (!timer) {
        window.location.href = `/foco?tarefa=${button.dataset.taskId}`;
        return;
      }
      timer.setTask(button.dataset.taskId);
      timer.setMode("focus");
      timer.start();
      toast("Ciclo de foco iniciado.");
    });
  });

  // ------------------------------------------------------------- iOS hint
  const hint = document.getElementById("ios-install-hint");
  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
  const isStandalone =
    window.navigator.standalone === true ||
    window.matchMedia("(display-mode: standalone)").matches;
  let hintDismissed = false;
  try {
    hintDismissed = window.localStorage.getItem("psuite.iosHintDismissed") === "1";
  } catch (_error) {
    hintDismissed = false;
  }
  if (hint && isIOS && !isStandalone && !hintDismissed) {
    hint.classList.add("is-visible");
  }
  document.querySelectorAll("[data-dismiss-ios-hint]").forEach((button) => {
    button.addEventListener("click", () => {
      hint?.classList.remove("is-visible");
      try {
        window.localStorage.setItem("psuite.iosHintDismissed", "1");
      } catch (_error) {
        /* modo privado: apenas esconde nesta sessão */
      }
    });
  });

  // ------------------------------------------------------ service worker
  if ("serviceWorker" in navigator) {
    if (window.isSecureContext) {
      window.addEventListener("load", () => {
        navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {
          /* PWA offline é degradação graciosa; a app continua funcionando */
        });
      });
    } else {
      /* O modo offline precisa de um endereço seguro; sem ele, o app segue online. */
    }
  }

  // Contexto compartilhado com pomodoro.js e templates.
  window.PSUITE = Object.assign(window.PSUITE || {}, {
    csrfToken,
    toast,
    parseJson,
  });
})();
