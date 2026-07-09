(function () {
  "use strict";

  const INSTALL_BUTTON_SELECTOR = "[data-pwa-install]";
  let deferredInstallPrompt = null;

  function isStandalone() {
    return (
      window.matchMedia("(display-mode: standalone)").matches ||
      window.navigator.standalone === true
    );
  }

  function setInstallButtonsVisible(isVisible) {
    document.querySelectorAll(INSTALL_BUTTON_SELECTOR).forEach(function (button) {
      button.hidden = !isVisible;
      button.disabled = !isVisible;
    });
  }

  function registerServiceWorker() {
    if (!("serviceWorker" in navigator)) {
      return;
    }

    window.addEventListener("load", function () {
      navigator.serviceWorker
        .register("/sw.js", { scope: "/" })
        .catch(function (error) {
          if (window.console) {
            console.warn("Heartly service worker registration failed:", error);
          }
        });
    });
  }

  window.addEventListener("beforeinstallprompt", function (event) {
    event.preventDefault();
    deferredInstallPrompt = event;
    setInstallButtonsVisible(true);
  });

  window.addEventListener("appinstalled", function () {
    deferredInstallPrompt = null;
    setInstallButtonsVisible(false);
    document.documentElement.classList.add("heartly-pwa-installed");
  });

  document.addEventListener("click", async function (event) {
    const button = event.target.closest(INSTALL_BUTTON_SELECTOR);

    if (!button || !deferredInstallPrompt) {
      return;
    }

    button.disabled = true;
    deferredInstallPrompt.prompt();

    try {
      await deferredInstallPrompt.userChoice;
    } finally {
      deferredInstallPrompt = null;
      setInstallButtonsVisible(false);
    }
  });

  if (isStandalone()) {
    document.documentElement.classList.add("heartly-pwa-installed");
    setInstallButtonsVisible(false);
  }

  registerServiceWorker();
})();
