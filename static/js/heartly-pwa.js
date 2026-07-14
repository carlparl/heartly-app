(function () {
  "use strict";

  let deferredInstallPrompt = null;
  let installCard = null;

  const isIOS = /iphone|ipad|ipod/i.test(window.navigator.userAgent);
  const isAndroid = /android/i.test(window.navigator.userAgent);
  const isMobile = isIOS || isAndroid || window.matchMedia("(max-width: 820px)").matches;
  const isStandalone =
    window.matchMedia("(display-mode: standalone)").matches ||
    window.navigator.standalone === true;

  function addInstallStyles() {
    if (document.getElementById("heartlyPwaInstallStyles")) {
      return;
    }

    const style = document.createElement("style");
    style.id = "heartlyPwaInstallStyles";
    style.textContent = `
      .heartly-pwa-install {
        position: fixed;
        left: 12px;
        right: 12px;
        bottom: calc(env(safe-area-inset-bottom, 0px) + 94px);
        z-index: 9000;
        width: min(calc(100% - 24px), 460px);
        margin: 0 auto;
        padding: 14px;
        border: 1px solid var(--heartly-border, rgba(15, 23, 42, .10));
        border-radius: 22px;
        display: grid;
        grid-template-columns: 48px minmax(0, 1fr) auto;
        gap: 11px;
        align-items: center;
        color: var(--heartly-text, #0f172a);
        background: var(--heartly-card, #ffffff);
        box-shadow: 0 18px 55px rgba(15, 23, 42, .20);
      }
      body:not(.heartly-authenticated) .heartly-pwa-install {
        bottom: calc(env(safe-area-inset-bottom, 0px) + 14px);
      }
      .heartly-pwa-install__icon {
        width: 48px;
        height: 48px;
        border-radius: 14px;
        object-fit: cover;
      }
      .heartly-pwa-install__copy { min-width: 0; }
      .heartly-pwa-install__copy strong {
        display: block;
        margin-bottom: 3px;
        font-size: .92rem;
        line-height: 1.2;
        font-weight: 900;
      }
      .heartly-pwa-install__copy p {
        margin: 0;
        color: var(--heartly-muted, #64748b);
        font-size: .76rem;
        line-height: 1.4;
        font-weight: 650;
      }
      .heartly-pwa-install__actions {
        display: flex;
        align-items: center;
        gap: 6px;
      }
      .heartly-pwa-install__button,
      .heartly-pwa-install__close {
        border: 0;
        cursor: pointer;
        font: inherit;
      }
      .heartly-pwa-install__button {
        border-radius: 999px;
        padding: 10px 13px;
        color: #ffffff;
        background: linear-gradient(135deg, #18aaa1, #f24d6b);
        font-size: .76rem;
        font-weight: 900;
        white-space: nowrap;
      }
      .heartly-pwa-install__close {
        width: 32px;
        height: 32px;
        border-radius: 50%;
        color: var(--heartly-muted, #64748b);
        background: var(--heartly-card-soft, #f1f5f9);
        font-size: 1rem;
      }
      @media (max-width: 390px) {
        .heartly-pwa-install {
          grid-template-columns: 42px minmax(0, 1fr);
        }
        .heartly-pwa-install__icon {
          width: 42px;
          height: 42px;
        }
        .heartly-pwa-install__actions {
          grid-column: 1 / -1;
          justify-content: flex-end;
        }
      }
    `;
    document.head.appendChild(style);
  }

  function hideInstallCard() {
    if (installCard) {
      installCard.remove();
      installCard = null;
    }
  }

  function buildInstallCard() {
    if (!isMobile || isStandalone || sessionStorage.getItem("heartlyPwaDismissed") === "1") {
      return;
    }

    addInstallStyles();
    hideInstallCard();

    const card = document.createElement("aside");
    card.className = "heartly-pwa-install";
    card.setAttribute("role", "region");
    card.setAttribute("aria-label", "Install Heartly");

    const icon = document.createElement("img");
    icon.className = "heartly-pwa-install__icon";
    icon.src = "/pwa/icon-192.png";
    icon.alt = "";

    const copy = document.createElement("div");
    copy.className = "heartly-pwa-install__copy";

    const title = document.createElement("strong");
    const message = document.createElement("p");

    if (isIOS) {
      title.textContent = "Install Heartly on iPhone";
      message.textContent = "In Safari, tap Share, choose Add to Home Screen, keep Open as Web App on, then tap Add.";
    } else if (deferredInstallPrompt) {
      title.textContent = "Install Heartly";
      message.textContent = "Add Heartly to your phone for a full-screen app experience.";
    } else {
      title.textContent = "Add Heartly to your phone";
      message.textContent = "Open your browser menu and choose Install app or Add to Home screen.";
    }

    copy.append(title, message);

    const actions = document.createElement("div");
    actions.className = "heartly-pwa-install__actions";

    if (deferredInstallPrompt && !isIOS) {
      const installButton = document.createElement("button");
      installButton.type = "button";
      installButton.className = "heartly-pwa-install__button";
      installButton.textContent = "Install";
      installButton.addEventListener("click", async function () {
        const prompt = deferredInstallPrompt;

        if (!prompt) {
          return;
        }

        deferredInstallPrompt = null;
        prompt.prompt();
        const choice = await prompt.userChoice;

        if (choice.outcome === "accepted") {
          hideInstallCard();
        } else {
          buildInstallCard();
        }
      });
      actions.appendChild(installButton);
    }

    const closeButton = document.createElement("button");
    closeButton.type = "button";
    closeButton.className = "heartly-pwa-install__close";
    closeButton.setAttribute("aria-label", "Close install message");
    closeButton.textContent = "×";
    closeButton.addEventListener("click", function () {
      sessionStorage.setItem("heartlyPwaDismissed", "1");
      hideInstallCard();
    });
    actions.appendChild(closeButton);

    card.append(icon, copy, actions);
    document.body.appendChild(card);
    installCard = card;
  }

  window.addEventListener("beforeinstallprompt", function (event) {
    event.preventDefault();
    deferredInstallPrompt = event;
    buildInstallCard();
  });

  window.addEventListener("appinstalled", function () {
    deferredInstallPrompt = null;
    hideInstallCard();
  });

  document.addEventListener("DOMContentLoaded", buildInstallCard);

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/sw.js", {
        scope: "/",
        updateViaCache: "none"
      }).then(function (registration) {
        registration.update();

        if (registration.waiting) {
          registration.waiting.postMessage({ type: "SKIP_WAITING" });
        }
      }).catch(function (error) {
        console.warn("Heartly service worker registration failed:", error);
      });
    });
  }
})();
