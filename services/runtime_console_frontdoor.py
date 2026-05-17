from __future__ import annotations


class RuntimeConsoleFrontdoorService:
    """Own the legacy NYO runtime console surface outside the HTTP transport shell."""

    @staticmethod
    def render_html() -> str:
        return RUNTIME_CONSOLE_HTML


RUNTIME_CONSOLE_HTML = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>NYO Runtime Console</title>
  <style>
    :root {
      --bg: #f7f4ec;
      --panel: #fffdf8;
      --ink: #1f1d19;
      --muted: #70695f;
      --accent: #0d6b5f;
      --accent-2: #d9972d;
      --line: #e4dbc8;
    }
    body { margin: 0; font-family: "Segoe UI", Tahoma, sans-serif; color: var(--ink); background: radial-gradient(circle at top left, #fff8e7, var(--bg)); }
    .wrap { max-width: 900px; margin: 24px auto; padding: 0 16px; }
    .card { background: var(--panel); border: 1px solid var(--line); border-radius: 14px; box-shadow: 0 8px 30px rgba(0,0,0,0.06); overflow: hidden; }
    .head { padding: 14px 16px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--line); }
    .title { font-weight: 700; letter-spacing: 0.02em; }
    .status { font-size: 12px; color: var(--muted); }
    .head-right { display: flex; align-items: center; gap: 10px; }
    .btn-mini { padding: 6px 10px; font-size: 12px; }
    .btn-mini.alt { background: linear-gradient(135deg, #846540, #a47d4f); }
    .btn-mini.muted { background: linear-gradient(135deg, #8d8a84, #6d6a65); }
    .btn-link { color: var(--accent); font-size: 12px; font-weight: 600; text-decoration: none; }
    #chat { height: 58vh; overflow: auto; padding: 14px; display: grid; gap: 10px; }
    .msg { padding: 10px 12px; border-radius: 10px; max-width: 85%; white-space: pre-wrap; line-height: 1.35; }
    .u { margin-left: auto; background: #d7efe9; border: 1px solid #a9d9ce; }
    .a { margin-right: auto; background: #fff4db; border: 1px solid #f0d59f; }
    form { display: grid; grid-template-columns: 1fr auto; gap: 10px; padding: 12px; border-top: 1px solid var(--line); }
    input { font-size: 15px; padding: 10px 12px; border-radius: 9px; border: 1px solid #cabfae; outline: none; }
    button { background: linear-gradient(135deg, var(--accent), #0f8f7d); color: #fff; border: 0; border-radius: 9px; padding: 10px 14px; cursor: pointer; font-weight: 600; }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"card\">
            <div class=\"head\">
                <div class=\"title\">NYO Runtime Console</div>
                <div class=\"head-right\">
                    <div id=\"status\" class=\"status\">Checking health...</div>
                    <button id="btnToggleAudio" type="button" class="btn-mini alt">Voice Off</button>
                    <button id="btnMic" type="button" class="btn-mini muted">Mic Unavailable</button>
                    <a class="btn-link" href="/control">Open Operator Console</a>
                    <button id=\"btnNewSession\" type=\"button\" class=\"btn-mini\">New Session</button>
                </div>
            </div>
      <div id=\"chat\"></div>
      <form id=\"f\">
        <input id=\"m\" placeholder=\"Enter a request for the NYO runtime...\" autocomplete=\"off\" />
        <button type=\"submit\">Send</button>
      </form>
    </div>
  </div>
<script>
  const chat = document.getElementById('chat');
  const form = document.getElementById('f');
  const input = document.getElementById('m');
    const statusEl = document.getElementById('status');
        const btnToggleAudio = document.getElementById('btnToggleAudio');
        const btnMic = document.getElementById('btnMic');
    const btnNewSession = document.getElementById('btnNewSession');
    const qs = new URLSearchParams(window.location.search || '');
        const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition || null;
    const sidParam = (qs.get('sid') || '').trim();
    const uidParam = (qs.get('uid') || '').trim();
    const makeUserId = () => {
        if (window.crypto && typeof window.crypto.randomUUID === 'function') {
            return 'web-' + window.crypto.randomUUID().replace(/-/g, '').slice(0, 24);
        }
        return 'web-' + Math.random().toString(16).slice(2) + Date.now().toString(16);
    };
    let userId = uidParam || localStorage.getItem('nova_user_id') || makeUserId();
    localStorage.setItem('nova_user_id', userId);
    let chatLoginEnabled = false;
    let sessionId = sidParam || localStorage.getItem('nova_session_id') || '';
    let voiceOutputEnabled = localStorage.getItem('nova_voice_output') === 'on';
    let lastOperatorOutboxId = localStorage.getItem('nova_operator_outbox_last_id') || '';
    let recognition = null;
    let recognitionActive = false;
    if (sidParam) {
        localStorage.setItem('nova_session_id', sessionId);
    }
        let historyLoaded = false;
        let pendingResumeNeeded = false;

    function syncAudioButton() {
        if (!btnToggleAudio) return;
        btnToggleAudio.textContent = voiceOutputEnabled ? 'Voice On' : 'Voice Off';
        btnToggleAudio.classList.toggle('alt', voiceOutputEnabled);
        btnToggleAudio.classList.toggle('muted', !voiceOutputEnabled);
    }

    function syncMicButton() {
        if (!btnMic) return;
        if (!SpeechRecognitionCtor) {
            btnMic.textContent = 'Mic Unavailable';
            btnMic.disabled = true;
            return;
        }
        btnMic.disabled = false;
        btnMic.textContent = recognitionActive ? 'Listening...' : 'Mic Ready';
        btnMic.classList.toggle('alt', recognitionActive);
        btnMic.classList.toggle('muted', !recognitionActive);
    }

    function speakAssistant(text) {
        if (!voiceOutputEnabled || !window.speechSynthesis) return;
        const spoken = String(text || '').trim();
        if (!spoken) return;
        try {
            window.speechSynthesis.cancel();
            const utterance = new SpeechSynthesisUtterance(spoken);
            utterance.rate = 1.0;
            utterance.pitch = 1.0;
            window.speechSynthesis.speak(utterance);
        } catch (_) {
            // Keep chat usable if browser speech APIs fail.
        }
    }

  function add(kind, text) {
    const d = document.createElement('div');
    d.className = 'msg ' + kind;
    d.textContent = text;
    chat.appendChild(d);
    chat.scrollTop = chat.scrollHeight;
    if (kind === 'a') {
        speakAssistant(text);
    }
  }

    function handleOperatorOutbox(payload) {
        const events = Array.isArray(payload?.events) ? payload.events : [];
        if (!events.length) return;
        let newest = lastOperatorOutboxId || '';
        events.forEach(event => {
            if (!event || !event.id) return;
            const id = String(event.id);
            if (lastOperatorOutboxId && id <= lastOperatorOutboxId) return;
            const title = String(event.title || '').trim();
            const message = String(event.message || '').trim();
            const rendered = title && message ? `${title}\n${message}` : (message || title);
            if (rendered) {
                add('a', rendered);
            }
            if (!newest || id > newest) {
                newest = id;
            }
        });
        if (newest && newest !== lastOperatorOutboxId) {
            lastOperatorOutboxId = newest;
            localStorage.setItem('nova_operator_outbox_last_id', newest);
        }
    }

    async function sendMessage(message) {
        if (!message) return;
        add('u', message);
        try {
            const r = await chatFetch('/api/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-Nova-User-Id': userId},
                body: JSON.stringify({message, session_id: sessionId, user_id: userId})
            });
            const j = await r.json();
            if (j.session_id) {
                sessionId = j.session_id;
                localStorage.setItem('nova_session_id', sessionId);
            }
            add('a', j.reply || (j.error ? `Error: ${j.error}` : 'No reply'));
        } catch (err) {
            add('a', 'Network error: ' + err.message);
        }
    }

    function initSpeechRecognition() {
        if (!SpeechRecognitionCtor || recognition) return;
        recognition = new SpeechRecognitionCtor();
        recognition.lang = 'en-US';
        recognition.interimResults = false;
        recognition.maxAlternatives = 1;
        recognition.onstart = () => {
            recognitionActive = true;
            syncMicButton();
        };
        recognition.onend = () => {
            recognitionActive = false;
            syncMicButton();
        };
        recognition.onerror = () => {
            recognitionActive = false;
            syncMicButton();
        };
        recognition.onresult = (event) => {
            const transcript = String(event.results?.[0]?.[0]?.transcript || '').trim();
            if (!transcript) return;
            input.value = transcript;
            if (typeof form.requestSubmit === 'function') {
                form.requestSubmit();
            } else {
                form.dispatchEvent(new Event('submit', {cancelable: true}));
            }
        };
    }

    async function ensureChatLogin(forcePrompt = false) {
        if (!chatLoginEnabled && !forcePrompt) return true;
        let username = (localStorage.getItem('nova_chat_user') || userId || '').trim();
        if (!username || forcePrompt) {
            username = (window.prompt('NYO username', username || userId || '') || '').trim();
        }
        if (!username) return false;
        const password = window.prompt('NYO password', '');
        if (password === null) return false;
        try {
            const r = await fetch('/api/chat/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username, password})
            });
            const j = await r.json();
            if (!r.ok || !j.ok) throw new Error(j.error || 'login_failed');
            userId = String(j.user_id || username).trim() || username;
            localStorage.setItem('nova_chat_user', userId);
            localStorage.setItem('nova_user_id', userId);
            return true;
        } catch (err) {
            add('a', 'Login failed: ' + err.message);
            return false;
        }
    }

    async function chatFetch(url, options = {}) {
        const headers = Object.assign({}, options.headers || {});
        if (userId) headers['X-Nova-User-Id'] = userId;
        let response = await fetch(url, Object.assign({}, options, {headers}));
        if (response.status !== 403) return response;

        let payload = null;
        try {
            payload = await response.clone().json();
        } catch (_) {
            return response;
        }
        if (!payload || payload.error !== 'chat_login_required') return response;

        const ok = await ensureChatLogin(true);
        if (!ok) return response;

        const retryHeaders = Object.assign({}, options.headers || {});
        if (userId) retryHeaders['X-Nova-User-Id'] = userId;
        return fetch(url, Object.assign({}, options, {headers: retryHeaders}));
    }

    async function loadHistory() {
        if (!sessionId) return;
        try {
            const r = await chatFetch('/api/chat/history?session_id=' + encodeURIComponent(sessionId) + '&user_id=' + encodeURIComponent(userId));
            const j = await r.json();
            if (!r.ok || !j.ok || !Array.isArray(j.turns)) return;
            if (j.turns.length === 0) return;

            j.turns.forEach(t => {
                if (!t || !t.role || !t.text) return;
                add(t.role === 'user' ? 'u' : 'a', String(t.text));
            });
                        const last = j.turns[j.turns.length - 1];
                        pendingResumeNeeded = Boolean(last && String(last.role || '').toLowerCase() === 'user');
            historyLoaded = true;
        } catch (_) {
            // Keep startup resilient; chat can still operate without history.
        }
    }

    async function resumePendingTurn() {
        if (!sessionId || !pendingResumeNeeded) return;
        try {
            const r = await chatFetch('/api/chat/resume', {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-Nova-User-Id': userId},
                body: JSON.stringify({session_id: sessionId, user_id: userId})
            });
            const j = await r.json();
            if (r.ok && j.ok && j.resumed && j.reply) {
                add('a', String(j.reply));
            }
        } catch (_) {
            // Keep UI responsive even if resume fails.
        } finally {
            pendingResumeNeeded = false;
        }
    }

  async function health() {
    try {
      const r = await fetch('/api/health');
      const j = await r.json();
            chatLoginEnabled = Boolean(j.chat_login_enabled);
      statusEl.textContent = j.ollama_api_up && j.ollama_model_available !== false ? `Healthy | model: ${j.chat_model}` : 'Ollama unavailable';
            handleOperatorOutbox(j.operator_outbox || {});
    } catch (_) {
      statusEl.textContent = 'Health check failed';
    }
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const message = input.value.trim();
    if (!message) return;
    input.value = '';
    await sendMessage(message);
  });

    if (btnToggleAudio) {
        syncAudioButton();
        btnToggleAudio.addEventListener('click', () => {
            voiceOutputEnabled = !voiceOutputEnabled;
            localStorage.setItem('nova_voice_output', voiceOutputEnabled ? 'on' : 'off');
            if (!voiceOutputEnabled && window.speechSynthesis) {
                window.speechSynthesis.cancel();
            }
            syncAudioButton();
            add('a', voiceOutputEnabled ? 'Browser voice output enabled.' : 'Browser voice output disabled.');
        });
    }

    initSpeechRecognition();
    syncMicButton();
    if (btnMic && SpeechRecognitionCtor) {
        btnMic.addEventListener('click', () => {
            if (!recognition) {
                initSpeechRecognition();
            }
            if (!recognition) return;
            if (recognitionActive) {
                recognition.stop();
                return;
            }
            try {
                recognition.start();
            } catch (_) {
                recognitionActive = false;
                syncMicButton();
            }
        });
    }

    if (btnNewSession) {
        btnNewSession.addEventListener('click', () => {
            sessionId = '';
            pendingResumeNeeded = false;
            historyLoaded = false;
            localStorage.removeItem('nova_session_id');
            chat.innerHTML = '';
            add('a', 'Started a new runtime session. Context was reset.');
            input.focus();
        });
    }

    (async () => {
        await loadHistory();
        await resumePendingTurn();
        if (!historyLoaded) {
            add('a', 'NYO runtime console ready. Enter a request when you are ready.');
        }
        health();
        window.setInterval(health, 5000);
    })();
</script>
</body>
</html>
"""


RUNTIME_CONSOLE_FRONTDOOR_SERVICE = RuntimeConsoleFrontdoorService()
