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
    }, 2300);
  }

  function closeMenus() {
    document.querySelectorAll(".post-menu[open]").forEach(function (menu) {
      menu.removeAttribute("open");
    });
  }

  function replacePost(data) {
    if (!data.post_html || !data.post_id) {
      return;
    }

    const currentPost = document.getElementById("post-" + data.post_id);
    const feedList = document.querySelector("[data-feed-list]");

    if (currentPost) {
      currentPost.outerHTML = data.post_html;
      return;
    }

    if (feedList) {
      const empty = feedList.querySelector("[data-empty-feed]");
      if (empty) {
        empty.remove();
      }

      feedList.insertAdjacentHTML("afterbegin", data.post_html);
    }
  }

  function closeEditPanel(form) {
    const panel = form.closest(".edit-post-panel");

    if (panel) {
      panel.hidden = true;
    }
  }

  async function submitAjaxForm(form, submitter) {
    if (form.dataset.confirm && !confirm(form.dataset.confirm)) {
      return;
    }

    const button =
      submitter && submitter.tagName === "BUTTON"
        ? submitter
        : form.querySelector("button[type='submit']");

    const originalText = button ? button.textContent : "";

    if (button) {
      button.disabled = true;
      button.textContent = "Wait...";
    }

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
        showToast(data.message || "Action failed.", "error");
        return;
      }

      if (data.remove_post_id) {
        const post = document.getElementById("post-" + data.remove_post_id);
        if (post) post.remove();
      }

      if (data.post_html) {
        replacePost(data);
      }

      if (form.matches("[data-create-post]")) {
        form.reset();

        const preview = document.getElementById("composerPreview");
        const clearBtn = document.getElementById("clearComposerMedia");

        if (preview) {
          preview.hidden = true;
          preview.innerHTML = "";
        }

        if (clearBtn) {
          clearBtn.hidden = true;
        }
      }

      if (form.matches("[data-edit-post]")) {
        closeEditPanel(form);
      }

      if (form.matches("[data-comment-form], [data-reply-form]")) {
        form.reset();
      }

      closeMenus();

      if (data.message) {
        showToast(data.message, "success");
      }
    } catch (error) {
      console.error("Heartly feed AJAX failed:", error);
      showToast(error.message || "Network error.", "error");
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = originalText;
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

    submitAjaxForm(form, event.submitter);
  }, true);

  document.addEventListener("click", function (event) {
    const focusButton = event.target.closest("[data-comment-focus]");

    if (focusButton) {
      const input = document.getElementById(focusButton.getAttribute("data-comment-focus"));
      if (input) input.focus();
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

      if (panel) {
        panel.hidden = false;
      }
    }

    const closeButton = event.target.closest("[data-edit-close]");

    if (closeButton) {
      const panel = document.getElementById(closeButton.getAttribute("data-edit-close"));

      if (panel) {
        panel.hidden = true;
      }
    }

    const panel = event.target.closest(".edit-post-panel");

    if (panel && event.target === panel) {
      panel.hidden = true;
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

      if (clearBtn) {
        clearBtn.hidden = true;
      }
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
        preview.innerHTML = `
          <video controls playsinline preload="metadata">
            <source src="${url}">
            Your browser does not support video playback.
          </video>
        `;
      }

      if (clearBtn) {
        clearBtn.hidden = false;
      }
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

  console.log("Heartly feed AJAX loaded.");
})();