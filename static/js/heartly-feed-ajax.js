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

  function showToast(message, type) {
    let toast = document.querySelector("[data-feed-toast]");

    if (!toast) {
      toast = document.createElement("div");
      toast.setAttribute("data-feed-toast", "");
      toast.style.position = "fixed";
      toast.style.left = "50%";
      toast.style.bottom = "100px";
      toast.style.zIndex = "99999";
      toast.style.transform = "translateX(-50%)";
      toast.style.maxWidth = "min(92vw, 420px)";
      toast.style.padding = "12px 16px";
      toast.style.borderRadius = "999px";
      toast.style.fontWeight = "900";
      toast.style.boxShadow = "0 16px 40px rgba(0,0,0,.22)";
      document.body.appendChild(toast);
    }

    toast.textContent = message || "";
    toast.style.color = "#fff";
    toast.style.background = type === "error" ? "#ef4444" : "#14b8a6";
    toast.hidden = false;

    clearTimeout(toast._timer);
    toast._timer = setTimeout(function () {
      toast.hidden = true;
    }, 2500);
  }

  async function submitAjaxForm(form) {
    const submitter = document.activeElement;
    const originalText = submitter && submitter.tagName === "BUTTON"
      ? submitter.textContent
      : "";

    if (submitter && submitter.tagName === "BUTTON") {
      submitter.disabled = true;
      submitter.textContent = "Wait...";
    }

    try {
      const response = await fetch(form.action, {
        method: form.method || "POST",
        body: new FormData(form),
        headers: {
          "X-Requested-With": "XMLHttpRequest",
          "Accept": "application/json",
          "X-CSRFToken": getCookie("csrftoken")
        },
        credentials: "same-origin"
      });

      const contentType = response.headers.get("content-type") || "";

      if (!contentType.includes("application/json")) {
        throw new Error("Server did not return JSON. Check feed/views.py AJAX handling.");
      }

      const data = await response.json();

      if (!response.ok || data.success === false) {
        showToast(data.message || "Action failed.", "error");
        return;
      }

      if (data.message) {
        showToast(data.message, "success");
      }

      if (data.post_html && data.post_id) {
        const currentPost = document.getElementById("post-" + data.post_id);
        if (currentPost) {
          currentPost.outerHTML = data.post_html;
        }
      }

      if (data.comment_html && data.post_id) {
        const post = document.getElementById("post-" + data.post_id);
        const list = post ? post.querySelector("[data-comment-list]") : null;

        if (list) {
          list.insertAdjacentHTML("beforeend", data.comment_html);
        }
      }

      if (data.remove_post_id) {
        const post = document.getElementById("post-" + data.remove_post_id);
        if (post) post.remove();
      }

      if (data.feed_html) {
        const feedList = document.querySelector("[data-feed-list]");
        if (feedList) {
          feedList.innerHTML = data.feed_html;
        }
      }

      if (form.matches("[data-create-post]")) {
        form.reset();
      }

      if (form.matches("[data-comment-form]")) {
        form.reset();
      }

      if (form.matches("[data-edit-post]")) {
        const modal = document.getElementById("editModal");
        if (modal) {
          modal.classList.remove("open", "is-open");
          modal.setAttribute("aria-hidden", "true");
        }
      }
    } catch (error) {
      console.error("Heartly feed AJAX failed:", error);
      showToast(error.message || "Network error.", "error");
    } finally {
      if (submitter && submitter.tagName === "BUTTON") {
        submitter.disabled = false;
        submitter.textContent = originalText;
      }
    }
  }

  document.addEventListener("submit", function (event) {
    const form = event.target.closest("form[data-feed-ajax]");

    if (!form) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();

    console.log("Heartly AJAX submit:", form.action);
    submitAjaxForm(form);
  }, true);

  document.addEventListener("click", function (event) {
    const focusButton = event.target.closest("[data-focus-comment]");
    if (focusButton) {
      const input = document.getElementById(focusButton.dataset.focusComment);
      if (input) input.focus();
    }

    const editButton = event.target.closest("[data-edit-button]");
    if (editButton) {
      const modal = document.getElementById("editModal");
      const editForm = document.getElementById("editForm");
      const editContent = document.getElementById("editContent");

      if (modal && editForm && editContent) {
        editForm.action = editButton.dataset.editUrl;
        editContent.value = editButton.dataset.content || "";
        modal.classList.add("open");
        modal.setAttribute("aria-hidden", "false");
        editContent.focus();
      }
    }
  });

  console.log("Heartly feed AJAX loaded.");
})();