(function () {
  "use strict";

  const STORAGE_KEY = "heartly-theme";
  const root = document.documentElement;
  const media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;

  function savedTheme() {
    try {
      return localStorage.getItem(STORAGE_KEY) || "system";
    } catch (error) {
      return "system";
    }
  }

  function systemTheme() {
    return media && media.matches ? "dark" : "light";
  }

  function applyTheme(value) {
    const requested = value || savedTheme();
    const resolved = requested === "system" ? systemTheme() : requested;

    root.dataset.heartlyTheme = resolved;
    root.classList.toggle("heartly-dark-root", resolved === "dark");
    root.classList.toggle("heartly-light-root", resolved !== "dark");

    if (document.body) {
      document.body.dataset.heartlyTheme = resolved;
      document.body.classList.toggle("heartly-dark", resolved === "dark");
      document.body.classList.toggle("heartly-light", resolved !== "dark");
    }
  }

  window.HeartlyTheme = {
    apply: function (value) {
      const next = value || "system";
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch (error) {}
      applyTheme(next);
    },
    current: function () {
      return savedTheme();
    }
  };

  applyTheme(savedTheme());

  document.addEventListener("DOMContentLoaded", function () {
    applyTheme(savedTheme());

    document.querySelectorAll("[data-theme-choice]").forEach(function (button) {
      button.addEventListener("click", function () {
        window.HeartlyTheme.apply(button.getAttribute("data-theme-choice"));
      });
    });
  });

  if (media && media.addEventListener) {
    media.addEventListener("change", function () {
      if (savedTheme() === "system") {
        applyTheme("system");
      }
    });
  }
})();
