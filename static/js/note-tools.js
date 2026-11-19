/* PRD//SUITE — compartilhar nota e copiar blocos de código. */
(() => {
  "use strict";

  const toast = (message, type) => window.PSUITE?.toast?.(message, type);

  async function copyText(text) {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
    const field = document.createElement("textarea");
    field.value = text;
    field.setAttribute("readonly", "");
    field.style.position = "fixed";
    field.style.opacity = "0";
    document.body.appendChild(field);
    field.select();
    document.execCommand("copy");
    field.remove();
  }

  function enhanceCodeBlocks(scope = document) {
    scope.querySelectorAll(".prose pre").forEach((pre) => {
      if (pre.querySelector("[data-copy-code]")) return;
      const code = pre.querySelector("code");
      if (!code) return;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "code-copy-btn";
      button.dataset.copyCode = "1";
      button.setAttribute("aria-label", "Copiar código");
      button.title = "Copiar código";
      button.innerHTML = '<i class="bi bi-clipboard" aria-hidden="true"></i><span>Copiar</span>';
      button.addEventListener("click", async (event) => {
        event.preventDefault();
        event.stopPropagation();
        try {
          await copyText((code.textContent || "").replace(/\n$/, ""));
          button.classList.add("is-copied");
          button.querySelector("span").textContent = "Copiado";
          toast("Código copiado sem as cercas.");
          window.setTimeout(() => {
            button.classList.remove("is-copied");
            button.querySelector("span").textContent = "Copiar";
          }, 1800);
        } catch (_error) {
          toast("Não foi possível copiar o código.", "error");
        }
      });
      pre.appendChild(button);
    });
  }

  function visualPlainText(prose, title) {
    const clone = prose.cloneNode(true);
    clone.querySelectorAll("[data-copy-code]").forEach((node) => node.remove());
    clone.style.position = "fixed";
    clone.style.left = "-10000px";
    clone.style.top = "0";
    clone.style.width = "720px";
    document.body.appendChild(clone);
    const body = clone.innerText.trim();
    clone.remove();
    return [title, body].filter(Boolean).join("\n\n");
  }

  function shareStyles(tag) {
    return {
      h1: "font-size:22px;line-height:1.25;font-weight:700;margin:0 0 12px;",
      h2: "font-size:19px;line-height:1.3;font-weight:700;margin:18px 0 8px;",
      h3: "font-size:16px;line-height:1.35;font-weight:700;margin:16px 0 8px;",
      h4: "font-size:15px;line-height:1.35;font-weight:700;margin:14px 0 8px;",
      h5: "font-size:14px;line-height:1.35;font-weight:700;margin:14px 0 8px;",
      h6: "font-size:13px;line-height:1.35;font-weight:700;margin:14px 0 8px;",
      p: "margin:0 0 10px;line-height:1.55;",
      ul: "margin:0 0 12px;padding-left:22px;",
      ol: "margin:0 0 12px;padding-left:22px;",
      li: "margin:2px 0;line-height:1.5;",
      blockquote: "margin:12px 0;padding:8px 12px;border-left:3px solid #b9a8cf;background:#f6f2f8;color:#6f6479;",
      pre: "margin:12px 0;padding:12px;border:1px solid #e3dce8;border-radius:6px;background:#f4f0f5;white-space:pre-wrap;font-family:Consolas,Monaco,monospace;font-size:13px;line-height:1.5;",
      code: "padding:1px 4px;border-radius:4px;background:#f4f0f5;font-family:Consolas,Monaco,monospace;font-size:.9em;",
      a: "color:#5b4b7d;",
      table: "width:100%;margin:0 0 12px;border-collapse:collapse;font-size:13px;",
      th: "padding:6px 8px;border:1px solid #ded6e3;background:#f6f2f8;text-align:left;",
      td: "padding:6px 8px;border:1px solid #ded6e3;text-align:left;",
      hr: "border:0;border-top:1px solid #ded6e3;margin:16px 0;",
    }[tag] || "";
  }

  function buildShareHtml(prose, title) {
    const clone = prose.cloneNode(true);
    clone.querySelectorAll("[data-copy-code]").forEach((node) => node.remove());
    clone.querySelectorAll("[class]").forEach((node) => node.removeAttribute("class"));
    clone.querySelectorAll("[id]").forEach((node) => node.removeAttribute("id"));
    clone.querySelectorAll("a[href]").forEach((link) => {
      const href = link.getAttribute("href") || "";
      if (href.startsWith("/") || href.startsWith("#")) {
        // Links internos do app não fazem sentido fora do ProdSuite.
        link.replaceWith(document.createTextNode(link.textContent || ""));
        return;
      }
      link.setAttribute("target", "_blank");
      link.setAttribute("rel", "noopener noreferrer");
    });
    clone.querySelectorAll("*").forEach((node) => {
      const style = shareStyles(node.tagName.toLowerCase());
      if (style) node.setAttribute("style", style);
    });
    const wrapper = document.createElement("div");
    wrapper.setAttribute(
      "style",
      "font-family:Segoe UI,Arial,sans-serif;color:#3d3442;font-size:14px;line-height:1.55;"
    );
    const heading = document.createElement("h1");
    heading.setAttribute("style", shareStyles("h1"));
    heading.textContent = title;
    wrapper.appendChild(heading);
    wrapper.appendChild(clone);
    return wrapper.outerHTML;
  }

  async function copyForChat(prose, title) {
    const html = buildShareHtml(prose, title);
    const plain = visualPlainText(prose, title);
    if (navigator.clipboard?.write && window.ClipboardItem) {
      try {
        const item = new ClipboardItem({
          "text/html": new Blob([html], { type: "text/html" }),
          "text/plain": new Blob([plain], { type: "text/plain" }),
        });
        await navigator.clipboard.write([item]);
        return "rich";
      } catch (_error) {
        // Alguns navegadores negam HTML rico; o texto formatado ainda serve.
      }
    }
    await copyText(plain);
    return "plain";
  }

  const noteView = document.querySelector("[data-note-view]");
  const shareOpen = document.querySelector("[data-note-share-open]");
  const shareDialog = document.querySelector("[data-note-share-dialog]");
  const shareCopy = document.querySelector("[data-note-share-copy]");
  const shareNative = document.querySelector("[data-note-share-native]");
  const shareClose = document.querySelector("[data-note-share-close]");
  const shareStatus = document.querySelector("[data-note-share-status]");
  const prose = noteView?.querySelector(".prose");
  const noteTitle = noteView?.dataset.noteTitle || "Nota";

  if (noteView) enhanceCodeBlocks(noteView);

  const preview = document.querySelector("[data-note-preview]");
  if (preview) {
    new MutationObserver(() => enhanceCodeBlocks(preview)).observe(preview, {
      childList: true,
      subtree: true,
    });
  }

  if (shareOpen && shareDialog && shareCopy && prose) {
    const openShare = () => {
      shareDialog.hidden = false;
      shareStatus.textContent = "";
      shareCopy.focus();
    };
    const closeShare = () => {
      shareDialog.hidden = true;
      shareOpen.focus();
    };

    shareOpen.addEventListener("click", openShare);
    shareClose?.addEventListener("click", closeShare);
    shareDialog.addEventListener("click", (event) => {
      if (event.target === shareDialog) closeShare();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !shareDialog.hidden) closeShare();
    });

    shareCopy.addEventListener("click", async () => {
      shareCopy.disabled = true;
      shareStatus.textContent = "Copiando…";
      try {
        const mode = await copyForChat(prose, noteTitle);
        shareStatus.textContent =
          mode === "rich"
            ? "Nota copiada com formatação. Cole no Teams ou no chat."
            : "Nota copiada como texto. Cole no Teams ou no chat.";
        toast("Nota pronta para colar no chat.");
      } catch (_error) {
        shareStatus.textContent =
          "O navegador não permitiu copiar. Selecione o texto da nota e use Ctrl+C.";
        toast("Não foi possível copiar a nota.", "error");
      } finally {
        shareCopy.disabled = false;
      }
    });

    if (shareNative && navigator.share) {
      shareNative.addEventListener("click", async () => {
        try {
          await navigator.share({
            title: noteTitle,
            text: visualPlainText(prose, noteTitle),
          });
          shareStatus.textContent = "Nota enviada para o app escolhido.";
        } catch (error) {
          if (error?.name !== "AbortError") {
            shareStatus.textContent = "O compartilhamento do sistema não foi concluído.";
          }
        }
      });
    } else if (shareNative) {
      shareNative.hidden = true;
    }
  }
})();
