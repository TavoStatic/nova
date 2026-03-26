document.body.classList.add('js-ready');

const keyInput = document.getElementById('key');
const statusKv = document.getElementById('statusKv');
const healthBadge = document.getElementById('healthBadge');
const feedbackBar = document.getElementById('feedbackBar');
const runtimeNoteBar = document.getElementById('runtimeNoteBar');
const policyBox = document.getElementById('policyBox');
const actionBox = document.getElementById('actionBox');
const actionBoxClone = document.getElementById('actionBoxClone');
const guardBox = document.getElementById('guardBox');
const sessionFilterSelect = document.getElementById('sessionFilterSelect');
const sessionSelect = document.getElementById('sessionSelect');
const sessionBox = document.getElementById('sessionBox');
const sessionProbeBox = document.getElementById('sessionProbeBox');
const testRunSelect = document.getElementById('testRunSelect');
const testRunBox = document.getElementById('testRunBox');
const testRunProbeBox = document.getElementById('testRunProbeBox');
const testRunBadges = document.getElementById('testRunBadges');
const testSessionDefinitionSelect = document.getElementById('testSessionDefinitionSelect');
const testRunDriftGrid = document.getElementById('testRunDriftGrid');
const operatorSessionIdInput = document.getElementById('operatorSessionId');
const operatorMacroSelect = document.getElementById('operatorMacroSelect');
const operatorPromptInput = document.getElementById('operatorPromptInput');
const operatorPromptReply = document.getElementById('operatorPromptReply');
const btnOperatorToggleAudio = document.getElementById('btnOperatorToggleAudio');
const btnOperatorMic = document.getElementById('btnOperatorMic');
const backendCommandSelect = document.getElementById('backendCommandSelect');
const backendCommandArgs = document.getElementById('backendCommandArgs');
const backendCommandOutput = document.getElementById('backendCommandOutput');
const memoryScopeSelect = document.getElementById('memoryScope');
const memoryScopeBox = document.getElementById('memoryScopeBox');
const chatUserSelect = document.getElementById('chatUserSelect');
const chatUserNameInput = document.getElementById('chatUserName');
const chatUserPassInput = document.getElementById('chatUserPass');
const chatAuthBox = document.getElementById('chatAuthBox');
const plannerInspector = document.getElementById('plannerInspector');
const ledgerInspector = document.getElementById('ledgerInspector');
const supervisorInspector = document.getElementById('supervisorInspector');
const sessionStateInspector = document.getElementById('sessionStateInspector');
const overrideBadges = document.getElementById('overrideBadges');
const patchStatusBadge = document.getElementById('patchStatusBadge');
const patchStatusNarrative = document.getElementById('patchStatusNarrative');
const patchPreviewSelect = document.getElementById('patchPreviewSelect');
const patchPreviewNote = document.getElementById('patchPreviewNote');
const patchSummaryGrid = document.getElementById('patchSummaryGrid');
const patchPreviewGrid = document.getElementById('patchPreviewGrid');
const patchLogBox = document.getElementById('patchLogBox');
const patchPreviewSummary = document.getElementById('patchPreviewSummary');
const patchPreviewBox = document.getElementById('patchPreviewBox');
const patchActionReadiness = document.getElementById('patchActionReadiness');
const healthSummary = document.getElementById('healthSummary');
const runtimeSummary = document.getElementById('runtimeSummary');
const runtimeRawBox = document.getElementById('runtimeRawBox');
const runtimeTimeline = document.getElementById('runtimeTimeline');
const runtimeFailures = document.getElementById('runtimeFailures');
const runtimeArtifacts = document.getElementById('runtimeArtifacts');
const artifactDetailMeta = document.getElementById('artifactDetailMeta');
const artifactDetailBox = document.getElementById('artifactDetailBox');
const restartAnalytics = document.getElementById('restartAnalytics');
const runtimeActionReadiness = document.getElementById('runtimeActionReadiness');
const supervisorSummaryMain = document.getElementById('supervisorSummaryMain');
const guardRawBox = document.getElementById('guardRawBox');
const heroHealthSummary = document.getElementById('heroHealthSummary');
const heroRouteSummary = document.getElementById('heroRouteSummary');
const heroOpsSummary = document.getElementById('heroOpsSummary');
const subconsciousStatusBox = document.getElementById('subconsciousStatusBox');
const subconsciousPriorityList = document.getElementById('subconsciousPriorityList');
const generatedQueueBox = document.getElementById('generatedQueueBox');
const metricsCanvas = document.getElementById('metricsCanvas');
const ctx = metricsCanvas ? metricsCanvas.getContext('2d') : null;
const navButtons = Array.from(document.querySelectorAll('[data-view-target]'));
const mainViews = Array.from(document.querySelectorAll('.main-view'));

let sessionsCache = [];
let testRunsCache = [];
let testSessionDefinitions = [];
let latestStatus = null;
let latestPolicy = null;
const runtimeInspectCache = new Map();
let runtimeInspectSeq = 0;
let selectedArtifactName = '';
let currentArtifactDetail = null;
let operatorPromptBusy = false;
let operatorVoiceOutputEnabled = localStorage.getItem('nova_operator_voice_output') === 'on';
let operatorRecognition = null;
let operatorRecognitionActive = false;
const OperatorSpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition || null;
let operatorMacroValueCache = {};

function filteredSessions() {
    const filter = sessionFilterSelect ? String(sessionFilterSelect.value || 'all').trim().toLowerCase() : 'all';
    if (filter === 'operator') {
        return sessionsCache.filter((item) => String(item.owner || '').trim().toLowerCase() === 'operator' || String(item.session_id || '').startsWith('operator-'));
    }
    if (filter === 'non-operator') {
        return sessionsCache.filter((item) => !(String(item.owner || '').trim().toLowerCase() === 'operator' || String(item.session_id || '').startsWith('operator-')));
    }
    return sessionsCache;
}

function generatedPriorityRank(priority) {
    const urgency = String(priority && priority.urgency ? priority.urgency : '').trim().toLowerCase();
    return ({high: 0, medium: 1, low: 2, deferred: 3})[urgency] ?? 4;
}

function summarizeGeneratedPriority(item) {
    const priorities = Array.isArray(item && item.training_priorities) ? item.training_priorities.filter((entry) => entry && typeof entry === 'object') : [];
    if (!priorities.length) return '';
    const ordered = priorities.slice().sort((left, right) => {
        const leftRank = generatedPriorityRank(left);
        const rightRank = generatedPriorityRank(right);
        if (leftRank !== rightRank) return leftRank - rightRank;
        const leftRobustness = Number(left && left.robustness != null ? left.robustness : 0);
        const rightRobustness = Number(right && right.robustness != null ? right.robustness : 0);
        if (leftRobustness !== rightRobustness) return rightRobustness - leftRobustness;
        return String(left && left.signal ? left.signal : '').localeCompare(String(right && right.signal ? right.signal : ''));
    });
    const lead = ordered[0] || {};
    const urgency = String(lead.urgency || 'n/a').toLowerCase();
    const signal = String(lead.signal || 'priority').trim();
    const seam = String(lead.seam || item.family_id || '').trim();
    const score = Number(lead.robustness != null ? lead.robustness : 0);
    const shortScore = Number.isFinite(score) ? score.toFixed(2) : 'n/a';
    return `${urgency} ${signal}${seam ? ' @ ' + seam : ''} (${shortScore})`;
}

function buildGeneratedPriorityTitle(item) {
    const priorities = Array.isArray(item && item.training_priorities) ? item.training_priorities.filter((entry) => entry && typeof entry === 'object') : [];
    if (!priorities.length) return '';
    const ordered = priorities.slice().sort((left, right) => {
        const leftRank = generatedPriorityRank(left);
        const rightRank = generatedPriorityRank(right);
        if (leftRank !== rightRank) return leftRank - rightRank;
        return Number(right && right.robustness != null ? right.robustness : 0) - Number(left && left.robustness != null ? left.robustness : 0);
    });
    return ordered.slice(0, 3).map((entry) => {
        const urgency = String(entry.urgency || 'n/a').toLowerCase();
        const signal = String(entry.signal || 'priority').trim();
        const seam = String(entry.seam || item.family_id || '').trim();
        const testName = String(entry.suggested_test_name || '').trim();
        const score = Number(entry.robustness != null ? entry.robustness : 0);
        return `${urgency} | ${signal}${seam ? ' | ' + seam : ''}${testName ? ' | ' + testName : ''} | robustness=${Number.isFinite(score) ? score.toFixed(2) : 'n/a'}`;
    }).join('\n');
}

async function resolveOperatorMacroValues(macro) {
    const macroId = String(macro && macro.macro_id ? macro.macro_id : '').trim();
    if (!macroId) return {};
    const placeholders = Array.isArray(macro && macro.placeholders) ? macro.placeholders.filter((item) => item && typeof item === 'object') : [];
    if (!placeholders.length) return {};
    const cached = operatorMacroValueCache[macroId] && typeof operatorMacroValueCache[macroId] === 'object' ? operatorMacroValueCache[macroId] : {};
    const values = {...cached};
    for (const placeholder of placeholders) {
        const name = String(placeholder.name || '').trim();
        if (!name) continue;
        const label = String(placeholder.label || name).trim();
        const current = String(values[name] || placeholder.default || '').trim();
        const entered = window.prompt(label, current);
        if (entered === null) return null;
        const resolved = String(entered || '').trim() || String(placeholder.default || '').trim();
        if (Boolean(placeholder.required) && !resolved) {
            setAction(`Macro placeholder required: ${label}`);
            return null;
        }
        values[name] = resolved;
    }
    operatorMacroValueCache[macroId] = values;
    return values;
}

function renderOperatorMacroPrompt(macro, values, note = '') {
    let prompt = String((macro && (macro.prompt_template || macro.prompt)) || '').trim();
    const resolved = values && typeof values === 'object' ? values : {};
    Object.keys(resolved).forEach((name) => {
        const value = String(resolved[name] || '');
        prompt = prompt.split(`{${name}}`).join(value);
    });
    const cleanNote = String(note || '').trim();
    if (cleanNote) {
        prompt = `${prompt}\n\nOperator note: ${cleanNote}`;
    }
    return prompt.trim();
}

