(function () {
  "use strict";

  const viewer = document.querySelector(
    "[data-story-viewer]"
  );

  if (!viewer) return;

  const mediaStage = viewer.querySelector(
    "[data-story-media-stage]"
  );
  const image = viewer.querySelector(
    "[data-story-image]"
  );
  const video = viewer.querySelector(
    "[data-story-video]"
  );
  const progressFill = viewer.querySelector(
    "[data-story-progress-fill]"
  );
  const status = viewer.querySelector(
    "[data-story-status]"
  );

  const nextUrl =
    viewer.dataset.storyNextUrl || "";
  const previousUrl =
    viewer.dataset.storyPreviousUrl || "";
  const closeUrl =
    viewer.dataset.storyCloseUrl || "/";
  const photoPlayMs = Math.max(
    1000,
    Number(viewer.dataset.photoPlayMs) || 5000
  );

  let isAdvancing = false;
  let isDestroyed = false;
  let timerId = 0;
  let animationId = 0;
  let timerStartedAt = 0;
  let timerRemainingMs = photoPlayMs;
  let timerDurationMs = photoPlayMs;
  let timerRunning = false;
  let hiddenPausedVideo = false;
  let holdPausedVideo = false;
  let holdPausedTimer = false;
  let lastVideoProgress = 0;

  function clamp(value, minimum, maximum) {
    return Math.min(
      maximum,
      Math.max(minimum, value)
    );
  }

  function setProgress(value) {
    if (!progressFill) return;

    const percent = clamp(
      Number(value) || 0,
      0,
      1
    ) * 100;

    progressFill.style.width = percent + "%";
    progressFill.parentElement?.setAttribute(
      "aria-valuenow",
      String(Math.round(percent))
    );
  }

  function setStatus(message, visible) {
    if (!status) return;

    status.textContent = message || "";
    status.hidden = !visible || !message;
  }

  function cancelTimer() {
    if (timerId) {
      window.clearTimeout(timerId);
      timerId = 0;
    }

    timerRunning = false;
  }

  function cancelAnimation() {
    if (animationId) {
      window.cancelAnimationFrame(animationId);
      animationId = 0;
    }
  }

  function cleanup() {
    if (isDestroyed) return;

    isDestroyed = true;
    cancelTimer();
    cancelAnimation();

    document.removeEventListener(
      "visibilitychange",
      handleVisibilityChange
    );
  }

  function navigate(url, replace) {
    if (
      isAdvancing ||
      isDestroyed ||
      !url
    ) {
      return;
    }

    isAdvancing = true;
    cancelTimer();
    cancelAnimation();

    if (replace) {
      window.location.replace(url);
    } else {
      window.location.assign(url);
    }
  }

  function advanceStory() {
    navigate(nextUrl || closeUrl, true);
  }

  function previousStory() {
    navigate(previousUrl || closeUrl, false);
  }

  function updateTimerProgress() {
    if (
      !timerRunning ||
      isDestroyed ||
      document.hidden
    ) {
      return;
    }

    const elapsed = performance.now() -
      timerStartedAt;
    const remaining = Math.max(
      0,
      timerRemainingMs - elapsed
    );
    const completed =
      1 - (remaining / timerDurationMs);

    setProgress(completed);

    if (remaining > 0) {
      animationId = window.requestAnimationFrame(
        updateTimerProgress
      );
    }
  }

  function startTimer(
    durationMs,
    remainingMs
  ) {
    cancelTimer();
    cancelAnimation();

    timerDurationMs = Math.max(
      1,
      Number(durationMs) || photoPlayMs
    );
    timerRemainingMs = clamp(
      Number(remainingMs ?? timerDurationMs),
      0,
      timerDurationMs
    );
    timerStartedAt = performance.now();
    timerRunning = true;

    setProgress(
      1 - (
        timerRemainingMs /
        timerDurationMs
      )
    );

    timerId = window.setTimeout(
      advanceStory,
      timerRemainingMs
    );

    animationId = window.requestAnimationFrame(
      updateTimerProgress
    );
  }

  function pauseTimer() {
    if (!timerRunning) return;

    const elapsed = performance.now() -
      timerStartedAt;

    timerRemainingMs = Math.max(
      0,
      timerRemainingMs - elapsed
    );

    cancelTimer();
    cancelAnimation();

    setProgress(
      1 - (
        timerRemainingMs /
        timerDurationMs
      )
    );
  }

  function resumeTimer() {
    if (
      timerRunning ||
      timerRemainingMs <= 0 ||
      document.hidden
    ) {
      return;
    }

    startTimer(
      timerDurationMs,
      timerRemainingMs
    );
  }

  function updateVideoProgress() {
    if (
      !video ||
      isDestroyed ||
      video.paused ||
      video.ended
    ) {
      return;
    }

    const duration = Number(video.duration);
    const current = Number(video.currentTime);

    if (
      Number.isFinite(duration) &&
      duration > 0
    ) {
      lastVideoProgress = clamp(
        current / duration,
        0,
        1
      );
      setProgress(lastVideoProgress);
    }

    animationId = window.requestAnimationFrame(
      updateVideoProgress
    );
  }

  function beginVideoProgress() {
    cancelAnimation();
    animationId = window.requestAnimationFrame(
      updateVideoProgress
    );
  }

  function pauseVideoForVisibility() {
    if (
      !video ||
      video.paused ||
      video.ended
    ) {
      hiddenPausedVideo = false;
      return;
    }

    hiddenPausedVideo = true;
    video.pause();
  }

  function resumeVideoFromVisibility() {
    if (
      !video ||
      !hiddenPausedVideo ||
      holdPausedVideo
    ) {
      return;
    }

    hiddenPausedVideo = false;
    const attempt = video.play();

    if (
      attempt &&
      typeof attempt.catch === "function"
    ) {
      attempt.catch(function () {
        setStatus(
          "Tap play to continue this Story.",
          true
        );
      });
    }
  }

  function handleVisibilityChange() {
    if (document.hidden) {
      if (video) {
        pauseVideoForVisibility();
      } else {
        pauseTimer();
      }
      return;
    }

    if (video) {
      resumeVideoFromVisibility();
    } else if (!holdPausedTimer) {
      resumeTimer();
    }
  }

  function startPhotoPlayback() {
    setStatus("", false);
    timerRemainingMs = photoPlayMs;
    timerDurationMs = photoPlayMs;
    startTimer(photoPlayMs, photoPlayMs);
  }

  function handleImageError() {
    setStatus(
      "This image could not be loaded. " +
      "Moving to the next Story.",
      true
    );
    timerRemainingMs = photoPlayMs;
    timerDurationMs = photoPlayMs;
    startTimer(photoPlayMs, photoPlayMs);
  }

  function startVideoPlayback() {
    setProgress(lastVideoProgress);

    video.addEventListener(
      "ended",
      advanceStory,
      { once: true }
    );

    video.addEventListener(
      "play",
      function () {
        setStatus("", false);
        beginVideoProgress();
      }
    );

    video.addEventListener(
      "pause",
      cancelAnimation
    );

    video.addEventListener(
      "timeupdate",
      function () {
        const duration = Number(video.duration);

        if (
          Number.isFinite(duration) &&
          duration > 0
        ) {
          lastVideoProgress = clamp(
            Number(video.currentTime) /
              duration,
            0,
            1
          );
          setProgress(lastVideoProgress);
        }
      }
    );

    video.addEventListener(
      "error",
      function () {
        cancelAnimation();
        setStatus(
          "This video could not be played. " +
          "Moving to the next Story.",
          true
        );
        timerRemainingMs = photoPlayMs;
        timerDurationMs = photoPlayMs;
        startTimer(photoPlayMs, photoPlayMs);
      },
      { once: true }
    );

    const attempt = video.play();

    if (
      attempt &&
      typeof attempt.catch === "function"
    ) {
      attempt.catch(function () {
        setStatus(
          "Tap play to continue this Story.",
          true
        );
      });
    }
  }

  function holdPlayback() {
    if (document.hidden || isDestroyed) return;

    if (video) {
      holdPausedVideo = (
        !video.paused &&
        !video.ended
      );

      if (holdPausedVideo) {
        video.pause();
      }
      return;
    }

    holdPausedTimer = timerRunning;

    if (holdPausedTimer) {
      pauseTimer();
    }
  }

  function releasePlayback() {
    if (document.hidden || isDestroyed) return;

    if (video) {
      if (holdPausedVideo) {
        holdPausedVideo = false;
        const attempt = video.play();

        if (
          attempt &&
          typeof attempt.catch === "function"
        ) {
          attempt.catch(function () {
            setStatus(
              "Tap play to continue this Story.",
              true
            );
          });
        }
      }
      return;
    }

    if (holdPausedTimer) {
      holdPausedTimer = false;
      resumeTimer();
    }
  }

  function isInteractiveTarget(target) {
    return Boolean(
      target &&
      target.closest(
        "a, button, input, summary, " +
        "details, video[controls]"
      )
    );
  }

  function preloadNextStory() {
    if (!nextUrl) return;

    const link = document.createElement("link");
    link.rel = "prefetch";
    link.href = nextUrl;
    document.head.appendChild(link);
  }

  document.addEventListener(
    "visibilitychange",
    handleVisibilityChange
  );

  window.addEventListener(
    "pagehide",
    cleanup,
    { once: true }
  );

  window.addEventListener(
    "beforeunload",
    cleanup,
    { once: true }
  );

  document.addEventListener(
    "keydown",
    function (event) {
      if (isDestroyed) return;

      if (event.key === "ArrowRight") {
        event.preventDefault();
        advanceStory();
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        previousStory();
      } else if (event.key === "Escape") {
        event.preventDefault();
        navigate(closeUrl, false);
      } else if (
        event.key === " " ||
        event.code === "Space"
      ) {
        event.preventDefault();

        if (video) {
          if (video.paused) {
            video.play().catch(function () {});
          } else {
            video.pause();
          }
        } else if (timerRunning) {
          pauseTimer();
        } else {
          resumeTimer();
        }
      }
    }
  );

  if (mediaStage) {
    mediaStage.addEventListener(
      "pointerdown",
      function (event) {
        if (
          isInteractiveTarget(event.target)
        ) {
          return;
        }

        holdPlayback();
      }
    );

    mediaStage.addEventListener(
      "pointerup",
      releasePlayback
    );

    mediaStage.addEventListener(
      "pointercancel",
      releasePlayback
    );

    mediaStage.addEventListener(
      "pointerleave",
      releasePlayback
    );
  }

  preloadNextStory();

  if (video) {
    startVideoPlayback();
  } else if (image) {
    image.addEventListener(
      "load",
      startPhotoPlayback,
      { once: true }
    );

    image.addEventListener(
      "error",
      handleImageError,
      { once: true }
    );

    if (
      image.complete &&
      image.naturalWidth > 0
    ) {
      startPhotoPlayback();
    } else if (
      image.complete &&
      image.naturalWidth === 0
    ) {
      handleImageError();
    }
  } else {
    setStatus(
      "Story media is unavailable. " +
      "Moving to the next Story.",
      true
    );
    startTimer(photoPlayMs, photoPlayMs);
  }
})();
