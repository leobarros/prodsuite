/* Hidratação: registro rápido, animação e lembretes locais. */
(() => {
  "use strict";

  const page = document.querySelector("[data-water-reminders]");
  if (!page) return;

  const toast = window.PSUITE?.toast;
  const glassFill = document.querySelector("[data-water-fill]");
  const totalNode = document.querySelector("[data-water-total]");
  const percentNode = document.querySelector("[data-water-percent]");
  const percentLabel = document.querySelector("[data-water-percent-label]");
  const remainingNode = document.querySelector("[data-water-remaining-wrap]");
  const statusNode = document.querySelector("[data-water-status]");
  const recentNode = document.querySelector("[data-water-recent]");
  const warningNode = document.querySelector("[data-water-hourly-warning]");

  function updateWaterUI(data) {
    if (!data) return;
    if (glassFill) {
      const offset = 236 * (1 - Math.min(100, data.percent) / 100);
      glassFill.style.setProperty("--water-offset", `${Math.round(offset * 10) / 10}px`);
    }
    if (totalNode) totalNode.textContent = data.total;
    if (percentNode) {
      percentNode.style.width = `${data.percent}%`;
      percentNode.parentElement?.setAttribute("aria-valuenow", data.percent);
    }
    if (percentLabel) percentLabel.textContent = `${data.percent}%`;
    if (remainingNode) {
      remainingNode.textContent = data.remaining
        ? `faltam ${data.remaining} ml`
        : "faixa atingida";
    }
    if (statusNode) {
      statusNode.className = `chip water-status-${data.status_key}`;
      statusNode.textContent = data.status_label;
    }
    if (recentNode && data.recent_html) recentNode.innerHTML = data.recent_html;
    if (warningNode) warningNode.hidden = !data.hourly_warning;
    if (Array.isArray(data.week_days)) {
      const weekMax = Math.max(Number(data.high) || 0, ...data.week_days.map((day) => day.ml), 1);
      data.week_days.forEach((day) => {
        const col = document.querySelector(`[data-water-week-col="${day.date}"]`);
        if (!col) return;
        const value = col.querySelector("[data-water-week-value]");
        const fill = col.querySelector("[data-water-week-fill]");
        if (value) value.textContent = `${(day.ml / 1000).toFixed(1).replace(".", ",")}L`;
        if (fill) fill.style.height = `${Math.max(2, Math.round((day.ml / weekMax) * 100))}%`;
      });
      const average = document.querySelector("[data-water-week-average]");
      const days = document.querySelector("[data-water-week-days]");
      if (average) average.textContent = `${(data.week_average / 1000).toFixed(1).replace(".", ",")} L`;
      if (days) days.textContent = `${data.in_range_days} de 7 dias na faixa`;
    }
    const reached = data.status_key === "in_range" || data.status_key === "above";
    goalReached = reached;
    if (reached) {
      window.clearTimeout(reminderTimer);
      const next = document.querySelector("[data-water-next-reminder]");
      if (next) next.textContent = "Faixa atingida — lembretes pausados hoje.";
    }
  }

  document.querySelectorAll("[data-water-add]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = form.querySelector("button[type=submit]");
      if (button) button.disabled = true;
      try {
        const response = await fetch(form.action, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "X-Requested-With": "fetch",
            Accept: "application/json",
          },
          body: new FormData(form),
        });
        const data = await response.json().catch(() => null);
        if (!response.ok || !data?.ok) {
          toast?.(data?.error || "Não foi possível registrar a água.", "error");
          return;
        }
        updateWaterUI(data);
        const input = form.querySelector('input[name="amount_ml"]');
        if (input && input.type === "number") input.value = "";
        toast?.(`${data.amount} ml registrados.`, "success");
      } catch (_error) {
        toast?.("Não foi possível conectar. Tente novamente.", "error");
      } finally {
        if (button) button.disabled = false;
      }
    });
  });

  document.addEventListener("submit", async (event) => {
    const form = event.target.closest?.("form[data-water-delete]");
    if (!form || event.defaultPrevented) return;
    event.preventDefault();
    const button = form.querySelector("button[type=submit]");
    if (button) button.disabled = true;
    try {
      const response = await fetch(form.action, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "X-Requested-With": "fetch",
          Accept: "application/json",
        },
        body: new FormData(form),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok || !data?.ok) {
        toast?.(data?.error || "Não foi possível remover o registro.", "error");
        return;
      }
      updateWaterUI(data);
      toast?.("Registro removido.", "success");
    } catch (_error) {
      toast?.("Não foi possível conectar. Tente novamente.", "error");
    } finally {
      if (button) button.disabled = false;
    }
  });

  const reminderForm = document.querySelector("[data-water-reminders-form]");
  if (reminderForm) {
    reminderForm.addEventListener("submit", async (event) => {
      const enabling = reminderForm.querySelector(
        'input[name="reminders_enabled"]'
      )?.value === "1";
      if (!enabling || !("Notification" in window)) return;
      if (Notification.permission !== "default") return;
      event.preventDefault();
      try {
        await Notification.requestPermission();
      } finally {
        reminderForm.submit();
      }
    });
  }

  const REMINDER_MESSAGES = [
    {
      title: "Uma gota agora",
      body: "Um gole curto, sem pressa. Você não precisa cumprir a meta de uma vez.",
    },
    {
      title: "Cachoeira de pausa",
      body: "Respire, beba um pouco e volte ao que estava fazendo. A água pode esperar um instante.",
    },
    {
      title: "Mar calmo",
      body: "Hidratação é ritmo, não corrida. Um gole agora, se fizer sentido.",
    },
  ];

  const enabled = page.dataset.waterReminders === "1";
  const interval = Math.max(30, Number(page.dataset.waterInterval) || 90);
  const nextNode = document.querySelector("[data-water-next-reminder]");
  let reminderTimer = null;
  let goalReached = page.dataset.waterGoalReached === "1";

  function nextAllowedTime() {
    const now = new Date();
    const candidate = new Date(now.getTime() + interval * 60000);
    const start = new Date(candidate);
    start.setHours(8, 0, 0, 0);
    const end = new Date(candidate);
    end.setHours(21, 0, 0, 0);
    if (candidate < start) return start;
    if (candidate > end) {
      const tomorrow = new Date(candidate);
      tomorrow.setDate(tomorrow.getDate() + 1);
      tomorrow.setHours(8, 0, 0, 0);
      return tomorrow;
    }
    return candidate;
  }

  function showReminder() {
    if (!enabled) return;
    try {
      const key = `prodsuite.water.reminders.${new Date().toISOString().slice(0, 10)}`;
      const count = Number(localStorage.getItem(key) || 0);
      if (count < 8) {
        const message = REMINDER_MESSAGES[count % REMINDER_MESSAGES.length];
        toast?.(`${message.title}: ${message.body}`, "success", 6000);
        if ("Notification" in window && Notification.permission === "granted") {
          new Notification(message.title, {
            body: message.body,
            icon: "/static/icons/water-notification.png",
            tag: "prosuite-water",
          });
        }
        localStorage.setItem(key, String(count + 1));
      }
    } catch (_error) {
      const message = REMINDER_MESSAGES[0];
      toast?.(`${message.title}: ${message.body}`, "success", 6000);
    }
    scheduleReminder();
  }

  function scheduleReminder() {
    window.clearTimeout(reminderTimer);
    if (!enabled) return;
    if (goalReached) {
      if (nextNode) nextNode.textContent = "Faixa atingida — lembretes pausados hoje.";
      return;
    }
    const next = nextAllowedTime();
    if (nextNode) {
      nextNode.textContent = `Próximo lembrete: ${next.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`;
    }
    reminderTimer = window.setTimeout(showReminder, next.getTime() - Date.now());
  }

  if (enabled) scheduleReminder();
})();