function escapeHtml(text) {
    return String(text == null ? '' : text).replace(/[&<>"']/g, (match) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[match]));
}

function classifyPatchFileImpact(path) {
    const clean = String(path || '').trim().toLowerCase();
    if (!clean) return 'runtime update';
    if (clean.startsWith('tests/')) return 'test coverage';
    if (clean.startsWith('docs/')) return 'operator documentation';
    if (clean.startsWith('templates/') || clean.startsWith('static/')) return 'control UI behavior';
    if (clean.startsWith('scripts/')) return 'automation script behavior';
    if (clean.endsWith('.py')) return 'runtime logic';
    if (clean.endsWith('.md')) return 'docs and runbooks';
    if (clean.endsWith('.json')) return 'policy or data contract';
    return 'runtime files';
}

function parsePatchPreviewReport(text) {
    const lines = String(text || '').split(/\r?\n/);
    const out = {
        zip: '',
        status: '',
        patchRevision: '',
        minBaseRevision: '',
        currentRevision: '',
        changed: [],
        added: [],
        skipped: [],
    };
    let section = '';
    for (const line of lines) {
        const raw = String(line || '');
        const trimmed = raw.trim();
        if (!trimmed) {
            section = '';
            continue;
        }
        if (trimmed === 'Changed files:') { section = 'changed'; continue; }
        if (trimmed === 'Added files:') { section = 'added'; continue; }
        if (trimmed === 'Skipped files:') { section = 'skipped'; continue; }
        if (trimmed.startsWith('Diff summary:')) { section = ''; continue; }

        const zipMatch = trimmed.match(/^Zip:\s*(.+)$/i);
        if (zipMatch) { out.zip = zipMatch[1].trim(); continue; }
        const statusMatch = trimmed.match(/^Status:\s*(.+)$/i);
        if (statusMatch) { out.status = statusMatch[1].trim(); continue; }
        const revMatch = trimmed.match(/^Patch revision:\s*(.+)$/i);
        if (revMatch) { out.patchRevision = revMatch[1].trim(); continue; }
        const baseMatch = trimmed.match(/^Min base revision:\s*(.+)$/i);
        if (baseMatch) { out.minBaseRevision = baseMatch[1].trim(); continue; }
        const currentMatch = trimmed.match(/^Current revision:\s*(.+)$/i);
        if (currentMatch) { out.currentRevision = currentMatch[1].trim(); continue; }

        if (section && trimmed.startsWith('- ')) {
            const value = trimmed.slice(2).trim();
            if (value) out[section].push(value);
        }
    }
    return out;
}

function renderPatchPreviewSummary(text, previewName = '') {
    if (!patchPreviewSummary) return;
    const parsed = parsePatchPreviewReport(text);
    const changed = Array.isArray(parsed.changed) ? parsed.changed : [];
    const added = Array.isArray(parsed.added) ? parsed.added : [];
    const skipped = Array.isArray(parsed.skipped) ? parsed.skipped : [];
    if (!String(text || '').trim()) {
        patchPreviewSummary.innerHTML = '<div class="inspector-item"><div class="inspector-key">Preview Summary</div><div class="inspector-value">Load a preview to see what Nova is adding before approving it.</div></div>';
        return;
    }

    const allTouched = [...added, ...changed];
    const impactCounts = new Map();
    allTouched.forEach((item) => {
        const key = classifyPatchFileImpact(item);
        impactCounts.set(key, (impactCounts.get(key) || 0) + 1);
    });
    const topImpacts = [...impactCounts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3).map(([name, count]) => `${count} ${name}`);
    const statusLow = String(parsed.status || '').toLowerCase();
    let approvalMessage = 'This preview is ready for operator decision.';
    if (statusLow.startsWith('eligible')) {
        approvalMessage = 'Nova can apply this after you approve it.';
    } else if (statusLow.startsWith('rejected')) {
        approvalMessage = 'Do not approve yet: governance marked this preview as blocked.';
    }

    const changedPreview = changed.slice(0, 4).map((item) => `<li>${escapeHtml(item)}</li>`).join('');
    const addedPreview = added.slice(0, 4).map((item) => `<li>${escapeHtml(item)}</li>`).join('');

    patchPreviewSummary.innerHTML = [
        '<div class="patch-summary-highlight">',
        '<div class="patch-summary-title">What Nova Is Adding</div>',
        `<div class="patch-summary-body">${escapeHtml(approvalMessage)} ${escapeHtml(topImpacts.length ? 'Main impact areas: ' + topImpacts.join(', ') + '.' : 'No changed or added files were detected.')}</div>`,
        '</div>',
        '<div class="inspector-item">',
        '<div class="inspector-key">Preview</div>',
        `<div class="inspector-value">${escapeHtml(previewName || parsed.zip || 'selected preview')}</div>`,
        '</div>',
        '<div class="inspector-item">',
        '<div class="inspector-key">Approval Gate</div>',
        `<div class="inspector-value">Status=${escapeHtml(parsed.status || 'unknown')} | Patch rev=${escapeHtml(parsed.patchRevision || 'unknown')} | Base=${escapeHtml(parsed.minBaseRevision || 'n/a')} | Current=${escapeHtml(parsed.currentRevision || 'n/a')}</div>`,
        '</div>',
        '<div class="inspector-item">',
        '<div class="inspector-key">Change Counts</div>',
        `<div class="inspector-value">Added=${added.length} | Changed=${changed.length} | Skipped=${skipped.length}</div>`,
        '</div>',
        changedPreview ? `<div class="inspector-item"><div class="inspector-key">Top Changed Files</div><div class="inspector-value"><ul>${changedPreview}</ul></div></div>` : '',
        addedPreview ? `<div class="inspector-item"><div class="inspector-key">Top Added Files</div><div class="inspector-value"><ul>${addedPreview}</ul></div></div>` : '',
    ].join('');
}

function setActiveView(name) {
    navButtons.forEach((button) => {
        const active = (button.getAttribute('data-view-target') || '') === name;
        button.classList.toggle('active', active);
    });
    mainViews.forEach((view) => {
        const visible = (view.getAttribute('data-view') || '') === name;
        view.classList.toggle('d-none', !visible);
    });
}

if (keyInput) {
    keyInput.value = localStorage.getItem('nova_control_key') || '';
    keyInput.addEventListener('change', () => {
        localStorage.setItem('nova_control_key', keyInput.value.trim());
    });
}

if (operatorSessionIdInput) {
    operatorSessionIdInput.value = localStorage.getItem('nova_operator_session_id') || '';
    operatorSessionIdInput.addEventListener('change', () => {
        localStorage.setItem('nova_operator_session_id', operatorSessionIdInput.value.trim());
    });
}

function controlHeaders() {
    const key = keyInput ? keyInput.value.trim() : '';
    const headers = {'Content-Type': 'application/json'};
    if (key) headers['X-Nova-Control-Key'] = key;
    return headers;
}

function setFeedback(text, level = 'muted') {
    if (!feedbackBar) return;
    feedbackBar.className = 'signal-bar signal-' + (['good', 'warn', 'danger', 'info', 'muted'].includes(level) ? level : 'muted');
    feedbackBar.textContent = text;
}

function setAction(text) {
    if (actionBox) actionBox.textContent = text;
    if (actionBoxClone) actionBoxClone.textContent = text;
    const firstLine = String(text || '').split('\n')[0].trim() || 'Action complete.';
    setFeedback(firstLine, /failed|error|denied|forbidden/i.test(firstLine) ? 'danger' : 'good');
}

function focusOperatorSession(sessionId) {
    const sid = String(sessionId || '').trim();
    if (!sid) return;
    if (operatorSessionIdInput) operatorSessionIdInput.value = sid;
    localStorage.setItem('nova_operator_session_id', sid);
    if (sessionFilterSelect && String(sessionFilterSelect.value || 'all') === 'non-operator' && sid.startsWith('operator-')) {
        sessionFilterSelect.value = 'operator';
        renderSessions();
    }
    if (sessionSelect && sessionsCache.some((session) => session.session_id === sid)) {
        sessionSelect.value = sid;
        renderSessionPreview();
    }
}

function renderOperatorReply(payload) {
    if (!operatorPromptReply) return;
    if (!payload) {
        operatorPromptReply.textContent = 'No operator prompt sent yet.';
        return;
    }
    const session = payload.session || {};
    operatorPromptReply.textContent = [
        `Session: ${payload.session_id || session.session_id || 'n/a'}`,
        `Owner: ${payload.user_id || session.owner || 'operator'}`,
        `Turns: ${session.turn_count != null ? session.turn_count : 'n/a'}`,
        '',
        'Reply:',
        payload.reply || payload.message || 'No reply returned.',
    ].join('\n');

    if (payload.reply) {
        speakOperatorReply(payload.reply);
    }
}

function syncOperatorAudioButton() {
    if (!btnOperatorToggleAudio) return;
    btnOperatorToggleAudio.textContent = operatorVoiceOutputEnabled ? 'Voice On' : 'Voice Off';
    btnOperatorToggleAudio.classList.toggle('btn-operator-primary', operatorVoiceOutputEnabled);
    btnOperatorToggleAudio.classList.toggle('btn-operator-alt', !operatorVoiceOutputEnabled);
}

function syncOperatorMicButton() {
    if (!btnOperatorMic) return;
    if (!OperatorSpeechRecognitionCtor) {
        btnOperatorMic.textContent = 'Mic Unavailable';
        btnOperatorMic.disabled = true;
        return;
    }
    btnOperatorMic.disabled = false;
    btnOperatorMic.textContent = operatorRecognitionActive ? 'Listening...' : 'Mic Ready';
    btnOperatorMic.classList.toggle('btn-operator-primary', operatorRecognitionActive);
    btnOperatorMic.classList.toggle('btn-operator-alt', !operatorRecognitionActive);
}

function speakOperatorReply(text) {
    if (!operatorVoiceOutputEnabled || !window.speechSynthesis) return;
    const spoken = String(text || '').trim();
    if (!spoken) return;
    try {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(spoken);
        utterance.rate = 1.0;
        utterance.pitch = 1.0;
        window.speechSynthesis.speak(utterance);
    } catch (_) {
        // Keep operator controls usable if browser speech APIs fail.
    }
}

function initOperatorSpeechRecognition() {
    if (!OperatorSpeechRecognitionCtor || operatorRecognition) return;
    operatorRecognition = new OperatorSpeechRecognitionCtor();
    operatorRecognition.lang = 'en-US';
    operatorRecognition.interimResults = false;
    operatorRecognition.maxAlternatives = 1;
    operatorRecognition.onstart = () => {
        operatorRecognitionActive = true;
        syncOperatorMicButton();
    };
    operatorRecognition.onend = () => {
        operatorRecognitionActive = false;
        syncOperatorMicButton();
    };
    operatorRecognition.onerror = () => {
        operatorRecognitionActive = false;
        syncOperatorMicButton();
    };
    operatorRecognition.onresult = async (event) => {
        const transcript = String(event.results?.[0]?.[0]?.transcript || '').trim();
        if (!transcript || !operatorPromptInput) return;
        operatorPromptInput.value = transcript;
        await sendOperatorPrompt();
    };
}

async function sendOperatorPrompt() {
    if (operatorPromptBusy) return;
    const macroId = operatorMacroSelect ? operatorMacroSelect.value.trim() : '';
    let message = operatorPromptInput ? operatorPromptInput.value.trim() : '';
    if (!message && !macroId) {
        setAction('Enter an operator prompt or select a macro first.');
        return;
    }
    operatorPromptBusy = true;
    try {
        let macroValues = {};
        if (macroId) {
            const macro = selectedOperatorMacro();
            const resolved = await resolveOperatorMacroValues(macro);
            if (resolved === null) return;
            macroValues = resolved;
        }
        const payload = await postAction('operator_prompt', {
            session_id: operatorSessionIdInput ? operatorSessionIdInput.value.trim() : '',
            source: 'manual',
            macro: macroId,
            macro_values: macroValues,
            message,
        });
        sessionsCache = Array.isArray(payload.sessions) ? payload.sessions : sessionsCache;
        renderSessions();
        focusOperatorSession(payload.session_id || '');
        renderOperatorReply(payload);
        if (operatorPromptInput) operatorPromptInput.value = '';
        setAction(payload.reply || payload.message || 'Operator prompt completed.');
    } finally {
        operatorPromptBusy = false;
    }
}

async function runNextGeneratedQueueItem() {
    const payload = await postAction('generated_queue_run_next', {});
    testRunsCache = Array.isArray(payload.reports) ? payload.reports : testRunsCache;
    testSessionDefinitions = Array.isArray(payload.definitions) ? payload.definitions : testSessionDefinitions;
    renderTestRuns();
    renderTestSessionDefinitions();
    if (payload.latest_report && testRunSelect && payload.latest_report.run_id) {
        testRunSelect.value = payload.latest_report.run_id;
        renderTestRunPreview();
    }
    const selected = payload.selected && payload.selected.file ? payload.selected.file : 'none';
    const latest = payload.latest_report && payload.latest_report.run_id ? payload.latest_report.run_id : 'no report';
    setAction(`${payload.message || 'generated_queue_run_next completed'}\nSelected: ${selected}\nLatest report: ${latest}`);
    await refresh();
}

async function investigateNextGeneratedQueueItem() {
    const payload = await postAction('generated_queue_investigate', {
        session_id: operatorSessionIdInput ? operatorSessionIdInput.value.trim() : '',
        user_id: 'operator',
    });
    sessionsCache = Array.isArray(payload.sessions) ? payload.sessions : sessionsCache;
    renderSessions();
    focusOperatorSession(payload.session_id || '');
    renderOperatorReply(payload);
    const selected = payload.selected && payload.selected.file ? payload.selected.file : 'none';
    setAction(`${payload.message || 'generated_queue_investigate completed'}\nSelected: ${selected}\nOperator session: ${payload.session_id || 'n/a'}`);
}

function renderMetricGrid(status) {
    if (!statusKv) return;
    const keys = [
        'server_time', 'ollama_api_up', 'chat_model', 'memory_enabled', 'memory_scope', 'web_enabled',
        'search_provider', 'allow_domains_count', 'active_http_sessions', 'health_score',
        'self_check_pass_ratio', 'tool_events_total', 'memory_events_total', 'action_ledger_total',
        'last_planner_decision', 'last_route_summary', 'process_counting_mode', 'heartbeat_age_sec',
        'subconscious_family_count', 'subconscious_training_priority_count', 'subconscious_generated_definition_count'
    ];
    statusKv.innerHTML = keys.map((key) => [
        '<div class="metric-cell">',
        `<div class="metric-label">${escapeHtml(key)}</div>`,
        `<div class="metric-value">${escapeHtml(status && status[key] != null ? status[key] : '')}</div>`,
        '</div>'
    ].join('')).join('');
}

function renderSubconscious(status) {
    const summary = status && status.subconscious_summary ? status.subconscious_summary : {};
    const topPriorities = Array.isArray(status && status.subconscious_top_priorities) ? status.subconscious_top_priorities : [];
    const workQueue = status && status.generated_work_queue ? status.generated_work_queue : {};
    const queueItems = Array.isArray(workQueue && workQueue.items) ? workQueue.items : [];

    renderInspectorList(subconsciousStatusBox, [
        {label: 'Latest run', value: summary.generated_at || 'not available'},
        {label: 'Label', value: summary.label || 'n/a'},
        {label: 'Families', value: summary.family_count != null ? summary.family_count : 0},
        {label: 'Variations', value: summary.variation_count != null ? summary.variation_count : 0},
        {label: 'Training priorities', value: summary.training_priority_count != null ? summary.training_priority_count : 0},
        {label: 'Generated session definitions', value: summary.generated_definition_count != null ? summary.generated_definition_count : 0},
        {label: 'Open queue items', value: workQueue.open_count != null ? workQueue.open_count : 0},
        {label: 'Next queue item', value: workQueue.next_item && workQueue.next_item.file ? workQueue.next_item.file : 'none'},
        {label: 'Latest report path', value: summary.latest_report_path || 'n/a'},
    ]);

    renderInspectorList(subconsciousPriorityList, topPriorities.map((item) => ({
        label: `${item.signal || 'signal'} [${item.urgency || 'n/a'}]`,
        value: `${item.seam || 'unknown seam'} -> ${item.suggested_test_name || 'no_test_name'} (robustness=${item.robustness != null ? item.robustness : 'n/a'})`
    })));

    renderInspectorList(generatedQueueBox, queueItems.map((item) => ({
        label: `${item.file || 'generated session'} [${item.latest_status || 'never_run'}]`,
        value: `${item.opportunity_reason || 'n/a'}${item.family_id ? ' | ' + item.family_id : ''}${summarizeGeneratedPriority(item) ? ' | ' + summarizeGeneratedPriority(item) : ''}`
    })));
}

function renderInspectorList(container, items) {
    if (!container) return;
    container.innerHTML = (items && items.length ? items : [{label: 'Status', value: 'No data yet.'}]).map((item) => [
        '<div class="inspector-item">',
        `<div class="inspector-key">${escapeHtml(item.label)}</div>`,
        `<div class="inspector-value">${escapeHtml(item.value)}</div>`,
        '</div>'
    ].join('')).join('');
}

function patchBadgeClass(status) {
    if (!status || status.patch_enabled === false) return 'status-pill status-pill-neutral';
    if (status.patch_ready_for_validated_apply) return 'status-pill status-pill-good';
    if (status.patch_pipeline_ready) return 'status-pill status-pill-warn';
    const previewStatus = String(status.patch_last_preview_status || '').toLowerCase();
    if (previewStatus.startsWith('rejected') || status.patch_behavioral_check === false || status.patch_strict_manifest === false) {
        return 'status-pill status-pill-danger';
    }
    return 'status-pill status-pill-warn';
}

function renderPatchReadiness(status) {
    const patchEnabled = Boolean(status && status.patch_enabled);
    const pipelineReady = Boolean(status && status.patch_pipeline_ready);
    const validatedReady = Boolean(status && status.patch_ready_for_validated_apply);
    const currentRevision = status && status.patch_current_revision != null ? status.patch_current_revision : 'n/a';
    const previewsTotal = status && status.patch_previews_total != null ? status.patch_previews_total : 0;
    const previewsPending = status && status.patch_previews_pending != null ? status.patch_previews_pending : 0;
    const previewsApproved = status && status.patch_previews_approved != null ? status.patch_previews_approved : 0;
    const previewsRejected = status && status.patch_previews_rejected != null ? status.patch_previews_rejected : 0;
    const previewsEligible = status && status.patch_previews_eligible != null ? status.patch_previews_eligible : 0;
    const previewsApprovedEligible = status && status.patch_previews_approved_eligible != null ? status.patch_previews_approved_eligible : 0;
    const previewStatus = String(status && status.patch_last_preview_status ? status.patch_last_preview_status : '').trim();
    const previewDecision = String(status && status.patch_last_preview_decision ? status.patch_last_preview_decision : 'pending').trim() || 'pending';
    const lastPreviewName = String(status && status.patch_last_preview_name ? status.patch_last_preview_name : '').trim() || 'none';
    const lastLogLine = String(status && status.patch_last_log_line ? status.patch_last_log_line : '').trim() || 'No recent patch log line.';

    if (patchStatusBadge) {
        patchStatusBadge.className = patchBadgeClass(status);
        if (!patchEnabled) patchStatusBadge.textContent = 'Patch pipeline disabled';
        else if (validatedReady) patchStatusBadge.textContent = previewsApprovedEligible === 1 ? '1 preview ready to apply' : `${previewsApprovedEligible} previews ready to apply`;
        else if (!pipelineReady) patchStatusBadge.textContent = 'Pipeline blocked';
        else if (previewsTotal === 0) patchStatusBadge.textContent = 'Awaiting preview';
        else if (previewsApproved === 0 && previewsPending > 0) patchStatusBadge.textContent = 'Awaiting approval';
        else if (previewsApproved > 0 && previewsApprovedEligible === 0) patchStatusBadge.textContent = 'Approved preview blocked';
        else if (previewStatus.toLowerCase().startsWith('rejected')) patchStatusBadge.textContent = 'Preview blocked';
        else patchStatusBadge.textContent = 'No ready preview';
    }

    if (patchStatusNarrative) {
        if (!patchEnabled) {
            patchStatusNarrative.textContent = 'Patch apply is disabled by policy. No live promotion should be attempted until the pipeline is re-enabled.';
        } else {
            const blockers = [];
            if (status && status.patch_strict_manifest === false) blockers.push('strict manifest is disabled');
            if (status && status.patch_behavioral_check === false) blockers.push('behavioral validation is disabled');
            if (status && status.patch_tests_available === false) blockers.push('tests are not available');
            if (!pipelineReady) {
                patchStatusNarrative.textContent = blockers.length
                    ? `The patch pipeline is not ready because ${blockers.join(', ')}.`
                    : 'The patch pipeline is not ready yet. Review policy gates and workspace validation coverage.';
            } else if (validatedReady) {
                const queueText = previewsPending > 0
                    ? `${previewsPending} preview${previewsPending === 1 ? '' : 's'} still await operator review`
                    : 'no additional preview backlog is waiting for review';
                patchStatusNarrative.textContent = `The patch pipeline is armed at revision ${currentRevision}, and ${previewsApprovedEligible} approved eligible preview${previewsApprovedEligible === 1 ? '' : 's'} can be promoted now. ${queueText}.`;
            } else if (previewsTotal === 0) {
                patchStatusNarrative.textContent = `The patch pipeline is armed at revision ${currentRevision}, but there are no preview reports in the queue yet.`;
            } else {
                const queueReasons = [];
                if (previewsEligible > 0 && previewsApprovedEligible === 0) {
                    queueReasons.push(`${previewsEligible} eligible preview${previewsEligible === 1 ? '' : 's'} still need operator approval`);
                }
                if (previewsApproved > previewsApprovedEligible) {
                    const blockedApproved = previewsApproved - previewsApprovedEligible;
                    queueReasons.push(`${blockedApproved} approved preview${blockedApproved === 1 ? '' : 's'} are not currently eligible`);
                }
                if (previewsRejected > 0) {
                    queueReasons.push(`${previewsRejected} preview${previewsRejected === 1 ? '' : 's'} are rejected`);
                }
                if (!queueReasons.length && previewStatus.toLowerCase().startsWith('rejected')) {
                    queueReasons.push(`the latest preview is ${previewStatus}`);
                }
                patchStatusNarrative.textContent = queueReasons.length
                    ? `The patch pipeline is armed, but no approved eligible preview is ready to apply because ${queueReasons.join(', ')}.`
                    : 'The patch pipeline is armed, but no approved eligible preview is ready to apply yet. Review preview state and the latest patch log before attempting promotion.';
            }
        }
    }

    renderInspectorList(patchSummaryGrid, [
        {label: 'Patch enabled', value: String(patchEnabled)},
        {label: 'Strict manifest', value: String(Boolean(status && status.patch_strict_manifest))},
        {label: 'Behavioral gate', value: String(Boolean(status && status.patch_behavioral_check))},
        {label: 'Tests available', value: String(Boolean(status && status.patch_tests_available))},
        {label: 'Pipeline ready', value: String(pipelineReady)},
        {label: 'Validated apply ready', value: String(validatedReady)},
        {label: 'Current revision', value: currentRevision},
        {label: 'Behavior timeout sec', value: status && status.patch_behavioral_check_timeout_sec != null ? status.patch_behavioral_check_timeout_sec : 'n/a'},
    ]);

    renderInspectorList(patchPreviewGrid, [
        {label: 'Previews total', value: previewsTotal},
        {label: 'Pending', value: previewsPending},
        {label: 'Approved', value: previewsApproved},
        {label: 'Rejected', value: previewsRejected},
        {label: 'Eligible', value: previewsEligible},
        {label: 'Approved + eligible', value: previewsApprovedEligible},
        {label: 'Latest preview', value: lastPreviewName},
        {label: 'Preview status', value: previewStatus || 'unknown'},
        {label: 'Decision', value: previewDecision},
    ]);

    if (patchLogBox) {
        patchLogBox.textContent = lastLogLine;
    }

    if (patchPreviewSelect) {
        const previews = status && Array.isArray(status.patch_previews) ? status.patch_previews : [];
        const current = (patchPreviewSelect.value || '').trim();
        patchPreviewSelect.innerHTML = '';
        if (!previews.length) {
            const option = document.createElement('option');
            option.value = '';
            option.textContent = '(no patch previews)';
            patchPreviewSelect.appendChild(option);
        } else {
            previews.forEach((preview) => {
                const option = document.createElement('option');
                const name = String(preview && preview.name ? preview.name : '').trim();
                const decision = String(preview && preview.decision ? preview.decision : 'pending').trim() || 'pending';
                const previewState = String(preview && preview.status ? preview.status : 'unknown').trim() || 'unknown';
                option.value = name;
                option.textContent = `${decision.toUpperCase()} | ${previewState} | ${name}`;
                patchPreviewSelect.appendChild(option);
            });
            if (current && previews.some((preview) => String(preview && preview.name ? preview.name : '') === current)) {
                patchPreviewSelect.value = current;
            }
        }
    }

    if (patchPreviewBox && (!status || !Array.isArray(status.patch_previews) || !status.patch_previews.length)) {
        patchPreviewBox.textContent = 'No patch previews are available yet.';
    }
    if (patchPreviewSummary && (!status || !Array.isArray(status.patch_previews) || !status.patch_previews.length)) {
        renderPatchPreviewSummary('', '');
    }

    renderPatchActionReadiness(status);
}

function selectedPatchPreviewState(status) {
    const readiness = status && status.patch_action_readiness ? status.patch_action_readiness : {};
    const previewMap = readiness && readiness.by_preview && typeof readiness.by_preview === 'object' ? readiness.by_preview : {};
    const selected = (patchPreviewSelect && patchPreviewSelect.value ? patchPreviewSelect.value.trim() : '') || String(readiness.default_preview || '').trim();
    return {
        readiness,
        selected,
        preview: selected && previewMap[selected] ? previewMap[selected] : null,
    };
}

function renderPatchActionReadiness(status) {
    const state = selectedPatchPreviewState(status);
    const previewState = state.preview;
    const fallback = String(state.readiness && state.readiness.preview_fallback_reason ? state.readiness.preview_fallback_reason : 'Select a patch preview first.');
    const refreshState = state.readiness && state.readiness.preview_refresh ? state.readiness.preview_refresh : {enabled: true, reason: 'Refresh patch preview queue state and governance telemetry.'};
    const showState = previewState && previewState.show ? previewState.show : {enabled: false, reason: fallback};
    const approveState = previewState && previewState.approve ? previewState.approve : {enabled: false, reason: fallback};
    const rejectState = previewState && previewState.reject ? previewState.reject : {enabled: false, reason: fallback};
    const applyState = previewState && previewState.apply ? previewState.apply : {enabled: false, reason: fallback};

    renderInspectorList(patchActionReadiness, [
        {label: 'Selected Preview', value: state.selected || 'none'},
        {label: 'Preview Status', value: previewState ? `${previewState.status || 'unknown'} | decision=${previewState.decision || 'pending'}` : 'No preview selected'},
        {label: 'Refresh Queue', value: `${refreshState.enabled ? 'Enabled' : 'Disabled'} - ${refreshState.reason}`},
        {label: 'Show Preview', value: `${showState.enabled ? 'Enabled' : 'Disabled'} - ${showState.reason}`},
        {label: 'Approve Preview', value: `${approveState.enabled ? 'Enabled' : 'Disabled'} - ${approveState.reason}`},
        {label: 'Reject Preview', value: `${rejectState.enabled ? 'Enabled' : 'Disabled'} - ${rejectState.reason}`},
        {label: 'Apply Preview', value: `${applyState.enabled ? 'Enabled' : 'Disabled'} - ${applyState.reason}`},
    ]);

    setButtonReadiness('btnPatchPreviewRefresh', refreshState);
    setButtonReadiness('btnPatchPreviewShow', showState);
    setButtonReadiness('btnPatchPreviewApprove', approveState);
    setButtonReadiness('btnPatchPreviewReject', rejectState);
    setButtonReadiness('btnPatchPreviewApply', applyState);
}

function renderPlannerInspector(status) {
    renderInspectorList(plannerInspector, [
        {label: 'Intent', value: status && status.last_intent ? status.last_intent : 'n/a'},
        {label: 'Route', value: status && status.last_planner_decision ? status.last_planner_decision : 'n/a'},
        {label: 'Tool', value: status && status.last_action_tool ? status.last_action_tool : 'n/a'},
        {label: 'Reason / Summary', value: status && status.last_route_summary ? status.last_route_summary : 'n/a'},
    ]);
}

function renderLedgerInspector(status) {
    if (!ledgerInspector) return;
    const trace = status && Array.isArray(status.last_route_trace) ? status.last_route_trace : [];
    const items = trace.length ? trace : [
        {stage: 'input', outcome: 'received'},
        {stage: 'planner', outcome: status && status.last_planner_decision ? status.last_planner_decision : 'n/a'},
        {stage: 'final_answer', outcome: status && status.last_action_final_answer ? status.last_action_final_answer : 'n/a'},
    ];
    ledgerInspector.innerHTML = items.map((item) => {
        const outcome = String(item.outcome || '');
        let cls = 'timeline-item';
        if (/ok|matched|grounded|run_tool/i.test(outcome)) cls += ' good';
        else if (/clarify|fallback|warning/i.test(outcome)) cls += ' warn';
        else if (/fail|error|denied/i.test(outcome)) cls += ' danger';
        return [
            `<div class="${cls}">`,
            '<div class="timeline-step">',
            '<div class="timeline-bullet"></div>',
            '<div>',
            `<div class="inspector-key">${escapeHtml(item.stage || 'stage')}</div>`,
            `<div class="inspector-value">${escapeHtml(outcome)}</div>`,
            '</div>',
            '</div>',
            '</div>'
        ].join('');
    }).join('');
}

function runtimeTimelineClass(levelText) {
    const low = String(levelText || '').trim().toLowerCase();
    if (low === 'good' || low === 'ok' || low === 'success') return 'timeline-item good';
    if (low === 'danger' || low === 'fail' || low === 'error') return 'timeline-item danger';
    if (low === 'warn' || low === 'warning') return 'timeline-item warn';
    return 'timeline-item';
}

function formatRuntimeEventTime(tsValue) {
    const numeric = Number(tsValue || 0);
    if (!Number.isFinite(numeric) || numeric <= 0) return 'time unavailable';
    return new Date(numeric * 1000).toLocaleString();
}

function renderRuntimeTimeline(status) {
    if (!runtimeTimeline) return;
    const payload = status && status.runtime_timeline ? status.runtime_timeline : {};
    const events = Array.isArray(payload.events) ? payload.events : [];
    if (!events.length) {
        runtimeTimeline.innerHTML = '<div class="timeline-item"><div class="timeline-step"><div class="timeline-bullet"></div><div><div class="inspector-key">Runtime Event Timeline</div><div class="inspector-value">No runtime events recorded yet.</div></div></div></div>';
        return;
    }
    runtimeTimeline.innerHTML = events.map((event) => [
        `<div class="${escapeHtml(runtimeTimelineClass(event.level))}">`,
        '<div class="timeline-step">',
        '<div class="timeline-bullet"></div>',
        '<div class="timeline-body">',
        `<div class="timeline-meta"><span class="timeline-chip">${escapeHtml(event.source || 'runtime')}</span><span class="timeline-chip">${escapeHtml(event.service || 'runtime')}</span><span class="timeline-time">${escapeHtml(formatRuntimeEventTime(event.ts))}</span></div>`,
        `<div class="inspector-key">${escapeHtml(event.title || 'Runtime event')}</div>`,
        `<div class="inspector-value">${escapeHtml(event.detail || '')}</div>`,
        '</div>',
        '</div>',
        '</div>'
    ].join('')).join('');
}

function runtimeBadgeClassForLevel(levelText) {
    const low = String(levelText || '').trim().toLowerCase();
    if (low === 'danger' || low === 'fail' || low === 'error') return 'status-pill status-pill-danger';
    if (low === 'warn' || low === 'warning') return 'status-pill status-pill-warn';
    if (low === 'good' || low === 'ok' || low === 'success') return 'status-pill status-pill-good';
    return 'status-pill status-pill-blue';
}

function renderRuntimeFailures(status) {
    if (!runtimeFailures) return;
    const failures = status && status.runtime_failures ? status.runtime_failures : {};
    const rows = ['guard', 'core', 'webui'].map((key) => failures[key]).filter(Boolean);
    if (!rows.length) {
        runtimeFailures.innerHTML = '<div class="runtime-card"><div class="runtime-card-label">Failure Reasons</div><div class="runtime-card-details"><div class="runtime-detail-value">No failure data yet.</div></div></div>';
        return;
    }
    runtimeFailures.innerHTML = rows.map((item) => [
        '<div class="runtime-card">',
        '<div class="runtime-card-header">',
        `<div class="runtime-card-label">${escapeHtml(item.label || item.service || 'Service')}</div>`,
        `<span class="${escapeHtml(runtimeBadgeClassForLevel(item.level))}">${escapeHtml(item.status || item.level || 'unknown')}</span>`,
        '</div>',
        '<div class="runtime-card-details">',
        `<div class="runtime-detail-row"><div class="runtime-detail-key">Summary</div><div class="runtime-detail-value">${escapeHtml(item.summary || 'No failure detail.')}</div></div>`,
        `<div class="runtime-detail-row"><div class="runtime-detail-key">Latest Evidence</div><div class="runtime-detail-value">${escapeHtml(item.detail || 'No recent event detail.')}</div></div>`,
        '</div>',
        '</div>'
    ].join('')).join('');
}

function artifactBadgeClass(statusText) {
    const low = String(statusText || '').trim().toLowerCase();
    if (low === 'missing') return 'status-pill status-pill-neutral';
    if (low === 'stale') return 'status-pill status-pill-danger';
    if (low === 'running') return 'status-pill status-pill-good';
    if (low === 'present') return 'status-pill status-pill-blue';
    return 'status-pill status-pill-warn';
}

function renderRuntimeArtifacts(status) {
    if (!runtimeArtifacts) return;
    const payload = status && status.runtime_artifacts ? status.runtime_artifacts : {};
    const items = Array.isArray(payload.items) ? payload.items : [];
    if (!items.length) {
        runtimeArtifacts.innerHTML = '<div class="artifact-card"><div class="runtime-card-label">Runtime Artifacts</div><div class="runtime-detail-value">No runtime artifacts yet.</div></div>';
        return;
    }
    runtimeArtifacts.innerHTML = items.map((item) => [
        `<div class="artifact-card${selectedArtifactName && selectedArtifactName === String(item.name || '') ? ' is-active' : ''}">`,
        '<div class="runtime-card-header">',
        `<div class="runtime-card-label">${escapeHtml(item.name || 'artifact')}</div>`,
        `<span class="${escapeHtml(artifactBadgeClass(item.status))}">${escapeHtml(item.status || 'unknown')}</span>`,
        '</div>',
        `<div class="artifact-meta">${escapeHtml(item.kind || 'artifact')} | service=${escapeHtml(item.service || 'runtime')} | age=${escapeHtml(item.age_sec != null ? String(item.age_sec) + 's' : 'n/a')}</div>`,
        `<div class="runtime-detail-value artifact-summary">${escapeHtml(item.summary || '')}</div>`,
        '<div class="artifact-actions">',
        `<button type="button" class="btn btn-sm btn-operator-alt artifact-inspect-button" data-artifact-name="${escapeHtml(item.name || '')}">Inspect</button>`,
        `<button type="button" class="btn btn-sm btn-operator-primary artifact-copy-button" data-artifact-name="${escapeHtml(item.name || '')}" data-artifact-path="${escapeHtml(item.path || '')}">Copy Path</button>`,
        '</div>',
        `<pre class="artifact-excerpt">${escapeHtml(item.excerpt || '')}</pre>`,
        '</div>'
    ].join('')).join('');
}

function renderArtifactDetail(detail) {
    if (!artifactDetailMeta || !artifactDetailBox) return;
    if (!detail || !detail.name) {
        renderInspectorList(artifactDetailMeta, [{label: 'Artifact', value: 'Select a runtime artifact to inspect it in detail.'}]);
        artifactDetailBox.textContent = 'Artifact detail will appear here.';
        return;
    }
    const relatedEvents = Array.isArray(detail.related_events) ? detail.related_events : [];
    renderInspectorList(artifactDetailMeta, [
        {label: 'Artifact', value: detail.name || 'unknown'},
        {label: 'Path', value: detail.path || 'n/a'},
        {label: 'Status', value: `${detail.status || 'unknown'} | service=${detail.service || 'runtime'} | kind=${detail.kind || 'artifact'}`},
        {label: 'Summary', value: detail.summary || 'No artifact summary available.'},
        {label: 'Related Events', value: relatedEvents.length ? relatedEvents.map((event) => `${event.title || 'event'} | ${event.detail || 'no detail'}`).join('\n') : 'No related runtime events recorded.'},
    ]);
    artifactDetailBox.textContent = String(detail.content || detail.excerpt || 'Artifact content unavailable.');
}

function renderRestartAnalytics(status) {
    const payload = status && status.runtime_restart_analytics ? status.runtime_restart_analytics : {};
    const recentOutcomes = Array.isArray(payload.recent_outcomes) ? payload.recent_outcomes : [];
    renderInspectorList(restartAnalytics, [
        {label: 'Flap Detection', value: `${String(payload.flap_level || 'info').toUpperCase()} - ${payload.flap_summary || 'No restart analytics available yet.'}`},
        {label: 'Observed Restarts', value: `total=${payload.count != null ? payload.count : 0} | 15m=${payload.recent_restart_count_15m != null ? payload.recent_restart_count_15m : 0} | 1h=${payload.recent_restart_count_1h != null ? payload.recent_restart_count_1h : 0} | 24h=${payload.recent_restart_count_24h != null ? payload.recent_restart_count_24h : 0}`},
        {label: 'Outcomes', value: `success=${payload.success_count != null ? payload.success_count : 0} | failure=${payload.failure_count != null ? payload.failure_count : 0} | consecutive_failures=${payload.consecutive_failures != null ? payload.consecutive_failures : 0}`},
        {label: 'Latest Outcome', value: `${payload.latest_outcome || 'unknown'} | reason=${payload.latest_reason || 'n/a'}`},
        {label: 'Last Success', value: payload.last_success_age_sec != null ? `${payload.last_success_age_sec}s ago` : 'No recorded success'},
        {label: 'Average Healthy Boot', value: payload.avg_success_boot_sec ? `${payload.avg_success_boot_sec}s` : 'n/a'},
        {label: 'Recent History', value: recentOutcomes.length ? recentOutcomes.map((item) => `${item.outcome || 'unknown'} | ${item.reason || 'n/a'} | observed=${item.observed_sec != null ? item.observed_sec : 0}s`).join('\n') : 'No recent restart observations.'},
    ]);
}

function selectedSession() {
    const sid = sessionSelect ? (sessionSelect.value || '').trim() : '';
    const available = filteredSessions();
    return available.find((item) => item.session_id === sid) || available[0] || null;
}

function selectedTestRun() {
    const runId = testRunSelect ? (testRunSelect.value || '').trim() : '';
    return testRunsCache.find((item) => item.run_id === runId) || testRunsCache[0] || null;
}

function testRunStatusLabel(run) {
    const status = String(run && run.status ? run.status : 'green').toLowerCase();
    if (status === 'drift') return 'DRIFT';
    if (status === 'warning') return 'WARN';
    return 'GREEN';
}

function testRunBadgeClass(run) {
    const status = String(run && run.status ? run.status : 'green').toLowerCase();
    if (status === 'drift') return 'status-pill status-pill-danger';
    if (status === 'warning') return 'status-pill status-pill-warn';
    return 'status-pill status-pill-good';
}

function renderSessionState(session) {
    if (!session) {
        renderInspectorList(sessionStateInspector, [{label: 'Session', value: 'No session selected.'}]);
        return;
    }
    const state = session.state || {};
    const reflection = session.reflection || {};
    renderInspectorList(sessionStateInspector, [
        {label: 'Session ID', value: session.session_id || ''},
        {label: 'Active Subject', value: state.active_subject || reflection.active_subject || 'none'},
        {label: 'State Kind', value: state.state_kind || 'none'},
        {label: 'Continuation', value: String(Boolean(state.continuation_used))},
        {label: 'Pending Action', value: state.pending_action ? JSON.stringify(state.pending_action, null, 2) : 'none'},
        {label: 'Pending Correction', value: state.pending_correction_target || 'none'},
    ]);
}

function renderSupervisorInspector(session, status) {
    const reflection = session && session.reflection ? session.reflection : {};
    const alerts = status && Array.isArray(status.alerts) ? status.alerts : [];
    const items = [
        {label: 'Probe Summary', value: reflection.probe_summary || (alerts.length ? `Alerts: ${alerts.length}` : 'All green')},
        {label: 'Findings', value: Array.isArray(reflection.probe_results) && reflection.probe_results.length ? reflection.probe_results.join('\n') : (alerts.length ? alerts.join('\n') : 'No supervisor issues detected.')},
    ];
    renderInspectorList(supervisorInspector, items);
    renderInspectorList(supervisorSummaryMain, items);
}

function renderOverrideBadges(session) {
    if (!overrideBadges) return;
    const reflection = session && session.reflection ? session.reflection : {};
    const overrides = Array.isArray(reflection.overrides_active) ? reflection.overrides_active : [];
    overrideBadges.innerHTML = overrides.length ? overrides.map((item) => `<span class="override-badge">${escapeHtml(item)}</span>`).join('') : '<span class="override-badge">No active overrides</span>';
}

function renderHealthSummary(status) {
    const alerts = status && Array.isArray(status.alerts) ? status.alerts : [];
    renderInspectorList(healthSummary, [
        {label: 'Health Score', value: status && status.health_score != null ? status.health_score : 'n/a'},
        {label: 'Pass Ratio', value: status && status.self_check_pass_ratio != null ? status.self_check_pass_ratio : 'n/a'},
        {label: 'Alerts', value: alerts.length ? alerts.join('\n') : 'No active alerts'},
    ]);
}

function setButtonReadiness(buttonId, readiness) {
    const button = document.getElementById(buttonId);
    if (!button) return;
    const enabled = Boolean(readiness && readiness.enabled);
    const reason = String(readiness && readiness.reason ? readiness.reason : '');
    button.disabled = !enabled;
    button.title = reason;
}

function renderActionReadiness(status) {
    const readiness = status && status.action_readiness ? status.action_readiness : {};
    renderInspectorList(runtimeActionReadiness, [
        {label: 'Guard Start', value: `${readiness.guard_start && readiness.guard_start.enabled ? 'Enabled' : 'Disabled'} - ${readiness.guard_start && readiness.guard_start.reason ? readiness.guard_start.reason : 'n/a'}`},
        {label: 'Guard Stop', value: `${readiness.guard_stop && readiness.guard_stop.enabled ? 'Enabled' : 'Disabled'} - ${readiness.guard_stop && readiness.guard_stop.reason ? readiness.guard_stop.reason : 'n/a'}`},
        {label: 'Guard Restart', value: `${readiness.guard_restart && readiness.guard_restart.enabled ? 'Enabled' : 'Disabled'} - ${readiness.guard_restart && readiness.guard_restart.reason ? readiness.guard_restart.reason : 'n/a'}`},
        {label: 'Core Start', value: `${readiness.nova_start && readiness.nova_start.enabled ? 'Enabled' : 'Disabled'} - ${readiness.nova_start && readiness.nova_start.reason ? readiness.nova_start.reason : 'n/a'}`},
        {label: 'Core Stop', value: `${readiness.core_stop && readiness.core_stop.enabled ? 'Enabled' : 'Disabled'} - ${readiness.core_stop && readiness.core_stop.reason ? readiness.core_stop.reason : 'n/a'}`},
        {label: 'Core Restart', value: `${readiness.core_restart && readiness.core_restart.enabled ? 'Enabled' : 'Disabled'} - ${readiness.core_restart && readiness.core_restart.reason ? readiness.core_restart.reason : 'n/a'}`},
        {label: 'Web UI Restart', value: `${readiness.webui_restart && readiness.webui_restart.enabled ? 'Enabled' : 'Disabled'} - ${readiness.webui_restart && readiness.webui_restart.reason ? readiness.webui_restart.reason : 'n/a'}`},
    ]);

    setButtonReadiness('btnGuardStart', readiness.guard_start);
    setButtonReadiness('btnGuardStop', readiness.guard_stop);
    setButtonReadiness('btnGuardRestart', readiness.guard_restart);
    setButtonReadiness('btnNovaStart', readiness.nova_start);
    setButtonReadiness('btnCoreStart', readiness.nova_start);
    setButtonReadiness('btnCoreStop', readiness.core_stop);
    setButtonReadiness('btnCoreRestart', readiness.core_restart);
    setButtonReadiness('btnWebuiRestart', readiness.webui_restart);
}

function registerRuntimeInspectPayload(payload) {
    runtimeInspectSeq += 1;
    const key = `runtime-${runtimeInspectSeq}`;
    runtimeInspectCache.set(key, payload || {});
    return key;
}

function runtimeBadgeClassForStatus(statusText) {
    const low = String(statusText || '').trim().toLowerCase();
    if (!low || low === 'stopped') return 'status-pill status-pill-neutral';
    if (['running', 'healthy', 'ok'].includes(low)) return 'status-pill status-pill-good';
    if (low === 'heartbeat_only') return 'status-pill status-pill-blue';
    if (low === 'starting' || low === 'stopping') return 'status-pill status-pill-warn';
    if (low === 'heartbeat_stale' || low === 'boot_timeout' || low === 'stale_identity') return 'status-pill status-pill-danger';
    if (
        low.includes('starting') ||
        low.includes('boot') ||
        low.includes('restart') ||
        low.includes('stopping') ||
        low.includes('resolving') ||
        low.includes('wait')
    ) {
        return 'status-pill status-pill-warn';
    }
    if (
        low.includes('stale') ||
        low.includes('fail') ||
        low.includes('error') ||
        low.includes('dead') ||
        low.includes('timeout') ||
        low.includes('missing') ||
        low.includes('orphan')
    ) {
        return 'status-pill status-pill-danger';
    }
    return 'status-pill status-pill-blue';
}

function runtimeStatusLabel(payload) {
    return String(payload && payload.status ? payload.status : (payload && payload.running ? 'running' : 'stopped'));
}

function runtimeSummaryRows(status) {
    const summary = status && status.runtime_summary ? status.runtime_summary : {};
    const guard = summary.guard || (status && status.guard) || {};
    const core = summary.core || (status && status.core) || {};
    const webui = summary.webui || (status && status.webui) || {};
    return [
        {
            label: 'Guard',
            status: runtimeStatusLabel(guard),
            badgeClass: runtimeBadgeClassForStatus(runtimeStatusLabel(guard)),
            raw: guard,
            details: [
                {key: 'PID', value: guard.pid != null ? String(guard.pid) : '-'},
                {key: 'Process Count', value: guard.process_count != null ? String(guard.process_count) : '0'},
                {key: 'Lock File', value: guard.lock_exists ? 'present' : 'missing'},
                {key: 'Stop Flag', value: guard.stop_flag ? 'present' : 'clear'},
            ],
            value: `${runtimeStatusLabel(guard)} | pid=${guard.pid != null ? guard.pid : '-'} | count=${guard.process_count != null ? guard.process_count : 0} | lock=${guard.lock_exists ? 'yes' : 'no'} | stop=${guard.stop_flag ? 'yes' : 'no'}`,
        },
        {
            label: 'Core',
            status: runtimeStatusLabel(core),
            badgeClass: runtimeBadgeClassForStatus(runtimeStatusLabel(core)),
            raw: core,
            details: [
                {key: 'PID', value: core.pid != null ? String(core.pid) : '-'},
                {key: 'Process Count', value: core.process_count != null ? String(core.process_count) : '0'},
                {key: 'Heartbeat Age', value: core.heartbeat_age_sec != null ? `${core.heartbeat_age_sec}s` : '-'},
                {key: 'State File', value: core.state_exists === false ? 'missing' : 'present or n/a'},
            ],
            value: `${runtimeStatusLabel(core)} | pid=${core.pid != null ? core.pid : '-'} | count=${core.process_count != null ? core.process_count : 0} | hb_age=${core.heartbeat_age_sec != null ? core.heartbeat_age_sec + 's' : '-'}`,
        },
        {
            label: 'Web UI',
            status: runtimeStatusLabel(webui),
            badgeClass: runtimeBadgeClassForStatus(runtimeStatusLabel(webui)),
            raw: webui,
            details: [
                {key: 'PID', value: webui.pid != null ? String(webui.pid) : '-'},
                {key: 'Process Count', value: webui.process_count != null ? String(webui.process_count) : '0'},
                {key: 'Host', value: webui.host ? String(webui.host) : 'n/a'},
                {key: 'Port', value: webui.port != null ? String(webui.port) : 'n/a'},
            ],
            value: `${runtimeStatusLabel(webui)} | pid=${webui.pid != null ? webui.pid : '-'} | count=${webui.process_count != null ? webui.process_count : 0}`,
        },
    ];
}

function formatRuntimeRawFields(title, payload) {
    return [
        `${title}`,
        '',
        JSON.stringify(payload || {}, null, 2),
    ].join('\n');
}

function selectRuntimeInspectButton(group, inspectKey) {
    document.querySelectorAll(`[data-runtime-group="${group}"]`).forEach((button) => {
        const active = (button.getAttribute('data-runtime-key') || '') === inspectKey;
        button.setAttribute('aria-pressed', active ? 'true' : 'false');
        const card = button.closest('.runtime-card');
        if (card) card.classList.toggle('is-active', active);
    });
}

function showRuntimeInspect(targetId, title, inspectKey, group) {
    const target = document.getElementById(targetId);
    if (!target) return;
    target.textContent = formatRuntimeRawFields(title, runtimeInspectCache.get(inspectKey) || {});
    selectRuntimeInspectButton(group, inspectKey);
}

function renderRuntimeCards(container, rawBox, rows, group) {
    if (!container) return;
    container.className = 'runtime-summary-grid';
    container.innerHTML = rows.map((item) => {
        const inspectKey = registerRuntimeInspectPayload(item.raw || {});
        return [
            '<div class="runtime-card">',
            '<div class="runtime-card-header">',
            `<div class="runtime-card-label">${escapeHtml(item.label)}</div>`,
            `<button type="button" class="${escapeHtml(item.badgeClass)} runtime-badge-button" data-runtime-group="${escapeHtml(group)}" data-runtime-key="${escapeHtml(inspectKey)}" data-runtime-target="${escapeHtml(rawBox ? rawBox.id : '')}" data-runtime-title="${escapeHtml(item.label + ' Raw Fields')}">${escapeHtml(item.status)}</button>`,
            '</div>',
            '<div class="runtime-card-details">',
            (Array.isArray(item.details) ? item.details : []).map((detail) => [
                '<div class="runtime-detail-row">',
                `<div class="runtime-detail-key">${escapeHtml(detail.key || '')}</div>`,
                `<div class="runtime-detail-value">${escapeHtml(detail.value || '')}</div>`,
                '</div>'
            ].join('')).join(''),
            '</div>',
            '</div>'
        ].join('');
    }).join('');
    if (rawBox && rows.length) {
        const firstButton = container.querySelector('.runtime-badge-button');
        if (firstButton) {
            showRuntimeInspect(
                firstButton.getAttribute('data-runtime-target') || rawBox.id,
                firstButton.getAttribute('data-runtime-title') || 'Runtime Raw Fields',
                firstButton.getAttribute('data-runtime-key') || '',
                group,
            );
        }
    }
}

function renderRuntimeSummary(status) {
    renderRuntimeCards(runtimeSummary, runtimeRawBox, runtimeSummaryRows(status), 'health-runtime');
}

function formatRuntimeConsole(status) {
    return runtimeSummaryRows(status).map((item) => `${item.label}: ${item.value}`).join('\n');
}

function renderGuardRuntime(status) {
    renderRuntimeCards(guardBox, guardRawBox, runtimeSummaryRows(status), 'guard-runtime');
}

function renderHeroDeck(status) {
    const alerts = status && Array.isArray(status.alerts) ? status.alerts : [];
    const numericScore = Number(status && status.health_score != null ? status.health_score : 0);
    const ratio = Math.max(0, Math.min(100, Math.round(Number(status && status.self_check_pass_ratio != null ? status.self_check_pass_ratio : 0) * 100)));
    if (heroHealthSummary) {
        heroHealthSummary.textContent = alerts.length
            ? `Health ${numericScore}/100 at ${ratio}% pass with ${alerts.length} alert${alerts.length === 1 ? '' : 's'}`
            : `Health ${numericScore}/100 with ${ratio}% pass and no active alerts`;
    }
    if (heroRouteSummary) {
        const route = status && status.last_planner_decision ? status.last_planner_decision : 'no planner decision yet';
        const summary = status && status.last_route_summary ? status.last_route_summary : 'route summary not available';
        const tool = status && status.last_action_tool ? status.last_action_tool : 'no tool used';
        heroRouteSummary.textContent = `${route} | ${summary} | ${tool}`;
    }
    if (heroOpsSummary) {
        const sessions = Number(status && status.active_http_sessions != null ? status.active_http_sessions : 0);
        const provider = status && status.search_provider ? status.search_provider : 'n/a';
        const scope = status && status.memory_scope ? status.memory_scope : 'private';
        const processMode = status && status.process_counting_mode ? status.process_counting_mode : 'n/a';
        heroOpsSummary.textContent = `${sessions} live session${sessions === 1 ? '' : 's'} | ${provider} search | ${scope} memory | ${processMode}`;
    }
}

function renderSessionPreview() {
    const session = selectedSession();
    if (!sessionBox) return;
    if (!session) {
        sessionBox.textContent = 'No session selected.';
        if (sessionProbeBox) sessionProbeBox.textContent = 'No session selected.';
        renderSessionState(null);
        renderSupervisorInspector(null, latestStatus);
        renderOverrideBadges(null);
        return;
    }
    const reflection = session.reflection || {};
    const probeResults = Array.isArray(reflection.probe_results) ? reflection.probe_results : [];
    const suggestions = Array.isArray(reflection.suggestions) ? reflection.suggestions : [];
    sessionBox.textContent = [
        `Session: ${session.session_id}`,
        `Owner: ${session.owner || '(none)'}`,
        `Turns: ${session.turn_count}`,
        '',
        'Last user:',
        session.last_user || '(none)',
        '',
        'Last assistant:',
        session.last_assistant || '(none)',
    ].join('\n');
    if (sessionProbeBox) {
        sessionProbeBox.textContent = [
            `Probe summary: ${reflection.probe_summary || 'All green'}`,
            '',
            'Findings:',
            probeResults.length ? probeResults.join('\n') : 'No supervisor issues detected.',
            '',
            'Suggestions:',
            suggestions.length ? suggestions.join('\n') : 'None',
        ].join('\n');
    }
    renderSessionState(session);
    renderSupervisorInspector(session, latestStatus);
    renderOverrideBadges(session);
}

function renderSessions() {
    const previous = sessionSelect ? (sessionSelect.value || '').trim() : '';
    if (!sessionSelect) return;
    const available = filteredSessions();
    sessionSelect.innerHTML = '';
    if (!available.length) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = '(no matching sessions)';
        sessionSelect.appendChild(option);
        renderSessionPreview();
        return;
    }
    available.forEach((session) => {
        const option = document.createElement('option');
        option.value = session.session_id;
        option.textContent = `${session.session_id} (${session.turn_count} turns)${String(session.owner || '').trim() ? ' | ' + session.owner : ''}`;
        sessionSelect.appendChild(option);
    });
    if (previous && available.some((session) => session.session_id === previous)) {
        sessionSelect.value = previous;
    }
    renderSessionPreview();
}

function renderTestRunPreview() {
    const run = selectedTestRun();
    if (!testRunBox || !testRunProbeBox || !testRunDriftGrid) return;
    if (!run) {
        testRunBox.textContent = 'No test run selected.';
        testRunProbeBox.textContent = 'No test run selected.';
        testRunDriftGrid.textContent = 'No test run selected.';
        return;
    }

    const comparison = run.comparison || {};
    const diffs = Array.isArray(comparison.diffs) ? comparison.diffs : [];
    const cliFlagged = Array.isArray(comparison.cli_flagged_probes) ? comparison.cli_flagged_probes : [];
    const httpFlagged = Array.isArray(comparison.http_flagged_probes) ? comparison.http_flagged_probes : [];
    const diffLines = diffs.length
        ? diffs.map((item) => {
            const fields = Object.keys(item.issues || {});
            return `Turn ${item.turn}: ${fields.length ? fields.join(', ') : 'difference detected'}`;
        })
        : ['None'];

    testRunBox.textContent = [
        `Run: ${run.run_id}`,
        `Session: ${run.session_name || '(unknown)'}`,
        `Generated: ${run.generated_at || '(unknown)'}`,
        `Source: ${run.session_path || '(unknown)'}`,
        `Messages: ${run.message_count || 0}`,
        `CLI turns / HTTP turns: ${comparison.cli_turns || 0} / ${comparison.http_turns || 0}`,
        `Turn count parity: ${comparison.turn_count_match ? 'OK' : 'MISMATCH'}`,
        `Drift count: ${comparison.diff_count || 0}`,
        `Flagged probes: ${comparison.flagged_probe_count || 0}`,
        `Report: ${run.report_path || ''}`,
        '',
        'Drift details:',
        diffLines.join('\n'),
    ].join('\n');

    const formatProbeRows = (label, rows) => {
        if (!rows.length) return `${label}: none`;
        return `${label}:\n` + rows.map((row) => `- Turn ${row.turn}: ${(row.lines || []).join(' | ') || 'flagged'}`).join('\n');
    };

    testRunProbeBox.textContent = [
        `Runner status: ${testRunStatusLabel(run)}`,
        '',
        formatProbeRows('CLI flagged probes', cliFlagged),
        '',
        formatProbeRows('HTTP flagged probes', httpFlagged),
    ].join('\n');

    if (diffs.length) {
        testRunDriftGrid.className = 'drift-grid';
        testRunDriftGrid.innerHTML = diffs.map((item) => {
            const issues = item.issues || {};
            const fields = Object.keys(issues);
            const rows = fields.map((fieldName) => {
                const values = issues[fieldName] || {};
                return [
                    '<div class="drift-field">',
                    `<div class="inspector-key">${escapeHtml(fieldName)}</div>`,
                    `<div class="inspector-value">CLI: ${escapeHtml(values.cli != null ? values.cli : '')}</div>`,
                    `<div class="inspector-value">HTTP: ${escapeHtml(values.http != null ? values.http : '')}</div>`,
                    '</div>'
                ].join('');
            }).join('');
            return [
                '<div class="drift-card drift-danger">',
                '<div class="drift-card-header">',
                `<div class="section-title">Turn ${escapeHtml(item.turn)}</div>`,
                '<span class="status-pill status-pill-danger">Drift</span>',
                '</div>',
                '<div class="drift-field-list">',
                rows,
                '</div>',
                '</div>'
            ].join('');
        }).join('');
    } else {
        testRunDriftGrid.className = 'drift-grid';
        testRunDriftGrid.innerHTML = '<div class="drift-card drift-good"><div class="drift-card-header"><div class="section-title">Per-Turn Drift</div><span class="status-pill status-pill-good">Clean</span></div><div class="inspector-value">No CLI/HTTP field drift detected for this run.</div></div>';
    }
}

function renderTestRuns() {
    if (!testRunSelect) return;
    const previous = (testRunSelect.value || '').trim();
    testRunSelect.innerHTML = '';
    if (!testRunsCache.length) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = '(no parity test runs)';
        testRunSelect.appendChild(option);
        renderTestRunPreview();
        return;
    }
    testRunsCache.forEach((run) => {
        const option = document.createElement('option');
        option.value = run.run_id;
        option.textContent = `${testRunStatusLabel(run)} | ${run.session_name} | ${run.generated_at || 'unknown time'}`;
        testRunSelect.appendChild(option);
    });
    if (previous && testRunsCache.some((run) => run.run_id === previous)) {
        testRunSelect.value = previous;
    }
    if (testRunBadges) {
        testRunBadges.innerHTML = testRunsCache.slice(0, 6).map((run) => `<span class="${testRunBadgeClass(run)}">${escapeHtml(testRunStatusLabel(run))} ${escapeHtml(run.session_name || run.run_id)}</span>`).join('');
    }
    renderTestRunPreview();
}

