const HEARTLY_CACHE = "heartly-pwa-v4";
const HEARTLY_OFFLINE_URL = "/offline/";
const HEARTLY_PRECACHE = [
  HEARTLY_OFFLINE_URL,
  "/manifest.webmanifest",
  "/pwa/icon-192.png",
  "/pwa/icon-512.png",
  "/pwa/maskable-192.png",
  "/pwa/maskable-512.png"
];

async function cacheIfAvailable(cache, url) {
  try {
    const response = await fetch(new Request(url, { cache: "reload" }));

    if (response && response.ok) {
      await cache.put(url, response);
    }
  } catch (error) {
    console.warn("Heartly could not precache:", url, error);
  }
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(HEARTLY_CACHE).then((cache) =>
      Promise.all(HEARTLY_PRECACHE.map((url) => cacheIfAvailable(cache, url)))
    ).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys
          .filter((key) => key.startsWith("heartly-pwa-") && key !== HEARTLY_CACHE)
          .map((key) => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") {
    self.skipWaiting();
  }
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);

  if (request.method !== "GET" || url.origin !== self.location.origin) {
    return;
  }

  if (url.pathname.startsWith("/admin/")) {
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() =>
        caches.match(HEARTLY_OFFLINE_URL).then((cached) => cached || Response.error())
      )
    );
    return;
  }

  if (url.pathname.startsWith("/static/") || url.pathname.startsWith("/pwa/")) {
    event.respondWith(
      caches.match(request).then((cached) => {
        if (cached) {
          return cached;
        }

        return fetch(request).then((response) => {
          if (response && response.ok) {
            const copy = response.clone();
            caches.open(HEARTLY_CACHE).then((cache) => cache.put(request, copy));
          }

          return response;
        });
      })
    );
  }
});
