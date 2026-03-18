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
const sessionSelect = document.getElementById('sessionSelect');
const sessionBox = document.getElementById('sessionBox');
const sessionProbeBox = document.getElementById('sessionProbeBox');
const testRunSelect = document.getElementById('testRunSelect');
const testRunBox = document.getElementById('testRunBox');
const testRunProbeBox = document.getElementById('testRunProbeBox');
const testRunBadges = document.getElementById('testRunBadges');
const testSessionDefinitionSelect = document.getElementById('testSessionDefinitionSelect');
const testRunDriftGrid = document.getElementById('testRunDriftGrid');
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
const healthSummary = document.getElementById('healthSummary');
const supervisorSummaryMain = document.getElementById('supervisorSummaryMain');
const heroHealthSummary = document.getElementById('heroHealthSummary');
const heroRouteSummary = document.getElementById('heroRouteSummary');
const heroOpsSummary = document.getElementById('heroOpsSummary');
const metricsCanvas = document.getElementById('metricsCanvas');
const ctx = metricsCanvas ? metricsCanvas.getContext('2d') : null;
const navButtons = Array.from(document.querySelectorAll('[data-view-target]'));
const mainViews = Array.from(document.querySelectorAll('.main-view'));

let sessionsCache = [];
let testRunsCache = [];
let testSessionDefinitions = [];
let latestStatus = null;
let latestPolicy = null;

function escapeHtml(text) {
    return String(text || '').replace(/[&<>"']/g, (match) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[match]));
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

function renderMetricGrid(status) {
    if (!statusKv) return;
    const keys = [
        'server_time', 'ollama_api_up', 'chat_model', 'memory_enabled', 'memory_scope', 'web_enabled',
        'search_provider', 'allow_domains_count', 'active_http_sessions', 'health_score',
        'self_check_pass_ratio', 'tool_events_total', 'memory_events_total', 'action_ledger_total',
        'last_planner_decision', 'last_route_summary', 'process_counting_mode', 'heartbeat_age_sec'
    ];
    statusKv.innerHTML = keys.map((key) => [
        '<div class="metric-cell">',
        `<div class="metric-label">${escapeHtml(key)}</div>`,
        `<div class="metric-value">${escapeHtml(status && status[key] != null ? status[key] : '')}</div>`,
        '</div>'
    ].join('')).join('');
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

function selectedSession() {
    const sid = sessionSelect ? (sessionSelect.value || '').trim() : '';
    return sessionsCache.find((item) => item.session_id === sid) || sessionsCache[0] || null;
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
    sessionSelect.innerHTML = '';
    if (!sessionsCache.length) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = '(no sessions)';
        sessionSelect.appendChild(option);
        renderSessionPreview();
        return;
    }
    sessionsCache.forEach((session) => {
        const option = document.createElement('option');
        option.value = session.session_id;
        option.textContent = `${session.session_id} (${session.turn_count} turns)`;
        sessionSelect.appendChild(option);
    });
    if (previous && sessionsCache.some((session) => session.session_id === previous)) {
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
        option.textContent = `${item.name} (${item.message_count || 0} turns)`;
        testSessionDefinitionSelect.appendChild(option);
    });
    if (previous && testSessionDefinitions.some((item) => item.file === previous)) {
        testSessionDefinitionSelect.value = previous;
    }
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
            renderPlannerInspector(latestStatus);
            renderLedgerInspector(latestStatus);
            renderHealthSummary(latestStatus);
            renderHeroDeck(latestStatus);
            runtimeNoteBar.textContent = String(latestStatus.runtime_process_note || '');
            if (guardBox) guardBox.textContent = JSON.stringify(latestStatus.guard || {}, null, 2);
            setHealthBadge(latestStatus.health_score, latestStatus.self_check_pass_ratio, latestStatus.alerts || []);
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
if (testRunSelect) testRunSelect.addEventListener('change', renderTestRunPreview);
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
bindClick('btnGuardStatus', async () => { const payload = await postAction('guard_status'); if (guardBox) guardBox.textContent = JSON.stringify(payload.guard || {}, null, 2); setAction(payload.message || 'guard_status done'); await refresh(); });
bindClick('btnGuardStart', async () => { const payload = await postAction('guard_start'); if (guardBox) guardBox.textContent = JSON.stringify(payload.guard || {}, null, 2); setAction(payload.message || 'guard_start done'); await refresh(); });
bindClick('btnGuardStop', async () => { const payload = await postAction('guard_stop'); if (guardBox) guardBox.textContent = JSON.stringify(payload.guard || {}, null, 2); setAction(payload.message || 'guard_stop done'); await refresh(); });
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