function renderTestSessionDefinitions() {
    if (!testSessionDefinitionSelect) return;
    const previous = (testSessionDefinitionSelect.value || '').trim();
    testSessionDefinitionSelect.innerHTML = '';
    if (!testSessionDefinitions.length) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = '(no saved test sessions)';
        testSessionDefinitionSelect.appendChild(option);
        return;
    }
    testSessionDefinitions.forEach((item) => {
        const option = document.createElement('option');
        option.value = item.file;
        const origin = String(item.origin || 'saved').trim();
        const rationale = origin === 'generated' ? summarizeGeneratedPriority(item) : '';
        option.textContent = `${item.name} (${item.message_count || 0} turns)${origin === 'generated' ? ' | generated' : ''}${rationale ? ' | ' + rationale : ''}`;
        if (rationale) {
            option.title = buildGeneratedPriorityTitle(item);
        }
        testSessionDefinitionSelect.appendChild(option);
    });
    if (previous && testSessionDefinitions.some((item) => item.file === previous)) {
        testSessionDefinitionSelect.value = previous;
    }
}

function renderOperatorMacros(status) {
    if (!operatorMacroSelect) return;
    const previous = String(operatorMacroSelect.value || '').trim();
    const macros = Array.isArray(status && status.operator_macros) ? status.operator_macros : [];
    operatorMacroSelect.innerHTML = '';
    const empty = document.createElement('option');
    empty.value = '';
    empty.textContent = macros.length ? '(select operator macro)' : '(no operator macros)';
    operatorMacroSelect.appendChild(empty);
    macros.forEach((macro) => {
        const option = document.createElement('option');
        option.value = String(macro.macro_id || '');
        const placeholders = Array.isArray(macro.placeholders) ? macro.placeholders : [];
        option.textContent = String(macro.label || macro.macro_id || 'macro') + (placeholders.length ? ` (${placeholders.length} fields)` : '');
        operatorMacroSelect.appendChild(option);
    });
    if (previous && macros.some((macro) => String(macro.macro_id || '') === previous)) {
        operatorMacroSelect.value = previous;
    }
}

