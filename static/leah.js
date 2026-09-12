(() => {
  "use strict";

  const config = Object.assign(
    {
      healthUrl: "/api/health",
      controlStatusUrl: "/api/leah/pulse",
      chatUrl: "/api/chat",
      chatHistoryUrl: "/api/chat/history",
      chatResumeUrl: "/api/chat/resume",
      chatLoginUrl: "/api/chat/login",
      chatLogoutUrl: "/api/chat/logout",
      uploadUrl: "/api/chat/upload",
    },
    window.__LEAH_CONFIG__ || {},
  );

  const qs = new URLSearchParams(window.location.search || "");
  const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition || null;
  const state = {
    userId: "",
    sessionId: "",
    chatLoginEnabled: false,
    voiceEnabled: false,
    listenMode: false,
    recognition: null,
    recognitionActive: false,
    recognitionMode: "manual",
    recognitionRestart: false,
    cameraStream: null,
    cameraLive: false,
    thinking: false,
    uploading: false,
    stagedItems: [],
    recentHandoff: [],
    historyLoaded: false,
    pendingResume: false,
    healthTimer: null,
    replyPulseTimers: [],
    replyPulseFadeTimer: null,
    moodMode: "calm",
    moodReason: "steady runtime",
    lastRuntimePulse: null,
    lastOutreachId: "",
  };

  const moodProfiles = {
    calm: {
      label: "Calm Flow",
      chip: "ok",
      primary: "87, 211, 200",
      secondary: "126, 193, 255",
      tertiary: "255, 200, 106",
      note: "steady runtime",
    },
    sensing: {
      label: "Sensing",
      chip: "live",
      primary: "87, 205, 255",
      secondary: "87, 211, 200",
      tertiary: "152, 230, 255",
      note: "watching live input",
    },
    focus: {
      label: "Focused",
      chip: "live",
      primary: "98, 158, 255",
      secondary: "87, 211, 200",
      tertiary: "188, 225, 255",
      note: "working a concrete task",
    },
    synthesis: {
      label: "Deep Work",
      chip: "warn",
      primary: "255, 200, 106",
      secondary: "255, 148, 96",
      tertiary: "255, 230, 166",
      note: "weighing multiple paths",
    },
    strain: {
      label: "Strain",
      chip: "danger",
      primary: "255, 130, 111",
      secondary: "255, 179, 122",
      tertiary: "255, 214, 168",
      note: "blocked or under pressure",
    },
  };

  const dom = {
    chat: document.getElementById("chat"),
    form: document.getElementById("composerForm"),
    input: document.getElementById("messageInput"),
    dropZone: document.getElementById("dropZone"),
    fileInput: document.getElementById("fileInput"),
    btnUpload: document.getElementById("btnUpload"),
    btnCamera: document.getElementById("btnCamera"),
    btnCapture: document.getElementById("btnCapture"),
    btnMic: document.getElementById("btnMic"),
    btnListen: document.getElementById("btnListen"),
    btnVoice: document.getElementById("btnVoice"),
    btnSend: document.getElementById("btnSend"),
    btnNewSession: null,
    stagedList: document.getElementById("stagedList"),
    activityHeadline: document.getElementById("activityHeadline"),
    activityDetail: document.getElementById("activityDetail"),
    welcomeUser: document.getElementById("welcomeUser"),
    sessionLabel: document.getElementById("sessionLabel"),
    userLabel: document.getElementById("userLabel"),
    modeLabel: document.getElementById("modeLabel"),
    moodLabel: document.getElementById("moodLabel"),
    heroState: document.getElementById("heroState"),
    heroInputs: document.getElementById("heroInputs"),
    pulseRuntime: document.getElementById("pulseRuntime"),
    pulseQueue: document.getElementById("pulseQueue"),
    pulseSearch: document.getElementById("pulseSearch"),
    pulseMaintenance: document.getElementById("pulseMaintenance"),
    pulseTask: document.getElementById("pulseTask"),
    transcriptBox: document.getElementById("transcriptBox"),
    cameraPreview: document.getElementById("cameraPreview"),
    cameraCanvas: document.getElementById("cameraCanvas"),
    cameraEmpty: document.getElementById("cameraEmpty"),
    presenceHealth: document.getElementById("presenceHealth"),
    presenceThinking: document.getElementById("presenceThinking"),
    presenceListening: document.getElementById("presenceListening"),
    presenceVoice: document.getElementById("presenceVoice"),
    presenceCamera: document.getElementById("presenceCamera"),
    presenceMood: document.getElementById("presenceMood"),
    presenceUploads: document.getElementById("presenceUploads"),
    headerPresenceHealth: document.getElementById("headerPresenceHealth"),
    headerPresenceThinking: document.getElementById("headerPresenceThinking"),
    headerPresenceListening: document.getElementById("headerPresenceListening"),
    headerPresenceVoice: document.getElementById("headerPresenceVoice"),
    headerPresenceCamera: document.getElementById("headerPresenceCamera"),
    headerPresenceMood: document.getElementById("headerPresenceMood"),
    dotCore: document.getElementById("stateCore"),
    dotGuard: document.getElementById("stateGuard"),
    dotHttp: document.getElementById("stateHttp"),
    dotOllama: document.getElementById("stateOllama"),
    focusTask: document.getElementById("focusTask"),
    focusContext: document.getElementById("focusContext"),
    focusMemory: document.getElementById("focusMemory"),
    focusVoice: document.getElementById("focusVoice"),
    focusContinuity: document.getElementById("focusContinuity"),
    focusSystem: document.getElementById("focusSystem"),
    evidenceFeed: document.getElementById("evidenceFeed"),
    hudStatus: document.getElementById("hudStatus"),
    hudRing: document.querySelector(".hud-container"),
  };

  function makeUserId() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return "leah-" + window.crypto.randomUUID().replace(/-/g, "").slice(0, 24);
    }
    return "leah-" + Math.random().toString(16).slice(2) + Date.now().toString(16);
  }

  function humanBytes(value) {
    const bytes = Number(value || 0);
    if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
    const units = ["B", "KB", "MB", "GB"];
    let size = bytes;
    let index = 0;
    while (size >= 1024 && index < units.length - 1) {
      size /= 1024;
      index += 1;
    }
    return `${size.toFixed(size >= 10 || index === 0 ? 0 : 1)} ${units[index]}`;
  }

  function setChip(el, label, mode) {
    if (!el) return;
    el.textContent = label;
    el.classList.remove("ok", "live", "warn", "danger");
    if (mode) {
      el.classList.add(mode);
    }
  }

  function formatWelcomeUser(value) {
    const raw = String(value || "").trim();
    if (!raw) return "User";
    if (/^(web-|leah-)/i.test(raw)) return "User";
    if (raw.includes("@")) {
      const local = raw.split("@")[0].trim();
      return local || "User";
    }
    if (/^[a-f0-9-]{12,}$/i.test(raw)) return "User";
    return raw;
  }

  function syncSessionLabels() {
    if (dom.sessionLabel) {
      dom.sessionLabel.textContent = state.sessionId ? state.sessionId : "Not started";
    }
    if (dom.userLabel) {
      dom.userLabel.textContent = state.userId || "Unknown";
    }
    if (dom.welcomeUser) {
      dom.welcomeUser.textContent = formatWelcomeUser(state.userId);
    }
    if (dom.modeLabel) {
      dom.modeLabel.textContent = state.listenMode ? "Hands-free listen" : "Conversation";
    }
    if (dom.moodLabel) {
      const profile = moodProfiles[state.moodMode] || moodProfiles.calm;
      dom.moodLabel.textContent = `${profile.label} · ${state.moodReason || profile.note}`;
    }
  }

  function setStatus(el, ok, label) {
    if (!el) return;
    el.textContent = label || (ok ? "ONLINE" : "OFFLINE");
    el.className = "status-state " + (ok ? "ok" : "off");
  }

  function updateStatusDots(summary) {
    setStatus(dom.dotCore, summary.runtimeOk, summary.runtimeOk ? "ONLINE" : "OFFLINE");
    setStatus(dom.dotGuard, state.lastRuntimePulse?.guard_running ?? false, (state.lastRuntimePulse?.guard_running ?? false) ? "ACTIVE" : "INACTIVE");
    setStatus(dom.dotHttp, true, "CONNECTED");
    setStatus(dom.dotOllama, state.lastRuntimePulse?.ollama_api_up ?? false, (state.lastRuntimePulse?.ollama_api_up ?? false) ? "READY" : "OFFLINE");
  }

  function updateFocusPanel(summary) {
    if (dom.focusTask) dom.focusTask.textContent = summary.queueActionable > 0 ? "Active repair queue" : "Monitoring conversation";
    if (dom.focusSystem) dom.focusSystem.textContent = summary.runtimeOk ? "All systems nominal" : "Runtime recovering";
    if (dom.focusMemory) dom.focusMemory.textContent = state.lastRuntimePulse?.memory_enabled ? "Retrieval active" : "Memory off";
    if (dom.focusContinuity) dom.focusContinuity.textContent = state.sessionId ? "Maintaining session" : "No active session";
    if (dom.focusVoice) dom.focusVoice.textContent = state.voiceEnabled ? "Active" : "Ready";
  }

  function appendEvidence(text) {
    if (!dom.evidenceFeed) return;
    const entry = document.createElement("div");
    entry.className = "evidence-entry";
    entry.innerHTML = '<span class="evidence-text">' + text + '</span><span class="evidence-time">now</span>';
    dom.evidenceFeed.prepend(entry);
    while (dom.evidenceFeed.children.length > 8) {
      dom.evidenceFeed.lastChild.remove();
    }
  }

  function syncHeroInputs() {
    const parts = ["Text"];
    if (state.stagedItems.length) parts.push(`${state.stagedItems.length} staged`);
    else if (state.recentHandoff.length) parts.push("recent context");
    if (state.cameraLive) parts.push("camera");
    if (state.listenMode) parts.push("listen");
    else if (state.recognitionActive) parts.push("mic");
    if (state.voiceEnabled) parts.push("voice");
    if (dom.heroInputs) {
      dom.heroInputs.textContent = parts.join(" + ");
    }
  }

  function syncPresence() {
    const mood = moodProfiles[state.moodMode] || moodProfiles.calm;
    setChip(dom.presenceThinking, state.thinking ? "Thinking" : "Idle", state.thinking ? "live" : "");
    setChip(dom.presenceListening, state.listenMode ? (state.recognitionActive ? "Listening Live" : "Listen Armed") : (state.recognitionActive ? "Mic Live" : "Listen Off"), state.recognitionActive ? "live" : state.listenMode ? "warn" : "");
    setChip(dom.presenceVoice, state.voiceEnabled ? "Voice On" : "Voice Off", state.voiceEnabled ? "ok" : "");
    setChip(dom.presenceCamera, state.cameraLive ? "Camera On" : "Camera Off", state.cameraLive ? "live" : "");
    setChip(dom.presenceMood, mood.label, mood.chip);
    setChip(dom.presenceUploads, `${state.stagedItems.length} staged`, state.stagedItems.length ? "warn" : "");
    setChip(dom.headerPresenceThinking, state.thinking ? "Thinking" : "Idle", state.thinking ? "live" : "");
    setChip(dom.headerPresenceListening, state.listenMode ? (state.recognitionActive ? "Listening Live" : "Listen Off") : (state.recognitionActive ? "Mic Live" : "Listen Off"), state.recognitionActive ? "live" : state.listenMode ? "warn" : "");
    setChip(dom.headerPresenceVoice, state.voiceEnabled ? "Voice On" : "Voice Off", state.voiceEnabled ? "ok" : "");
    setChip(dom.headerPresenceCamera, state.cameraLive ? "Camera On" : "Camera Off", state.cameraLive ? "live" : "");
    setChip(dom.headerPresenceMood, mood.label, mood.chip);
    if (dom.heroState) {
      if (state.uploading) {
        dom.heroState.textContent = "Uploading";
      } else if (state.thinking) {
        dom.heroState.textContent = "Responding";
      } else if (state.listenMode) {
        dom.heroState.textContent = "Listening";
      } else {
        dom.heroState.textContent = "Ready";
      }
    }
    syncHeroInputs();
    syncSessionLabels();
    syncButtons();
    syncSensingDock();
  }

  function hasImmediateLocalFocus() {
    return Boolean(
      state.thinking ||
      state.uploading ||
      state.listenMode ||
      state.recognitionActive ||
      state.cameraLive ||
      state.stagedItems.length,
    );
  }

  function setMood(mode, reason = "") {
    const profile = moodProfiles[mode] || moodProfiles.calm;
    state.moodMode = mode in moodProfiles ? mode : "calm";
    state.moodReason = String(reason || profile.note || "").trim() || profile.note;
    const root = document.documentElement;
    root.style.setProperty("--mood-primary-rgb", profile.primary);
    root.style.setProperty("--mood-secondary-rgb", profile.secondary);
    root.style.setProperty("--mood-tertiary-rgb", profile.tertiary);
    syncPresence();
  }

  function inferMoodFromText(text, fallback = "focus") {
    const normalized = ` ${String(text || "").toLowerCase()} `;
    if (!normalized.trim()) return fallback;
    if (
      normalized.includes("can't ") ||
      normalized.includes("cannot ") ||
      normalized.includes("failed") ||
      normalized.includes("error") ||
      normalized.includes("unavailable") ||
      normalized.includes("clarify") ||
      normalized.includes("blocked") ||
      normalized.includes("under pressure")
    ) {
      return "strain";
    }
    if (
      normalized.includes("multiple") ||
      normalized.includes("tradeoff") ||
      normalized.includes("paths") ||
      normalized.includes("guided") ||
      normalized.includes("direct") ||
      normalized.includes("distinct") ||
      normalized.includes("fulfillment")
    ) {
      return "synthesis";
    }
    if (
      normalized.includes("read") ||
      normalized.includes("review") ||
      normalized.includes("inspect") ||
      normalized.includes("analy") ||
      normalized.includes("summar") ||
      normalized.includes("extract") ||
      normalized.includes("image") ||
      normalized.includes("camera") ||
      normalized.includes("file")
    ) {
      return "focus";
    }
    return fallback;
  }

  function syncButtons() {
    if (dom.btnVoice) {
      dom.btnVoice.classList.toggle("live", state.voiceEnabled);
    }
    if (dom.btnMic) {
      dom.btnMic.disabled = !SpeechRecognitionCtor;
      dom.btnMic.classList.toggle("live", !state.listenMode && state.recognitionActive);
    }
    if (dom.btnListen) {
      dom.btnListen.disabled = !SpeechRecognitionCtor;
      dom.btnListen.classList.toggle("live", state.listenMode);
    }
    if (dom.btnCamera) {
      dom.btnCamera.classList.toggle("live", state.cameraLive);
      dom.btnCamera.textContent = state.cameraLive ? "Camera On" : "Camera";
    }
    if (dom.btnCapture) {
      dom.btnCapture.disabled = !state.cameraLive || state.uploading;
    }
    if (dom.btnSend) {
      dom.btnSend.disabled = state.thinking || state.uploading;
    }
  }

  function syncSensingDock() {
    const dock = document.getElementById("sensingDock");
    if (!dock) return;
    const hasStage = state.stagedItems.length > 0 || state.recentHandoff.length > 0;
    const show = Boolean(state.cameraLive || state.recognitionActive || hasStage);
    dock.hidden = !show;
    if (dom.transcriptBox) {
      dom.transcriptBox.hidden = !state.recognitionActive && !(dom.transcriptBox.textContent || "").trim();
    }
    if (dom.btnCapture) {
      dom.btnCapture.hidden = !state.cameraLive;
    }
  }

  function setTranscript(text, live = false) {
    if (!dom.transcriptBox) return;
    const value = String(text || "").trim();
    dom.transcriptBox.textContent = value;
    dom.transcriptBox.hidden = !value;
    dom.transcriptBox.classList.toggle("live", Boolean(live && value));
    syncSensingDock();
  }

  function pushActivity(title, meta = "") {
    if (!dom.activityDetail) return;
    const parts = [String(title || "").trim(), String(meta || "").trim()].filter(Boolean);
    if (!parts.length) return;
    dom.activityDetail.textContent = parts.join(" — ");
  }

  function setActivityDetail(text) {
    if (!dom.activityDetail) return;
    dom.activityDetail.textContent = text;
  }

  function setPulseField(el, text) {
    if (!el) return;
    el.textContent = text;
  }

  function setUserFacingStatus(payload, summary) {
    if (hasImmediateLocalFocus()) return;
    if (summary.queueActionable > 0) {
      setActivityDetail(
        `${summary.queueActionable} repair item${summary.queueActionable === 1 ? "" : "s"} waiting in Nova's background work.`,
      );
      return;
    }
    if (summary.patchReview > 0) {
      setActivityDetail(
        `${summary.patchReview} patch review item${summary.patchReview === 1 ? "" : "s"} still need attention before they become active work.`,
      );
      return;
    }
    if (!summary.searchOk) {
      setActivityDetail("Search is offline right now, so Nova may stay local until that lane returns.");
      return;
    }
    if (!summary.runtimeOk) {
      setActivityDetail("Nova is recovering its runtime and should settle again shortly.");
      return;
    }
    if (summary.maintenanceStatus) {
      setActivityDetail("Nova is healthy and quietly keeping watch in the background.");
      return;
    }
    setActivityDetail("Nova is ready for your next file, question, or signal.");
  }

  function setActivityHeadline(text) {
    if (dom.activityHeadline) {
      dom.activityHeadline.textContent = text;
    }
  }

  function describeMaintenanceMode(value) {
    const normalized = String(value || "").trim().toLowerCase();
    if (!normalized) return "Maintenance mode unknown";
    if (normalized === "guard_scheduled") return "Guard tick scheduled";
    if (normalized === "running") return "Worker loop active";
    if (normalized === "inactive") return "Maintenance inactive";
    return normalized.replace(/_/g, " ");
  }

  function updatePulseHeadline(payload, summary) {
    if (hasImmediateLocalFocus()) return;
    if (summary.queueActionable > 0) {
      setActivityHeadline(`Nova has ${summary.queueActionable} actionable repair item${summary.queueActionable === 1 ? "" : "s"} queued.`);
      setUserFacingStatus(payload, summary);
      return;
    }
    if (summary.patchReview > 0) {
      setActivityHeadline(`Nova is quiet right now, with ${summary.patchReview} patch review item${summary.patchReview === 1 ? "" : "s"} still waiting.`);
      setUserFacingStatus(payload, summary);
      return;
    }
    if (summary.workTreeStatus && summary.workTreeStatus !== "idle" && summary.workTreeStatus !== "complete") {
      setActivityHeadline(`Nova is here. Work tree is ${summary.workTreeStatus.replace(/_/g, " ")}.`);
      setUserFacingStatus(payload, summary);
      return;
    }
    setActivityHeadline("Nova is here.");
    setUserFacingStatus(payload, summary);
  }

  function updateRuntimePulse(payload) {
    const summary = {
      health: Number(payload?.health_score || 0),
      runtimeOk: Boolean(payload?.core_running),
      queueActionable: Number(payload?.queue_actionable_count || 0),
      queueOpen: Number(payload?.queue_open_count || 0),
      patchReview: Number(payload?.patch_review_previews_total || 0),
      searchOk: Boolean(payload?.searxng_ok),
      workTreeStatus: String(payload?.work_tree_status || "").trim().toLowerCase(),
      maintenanceStatus: String(payload?.maintenance_scheduler_status || "").trim(),
    };

    let runtimeText = "Nova runtime state is unknown.";
    if (summary.runtimeOk && summary.health >= 100) {
      runtimeText = "Healthy and online.";
    } else if (summary.runtimeOk) {
      runtimeText = `Online with health ${summary.health || "unknown"}.`;
    } else {
      runtimeText = "Runtime recovery is in progress.";
    }

    let queueText = "Queue clear.";
    if (summary.queueActionable > 0) {
      queueText = `${summary.queueActionable} actionable item${summary.queueActionable === 1 ? "" : "s"} waiting.`;
    } else if (summary.queueOpen > 0) {
      queueText = `${summary.queueOpen} tracked item${summary.queueOpen === 1 ? "" : "s"} with no active repair pressure.`;
    }

    let searchText = summary.searchOk ? "Search online." : "Search offline.";
    const searchNote = String(payload?.searxng_note || "").trim();
    if (searchNote) {
      searchText = `${searchText} ${searchNote}`;
    }

    let taskText = "No active repair pressure.";
    if (summary.queueActionable > 0) {
      taskText = "Generated repair queue is active.";
    } else if (summary.patchReview > 0) {
      taskText = `${summary.patchReview} patch review item${summary.patchReview === 1 ? "" : "s"} still waiting.`;
    } else if (summary.workTreeStatus && summary.workTreeStatus !== "idle" && summary.workTreeStatus !== "complete") {
      taskText = `Work Tree is ${summary.workTreeStatus.replace(/_/g, " ")}.`;
    }

    setPulseField(dom.pulseRuntime, runtimeText);
    setPulseField(dom.pulseQueue, queueText);
      setPulseField(dom.pulseSearch, searchText);
      setPulseField(dom.pulseMaintenance, describeMaintenanceMode(summary.maintenanceStatus));
      setPulseField(dom.pulseTask, taskText);

    updateStatusDots(summary);
    updateFocusPanel(summary);

    if (dom.hudStatus) {
      if (state.thinking) {
        dom.hudStatus.textContent = "THINKING";
      } else if (state.uploading) {
        dom.hudStatus.textContent = "STAGING";
      } else if (state.listenMode) {
        dom.hudStatus.textContent = "LISTENING";
      } else if (summary.runtimeOk && summary.health >= 100) {
        dom.hudStatus.textContent = "OBSERVING";
      } else if (summary.runtimeOk) {
        dom.hudStatus.textContent = "ONLINE";
      } else {
        dom.hudStatus.textContent = "RECOVERING";
      }
    }

    if (!state.thinking && !state.uploading && !state.listenMode && !state.recognitionActive) {
      if (!summary.searchOk) {
        setMood("strain", "search lane offline");
      } else if (summary.queueActionable > 0 || summary.patchReview > 0) {
        setMood("focus", "watching runtime pressure");
      } else if (summary.runtimeOk && summary.health >= 100) {
        setMood("calm", "steady runtime");
      }
    }

    updatePulseHeadline(payload, summary);
    state.lastRuntimePulse = summary;
  }

  function addMessage(kind, text) {
    if (!dom.chat) return;
    const card = document.createElement("div");
    card.className = `chat-card ${kind}`;
    card.textContent = text;
    dom.chat.appendChild(card);
    dom.chat.scrollTop = dom.chat.scrollHeight;
    if (kind === "assistant") {
      startReplyPulse(text, card);
      speakAssistant(text);
    }
  }

  function clearReplyPulseTimers() {
    state.replyPulseTimers.forEach((timer) => window.clearTimeout(timer));
    state.replyPulseTimers = [];
    if (state.replyPulseFadeTimer) {
      window.clearTimeout(state.replyPulseFadeTimer);
      state.replyPulseFadeTimer = null;
    }
  }

  function setReplyPulseVisual(strength, step, token = "", card = null) {
    const normalized = Math.max(0, Math.min(1, Number(strength || 0)));
    const root = document.documentElement;
    const x = 30 + ((step * 13) % 44);
    const y = 24 + ((step * 9) % 34);
    const warm = /[!?]/.test(token) || step % 4 === 2;
    root.style.setProperty("--reply-pulse-strength", normalized.toFixed(3));
    root.style.setProperty("--reply-pulse-x", `${x}%`);
    root.style.setProperty("--reply-pulse-y", `${y}%`);
    root.style.setProperty("--pulse-rgb", warm ? "255, 200, 106" : "87, 211, 200");
    document.body.classList.add("reply-pulsing");
    if (card) {
      card.classList.add("is-speaking");
    }
    if (state.replyPulseFadeTimer) {
      window.clearTimeout(state.replyPulseFadeTimer);
    }
    state.replyPulseFadeTimer = window.setTimeout(() => {
      root.style.setProperty("--reply-pulse-strength", "0");
      document.body.classList.remove("reply-pulsing");
      card?.classList.remove("is-speaking");
      state.replyPulseFadeTimer = null;
    }, 210);
  }

  function startReplyPulse(text, card = null) {
    clearReplyPulseTimers();
    const tokens = String(text || "").trim().split(/\s+/).filter(Boolean).slice(0, 44);
    if (!tokens.length) return;
    let cursor = 0;
    tokens.forEach((token, index) => {
      const emphasis = /[!?]/.test(token) ? 0.98 : /[,:;]/.test(token) ? 0.8 : 0.62 + Math.min(token.length, 10) * 0.025;
      state.replyPulseTimers.push(
        window.setTimeout(() => {
          setReplyPulseVisual(emphasis, index, token, card);
        }, cursor),
      );
      cursor += 88 + Math.min(token.length * 16, 150) + (/[.,!?;:]/.test(token) ? 55 : 0);
    });
    state.replyPulseTimers.push(
      window.setTimeout(() => {
        if (card) {
          card.classList.remove("is-speaking");
        }
        document.documentElement.style.setProperty("--reply-pulse-strength", "0");
        document.body.classList.remove("reply-pulsing");
      }, cursor + 260),
    );
  }

  function renderStagedItems() {
    if (!dom.stagedList) return;
    dom.stagedList.innerHTML = "";
    if (!state.stagedItems.length && !state.recentHandoff.length) {
      syncSensingDock();
      syncPresence();
      return;
    }
    if (state.stagedItems.length) {
      state.stagedItems.forEach((item) => {
        const entry = document.createElement("li");
        const title = document.createElement("strong");
        title.className = "staged-item-title";
        title.textContent = item.original_name || item.name || "Staged item";
        entry.appendChild(title);

        const meta = document.createElement("div");
        meta.className = "staged-item-meta";
        const bits = ["Staged for next turn"];
        if (item.source) bits.push(item.source);
        if (item.mime) bits.push(item.mime);
        if (item.bytes) bits.push(humanBytes(item.bytes));
        if (item.path) bits.push(item.path);
        meta.textContent = bits.join(" | ");
        entry.appendChild(meta);
        dom.stagedList.appendChild(entry);
      });
      syncPresence();
      return;
    }

    state.recentHandoff.forEach((item) => {
      const entry = document.createElement("li");
      const title = document.createElement("strong");
      title.className = "staged-item-title";
      title.textContent = item.original_name || item.name || "Recent item";
      entry.appendChild(title);

      const meta = document.createElement("div");
      meta.className = "staged-item-meta";
      const bits = ["Last handed to Nova"];
      if (item.source) bits.push(item.source);
      if (item.mime) bits.push(item.mime);
      if (item.bytes) bits.push(humanBytes(item.bytes));
      if (item.path) bits.push(item.path);
      meta.textContent = bits.join(" | ");
      entry.appendChild(meta);
      dom.stagedList.appendChild(entry);
    });
    syncSensingDock();
    syncPresence();
  }

  function speakAssistant(text) {
    if (!state.voiceEnabled || !window.speechSynthesis) return;
    const spoken = String(text || "").trim();
    if (!spoken) return;
    try {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(spoken);
      utterance.rate = 1;
      utterance.pitch = 1;
      window.speechSynthesis.speak(utterance);
    } catch (_) {
      // Keep the panel usable even if speech APIs are flaky.
    }
  }

  async function ensureChatLogin(forcePrompt = false) {
    if (!state.chatLoginEnabled && !forcePrompt) return true;
    let username = (localStorage.getItem("nova_chat_user") || state.userId || "").trim();
    if (!username || forcePrompt) {
      username = (window.prompt("Nova username", username || state.userId || "") || "").trim();
    }
    if (!username) return false;
    const password = window.prompt("Nova password", "");
    if (password === null) return false;
    const response = await fetch(config.chatLoginUrl, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({username, password}),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || "login_failed");
    }
    state.userId = String(payload.user_id || username).trim() || username;
    localStorage.setItem("nova_chat_user", state.userId);
    localStorage.setItem("nova_user_id", state.userId);
    syncSessionLabels();
    return true;
  }

  async function chatFetch(url, options = {}) {
    const timeoutMs = Number(options._timeoutMs || 0) || 0;
    const attempt = async () => {
      const headers = Object.assign({}, options.headers || {});
      if (state.userId) headers["X-Nova-User-Id"] = state.userId;
      const fetchOptions = Object.assign({}, options, {headers});
      delete fetchOptions._timeoutMs;
      if (timeoutMs > 0) {
        const controller = new AbortController();
        const timer = window.setTimeout(() => controller.abort(), timeoutMs);
        try {
          const r = await fetch(url, Object.assign({}, fetchOptions, {signal: controller.signal}));
          window.clearTimeout(timer);
          return r;
        } catch (err) {
          window.clearTimeout(timer);
          throw err;
        }
      }
      return fetch(url, fetchOptions);
    };

    let response = await attempt();
    if (response.status !== 403) return response;

    let payload = null;
    try {
      payload = await response.clone().json();
    } catch (_) {
      return response;
    }
    if (!payload || payload.error !== "chat_login_required") return response;

    const ok = await ensureChatLogin(true).catch((error) => {
      addMessage("system", `Login failed: ${error.message}`);
      return false;
    });
    if (!ok) return response;
    return attempt();
  }

  async function checkHealth() {
    try {
      const response = await fetch(config.healthUrl);
      const payload = await response.json();
      state.chatLoginEnabled = Boolean(payload.chat_login_enabled);
      if (payload.ollama_api_up) {
        appendEvidence("Ollama online");
        setChip(dom.presenceHealth, "Ready", "ok");
        setChip(dom.headerPresenceHealth, "Ready", "ok");
        state.lastRuntimePulse = state.lastRuntimePulse || {};
        state.lastRuntimePulse.ollama_api_up = true;
        state.lastRuntimePulse.memory_enabled = payload.memory_enabled;
        if (!state.thinking && !state.uploading && !state.listenMode && !state.recognitionActive && !state.cameraLive && !state.stagedItems.length && !state.recentHandoff.length) {
          setMood("calm", "steady runtime");
        }
      } else {
        setChip(dom.presenceHealth, "Offline", "danger");
        setChip(dom.headerPresenceHealth, "Offline", "danger");
        setMood("strain", "model unavailable");
      }
    } catch (_) {
      setChip(dom.presenceHealth, "Health check failed", "danger");
      setChip(dom.headerPresenceHealth, "Health check failed", "danger");
      setMood("strain", "health check failed");
    }
  }

  function applyNovaOutreach(payload) {
    const outreach = payload && payload.nova_outreach;
    if (!outreach) return;
    const kind = String(outreach.kind || "");
    const text = String(outreach.text || "").trim();
    if (kind !== "attention" || !text) return;
    const oid = String(outreach.id || "");
    if (oid && oid === state.lastOutreachId) return;
    state.lastOutreachId = oid;
    addMessage("assistant", text);
    setActivityHeadline(text);
    setMood("focus", "runtime pressure");
  }

  async function refreshRuntimePulse() {
    if (!config.controlStatusUrl) return;
    try {
      const response = await fetch(config.controlStatusUrl);
      const payload = await response.json();
      updateRuntimePulse(payload || {});
      applyNovaOutreach(payload || {});
    } catch (_) {
      setPulseField(dom.pulseRuntime, "Unable to reach runtime pulse.");
      setPulseField(dom.pulseQueue, "Queue state unavailable.");
      setPulseField(dom.pulseSearch, "Search state unavailable.");
      setPulseField(dom.pulseMaintenance, "Maintenance state unavailable.");
      setPulseField(dom.pulseTask, "Current focus unavailable.");
      if (!hasImmediateLocalFocus()) {
        setActivityHeadline("Nova is here, but the runtime pulse could not be refreshed.");
        setActivityDetail("The front door is still open, but the background pulse is temporarily unavailable.");
      }
    }
  }

  async function uploadItems(items) {
    if (!items.length) return;
    state.uploading = true;
    setMood("sensing", "staging local context");
    setActivityHeadline("Nova is staging local context for the next turn.");
    syncPresence();
    try {
      const response = await chatFetch(config.uploadUrl, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          session_id: state.sessionId,
          user_id: state.userId,
          items,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "upload_failed");
      }
      if (payload.session_id) {
        state.sessionId = String(payload.session_id);
        localStorage.setItem("nova_session_id", state.sessionId);
      }
      const stored = Array.isArray(payload.items) ? payload.items : [];
      state.stagedItems = state.stagedItems.concat(stored);
      state.recentHandoff = [];
      renderStagedItems();
      pushActivity("Staged local context", `${stored.length} item(s) ready for the next turn.`);
      setActivityHeadline("Local files are staged and waiting for Nova.");
      setMood("focus", stored.length > 1 ? "holding a working set" : "holding local context");
    } catch (error) {
      addMessage("system", `Upload error: ${error.message}`);
      pushActivity("Upload failed", error.message);
      setActivityHeadline("Nova hit an upload problem. You can try again.");
      setMood("strain", "upload problem");
    } finally {
      state.uploading = false;
      syncPresence();
    }
  }

  function fileToBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const value = String(reader.result || "");
        const comma = value.indexOf(",");
        resolve(comma >= 0 ? value.slice(comma + 1) : value);
      };
      reader.onerror = () => reject(reader.error || new Error("file_read_failed"));
      reader.readAsDataURL(file);
    });
  }

  async function stageFiles(fileList) {
    const files = Array.from(fileList || []).slice(0, 6);
    if (!files.length) return;
    const items = [];
    for (const file of files) {
      try {
        const contentB64 = await fileToBase64(file);
        items.push({
          name: file.name,
          mime: file.type || "application/octet-stream",
          source: "upload",
          content_b64: contentB64,
        });
      } catch (_) {
        pushActivity("Skipped file", file.name);
      }
    }
    await uploadItems(items);
  }

  async function sendMessage(message) {
    const raw = String(message || "").trim();
    const hasStaged = state.stagedItems.length > 0;
    if (!raw && !hasStaged) return;

    const outgoing = raw || "Please inspect the staged context for this turn.";
    const userEcho = raw || `[Shared ${state.stagedItems.length} staged item(s)]`;
    addMessage("user", userEcho);
    appendEvidence("Turn sent" + (hasStaged ? " with " + state.stagedItems.length + " attachments" : ""));
    state.thinking = true;
    setMood(
      hasStaged ? "focus" : inferMoodFromText(outgoing, "focus"),
      hasStaged ? "working from handed context" : "processing the current turn",
    );
    setActivityHeadline("Nova is thinking through the current turn.");
    pushActivity("Turn sent", hasStaged ? `${state.stagedItems.length} staged item(s) included.` : "Conversation only.");
    syncPresence();

    // Show "still working" after 8s so the user knows Nova is alive, not frozen.
    const stillWorkingTimer = window.setTimeout(() => {
      if (state.thinking) {
        setActivityHeadline("Nova is still working — this one is taking a bit longer than usual.");
        setMood("synthesis", "deep processing");
      }
    }, 3000);

    try {
      const response = await chatFetch(config.chatUrl, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          message: outgoing,
          attachments: state.stagedItems,
          session_id: state.sessionId,
          user_id: state.userId,
        }),
        _timeoutMs: 120000,
      });
      const payload = await response.json().catch(() => ({}));
      if (payload.session_id) {
        state.sessionId = String(payload.session_id);
        localStorage.setItem("nova_session_id", state.sessionId);
      }
      const reply = payload.reply || (payload.error ? `Error: ${payload.error}` : "No reply");
      addMessage("assistant", String(reply));
      appendEvidence(reply.substring(0, 60) + (reply.length > 60 ? "..." : ""));
      if (response.ok && payload.reply) {
        const replyMood = inferMoodFromText(reply, hasStaged ? "focus" : "calm");
        const replyReason =
          replyMood === "synthesis"
            ? "weighing multiple paths"
            : replyMood === "strain"
              ? "hitting resistance"
              : replyMood === "focus"
                ? "working the active task"
                : "steady runtime";
        setMood(replyMood, replyReason);
        if (hasStaged) {
          state.recentHandoff = state.stagedItems.map((item) => Object.assign({}, item));
          pushActivity("Staged items handed to Nova", `${state.stagedItems.length} item(s) moved into the live turn.`);
          setActivityHeadline("Nova is now working from the local context you just handed over.");
        }
        state.stagedItems = [];
        renderStagedItems();
        if (!hasStaged) {
          setActivityHeadline("Nova responded. The session is ready for the next move.");
        }
      } else {
        setActivityHeadline("Nova hit a reply problem. You can keep working from here.");
        setMood("strain", "reply problem");
      }
    } catch (error) {
      const timedOut = error && error.name === "AbortError";
      addMessage("assistant", timedOut
        ? "Nova's reply took too long and the request was cancelled. You can try again."
        : `Network error: ${error.message}`);
      setActivityHeadline(timedOut
        ? "Nova timed out on that turn. The front door is still open."
        : "Nova hit a network problem. The front door stayed open.");
      setMood("strain", timedOut ? "turn timed out" : "network problem");
    } finally {
      window.clearTimeout(stillWorkingTimer);
      state.thinking = false;
      syncPresence();
    }
  }

  function stopCamera() {
    if (state.cameraStream) {
      state.cameraStream.getTracks().forEach((track) => track.stop());
    }
    state.cameraStream = null;
    state.cameraLive = false;
    if (dom.cameraPreview) {
      dom.cameraPreview.srcObject = null;
      dom.cameraPreview.classList.remove("live");
    }
    if (dom.cameraEmpty) {
      dom.cameraEmpty.hidden = false;
    }
    setActivityHeadline("Camera is off. Nova is waiting for the next input.");
    setMood(state.recentHandoff.length ? "focus" : "calm", state.recentHandoff.length ? "holding recent context" : "steady runtime");
    syncPresence();
  }

  async function toggleCamera() {
    if (state.cameraLive) {
      stopCamera();
      pushActivity("Camera stopped", "Live preview was closed.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({video: true, audio: false});
      state.cameraStream = stream;
      state.cameraLive = true;
      if (dom.cameraPreview) {
        dom.cameraPreview.srcObject = stream;
        dom.cameraPreview.classList.add("live");
      }
      if (dom.cameraEmpty) {
        dom.cameraEmpty.hidden = true;
      }
      setActivityHeadline("Camera is live. Capture a frame when you want Nova to inspect it.");
      pushActivity("Camera live", "Visual input is available in LEAH.");
      setMood("sensing", "watching visual input");
      syncPresence();
    } catch (error) {
      addMessage("system", `Camera error: ${error.message}`);
      pushActivity("Camera unavailable", error.message);
      setActivityHeadline("Camera access was denied or unavailable.");
      setMood("strain", "camera unavailable");
      syncPresence();
    }
  }

  async function captureFrame() {
    if (!state.cameraLive || !dom.cameraPreview || !dom.cameraCanvas) return;
    const width = dom.cameraPreview.videoWidth || 1280;
    const height = dom.cameraPreview.videoHeight || 720;
    dom.cameraCanvas.width = width;
    dom.cameraCanvas.height = height;
    const ctx = dom.cameraCanvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(dom.cameraPreview, 0, 0, width, height);
    const dataUrl = dom.cameraCanvas.toDataURL("image/png");
    const comma = dataUrl.indexOf(",");
    const contentB64 = comma >= 0 ? dataUrl.slice(comma + 1) : dataUrl;
    await uploadItems([
      {
        name: `camera_capture_${Date.now()}.png`,
        mime: "image/png",
        source: "camera",
        content_b64: contentB64,
      },
    ]);
    pushActivity("Camera frame staged", "A still image is ready for the next turn.");
    setMood("focus", "holding a visual frame");
  }

  function initSpeechRecognition() {
    if (!SpeechRecognitionCtor || state.recognition) return;
    const recognition = new SpeechRecognitionCtor();
    recognition.lang = "en-US";
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      state.recognitionActive = true;
      setActivityHeadline(state.listenMode ? "Nova is listening hands-free." : "Nova is listening for a single turn.");
      setMood("sensing", state.listenMode ? "hands-free listening" : "listening for a turn");
      syncPresence();
    };

    recognition.onresult = (event) => {
      const transcript = Array.from(event.results || [])
        .map((result) => String(result?.[0]?.transcript || ""))
        .join(" ")
        .trim();
      if (!transcript) return;
      setTranscript(transcript, true);
      if (event.results && event.results[event.results.length - 1] && event.results[event.results.length - 1].isFinal) {
        if (state.listenMode) {
          void sendMessage(transcript);
        } else if (dom.input) {
          dom.input.value = transcript;
          if (typeof dom.form?.requestSubmit === "function") {
            dom.form.requestSubmit();
          } else {
            dom.form?.dispatchEvent(new Event("submit", {cancelable: true}));
          }
        }
      }
    };

    recognition.onerror = (event) => {
      state.recognitionActive = false;
      const error = String(event?.error || "speech_error");
      setTranscript(`Voice input error: ${error}`, false);
      if (state.listenMode && error !== "not-allowed" && error !== "service-not-allowed") {
        state.recognitionRestart = true;
      } else {
        state.listenMode = false;
      }
      setMood("strain", "speech input trouble");
      syncPresence();
    };

    recognition.onend = () => {
      state.recognitionActive = false;
      syncPresence();
      if (state.listenMode || state.recognitionRestart) {
        state.recognitionRestart = false;
        window.setTimeout(() => {
          if (!state.listenMode || !state.recognition || state.recognitionActive) return;
          try {
            state.recognitionMode = "listen";
            state.recognition.start();
          } catch (_) {
            state.listenMode = false;
            syncPresence();
          }
        }, 300);
      }
    };

    state.recognition = recognition;
  }

  function stopListening() {
    state.listenMode = false;
    state.recognitionRestart = false;
    if (state.recognition && state.recognitionActive) {
      try {
        state.recognition.stop();
      } catch (_) {
        // Ignore stop errors from browsers with flaky speech APIs.
      }
    }
    setTranscript("", false);
    setActivityHeadline("Listen mode is off.");
    setMood(state.recentHandoff.length ? "focus" : "calm", state.recentHandoff.length ? "holding recent context" : "steady runtime");
    syncPresence();
  }

  function startManualMic() {
    if (!SpeechRecognitionCtor) {
      addMessage("system", "Speech recognition is not available in this browser.");
      return;
    }
    initSpeechRecognition();
    if (!state.recognition) return;
    state.listenMode = false;
    state.recognitionMode = "manual";
    setTranscript("Listening for one spoken turn...", true);
    try {
      state.recognition.start();
    } catch (_) {
      syncPresence();
    }
  }

  function toggleListenMode() {
    if (!SpeechRecognitionCtor) {
      addMessage("system", "Listen mode is not available in this browser.");
      return;
    }
    initSpeechRecognition();
    if (!state.recognition) return;
    if (state.listenMode) {
      stopListening();
      pushActivity("Listen mode stopped", "Hands-free capture is off.");
      return;
    }
    state.listenMode = true;
    state.recognitionMode = "listen";
    setTranscript("Hands-free listening is armed.", true);
    pushActivity("Listen mode armed", "Nova will send recognized speech as turns.");
    setMood("sensing", "hands-free listening");
    try {
      state.recognition.start();
    } catch (_) {
      state.listenMode = false;
    }
    syncPresence();
  }

  async function loadHistory() {
    if (!state.sessionId) return;
    try {
      const response = await chatFetch(
        `${config.chatHistoryUrl}?session_id=${encodeURIComponent(state.sessionId)}&user_id=${encodeURIComponent(state.userId)}`,
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.ok || !Array.isArray(payload.turns) || payload.turns.length === 0) return;
      payload.turns.forEach((turn) => {
        if (!turn || !turn.role || !turn.text) return;
        addMessage(turn.role === "user" ? "user" : "assistant", String(turn.text));
      });
      const last = payload.turns[payload.turns.length - 1];
      state.pendingResume = Boolean(last && String(last.role || "").toLowerCase() === "user");
      state.historyLoaded = true;
      setActivityHeadline("Nova reopened the last lived session.");
    } catch (_) {
      // Keep startup resilient.
    }
  }

  async function resumePendingTurn() {
    if (!state.sessionId || !state.pendingResume) return;
    try {
      const response = await chatFetch(config.chatResumeUrl, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({session_id: state.sessionId, user_id: state.userId}),
      });
      const payload = await response.json().catch(() => ({}));
      if (response.ok && payload.ok && payload.resumed && payload.reply) {
        addMessage("assistant", String(payload.reply));
        setActivityHeadline("Nova finished the pending turn from your last session.");
      }
    } catch (_) {
      // Resume is helpful, not required.
    } finally {
      state.pendingResume = false;
    }
  }

  function resetSession() {
    stopListening();
    stopCamera();
    state.sessionId = "";
    state.stagedItems = [];
    state.recentHandoff = [];
    state.historyLoaded = false;
    state.pendingResume = false;
    localStorage.removeItem("nova_session_id");
    if (dom.chat) dom.chat.innerHTML = "";
    renderStagedItems();
    addMessage("system", "Started a fresh LEAH session. Nova is ready.");
    setActivityHeadline("Fresh session opened. Bring Nova the next thing that matters.");
    pushActivity("New session", "Conversation state was reset.");
    setMood("calm", "fresh session");
    syncPresence();
    dom.input?.focus();
  }

  function bindEvents() {
    dom.form?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const message = dom.input ? dom.input.value.trim() : "";
      if (!message && !state.stagedItems.length) return;
      if (dom.input) dom.input.value = "";
      await sendMessage(message);
    });

    dom.btnUpload?.addEventListener("click", () => dom.fileInput?.click());
    dom.fileInput?.addEventListener("change", async () => {
      await stageFiles(dom.fileInput?.files || []);
      if (dom.fileInput) dom.fileInput.value = "";
    });

    // File button opens the picker. Drop-zone is drag-only so typing is not stolen.
    dom.dropZone?.addEventListener("dragover", (event) => {
      event.preventDefault();
      dom.dropZone?.classList.add("dragging");
    });
    dom.dropZone?.addEventListener("dragleave", () => {
      dom.dropZone?.classList.remove("dragging");
    });
    dom.dropZone?.addEventListener("drop", async (event) => {
      event.preventDefault();
      dom.dropZone?.classList.remove("dragging");
      await stageFiles(event.dataTransfer?.files || []);
    });

    dom.btnVoice?.addEventListener("click", () => {
      state.voiceEnabled = !state.voiceEnabled;
      localStorage.setItem("leah_voice_output", state.voiceEnabled ? "on" : "off");
      if (!state.voiceEnabled && window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
      pushActivity("Voice output", state.voiceEnabled ? "Browser speech is on." : "Browser speech is off.");
      setActivityHeadline(state.voiceEnabled ? "Nova can speak back through this browser." : "Voice output is off.");
      syncPresence();
    });

    dom.btnMic?.addEventListener("click", () => {
      if (state.recognitionActive && !state.listenMode && state.recognition) {
        try {
          state.recognition.stop();
        } catch (_) {
          // Ignore.
        }
        return;
      }
      startManualMic();
    });

    dom.btnListen?.addEventListener("click", () => {
      toggleListenMode();
    });

    dom.btnCamera?.addEventListener("click", () => {
      void toggleCamera();
    });

    dom.btnCapture?.addEventListener("click", () => {
      void captureFrame();
    });

    dom.btnNewSession?.addEventListener("click", () => {
      resetSession();
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "/" && document.activeElement?.tagName !== "TEXTAREA" && document.activeElement?.tagName !== "INPUT") {
        event.preventDefault();
        dom.input?.focus();
      }
      if (event.key === "Escape" && document.activeElement === dom.input) {
        dom.input.blur();
      }
      if (event.ctrlKey && event.shiftKey && event.key === "N") {
        event.preventDefault();
        resetSession();
      }
    });
  }

  async function boot() {
    state.userId = (qs.get("uid") || localStorage.getItem("nova_user_id") || makeUserId()).trim();
    state.sessionId = (qs.get("sid") || localStorage.getItem("nova_session_id") || "").trim();
    state.voiceEnabled = localStorage.getItem("leah_voice_output") === "on";
    localStorage.setItem("nova_user_id", state.userId);
    if (state.sessionId) {
      localStorage.setItem("nova_session_id", state.sessionId);
    }

    bindEvents();
    renderStagedItems();
    setMood("calm", "steady runtime");
    syncPresence();
    appendEvidence("System initialized");
    await loadHistory();
    await resumePendingTurn();
    try {
      const response = await fetch(config.controlStatusUrl);
      const payload = await response.json();
      updateRuntimePulse(payload || {});
      applyNovaOutreach(payload || {});
    } catch (_) {
      if (!state.historyLoaded) {
        setActivityHeadline("Nova is here.");
      }
    }
    void checkHealth();
    state.healthTimer = window.setInterval(() => {
      void checkHealth();
      void refreshRuntimePulse();
    }, 25000);
  }

  boot().catch((error) => {
    addMessage("system", `LEAH startup error: ${error.message}`);
    setActivityHeadline("LEAH hit a startup error, but the front door is still open.");
  });
})();
