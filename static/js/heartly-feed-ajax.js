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

  function closeMenus() {
    document
      .querySelectorAll(".post-menu[open]")
      .forEach(function (menu) {
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

  function getPost(form) {
    return form.closest("[data-post-id]");
  }

  function numberFrom(element) {
    return Math.max(
      0,
      Number.parseInt(
        element ? element.textContent : "0",
        10
      ) || 0
    );
  }

  function setCount(element, value) {
    if (!element) return;
    element.textContent = String(
      Math.max(0, Number(value) || 0)
    );
  }

  function setPressed(button, active) {
    if (!button) return;

    button.classList.toggle("is-active", active);
    button.setAttribute(
      "aria-pressed",
      active ? "true" : "false"
    );
  }

  function snapshotButton(button) {
    if (!button) return null;

    return {
      active: button.classList.contains("is-active"),
      pressed: button.getAttribute("aria-pressed"),
      label: button.getAttribute("aria-label")
    };
  }

  function restoreButton(button, snapshot) {
    if (!button || !snapshot) return;

    button.classList.toggle(
      "is-active",
      snapshot.active
    );

    if (snapshot.pressed === null) {
      button.removeAttribute("aria-pressed");
    } else {
      button.setAttribute(
        "aria-pressed",
        snapshot.pressed
      );
    }

    if (snapshot.label === null) {
      button.removeAttribute("aria-label");
    } else {
      button.setAttribute(
        "aria-label",
        snapshot.label
      );
    }
  }

  function applyOptimisticState(form) {
    const post = getPost(form);

    if (form.matches("[data-like-form]")) {
      const button = form.querySelector(
        "[data-like-button]"
      );
      const count = post && post.querySelector(
        "[data-like-count]"
      );
      const active = button &&
        button.classList.contains("is-active");
      const snapshot = {
        type: "like",
        button,
        buttonState: snapshotButton(button),
        count,
        countValue: numberFrom(count)
      };

      setPressed(button, !active);
      setCount(
        count,
        snapshot.countValue + (active ? -1 : 1)
      );

      return snapshot;
    }

    if (form.matches("[data-save-post]")) {
      const button = form.querySelector(
        "[data-save-button]"
      );
      const active = button &&
        button.classList.contains("is-active");
      const snapshot = {
        type: "save",
        button,
        buttonState: snapshotButton(button)
      };

      setPressed(button, !active);
      if (button) {
        button.setAttribute(
          "aria-label",
          active ? "Save post" : "Unsave post"
        );
      }

      return snapshot;
    }

    if (form.matches("[data-comment-reaction]")) {
      const button = form.querySelector(
        "[data-comment-like-button]"
      );
      const count = form.querySelector(
        "[data-comment-like-count]"
      );
      const active = button &&
        button.classList.contains("is-active");
      const snapshot = {
        type: "comment-reaction",
        button,
        buttonState: snapshotButton(button),
        count,
        countValue: numberFrom(count),
        countHidden: count ? count.hidden : true
      };

      setPressed(button, !active);
      const next = snapshot.countValue +
        (active ? -1 : 1);
      setCount(count, next);
      if (count) count.hidden = next === 0;

      return snapshot;
    }

    return null;
  }

  function rollbackOptimisticState(snapshot) {
    if (!snapshot) return;

    restoreButton(
      snapshot.button,
      snapshot.buttonState
    );

    if (snapshot.count) {
      setCount(
        snapshot.count,
        snapshot.countValue
      );
      snapshot.count.hidden = Boolean(
        snapshot.countHidden
      );
    }
  }

  function getOpenSheetId() {
    const openSheet = document.querySelector(
      "[data-comments-sheet]:not([hidden])"
    );

    return openSheet ? openSheet.id : "";
  }

  function openCommentsSheet(sheetId, focusInput) {
    const sheet = document.getElementById(sheetId);
    if (!sheet) return;

    document
      .querySelectorAll("[data-comments-sheet]")
      .forEach(function (item) {
        if (item !== sheet) {
          item.hidden = true;
          item.classList.remove("is-open");
        }
      });

    sheet.hidden = false;
    document.body.classList.add(
      "comments-sheet-open"
    );

    window.requestAnimationFrame(function () {
      sheet.classList.add("is-open");
    });

    if (focusInput) {
      window.setTimeout(function () {
        const input = sheet.querySelector(
          ".ig-sheet-comment-form " +
          "input[name='content']"
        );
        if (input) input.focus();
      }, 180);
    }
  }

  function closeCommentsSheet(sheet) {
    const target = sheet ||
      document.querySelector(
        "[data-comments-sheet]:not([hidden])"
      );

    if (!target) return;

    target.classList.remove("is-open");

    window.setTimeout(function () {
      target.hidden = true;

      if (
        !document.querySelector(
          "[data-comments-sheet]:not([hidden])"
        )
      ) {
        document.body.classList.remove(
          "comments-sheet-open"
        );
      }
    }, 160);
  }

  function replacePost(data) {
    if (!data.post_html || !data.post_id) return;

    const openSheetId = getOpenSheetId();
    const currentPost = document.getElementById(
      "post-" + data.post_id
    );
    const feedList = document.querySelector(
      "[data-feed-list]"
    );

    if (currentPost) {
      currentPost.outerHTML = data.post_html;

      if (openSheetId) {
        openCommentsSheet(
          openSheetId,
          false
        );
      }

      return;
    }

    if (feedList) {
      const empty = feedList.querySelector(
        "[data-empty-feed]"
      );
      if (empty) empty.remove();

      feedList.insertAdjacentHTML(
        "afterbegin",
        data.post_html
      );
    }
  }

  function updateCommentCount(post, value) {
    if (!post) return;

    const count = post.querySelector(
      "[data-comment-count]"
    );
    setCount(count, value);

    const label = post.querySelector(
      "[data-view-comments-label]"
    );

    if (label) {
      const number = Math.max(
        0,
        Number(value) || 0
      );

      label.textContent =
        "View all " +
        number +
        " comment" +
        (number === 1 ? "" : "s");
      label.hidden = number === 0;
    }
  }

  function insertCommentResponse(form, data) {
    const post = getPost(form);
    if (!post || !data.comment_html) return;

    const list = post.querySelector(
      "[data-comments-list]"
    );
    if (!list) return;

    const empty = list.querySelector(
      ".ig-no-comments"
    );
    if (empty) empty.remove();

    list.insertAdjacentHTML(
      "beforeend",
      data.comment_html
    );

    updateCommentCount(
      post,
      data.comments_count
    );
  }

  function insertReplyResponse(form, data) {
    const post = getPost(form);
    if (!post || !data.reply_html) return;

    const parent = post.querySelector(
      '[data-comment-id="' +
      String(data.parent_id) +
      '"]'
    );
    if (!parent) return;

    const list = parent.querySelector(
      "[data-replies-list]"
    );
    if (!list) return;

    list.insertAdjacentHTML(
      "beforeend",
      data.reply_html
    );

    const more = parent.querySelector(
      ".ig-view-more-replies"
    );
    if (
      more &&
      Number(data.replies_count) <=
        list.children.length
    ) {
      more.remove();
    }
  }

  function applyServerResponse(form, data) {
    const post = getPost(form);

    if (form.matches("[data-like-form]")) {
      const button = form.querySelector(
        "[data-like-button]"
      );
      const count = post && post.querySelector(
        "[data-like-count]"
      );

      setPressed(button, Boolean(data.reacted));
      setCount(count, data.likes_count);
      return;
    }

    if (form.matches("[data-save-post]")) {
      const button = form.querySelector(
        "[data-save-button]"
      );

      setPressed(button, Boolean(data.saved));

      if (button) {
        button.setAttribute(
          "aria-label",
          data.saved ? "Unsave post" : "Save post"
        );
      }
      return;
    }

    if (form.matches("[data-comment-form]")) {
      insertCommentResponse(form, data);
      return;
    }

    if (form.matches("[data-reply-form]")) {
      insertReplyResponse(form, data);
      return;
    }

    if (form.matches("[data-comment-reaction]")) {
      const button = form.querySelector(
        "[data-comment-like-button]"
      );
      const count = form.querySelector(
        "[data-comment-like-count]"
      );

      setPressed(button, Boolean(data.reacted));
      setCount(count, data.reaction_count);
      if (count) {
        count.hidden = (
          Number(data.reaction_count) === 0
        );
      }
      return;
    }

    if (data.post_html) {
      replacePost(data);
    }
  }

  function closeEditPanel(form) {
    const panel = form.closest(
      ".edit-post-panel"
    );
    if (panel) panel.hidden = true;
  }

  function resetComposerPreview() {
    const preview = document.getElementById(
      "composerPreview"
    );
    const clearBtn = document.getElementById(
      "clearComposerMedia"
    );

    if (preview) {
      preview.hidden = true;
      preview.innerHTML = "";
    }

    if (clearBtn) clearBtn.hidden = true;
  }

  function setLoading(button, active) {
    if (!button) return;
    button.disabled = active;
    button.classList.toggle(
      "is-loading",
      active
    );
  }

  async function submitAjaxForm(
    form,
    submitter
  ) {
    if (
      form.dataset.confirm &&
      !confirm(form.dataset.confirm)
    ) {
      return;
    }

    if (form.dataset.busy === "1") return;

    const button =
      submitter &&
      submitter.tagName === "BUTTON"
        ? submitter
        : form.querySelector(
            "button[type='submit']"
          );

    form.dataset.busy = "1";
    const optimistic = applyOptimisticState(form);
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

      const contentType =
        response.headers.get("content-type") || "";

      if (
        !contentType.includes(
          "application/json"
        )
      ) {
        throw new Error(
          "Server returned a page instead of JSON."
        );
      }

      const data = await response.json();

      if (!response.ok || data.ok === false) {
        rollbackOptimisticState(optimistic);
        setInlineError(
          form,
          data.message || "Action failed."
        );
        return;
      }

      const removePostId =
        data.remove_post_id ||
        (
          form.matches("[data-delete-post]")
            ? data.post_id
            : null
        );

      if (removePostId) {
        const post = document.getElementById(
          "post-" + removePostId
        );
        if (post) post.remove();
      }

      applyServerResponse(form, data);

      if (form.matches("[data-create-post]")) {
        form.reset();
        resetComposerPreview();
      }

      if (form.matches("[data-edit-post]")) {
        closeEditPanel(form);
      }

      if (
        form.matches(
          "[data-comment-form], " +
          "[data-reply-form]"
        )
      ) {
        form.reset();
      }

      closeMenus();
    } catch (error) {
      rollbackOptimisticState(optimistic);
      console.error(
        "Heartly feed AJAX failed:",
        error
      );
      setInlineError(
        form,
        error.message || "Network error."
      );
    } finally {
      delete form.dataset.busy;
      setLoading(button, false);
    }
  }

  function insertTextAtCursor(input, value) {
    if (!input) return;

    const start =
      input.selectionStart || input.value.length;
    const end =
      input.selectionEnd || input.value.length;
    const before = input.value.slice(0, start);
    const after = input.value.slice(end);

    input.value = before + value + after;
    input.focus();

    const nextPosition = start + value.length;
    input.setSelectionRange(
      nextPosition,
      nextPosition
    );
  }

  document.addEventListener(
    "submit",
    function (event) {
      const form = event.target.closest(
        "form[data-feed-ajax]"
      );

      if (!form) return;

      event.preventDefault();
      event.stopPropagation();
      submitAjaxForm(form, event.submitter);
    },
    true
  );

  document.addEventListener(
    "click",
    function (event) {
      const commentsButton = event.target.closest(
        "[data-comments-open]"
      );

      if (commentsButton) {
        event.preventDefault();
        openCommentsSheet(
          commentsButton.getAttribute(
            "data-comments-open"
          ),
          true
        );
        return;
      }

      const commentsClose = event.target.closest(
        "[data-comments-close]"
      );

      if (commentsClose) {
        event.preventDefault();
        closeCommentsSheet(
          commentsClose.closest(
            "[data-comments-sheet]"
          )
        );
        return;
      }

      const emojiButton = event.target.closest(
        "[data-comment-emoji]"
      );

      if (emojiButton) {
        event.preventDefault();
        const sheet = emojiButton.closest(
          "[data-comments-sheet]"
        );
        const input = sheet
          ? sheet.querySelector(
              ".ig-sheet-comment-form " +
              "input[name='content']"
            )
          : null;

        insertTextAtCursor(
          input,
          emojiButton.getAttribute(
            "data-comment-emoji"
          )
        );
        return;
      }

      const replyButton = event.target.closest(
        "[data-reply-toggle]"
      );

      if (replyButton) {
        const form = document.getElementById(
          replyButton.getAttribute(
            "data-reply-toggle"
          )
        );

        if (form) {
          form.hidden = !form.hidden;

          if (!form.hidden) {
            const input = form.querySelector(
              "input[name='content']"
            );
            if (input) input.focus();
          }
        }
      }

      const openButton = event.target.closest(
        "[data-edit-open]"
      );

      if (openButton) {
        const panel = document.getElementById(
          openButton.getAttribute(
            "data-edit-open"
          )
        );
        if (panel) panel.hidden = false;
      }

      const closeButton = event.target.closest(
        "[data-edit-close]"
      );

      if (closeButton) {
        const panel = document.getElementById(
          closeButton.getAttribute(
            "data-edit-close"
          )
        );
        if (panel) panel.hidden = true;
      }

      const panel = event.target.closest(
        ".edit-post-panel"
      );
      if (panel && event.target === panel) {
        panel.hidden = true;
      }
    }
  );

  document.addEventListener(
    "keydown",
    function (event) {
      if (event.key === "Escape") {
        closeCommentsSheet();
      }
    }
  );

  document.addEventListener(
    "DOMContentLoaded",
    function () {
      const imageInput = document.getElementById(
        "composerImageInput"
      );
      const videoInput = document.getElementById(
        "composerVideoInput"
      );
      const preview = document.getElementById(
        "composerPreview"
      );
      const clearBtn = document.getElementById(
        "clearComposerMedia"
      );

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
          preview.innerHTML =
            '<img src="' +
            url +
            '" alt="Selected image preview">';
        } else {
          preview.innerHTML =
            '<video controls playsinline ' +
            'preload="metadata">' +
            '<source src="' +
            url +
            '">' +
            "Your browser does not support " +
            "video playback.</video>";
        }

        if (clearBtn) clearBtn.hidden = false;
      }

      if (imageInput) {
        imageInput.addEventListener(
          "change",
          function () {
            if (this.files && this.files[0]) {
              if (videoInput) {
                videoInput.value = "";
              }
              showPreview(
                this.files[0],
                "image"
              );
            } else {
              clearPreview();
            }
          }
        );
      }

      if (videoInput) {
        videoInput.addEventListener(
          "change",
          function () {
            if (this.files && this.files[0]) {
              if (imageInput) {
                imageInput.value = "";
              }
              showPreview(
                this.files[0],
                "video"
              );
            } else {
              clearPreview();
            }
          }
        );
      }

      if (clearBtn) {
        clearBtn.addEventListener(
          "click",
          function () {
            if (imageInput) {
              imageInput.value = "";
            }
            if (videoInput) {
              videoInput.value = "";
            }
            clearPreview();
          }
        );
      }
    }
  );
})();