function renderBackendCommands(status, commandsOverride = null) {
    if (!backendCommandSelect) return;
    const previous = String(backendCommandSelect.value || '').trim();
    const commands = Array.isArray(commandsOverride)
        ? commandsOverride
        : (Array.isArray(status && status.backend_commands) ? status.backend_commands : []);
    backendCommandSelect.innerHTML = '';
    const empty = document.createElement('option');
    empty.value = '';
    empty.textContent = commands.length ? '(select backend command)' : '(no backend commands)';
    backendCommandSelect.appendChild(empty);
    commands.forEach((command) => {
        const option = document.createElement('option');
        const commandId = String(command && command.command_id ? command.command_id : '').trim();
        const label = String(command && command.label ? command.label : commandId).trim();
        option.value = commandId;
        option.textContent = label;
        const details = [
            String(command && command.description ? command.description : '').trim(),
            `kind=${String(command && command.kind ? command.kind : '').trim()}`,
            `entry=${String(command && command.entry ? command.entry : '').trim()}`,
            `dynamic_args=${Boolean(command && command.allow_dynamic_args)}`,
        ].filter(Boolean);
        option.title = details.join(' | ');
        backendCommandSelect.appendChild(option);
    });
    if (previous && commands.some((row) => String(row.command_id || '') === previous)) {
        backendCommandSelect.value = previous;
    }
    if (backendCommandOutput && !String(backendCommandOutput.textContent || '').trim()) {
        backendCommandOutput.textContent = 'No backend command has run yet.';
    }
}

