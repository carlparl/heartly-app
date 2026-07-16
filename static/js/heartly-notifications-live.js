(() => {
    "use strict";

    if (!document.body.classList.contains("heartly-authenticated")) {
        return;
    }

    const cfg = window.HEARTLY_NOTIFICATIONS || {};
    const snapshotUrl = cfg.snapshotUrl || "/notifications/snapshot/";
    const unreadUrl = cfg.unreadUrl || "/notifications/unread-count/";
    const markAllUrl = cfg.markAllUrl || "/notifications/mark-read/";
    const clearAllUrl = cfg.clearAllUrl || "/notifications/clear-all/";

    let socket = null;
    let reconnectTimer = null;
    let reconnectAttempt = 0;
    let pollTimer = null;
    let lastSnapshotSignature = "";

    const csrfToken = (() => {
        const input = document.querySelector(
            'input[name="csrfmiddlewaretoken"]'
        );
        if (input?.value) return input.value;

        const match = document.cookie.match(
            /(?:^|;\s*)csrftoken=([^;]+)/
        );
        return match ? decodeURIComponent(match[1]) : "";
    })();

    function websocketUrl() {
        const protocol = location.protocol === "https:" ? "wss:" : "ws:";
        return `${protocol}//${location.host}/ws/notifications/`;
    }

    function setUnreadCount(count) {
        const value = Math.max(0, Number(count) || 0);

        document
            .querySelectorAll(
                "[data-heartly-notification-count], " +
                ".heartly-notification-badge, " +
                "#heartlyNotificationBadge"
            )
            .forEach((element) => {
                element.textContent = value > 99 ? "99+" : String(value);
                element.hidden = value === 0;
                element.classList.toggle("is-empty", value === 0);
                element.setAttribute(
                    "aria-label",
                    `${value} unread notification${value === 1 ? "" : "s"}`
                );
            });

        document
            .querySelectorAll("[data-notification-summary-text]")
            .forEach((element) => {
                element.textContent = value
                    ? `You have ${value} unread notification${value === 1 ? "" : "s"}.`
                    : "You are all caught up.";
            });

        document
            .querySelectorAll("[data-notification-unread-pill]")
            .forEach((element) => {
                element.textContent = value ? `${value} unread` : "No unread";
            });

        document.title = value
            ? `(${value}) Notifications - Heartly`
            : "Notifications - Heartly";

        window.dispatchEvent(
            new CustomEvent("heartly:notification-count", {
                detail: { count: value },
            })
        );
    }

    function escapeHtml(value) {
        const div = document.createElement("div");
        div.textContent = value ?? "";
        return div.innerHTML;
    }

    function notificationRow(item) {
        const actor = item.actor_name
            ? `<span>From ${escapeHtml(item.actor_name)}</span>`
            : "";

        return `
            <article class="notification-row ${item.is_read ? "" : "unread"}"
                     data-notification-id="${item.id}">
                <a href="${escapeHtml(item.open_url)}"
                   class="notification-main-link">
                    <div class="notification-left">
                        <div class="notification-icon">${escapeHtml(item.icon)}</div>
                        <div class="notification-copy">
                            <p class="notification-label">${escapeHtml(item.title || "Heartly notification")}</p>
                            <p class="notification-desc">${escapeHtml(item.message || "Open this notification for more details.")}</p>
                            <div class="notification-meta-line">
                                ${actor}
                                <span>${escapeHtml(item.created_label || "Now")}</span>
                            </div>
                        </div>
                    </div>
                    <span class="notification-chevron">›</span>
                </a>
                <form method="post"
                      action="${escapeHtml(item.clear_url)}"
                      class="notification-clear-form"
                      data-live-clear>
                    <input type="hidden" name="csrfmiddlewaretoken"
                           value="${escapeHtml(csrfToken)}">
                    <button type="submit"
                            title="Clear notification"
                            aria-label="Clear notification">×</button>
                </form>
            </article>
        `;
    }

    function renderSnapshot(payload) {
        setUnreadCount(payload.unread_count);

        const list = document.querySelector("[data-notification-list]");
        if (!list || !Array.isArray(payload.notifications)) return;

        const signature = payload.notifications
            .map((item) => `${item.id}:${item.is_read}:${item.is_resolved}`)
            .join("|");

        if (signature === lastSnapshotSignature) return;
        lastSnapshotSignature = signature;

        if (!payload.notifications.length) {
            list.innerHTML = `
                <div class="notifications-empty" data-live-empty>
                    <div class="notifications-empty-icon">✅</div>
                    <h3 class="notifications-empty-title">No notifications</h3>
                    <p class="notifications-empty-text">
                        Likes, comments, matches, messages, calls, and safety alerts will appear here.
                    </p>
                </div>
            `;
            return;
        }

        list.innerHTML = payload.notifications
            .map(notificationRow)
            .join("");
    }

    async function fetchSnapshot() {
        try {
            const response = await fetch(snapshotUrl, {
                headers: {
                    Accept: "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                },
                credentials: "same-origin",
                cache: "no-store",
            });
            if (!response.ok) return;
            renderSnapshot(await response.json());
        } catch (_) {
            // WebSocket reconnection and the next poll will retry.
        }
    }

    function scheduleReconnect() {
        clearTimeout(reconnectTimer);
        const delay = Math.min(30000, 1000 * (2 ** reconnectAttempt));
        reconnectAttempt += 1;
        reconnectTimer = setTimeout(connect, delay);
    }

    function connect() {
        if (socket?.readyState === WebSocket.OPEN) return;

        try {
            socket = new WebSocket(websocketUrl());
        } catch (_) {
            scheduleReconnect();
            return;
        }

        socket.addEventListener("open", () => {
            reconnectAttempt = 0;
            socket.send(JSON.stringify({ type: "notifications.refresh" }));
        });

        socket.addEventListener("message", (event) => {
            let payload;
            try {
                payload = JSON.parse(event.data);
            } catch (_) {
                return;
            }

            if (payload.type === "notifications.snapshot") {
                renderSnapshot(payload);
            } else if (
                payload.type === "notification.created" ||
                payload.type === "notification.updated" ||
                payload.type === "notification.removed"
            ) {
                fetchSnapshot();
            }
        });

        socket.addEventListener("close", scheduleReconnect);
        socket.addEventListener("error", () => socket.close());
    }

    function startPollingFallback() {
        clearInterval(pollTimer);
        pollTimer = setInterval(() => {
            if (
                document.visibilityState === "visible" &&
                socket?.readyState !== WebSocket.OPEN
            ) {
                fetchSnapshot();
            }
        }, 15000);
    }

    async function ajaxPost(url) {
        const response = await fetch(url, {
            method: "POST",
            headers: {
                "X-CSRFToken": csrfToken,
                "X-Requested-With": "XMLHttpRequest",
                Accept: "application/json",
            },
            credentials: "same-origin",
        });

        if (!response.ok) {
            throw new Error(`Request failed: ${response.status}`);
        }
        return response.json();
    }

    document.addEventListener("submit", async (event) => {
        const form = event.target;

        if (form.matches("[data-live-clear]")) {
            event.preventDefault();
            const row = form.closest("[data-notification-id]");
            row?.classList.add("is-removing");

            try {
                await ajaxPost(form.action);
                row?.remove();
                await fetchSnapshot();
            } catch (_) {
                row?.classList.remove("is-removing");
            }
        }

        if (form.matches("[data-live-mark-all]")) {
            event.preventDefault();
            try {
                await ajaxPost(markAllUrl);
                await fetchSnapshot();
            } catch (_) {}
        }

        if (form.matches("[data-live-clear-all]")) {
            event.preventDefault();
            if (!confirm("Clear all notifications?")) return;
            try {
                await ajaxPost(clearAllUrl);
                await fetchSnapshot();
            } catch (_) {}
        }
    });

    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") {
            fetchSnapshot();
            if (socket?.readyState !== WebSocket.OPEN) connect();
        }
    });

    window.addEventListener("focus", fetchSnapshot);
    window.addEventListener("online", () => {
        connect();
        fetchSnapshot();
    });

    if ("serviceWorker" in navigator) {
        navigator.serviceWorker.addEventListener(
            "message",
            (event) => {
                const data = event.data || {};

                if (data.type === "heartly.push.received") {
                    fetchSnapshot();
                    window.dispatchEvent(
                        new CustomEvent(
                            "heartly:push-received",
                            {
                                detail: data.payload || {},
                            }
                        )
                    );
                }
            }
        );
    }

    connect();
    fetchSnapshot();
    startPollingFallback();
})();
