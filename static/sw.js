const HEARTLY_CACHE = "heartly-pwa-v6";
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
    caches.open(HEARTLY_CACHE)
      .then((cache) =>
        Promise.all(
          HEARTLY_PRECACHE.map((url) =>
            cacheIfAvailable(cache, url)
          )
        )
      )
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys
          .filter(
            (key) =>
              key.startsWith("heartly-pwa-") &&
              key !== HEARTLY_CACHE
          )
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

  if (
    request.method !== "GET" ||
    url.origin !== self.location.origin
  ) {
    return;
  }

  if (url.pathname.startsWith("/admin/")) {
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() =>
        caches.match(HEARTLY_OFFLINE_URL)
          .then((cached) => cached || Response.error())
      )
    );
    return;
  }

  if (
    url.pathname.startsWith("/static/") ||
    url.pathname.startsWith("/pwa/")
  ) {
    event.respondWith(
      caches.match(request).then((cached) => {
        if (cached) {
          return cached;
        }

        return fetch(request).then((response) => {
          if (response && response.ok) {
            const copy = response.clone();
            caches.open(HEARTLY_CACHE)
              .then((cache) => cache.put(request, copy));
          }

          return response;
        });
      })
    );
  }
});

function safePushData(event) {
  try {
    return event.data ? event.data.json() : {};
  } catch (error) {
    return {
      body: event.data
        ? event.data.text()
        : "You have a Heartly update."
    };
  }
}

async function notifyOpenClients(clientList, payload) {
  await Promise.all(
    clientList.map(async (client) => {
      try {
        client.postMessage({
          type: "heartly.push.received",
          payload
        });
      } catch (error) {
        // Another client or the next snapshot poll will recover.
      }
    })
  );
}

self.addEventListener("push", (event) => {
  event.waitUntil((async () => {
    const data = safePushData(event);
    const clientList = await self.clients.matchAll({
      type: "window",
      includeUncontrolled: true
    });

    await notifyOpenClients(clientList, data);

    const hasVisibleClient = clientList.some(
      (client) => client.visibilityState === "visible"
    );
    if (hasVisibleClient) {
      return;
    }

    const notificationOptions = {
      body: data.body || "You have a new update.",
      icon: data.icon || "/pwa/icon-192.png",
      badge: data.badge || "/pwa/icon-192.png",
      tag: data.tag || "heartly-update",
      renotify: true,
      silent: false,
      timestamp: Number(data.timestamp) || Date.now(),
      requireInteraction: Boolean(
        data.require_interaction
      ),
      data: {
        url: data.url || "/notifications/",
        notificationId: data.notification_id || null,
        notificationType: (
          data.notification_type || "system"
        )
      }
    };

    if (
      Array.isArray(data.vibrate) &&
      data.vibrate.length
    ) {
      notificationOptions.vibrate = data.vibrate;
    }

    await self.registration.showNotification(
      data.title || "Heartly",
      notificationOptions
    );
  })());
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();

  let targetUrl = new URL(
    event.notification.data &&
    event.notification.data.url
      ? event.notification.data.url
      : "/notifications/",
    self.location.origin
  );

  if (targetUrl.origin !== self.location.origin) {
    targetUrl = new URL(
      "/notifications/",
      self.location.origin
    );
  }

  event.waitUntil((async () => {
    const clientList = await self.clients.matchAll({
      type: "window",
      includeUncontrolled: true
    });

    const exactClient = clientList.find((client) => {
      try {
        return (
          new URL(client.url).pathname ===
          targetUrl.pathname
        );
      } catch (error) {
        return false;
      }
    });
    const visibleClient = clientList.find(
      (client) => client.visibilityState === "visible"
    );
    const client = exactClient || visibleClient || clientList[0];

    if (client) {
      if ("navigate" in client) {
        await client.navigate(targetUrl.href);
      }
      return client.focus();
    }

    return self.clients.openWindow(targetUrl.href);
  })());
});

self.addEventListener(
  "pushsubscriptionchange",
  (event) => {
    event.waitUntil((async () => {
      const clientList = await self.clients.matchAll({
        type: "window",
        includeUncontrolled: true
      });

      await Promise.all(
        clientList.map(async (client) => {
          try {
            client.postMessage({
              type: "heartly.push.subscription-change"
            });
          } catch (error) {
            // The page performs a complete sync on its next load.
          }
        })
      );
    })());
  }
);
