/*
 * PRD//SUITE — motor do Pomodoro.
 *
 * O relógio usa timestamps absolutos (endsAt) para sobreviver a refresh,
 * navegação entre páginas e throttling de timers no Safari iOS. O ciclo só é
 * contabilizado depois de validado pela API no servidor.
 */
(() => {
  "use strict";

  const body = document.body;
  if (!body || body.dataset.authenticated !== "1") return;

  const PSuite = (window.PSUITE = window.PSUITE || {});
  const csrfToken =
    PSuite.csrfToken ||
    document.querySelector('meta[name="csrf-token"]')?.content ||
    "";
  const userId = body.dataset.userId || "anon";
  const STORAGE_KEY = `prodsuite.timer.v2.${userId}`;
  const PENDING_KEY = `prodsuite.timer.pending.${userId}`;
  const baseTitle = document.title;

  const MODES = {
    focus: { seconds: 25 * 60, minutes: 25, label: "Foco", short: "Foco" },
    short_break: { seconds: 5 * 60, minutes: 5, label: "Pausa curta", short: "Pausa" },
    long_break: { seconds: 20 * 60, minutes: 20, label: "Pausa longa", short: "Pausa" },
  };
  const RING_CIRCUMFERENCE = 2 * Math.PI * 132;

  const displays = document.querySelectorAll("[data-timer-display]");
  const modeLabels = document.querySelectorAll("[data-timer-mode-label]");
  const modeEmojis = document.querySelectorAll("[data-timer-emoji]");
  const statusLabels = document.querySelectorAll("[data-timer-status]");
  const icons = document.querySelectorAll("[data-timer-icon]");
  const actionLabels = document.querySelectorAll("[data-timer-action-label]");
  const toggles = document.querySelectorAll("[data-timer-toggle]");
  const resets = document.querySelectorAll("[data-timer-reset]");
  const modeButtons = document.querySelectorAll("[data-timer-mode]");
  const taskSelects = document.querySelectorAll("[data-timer-task]");
  const ring = document.querySelector("[data-timer-ring]");
  const ringWrap = document.querySelector("[data-timer-ring-wrap]");
  const hud = document.getElementById("pomodoro-hud");
  const progressBar = document.querySelector("[data-timer-progress]");
  const sessionContainers = document.querySelectorAll("[data-session-dots]");
  const focusSelect = document.getElementById("focusTaskSelect");
  const soundEl = document.getElementById("pomodoro-sound");
  const completionAlert = document.getElementById("pomodoro-completion-alert");
  const completionAlertEmoji = document.querySelector("[data-pomodoro-alert-emoji]");
  const completionAlertTitle = document.querySelector("[data-pomodoro-alert-title]");
  const completionAlertMessage = document.querySelector("[data-pomodoro-alert-message]");
  const completionAlertAction = document.querySelector("[data-pomodoro-alert-action]");

  let audioContext = null;
  let soundUnlocked = false;
  let serverClockOffset = 0;
  let completionAlertVisible = false;
  let lastRenderedSecond = null;
  let transitioning = false;
  // Evita anunciar um ciclo que só foi percebido depois de uma navegação,
  // restauração do bfcache ou retorno do background no iOS.
  let pageInteractiveAt = Date.now();

  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

  function localDateKey() {
    const now = new Date();
    return [
      now.getFullYear(),
      String(now.getMonth() + 1).padStart(2, "0"),
      String(now.getDate()).padStart(2, "0"),
    ].join("-");
  }

  function defaultState() {
    return {
      mode: "focus",
      duration: MODES.focus.seconds,
      remaining: MODES.focus.seconds,
      endsAt: null,
      running: false,
      taskId: null,
      runId: null,
      serverRevision: 0,
      focusCyclesToday: Number(
        sessionContainers[0]?.dataset.cycles || sessionContainers[0]?.dataset.filled || 0
      ),
      focusDate: localDateKey(),
    };
  }

  function loadState() {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (!parsed || !MODES[parsed.mode]) return null;
      const fallback = MODES[parsed.mode].seconds;
      return {
        mode: parsed.mode,
        duration: fallback,
        remaining: clamp(Number(parsed.remaining) || fallback, 0, fallback),
        endsAt: Number(parsed.endsAt) || null,
        running: Boolean(parsed.running),
        taskId: parsed.taskId ? String(parsed.taskId) : null,
        runId: parsed.runId ? String(parsed.runId) : null,
        serverRevision: Number(parsed.serverRevision) || 0,
        // O contador de ciclos é diário. Estado antigo (ou de ontem) não
        // pode disparar uma pausa longa hoje.
        focusCyclesToday:
          parsed.focusDate === localDateKey()
            ? Number(parsed.focusCyclesToday) || 0
            : Number(
                sessionContainers[0]?.dataset.cycles ||
                  sessionContainers[0]?.dataset.filled ||
                  0
              ),
        focusDate: localDateKey(),
      };
    } catch (_error) {
      return null;
    }
  }

  let state = loadState() || defaultState();

  // A URL (?tarefa=) tem prioridade quando o timer não está em curso.
  if (!state.running && focusSelect && focusSelect.value) {
    state.taskId = focusSelect.value;
  }

  function save() {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (_error) {
      /* Safari privado pode bloquear storage: timer ainda funciona na sessão */
    }
  }

  let syncPending = 0;

  function applyServerState(remote, { force = false } = {}) {
    if (!remote) return false;
    const revision = Number(remote.revision) || 0;
    if (!force && revision <= (Number(state.serverRevision) || 0)) {
      return false;
    }
    if (remote.now) {
      // O servidor é a referência de tempo. O Docker pode ter um relógio
      // alguns minutos diferente do navegador.
      serverClockOffset = Date.parse(remote.now) - Date.now();
    }
    state.mode = remote.mode;
    const canonicalDuration = modeInfo(remote.mode).seconds;
    state.duration = canonicalDuration;
    state.endsAt = remote.endsAt ? Date.parse(remote.endsAt) : null;
    state.running = Boolean(remote.running && state.endsAt);
    state.remaining = state.running
      ? clamp(
          Math.ceil((state.endsAt - (Date.now() + serverClockOffset)) / 1000),
          0,
          canonicalDuration
        )
      : clamp(Number(remote.remaining) || 0, 0, canonicalDuration);
    state.taskId = remote.taskId ? String(remote.taskId) : null;
    state.runId = remote.runId || null;
    if (remote.focusCyclesToday !== undefined) {
      // O servidor é a fonte da verdade para o contador diário. O HTML pode
      // vir do cache/bfcache e carregar a contagem de ontem.
      state.focusCyclesToday = Math.max(0, Number(remote.focusCyclesToday) || 0);
      state.focusDate = remote.focusDate || localDateKey();
      updateSessionDots();
    }
    state.serverRevision = revision;
    save();
    render();
    return true;
  }

  async function pushTimerState(action, extra = {}) {
    syncPending += 1;
    try {
      const response = await fetch("/foco/estado", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
          "X-Requested-With": "fetch",
          Accept: "application/json",
        },
        body: JSON.stringify({ action, ...extra }),
      });
      const data = await response.json().catch(() => null);
      if (response.ok && data?.ok && data.state) {
        const revision = Number(data.state.revision) || 0;
        if (revision >= (Number(state.serverRevision) || 0)) {
          applyServerState(data.state, { force: true });
        }
      }
    } catch (_error) {
      /* offline: o estado local continua valendo */
    } finally {
      syncPending -= 1;
    }
  }

  async function pullTimerState() {
    if (syncPending > 0) return;
    try {
      const response = await fetch("/foco/estado", {
        credentials: "same-origin",
        headers: { Accept: "application/json", "X-Requested-With": "fetch" },
      });
      const data = await response.json().catch(() => null);
      if (response.ok && data?.ok && data.state) {
        // GET é a fonte da verdade; reconcilia até quando a revisão é igual.
        applyServerState(data.state, { force: true });
      }
    } catch (_error) {
      /* offline: mantém o timer local */
    }
  }

  function formatClock(totalSeconds) {
    const safe = Math.max(0, Math.ceil(totalSeconds));
    const minutes = Math.floor(safe / 60);
    const seconds = safe % 60;
    return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }

  function modeInfo(mode) {
    return MODES[mode] || MODES.focus;
  }

  function isRunning() {
    return state.running && Boolean(state.endsAt);
  }

  function updateSessionDots() {
    const count = Math.max(0, Number(state.focusCyclesToday) || 0);
    const filled = count === 0 ? 0 : ((count - 1) % 4) + 1;
    sessionContainers.forEach((container) => {
      container.dataset.cycles = String(count);
      container.querySelectorAll(".session-dot").forEach((dot, index) => {
        dot.classList.toggle("filled", index < filled);
      });
      const caption = container.parentElement?.querySelector("[data-session-caption]");
      if (caption) {
        caption.textContent =
          filled === 0
            ? "A pausa longa vem após 4 sessões"
            : `${filled} de 4 sessões para a pausa longa`;
      }
      container.setAttribute(
        "aria-label",
        filled === 0
          ? "Nenhuma sessão concluída no ciclo atual; a pausa longa vem após 4 sessões"
          : `${filled} de 4 sessões concluídas para a pausa longa`
      );
      container.title =
        filled === 0
          ? "A pausa longa vem após 4 sessões de foco"
          : `${filled} de 4 sessões para a pausa longa`;
    });
  }

  function updateStatsDom(stats) {
    if (!stats) return;
    const setText = (name, value) => {
      document.querySelectorAll(`[data-stat="${name}"]`).forEach((node) => {
        node.textContent = value;
      });
    };
    setText("today-cycles", stats.today?.cycles ?? 0);
    setText("today-minutes", stats.today?.minutes ?? 0);
    setText("week-cycles", stats.week?.cycles ?? 0);
    setText("streak", stats.streak ?? 0);
    setText("week-label", stats.week?.label ?? "0m");
  }

  function render() {
    const clock = formatClock(state.remaining);
    const info = modeInfo(state.mode);
    const running = isRunning();
    const elapsed = state.duration
      ? clamp(1 - state.remaining / state.duration, 0, 1)
      : 0;

    displays.forEach((node) => {
      if (node.textContent !== clock) node.textContent = clock;
    });
    modeLabels.forEach((node) => {
      node.textContent = transitioning ? "salvando…" : info.label;
    });
    modeEmojis.forEach((node) => {
      node.innerHTML = modeIconMarkup(state.mode);
    });
    statusLabels.forEach((node) => {
      node.textContent = transitioning
        ? "sync"
        : running
          ? "em curso"
          : state.remaining < state.duration
            ? "pausado"
            : "pronto";
    });

    icons.forEach((node) => {
      node.className = `bi ${running ? "bi-pause-fill" : "bi-play-fill"}`;
    });
    actionLabels.forEach((node) => {
      node.textContent = running
        ? "Pausar"
        : state.remaining < state.duration
          ? "Continuar"
          : "Começar";
    });
    toggles.forEach((button) => {
      button.setAttribute(
        "aria-label",
        running ? "Pausar timer" : "Iniciar timer"
      );
    });

    if (ring) {
      ring.style.strokeDashoffset = String(RING_CIRCUMFERENCE * elapsed);
    }
    if (progressBar) {
      progressBar.style.width = `${elapsed * 100}%`;
    }
    if (ringWrap) {
      ringWrap.classList.toggle("is-break", state.mode === "short_break");
      ringWrap.classList.toggle("is-long", state.mode === "long_break");
    }
    if (hud) {
      hud.classList.toggle("is-running", running);
      hud.classList.toggle("is-break", state.mode !== "focus");
    }

    modeButtons.forEach((button) => {
      const active = button.dataset.timerMode === state.mode;
      button.classList.toggle("active", active);
      button.classList.toggle("is-locked", running && !active);
      button.setAttribute("aria-selected", active ? "true" : "false");
      button.setAttribute(
        "aria-disabled",
        running && !active ? "true" : "false"
      );
      button.title =
        running && !active
          ? "Pause o cronômetro antes de trocar de modo"
          : "Trocar para este modo";
    });

    taskSelects.forEach((select) => {
      const desired = state.taskId || "";
      if (select.value !== desired) {
        const exists = Array.from(select.options).some(
          (option) => option.value === desired
        );
        select.value = exists ? desired : "";
      }
    });

    updateSessionDots();

    if (running) {
      document.title = `${clock} · ${info.short} · ProdSuite`;
    } else if (!completionAlertVisible && document.title !== baseTitle) {
      document.title = baseTitle;
    }
    lastRenderedSecond = state.remaining;
    updateDashboardFocusCard();
  }

  let dashboardFocusInitial = null;

  function dashboardFocusElements() {
    const card = document.querySelector("[data-dashboard-focus]");
    if (!card) return null;
    return {
      card,
      heading: card.querySelector("[data-focus-heading]"),
      label: card.querySelector("[data-focus-label]"),
      title: card.querySelector("[data-focus-title]"),
      titleLink: card.querySelector("[data-focus-title-link]"),
      meta: card.querySelector("[data-focus-meta]"),
      progress: card.querySelector("[data-focus-progress]"),
      start: card.querySelector("[data-focus-start]"),
      resume: card.querySelector("[data-focus-resume]"),
      expand: card.querySelector("[data-focus-expand]"),
    };
  }

  function updateDashboardFocusCard() {
    const elements = dashboardFocusElements();
    if (!elements) return;

    if (!dashboardFocusInitial) {
      dashboardFocusInitial = {
        heading: elements.heading?.textContent || "Próxima tarefa",
        label: elements.label?.textContent || "",
        title: elements.title?.textContent || "",
        titleHref: elements.titleLink?.getAttribute("href") || "/foco",
        resumeHref: elements.resume?.getAttribute("href") || "/foco",
        expandHref: elements.expand?.getAttribute("href") || "/foco",
      };
    }

    const active =
      state.running ||
      (state.remaining > 0 && state.remaining < state.duration);
    elements.start?.classList.toggle("d-none", active);
    elements.resume?.classList.toggle("d-none", !active);
    elements.meta?.classList.toggle("d-none", active);
    elements.progress?.classList.toggle("d-none", active);

    if (!active) {
      if (elements.heading) elements.heading.textContent = dashboardFocusInitial.heading;
      if (elements.label) elements.label.textContent = dashboardFocusInitial.label;
      if (elements.title) elements.title.textContent = dashboardFocusInitial.title;
      elements.titleLink?.setAttribute("href", dashboardFocusInitial.titleHref);
      elements.resume?.setAttribute("href", dashboardFocusInitial.resumeHref);
      elements.expand?.setAttribute("href", dashboardFocusInitial.expandHref);
      return;
    }

    const info = modeInfo(state.mode);
    const taskId = state.taskId;
    const option = taskId
      ? document.querySelector(`.hud-task option[value="${taskId}"]`)
      : null;
    const taskTitle = option?.dataset.taskTitle || option?.textContent?.trim();
    const status = state.running ? "em andamento" : "pausado";
    const pausedPrefix = state.running ? "" : "Pomodoro pausado";
    const focusHref = taskId ? `/foco?tarefa=${taskId}` : "/foco";

    if (elements.heading) {
      elements.heading.textContent = state.running
        ? state.mode === "focus"
          ? "Foco em andamento"
          : "Intervalo em andamento"
        : "Pomodoro pausado";
    }
    if (elements.label) {
      elements.label.textContent = taskTitle
        ? `Pomodoro atual · ${info.label} ${status}`
        : pausedPrefix || "Pomodoro atual";
    }
    if (elements.title) {
      elements.title.textContent = taskTitle || "Sem tarefa vinculada";
    }
    if (elements.titleLink) {
      elements.titleLink.setAttribute(
        "href",
        taskId ? `/tarefas/${taskId}/editar` : "/foco"
      );
    }
    elements.resume?.setAttribute("href", focusHref);
    elements.expand?.setAttribute("href", focusHref);
  }

  function modeIconMarkup(mode) {
    if (mode === "focus") return '<span class="tomato-glyph" aria-hidden="true"></span>';
    if (mode === "short_break") return '<i class="bi bi-cup-hot" aria-hidden="true"></i>';
    return '<i class="bi bi-moon-stars" aria-hidden="true"></i>';
  }

  function primeAudio() {
    if (!audioContext) {
      const Context = window.AudioContext || window.webkitAudioContext;
      if (Context) {
        try {
          audioContext = new Context();
        } catch (_error) {
          audioContext = null;
        }
      }
    }
    if (audioContext?.state === "suspended") {
      audioContext.resume().catch(() => {});
    }
  }

  /**
   * Desbloqueia o áudio dentro de um gesto do usuário. Isso é obrigatório no
   * Safari iOS e evita que o navegador bloqueie o som no fim dos 25 minutos.
   */
  async function unlockAudio() {
    useMixingAudioSession();
    primeAudio();
    if (!audioContext) return;
    if (audioContext.state === "suspended") {
      try {
        await audioContext.resume();
      } catch (_error) {
        /* o próximo gesto tenta novamente */
      }
    }
    if (audioContext.state === "running") {
      soundUnlocked = true;
    }
  }

  function playSynthChime() {
    if (!audioContext) return;
    const play = () => {
      if (!audioContext || audioContext.state !== "running") return;
      const now = audioContext.currentTime;
      [880, 1320].forEach((frequency, index) => {
        const oscillator = audioContext.createOscillator();
        const gain = audioContext.createGain();
        oscillator.type = "sine";
        oscillator.frequency.value = frequency;
        gain.gain.setValueAtTime(0.0001, now + index * 0.2);
        gain.gain.exponentialRampToValueAtTime(0.16, now + index * 0.2 + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + index * 0.2 + 0.35);
        oscillator.connect(gain).connect(audioContext.destination);
        oscillator.start(now + index * 0.2);
        oscillator.stop(now + index * 0.2 + 0.4);
      });
    };
    if (audioContext.state === "suspended") {
      audioContext.resume().then(play).catch(() => {});
    } else if (audioContext.state === "running") {
      play();
    }
  }

  function useMixingAudioSession() {
    const session = window.navigator?.audioSession;
    if (!session) return;
    try {
      // "ambient" mistura com podcast/música em vez de pausar ou abduzir
      // a sessão de áudio do dispositivo. É o modo correto para um alerta
      // curto que deve conviver com o que já está tocando.
      session.type = "ambient";
    } catch (_error) {
      /* API experimental indisponível */
    }
  }

  // Configura a mistura antes de qualquer AudioContext/áudio do Pomodoro.
  useMixingAudioSession();

  function playChime() {
    useMixingAudioSession();
    primeAudio();
    if (audioContext?.state === "running") {
      playSynthChime();
      return;
    }
    if (soundEl) {
      try {
        soundEl.pause();
        soundEl.currentTime = 0;
        soundEl.muted = false;
        soundEl.volume = 0.9;
        const playback = soundEl.play();
        if (playback && typeof playback.then === "function") {
          playback.catch(() => playSynthChime());
        }
        return;
      } catch (_error) {
        /* sem contexto: tenta o áudio curto de fallback */
      }
    }
    playSynthChime();
  }

  function testSound() {
    unlockAudio().finally(() => {
      playChime();
      PSuite.toast?.("Som de teste reproduzido.");
      if (!isRunning()) {
      }
    });
  }

  function requestNotificationPermission() {
    if (!("Notification" in window)) return;
    if (Notification.permission !== "default") return;
    Notification.requestPermission().catch(() => {});
  }

  function notify(title, message) {
    if (!("Notification" in window) || Notification.permission !== "granted") {
      return;
    }
    try {
      new Notification(title, {
        body: message,
        icon: "/static/icons/icon-192.png",
        tag: "prosuite-pomodoro",
        // O som é o nosso alerta, não o som padrão do sistema.
        silent: true,
      });
    } catch (_error) {
      /* iOS exige PWA instalada; silencioso */
    }
  }

  function hideCompletionAlert() {
    if (!completionAlert) return;
    completionAlert.hidden = true;
    completionAlert.classList.remove("is-visible");
    document.body.classList.remove("has-completion-alert");
    completionAlertVisible = false;
    document.title = baseTitle;
  }

  function showCompletionAlert(finishedMode, nextMode) {
    if (!completionAlert) return;
    const isFocus = finishedMode === "focus";
    const next = modeInfo(nextMode);
    if (completionAlertEmoji) {
      completionAlertEmoji.innerHTML = isFocus
        ? '<span class="tomato-glyph" aria-hidden="true"></span>'
        : '<i class="bi bi-cup-hot" aria-hidden="true"></i>';
    }
    if (completionAlertTitle) {
      completionAlertTitle.textContent = isFocus ? "Foco concluído" : "Pausa concluída";
    }
    if (completionAlertMessage) {
      completionAlertMessage.textContent = isFocus
        ? `${modeInfo(finishedMode).minutes} min de foco concluídos. Pausa de ${next.minutes} min.`
        : `Pausa de ${modeInfo(finishedMode).minutes} min concluída. Hora do foco.`;
    }
    if (completionAlertAction) {
      completionAlertAction.textContent = isFocus ? "Iniciar pausa" : "Começar foco";
      completionAlertAction.dataset.nextMode = nextMode;
    }
    completionAlert.classList.toggle("is-break", !isFocus);
    completionAlert.hidden = false;
    completionAlert.classList.add("is-visible");
    document.body.classList.add("has-completion-alert");
    completionAlertVisible = true;
    document.title = isFocus
      ? "Foco concluído · ProdSuite"
      : "Pausa concluída · ProdSuite";
  }

  function start() {
    if (state.running) return;
    requestNotificationPermission();
    hideCompletionAlert();
    const canonicalDuration = modeInfo(state.mode).seconds;
    state.duration = canonicalDuration;
    state.remaining = clamp(
      Number(state.remaining) || canonicalDuration,
      1,
      canonicalDuration
    );
    state.endsAt = serverNowMs() + state.remaining * 1000;
    state.running = true;
    save();
    render();
    // Só ativa o contexto quando a pessoa inicia o Pomodoro explicitamente.
    unlockAudio();
    pushTimerState("start", {
      mode: state.mode,
      duration: state.duration,
      remaining: state.remaining,
      task_id: state.taskId,
    });
  }

  function pause() {
    if (!state.running) return;
    // O relógio do navegador pode estar alguns minutos diferente do
    // container; pause precisa usar a mesma referência do start.
    state.remaining = Math.max(
      0,
      Math.ceil((state.endsAt - serverNowMs()) / 1000)
    );
    state.running = false;
    state.endsAt = null;
    save();
    pushTimerState("pause", {
      remaining: state.remaining,
      mode: state.mode,
    });
    if (state.remaining <= 0) {
      completeCycle();
    } else {
      render();
    }
  }

  function reset() {
    state.running = false;
    state.endsAt = null;
    state.remaining = state.duration;
    save();
    render();
    pushTimerState("reset", { mode: state.mode });
  }

  function setMode(mode, { silent = false } = {}) {
    if (!MODES[mode]) return;
    // Não cancele um chime já agendado aqui: advanceAfter() troca de modo
    // logo após a conclusão e isso silenciava o fim do ciclo.
    state.mode = mode;
    state.duration = MODES[mode].seconds;
    state.remaining = state.duration;
    state.running = false;
    state.endsAt = null;
    save();
    if (!silent) primeAudio();
    render();
    pushTimerState("mode", { mode: state.mode });
  }

  function setTask(value) {
    state.taskId = value ? String(value) : null;
    save();
    render();
    pushTimerState("task", { task_id: state.taskId });
  }

  function laterMode(finishedMode) {
    if (finishedMode !== "focus") return "focus";
    const count = Math.max(0, Number(state.focusCyclesToday) || 0);
    return count > 0 && count % 4 === 0 ? "long_break" : "short_break";
  }

  function advanceAfter(finishedMode, nextMode) {
    const next = MODES[nextMode] || MODES.focus;
    setMode(nextMode, { silent: true });
    const message =
      finishedMode === "focus"
        ? `Pomodoro concluído! Hora de uma pausa de ${next.minutes} min.`
        : "Pausa concluída. Quando quiser, comece outra sessão.";
    PSuite.toast?.(message);
  }

  async function postCycle(payload) {
    const response = await fetch("/foco/ciclos", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
        "X-Requested-With": "fetch",
        Accept: "application/json",
      },
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => null);
    if (!response.ok || !data?.ok) {
      throw new Error(data?.error || "Não foi possível salvar a sessão.");
    }
    return data;
  }

  function readPending() {
    try {
      const raw = window.localStorage.getItem(PENDING_KEY);
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch (_error) {
      return [];
    }
  }

  function writePending(queue) {
    try {
      window.localStorage.setItem(PENDING_KEY, JSON.stringify(queue.slice(-50)));
    } catch (_error) {
      /* sem storage: ciclo não será reenviado */
    }
  }

  async function flushPending() {
    const queue = readPending();
    if (!queue.length) return;
    const remaining = [];
    let flushed = 0;
    for (const item of queue) {
      try {
        await postCycle(item);
        flushed += 1;
      } catch (_error) {
        remaining.push(item);
      }
    }
    writePending(remaining);
    if (flushed > 0) {
      PSuite.toast?.("Tudo certo: suas sessões foram salvas.");
    }
  }

  async function completeCycle({ reload = false, silent = false } = {}) {
    if (transitioning) return;
    const finishedMode = state.mode;
    const finishedInfo = modeInfo(finishedMode);
    const taskId = state.taskId;

    transitioning = true;
    state.running = false;
    state.endsAt = null;
    state.remaining = 0;
    if (finishedMode === "focus") {
      const todayKey = localDateKey();
      if (state.focusDate !== todayKey) {
        state.focusCyclesToday = 0;
        state.focusDate = todayKey;
      }
      state.focusCyclesToday = (Number(state.focusCyclesToday) || 0) + 1;
    }
    save();
    render();

    let nextMode = laterMode(finishedMode);

    const shouldAnnounce =
      !silent &&
      !reload &&
      document.visibilityState === "visible" &&
      Date.now() - pageInteractiveAt > 1200;

    if (shouldAnnounce) {
      playChime();
      showCompletionAlert(finishedMode, nextMode);
      if (navigator.vibrate && navigator.userActivation?.hasBeenActive) {
        try {
          navigator.vibrate([120, 70, 120, 70, 180]);
        } catch (_error) {
          /* dispositivo sem suporte */
        }
      }
      notify(
        finishedMode === "focus"
          ? "Foco concluído"
          : "Pausa concluída",
        finishedMode === "focus"
          ? `${modeInfo(finishedMode).minutes} min de foco concluídos. Pausa de ${modeInfo(nextMode).minutes} min.`
          : "Hora do foco."
      );
    }

    const payload = {
      mode: finishedMode,
      duration_minutes: Math.max(1, Math.round(state.duration / 60)),
      task_id: taskId || null,
      run_id: state.runId || null,
    };

    try {
      const data = await postCycle(payload);
      if (data?.stats) {
        state.focusCyclesToday = Number(data.stats.focus_cycles_today) || 0;
        state.focusDate = localDateKey();
        updateStatsDom(data.stats);
        updateSessionDots();
        const chartHost = document.querySelector("[data-weekly-chart-host]");
        if (chartHost && data.chart_html) {
          chartHost.innerHTML = data.chart_html;
        }
        const historyHost = document.querySelector("[data-focus-history]");
        if (historyHost && data.history_html) {
          historyHost.innerHTML = data.history_html;
        }
      }
      if (finishedMode === "focus" && data?.suggested_next) {
        // O servidor pode sugerir uma pausa longa; o alerta já usou a
        // estimativa local, mas o próximo modo acompanha a sugestão.
        nextMode = data.suggested_next;
      }
      await flushPending();
      await pushTimerState("complete", { run_id: state.runId });
    } catch (error) {
      writePending([...readPending(), { ...payload, queued_at: new Date().toISOString() }]);
      PSuite.toast?.("Sem internet: sua sessão ficou guardada e será salva quando a conexão voltar.", "error");
    } finally {
      transitioning = false;
      advanceAfter(finishedMode, nextMode);
    }
  }

  function tick() {
    if (!isRunning()) return;
    const remaining = Math.min(
      state.duration,
      Math.ceil((state.endsAt - serverNowMs()) / 1000)
    );
    if (remaining <= 0) {
      completeCycle();
      return;
    }
    if (remaining !== lastRenderedSecond) {
      state.remaining = remaining;
      save();
      render();
    }
  }

  toggles.forEach((button) => {
    button.addEventListener("click", () => {
      if (isRunning()) pause();
      else start();
    });
  });

  resets.forEach((button) => {
    button.addEventListener("click", reset);
  });

  modeButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const mode = button.dataset.timerMode;
      if (mode === state.mode) return;
      if (isRunning()) {
        PSuite.toast?.(
          "Pause o cronômetro antes de trocar de modo. Seu tempo está preservado.",
          "error"
        );
        return;
      }
      setMode(mode);
    });
  });

  taskSelects.forEach((select) => {
    select.addEventListener("change", () => setTask(select.value));
  });

  document.querySelectorAll("[data-test-sound]").forEach((button) => {
    button.addEventListener("click", testSound);
  });

  document.querySelectorAll("[data-dismiss-pomodoro-alert]").forEach((button) => {
    button.addEventListener("click", hideCompletionAlert);
  });

  completionAlertAction?.addEventListener("click", () => {
    const nextMode = completionAlertAction.dataset.nextMode;
    hideCompletionAlert();
    if (!nextMode) return;
    setMode(nextMode);
    start();
  });

  document.addEventListener("keydown", (event) => {
    const target = event.target;
    const typing =
      target instanceof HTMLElement &&
      (target.matches("input, textarea, select, button, a") ||
        target.isContentEditable);
    if (typing || event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.code === "Space") {
      event.preventDefault();
      if (isRunning()) pause();
      else start();
    } else if (event.key.toLowerCase() === "r") {
      reset();
    }
  });

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible") return;
    pageInteractiveAt = Date.now();
    // Se o ciclo venceu enquanto o app estava em background, registra o
    // ciclo sem tocar o som atrasado.
    if (state.running && state.endsAt && state.endsAt <= Date.now()) {
      completeCycle({ reload: true });
    } else {
      tick();
    }
  });

  window.addEventListener("pageshow", (event) => {
    pageInteractiveAt = Date.now();
    if (!event.persisted) return;
    // iOS/Safari pode restaurar a página do bfcache; não trate o tempo
    // decorrido como uma conclusão "ao vivo".
    if (state.running && state.endsAt && state.endsAt <= Date.now()) {
      completeCycle({ reload: true });
    } else {
      render();
      tick();
    }
  });
  window.addEventListener("online", flushPending);
  window.addEventListener("offline", () => {
    PSuite.toast?.("Você está sem internet. O timer continua e suas sessões serão salvas quando a conexão voltar.");
  });

  // Recalcula ao carregar: se o ciclo terminou com a aba fechada, registra.
  render();
  if (state.running && state.endsAt && state.endsAt <= Date.now()) {
    completeCycle({ reload: true });
  } else if (state.running) {
    tick();
  }

  window.setInterval(tick, 400);
  pullTimerState();
  window.setInterval(pullTimerState, 5000);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") pullTimerState();
  });
  window.addEventListener("focus", pullTimerState);

  // Reenvia ciclos pendentes ao abrir o app.
  window.setTimeout(flushPending, 1800);

  PSuite.timer = {
    getState: () => ({ ...state }),
    start,
    pause,
    reset,
    setMode,
    setTask,
    testSound,
    formatClock,
    MODES,
  };
})();
