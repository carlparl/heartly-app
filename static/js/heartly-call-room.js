(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    const page = document.getElementById("callPage");
    if (!page) return;

    const callId = String(page.dataset.callId || "");
    const threadId = String(page.dataset.threadId || "");
    const callType = String(page.dataset.callType || "audio");
    const currentUserId = String(
      page.dataset.currentUserId || ""
    );
    const isCaller = page.dataset.isCaller === "1";
    const isReceiver = page.dataset.isReceiver === "1";
    const chatUrl = page.dataset.chatUrl || "/chat/";
    const statusUrl = page.dataset.statusUrl || "";
    const missUrl = page.dataset.missUrl || "";
    const initialStartedAt =
      page.dataset.startedAt || "";

    let currentStatus =
      page.dataset.callStatus || "ringing";
    let socket = null;
    let reconnectTimer = null;
    let reconnectAttempt = 0;
    let socketClosing = false;
    let peerConnection = null;
    let localStream = null;
    let remoteStream = null;
    let pendingIceCandidates = [];
    let makingOffer = false;
    let mediaStarted = false;
    let muted = false;
    let cameraOff = false;
    let terminal = !["ringing", "accepted"].includes(
      currentStatus
    );
    let statusPollTimer = null;
    let missedTimer = null;
    let iceRestartTimer = null;
    let redirectTimer = null;

    const statusBadge =
      document.getElementById("callStatusBadge");
    const liveStatus =
      document.getElementById("callLiveStatus");
    const remoteVideo =
      document.getElementById("remoteVideo");
    const localVideo =
      document.getElementById("localVideo");
    const remoteAudio =
      document.getElementById("remoteAudio");
    const muteBtn =
      document.getElementById("muteBtn");
    const cameraBtn =
      document.getElementById("cameraBtn");
    const endCallForm =
      document.getElementById("endCallForm");
    const audioStateText =
      document.getElementById("audioStateText");
    const mediaUnlockBtn =
      document.getElementById("callMediaUnlockBtn");

    const csrfToken = (function () {
      const input = document.querySelector(
        'input[name="csrfmiddlewaretoken"]'
      );
      if (input && input.value) return input.value;

      const match = document.cookie.match(
        /(?:^|;\s*)csrftoken=([^;]+)/
      );
      return match
        ? decodeURIComponent(match[1])
        : "";
    })();

    const iceServersElement =
      document.getElementById("heartlyIceServers");
    let iceServers = [
      { urls: "stun:stun.l.google.com:19302" }
    ];

    if (iceServersElement) {
      try {
        const parsed = JSON.parse(
          iceServersElement.textContent
        );
        if (Array.isArray(parsed) && parsed.length) {
          iceServers = parsed;
        }
      } catch (error) {}
    }

    const rtcConfig = { iceServers: iceServers };
    const turnConfigured = iceServers.some(function (server) {
      const urls = Array.isArray(server.urls)
        ? server.urls
        : [server.urls];

      return urls.some(function (url) {
        return /^turns?:/i.test(String(url || ""));
      });
    });

    function setLiveStatus(text) {
      if (liveStatus) liveStatus.textContent = text;

      if (audioStateText && callType === "audio") {
        audioStateText.textContent = text;
      }
    }

    function setBadge(status) {
      if (!statusBadge) return;

      const value = String(status || "ended");
      statusBadge.textContent =
        value.charAt(0).toUpperCase() + value.slice(1);
      statusBadge.className =
        "call-status-badge call-status-" + value;
    }

    function getMediaElement() {
      return remoteVideo || remoteAudio || null;
    }

    async function unlockRemoteMedia() {
      const media = getMediaElement();
      if (!media) return true;

      try {
        await media.play();
        if (mediaUnlockBtn) mediaUnlockBtn.hidden = true;
        return true;
      } catch (error) {
        if (mediaUnlockBtn) mediaUnlockBtn.hidden = false;
        setLiveStatus("Tap Enable audio to hear the call.");
        return false;
      }
    }

    function websocketUrl() {
      const scheme =
        window.location.protocol === "https:" ? "wss:" : "ws:";
      return (
        scheme +
        "//" +
        window.location.host +
        "/ws/chat/" +
        threadId +
        "/"
      );
    }

    function sendSocket(payload) {
      if (
        !socket ||
        socket.readyState !== WebSocket.OPEN
      ) {
        return false;
      }

      socket.send(JSON.stringify(payload));
      return true;
    }

    async function postAction(url) {
      if (!url) {
        throw new Error("Call action URL is unavailable.");
      }

      const response = await fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "X-CSRFToken": csrfToken,
          "X-Requested-With": "XMLHttpRequest",
          "Accept": "application/json"
        }
      });

      let data = {};
      try {
        data = await response.json();
      } catch (error) {}

      if (!response.ok || data.ok === false) {
        throw new Error(
          data.message ||
          "The call action could not be completed."
        );
      }

      return data;
    }

    function stopLocalMedia() {
      if (localStream) {
        localStream.getTracks().forEach(function (track) {
          try { track.stop(); } catch (error) {}
        });
      }

      localStream = null;
      mediaStarted = false;

      if (localVideo) localVideo.srcObject = null;
    }

    function closePeerConnection() {
      clearTimeout(iceRestartTimer);
      iceRestartTimer = null;
      pendingIceCandidates = [];

      if (peerConnection) {
        try {
          peerConnection.ontrack = null;
          peerConnection.onicecandidate = null;
          peerConnection.onconnectionstatechange = null;
          peerConnection.oniceconnectionstatechange = null;
          peerConnection.close();
        } catch (error) {}
      }

      peerConnection = null;
      remoteStream = null;

      if (remoteVideo) remoteVideo.srcObject = null;
      if (remoteAudio) remoteAudio.srcObject = null;
    }

    function stopAllMedia() {
      closePeerConnection();
      stopLocalMedia();
    }

    function clearCallTimers() {
      clearTimeout(missedTimer);
      clearTimeout(iceRestartTimer);
      clearTimeout(redirectTimer);
      clearInterval(statusPollTimer);
      missedTimer = null;
      iceRestartTimer = null;
      redirectTimer = null;
      statusPollTimer = null;
    }

    function finishCall(status, shouldRedirect) {
      if (terminal && currentStatus === status) return;

      terminal = true;
      currentStatus = status;
      socketClosing = true;
      clearCallTimers();
      setBadge(status);

      const labels = {
        declined: "Call declined",
        ended: "Call ended",
        missed: "Call missed"
      };
      setLiveStatus(labels[status] || "Call ended");
      stopAllMedia();

      if (socket) {
        try { socket.close(); } catch (error) {}
      }

      if (shouldRedirect !== false) {
        redirectTimer = window.setTimeout(function () {
          window.location.href = chatUrl;
        }, 1200);
      }
    }

    async function ensurePeerConnection() {
      if (
        peerConnection &&
        peerConnection.connectionState !== "closed"
      ) {
        return peerConnection;
      }

      peerConnection = new RTCPeerConnection(rtcConfig);
      pendingIceCandidates = [];

      if (localStream) {
        localStream.getTracks().forEach(function (track) {
          const alreadyAdded =
            peerConnection.getSenders().some(
              function (sender) {
                return (
                  sender.track &&
                  sender.track.id === track.id
                );
              }
            );

          if (!alreadyAdded) {
            peerConnection.addTrack(track, localStream);
          }
        });
      }

      peerConnection.ontrack = function (event) {
        const stream =
          event.streams && event.streams[0]
            ? event.streams[0]
            : new MediaStream([event.track]);

        remoteStream = stream;

        if (remoteVideo) remoteVideo.srcObject = stream;
        if (remoteAudio) remoteAudio.srcObject = stream;

        setBadge("accepted");
        setLiveStatus("Connected");
        unlockRemoteMedia();
      };

      peerConnection.onicecandidate = function (event) {
        if (!event.candidate) return;

        sendSocket({
          type: "webrtc.ice",
          call_id: callId,
          candidate: event.candidate
        });
      };

      peerConnection.onconnectionstatechange = function () {
        if (!peerConnection || terminal) return;

        const state = peerConnection.connectionState;

        if (state === "connected") {
          clearTimeout(iceRestartTimer);
          iceRestartTimer = null;
          setBadge("accepted");
          setLiveStatus("Connected");
          unlockRemoteMedia();
          return;
        }

        if (
          state === "disconnected" ||
          state === "failed"
        ) {
          setLiveStatus("Reconnecting call...");
          scheduleIceRestart(
            state === "failed" ? 300 : 1800
          );
        }
      };

      peerConnection.oniceconnectionstatechange =
        function () {
          if (!peerConnection || terminal) return;

          if (
            peerConnection.iceConnectionState === "failed"
          ) {
            scheduleIceRestart(300);
          }
        };

      return peerConnection;
    }

    async function startLocalMedia() {
      if (mediaStarted && localStream) {
        await ensurePeerConnection();
        return localStream;
      }

      if (
        !navigator.mediaDevices ||
        !navigator.mediaDevices.getUserMedia
      ) {
        setLiveStatus(
          "This browser cannot access the microphone or camera."
        );
        return null;
      }

      const constraints =
        callType === "video"
          ? {
              audio: {
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true
              },
              video: {
                facingMode: "user"
              }
            }
          : {
              audio: {
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true
              },
              video: false
            };

      try {
        localStream =
          await navigator.mediaDevices.getUserMedia(
            constraints
          );
        mediaStarted = true;

        if (localVideo && callType === "video") {
          localVideo.srcObject = localStream;
          try { await localVideo.play(); } catch (error) {}
        }

        const pc = await ensurePeerConnection();

        localStream.getTracks().forEach(function (track) {
          const alreadyAdded = pc.getSenders().some(
            function (sender) {
              return (
                sender.track &&
                sender.track.id === track.id
              );
            }
          );

          if (!alreadyAdded) {
            pc.addTrack(track, localStream);
          }
        });

        setLiveStatus(
          currentStatus === "ringing"
            ? "Ringing..."
            : "Media ready"
        );
        return localStream;
      } catch (error) {
        console.error("Heartly call media failed:", error);
        setLiveStatus(
          "Microphone or camera permission was not granted."
        );
        if (mediaUnlockBtn) {
          mediaUnlockBtn.hidden = false;
          mediaUnlockBtn.textContent =
            "Enable microphone";
        }
        return null;
      }
    }

    async function flushPendingIceCandidates() {
      if (
        !peerConnection ||
        !peerConnection.remoteDescription
      ) {
        return;
      }

      while (pendingIceCandidates.length) {
        const candidate = pendingIceCandidates.shift();

        try {
          await peerConnection.addIceCandidate(
            new RTCIceCandidate(candidate)
          );
        } catch (error) {
          console.error(
            "Heartly ICE candidate failed:",
            error
          );
        }
      }
    }

    async function createCallerOffer(options) {
      options = options || {};

      if (
        terminal ||
        !isCaller ||
        currentStatus !== "accepted" ||
        makingOffer
      ) {
        return;
      }

      if (
        !socket ||
        socket.readyState !== WebSocket.OPEN
      ) {
        connectSocket();
        return;
      }

      makingOffer = true;

      try {
        const stream = await startLocalMedia();
        if (!stream) return;

        const pc = await ensurePeerConnection();

        if (
          pc.signalingState !== "stable" &&
          !options.iceRestart
        ) {
          return;
        }

        const offer = await pc.createOffer(
          options.iceRestart
            ? { iceRestart: true }
            : undefined
        );
        await pc.setLocalDescription(offer);

        sendSocket({
          type: "webrtc.offer",
          call_id: callId,
          sdp: pc.localDescription,
          ice_restart: Boolean(options.iceRestart)
        });

        setLiveStatus(
          options.iceRestart
            ? "Restoring connection..."
            : "Connecting..."
        );
      } catch (error) {
        console.error(
          "Heartly offer creation failed:",
          error
        );
        setLiveStatus("Could not start call media.");
      } finally {
        makingOffer = false;
      }
    }

    async function prepareReceiver() {
      if (
        terminal ||
        !isReceiver ||
        currentStatus !== "accepted"
      ) {
        return;
      }

      const stream = await startLocalMedia();
      if (stream) {
        setLiveStatus("Waiting for caller signal...");
      }
    }

    async function handleOffer(data) {
      if (
        terminal ||
        String(data.sender_id) === currentUserId
      ) {
        return;
      }

      currentStatus = "accepted";
      setBadge("accepted");

      const stream = await startLocalMedia();
      if (!stream) return;

      const pc = await ensurePeerConnection();

      try {
        if (pc.signalingState !== "stable") {
          await pc.setLocalDescription({
            type: "rollback"
          });
        }
      } catch (error) {}

      try {
        await pc.setRemoteDescription(
          new RTCSessionDescription(data.sdp)
        );
        await flushPendingIceCandidates();

        const answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);

        sendSocket({
          type: "webrtc.answer",
          call_id: callId,
          sdp: pc.localDescription
        });

        setLiveStatus("Connecting...");
      } catch (error) {
        console.error(
          "Heartly offer handling failed:",
          error
        );
        setLiveStatus("Call negotiation failed.");
      }
    }

    async function handleAnswer(data) {
      if (
        terminal ||
        String(data.sender_id) === currentUserId ||
        !peerConnection
      ) {
        return;
      }

      try {
        await peerConnection.setRemoteDescription(
          new RTCSessionDescription(data.sdp)
        );
        await flushPendingIceCandidates();
        setLiveStatus("Connecting...");
      } catch (error) {
        console.error(
          "Heartly answer handling failed:",
          error
        );
      }
    }

    async function handleIce(data) {
      if (
        terminal ||
        String(data.sender_id) === currentUserId ||
        !data.candidate
      ) {
        return;
      }

      if (
        !peerConnection ||
        !peerConnection.remoteDescription
      ) {
        pendingIceCandidates.push(data.candidate);
        return;
      }

      try {
        await peerConnection.addIceCandidate(
          new RTCIceCandidate(data.candidate)
        );
      } catch (error) {
        console.error(
          "Heartly ICE candidate failed:",
          error
        );
      }
    }

    function scheduleIceRestart(delay) {
      if (
        terminal ||
        currentStatus !== "accepted" ||
        iceRestartTimer
      ) {
        return;
      }

      iceRestartTimer = window.setTimeout(
        async function () {
          iceRestartTimer = null;

          if (!socket ||
              socket.readyState !== WebSocket.OPEN) {
            connectSocket();
            return;
          }

          if (isCaller) {
            await createCallerOffer({
              iceRestart: true
            });
          } else {
            closePeerConnection();
            await prepareReceiver();
            sendSocket({
              type: "call.sync",
              call_id: callId
            });
          }

          if (!turnConfigured) {
            window.setTimeout(function () {
              if (
                peerConnection &&
                ["failed", "disconnected"].includes(
                  peerConnection.connectionState
                )
              ) {
                setLiveStatus(
                  "Connection could not be restored. A TURN server may be required."
                );
              }
            }, 8000);
          }
        },
        Math.max(0, Number(delay) || 0)
      );
    }

    function scheduleMissedCall(startedAt) {
      clearTimeout(missedTimer);
      missedTimer = null;

      if (
        terminal ||
        !isCaller ||
        currentStatus !== "ringing" ||
        !missUrl
      ) {
        return;
      }

      const startedMs = Date.parse(
        startedAt || initialStartedAt || ""
      );
      const elapsed = Number.isFinite(startedMs)
        ? Math.max(0, Date.now() - startedMs)
        : 0;
      const remaining = Math.max(
        1000,
        60000 - elapsed
      );

      missedTimer = window.setTimeout(
        async function () {
          if (
            terminal ||
            currentStatus !== "ringing"
          ) {
            return;
          }

          try {
            const data = await postAction(missUrl);
            const call = data.call || {};
            applyServerState(call, true);
          } catch (error) {
            fetchCallStatus();
          }
        },
        remaining
      );
    }

    async function applyServerState(call, redirectTerminal) {
      if (!call || !call.status) return;

      currentStatus = String(call.status);
      page.dataset.callStatus = currentStatus;

      if (
        ["declined", "ended", "missed"].includes(
          currentStatus
        )
      ) {
        finishCall(
          currentStatus,
          redirectTerminal !== false
        );
        return;
      }

      terminal = false;
      socketClosing = false;
      setBadge(currentStatus);

      if (currentStatus === "ringing") {
        setLiveStatus(
          isCaller
            ? "Ringing..."
            : "Incoming call"
        );
        scheduleMissedCall(call.started_at);
        if (isCaller) startLocalMedia();
        return;
      }

      clearTimeout(missedTimer);
      missedTimer = null;

      if (currentStatus === "accepted") {
        setBadge("accepted");

        if (isCaller) {
          await createCallerOffer();
        } else {
          await prepareReceiver();
        }
      }
    }

    async function fetchCallStatus() {
      if (terminal || !statusUrl) return;

      try {
        const response = await fetch(statusUrl, {
          credentials: "same-origin",
          cache: "no-store",
          headers: {
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest"
          }
        });

        if (!response.ok) return;

        const data = await response.json();
        await applyServerState(
          data.call || data,
          true
        );
      } catch (error) {}
    }

    function scheduleReconnect() {
      if (
        terminal ||
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
          connectSocket();
        },
        delay
      );
    }

    function connectSocket() {
      if (
        terminal ||
        socketClosing ||
        !threadId ||
        !("WebSocket" in window) ||
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

        sendSocket({
          type: "call.sync",
          call_id: callId
        });
      };

      socket.onmessage = async function (event) {
        let data = null;

        try {
          data = JSON.parse(event.data);
        } catch (error) {
          return;
        }

        if (!data || !data.type) return;

        if (
          data.call_id &&
          String(data.call_id) !== callId
        ) {
          return;
        }

        if (data.type === "call.state") {
          await applyServerState(data, false);
          return;
        }

        if (data.type === "call.accepted") {
          currentStatus = "accepted";
          await applyServerState(
            Object.assign({}, data, {
              status: "accepted"
            }),
            false
          );
          return;
        }

        if (
          data.type === "call.declined" ||
          data.type === "call.ended" ||
          data.type === "call.missed"
        ) {
          const status = data.type.split(".")[1];
          finishCall(status, true);
          return;
        }

        if (data.type === "webrtc.offer") {
          await handleOffer(data);
          return;
        }

        if (data.type === "webrtc.answer") {
          await handleAnswer(data);
          return;
        }

        if (data.type === "webrtc.ice") {
          await handleIce(data);
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

    if (muteBtn) {
      muteBtn.addEventListener("click", function () {
        if (!localStream) return;

        muted = !muted;
        localStream.getAudioTracks().forEach(
          function (track) {
            track.enabled = !muted;
          }
        );
        muteBtn.textContent =
          muted ? "Unmute" : "Mute";
      });
    }

    if (cameraBtn) {
      cameraBtn.addEventListener("click", function () {
        if (!localStream) return;

        cameraOff = !cameraOff;
        localStream.getVideoTracks().forEach(
          function (track) {
            track.enabled = !cameraOff;
          }
        );
        cameraBtn.textContent =
          cameraOff ? "Camera on" : "Camera off";
      });
    }

    if (mediaUnlockBtn) {
      mediaUnlockBtn.addEventListener(
        "click",
        async function () {
          mediaUnlockBtn.disabled = true;

          if (!localStream) {
            await startLocalMedia();
          }

          await unlockRemoteMedia();
          mediaUnlockBtn.disabled = false;
        }
      );
    }

    if (endCallForm) {
      endCallForm.addEventListener(
        "submit",
        async function (event) {
          event.preventDefault();

          try {
            const data = await postAction(
              endCallForm.action
            );
            const call = data.call || {
              status: "ended"
            };
            await applyServerState(call, true);
          } catch (error) {
            setLiveStatus(
              error.message || "Could not end the call."
            );
          }
        }
      );
    }

    document.addEventListener(
      "click",
      function (event) {
        const link = event.target.closest("a[href]");

        if (!link || terminal) return;

        event.preventDefault();
        setLiveStatus(
          "End the call before leaving this screen."
        );
      },
      true
    );

    document.addEventListener(
      "pointerdown",
      function () {
        unlockRemoteMedia();
      },
      { once: true }
    );

    window.addEventListener("online", function () {
      connectSocket();
      fetchCallStatus();
    });

    document.addEventListener(
      "visibilitychange",
      function () {
        if (document.visibilityState === "visible") {
          connectSocket();
          fetchCallStatus();
          unlockRemoteMedia();
        }
      }
    );

    /*
     * Do not end the call on pagehide. Mobile PWAs can emit pagehide
     * when temporarily backgrounded. The previous implementation
     * treated that as a hang-up.
     */
    window.addEventListener("beforeunload", function () {
      socketClosing = true;
      clearTimeout(reconnectTimer);
    });

    statusPollTimer = window.setInterval(
      fetchCallStatus,
      4000
    );

    setBadge(currentStatus);

    if (terminal) {
      setLiveStatus("Call " + currentStatus + ".");
      stopAllMedia();
      return;
    }

    connectSocket();
    fetchCallStatus();

    if (currentStatus === "ringing") {
      scheduleMissedCall(initialStartedAt);
      if (isCaller) startLocalMedia();
    } else if (currentStatus === "accepted") {
      if (isCaller) {
        startLocalMedia();
      } else {
        prepareReceiver();
      }
    }
  });
})();
