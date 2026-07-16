(function () {
  "use strict";

  const CONFIG_URL = "/notifications/push/config/";
  const SUBSCRIBE_URL = "/notifications/push/subscribe/";
  const UNSUBSCRIBE_URL = "/notifications/push/unsubscribe/";
  const DEFER_KEY = "heartlyPushPromptDeferredUntil";
  const WEEK = 7 * 24 * 60 * 60 * 1000;

  let currentConfig = null;
  let syncPromise = null;

  function getCookie(name) {
    const item = document.cookie
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith(name + "="));

    return item
      ? decodeURIComponent(item.slice(name.length + 1))
      : "";
  }

  function base64ToUint8Array(value) {
    const padding = "=".repeat(
      (4 - value.length % 4) % 4
    );
    const raw = atob(
      (value + padding)
        .replace(/-/g, "+")
        .replace(/_/g, "/")
    );

    return Uint8Array.from(
      raw,
      (character) => character.charCodeAt(0)
    );
  }

  function uint8ArrayToBase64Url(value) {
    const bytes = value instanceof Uint8Array
      ? value
      : new Uint8Array(value);
    let binary = "";

    bytes.forEach((byte) => {
      binary += String.fromCharCode(byte);
    });

    return btoa(binary)
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/g, "");
  }

  function normalisePublicKey(value) {
    return String(value || "")
      .trim()
      .replace(/=+$/g, "");
  }

  function subscriptionUsesKey(
    subscription,
    publicKey
  ) {
    const options = subscription &&
      subscription.options;
    const applicationServerKey = options &&
      options.applicationServerKey;

    if (!applicationServerKey) {
      return true;
    }

    return (
      uint8ArrayToBase64Url(applicationServerKey) ===
      normalisePublicKey(publicKey)
    );
  }

  function isIos() {
    return /iphone|ipad|ipod/i.test(
      navigator.userAgent
    );
  }

  function isStandalone() {
    return (
      window.matchMedia(
        "(display-mode: standalone)"
      ).matches ||
      navigator.standalone === true
    );
  }

  function dispatchStatus(status, extra) {
    window.dispatchEvent(
      new CustomEvent("heartly:push-status", {
        detail: Object.assign(
          { status },
          extra || {}
        )
      })
    );
  }

  async function postJson(url, body) {
    const response = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json"
      },
      body: JSON.stringify(body)
    });

    if (!response.ok) {
      throw new Error(
        `Heartly push request failed: ${response.status}`
      );
    }

    return response.json();
  }

  async function saveSubscription(subscription) {
    await postJson(
      SUBSCRIBE_URL,
      subscription.toJSON()
    );
  }

  async function removeSubscription(subscription) {
    const endpoint = subscription &&
      subscription.endpoint;

    if (endpoint) {
      try {
        await postJson(
          UNSUBSCRIBE_URL,
          { endpoint }
        );
      } catch (error) {
        console.warn(
          "Heartly could not remove the old push " +
          "subscription from the server:",
          error
        );
      }
    }

    try {
      await subscription.unsubscribe();
    } catch (error) {
      console.warn(
        "Heartly could not unsubscribe the old " +
        "browser endpoint:",
        error
      );
    }
  }

  async function ensureSubscription(config) {
    if (syncPromise) {
      return syncPromise;
    }

    syncPromise = (async () => {
      const registration =
        await navigator.serviceWorker.ready;
      let subscription =
        await registration.pushManager
          .getSubscription();

      if (
        subscription &&
        !subscriptionUsesKey(
          subscription,
          config.public_key
        )
      ) {
        await removeSubscription(subscription);
        subscription = null;
      }

      if (!subscription) {
        subscription =
          await registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: base64ToUint8Array(
              config.public_key
            )
          });
      }

      await saveSubscription(subscription);
      localStorage.removeItem(DEFER_KEY);
      dispatchStatus("enabled", {
        endpoint: subscription.endpoint
      });
      return subscription;
    })();

    try {
      return await syncPromise;
    } finally {
      syncPromise = null;
    }
  }

  async function enablePush(
    config,
    requestPermission
  ) {
    let permission = Notification.permission;

    if (
      permission === "default" &&
      requestPermission
    ) {
      permission =
        await Notification.requestPermission();
    }

    if (permission !== "granted") {
      dispatchStatus(
        permission === "denied"
          ? "blocked"
          : "not-enabled"
      );
      return false;
    }

    await ensureSubscription(config);
    return true;
  }

  function buildPrompt(config) {
    if (
      document.querySelector(
        ".heartly-push-card"
      )
    ) {
      return;
    }

    const card = document.createElement("section");
    card.className = "heartly-push-card";
    card.setAttribute("role", "dialog");
    card.setAttribute(
      "aria-label",
      "Enable Heartly notifications"
    );
    card.innerHTML = `
      <div class="heartly-push-card__row">
        <div class="heartly-push-card__icon" aria-hidden="true">🔔</div>
        <div>
          <h2>Stay updated on Heartly</h2>
          <p>Allow alerts for likes, matches, messages, comments and incoming calls—even when Heartly is closed.</p>
        </div>
      </div>
      <div class="heartly-push-card__actions">
        <button class="heartly-push-card__enable" type="button">Enable notifications</button>
        <button class="heartly-push-card__later" type="button">Not now</button>
      </div>`;

    card.querySelector(
      ".heartly-push-card__later"
    ).addEventListener("click", function () {
      localStorage.setItem(
        DEFER_KEY,
        String(Date.now() + WEEK)
      );
      card.remove();
    });

    card.querySelector(
      ".heartly-push-card__enable"
    ).addEventListener(
      "click",
      async function (event) {
        const button = event.currentTarget;
        button.disabled = true;
        button.textContent = "Enabling…";

        try {
          const enabled = await enablePush(
            config,
            true
          );

          if (enabled) {
            card.remove();
          } else {
            button.textContent =
              "Notifications blocked";
          }
        } catch (error) {
          console.warn(error);
          dispatchStatus("error", {
            message: String(error)
          });
          button.disabled = false;
          button.textContent = "Try again";
        }
      }
    );

    document.body.appendChild(card);
  }

  async function fetchConfig() {
    const response = await fetch(CONFIG_URL, {
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest"
      }
    });

    if (!response.ok) {
      throw new Error(
        `Push configuration failed: ${response.status}`
      );
    }

    return response.json();
  }

  async function initialise() {
    if (
      !("serviceWorker" in navigator) ||
      !("PushManager" in window) ||
      !("Notification" in window)
    ) {
      dispatchStatus("unsupported");
      return;
    }

    if (isIos() && !isStandalone()) {
      dispatchStatus("install-required");
      return;
    }

    const config = await fetchConfig();
    currentConfig = config;

    if (!config.enabled || !config.public_key) {
      dispatchStatus("server-disabled");
      return;
    }

    if (Notification.permission === "granted") {
      await enablePush(config, false);
      return;
    }

    if (Notification.permission === "denied") {
      dispatchStatus("blocked");
      return;
    }

    if (
      Number(
        localStorage.getItem(DEFER_KEY) || 0
      ) > Date.now()
    ) {
      dispatchStatus("deferred");
      return;
    }

    window.setTimeout(
      function () {
        buildPrompt(config);
      },
      1200
    );
  }

  async function resynchronise() {
    if (
      !currentConfig ||
      Notification.permission !== "granted"
    ) {
      return;
    }

    try {
      await ensureSubscription(currentConfig);
    } catch (error) {
      console.warn(
        "Heartly push resynchronisation failed:",
        error
      );
      dispatchStatus("error", {
        message: String(error)
      });
    }
  }

  document.addEventListener(
    "DOMContentLoaded",
    function () {
      initialise().catch(function (error) {
        console.warn(
          "Heartly push setup failed:",
          error
        );
        dispatchStatus("error", {
          message: String(error)
        });
      });
    }
  );

  window.addEventListener(
    "online",
    resynchronise
  );

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.addEventListener(
      "message",
      function (event) {
        const data = event.data || {};

        if (
          data.type ===
          "heartly.push.subscription-change"
        ) {
          resynchronise();
        }
      }
    );
  }
})();
