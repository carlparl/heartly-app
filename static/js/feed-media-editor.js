document.addEventListener("DOMContentLoaded", function () {
  "use strict";

  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => Array.from(document.querySelectorAll(selector));

  const composerModal = $("#composerModal");
  const editModal = $("#editModal");
  const cropModal = $("#xCropModal");

  const createPostForm = $("#createPostForm");
  const editPostForm = $("#editPostForm");

  const createImagesInput = $("#createImagesInput");
  const createVideoInput = $("#createVideoInput");
  const createMediaPreview = $("#createMediaPreview");
  const createAltTextStack = $("#createAltTextStack");

  const editImagesInput = $("#editImagesInput");
  const editVideoInput = $("#editVideoInput");
  const editMediaPreview = $("#editMediaPreview");
  const editAltTextStack = $("#editAltTextStack");
  const editPostContent = $("#editPostContent");

  const cropCanvas = $("#xCropCanvas");
  const cropCtx = cropCanvas ? cropCanvas.getContext("2d") : null;
  const cropZoomInput = $("#xCropZoom");

  const state = {
    create: {
      images: [],
      video: null,
      altTexts: [],
    },
    edit: {
      images: [],
      video: null,
      altTexts: [],
    },
  };

  let cropMode = "create";
  let cropIndex = 0;
  let cropImage = new Image();
  let cropFileName = "heartly-image.jpg";

  let cropRatio = 1;
  let cropZoom = 1;
  let cropRotation = 0;
  let cropOffsetX = 0;
  let cropOffsetY = 0;

  let dragging = false;
  let lastX = 0;
  let lastY = 0;

  function openModal(modal) {
    if (!modal) return;
    modal.classList.add("is-open");
    document.body.style.overflow = "hidden";
  }

  function closeModal(modal) {
    if (!modal) return;
    modal.classList.remove("is-open");

    if (
      !composerModal?.classList.contains("is-open") &&
      !editModal?.classList.contains("is-open") &&
      !cropModal?.classList.contains("is-open")
    ) {
      document.body.style.overflow = "";
    }
  }

  function bindClick(selector, callback) {
    const element = $(selector);
    if (!element) return;
    element.addEventListener("click", callback);
  }

  function setInputFiles(input, files) {
    if (!input) return;

    const transfer = new DataTransfer();

    files.forEach(function (file) {
      transfer.items.add(file);
    });

    input.files = transfer.files;
  }

  function clearFileInput(input) {
    if (input) input.value = "";
  }

  function isImage(file) {
    return file && file.type && file.type.startsWith("image/");
  }

  function isVideo(file) {
    return file && file.type && file.type.startsWith("video/");
  }

  function fileUrl(file) {
    return URL.createObjectURL(file);
  }

  function resetMedia(mode) {
    state[mode].images = [];
    state[mode].video = null;
    state[mode].altTexts = [];

    if (mode === "create") {
      clearFileInput(createImagesInput);
      clearFileInput(createVideoInput);
    } else {
      clearFileInput(editImagesInput);
      clearFileInput(editVideoInput);
    }

    renderMedia(mode);
  }

  function setImages(mode, files) {
    const selectedImages = Array.from(files || []).filter(isImage);

    if (selectedImages.length > 4) {
      alert("You can upload up to 4 photos.");
    }

    const images = selectedImages.slice(0, 4);

    state[mode].images = images;
    state[mode].video = null;
    state[mode].altTexts = images.map(function (_, index) {
      return state[mode].altTexts[index] || "";
    });

    if (mode === "create") {
      setInputFiles(createImagesInput, images);
      clearFileInput(createVideoInput);
    } else {
      setInputFiles(editImagesInput, images);
      clearFileInput(editVideoInput);
    }

    renderMedia(mode);
  }

  function setVideo(mode, file) {
    if (!file) return;

    if (!isVideo(file)) {
      alert("Choose a valid video.");
      return;
    }

    state[mode].images = [];
    state[mode].video = file;
    state[mode].altTexts = [];

    if (mode === "create") {
      clearFileInput(createImagesInput);
      setInputFiles(createVideoInput, [file]);
    } else {
      clearFileInput(editImagesInput);
      setInputFiles(editVideoInput, [file]);
    }

    renderMedia(mode);
  }

  function syncInputs(mode) {
    if (mode === "create") {
      setInputFiles(createImagesInput, state.create.images);

      if (state.create.video) {
        setInputFiles(createVideoInput, [state.create.video]);
      } else {
        clearFileInput(createVideoInput);
      }
    }

    if (mode === "edit") {
      setInputFiles(editImagesInput, state.edit.images);

      if (state.edit.video) {
        setInputFiles(editVideoInput, [state.edit.video]);
      } else {
        clearFileInput(editVideoInput);
      }
    }
  }

  function renderMedia(mode) {
    const preview = mode === "create" ? createMediaPreview : editMediaPreview;
    const altStack = mode === "create" ? createAltTextStack : editAltTextStack;
    const current = state[mode];

    if (!preview || !altStack) return;

    preview.innerHTML = "";
    altStack.innerHTML = "";

    preview.className = "x-selected-media";

    if (current.video) {
      preview.classList.add("has-media", "video-mode");

      const card = document.createElement("article");
      card.className = "x-selected-media-card video";

      const video = document.createElement("video");
      video.src = fileUrl(current.video);
      video.controls = true;
      video.playsInline = true;

      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "x-media-remove";
      removeBtn.textContent = "×";
      removeBtn.addEventListener("click", function () {
        resetMedia(mode);
      });

      card.appendChild(video);
      card.appendChild(removeBtn);
      preview.appendChild(card);

      return;
    }

    if (current.images.length > 0) {
      preview.classList.add("has-media", "count-" + current.images.length);

      current.images.forEach(function (file, index) {
        const card = document.createElement("article");
        card.className = "x-selected-media-card";

        const image = document.createElement("img");
        image.src = fileUrl(file);
        image.alt = "Selected image";

        const editBtn = document.createElement("button");
        editBtn.type = "button";
        editBtn.className = "x-media-edit";
        editBtn.textContent = "Edit";
        editBtn.addEventListener("click", function () {
          openCropEditor(mode, index);
        });

        const removeBtn = document.createElement("button");
        removeBtn.type = "button";
        removeBtn.className = "x-media-remove";
        removeBtn.textContent = "×";
        removeBtn.addEventListener("click", function () {
          current.images.splice(index, 1);
          current.altTexts.splice(index, 1);
          syncInputs(mode);
          renderMedia(mode);
        });

        card.appendChild(image);
        card.appendChild(editBtn);
        card.appendChild(removeBtn);
        preview.appendChild(card);

        const altLabel = document.createElement("label");
        altLabel.className = "x-alt-text-item";

        const span = document.createElement("span");
        span.textContent = "Alt text " + (index + 1);

        const input = document.createElement("input");
        input.type = "text";
        input.name = "image_alt_texts";
        input.placeholder = "Describe image...";
        input.maxLength = 420;
        input.value = current.altTexts[index] || "";

        input.addEventListener("input", function () {
          current.altTexts[index] = input.value;
        });

        altLabel.appendChild(span);
        altLabel.appendChild(input);
        altStack.appendChild(altLabel);
      });
    }
  }

  function resetCropState() {
    cropRatio = 1;
    cropZoom = 1;
    cropRotation = 0;
    cropOffsetX = 0;
    cropOffsetY = 0;

    if (cropZoomInput) cropZoomInput.value = "1";

    $$("[data-x-ratio]").forEach(function (button) {
      button.classList.remove("is-active");
    });

    const square = $('[data-x-ratio="1"]');
    if (square) square.classList.add("is-active");
  }

  function resizeCropCanvas() {
    if (!cropCanvas) return;

    const parent = cropCanvas.parentElement;
    const parentWidth = parent ? parent.clientWidth : 360;
    const width = Math.min(parentWidth, 420);
    const height = width / cropRatio;

    cropCanvas.width = width;
    cropCanvas.height = height;
  }

  function drawCropCanvas() {
    if (!cropCanvas || !cropCtx || !cropImage.complete) return;

    resizeCropCanvas();

    const canvasWidth = cropCanvas.width;
    const canvasHeight = cropCanvas.height;

    cropCtx.clearRect(0, 0, canvasWidth, canvasHeight);

    cropCtx.save();

    cropCtx.translate(
      canvasWidth / 2 + cropOffsetX,
      canvasHeight / 2 + cropOffsetY
    );

    cropCtx.rotate((cropRotation * Math.PI) / 180);

    const imageRatio = cropImage.width / cropImage.height;
    const canvasRatio = canvasWidth / canvasHeight;

    let drawWidth;
    let drawHeight;

    if (imageRatio > canvasRatio) {
      drawHeight = canvasHeight * cropZoom;
      drawWidth = drawHeight * imageRatio;
    } else {
      drawWidth = canvasWidth * cropZoom;
      drawHeight = drawWidth / imageRatio;
    }

    cropCtx.drawImage(
      cropImage,
      -drawWidth / 2,
      -drawHeight / 2,
      drawWidth,
      drawHeight
    );

    cropCtx.restore();
  }

  function openCropEditor(mode, index) {
    const file = state[mode].images[index];

    if (!file) return;

    cropMode = mode;
    cropIndex = index;
    cropFileName = file.name || "heartly-image.jpg";

    cropImage = new Image();

    cropImage.onload = function () {
      resetCropState();
      openModal(cropModal);
      drawCropCanvas();
    };

    cropImage.src = fileUrl(file);
  }

  function applyCrop() {
    if (!cropCanvas) return;

    cropCanvas.toBlob(
      function (blob) {
        if (!blob) return;

        const baseName = cropFileName.replace(/\.[^/.]+$/, "");

        const croppedFile = new File([blob], baseName + "-edited.jpg", {
          type: "image/jpeg",
          lastModified: Date.now(),
        });

        state[cropMode].images[cropIndex] = croppedFile;

        syncInputs(cropMode);
        renderMedia(cropMode);
        closeModal(cropModal);
      },
      "image/jpeg",
      0.92
    );
  }

  function compressImage(file) {
    return new Promise(function (resolve) {
      if (!isImage(file)) {
        resolve(file);
        return;
      }

      const img = new Image();
      img.src = fileUrl(file);

      img.onload = function () {
        let width = img.width;
        let height = img.height;
        const maxWidth = 1600;

        if (width > maxWidth) {
          height = Math.round((height * maxWidth) / width);
          width = maxWidth;
        }

        const canvas = document.createElement("canvas");
        const ctx = canvas.getContext("2d");

        canvas.width = width;
        canvas.height = height;

        ctx.drawImage(img, 0, 0, width, height);

        canvas.toBlob(
          function (blob) {
            if (!blob) {
              resolve(file);
              return;
            }

            const compressed = new File([blob], file.name, {
              type: "image/jpeg",
              lastModified: Date.now(),
            });

            resolve(compressed);
          },
          "image/jpeg",
          0.88
        );
      };

      img.onerror = function () {
        resolve(file);
      };
    });
  }

  async function prepareImages(mode) {
    if (!state[mode].images.length) return;

    const compressed = [];

    for (const image of state[mode].images) {
      compressed.push(await compressImage(image));
    }

    state[mode].images = compressed;
    syncInputs(mode);
  }

  bindClick("#openComposerBtn", function () {
    openModal(composerModal);
  });

  bindClick("#openTextComposer", function () {
    openModal(composerModal);
  });

  bindClick("#emptyComposerBtn", function () {
    openModal(composerModal);
  });

  bindClick("#openImageComposer", function () {
    openModal(composerModal);
    setTimeout(function () {
      if (createImagesInput) createImagesInput.click();
    }, 150);
  });

  bindClick("#openVideoComposer", function () {
    openModal(composerModal);
    setTimeout(function () {
      if (createVideoInput) createVideoInput.click();
    }, 150);
  });

  bindClick("#closeComposerBtn", function () {
    closeModal(composerModal);
  });

  bindClick("#closeEditBtn", function () {
    closeModal(editModal);
  });

  bindClick("#closeCropBtn", function () {
    closeModal(cropModal);
  });

  bindClick("#clearCreateMediaBtn", function () {
    resetMedia("create");
  });

  bindClick("#clearEditMediaBtn", function () {
    resetMedia("edit");
  });

  bindClick("#applyCropBtn", applyCrop);

  bindClick("#xRotateLeftBtn", function () {
    cropRotation -= 90;
    drawCropCanvas();
  });

  bindClick("#xRotateRightBtn", function () {
    cropRotation += 90;
    drawCropCanvas();
  });

  if (createImagesInput) {
    createImagesInput.addEventListener("change", function () {
      setImages("create", createImagesInput.files);
    });
  }

  if (createVideoInput) {
    createVideoInput.addEventListener("change", function () {
      setVideo("create", createVideoInput.files[0]);
    });
  }

  if (editImagesInput) {
    editImagesInput.addEventListener("change", function () {
      setImages("edit", editImagesInput.files);
    });
  }

  if (editVideoInput) {
    editVideoInput.addEventListener("change", function () {
      setVideo("edit", editVideoInput.files[0]);
    });
  }

  if (cropZoomInput) {
    cropZoomInput.addEventListener("input", function () {
      cropZoom = parseFloat(cropZoomInput.value);
      drawCropCanvas();
    });
  }

  $$("[data-x-ratio]").forEach(function (button) {
    button.addEventListener("click", function () {
      const value = button.getAttribute("data-x-ratio");
      cropRatio = parseFloat(value);

      $$("[data-x-ratio]").forEach(function (item) {
        item.classList.remove("is-active");
      });

      button.classList.add("is-active");
      drawCropCanvas();
    });
  });

  if (cropCanvas) {
    cropCanvas.addEventListener("pointerdown", function (event) {
      dragging = true;
      lastX = event.clientX;
      lastY = event.clientY;
      cropCanvas.setPointerCapture(event.pointerId);
    });

    cropCanvas.addEventListener("pointermove", function (event) {
      if (!dragging) return;

      cropOffsetX += event.clientX - lastX;
      cropOffsetY += event.clientY - lastY;

      lastX = event.clientX;
      lastY = event.clientY;

      drawCropCanvas();
    });

    cropCanvas.addEventListener("pointerup", function () {
      dragging = false;
    });

    cropCanvas.addEventListener("pointercancel", function () {
      dragging = false;
    });
  }

  [composerModal, editModal, cropModal].forEach(function (modal) {
    if (!modal) return;

    modal.addEventListener("click", function (event) {
      if (event.target === modal) {
        closeModal(modal);
      }
    });
  });

  $$(".x-post-menu-btn").forEach(function (button) {
    button.addEventListener("click", function (event) {
      event.stopPropagation();

      const wrapper = button.closest(".x-post-menu-wrap");

      $$(".x-post-menu-wrap.is-open").forEach(function (openWrapper) {
        if (openWrapper !== wrapper) {
          openWrapper.classList.remove("is-open");
        }
      });

      wrapper.classList.toggle("is-open");
    });
  });

  document.addEventListener("click", function () {
    $$(".x-post-menu-wrap.is-open").forEach(function (wrapper) {
      wrapper.classList.remove("is-open");
    });
  });

  $$(".editPostBtn").forEach(function (button) {
    button.addEventListener("click", function (event) {
      event.stopPropagation();

      const editUrl = button.getAttribute("data-edit-url");
      const content = button.getAttribute("data-edit-content") || "";

      resetMedia("edit");

      if (editPostForm) {
        editPostForm.setAttribute("action", editUrl);
      }

      if (editPostContent) {
        editPostContent.value = content;
      }

      openModal(editModal);
    });
  });

  $$(".copyFeedLinkBtn").forEach(function (button) {
    button.addEventListener("click", function () {
      if (!navigator.clipboard) return;

      navigator.clipboard.writeText(window.location.href);
      button.textContent = "Copied";

      setTimeout(function () {
        button.textContent = "↗ Share";
      }, 1200);
    });
  });

  if (createPostForm) {
    createPostForm.addEventListener("submit", function (event) {
      event.preventDefault();

      const submitBtn = $('[form="createPostForm"]');

      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = "Posting...";
      }

      prepareImages("create").then(function () {
        createPostForm.submit();
      });
    });
  }

  if (editPostForm) {
    editPostForm.addEventListener("submit", function (event) {
      event.preventDefault();

      const submitBtn = $('[form="editPostForm"]');

      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = "Saving...";
      }

      prepareImages("edit").then(function () {
        editPostForm.submit();
      });
    });
  }

  renderMedia("create");
  renderMedia("edit");
});