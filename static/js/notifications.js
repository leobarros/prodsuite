/* Web Push: assinatura e ativação por dispositivo. */
(() => {
  "use strict";

  const page = document.querySelector("[data-notifications]");
  if (!page) return;
  const button = page.querySelector("[data-push-enable]");
  const status = page.querySelector("[data-push-status]");
  const vapidKey = page.dataset.vapidKey || "";

  function setStatus(message, error = false) {
    if (!status) return;
    status.textContent = message;
    status.classList.toggle("is-error", error);
  }

  function keyBytes(value) {
    const padding = "=".repeat((4 - (value.length % 4)) % 4);
    const raw = atob((value + padding).replace(/-/g, "+").replace(/_/g, "/"));
    return Uint8Array.from([...raw].map((char) => char.charCodeAt(0)));
  }

  async function enable() {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      setStatus("Este navegador não oferece Web Push.", true);
      return;
    }
    if (!vapidKey) {
      setStatus("Web Push não configurado no servidor.", true);
      return;
    }
    button.disabled = true;
    try {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setStatus("Permissão não concedida. Você pode ativar depois.", true);
        return;
      }
      const registration = await navigator.serviceWorker.ready;
      let subscription = await registration.pushManager.getSubscription();
      if (!subscription) {
        subscription = await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: keyBytes(vapidKey),
        });
      }
      const response = await fetch("/notificacoes/assinar", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": document.querySelector('meta[name="csrf-token"]')?.content || "",
        },
        body: JSON.stringify(subscription.toJSON()),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok || !data?.ok) throw new Error(data?.error || "Não foi possível ativar.");
      setStatus("Ativo neste dispositivo.");
    } catch (error) {
      setStatus(error.message || "Não foi possível ativar as notificações.", true);
    } finally {
      button.disabled = false;
    }
  }

  button?.addEventListener("click", enable);
  if ("serviceWorker" in navigator && "PushManager" in window) {
    navigator.serviceWorker.ready
      .then((registration) => registration.pushManager.getSubscription())
      .then((subscription) => {
        if (subscription) setStatus("Ativo neste dispositivo.");
      })
      .catch(() => {});
  }
})();
