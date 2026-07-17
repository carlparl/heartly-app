(function () {
  "use strict";

  function getCookie(name) {
    const cookies = document.cookie
      ? document.cookie.split(";")
      : [];

    for (const cookie of cookies) {
      const trimmed = cookie.trim();

      if (trimmed.startsWith(name + "=")) {
        return decodeURIComponent(
          trimmed.slice(name.length + 1)
        );
      }
    }

    return "";
  }

  function setStatus(form, message) {
    const status = form.querySelector(
      "[data-story-reaction-status]"
    );

    if (!status) return;

    status.textContent = message || "";
    status.hidden = !message;
  }

  function buttonsFor(form) {
    return Array.from(
      form.querySelectorAll(
        "[data-story-reaction-button]"
      )
    );
  }

  function activeReaction(form) {
    const active = form.querySelector(
      "[data-story-reaction-button].is-active"
    );

    return active
      ? active.value
      : "";
  }

  function setActiveReaction(
    form,
    reactionType
  ) {
    buttonsFor(form).forEach(function (button) {
      const active =
        button.value === reactionType;

      button.classList.toggle(
        "is-active",
        active
      );
      button.setAttribute(
        "aria-pressed",
        active ? "true" : "false"
      );
    });
  }

  function setBusy(form, busy) {
    form.dataset.busy = busy ? "1" : "";

    buttonsFor(form).forEach(function (button) {
      button.disabled = busy;
    });

    form.classList.toggle(
      "is-loading",
      busy
    );
  }

  function dispatchPlaybackEvent(name) {
    document.dispatchEvent(
      new CustomEvent(name)
    );
  }

  async function submitReaction(
    form,
    submitter
  ) {
    if (
      form.dataset.busy === "1" ||
      !submitter
    ) {
      return;
    }

    const selected = submitter.value;
    const previous = activeReaction(form);

    setActiveReaction(form, selected);
    setStatus(form, "");
    setBusy(form, true);
    dispatchPlaybackEvent(
      "heartly:story-interaction-start"
    );

    try {
      const formData = new FormData(form);
      formData.set(
        "reaction_type",
        selected
      );
      formData.set("_ajax", "1");

      const response = await fetch(
        form.action,
        {
          method: "POST",
          body: formData,
          headers: {
            "X-Requested-With":
              "XMLHttpRequest",
            "Accept": "application/json",
            "X-CSRFToken":
              getCookie("csrftoken")
          },
          credentials: "same-origin"
        }
      );

      const contentType =
        response.headers.get(
          "content-type"
        ) || "";

      if (
        !contentType.includes(
          "application/json"
        )
      ) {
        throw new Error(
          "Story reaction could not be saved."
        );
      }

      const data = await response.json();

      if (
        !response.ok ||
        data.ok === false
      ) {
        throw new Error(
          data.message ||
          "Story reaction could not be saved."
        );
      }

      setActiveReaction(
        form,
        data.reaction_type || selected
      );
      setStatus(form, "");
    } catch (error) {
      setActiveReaction(form, previous);
      setStatus(
        form,
        error.message ||
        "Network error. Try again."
      );
    } finally {
      setBusy(form, false);
      dispatchPlaybackEvent(
        "heartly:story-interaction-end"
      );
    }
  }

  document.addEventListener(
    "submit",
    function (event) {
      const form = event.target.closest(
        "form[data-story-reaction-form]"
      );

      if (!form) return;

      event.preventDefault();
      event.stopPropagation();

      const submitter =
        event.submitter ||
        form.querySelector(
          "[data-story-reaction-button]"
        );

      submitReaction(form, submitter);
    },
    true
  );
})();
