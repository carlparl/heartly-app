(function () {
  "use strict";

  const root = document.querySelector("[data-heartly-global-calls]");
  if (!root) return;

  const userId = Number(root.dataset.userId || "0");
  const isAuthenticated = root.dataset.authenticated === "1";
  if (!isAuthenticated || !userId || !("WebSocket" in window)) return;

  const toast = document.getElementById("heartlyGlobalCallToast");
  const avatar = document.getElementById("heartlyGlobalCallAvatar");
  const title = document.getElementById("heartlyGlobalCallTitle");
  const text = document.getElementById("heartlyGlobalCallText");
  const answerBtn = document.getElementById("heartlyGlobalCallAnswer");
  const declineBtn = document.getElementById("heartlyGlobalCallDecline");

  let socket = null;
  let reconnectTimer = null;
  let activeCall = null;
  let ringtoneContext = null;
  let ringtoneTimer = null;

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

  function ensureRingtoneContext() {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return null;
    if (!ringtoneContext) ringtoneContext = new AudioContextClass();
    if (ringtoneContext.state === "suspended") ringtoneContext.resume().catch(function () {});
    return ringtoneContext;
  }

  function beepOnce(duration, frequency) {
    const ctx = ensureRingtoneContext();
    if (!ctx) return;
    try {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.value = frequency || 760;
      gain.gain.setValueAtTime(0.0001, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.18, ctx.currentTime + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + (duration || 0.22));
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + (duration || 0.22));
    } catch (error) {}
  }

  function startRingtone() {
    stopRingtone();
    beepOnce(0.22, 760);
    ringtoneTimer = window.setInterval(function () {
      beepOnce(0.22, 760);
      window.setTimeout(function () { beepOnce(0.2, 620); }, 260);
    }, 1300);
  }

  function stopRingtone() {
    if (ringtoneTimer) window.clearInterval(ringtoneTimer);
    ringtoneTimer = null;
  }

  function hideCall() {
    stopRingtone();
    activeCall = null;
    if (toast) toast.hidden = true;
  }

  function showIncomingCall(payload) {
    if (!payload || Number(payload.caller_id) === userId) return;

    activeCall = payload;
    const caller = payload.caller_name || "Heartly User";
    const type = String(payload.call_type || "audio").toLowerCase();

    if (avatar) avatar.textContent = type === "video" ? "🎥" : "☎";
    if (title) title.textContent = caller;
    if (text) text.textContent = (type === "video" ? "Video" : "Audio") + " call incoming";
    if (answerBtn) answerBtn.href = payload.accept_url || payload.url || ("/chat/call/" + payload.call_id + "/");
    if (toast) toast.hidden = false;

    startRingtone();
  }

  function connect() {
    const scheme = window.location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(scheme + "://" + window.location.host + "/ws/heartly/calls/");

    socket.onmessage = function (event) {
      let payload = null;
      try { payload = JSON.parse(event.data); } catch (error) { return; }
      if (!payload || !payload.type) return;

      if (payload.type === "incoming_call" || payload.type === "call.incoming") {
        showIncomingCall(payload);
        return;
      }

      if (["call_accepted", "call_declined", "call_ended", "missed_call", "call.accepted", "call.declined", "call.ended", "call.missed"].includes(payload.type)) {
        hideCall();
      }
    };

    socket.onclose = function () {
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      reconnectTimer = window.setTimeout(connect, 2500);
    };
  }

  document.addEventListener("pointerdown", ensureRingtoneContext, { once: true });
  document.addEventListener("keydown", ensureRingtoneContext, { once: true });

  if (declineBtn) {
    declineBtn.addEventListener("click", async function () {
      if (!activeCall || !activeCall.call_id) {
        hideCall();
        return;
      }

      try {
        await fetch(activeCall.decline_url || ("/chat/call/" + activeCall.call_id + "/decline/"), {
          method: "POST",
          headers: {
            "X-CSRFToken": getCookie("csrftoken"),
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json"
          },
          credentials: "same-origin"
        });
      } catch (error) {}

      hideCall();
    });
  }

  if (answerBtn) {
    answerBtn.addEventListener("click", function () {
      stopRingtone();
    });
  }

  connect();
})();
