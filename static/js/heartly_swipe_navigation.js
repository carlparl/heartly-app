(function () {
    "use strict";

    const PHONE_MAX_WIDTH = 768;
    const EDGE_GUARD_PX = 26;
    const DIRECTION_LOCK_PX = 12;
    const MIN_DISTANCE_PX = 68;
    const MIN_FAST_DISTANCE_PX = 44;
    const MIN_VELOCITY_PX_PER_MS = 0.38;
    const MAX_DRAG_OFFSET_PX = 34;
    const NAVIGATION_DELAY_MS = 145;
    const TOAST_DURATION_MS = 2600;

    function ready(callback) {
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", callback, {
                once: true
            });
        } else {
            callback();
        }
    }

    ready(function () {
        const body = document.body;
        const main = document.querySelector(".heartly-app-main");
        const configElement = document.getElementById(
            "heartlySwipeNavigationConfig"
        );

        const currentSection = (
            body.dataset.heartlySwipeSection || ""
        ).trim();

        if (!body || !main || !configElement || !currentSection) {
            return;
        }

        const isPhoneWidth = window.matchMedia(
            "(max-width: " + PHONE_MAX_WIDTH + "px)"
        );

        const hasTouch =
            navigator.maxTouchPoints > 0 ||
            "ontouchstart" in window;

        if (!isPhoneWidth.matches || !hasTouch) {
            return;
        }

        let config;

        try {
            config = JSON.parse(configElement.textContent || "{}");
        } catch (error) {
            console.error(
                "Heartly swipe navigation config is invalid.",
                error
            );
            return;
        }

        const routes = Array.isArray(config.routes)
            ? config.routes.filter(function (route) {
                return route && route.key && route.url;
            })
            : [];

        const currentIndex = routes.findIndex(function (route) {
            return route.key === currentSection;
        });

        if (currentIndex < 0) {
            return;
        }

        let tracking = false;
        let horizontalGesture = false;

        let startX = 0;
        let startY = 0;
        let latestX = 0;
        let latestY = 0;
        let startedAt = 0;

        let thresholdBuzzed = false;
        let toastTimer = null;
        let navigating = false;

        const indicator = document.createElement("div");
        indicator.className = "heartly-swipe-indicator";
        indicator.setAttribute("aria-hidden", "true");

        const indicatorArrow = document.createElement("span");
        indicatorArrow.className =
            "heartly-swipe-indicator-arrow";

        const indicatorLabel = document.createElement("span");

        indicator.appendChild(indicatorArrow);
        indicator.appendChild(indicatorLabel);

        document.body.appendChild(indicator);

        const toast = document.createElement("div");
        toast.className = "heartly-swipe-toast";
        toast.setAttribute("role", "status");
        toast.setAttribute("aria-live", "polite");

        document.body.appendChild(toast);

        body.classList.add("heartly-swipe-ready");

        restoreSwipeScrollPosition();

        function clamp(value, min, max) {
            return Math.min(max, Math.max(min, value));
        }

        function showToast(message) {
            toast.textContent = message;
            toast.classList.add("is-visible");

            window.clearTimeout(toastTimer);

            toastTimer = window.setTimeout(function () {
                toast.classList.remove("is-visible");
            }, TOAST_DURATION_MS);
        }

        function isElementVisible(element) {
            if (!element || element.hidden) {
                return false;
            }

            const style = window.getComputedStyle(element);

            return (
                style.display !== "none" &&
                style.visibility !== "hidden" &&
                element.getClientRects().length > 0
            );
        }

        function hasBlockingOverlay() {
            const selectors = [
                ".chat-modal:not([hidden])",
                ".attachment-drawer:not([hidden])",
                ".selected-toolbar:not([hidden])",
                ".selected-media-bar:not([hidden])",
                ".global-call-pop:not([hidden])",
                ".chat-call-toast:not([hidden])",
                "[role='dialog']:not([hidden])"
            ];

            return selectors.some(function (selector) {
                return Array.from(
                    document.querySelectorAll(selector)
                ).some(isElementVisible);
            });
        }

        function isInteractiveTarget(target) {
            if (!(target instanceof Element)) {
                return true;
            }

            return Boolean(
                target.closest(
                    [
                        "input",
                        "textarea",
                        "select",
                        "option",
                        "button",
                        "a",
                        "video",
                        "audio",
                        "iframe",
                        "canvas",
                        "[contenteditable='true']",
                        "[data-swipe-nav-ignore]",
                        ".heartly-bottomnav",
                        ".heartly-topbar",
                        ".chat-composer",
                        ".heartly-ai__composer",
                        ".coach-composer",
                        ".composer-preview",
                        ".attachment-drawer",
                        ".wallpaper-grid",
                        ".post-actions",
                        ".post-menu",
                        ".comment-form",
                        ".reply-form"
                    ].join(",")
                )
            );
        }

        function hasHorizontalScrollAncestor(target) {
            let element =
                target instanceof Element ? target : null;

            while (
                element &&
                element !== main &&
                element !== document.body
            ) {
                const style =
                    window.getComputedStyle(element);

                const overflowX = style.overflowX;

                const canScrollX =
                    element.scrollWidth >
                        element.clientWidth + 6 &&
                    (
                        overflowX === "auto" ||
                        overflowX === "scroll"
                    );

                if (canScrollX) {
                    return true;
                }

                element = element.parentElement;
            }

            return false;
        }

        function hasUnsavedDraft() {
            const textareas = Array.from(
                main.querySelectorAll(
                    "textarea:not([disabled]):not([readonly])"
                )
            );

            const hasTextDraft = textareas.some(
                function (textarea) {
                    return (
                        isElementVisible(textarea) &&
                        textarea.value.trim().length > 0
                    );
                }
            );

            if (hasTextDraft) {
                return true;
            }

            const fileInputs = Array.from(
                main.querySelectorAll(
                    "input[type='file']:not([disabled])"
                )
            );

            return fileInputs.some(function (input) {
                return (
                    input.files &&
                    input.files.length > 0
                );
            });
        }

        function routeForDelta(deltaX) {
            const direction =
                deltaX < 0 ? "next" : "previous";

            const targetIndex =
                direction === "next"
                    ? currentIndex + 1
                    : currentIndex - 1;

            return {
                direction: direction,
                route: routes[targetIndex] || null
            };
        }

        function updateIndicator(deltaX) {
            const target = routeForDelta(deltaX);
            const absoluteDelta = Math.abs(deltaX);
            const visibilityThreshold = 18;

            if (absoluteDelta < visibilityThreshold) {
                hideIndicator();
                return;
            }

            indicator.dataset.direction =
                target.direction;

            indicatorArrow.textContent =
                target.direction === "next"
                    ? "→"
                    : "←";

            indicatorLabel.textContent =
                target.route
                    ? target.route.label
                    : "End";

            indicator.classList.add("is-visible");
        }

        function hideIndicator() {
            indicator.classList.remove("is-visible");
        }

        function applyDrag(deltaX) {
            const easedOffset = clamp(
                deltaX * 0.16,
                -MAX_DRAG_OFFSET_PX,
                MAX_DRAG_OFFSET_PX
            );

            body.style.setProperty(
                "--heartly-swipe-offset",
                easedOffset + "px"
            );
        }

        function resetDrag() {
            tracking = false;
            horizontalGesture = false;
            thresholdBuzzed = false;

            body.classList.remove(
                "heartly-swipe-dragging"
            );

            body.style.setProperty(
                "--heartly-swipe-offset",
                "0px"
            );

            body.style.setProperty(
                "--heartly-swipe-opacity",
                "1"
            );

            hideIndicator();
        }

        function saveScrollPosition() {
            try {
                sessionStorage.setItem(
                    "heartly:swipe:scroll:" +
                        currentSection,
                    String(window.scrollY || 0)
                );
            } catch (error) {
                // Storage may be unavailable in private mode.
            }
        }

        function restoreSwipeScrollPosition() {
            try {
                const targetSection =
                    sessionStorage.getItem(
                        "heartly:swipe:target"
                    );

                if (targetSection !== currentSection) {
                    return;
                }

                const savedPosition = Number(
                    sessionStorage.getItem(
                        "heartly:swipe:scroll:" +
                            currentSection
                    )
                );

                sessionStorage.removeItem(
                    "heartly:swipe:target"
                );

                if (
                    Number.isFinite(savedPosition) &&
                    savedPosition > 0
                ) {
                    window.requestAnimationFrame(
                        function () {
                            window.scrollTo(
                                0,
                                savedPosition
                            );
                        }
                    );
                }
            } catch (error) {
                // Ignore storage errors.
            }
        }

        function navigateTo(target, direction) {
            if (!target || navigating) {
                return;
            }

            if (hasUnsavedDraft()) {
                showToast(
                    "Finish or clear your draft before swiping away."
                );

                resetDrag();
                return;
            }

            navigating = true;

            saveScrollPosition();

            try {
                sessionStorage.setItem(
                    "heartly:swipe:target",
                    target.key
                );
            } catch (error) {
                // Ignore storage errors.
            }

            body.classList.remove(
                "heartly-swipe-dragging"
            );

            body.classList.add(
                "heartly-swipe-navigating"
            );

            body.style.setProperty(
                "--heartly-swipe-offset",
                direction === "next"
                    ? "-52px"
                    : "52px"
            );

            body.style.setProperty(
                "--heartly-swipe-opacity",
                "0.82"
            );

            if (navigator.vibrate) {
                navigator.vibrate(8);
            }

            window.setTimeout(function () {
                window.location.assign(target.url);
            }, NAVIGATION_DELAY_MS);
        }

        function onTouchStart(event) {
            if (
                navigating ||
                event.touches.length !== 1 ||
                hasBlockingOverlay()
            ) {
                return;
            }

            const touch = event.touches[0];
            const viewportWidth = window.innerWidth;

            if (
                touch.clientX <= EDGE_GUARD_PX ||
                touch.clientX >=
                    viewportWidth - EDGE_GUARD_PX ||
                isInteractiveTarget(event.target) ||
                hasHorizontalScrollAncestor(event.target)
            ) {
                return;
            }

            tracking = true;
            horizontalGesture = false;
            thresholdBuzzed = false;

            startX = touch.clientX;
            startY = touch.clientY;

            latestX = startX;
            latestY = startY;

            startedAt = performance.now();
        }

        function onTouchMove(event) {
            if (
                !tracking ||
                event.touches.length !== 1
            ) {
                return;
            }

            const touch = event.touches[0];

            latestX = touch.clientX;
            latestY = touch.clientY;

            const deltaX = latestX - startX;
            const deltaY = latestY - startY;

            const absoluteX = Math.abs(deltaX);
            const absoluteY = Math.abs(deltaY);

            if (!horizontalGesture) {
                if (
                    absoluteX <
                        DIRECTION_LOCK_PX &&
                    absoluteY <
                        DIRECTION_LOCK_PX
                ) {
                    return;
                }

                if (absoluteY >= absoluteX * 0.92) {
                    resetDrag();
                    return;
                }

                horizontalGesture = true;

                body.classList.add(
                    "heartly-swipe-dragging"
                );
            }

            event.preventDefault();

            applyDrag(deltaX);
            updateIndicator(deltaX);

            const threshold = Math.max(
                MIN_DISTANCE_PX,
                window.innerWidth * 0.16
            );

            if (
                absoluteX >= threshold &&
                !thresholdBuzzed
            ) {
                thresholdBuzzed = true;

                if (navigator.vibrate) {
                    navigator.vibrate(5);
                }
            } else if (
                absoluteX < threshold - 16
            ) {
                thresholdBuzzed = false;
            }
        }

        function onTouchEnd() {
            if (
                !tracking ||
                !horizontalGesture
            ) {
                resetDrag();
                return;
            }

            const deltaX = latestX - startX;
            const deltaY = latestY - startY;

            const absoluteX = Math.abs(deltaX);
            const absoluteY = Math.abs(deltaY);

            const elapsed = Math.max(
                performance.now() - startedAt,
                1
            );

            const velocity = absoluteX / elapsed;

            const threshold = Math.max(
                MIN_DISTANCE_PX,
                window.innerWidth * 0.16
            );

            const validDistance =
                absoluteX >= threshold;

            const validFastSwipe =
                absoluteX >=
                    MIN_FAST_DISTANCE_PX &&
                velocity >=
                    MIN_VELOCITY_PX_PER_MS;

            const isHorizontal =
                absoluteX > absoluteY * 1.18;

            const target =
                routeForDelta(deltaX);

            if (
                isHorizontal &&
                (
                    validDistance ||
                    validFastSwipe
                )
            ) {
                if (target.route) {
                    navigateTo(
                        target.route,
                        target.direction
                    );

                    return;
                }

                showToast(
                    target.direction === "next"
                        ? "You are already on the last page."
                        : "You are already on the first page."
                );
            }

            resetDrag();
        }

        function onTouchCancel() {
            resetDrag();
        }

        main.addEventListener(
            "touchstart",
            onTouchStart,
            {
                passive: true
            }
        );

        main.addEventListener(
            "touchmove",
            onTouchMove,
            {
                passive: false
            }
        );

        main.addEventListener(
            "touchend",
            onTouchEnd,
            {
                passive: true
            }
        );

        main.addEventListener(
            "touchcancel",
            onTouchCancel,
            {
                passive: true
            }
        );

        window.addEventListener(
            "resize",
            function () {
                if (!isPhoneWidth.matches) {
                    resetDrag();
                }
            }
        );
    });
})();