function selectedOperatorMacro() {
    const macroId = operatorMacroSelect ? String(operatorMacroSelect.value || '').trim() : '';
    const macros = Array.isArray(latestStatus && latestStatus.operator_macros) ? latestStatus.operator_macros : [];
    return macros.find((item) => String(item.macro_id || '') === macroId) || null;
}

function renderGovernance(policy, status) {
    const memory = policy && policy.memory && typeof policy.memory === 'object' ? policy.memory : {};
    const chatAuth = policy && policy.chat_auth && typeof policy.chat_auth === 'object' ? policy.chat_auth : {};
    const users = Array.isArray(chatAuth.users) ? chatAuth.users : [];
    const scope = String(memory.scope || (status && status.memory_scope) || 'private').trim().toLowerCase();

    if (memoryScopeSelect && ['private', 'shared', 'hybrid'].includes(scope)) memoryScopeSelect.value = scope;
    if (memoryScopeBox) {
        memoryScopeBox.textContent = [
            `Current scope: ${scope}`,
            `Memory enabled: ${Boolean(memory.enabled)}`,
            `Mode: ${String(memory.mode || '')}`,
            `Top K: ${String(memory.top_k || '')}`,
        ].join('\n');
    }
    if (chatUserSelect) {
        const current = (chatUserSelect.value || '').trim();
        chatUserSelect.innerHTML = '';
        const empty = document.createElement('option');
        empty.value = '';
        empty.textContent = users.length ? '(select chat user)' : '(no chat users)';
        chatUserSelect.appendChild(empty);
        users.forEach((user) => {
            const option = document.createElement('option');
            option.value = user;
            option.textContent = user;
            chatUserSelect.appendChild(option);
        });
        if (current && users.includes(current)) chatUserSelect.value = current;
    }
    if (chatAuthBox) {
        chatAuthBox.textContent = [
            `Login enabled: ${Boolean(chatAuth.enabled)}`,
            `Source: ${String(chatAuth.source || (status && status.chat_auth_source) || 'disabled')}`,
            `Users: ${Number(chatAuth.count || users.length || 0)}`,
            `Managed file: ${String(chatAuth.managed_path || '')}`,
            '',
            'Usernames:',
            users.length ? users.join('\n') : '(none)',
        ].join('\n');
    }
}

