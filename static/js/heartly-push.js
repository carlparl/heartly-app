(function () {
  "use strict";

  const CONFIG_URL = "/notifications/push/config/";
  const SUBSCRIBE_URL = "/notifications/push/subscribe/";
  const DEFER_KEY = "heartlyPushPromptDeferredUntil";
  const WEEK = 7 * 24 * 60 * 60 * 1000;

  function getCookie(name) {
    const item = document.cookie.split(";").map((part) => part.trim())
      .find((part) => part.startsWith(name + "="));
    return item ? decodeURIComponent(item.slice(name.length + 1)) : "";
  }

  function base64ToUint8Array(value) {
    const padding = "=".repeat((4 - value.length % 4) % 4);
    const raw = atob((value + padding).replace(/-/g, "+").replace(/_/g, "/"));
    return Uint8Array.from(raw, (character) => character.charCodeAt(0));
  }

  function isIos() {
    return /iphone|ipad|ipod/i.test(navigator.userAgent);
  }

  function isStandalone() {
    return window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  }

  async function saveSubscription(subscription) {
    const response = await fetch(SUBSCRIBE_URL, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
        "X-Requested-With": "XMLHttpRequest"
      },
      body: JSON.stringify(subscription.toJSON())
    });
    if (!response.ok) {
      throw new Error("Heartly could not save this push subscription.");
    }
  }

  async function enablePush(config) {
    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      return false;
    }

    const registration = await navigator.serviceWorker.ready;
    let subscription = await registration.pushManager.getSubscription();
    if (!subscription) {
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: base64ToUint8Array(config.public_key)
      });
    }
    await saveSubscription(subscription);
    return true;
  }

  function buildPrompt(config) {
    const card = document.createElement("section");
    card.className = "heartly-push-card";
    card.setAttribute("role", "dialog");
    card.setAttribute("aria-label", "Enable Heartly notifications");
    card.innerHTML = `
      <div class="heartly-push-card__row">
        <div class="heartly-push-card__icon" aria-hidden="true">🔔</div>
        <div><h2>Stay updated on Heartly</h2><p>Allow alerts for likes, broadcasts, messages and incoming calls—even when Heartly is closed.</p></div>
      </div>
      <div class="heartly-push-card__actions">
        <button class="heartly-push-card__enable" type="button">Enable notifications</button>
        <button class="heartly-push-card__later" type="button">Not now</button>
      </div>`;

    card.querySelector(".heartly-push-card__later").addEventListener("click", function () {
      localStorage.setItem(DEFER_KEY, String(Date.now() + WEEK));
      card.remove();
    });
    card.querySelector(".heartly-push-card__enable").addEventListener("click", async function (event) {
      const button = event.currentTarget;
      button.disabled = true;
      button.textContent = "Enabling…";
      try {
        const enabled = await enablePush(config);
        if (enabled) {
          card.remove();
        } else {
          button.textContent = "Notifications blocked";
        }
      } catch (error) {
        console.warn(error);
        button.disabled = false;
        button.textContent = "Try again";
      }
    });
    document.body.appendChild(card);
  }

  async function initialise() {
    if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
      return;
    }
    if (isIos() && !isStandalone()) {
      return;
    }

    const response = await fetch(CONFIG_URL, { credentials: "same-origin" });
    if (!response.ok) return;
    const config = await response.json();
    if (!config.enabled || !config.public_key) return;

    if (Notification.permission === "granted") {
      await enablePush(config);
      return;
    }
    if (Notification.permission === "denied") return;
    if (Number(localStorage.getItem(DEFER_KEY) || 0) > Date.now()) return;

    window.setTimeout(function () { buildPrompt(config); }, 1200);
  }

  document.addEventListener("DOMContentLoaded", function () {
    initialise().catch(function (error) { console.warn("Heartly push setup failed:", error); });
  });
})();
