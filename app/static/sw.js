const CACHE_NAME = "f1-bets-shell-v1";
const APP_SHELL = [
  "/static/style.css",
  "/static/manifest.json",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/offline.html",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;

  // HTML pages are dynamic (predictions, leaderboard, admin) — always prefer
  // the network, only falling back to a static offline page if it's down.
  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(() => caches.match("/static/offline.html")));
    return;
  }

  // Static app-shell assets: cache-first, since they rarely change.
  if (request.url.includes("/static/")) {
    event.respondWith(caches.match(request).then((cached) => cached || fetch(request)));
  }
});
