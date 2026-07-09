const HEARTLY_CACHE = "heartly-pwa-v3";
const HEARTLY_OFFLINE_URL = "/offline/";
const HEARTLY_STATIC_ASSETS = [
  HEARTLY_OFFLINE_URL,
  "/manifest.webmanifest?v=3",
  "/static/js/heartly-pwa.js?v=3",
  "/static/icons/icon-192.png?v=3",
  "/static/icons/icon-512.png?v=3",
  "/static/icons/maskable-192.png?v=3",
  "/static/icons/maskable-512.png?v=3"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(HEARTLY_CACHE)
      .then((cache) => cache.addAll(HEARTLY_STATIC_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== HEARTLY_CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);

  if (request.method !== "GET") {
    return;
  }

  if (url.origin !== self.location.origin) {
    return;
  }

  if (url.pathname.startsWith("/admin/") || url.pathname.startsWith("/accounts/")) {
    return;
  }

  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.match(request).then((cached) => cached || fetch(request).then((response) => {
        const copy = response.clone();
        caches.open(HEARTLY_CACHE).then((cache) => cache.put(request, copy));
        return response;
      }))
    );
    return;
  }

  event.respondWith(
    fetch(request).catch(() => caches.match(HEARTLY_OFFLINE_URL))
  );
});
