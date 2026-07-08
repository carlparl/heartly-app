(function () {
  "use strict";

  const OLD_KEY = "heartlyTheme";
  const NEW_KEY = "heartly-theme";
  const root = document.documentElement;
  const validThemes = ["light", "dark"];

  function preferredSystemTheme() {
    if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
      return "dark";
    }
    return "light";
  }

  function getStoredTheme() {
    const stored = localStorage.getItem(OLD_KEY) || localStorage.getItem(NEW_KEY);
    if (validThemes.includes(stored)) return stored;
    return preferredSystemTheme();
  }

  function updateThemeControls(theme) {
    document.querySelectorAll("[data-heartly-theme-choice]").forEach(function (button) {
      const value = button.getAttribute("data-heartly-theme-choice");
      button.classList.toggle("is-active", value === theme);
      button.setAttribute("aria-pressed", value === theme ? "true" : "false");
    });

    document.querySelectorAll("[data-theme-choice]").forEach(function (button) {
      const value = button.getAttribute("data-theme-choice");
      button.classList.toggle("is-active", value === theme);
      button.setAttribute("aria-pressed", value === theme ? "true" : "false");
    });

    document.querySelectorAll("[data-heartly-theme-input]").forEach(function (input) {
      input.checked = input.value === theme;
    });

    document.querySelectorAll("[data-heartly-theme-label]").forEach(function (label) {
      label.textContent = theme === "dark" ? "Dark" : "Light";
    });
  }

  function applyTheme(theme) {
    const safeTheme = theme === "dark" ? "dark" : "light";

    root.classList.toggle("heartly-dark-root", safeTheme === "dark");
    root.setAttribute("data-heartly-theme", safeTheme);
    root.setAttribute("data-theme", safeTheme);

    if (document.body) {
      document.body.classList.toggle("heartly-dark", safeTheme === "dark");
      document.body.setAttribute("data-heartly-theme", safeTheme);
      document.body.setAttribute("data-theme", safeTheme);
    }

    localStorage.setItem(OLD_KEY, safeTheme);
    localStorage.setItem(NEW_KEY, safeTheme);

    const metaTheme = document.querySelector('meta[name="theme-color"]');
    if (metaTheme) {
      metaTheme.setAttribute("content", safeTheme === "dark" ? "#03080e" : "#18aaa1");
    }

    updateThemeControls(safeTheme);
  }

  function toggleTheme() {
    applyTheme(root.classList.contains("heartly-dark-root") ? "light" : "dark");
  }

  function bindThemeControls() {
    document.querySelectorAll("[data-heartly-theme-choice], [data-theme-choice]").forEach(function (button) {
      button.addEventListener("click", function () {
        applyTheme(button.getAttribute("data-heartly-theme-choice") || button.getAttribute("data-theme-choice"));
      });
    });

    document.querySelectorAll("[data-heartly-theme-toggle]").forEach(function (button) {
      button.addEventListener("click", toggleTheme);
    });

    document.querySelectorAll("[data-heartly-theme-input]").forEach(function (input) {
      input.addEventListener("change", function () {
        if (input.checked) applyTheme(input.value);
      });
    });
  }

  window.applyHeartlyTheme = applyTheme;
  window.setHeartlyTheme = applyTheme;
  window.toggleHeartlyTheme = toggleTheme;
  window.HeartlyTheme = {
    applyTheme: applyTheme,
    getStoredTheme: getStoredTheme,
    toggleTheme: toggleTheme
  };

  applyTheme(getStoredTheme());

  document.addEventListener("DOMContentLoaded", function () {
    applyTheme(getStoredTheme());
    bindThemeControls();
  });
})();
