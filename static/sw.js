/*
 * PRD//SUITE — Service Worker
 *
 * Estratégia consciente de privacidade:
 *  - Somente GET same-origin é interceptado.
 *  - Páginas autenticadas e respostas de API NUNCA entram no Cache Storage
 *    (evita vazar dados de sessão para o disco do aparelho).
 *  - Navegação: network-first com fallback para /offline.
 *  - Estáticos versionados: cache-first + revalidação em background.
 *
 * Ao alterar assets, incremente CACHE_VERSION para promover a limpeza.
 */
const CACHE_VERSION = "v2.72.0";
const PRECACHE = `prodsuite-precache-${CACHE_VERSION}`;
const RUNTIME = `prodsuite-runtime-${CACHE_VERSION}`;
const OFFLINE_URL = "/offline";

const CORE_ASSETS = [
  OFFLINE_URL,
  "/manifest.webmanifest",
  "/static/css/app.css",
  "/static/css/theme.css",
  "/static/js/theme-init.js",
  "/static/vendor/bootstrap/css/bootstrap.min.css",
  "/static/vendor/bootstrap-icons/bootstrap-icons.min.css",
  "/static/vendor/bootstrap-icons/fonts/bootstrap-icons.woff2",
  "/static/vendor/bootstrap/js/bootstrap.bundle.min.js",
  "/static/js/app.js",
  "/static/js/pomodoro.js",
  "/static/audio/pomodoro-alert.wav",
  "/static/icons/tomato.svg",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/icons/apple-touch-icon-180.png",
  "/static/icons/icon-maskable-512.png",
  "/static/icons/icon-32.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(PRECACHE);
      // allSettled: um asset ausente não invalida toda a instalação.
      await Promise.allSettled(
        CORE_ASSETS.map((url) =>
          cache.add(new Request(url, { cache: "reload" })).catch(() => null)
        )
      );
      await self.skipWaiting();
    })()
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys
          .filter((key) => key !== PRECACHE && key !== RUNTIME)
          .map((key) => caches.delete(key))
      );
      await self.clients.claim();
    })()
  );
});

async function networkFirstNavigation(request) {
  try {
    return await fetch(request);
  } catch (error) {
    const cache = await caches.open(PRECACHE);
    const offline = await cache.match(OFFLINE_URL);
    return (
      offline ||
      new Response("Offline", {
        status: 503,
        headers: { "Content-Type": "text/plain; charset=utf-8" },
      })
    );
  }
}

async function cacheFirstStatic(request) {
  const cache = await caches.open(RUNTIME);
  const cached = await cache.match(request);
  if (cached) return cached;

  const network = await fetch(request);
  if (network && network.ok && network.type === "basic") {
    cache.put(request, network.clone());
  }
  return network;
}

self.addEventListener("fetch", (event) => {
  const { request } = event;

  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === "navigate") {
    event.respondWith(networkFirstNavigation(request));
    return;
  }

  if (url.pathname.startsWith("/static/")) {
    event.respondWith(cacheFirstStatic(request).catch(() => caches.match(request)));
    return;
  }

  if (url.pathname === "/manifest.webmanifest") {
    event.respondWith(
      (async () => {
        const cached = await caches.match(request);
        const network = fetch(request)
          .then((response) => {
            if (response.ok) caches.open(PRECACHE).then((c) => c.put(request, response.clone()));
            return response;
          })
          .catch(() => cached);
        return cached || network;
      })()
    );
  }
  // Demais rotas (API, export, auth) vão direto à rede: nada é cacheado.
});
