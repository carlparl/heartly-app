(function () {
  "use strict";

  function getCookie(name) {
    const cookies = document.cookie ? document.cookie.split(";") : [];

    for (const cookie of cookies) {
      const trimmed = cookie.trim();

      if (trimmed.startsWith(name + "=")) {
        return decodeURIComponent(trimmed.slice(name.length + 1));
      }
    }

    return "";
  }

  function closeMenus() {
    document.querySelectorAll(".post-menu[open]").forEach(function (menu) {
      menu.removeAttribute("open");
    });
  }

  function setInlineError(form, message) {
    let holder = form.querySelector("[data-feed-error]");

    if (!holder) {
      holder = document.createElement("div");
      holder.className = "feed-inline-error";
      holder.setAttribute("data-feed-error", "");
      form.insertBefore(holder, form.firstChild);
    }

    holder.textContent = message || "";
    holder.hidden = !message;
  }

  function clearInlineError(form) {
    const holder = form.querySelector("[data-feed-error]");
    if (holder) {
      holder.textContent = "";
      holder.hidden = true;
    }
  }

  function getOpenSheetId() {
    const openSheet = document.querySelector("[data-comments-sheet]:not([hidden])");
    return openSheet ? openSheet.id : "";
  }

  function openCommentsSheet(sheetId, focusInput) {
    const sheet = document.getElementById(sheetId);
    if (!sheet) return;

    document.querySelectorAll("[data-comments-sheet]").forEach(function (item) {
      if (item !== sheet) {
        item.hidden = true;
        item.classList.remove("is-open");
      }
    });

    sheet.hidden = false;
    document.body.classList.add("comments-sheet-open");

    window.requestAnimationFrame(function () {
      sheet.classList.add("is-open");
    });

    if (focusInput) {
      window.setTimeout(function () {
        const input = sheet.querySelector(".ig-sheet-comment-form input[name='content']");
        if (input) input.focus();
      }, 180);
    }
  }

  function closeCommentsSheet(sheet) {
    const target = sheet || document.querySelector("[data-comments-sheet]:not([hidden])");
    if (!target) return;

    target.classList.remove("is-open");

    window.setTimeout(function () {
      target.hidden = true;
      if (!document.querySelector("[data-comments-sheet]:not([hidden])")) {
        document.body.classList.remove("comments-sheet-open");
      }
    }, 160);
  }

  function replacePost(data) {
    if (!data.post_html || !data.post_id) {
      return;
    }

    const openSheetId = getOpenSheetId();
    const currentPost = document.getElementById("post-" + data.post_id);
    const feedList = document.querySelector("[data-feed-list]");

    if (currentPost) {
      currentPost.outerHTML = data.post_html;

      if (openSheetId) {
        openCommentsSheet(openSheetId, false);
      }

      return;
    }

    if (feedList) {
      const empty = feedList.querySelector("[data-empty-feed]");
      if (empty) empty.remove();
      feedList.insertAdjacentHTML("afterbegin", data.post_html);
    }
  }

  function closeEditPanel(form) {
    const panel = form.closest(".edit-post-panel");
    if (panel) panel.hidden = true;
  }

  function resetComposerPreview() {
    const preview = document.getElementById("composerPreview");
    const clearBtn = document.getElementById("clearComposerMedia");

    if (preview) {
      preview.hidden = true;
      preview.innerHTML = "";
    }

    if (clearBtn) clearBtn.hidden = true;
  }

  function setLoading(button, active) {
    if (!button) return;
    button.disabled = active;
    button.classList.toggle("is-loading", active);
  }

  async function submitAjaxForm(form, submitter) {
    if (form.dataset.confirm && !confirm(form.dataset.confirm)) {
      return;
    }

    if (form.dataset.busy === "1") {
      return;
    }

    const button = submitter && submitter.tagName === "BUTTON"
      ? submitter
      : form.querySelector("button[type='submit']");

    form.dataset.busy = "1";
    setLoading(button, true);
    clearInlineError(form);

    try {
      const formData = new FormData(form);
      formData.append("_ajax", "1");

      const response = await fetch(form.action, {
        method: form.method || "POST",
        body: formData,
        headers: {
          "X-Requested-With": "XMLHttpRequest",
          "Accept": "application/json",
          "X-CSRFToken": getCookie("csrftoken")
        },
        credentials: "same-origin"
      });

      const contentType = response.headers.get("content-type") || "";

      if (!contentType.includes("application/json")) {
        throw new Error("Server returned a page instead of JSON.");
      }

      const data = await response.json();

      if (!response.ok || data.ok === false) {
        setInlineError(form, data.message || "Action failed.");
        return;
      }

      const removePostId = data.remove_post_id || (form.matches("[data-delete-post]") ? data.post_id : null);

      if (removePostId) {
        const post = document.getElementById("post-" + removePostId);
        if (post) post.remove();
      }

      if (data.post_html) {
        replacePost(data);
      }

      if (form.matches("[data-create-post]")) {
        form.reset();
        resetComposerPreview();
      }

      if (form.matches("[data-edit-post]")) {
        closeEditPanel(form);
      }

      if (form.matches("[data-comment-form], [data-reply-form]")) {
        form.reset();
      }

      closeMenus();
    } catch (error) {
      console.error("Heartly feed AJAX failed:", error);
      setInlineError(form, error.message || "Network error.");
    } finally {
      delete form.dataset.busy;
      setLoading(button, false);
    }
  }

  function insertTextAtCursor(input, value) {
    if (!input) return;

    const start = input.selectionStart || input.value.length;
    const end = input.selectionEnd || input.value.length;
    const before = input.value.slice(0, start);
    const after = input.value.slice(end);

    input.value = before + value + after;
    input.focus();

    const nextPosition = start + value.length;
    input.setSelectionRange(nextPosition, nextPosition);
  }

  document.addEventListener("submit", function (event) {
    const form = event.target.closest("form[data-feed-ajax]");

    if (!form) return;

    event.preventDefault();
    event.stopPropagation();
    submitAjaxForm(form, event.submitter);
  }, true);

  document.addEventListener("click", function (event) {
    const commentsButton = event.target.closest("[data-comments-open]");

    if (commentsButton) {
      event.preventDefault();
      openCommentsSheet(commentsButton.getAttribute("data-comments-open"), true);
      return;
    }

    const commentsClose = event.target.closest("[data-comments-close]");

    if (commentsClose) {
      event.preventDefault();
      const sheet = commentsClose.closest("[data-comments-sheet]");
      closeCommentsSheet(sheet);
      return;
    }

    const emojiButton = event.target.closest("[data-comment-emoji]");

    if (emojiButton) {
      event.preventDefault();
      const sheet = emojiButton.closest("[data-comments-sheet]");
      const input = sheet ? sheet.querySelector(".ig-sheet-comment-form input[name='content']") : null;
      insertTextAtCursor(input, emojiButton.getAttribute("data-comment-emoji"));
      return;
    }

    const replyButton = event.target.closest("[data-reply-toggle]");

    if (replyButton) {
      const form = document.getElementById(replyButton.getAttribute("data-reply-toggle"));

      if (form) {
        form.hidden = !form.hidden;

        if (!form.hidden) {
          const input = form.querySelector("input[name='content']");
          if (input) input.focus();
        }
      }
    }

    const openButton = event.target.closest("[data-edit-open]");

    if (openButton) {
      const panel = document.getElementById(openButton.getAttribute("data-edit-open"));
      if (panel) panel.hidden = false;
    }

    const closeButton = event.target.closest("[data-edit-close]");

    if (closeButton) {
      const panel = document.getElementById(closeButton.getAttribute("data-edit-close"));
      if (panel) panel.hidden = true;
    }

    const panel = event.target.closest(".edit-post-panel");
    if (panel && event.target === panel) panel.hidden = true;
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      closeCommentsSheet();
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    const imageInput = document.getElementById("composerImageInput");
    const videoInput = document.getElementById("composerVideoInput");
    const preview = document.getElementById("composerPreview");
    const clearBtn = document.getElementById("clearComposerMedia");

    function clearPreview() {
      if (!preview) return;
      preview.hidden = true;
      preview.innerHTML = "";
      if (clearBtn) clearBtn.hidden = true;
    }

    function showPreview(file, type) {
      if (!file || !preview) {
        clearPreview();
        return;
      }

      const url = URL.createObjectURL(file);
      preview.hidden = false;

      if (type === "image") {
        preview.innerHTML = `<img src="${url}" alt="Selected image preview">`;
      } else {
        preview.innerHTML = `<video controls playsinline preload="metadata"><source src="${url}">Your browser does not support video playback.</video>`;
      }

      if (clearBtn) clearBtn.hidden = false;
    }

    if (imageInput) {
      imageInput.addEventListener("change", function () {
        if (this.files && this.files[0]) {
          if (videoInput) videoInput.value = "";
          showPreview(this.files[0], "image");
        } else {
          clearPreview();
        }
      });
    }

    if (videoInput) {
      videoInput.addEventListener("change", function () {
        if (this.files && this.files[0]) {
          if (imageInput) imageInput.value = "";
          showPreview(this.files[0], "video");
        } else {
          clearPreview();
        }
      });
    }

    if (clearBtn) {
      clearBtn.addEventListener("click", function () {
        if (imageInput) imageInput.value = "";
        if (videoInput) videoInput.value = "";
        clearPreview();
      });
    }
  });
})();
