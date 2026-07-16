(function () {
  "use strict";

  const root = document.querySelector(
    "[data-heartly-global-calls]"
  );
  if (!root) return;

  const userId = Number(root.dataset.userId || "0");
  const isAuthenticated =
    root.dataset.authenticated === "1";

  if (
    !isAuthenticated ||
    !userId ||
    !("WebSocket" in window)
  ) {
    return;
  }

  const toast =
    document.getElementById("heartlyGlobalCallToast");
  const avatar =
    document.getElementById("heartlyGlobalCallAvatar");
  const title =
    document.getElementById("heartlyGlobalCallTitle");
  const text =
    document.getElementById("heartlyGlobalCallText");
  const answerBtn =
    document.getElementById("heartlyGlobalCallAnswer");
  const declineBtn =
    document.getElementById("heartlyGlobalCallDecline");

  let socket = null;
  let reconnectTimer = null;
  let reconnectAttempt = 0;
  let socketClosing = false;
  let activeCall = null;
  let ringtoneContext = null;
  let ringtoneNodes = [];
  let callExpiryTimer = null;

  function getCookie(name) {
    const match = document.cookie.match(
      new RegExp("(?:^|;\\s*)" + name + "=([^;]+)")
    );
    return match ? decodeURIComponent(match[1]) : "";
  }

  function ensureRingtoneContext() {
    const AudioContextClass =
      window.AudioContext || window.webkitAudioContext;

    if (!AudioContextClass) return null;

    if (!ringtoneContext) {
      ringtoneContext = new AudioContextClass();
    }

    if (ringtoneContext.state === "suspended") {
      ringtoneContext.resume().catch(function () {});
    }

    return ringtoneContext;
  }

  function scheduleTone(
    context,
    startsAt,
    duration,
    frequency
  ) {
    try {
      const oscillator = context.createOscillator();
      const gain = context.createGain();

      oscillator.type = "sine";
      oscillator.frequency.setValueAtTime(
        frequency,
        startsAt
      );
      gain.gain.setValueAtTime(0.0001, startsAt);
      gain.gain.exponentialRampToValueAtTime(
        0.2,
        startsAt + 0.025
      );
      gain.gain.exponentialRampToValueAtTime(
        0.0001,
        startsAt + duration
      );

      oscillator.connect(gain);
      gain.connect(context.destination);
      oscillator.start(startsAt);
      oscillator.stop(
        startsAt + duration + 0.02
      );
      ringtoneNodes.push({
        oscillator: oscillator,
        gain: gain
      });
    } catch (error) {}
  }

  function stopRingtone() {
    ringtoneNodes.forEach(function (node) {
      try { node.oscillator.stop(); } catch (error) {}
      try { node.oscillator.disconnect(); } catch (error) {}
      try { node.gain.disconnect(); } catch (error) {}
    });
    ringtoneNodes = [];
  }

  function startRingtone() {
    stopRingtone();
    const context = ensureRingtoneContext();
    if (!context) return;

    const schedulePattern = function () {
      const startsAt = context.currentTime + 0.05;

      for (let index = 0; index < 40; index += 1) {
        const cycle = startsAt + (index * 1.45);
        scheduleTone(context, cycle, 0.24, 760);
        scheduleTone(
          context,
          cycle + 0.3,
          0.22,
          620
        );
      }
    };

    if (context.state === "suspended") {
      context.resume()
        .then(schedulePattern)
        .catch(function () {});
    } else {
      schedulePattern();
    }
  }

  window.HeartlyCallAudio = {
    start: startRingtone,
    stop: stopRingtone
  };

  function activeCallMatches(callId) {
    if (!activeCall || !callId) return false;

    return (
      String(activeCall.call_id) ===
      String(callId)
    );
  }

  function hideCall(expectedCallId) {
    if (
      expectedCallId &&
      activeCall &&
      !activeCallMatches(expectedCallId)
    ) {
      return false;
    }

    stopRingtone();
    clearTimeout(callExpiryTimer);
    callExpiryTimer = null;
    activeCall = null;
    if (toast) toast.hidden = true;
    return true;
  }

  function showIncomingCall(payload) {
    if (
      !payload ||
      Number(payload.caller_id) === userId
    ) {
      return;
    }

    const sameIncomingCallVisible = Boolean(
      payload.call_id &&
      activeCall &&
      activeCallMatches(payload.call_id) &&
      toast &&
      !toast.hidden
    );

    if (sameIncomingCallVisible) {
      /*
       * The active-call recovery query and the live broadcast can
       * deliver the same call within milliseconds. Refresh the
       * payload without restarting the ringtone or popup.
       */
      activeCall = Object.assign({}, activeCall, payload);
      return;
    }

    activeCall = payload;
    const caller =
      payload.caller_name || "Heartly User";
    const type = String(
      payload.call_type || "audio"
    ).toLowerCase();

    if (avatar) {
      avatar.textContent =
        type === "video" ? "🎥" : "☎";
    }
    if (title) title.textContent = caller;
    if (text) {
      text.textContent =
        (type === "video" ? "Video" : "Audio") +
        " call incoming";
    }
    if (answerBtn) {
      answerBtn.href =
        payload.url ||
        ("/chat/call/" + payload.call_id + "/");
    }
    if (toast) toast.hidden = false;

    startRingtone();
    clearTimeout(callExpiryTimer);
    const shownCallId = payload.call_id;
    callExpiryTimer = window.setTimeout(
      function () {
        hideCall(shownCallId);
      },
      65000
    );
  }

  function websocketUrl() {
    const scheme =
      window.location.protocol === "https:" ? "wss:" : "ws:";
    return (
      scheme +
      "//" +
      window.location.host +
      "/ws/heartly/calls/"
    );
  }

  function scheduleReconnect() {
    if (
      socketClosing ||
      reconnectTimer ||
      navigator.onLine === false
    ) {
      return;
    }

    const delay = Math.min(
      30000,
      1000 * Math.pow(2, reconnectAttempt)
    );
    reconnectAttempt += 1;

    reconnectTimer = window.setTimeout(
      function () {
        reconnectTimer = null;
        connect();
      },
      delay
    );
  }

  function connect() {
    if (
      socketClosing ||
      navigator.onLine === false
    ) {
      return;
    }

    if (
      socket &&
      (
        socket.readyState === WebSocket.OPEN ||
        socket.readyState === WebSocket.CONNECTING
      )
    ) {
      return;
    }

    socket = new WebSocket(websocketUrl());

    socket.onopen = function () {
      reconnectAttempt = 0;
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    };

    socket.onmessage = function (event) {
      let payload = null;

      try {
        payload = JSON.parse(event.data);
      } catch (error) {
        return;
      }

      if (!payload || !payload.type) return;

      if (
        payload.type === "incoming_call" ||
        payload.type === "call.incoming"
      ) {
        showIncomingCall(payload);
        return;
      }

      if (payload.type === "call.none") {
        /*
         * The initial active-call lookup can race a newly arriving
         * call event. Never let a delayed call.none clear a banner
         * that is already displaying a concrete call.
         */
        if (!activeCall) {
          hideCall();
        }
        return;
      }

      if (
        [
          "call_accepted",
          "call_declined",
          "call_ended",
          "missed_call",
          "call.accepted",
          "call.declined",
          "call.ended",
          "call.missed"
        ].includes(payload.type)
      ) {
        /*
         * Ignore delayed terminal events from an older call. Only
         * the event for the currently displayed call may clear it.
         */
        if (
          activeCall &&
          payload.call_id &&
          activeCallMatches(payload.call_id)
        ) {
          hideCall(payload.call_id);
        }
      }
    };

    socket.onerror = function () {
      try { socket.close(); } catch (error) {}
    };

    socket.onclose = function () {
      socket = null;
      scheduleReconnect();
    };
  }

  async function postCallAction(url) {
    if (!url) return false;

    const response = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "X-CSRFToken": getCookie("csrftoken"),
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json"
      }
    });

    return response.ok;
  }

  document.addEventListener(
    "pointerdown",
    ensureRingtoneContext,
    { once: true }
  );
  document.addEventListener(
    "keydown",
    ensureRingtoneContext,
    { once: true }
  );

  if (declineBtn) {
    declineBtn.addEventListener(
      "click",
      async function () {
        const call = activeCall;

        if (!call || !call.call_id) {
          hideCall();
          return;
        }

        try {
          await postCallAction(
            call.decline_url ||
            (
              "/chat/call/" +
              call.call_id +
              "/decline/"
            )
          );
        } catch (error) {}

        hideCall(call.call_id);
      }
    );
  }

  if (answerBtn) {
    answerBtn.addEventListener(
      "click",
      async function (event) {
        const call = activeCall;
        if (!call) return;

        event.preventDefault();
        stopRingtone();

        const destination =
          call.url ||
          ("/chat/call/" + call.call_id + "/");

        try {
          await postCallAction(
            call.accept_post_url || ""
          );
        } catch (error) {
          /*
           * The call room keeps a GET acceptance fallback for
           * older clients and temporary network races.
           */
        }

        window.location.href = destination;
      }
    );
  }

  window.addEventListener("online", connect);

  document.addEventListener(
    "visibilitychange",
    function () {
      if (
        document.visibilityState === "visible"
      ) {
        connect();
      }
    }
  );

  window.addEventListener("beforeunload", function () {
    socketClosing = true;
    clearTimeout(reconnectTimer);
    if (socket) {
      try { socket.close(); } catch (error) {}
    }
  });

  connect();
})();
