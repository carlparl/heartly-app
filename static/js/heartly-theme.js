(function () {
  const STORAGE_KEY = "heartly-theme";
  const root = document.documentElement;
  const validThemes = ["system", "light", "dark"];

  function getStoredTheme() {
    const savedTheme = localStorage.getItem(STORAGE_KEY);

    if (validThemes.includes(savedTheme)) {
      return savedTheme;
    }

    return "system";
  }

  function applyTheme(theme) {
    const safeTheme = validThemes.includes(theme) ? theme : "system";

    root.setAttribute("data-theme", safeTheme);
    localStorage.setItem(STORAGE_KEY, safeTheme);

    updateThemeButtons(safeTheme);
  }

  function updateThemeButtons(activeTheme) {
    const buttons = document.querySelectorAll("[data-theme-choice]");

    buttons.forEach(function (button) {
      const buttonTheme = button.getAttribute("data-theme-choice");

      if (buttonTheme === activeTheme) {
        button.classList.add("is-active");
        button.setAttribute("aria-pressed", "true");
      } else {
        button.classList.remove("is-active");
        button.setAttribute("aria-pressed", "false");
      }
    });
  }

  function bindThemeButtons() {
    const buttons = document.querySelectorAll("[data-theme-choice]");

    buttons.forEach(function (button) {
      button.addEventListener("click", function () {
        const selectedTheme = button.getAttribute("data-theme-choice");
        applyTheme(selectedTheme);
      });
    });
  }

  function watchSystemThemeChanges() {
    if (!window.matchMedia) return;

    const systemTheme = window.matchMedia("(prefers-color-scheme: dark)");

    systemTheme.addEventListener("change", function () {
      const currentTheme = getStoredTheme();

      if (currentTheme === "system") {
        root.setAttribute("data-theme", "system");
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    const theme = getStoredTheme();

    applyTheme(theme);
    bindThemeButtons();
    watchSystemThemeChanges();
  });

  window.HeartlyTheme = {
    applyTheme: applyTheme,
    getStoredTheme: getStoredTheme
  };
})();