function setHealthBadge(score, ratio, alerts) {
    if (!healthBadge) return;
    const numericScore = Number(score || 0);
    const alertList = Array.isArray(alerts) ? alerts : [];
    const pct = Math.max(0, Math.min(100, Math.round(Number(ratio || 0) * 100)));
    healthBadge.className = numericScore >= 90 && !alertList.length ? 'status-pill status-pill-good' : (numericScore < 70 || alertList.length ? 'status-pill status-pill-danger' : 'status-pill status-pill-warn');
    healthBadge.textContent = `Health ${numericScore}/100 (${pct}%)`;
    healthBadge.title = alertList.length ? ('Alerts: ' + alertList.join('; ')) : 'No active alerts';
}

function drawMetrics(points) {
    if (!ctx) return;
    const width = metricsCanvas.width;
    const height = metricsCanvas.height;
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = '#07101d';
    ctx.fillRect(0, 0, width, height);
    if (!points || points.length < 2) {
        ctx.fillStyle = '#8ea0bb';
        ctx.font = '14px Segoe UI';
        ctx.fillText('Telemetry will appear after a few refresh cycles.', 16, 28);
        return;
    }
    const pad = 28;
    const innerWidth = width - pad * 2;
    const innerHeight = height - pad * 2;
    const recent = points.slice(-60);
    const hb = recent.map((point) => Number(point.heartbeat_age_sec || 0));
    const reqPerMin = [];
    const errPerMin = [];
    for (let index = 0; index < recent.length; index += 1) {
        if (index === 0) {
            reqPerMin.push(0);
            errPerMin.push(0);
            continue;
        }
        const dt = Math.max(1, Number(recent[index].ts || 0) - Number(recent[index - 1].ts || 0));
        const dr = Math.max(0, Number(recent[index].requests_total || 0) - Number(recent[index - 1].requests_total || 0));
        const de = Math.max(0, Number(recent[index].errors_total || 0) - Number(recent[index - 1].errors_total || 0));
        reqPerMin.push((dr * 60) / dt);
        errPerMin.push((de * 60) / dt);
    }
    const ymax = Math.max(5, ...hb, ...reqPerMin, ...errPerMin);
    const x = (index) => pad + (index / (recent.length - 1)) * innerWidth;
    const y = (value) => pad + innerHeight - (Math.max(0, value) / ymax) * innerHeight;
    ctx.strokeStyle = '#1f2d45';
    ctx.lineWidth = 1;
    for (let index = 0; index <= 4; index += 1) {
        const gy = pad + (innerHeight / 4) * index;
        ctx.beginPath();
        ctx.moveTo(pad, gy);
        ctx.lineTo(width - pad, gy);
        ctx.stroke();
    }
    function plot(values, color) {
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.beginPath();
        values.forEach((value, index) => {
            const px = x(index);
            const py = y(value);
            if (index === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
        });
        ctx.stroke();
    }
    plot(hb, '#22c55e');
    plot(reqPerMin, '#38bdf8');
    plot(errPerMin, '#ef4444');
}

async function getJson(url) {
    const response = await fetch(url, {headers: controlHeaders()});
    const payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(payload.error || payload.message || ('HTTP ' + response.status));
    return payload;
}

async function postAction(action, body = {}) {
    const response = await fetch('/api/control/action', {
        method: 'POST',
        headers: controlHeaders(),
        body: JSON.stringify({action, ...body})
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(payload.error || payload.message || ('HTTP ' + response.status));
    return payload;
}

async function refresh() {
    try {
        const results = await Promise.allSettled([
            getJson('/api/control/status'),
            getJson('/api/control/policy'),
            getJson('/api/control/metrics'),
            getJson('/api/control/sessions'),
            getJson('/api/control/test-sessions')
        ]);
        latestStatus = results[0].status === 'fulfilled' ? results[0].value : null;
        latestPolicy = results[1].status === 'fulfilled' ? results[1].value : null;
        const metrics = results[2].status === 'fulfilled' ? results[2].value : null;
        const sessions = results[3].status === 'fulfilled' ? results[3].value : null;
        const testRuns = results[4].status === 'fulfilled' ? results[4].value : null;
        if (latestStatus) {
            renderMetricGrid(latestStatus);
            renderSubconscious(latestStatus);
            renderOperatorMacros(latestStatus);
            renderBackendCommands(latestStatus);
            renderPlannerInspector(latestStatus);
            renderLedgerInspector(latestStatus);
            renderPatchReadiness(latestStatus);
            renderHealthSummary(latestStatus);
            renderActionReadiness(latestStatus);
            renderRuntimeSummary(latestStatus);
            renderRuntimeTimeline(latestStatus);
            renderRuntimeFailures(latestStatus);
            renderRuntimeArtifacts(latestStatus);
            renderArtifactDetail(currentArtifactDetail);
            renderRestartAnalytics(latestStatus);
            renderHeroDeck(latestStatus);
            runtimeNoteBar.textContent = String(latestStatus.runtime_process_note || '');
            renderGuardRuntime(latestStatus);
            setHealthBadge(latestStatus.health_score, latestStatus.self_check_pass_ratio, latestStatus.alerts || []);
        } else {
            renderSubconscious(null);
        }
        if (latestPolicy) {
            if (policyBox) policyBox.textContent = JSON.stringify(latestPolicy, null, 2);
            renderGovernance(latestPolicy, latestStatus);
        }
        if (metrics) drawMetrics(metrics.points || []);
        if (sessions) {
            sessionsCache = Array.isArray(sessions.sessions) ? sessions.sessions : [];
            renderSessions();
        } else {
            renderSessionPreview();
        }
        if (testRuns) {
            testRunsCache = Array.isArray(testRuns.reports) ? testRuns.reports : [];
            testSessionDefinitions = Array.isArray(testRuns.definitions) ? testRuns.definitions : [];
            renderTestRuns();
            renderTestSessionDefinitions();
        } else {
            renderTestRunPreview();
        }
        const failed = results.map((result, index) => ({result, index})).filter((entry) => entry.result.status !== 'fulfilled').map((entry) => ['status', 'policy', 'metrics', 'sessions', 'test-sessions'][entry.index]);
        if (!latestStatus && !latestPolicy && !metrics && !sessions && !testRuns) throw new Error('All control endpoints failed');
        setFeedback(failed.length ? 'Partial refresh (' + failed.join(', ') + ' failed) at ' + new Date().toLocaleTimeString() : 'Live status refreshed at ' + new Date().toLocaleTimeString(), failed.length ? 'warn' : 'muted');
    } catch (error) {
        setAction('Refresh failed: ' + error.message);
    }
}

function bindClick(id, handler) {
    const element = document.getElementById(id);
    if (!element) return;
    element.addEventListener('click', async (event) => {
        try {
            event.preventDefault();
            await handler(event);
        } catch (error) {
            setAction(id + ' failed: ' + (error.message || error));
        }
    });
}

if (sessionSelect) sessionSelect.addEventListener('change', renderSessionPreview);
if (sessionFilterSelect) sessionFilterSelect.addEventListener('change', renderSessions);
if (testRunSelect) testRunSelect.addEventListener('change', renderTestRunPreview);
if (patchPreviewSelect) patchPreviewSelect.addEventListener('change', () => renderPatchActionReadiness(latestStatus));
if (chatUserSelect && chatUserNameInput) {
    chatUserSelect.addEventListener('change', () => {
        const user = (chatUserSelect.value || '').trim();
        if (user) chatUserNameInput.value = user;
    });
}
navButtons.forEach((button) => {
    button.addEventListener('click', () => setActiveView(button.getAttribute('data-view-target') || 'overview'));
});

bindClick('btnInspectorToggle', async () => {
    document.body.classList.toggle('inspector-collapsed');
    setFeedback(document.body.classList.contains('inspector-collapsed') ? 'Inspector collapsed.' : 'Inspector expanded.', 'muted');
});
bindClick('btnRefresh', refresh);
bindClick('btnPatchPreviewRefresh', async () => {
    const payload = await postAction('patch_preview_list');
    if (payload.patch) {
        latestStatus = {
            ...(latestStatus || {}),
            ...payload.patch,
            patch_previews: Array.isArray(payload.previews) ? payload.previews : [],
            patch_action_readiness: payload.patch_action_readiness || (latestStatus && latestStatus.patch_action_readiness ? latestStatus.patch_action_readiness : {}),
        };
    }
    renderPatchReadiness(latestStatus || {patch_previews: Array.isArray(payload.previews) ? payload.previews : []});
    setAction(`Patch preview queue refreshed (${Array.isArray(payload.previews) ? payload.previews.length : 0} previews).`);
});
bindClick('btnPatchPreviewShow', async () => {
    const preview = patchPreviewSelect ? (patchPreviewSelect.value || '').trim() : '';
    const payload = await postAction('patch_preview_show', {preview});
    if (patchPreviewBox) {
        patchPreviewBox.textContent = payload.text || `Preview loaded: ${preview}`;
    }
    renderPatchPreviewSummary(payload.text || '', preview);
    await refresh();
    setAction(payload.text || `Preview loaded: ${preview}`);
});
bindClick('btnPatchPreviewApprove', async () => {
    const preview = patchPreviewSelect ? (patchPreviewSelect.value || '').trim() : '';
    const note = patchPreviewNote ? patchPreviewNote.value.trim() : '';
    const payload = await postAction('patch_preview_approve', {preview, note});
    if (patchPreviewBox) {
        patchPreviewBox.textContent = `${payload.text || 'Approved.'}${preview ? `\nPreview: ${preview}` : ''}${note ? `\nNote: ${note}` : ''}`;
    }
    await refresh();
    setAction(`${payload.text || 'Approved.'}${preview ? `\nPreview: ${preview}` : ''}${note ? `\nNote: ${note}` : ''}`);
});
bindClick('btnPatchPreviewReject', async () => {
    const preview = patchPreviewSelect ? (patchPreviewSelect.value || '').trim() : '';
    const note = patchPreviewNote ? patchPreviewNote.value.trim() : '';
    const payload = await postAction('patch_preview_reject', {preview, note});
    if (patchPreviewBox) {
        patchPreviewBox.textContent = `${payload.text || 'Rejected.'}${preview ? `\nPreview: ${preview}` : ''}${note ? `\nNote: ${note}` : ''}`;
    }
    await refresh();
    setAction(`${payload.text || 'Rejected.'}${preview ? `\nPreview: ${preview}` : ''}${note ? `\nNote: ${note}` : ''}`);
});
bindClick('btnPatchPreviewApply', async () => {
    const preview = patchPreviewSelect ? (patchPreviewSelect.value || '').trim() : '';
    const targetLabel = preview || 'the selected preview';
    const confirmed = window.confirm(`Apply ${targetLabel} to the live workspace? This will run the normal patch governance path, including compile and behavioral validation.`);
    if (!confirmed) {
        setAction(`Patch apply canceled for ${targetLabel}.`);
        return;
    }
    const payload = await postAction('patch_preview_apply', {preview});
    if (patchPreviewBox) {
        patchPreviewBox.textContent = `${payload.text || 'Patch apply completed.'}${preview ? `\nPreview: ${preview}` : ''}${payload.zip ? `\nZip: ${payload.zip}` : ''}`;
    }
    await refresh();
    setAction(`${payload.text || 'Patch apply completed.'}${preview ? `\nPreview: ${preview}` : ''}${payload.zip ? `\nZip: ${payload.zip}` : ''}`);
});
bindClick('btnLogout', async () => {
    await fetch('/api/control/logout', {method: 'POST', headers: controlHeaders(), body: '{}'});
    window.location.href = '/control';
});
bindClick('btnSessionsRefresh', async () => {
    const payload = await getJson('/api/control/sessions');
    sessionsCache = Array.isArray(payload.sessions) ? payload.sessions : [];
    renderSessions();
    setAction('Session list refreshed.');
});
bindClick('btnTestRunsRefresh', async () => {
    const payload = await getJson('/api/control/test-sessions');
    testRunsCache = Array.isArray(payload.reports) ? payload.reports : [];
    testSessionDefinitions = Array.isArray(payload.definitions) ? payload.definitions : [];
    renderTestRuns();
    renderTestSessionDefinitions();
    setAction('Parity test runs refreshed.');
});
bindClick('btnTestRunExecute', async () => {
    const sessionFile = testSessionDefinitionSelect ? (testSessionDefinitionSelect.value || '').trim() : '';
    if (!sessionFile) return setAction('Select a saved test session first.');
    setAction('Running parity test session: ' + sessionFile);
    const payload = await postAction('test_session_run', {session_file: sessionFile});
    testRunsCache = Array.isArray(payload.reports) ? payload.reports : testRunsCache;
    testSessionDefinitions = Array.isArray(payload.definitions) ? payload.definitions : testSessionDefinitions;
    renderTestRuns();
    renderTestSessionDefinitions();
    if (payload.latest_report && testRunSelect && payload.latest_report.run_id) {
        testRunSelect.value = payload.latest_report.run_id;
        renderTestRunPreview();
    }
    const summary = String(payload.message || 'test_session_run completed');
    const output = String(payload.stdout || '').trim();
    setAction(output ? `${summary}\n\n${output}` : summary);
});
bindClick('btnGeneratedPackRun', async () => {
    const payload = await postAction('generated_pack_run', {limit: 12, mode: 'recent'});
    testRunsCache = Array.isArray(payload.reports) ? payload.reports : testRunsCache;
    testSessionDefinitions = Array.isArray(payload.definitions) ? payload.definitions : testSessionDefinitions;
    renderTestRuns();
    renderTestSessionDefinitions();
    const results = Array.isArray(payload.results) ? payload.results : [];
    const summary = `${payload.message || 'generated_pack_run completed'}\n` + results.map((item) => `- ${item.file}: ${item.ok ? 'OK' : 'FAIL'}${item.message ? ' (' + item.message + ')' : ''}`).join('\n');
    setAction(summary.trim());
});
bindClick('btnGeneratedPriorityRun', async () => {
    const payload = await postAction('generated_pack_run', {limit: 8, mode: 'priority'});
    testRunsCache = Array.isArray(payload.reports) ? payload.reports : testRunsCache;
    testSessionDefinitions = Array.isArray(payload.definitions) ? payload.definitions : testSessionDefinitions;
    renderTestRuns();
    renderTestSessionDefinitions();
    const results = Array.isArray(payload.results) ? payload.results : [];
    const summary = `${payload.message || 'generated priority run completed'}\n` + results.map((item) => `- ${item.file}: ${item.ok ? 'OK' : 'FAIL'}${item.message ? ' (' + item.message + ')' : ''}`).join('\n');
    setAction(summary.trim());
});
bindClick('btnGeneratedQueueRunNext', async () => {
    await runNextGeneratedQueueItem();
});
bindClick('btnGeneratedQueueRunNextOps', async () => {
    await runNextGeneratedQueueItem();
});
bindClick('btnGeneratedQueueInvestigate', async () => {
    await investigateNextGeneratedQueueItem();
});
bindClick('btnGeneratedQueueInvestigateOps', async () => {
    await investigateNextGeneratedQueueItem();
});
bindClick('btnSessionOpen', async () => {
    const session = selectedSession();
    if (!session) return setAction('Select a session first.');
    window.open('/?sid=' + encodeURIComponent(session.session_id), '_blank');
});
bindClick('btnSessionCopy', async () => {
    const session = selectedSession();
    if (!session) return setAction('Select a session first.');
    try {
        await navigator.clipboard.writeText(session.session_id);
        setAction('Session ID copied: ' + session.session_id);
    } catch (_) {
        setAction('Unable to copy to clipboard. Session ID: ' + session.session_id);
    }
});
bindClick('btnTestRunCopy', async () => {
    const run = selectedTestRun();
    if (!run) return setAction('Select a test run first.');
    const value = String(run.report_path || '').trim();
    if (!value) return setAction('Selected test run has no report path.');
    try {
        await navigator.clipboard.writeText(value);
        setAction('Report path copied: ' + value);
    } catch (_) {
        setAction('Unable to copy to clipboard. Report path: ' + value);
    }
});
bindClick('btnSessionDelete', async () => {
    const session = selectedSession();
    if (!session) return setAction('Select a session first.');
    const payload = await postAction('session_delete', {session_id: session.session_id});
    sessionsCache = Array.isArray(payload.sessions) ? payload.sessions : sessionsCache.filter((item) => item.session_id !== session.session_id);
    renderSessions();
    setAction(payload.message || 'Session deleted.');
});
bindClick('btnOperatorSend', async () => {
    await sendOperatorPrompt();
});
bindClick('btnOperatorMacroApply', async () => {
    const macro = selectedOperatorMacro();
    if (!macro) {
        setAction('Select an operator macro first.');
        return;
    }
    const values = await resolveOperatorMacroValues(macro);
    if (values === null) return;
    if (operatorPromptInput) operatorPromptInput.value = renderOperatorMacroPrompt(macro, values);
    setAction('Operator macro loaded: ' + String(macro.label || macro.macro_id || 'macro'));
});
bindClick('btnOperatorMacroRun', async () => {
    const macro = selectedOperatorMacro();
    if (!macro) {
        setAction('Select an operator macro first.');
        return;
    }
    const values = await resolveOperatorMacroValues(macro);
    if (values === null) return;
    if (operatorPromptInput && !operatorPromptInput.value.trim()) {
        operatorPromptInput.value = renderOperatorMacroPrompt(macro, values);
    }
    await sendOperatorPrompt();
});
bindClick('btnOperatorNewSession', async () => {
    const newId = 'operator-' + Math.random().toString(16).slice(2, 10);
    focusOperatorSession(newId);
    renderOperatorReply({session_id: newId, user_id: 'operator', reply: 'New operator session is ready. Send a prompt to start the thread.', session: {turn_count: 0}});
    setAction('New operator session armed: ' + newId);
});
bindClick('btnOperatorInspect', async () => {
    const sid = operatorSessionIdInput ? operatorSessionIdInput.value.trim() : '';
    if (!sid) {
        setAction('No operator session is selected yet.');
        return;
    }
    await refresh();
    focusOperatorSession(sid);
    setActiveView('sessions');
    setAction('Operator session loaded in Sessions view: ' + sid);
});
bindClick('btnBackendCommandRefresh', async () => {
    const payload = await postAction('backend_command_list');
    const commands = Array.isArray(payload.commands) ? payload.commands : [];
    renderBackendCommands(latestStatus, commands);
    if (backendCommandOutput) {
        backendCommandOutput.textContent = commands.length
            ? `Loaded ${commands.length} backend commands from backend_command_deck.json.`
            : 'No backend commands are configured.';
    }
    setAction(payload.message || `backend command list refreshed (${commands.length})`);
});
bindClick('btnBackendCommandRun', async () => {
    const commandId = backendCommandSelect ? String(backendCommandSelect.value || '').trim() : '';
    if (!commandId) {
        setAction('Select a backend command first.');
        return;
    }
    const rawArgs = backendCommandArgs ? String(backendCommandArgs.value || '').trim() : '';
    const payload = await postAction('backend_command_run', {command_id: commandId, args: rawArgs});
    const commands = Array.isArray(payload.available_commands) ? payload.available_commands : null;
    if (commands) renderBackendCommands(latestStatus, commands);
    if (backendCommandOutput) {
        const output = String(payload.output || payload.stdout || payload.stderr || payload.message || '').trim();
        backendCommandOutput.textContent = output || `${commandId} completed with no output.`;
    }
    setAction(payload.message || `${commandId} completed.`);
    await refresh();
});
if (btnOperatorToggleAudio) {
    syncOperatorAudioButton();
    btnOperatorToggleAudio.addEventListener('click', () => {
        operatorVoiceOutputEnabled = !operatorVoiceOutputEnabled;
        localStorage.setItem('nova_operator_voice_output', operatorVoiceOutputEnabled ? 'on' : 'off');
        if (!operatorVoiceOutputEnabled && window.speechSynthesis) {
            window.speechSynthesis.cancel();
        }
        syncOperatorAudioButton();
        setAction(operatorVoiceOutputEnabled ? 'Operator voice output enabled.' : 'Operator voice output disabled.');
    });
}
initOperatorSpeechRecognition();
syncOperatorMicButton();
if (btnOperatorMic && OperatorSpeechRecognitionCtor) {
    btnOperatorMic.addEventListener('click', () => {
        if (!operatorRecognition) {
            initOperatorSpeechRecognition();
        }
        if (!operatorRecognition) return;
        if (operatorRecognitionActive) {
            operatorRecognition.stop();
            return;
        }
        try {
            operatorRecognition.start();
        } catch (_) {
            operatorRecognitionActive = false;
            syncOperatorMicButton();
        }
    });
}
bindClick('btnGuardStatus', async () => { const payload = await postAction('guard_status'); renderGuardRuntime({guard: payload.guard || {}, core: latestStatus && latestStatus.core ? latestStatus.core : {}, webui: latestStatus && latestStatus.webui ? latestStatus.webui : {}, runtime_summary: {guard: payload.guard || {}, core: latestStatus && latestStatus.core ? latestStatus.core : {}, webui: latestStatus && latestStatus.webui ? latestStatus.webui : {}}}); setAction(payload.message || 'guard_status done'); await refresh(); });
bindClick('btnGuardStart', async () => { const payload = await postAction('guard_start'); renderGuardRuntime({guard: payload.guard || {}, core: latestStatus && latestStatus.core ? latestStatus.core : {}, webui: latestStatus && latestStatus.webui ? latestStatus.webui : {}, runtime_summary: {guard: payload.guard || {}, core: latestStatus && latestStatus.core ? latestStatus.core : {}, webui: latestStatus && latestStatus.webui ? latestStatus.webui : {}}}); setAction(payload.message || 'guard_start done'); await refresh(); });
bindClick('btnGuardStop', async () => { const payload = await postAction('guard_stop'); renderGuardRuntime({guard: payload.guard || {}, core: latestStatus && latestStatus.core ? latestStatus.core : {}, webui: latestStatus && latestStatus.webui ? latestStatus.webui : {}, runtime_summary: {guard: payload.guard || {}, core: latestStatus && latestStatus.core ? latestStatus.core : {}, webui: latestStatus && latestStatus.webui ? latestStatus.webui : {}}}); setAction(payload.message || 'guard_stop done'); await refresh(); });
bindClick('btnGuardRestart', async () => { const payload = await postAction('guard_restart'); setAction(payload.message || 'guard_restart done'); await refresh(); });
bindClick('btnCoreStart', async () => { const payload = await postAction('nova_start'); const core = payload.core || {}; const pid = core.pid ? (' pid=' + core.pid) : ''; setAction((payload.message || 'core_start done') + pid); await refresh(); });
bindClick('btnCoreStop', async () => { const payload = await postAction('core_stop'); setAction(payload.message || 'core_stop done'); await refresh(); });
bindClick('btnCoreRestart', async () => { const payload = await postAction('core_restart'); setAction(payload.message || 'core_restart done'); await refresh(); });
bindClick('btnWebuiRestart', async () => { const confirmed = window.confirm('Restart the Web UI now? The control page will disconnect briefly and should recover after the process comes back up.'); if (!confirmed) { setAction('Web UI restart canceled.'); return; } const payload = await postAction('webui_restart'); setAction(payload.message || 'webui_restart done'); });
document.addEventListener('click', (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    const button = target.closest('.runtime-badge-button');
    if (!button) return;
    showRuntimeInspect(
        button.getAttribute('data-runtime-target') || '',
        button.getAttribute('data-runtime-title') || 'Runtime Raw Fields',
        button.getAttribute('data-runtime-key') || '',
        button.getAttribute('data-runtime-group') || '',
    );
});
document.addEventListener('click', async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;

    const inspectButton = target.closest('.artifact-inspect-button');
    if (inspectButton instanceof HTMLElement) {
        const artifact = String(inspectButton.getAttribute('data-artifact-name') || '').trim();
        if (!artifact) return;
        const payload = await postAction('runtime_artifact_show', {artifact, lines: 160});
        selectedArtifactName = artifact;
        currentArtifactDetail = payload.artifact || null;
        renderRuntimeArtifacts(latestStatus);
        renderArtifactDetail(currentArtifactDetail);
        setAction(`Loaded artifact detail: ${artifact}`);
        return;
    }

    const copyButton = target.closest('.artifact-copy-button');
    if (copyButton instanceof HTMLElement) {
        const path = String(copyButton.getAttribute('data-artifact-path') || '').trim();
        const artifact = String(copyButton.getAttribute('data-artifact-name') || '').trim() || 'artifact';
        if (!path) {
            setAction(`No path is available for ${artifact}.`);
            return;
        }
        try {
            await navigator.clipboard.writeText(path);
            setAction(`Artifact path copied: ${path}`);
        } catch (_) {
            setAction(`Unable to copy to clipboard. ${artifact} path: ${path}`);
        }
    }
});
bindClick('btnAllow', async () => { const payload = await postAction('policy_allow', {domain: (document.getElementById('domainInput').value || '').trim()}); setAction(payload.message || 'policy_allow done'); await refresh(); });
bindClick('btnRemove', async () => { const payload = await postAction('policy_remove', {domain: (document.getElementById('domainInput').value || '').trim()}); setAction(payload.message || 'policy_remove done'); await refresh(); });
bindClick('btnMode', async () => { const payload = await postAction('web_mode', {mode: document.getElementById('webMode').value}); setAction(payload.message || 'web_mode done'); await refresh(); });
bindClick('btnMemoryScope', async () => { const payload = await postAction('memory_scope_set', {scope: memoryScopeSelect ? memoryScopeSelect.value : 'private'}); setAction(payload.message || 'memory_scope_set done'); await refresh(); });
bindClick('btnSearchProvider', async () => { const payload = await postAction('search_provider', {provider: document.getElementById('searchProvider').value}); setAction(payload.message || 'search_provider done'); await refresh(); });
bindClick('btnSearchToggle', async () => { const payload = await postAction('search_provider_toggle'); setAction(payload.message || 'search_provider_toggle done'); await refresh(); });
bindClick('btnChatUserRefresh', async () => { await refresh(); setAction('Chat user list refreshed.'); });
bindClick('btnChatUserUpsert', async () => { const payload = await postAction('chat_user_upsert', {username: chatUserNameInput ? chatUserNameInput.value.trim() : '', password: chatUserPassInput ? chatUserPassInput.value : ''}); if (chatUserPassInput) chatUserPassInput.value = ''; setAction(payload.message || 'chat_user_upsert done'); await refresh(); });
bindClick('btnChatUserDelete', async () => { const username = (chatUserNameInput && chatUserNameInput.value.trim()) || (chatUserSelect && chatUserSelect.value.trim()) || ''; const payload = await postAction('chat_user_delete', {username}); if (chatUserNameInput) chatUserNameInput.value = ''; if (chatUserPassInput) chatUserPassInput.value = ''; setAction(payload.message || 'chat_user_delete done'); await refresh(); });
bindClick('btnAudit', async () => { const payload = await postAction('policy_audit'); setAction(payload.text || payload.message || 'policy_audit done'); });
bindClick('btnInspect', async () => { const payload = await postAction('inspect'); setAction(payload.report || payload.message || 'inspect done'); });
bindClick('btnNovaStart', async () => { const payload = await postAction('nova_start'); const core = payload.core || {}; const pid = core.pid ? (' pid=' + core.pid) : ''; const hb = Number.isFinite(Number(core.heartbeat_age_sec)) ? (' hb_age=' + Number(core.heartbeat_age_sec) + 's') : ''; setAction((payload.message || 'nova_start done') + (core.running ? ' (running)' : ' (starting)') + pid + hb); await refresh(); });
bindClick('btnSelfCheck', async () => { const payload = await postAction('self_check'); const checks = Array.isArray(payload.checks) ? payload.checks : []; const lines = [payload.summary || 'self_check completed']; checks.forEach((check) => lines.push(`- ${check.name}: ${check.ok ? 'OK' : 'FAIL'}${check.detail ? ' (' + check.detail + ')' : ''}`)); setAction(lines.join('\n')); await refresh(); });
bindClick('btnExportCaps', async () => { const payload = await postAction('export_capabilities'); const capabilities = payload.capabilities || {}; const fileName = payload.filename || 'capabilities_export.json'; const blob = new Blob([JSON.stringify(capabilities, null, 2)], {type: 'application/json'}); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = fileName; document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url); setAction(`Capabilities exported (${Object.keys(capabilities).length}) to ${fileName}`); });
bindClick('btnExportLedger', async () => { const payload = await postAction('export_ledger_summary', {limit: 80}); const summary = payload.summary || {}; const fileName = payload.filename || 'action_ledger_summary.json'; const blob = new Blob([JSON.stringify(summary, null, 2)], {type: 'application/json'}); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = fileName; document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url); setAction(`Action ledger summary exported to ${fileName}`); });
bindClick('btnExportBundle', async () => { const payload = await postAction('export_diagnostics_bundle'); const fileName = payload.filename || 'diagnostics_bundle.json'; const path = (payload.path || '').trim(); setAction(`Diagnostics bundle exported: ${fileName}${path ? ' @ ' + path : ''}`); });
bindClick('btnOut', async () => { const payload = await postAction('tail_log', {name: 'nova_http.out.log'}); setAction(payload.text || 'No output'); });
bindClick('btnErr', async () => { const payload = await postAction('tail_log', {name: 'nova_http.err.log'}); setAction(payload.text || 'No output'); });

if (operatorPromptInput) {
    operatorPromptInput.addEventListener('keydown', async (event) => {
        if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
            event.preventDefault();
            await sendOperatorPrompt();
        }
    });
}

window.addEventListener('error', (event) => {
    const message = event && event.message ? event.message : 'Unknown script error';
    setFeedback('UI script error: ' + message, 'danger');
});
window.addEventListener('unhandledrejection', (event) => {
    const reason = event && event.reason ? String(event.reason) : 'Unhandled promise rejection';
    setFeedback('UI async error: ' + reason, 'danger');
});

setFeedback('NYO System control linked. Fetching live status...', 'muted');
setActiveView('overview');
refresh();
setInterval(refresh, 15000);