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
const taskManagerSelect = document.getElementById('taskManagerSelect');
const taskManagerPreview = document.getElementById('taskManagerPreview');
const taskManagerName = document.getElementById('taskManagerName');
const taskManagerTaskId = document.getElementById('taskManagerTaskId');
const taskManagerCategory = document.getElementById('taskManagerCategory');
const taskManagerObjective = document.getElementById('taskManagerObjective');
const taskManagerPrompt = document.getElementById('taskManagerPrompt');
const taskManagerFollowup = document.getElementById('taskManagerFollowup');
const taskManagerNotes = document.getElementById('taskManagerNotes');
const operatorSessionIdInput = document.getElementById('operatorSessionId');
const operatorMacroSelect = document.getElementById('operatorMacroSelect');
const operatorPromptInput = document.getElementById('operatorPromptInput');
const operatorPromptReply = document.getElementById('operatorPromptReply');
const btnSidebarToggle = document.getElementById('btnSidebarToggle');
const btnInspectorToggle = document.getElementById('btnInspectorToggle');
const btnOperatorToggleAudio = document.getElementById('btnOperatorToggleAudio');
const btnOperatorMic = document.getElementById('btnOperatorMic');
const backendCommandSelect = document.getElementById('backendCommandSelect');
const backendCommandArgs = document.getElementById('backendCommandArgs');
const backendCommandOutput = document.getElementById('backendCommandOutput');
const memoryScopeSelect = document.getElementById('memoryScope');
const memoryScopeBox = document.getElementById('memoryScopeBox');
const searchEndpointInput = document.getElementById('searchEndpoint');
const searchProviderPriorityInput = document.getElementById('searchProviderPriority');
const searchEndpointBox = document.getElementById('searchEndpointBox');
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
const releaseStatusGrid = document.getElementById('releaseStatusGrid');
const releaseNarrative = document.getElementById('releaseNarrative');
const releaseLedgerGrid = document.getElementById('releaseLedgerGrid');
const restartAnalytics = document.getElementById('restartAnalytics');
const telemetrySummary = document.getElementById('telemetrySummary');
const telemetryPressure = document.getElementById('telemetryPressure');
const runtimeActionReadiness = document.getElementById('runtimeActionReadiness');
const supervisorSummaryMain = document.getElementById('supervisorSummaryMain');
const guardRawBox = document.getElementById('guardRawBox');
const heroHealthSummary = document.getElementById('heroHealthSummary');
const heroRouteSummary = document.getElementById('heroRouteSummary');
const heroOpsSummary = document.getElementById('heroOpsSummary');
const heroHealthMeta = document.getElementById('heroHealthMeta');
const heroRouteMeta = document.getElementById('heroRouteMeta');
const heroOpsMeta = document.getElementById('heroOpsMeta');
const subconsciousStatusBox = document.getElementById('subconsciousStatusBox');
const subconsciousLiveList = document.getElementById('subconsciousLiveList');
const subconsciousPriorityList = document.getElementById('subconsciousPriorityList');
const generatedQueueBox = document.getElementById('generatedQueueBox');
const generatedQueueCount = document.getElementById('generatedQueueCount');
const scheduleTreeBox = document.getElementById('scheduleTreeBox');
const overviewFocusStrip = document.getElementById('overviewFocusStrip');
const centerMissionBrief = document.getElementById('centerMissionBrief');
const liveTrackingSummary = document.getElementById('liveTrackingSummary');
const liveTrackingSignal = document.getElementById('liveTrackingSignal');
const liveTrackingMeta = document.getElementById('liveTrackingMeta');
const liveTrackingStatusBadge = document.getElementById('liveTrackingStatusBadge');
const liveTrackingConsentNote = document.getElementById('liveTrackingConsentNote');
const btnLocationTrackStart = document.getElementById('btnLocationTrackStart');
const btnLocationTrackAutoArm = document.getElementById('btnLocationTrackAutoArm');
const btnLocationTrackStop = document.getElementById('btnLocationTrackStop');
const btnLocationTrackClear = document.getElementById('btnLocationTrackClear');
const metricsCanvas = document.getElementById('metricsCanvas');
const ctx = metricsCanvas ? metricsCanvas.getContext('2d') : null;
const telemetryGraphToolbar = document.getElementById('telemetryGraphToolbar');
const telemetryGraphFootnote = document.getElementById('telemetryGraphFootnote');
const telemetryGraphButtons = Array.from(document.querySelectorAll('[data-telemetry-graph]'));
const navButtons = Array.from(document.querySelectorAll('[data-view-target]'));
const mainViews = Array.from(document.querySelectorAll('.main-view'));
const centerTabBar = document.querySelector('.center-tab-bar');
const centerTabButtons = Array.from(document.querySelectorAll('[data-center-tab]'));
const centerTabPanels = Array.from(document.querySelectorAll('[data-center-panel]'));
const layerTabShells = Array.from(document.querySelectorAll('.layer-tab-shell'));
const inspectorTabBar = document.querySelector('.inspector-tab-bar');
const inspectorTabButtons = Array.from(document.querySelectorAll('[data-inspector-tab]'));
const inspectorTabPanels = Array.from(document.querySelectorAll('[data-inspector-panel]'));

let sessionsCache = [];
let testRunsCache = [];
let testSessionDefinitions = [];
let latestStatus = null;
let latestPolicy = null;
let latestMetrics = null;
let refreshInFlight = null;
let refreshQueued = false;
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
let telemetryGraphMode = 'combined';
let locationTrackingWatchId = null;
let locationTrackingLastObserved = null;
let locationTrackingLastSent = null;
let locationTrackingLastHopMeters = 0;
let locationTrackingLastError = '';
let locationTrackingSendInFlight = null;
let liveTrackingAutoArmAttempted = false;

const LIVE_TRACKING_AUTO_ARM_KEY = 'nova_live_tracking_auto_arm';
let liveTrackingAutoArmEnabled = localStorage.getItem(LIVE_TRACKING_AUTO_ARM_KEY) === 'on';

const LOCATION_SYNC_MIN_INTERVAL_MS = 10000;
const LOCATION_SYNC_MIN_DISTANCE_M = 15;

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

function orderedGeneratedPriorities(item) {
    const priorities = Array.isArray(item && item.training_priorities) ? item.training_priorities.filter((entry) => entry && typeof entry === 'object') : [];
    return priorities.slice().sort((left, right) => {
        const leftRank = generatedPriorityRank(left);
        const rightRank = generatedPriorityRank(right);
        if (leftRank !== rightRank) return leftRank - rightRank;
        const leftRobustness = Number(left && left.robustness != null ? left.robustness : 0);
        const rightRobustness = Number(right && right.robustness != null ? right.robustness : 0);
        if (leftRobustness !== rightRobustness) return rightRobustness - leftRobustness;
        return String(left && left.signal ? left.signal : '').localeCompare(String(right && right.signal ? right.signal : ''));
    });
}

function formatSeamLabel(value) {
    const raw = String(value || '').trim();
    if (!raw) return '';
    return raw.split('_').filter(Boolean).join(' ');
}

function subconsciousSeamBadgeMeta(value) {
    const seam = String(value || '').trim().toLowerCase();
    if (!seam) return null;
    if (seam.includes('session_fact_recall')) {
        return {text: 'Session Fact Recall', className: 'status-pill status-pill-warn subconscious-seam-badge'};
    }
    if (seam.includes('weather_continuation')) {
        return {text: 'Weather Continuation', className: 'status-pill status-pill-blue subconscious-seam-badge'};
    }
    if (seam.includes('retrieval_followup')) {
        return {text: 'Retrieval Follow-up', className: 'status-pill status-pill-good subconscious-seam-badge'};
    }
    if (seam.includes('memory_capture')) {
        return {text: 'Memory Capture', className: 'status-pill status-pill-danger subconscious-seam-badge'};
    }
    if (seam.includes('patch_routing')) {
        return {text: 'Patch Routing', className: 'status-pill status-pill-neutral subconscious-seam-badge'};
    }
    if (seam.includes('fulfillment')) {
        return {text: 'Fulfillment', className: 'status-pill status-pill-good subconscious-seam-badge'};
    }
    if (seam.includes('supervisor')) {
        return {text: 'Supervisor Boundary', className: 'status-pill status-pill-blue subconscious-seam-badge'};
    }
    return {text: formatSeamLabel(seam), className: 'status-pill status-pill-neutral subconscious-seam-badge'};
}

function summarizeGeneratedPriority(item) {
    const ordered = orderedGeneratedPriorities(item);
    if (!ordered.length) return '';
    const lead = ordered[0] || {};
    const urgency = String(lead.urgency || 'n/a').toLowerCase();
    const signal = String(lead.signal || 'priority').trim();
    const seam = formatSeamLabel(lead.seam || item.family_id || '');
    const score = Number(lead.robustness != null ? lead.robustness : 0);
    const shortScore = Number.isFinite(score) ? score.toFixed(2) : 'n/a';
    return `${urgency} ${signal}${seam ? ' @ ' + seam : ''} (${shortScore})`;
}

function buildGeneratedPriorityTitle(item) {
    const ordered = orderedGeneratedPriorities(item);
    if (!ordered.length) return '';
    return ordered.slice(0, 3).map((entry) => {
        const urgency = String(entry.urgency || 'n/a').toLowerCase();
        const signal = String(entry.signal || 'priority').trim();
        const seam = formatSeamLabel(entry.seam || item.family_id || '');
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


    function telemetryRecentPoints(points) {
        return Array.isArray(points) ? points.slice(-60) : [];
    }

    function telemetryRates(points) {
        const recent = telemetryRecentPoints(points);
        const requests = [];
        const errors = [];
        const errorRatio = [];
        for (let index = 0; index < recent.length; index += 1) {
            if (index === 0) {
                requests.push(0);
                errors.push(0);
                errorRatio.push(0);
                continue;
            }
            const current = recent[index] || {};
            const previous = recent[index - 1] || {};
            const dt = Math.max(1, Number(current.ts || 0) - Number(previous.ts || 0));
            const dr = Math.max(0, Number(current.requests_total || 0) - Number(previous.requests_total || 0));
            const de = Math.max(0, Number(current.errors_total || 0) - Number(previous.errors_total || 0));
            requests.push((dr * 60) / dt);
            errors.push((de * 60) / dt);
            errorRatio.push(dr > 0 ? (de / dr) * 100 : 0);
        }
        return {recent, requests, errors, errorRatio};
    }

    function telemetryRolling(values, windowSize, reducer) {
        const out = [];
        for (let index = 0; index < values.length; index += 1) {
            const start = Math.max(0, index - windowSize + 1);
            const slice = values.slice(start, index + 1);
            out.push(reducer(slice));
        }
        return out;
    }

    function setTelemetryGraphMode(mode) {
        const target = String(mode || '').trim() || 'combined';
        telemetryGraphMode = target;
        telemetryGraphButtons.forEach((button) => {
            const active = (button.getAttribute('data-telemetry-graph') || '') === target;
            button.classList.toggle('active', active);
            button.setAttribute('aria-selected', active ? 'true' : 'false');
            button.setAttribute('tabindex', active ? '0' : '-1');
        });
        renderTelemetryGraph(latestMetrics, latestStatus);
    }

    window.setTelemetryGraphMode = setTelemetryGraphMode;

    function drawTelemetryGrid(width, height, pad, rows = 4) {
        const innerHeight = height - pad * 2;
        ctx.strokeStyle = '#1f2d45';
        ctx.lineWidth = 1;
        for (let index = 0; index <= rows; index += 1) {
            const gy = pad + (innerHeight / rows) * index;
            ctx.beginPath();
            ctx.moveTo(pad, gy);
            ctx.lineTo(width - pad, gy);
            ctx.stroke();
        }
    }

    function plotTelemetrySeries(values, color, x, y, fill = false) {
        if (!values.length) return;
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.beginPath();
        values.forEach((value, index) => {
            const px = x(index);
            const py = y(value);
            if (index === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
        });
        ctx.stroke();
        if (fill) {
            const lastX = x(values.length - 1);
            const baseline = y(0);
            ctx.lineTo(lastX, baseline);
            ctx.lineTo(x(0), baseline);
            ctx.closePath();
            ctx.fillStyle = color.replace('rgb', 'rgba').replace(')', ', 0.12)').replace('#f59e0b', 'rgba(245, 158, 11, 0.12)');
            ctx.fill();
        }
    }

    function drawDependencyLanes(recent, width, height, pad) {
        const laneHeight = 30;
        const laneGap = 18;
        const startY = pad + 18;
        const labelX = pad;
        const chartLeft = pad + 98;
        const chartWidth = width - chartLeft - pad;
        const boxWidth = chartWidth / Math.max(1, recent.length);
        const lanes = [
            {label: 'Ollama API', key: 'ollama_api_up'},
            {label: 'SearXNG', key: 'searxng_ok'}
        ];
        ctx.font = '12px Consolas';
        lanes.forEach((lane, laneIndex) => {
            const y = startY + laneIndex * (laneHeight + laneGap);
            ctx.fillStyle = '#8ea0bb';
            ctx.fillText(lane.label, labelX, y + 18);
            recent.forEach((point, index) => {
                const value = point ? point[lane.key] : null;
                const ok = value === true;
                const warn = value !== true && value != null;
                ctx.fillStyle = ok ? 'rgba(34, 197, 94, 0.72)' : (warn ? 'rgba(245, 158, 11, 0.68)' : 'rgba(239, 68, 68, 0.68)');
                ctx.fillRect(chartLeft + index * boxWidth, y, Math.max(2, boxWidth - 1), laneHeight);
            });
        });
    }

    function renderTelemetryGraph(metrics, status) {
        if (!ctx || !metricsCanvas) return;
        const width = metricsCanvas.width;
        const height = metricsCanvas.height;
        ctx.clearRect(0, 0, width, height);
        ctx.fillStyle = '#07101d';
        ctx.fillRect(0, 0, width, height);

        const points = Array.isArray(metrics && metrics.points) ? metrics.points : [];
        const {recent, requests, errors, errorRatio} = telemetryRates(points);
        if (recent.length < 2) {
            ctx.fillStyle = '#8ea0bb';
            ctx.font = '14px Segoe UI';
            ctx.fillText('Telemetry will appear after a few refresh cycles.', 16, 28);
            if (telemetryGraphFootnote) {
                telemetryGraphFootnote.textContent = 'Telemetry stream is still warming up.';
            }
            return;
        }

        const pad = 28;
        const innerWidth = width - pad * 2;
        const innerHeight = height - pad * 2;
        const x = (index) => pad + (index / Math.max(1, recent.length - 1)) * innerWidth;
        let footnote = 'Green: heartbeat age | Blue: requests/min | Red: errors/min';

        if (telemetryGraphMode === 'dependencies') {
            drawDependencyLanes(recent, width, height, pad);
            const last = recent[recent.length - 1] || {};
            footnote = `Dependency lanes | Ollama ${last.ollama_api_up ? 'up' : 'down'} | SearXNG ${last.searxng_ok ? 'ready' : 'degraded'}`;
        } else {
            drawTelemetryGrid(width, height, pad);
            if (telemetryGraphMode === 'combined') {
                const hb = recent.map((point) => Number(point.heartbeat_age_sec || 0));
                const ymax = Math.max(5, ...hb, ...requests, ...errors);
                const y = (value) => pad + innerHeight - (Math.max(0, value) / ymax) * innerHeight;
                plotTelemetrySeries(hb, '#22c55e', x, y);
                plotTelemetrySeries(requests, '#38bdf8', x, y);
                plotTelemetrySeries(errors, '#ef4444', x, y);
                footnote = 'Green: heartbeat age | Blue: requests/min | Red: errors/min';
            } else if (telemetryGraphMode === 'error-ratio') {
                const ymax = Math.max(1, ...errorRatio, 5);
                const y = (value) => pad + innerHeight - (Math.max(0, value) / ymax) * innerHeight;
                plotTelemetrySeries(errorRatio, '#f59e0b', x, y);
                footnote = `Amber: error ratio | now ${errorRatio[errorRatio.length - 1].toFixed(2)}% | peak ${Math.max(...errorRatio).toFixed(2)}%`;
            } else if (telemetryGraphMode === 'heartbeat') {
                const heartbeat = recent.map((point) => Number(point.heartbeat_age_sec || 0));
                const heartbeatAvg = telemetryRolling(heartbeat, 5, (values) => values.reduce((sum, value) => sum + value, 0) / Math.max(1, values.length));
                const heartbeatPeak = telemetryRolling(heartbeat, 8, (values) => Math.max(...values));
                const ymax = Math.max(2, ...heartbeat, ...heartbeatAvg, ...heartbeatPeak);
                const y = (value) => pad + innerHeight - (Math.max(0, value) / ymax) * innerHeight;
                plotTelemetrySeries(heartbeatPeak, '#f59e0b', x, y);
                plotTelemetrySeries(heartbeatAvg, '#38bdf8', x, y);
                plotTelemetrySeries(heartbeat, '#22c55e', x, y);
                footnote = `Green: current heartbeat | Blue: rolling average | Amber: peak envelope | health ${status && status.health_score != null ? `${Number(status.health_score)}/100` : 'n/a'}`;
            }
        }

        if (telemetryGraphFootnote) {
            telemetryGraphFootnote.textContent = footnote;
        }
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

function formatDeviceCoords(lat, lon) {
    const latitude = Number(lat);
    const longitude = Number(lon);
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return 'unknown';
    return `${latitude.toFixed(5)},${longitude.toFixed(5)}`;
}

function formatMetric(value, suffix = '', digits = 1) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return 'n/a';
    return `${numeric.toFixed(digits)}${suffix}`;
}

function formatAgeSeconds(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return 'n/a';
    if (numeric < 60) return `${numeric.toFixed(1)}s`;
    const minutes = Math.floor(numeric / 60);
    const seconds = Math.round(numeric % 60);
    return `${minutes}m ${seconds}s`;
}

function formatCapturedTime(epochSeconds) {
    const numeric = Number(epochSeconds);
    if (!Number.isFinite(numeric) || numeric <= 0) return 'n/a';
    return new Date(numeric * 1000).toLocaleTimeString();
}

function haversineMeters(left, right) {
    if (!left || !right) return 0;
    const lat1 = Number(left.lat);
    const lon1 = Number(left.lon);
    const lat2 = Number(right.lat);
    const lon2 = Number(right.lon);
    if (![lat1, lon1, lat2, lon2].every(Number.isFinite)) return 0;
    const toRad = (value) => value * (Math.PI / 180);
    const earthRadius = 6371000;
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
    return earthRadius * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function liveTrackingBrowserSupported() {
    return Boolean(navigator.geolocation && typeof navigator.geolocation.watchPosition === 'function');
}

function normalizeObservedPosition(position) {
    const coords = position && position.coords ? position.coords : null;
    if (!coords) return null;
    const latitude = Number(coords.latitude);
    const longitude = Number(coords.longitude);
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return null;
    return {
        lat: latitude,
        lon: longitude,
        accuracy_m: Number.isFinite(Number(coords.accuracy)) ? Number(coords.accuracy) : null,
        altitude_m: Number.isFinite(Number(coords.altitude)) ? Number(coords.altitude) : null,
        speed_mps: Number.isFinite(Number(coords.speed)) ? Number(coords.speed) : null,
        heading_deg: Number.isFinite(Number(coords.heading)) ? Number(coords.heading) : null,
        captured_ts: Number.isFinite(Number(position.timestamp)) ? Number(position.timestamp) / 1000 : Date.now() / 1000,
    };
}

function shouldSyncObservedPosition(observation) {
    if (!observation) return false;
    if (!locationTrackingLastSent) return true;
    const elapsedMs = Math.max(0, (Number(observation.captured_ts) - Number(locationTrackingLastSent.captured_ts)) * 1000);
    const movedMeters = haversineMeters(observation, locationTrackingLastSent);
    return elapsedMs >= LOCATION_SYNC_MIN_INTERVAL_MS || movedMeters >= LOCATION_SYNC_MIN_DISTANCE_M;
}

function setLiveTrackingAutoArmEnabled(enabled) {
    liveTrackingAutoArmEnabled = Boolean(enabled);
    localStorage.setItem(LIVE_TRACKING_AUTO_ARM_KEY, liveTrackingAutoArmEnabled ? 'on' : 'off');
}

function setLiveTrackingButtons() {
    const supported = liveTrackingBrowserSupported();
    if (btnLocationTrackStart) btnLocationTrackStart.disabled = !supported || locationTrackingWatchId !== null;
    if (btnLocationTrackAutoArm) {
        btnLocationTrackAutoArm.disabled = !supported && !liveTrackingAutoArmEnabled;
        btnLocationTrackAutoArm.className = liveTrackingAutoArmEnabled ? 'btn btn-sm btn-operator-primary' : 'btn btn-sm btn-operator-alt';
        btnLocationTrackAutoArm.textContent = liveTrackingAutoArmEnabled ? 'Auto-Arm On' : 'Auto-Arm Off';
        btnLocationTrackAutoArm.setAttribute('aria-pressed', liveTrackingAutoArmEnabled ? 'true' : 'false');
    }
    if (btnLocationTrackStop) btnLocationTrackStop.disabled = locationTrackingWatchId === null;
    if (btnLocationTrackClear) btnLocationTrackClear.disabled = false;
}

function renderLiveTrackingMetaCards(rows) {
    if (!liveTrackingMeta) return;
    if (!Array.isArray(rows) || !rows.length) {
        liveTrackingMeta.innerHTML = [
            '<div class="runtime-card">',
            '<div class="runtime-card-header">',
            '<div class="runtime-card-label">Signal Details</div>',
            '</div>',
            '<div class="runtime-card-details">',
            '<div class="runtime-detail-row"><div class="runtime-detail-value">Pending</div></div>',
            '<div class="runtime-detail-row"><div class="runtime-detail-key">Location signal details pending.</div></div>',
            '</div>',
            '</div>'
        ].join('');
        return;
    }
    liveTrackingMeta.innerHTML = rows.map((row) => [
        '<div class="runtime-card">',
        '<div class="runtime-card-header">',
        `<div class="runtime-card-label">${escapeHtml(row.label || 'Detail')}</div>`,
        '</div>',
        '<div class="runtime-card-details">',
        `<div class="runtime-detail-row"><div class="runtime-detail-value">${escapeHtml(row.value || 'n/a')}</div></div>`,
        row.note ? `<div class="runtime-detail-row"><div class="runtime-detail-key">${escapeHtml(row.note)}</div></div>` : '',
        '</div>',
        '</div>'
    ].join('')).join('');
}

function renderLiveTracking(status) {
    const live = status && status.live_tracking && typeof status.live_tracking === 'object' ? status.live_tracking : {};
    const backendProvider = live && live.backend_provider && typeof live.backend_provider === 'object' ? live.backend_provider : {};
    const available = Boolean(live.available);
    const stale = Boolean(live.stale);
    const browserActive = locationTrackingWatchId !== null;
    const fallbackCoords = locationTrackingLastObserved ? formatDeviceCoords(locationTrackingLastObserved.lat, locationTrackingLastObserved.lon) : 'Awaiting first device fix.';
    const coordsText = available ? String(live.coords_text || formatDeviceCoords(live.lat, live.lon)) : fallbackCoords;
    const badgeTone = available ? (stale ? 'warn' : 'good') : (browserActive ? 'blue' : 'neutral');
    const badgeText = available ? (stale ? 'Stale Fix' : 'Live Fix') : (browserActive ? 'Listening' : 'Idle');
    const accuracyText = live.accuracy_m != null
        ? `${Math.round(Number(live.accuracy_m))}m accuracy`
        : (locationTrackingLastObserved && locationTrackingLastObserved.accuracy_m != null ? `${Math.round(Number(locationTrackingLastObserved.accuracy_m))}m accuracy` : 'Accuracy pending');
    const watchState = browserActive ? 'browser watcher active' : (liveTrackingBrowserSupported() ? 'browser watcher paused' : 'browser geolocation unavailable');
    const backendProviderText = String(backendProvider.message || '').trim() || 'Windows geolocation fallback status unknown.';
    const consentText = liveTrackingAutoArmEnabled
        ? 'Auto-arm is on for this browser. Reloading the console will try to re-enable tracking after status refresh.'
        : 'Auto-arm is off. Tracking starts only when you enable it or explicitly arm it for this browser.';
    const signalLines = [
        available ? `Runtime fix: ${coordsText}` : `Browser fix: ${coordsText}`,
        `Watch state: ${watchState}`,
        `Last hop: ${locationTrackingLastHopMeters > 0 ? `${Math.round(locationTrackingLastHopMeters)}m` : 'no movement recorded yet'}`,
    ];
    if (available) {
        signalLines.push(`Source: ${String(live.source || 'unknown')}`);
    }
    if (locationTrackingLastError) {
        signalLines.push(`Last error: ${locationTrackingLastError}`);
    }

    if (liveTrackingStatusBadge) {
        liveTrackingStatusBadge.className = `status-pill status-pill-${badgeTone}`;
        liveTrackingStatusBadge.textContent = badgeText;
    }
    if (liveTrackingSummary) {
        liveTrackingSummary.textContent = available
            ? `${coordsText} | ${accuracyText}`
            : (browserActive ? `${coordsText} | waiting for runtime sync` : 'Tracking idle. Enable browser geolocation to stream the current device fix.');
    }
    if (liveTrackingSignal) {
        liveTrackingSignal.textContent = signalLines.join('\n');
    }
    if (liveTrackingConsentNote) {
        liveTrackingConsentNote.textContent = consentText;
    }

    renderLiveTrackingMetaCards([
        {
            label: 'Signal Age',
            value: available ? formatAgeSeconds(live.age_sec) : 'n/a',
            note: available ? `captured ${formatCapturedTime(live.captured_ts)}` : 'no runtime fix yet',
        },
        {
            label: 'Accuracy / Speed',
            value: `${accuracyText} | ${live.speed_mps != null ? formatMetric(live.speed_mps, ' m/s', 2) : 'speed n/a'}`,
            note: live.heading_deg != null ? `heading ${formatMetric(live.heading_deg, ' deg', 1)}` : 'heading pending',
        },
        {
            label: 'Source / Permission',
            value: `${available ? String(live.source || 'unknown') : 'browser watch'} | ${live.permission_state || (browserActive ? 'granted' : 'n/a')}`,
            note: stale ? 'runtime snapshot is stale' : watchState,
        },
        {
            label: 'Consent / Fallback',
            value: liveTrackingAutoArmEnabled ? 'auto-arm armed in browser' : 'manual start only',
            note: backendProviderText,
        }
    ]);

    setLiveTrackingButtons();
}

async function syncLiveTrackingObservation(observation) {
    if (!observation || locationTrackingSendInFlight) return;
    locationTrackingSendInFlight = postAction('device_location_update', {
        lat: observation.lat,
        lon: observation.lon,
        accuracy_m: observation.accuracy_m,
        altitude_m: observation.altitude_m,
        speed_mps: observation.speed_mps,
        heading_deg: observation.heading_deg,
        captured_ts: observation.captured_ts,
        source: 'browser_watch',
        permission_state: 'granted'
    });
    try {
        const payload = await locationTrackingSendInFlight;
        locationTrackingLastSent = {...observation};
        if (!latestStatus || typeof latestStatus !== 'object') latestStatus = {};
        latestStatus.live_tracking = payload.live_tracking || {};
        locationTrackingLastError = '';
        renderLiveTracking(latestStatus);
    } catch (error) {
        locationTrackingLastError = String(error && error.message ? error.message : error || 'location sync failed');
        renderLiveTracking(latestStatus);
        setAction('Live tracking sync failed: ' + locationTrackingLastError);
    } finally {
        locationTrackingSendInFlight = null;
    }
}

function handleLiveTrackingSuccess(position) {
    const observation = normalizeObservedPosition(position);
    if (!observation) {
        locationTrackingLastError = 'browser returned invalid coordinates';
        renderLiveTracking(latestStatus);
        return;
    }
    locationTrackingLastHopMeters = locationTrackingLastObserved ? haversineMeters(locationTrackingLastObserved, observation) : 0;
    locationTrackingLastObserved = observation;
    locationTrackingLastError = '';
    renderLiveTracking(latestStatus);
    if (shouldSyncObservedPosition(observation)) {
        syncLiveTrackingObservation(observation);
    }
}

function handleLiveTrackingError(error) {
    const code = Number(error && error.code);
    const message = code === 1
        ? 'permission denied'
        : (code === 2 ? 'position unavailable' : (code === 3 ? 'location request timed out' : String(error && error.message ? error.message : 'geolocation failed')));
    locationTrackingLastError = message;
    renderLiveTracking(latestStatus);
    setAction('Live tracking failed: ' + message);
}

function startLiveTracking(options = {}) {
    const autoArm = Boolean(options && options.autoArm);
    const quiet = Boolean(options && options.quiet);
    if (!liveTrackingBrowserSupported()) {
        if (!quiet) setAction('Browser geolocation is not available in this control session.');
        renderLiveTracking(latestStatus);
        return false;
    }
    if (locationTrackingWatchId !== null) {
        renderLiveTracking(latestStatus);
        return true;
    }
    locationTrackingLastError = '';
    locationTrackingWatchId = navigator.geolocation.watchPosition(handleLiveTrackingSuccess, handleLiveTrackingError, {
        enableHighAccuracy: true,
        maximumAge: 5000,
        timeout: 15000,
    });
    renderLiveTracking(latestStatus);
    if (!quiet) {
        setAction(autoArm
            ? 'Live tracking auto-armed from saved browser consent.'
            : 'Live tracking enabled. Browser geolocation will stream current device fixes into the runtime.');
    }
    return true;
}

function stopLiveTracking() {
    if (locationTrackingWatchId !== null && navigator.geolocation && typeof navigator.geolocation.clearWatch === 'function') {
        navigator.geolocation.clearWatch(locationTrackingWatchId);
    }
    locationTrackingWatchId = null;
    renderLiveTracking(latestStatus);
    setAction('Live tracking paused. The last runtime snapshot remains until cleared or it expires.');
}

async function clearLiveTracking() {
    const payload = await postAction('device_location_clear');
    locationTrackingLastObserved = null;
    locationTrackingLastSent = null;
    locationTrackingLastHopMeters = 0;
    locationTrackingLastError = '';
    if (!latestStatus || typeof latestStatus !== 'object') latestStatus = {};
    latestStatus.live_tracking = payload.live_tracking || {};
    renderLiveTracking(latestStatus);
    setAction('Live tracking runtime snapshot cleared.');
}

function maybeAutoArmLiveTracking() {
    if (liveTrackingAutoArmAttempted || !liveTrackingAutoArmEnabled) {
        return;
    }
    liveTrackingAutoArmAttempted = true;
    startLiveTracking({autoArm: true, quiet: true});
}

function toggleLiveTrackingAutoArm() {
    if (liveTrackingAutoArmEnabled) {
        setLiveTrackingAutoArmEnabled(false);
        renderLiveTracking(latestStatus);
        setAction('Live tracking auto-arm disabled for this browser. Future page loads will stay manual unless you re-enable it.');
        return;
    }
    const confirmed = window.confirm('Allow NYO System Control to auto-arm live tracking each time this browser opens the control console? The browser will still control location permission, and Nova keeps only a short-lived runtime snapshot.');
    if (!confirmed) {
        setAction('Live tracking auto-arm remains off.');
        return;
    }
    setLiveTrackingAutoArmEnabled(true);
    liveTrackingAutoArmAttempted = true;
    const started = startLiveTracking({autoArm: true, quiet: true});
    renderLiveTracking(latestStatus);
    setAction(started
        ? 'Live tracking auto-arm enabled for this browser and tracking started now.'
        : 'Live tracking auto-arm enabled for this browser.');
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

function setCenterTab(name) {
    const target = String(name || '').trim();
    const targetButton = centerTabButtons.find((button) => (button.getAttribute('data-center-tab') || '') === target);
    if (!targetButton) {
        return;
    }
    const centerTabPanelWrap = document.querySelector('.center-tab-panels');
    centerTabButtons.forEach((button) => {
        const active = (button.getAttribute('data-center-tab') || '') === target;
        button.classList.toggle('active', active);
        button.setAttribute('aria-selected', active ? 'true' : 'false');
        button.tabIndex = active ? 0 : -1;
    });
    if (centerTabPanelWrap) {
        centerTabPanelWrap.classList.remove('is-empty');
    }
    centerTabPanels.forEach((panel) => {
        const visible = (panel.getAttribute('data-center-panel') || '') === target;
        panel.classList.toggle('d-none', !visible);
    });
}

function clearCenterTabs() {
    const centerTabPanelWrap = document.querySelector('.center-tab-panels');
    centerTabButtons.forEach((button, index) => {
        button.classList.remove('active');
        button.setAttribute('aria-selected', 'false');
        button.tabIndex = index === 0 ? 0 : -1;
    });
    centerTabPanels.forEach((panel) => {
        panel.classList.add('d-none');
    });
    if (centerTabPanelWrap) {
        centerTabPanelWrap.classList.add('is-empty');
    }
}

function resolveInspectorTabButton(target) {
    if (!inspectorTabBar || !target || typeof target.closest !== 'function') {
        return null;
    }
    const button = target.closest('[data-inspector-tab]');
    if (!button || !inspectorTabBar.contains(button)) {
        return null;
    }
    return button;
}

function setInspectorTab(name) {
    const target = String(name || '').trim();
    const targetButton = inspectorTabButtons.find((button) => (button.getAttribute('data-inspector-tab') || '') === target);
    const inspectorTabShell = document.querySelector('.inspector-tab-shell');
    if (!targetButton) {
        return;
    }
    inspectorTabButtons.forEach((button) => {
        const active = (button.getAttribute('data-inspector-tab') || '') === target;
        button.classList.toggle('active', active);
        button.setAttribute('aria-selected', active ? 'true' : 'false');
        button.tabIndex = active ? 0 : -1;
    });
    inspectorTabPanels.forEach((panel) => {
        panel.hidden = (panel.getAttribute('data-inspector-panel') || '') !== target;
    });
    if (inspectorTabShell) {
        inspectorTabShell.setAttribute('data-active-inspector', target);
    }
}

function focusInspectorTabByOffset(currentButton, offset) {
    if (!currentButton || !inspectorTabButtons.length) {
        return;
    }
    const currentIndex = inspectorTabButtons.indexOf(currentButton);
    if (currentIndex < 0) {
        return;
    }
    const nextIndex = (currentIndex + offset + inspectorTabButtons.length) % inspectorTabButtons.length;
    const nextButton = inspectorTabButtons[nextIndex];
    if (!nextButton) {
        return;
    }
    setInspectorTab(nextButton.getAttribute('data-inspector-tab') || 'planner');
    nextButton.focus();
}

function resolveCenterTabButton(target) {
    if (!centerTabBar || !target || typeof target.closest !== 'function') {
        return null;
    }
    const button = target.closest('[data-center-tab]');
    if (!button || !centerTabBar.contains(button)) {
        return null;
    }
    return button;
}

function focusCenterTabByOffset(currentButton, offset) {
    if (!currentButton || !centerTabButtons.length) {
        return;
    }
    const currentIndex = centerTabButtons.indexOf(currentButton);
    if (currentIndex < 0) {
        return;
    }
    const nextIndex = (currentIndex + offset + centerTabButtons.length) % centerTabButtons.length;
    const nextButton = centerTabButtons[nextIndex];
    if (!nextButton) {
        return;
    }
    setCenterTab(nextButton.getAttribute('data-center-tab') || 'system-matrix');
    nextButton.focus();
}

function getLayerTabContext(shell) {
    if (!shell) {
        return null;
    }
    return {
        shell,
        bar: shell.querySelector('.layer-tab-bar'),
        buttons: Array.from(shell.querySelectorAll('[data-layer-tab]')),
        panels: Array.from(shell.querySelectorAll('[data-layer-panel]')),
    };
}

function resolveLayerTabButton(shell, target) {
    const context = getLayerTabContext(shell);
    if (!context || !context.bar || !target || typeof target.closest !== 'function') {
        return null;
    }
    const button = target.closest('[data-layer-tab]');
    if (!button || !context.bar.contains(button)) {
        return null;
    }
    return button;
}

function setLayerTab(shell, name) {
    const context = getLayerTabContext(shell);
    const target = String(name || '').trim();
    if (!context || !context.buttons.length) {
        return;
    }
    const targetButton = context.buttons.find((button) => (button.getAttribute('data-layer-tab') || '') === target);
    if (!targetButton) {
        return;
    }
    context.buttons.forEach((button) => {
        const active = (button.getAttribute('data-layer-tab') || '') === target;
        button.classList.toggle('active', active);
        button.setAttribute('aria-selected', active ? 'true' : 'false');
        button.tabIndex = active ? 0 : -1;
    });
    context.panels.forEach((panel) => {
        panel.hidden = (panel.getAttribute('data-layer-panel') || '') !== target;
    });
}

function focusLayerTabByOffset(shell, currentButton, offset) {
    const context = getLayerTabContext(shell);
    if (!context || !currentButton || !context.buttons.length) {
        return;
    }
    const currentIndex = context.buttons.indexOf(currentButton);
    if (currentIndex < 0) {
        return;
    }
    const nextIndex = (currentIndex + offset + context.buttons.length) % context.buttons.length;
    const nextButton = context.buttons[nextIndex];
    if (!nextButton) {
        return;
    }
    setLayerTab(shell, nextButton.getAttribute('data-layer-tab') || '');
    nextButton.focus();
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
    feedbackBar.className = 'system-note-value system-note-' + (['good', 'warn', 'danger', 'info', 'muted'].includes(level) ? level : 'muted');
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
        operatorPromptReply.textContent = 'Operator channel idle.';
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
    setActionButtonLabel(btnOperatorToggleAudio, operatorVoiceOutputEnabled ? 'Voice On' : 'Voice Off');
    btnOperatorToggleAudio.classList.toggle('btn-operator-primary', operatorVoiceOutputEnabled);
    btnOperatorToggleAudio.classList.toggle('btn-operator-alt', !operatorVoiceOutputEnabled);
}

function syncOperatorMicButton() {
    if (!btnOperatorMic) return;
    if (!OperatorSpeechRecognitionCtor) {
        setActionButtonLabel(btnOperatorMic, 'Mic Unavailable');
        btnOperatorMic.disabled = true;
        return;
    }
    btnOperatorMic.disabled = false;
    setActionButtonLabel(btnOperatorMic, operatorRecognitionActive ? 'Listening...' : 'Mic Ready');
    btnOperatorMic.classList.toggle('btn-operator-primary', operatorRecognitionActive);
    btnOperatorMic.classList.toggle('btn-operator-alt', !operatorRecognitionActive);
}

function inferButtonIcon(button, labelText) {
    const id = String(button && button.id || '').toLowerCase();
    const label = String(labelText || '').toLowerCase();
    const haystack = `${id} ${label}`;

    if (haystack.includes('refresh')) return 'bi-arrow-clockwise';
    if (haystack.includes('show')) return 'bi-eye';
    if (haystack.includes('approve')) return 'bi-check2-circle';
    if (haystack.includes('reject')) return 'bi-x-circle';
    if (haystack.includes('delete') || haystack.includes('remove')) return 'bi-trash3';
    if (haystack.includes('logout')) return 'bi-box-arrow-right';
    if (haystack.includes('start')) return 'bi-play-circle';
    if (haystack.includes('stop')) return 'bi-stop-circle';
    if (haystack.includes('restart')) return 'bi-arrow-clockwise';
    if (haystack.includes('status')) return 'bi-activity';
    if (haystack.includes('allow')) return 'bi-plus-circle';
    if (haystack.includes('save') || haystack.includes('upsert')) return 'bi-floppy';
    if (haystack.includes('load')) return 'bi-folder2-open';
    if (haystack.includes('run')) return 'bi-play-circle';
    if (haystack.includes('inspect')) return 'bi-search';
    if (haystack.includes('copy')) return 'bi-copy';
    if (haystack.includes('open')) return 'bi-box-arrow-up-right';
    if (haystack.includes('send')) return 'bi-send';
    if (haystack.includes('export')) return 'bi-download';
    if (haystack.includes('tail')) return 'bi-terminal';
    if (haystack.includes('audit')) return 'bi-clipboard-data';
    if (haystack.includes('mode') || haystack.includes('scope') || haystack.includes('provider')) return 'bi-sliders2';
    if (haystack.includes('toggle')) return 'bi-toggles2';
    if (haystack.includes('voice')) return 'bi-volume-up';
    if (haystack.includes('mic') || haystack.includes('listening')) return 'bi-mic';
    if (haystack.includes('new session')) return 'bi-plus-square';
    if (haystack.includes('session')) return 'bi-chat-square-text';
    if (haystack.includes('command')) return 'bi-terminal';
    return 'bi-dot';
}

function setActionButtonLabel(button, labelText) {
    if (!button) return;
    const label = String(labelText || '').trim();
    button.dataset.label = label;
    const iconClass = button.dataset.iconClass || inferButtonIcon(button, label);
    button.dataset.iconClass = iconClass;
    button.classList.add('control-action-button');
    button.innerHTML = [
        `<i class="bi ${escapeHtml(iconClass)} control-action-icon" aria-hidden="true"></i>`,
        `<span class="control-action-label">${escapeHtml(label)}</span>`
    ].join('');
}

function decorateActionButtons(root = document) {
    const buttons = root.querySelectorAll('button.btn.btn-sm, button.subconscious-action-button, button.artifact-inspect-button, button.artifact-copy-button');
    buttons.forEach((button) => {
        if (button.classList.contains('console-toggle-button') || button.classList.contains('user-hub-icon-button')) return;
        if (button.classList.contains('subconscious-action-button')) {
            button.classList.add('control-action-button');
            return;
        }
        const existingLabel = String(button.dataset.label || button.textContent || '').trim();
        setActionButtonLabel(button, existingLabel);
    });
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

async function startAutonomyMaintenanceWorker() {
    const payload = await postAction('autonomy_maintenance_start', {});
    const runtimeWorker = payload.autonomy_maintenance && payload.autonomy_maintenance.runtime_worker ? payload.autonomy_maintenance.runtime_worker : {};
    const status = runtimeWorker.last_cycle_status || 'running';
    await refresh();
    setAction(`${payload.message || 'autonomy maintenance worker started'}\nWorker status: ${status}`);
}

async function stopAutonomyMaintenanceWorker() {
    const payload = await postAction('autonomy_maintenance_stop', {});
    const runtimeWorker = payload.autonomy_maintenance && payload.autonomy_maintenance.runtime_worker ? payload.autonomy_maintenance.runtime_worker : {};
    const status = runtimeWorker.last_cycle_status || 'stopped';
    await refresh();
    setAction(`${payload.message || 'autonomy maintenance worker stopped'}\nWorker status: ${status}`);
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
    const displayLabels = {
        subconscious_family_count: 'Families',
        subconscious_training_priority_count: 'Priorities',
        subconscious_generated_definition_count: 'Definitions',
    };
    const columnCount = 3;
    const rows = [];

    for (let index = 0; index < keys.length; index += columnCount) {
        rows.push(keys.slice(index, index + columnCount));
    }

    const standardRows = rows.slice(0, -1);
    const subconsciousRow = rows[rows.length - 1] || [];

    statusKv.innerHTML = [
        '<tbody>',
        standardRows.map((row) => [
            '<tr class="system-matrix-row">',
            row.map((key) => [
                '<td class="system-matrix-cell">',
                '<table class="system-matrix-entry" aria-hidden="true">',
                '<tbody>',
                '<tr>',
                `<th scope="row" class="system-matrix-key">${escapeHtml(displayLabels[key] || key)}</th>`,
                '</tr>',
                '<tr>',
                `<td class="system-matrix-value">${escapeHtml(status && status[key] != null ? status[key] : '')}</td>`,
                '</tr>',
                '</tbody>',
                '</table>',
                '</td>'
            ].join('')).join(''),
            '</tr>'
        ].join('')).join(''),
        '<tr class="system-matrix-section-row">',
        '<td class="system-matrix-section-cell" colspan="3">SUBCONSCIOUS</td>',
        '</tr>',
        '<tr class="system-matrix-row system-matrix-row-subconscious">',
        subconsciousRow.map((key) => [
            '<td class="system-matrix-cell">',
            '<table class="system-matrix-entry" aria-hidden="true">',
            '<tbody>',
            '<tr>',
            `<th scope="row" class="system-matrix-key">${escapeHtml(displayLabels[key] || key)}</th>`,
            '</tr>',
            '<tr>',
            `<td class="system-matrix-value">${escapeHtml(status && status[key] != null ? status[key] : '')}</td>`,
            '</tr>',
            '</tbody>',
            '</table>',
            '</td>'
        ].join('')).join(''),
        '</tr>',
        '</tbody>'
    ].join('');
}

function renderSubconscious(status) {
    const summary = status && status.subconscious_summary ? status.subconscious_summary : {};
    const liveSummary = status && status.subconscious_live_summary ? status.subconscious_live_summary : {};
    const topPriorities = Array.isArray(status && status.subconscious_top_priorities) ? status.subconscious_top_priorities : [];
    const workQueue = status && status.generated_work_queue ? status.generated_work_queue : {};
    const maintenance = status && status.autonomy_maintenance ? status.autonomy_maintenance : {};
    const runtimeWorker = maintenance && maintenance.runtime_worker ? maintenance.runtime_worker : {};
    const lastQueueRun = maintenance && maintenance.last_generated_queue_run ? maintenance.last_generated_queue_run : {};
    const queueItems = Array.isArray(workQueue && workQueue.items) ? workQueue.items : [];
    const liveSessions = Array.isArray(liveSummary && liveSummary.sessions) ? liveSummary.sessions : [];
    const pressureConfig = liveSummary && liveSummary.pressure_config ? liveSummary.pressure_config : {};
    const weakSignalThresholds = pressureConfig && pressureConfig.weak_signal_thresholds ? pressureConfig.weak_signal_thresholds : {};
    const thresholdText = Object.entries(weakSignalThresholds).map(([signal, threshold]) => `${signal}:${threshold}`).join(' | ');
    const workerStatus = runtimeWorker && runtimeWorker.last_cycle_status ? runtimeWorker.last_cycle_status : 'inactive';
    const workerInterval = runtimeWorker && runtimeWorker.interval_sec != null ? `${runtimeWorker.interval_sec}s` : 'n/a';
    const workerCycles = runtimeWorker && runtimeWorker.cycle_count != null ? runtimeWorker.cycle_count : 0;
    const lastQueueRunText = lastQueueRun && lastQueueRun.selected_file
        ? `${lastQueueRun.status || 'n/a'} | ${lastQueueRun.selected_file}`
        : (lastQueueRun && lastQueueRun.status ? `${lastQueueRun.status} | none selected` : 'n/a');
    const lastQueueReport = lastQueueRun && lastQueueRun.latest_report_status ? lastQueueRun.latest_report_status : 'n/a';

    renderMatrixTable(subconsciousStatusBox, [
        {label: 'Latest run', value: summary.generated_at || 'not available'},
        {label: 'Label', value: summary.label || 'n/a'},
        {label: 'Families', value: summary.family_count != null ? summary.family_count : 0},
        {label: 'Variations', value: summary.variation_count != null ? summary.variation_count : 0},
        {label: 'Priorities', value: summary.training_priority_count != null ? summary.training_priority_count : 0},
        {label: 'Definitions', value: summary.generated_definition_count != null ? summary.generated_definition_count : 0},
        {label: 'Worker status', value: workerStatus},
        {label: 'Worker interval', value: workerInterval},
        {label: 'Worker cycles', value: workerCycles},
        {label: 'Live tracked', value: liveSummary.tracked_session_count != null ? liveSummary.tracked_session_count : 0},
        {label: 'Live replans', value: liveSummary.replan_session_count != null ? liveSummary.replan_session_count : 0},
        {label: 'Weak thresholds', value: thresholdText || 'n/a'},
        {label: 'Open queue', value: workQueue.open_count != null ? workQueue.open_count : 0},
        {label: 'Next item', value: workQueue.next_item && workQueue.next_item.file ? workQueue.next_item.file : 'none'},
        {label: 'Last queue run', value: lastQueueRunText},
        {label: 'Last queue report', value: lastQueueReport},
        {label: 'Report path', value: summary.latest_report_path || 'n/a'},
    ], 3);

    renderInspectorList(subconsciousLiveList, liveSessions.map((item) => {
        const reasons = Array.isArray(item && item.replan_reasons) ? item.replan_reasons : [];
        const reasonText = reasons.length
            ? reasons.map((reason) => {
                const signal = reason && reason.signal ? reason.signal : 'signal';
                if (reason && reason.kind === 'weak_signal_threshold') {
                    return `${signal} ${reason.window_count}/${reason.threshold}`;
                }
                return signal;
            }).join(' | ')
            : ((Array.isArray(item && item.active_recent_signals) ? item.active_recent_signals : []).join(' | ') || 'No active reasons');
        const subject = item && item.active_subject ? ` | ${item.active_subject}` : '';
        const lastUser = item && item.last_user ? ` | ${item.last_user}` : '';
        const owner = item && item.owner ? ` [${item.owner}]` : '';
        return {
            label: `${item && item.session_id ? item.session_id : 'session'}${owner}${item && item.replan_requested ? ' [replan]' : ''}`,
            value: `${reasonText}${subject}${lastUser}`,
        };
    }));

    renderInspectorList(subconsciousPriorityList, topPriorities.map((item) => {
        const badge = subconsciousSeamBadgeMeta(item.seam);
        return {
            label: `${item.seam_label || formatSeamLabel(item.seam) || 'unknown seam'} | ${item.signal || 'signal'} [${item.urgency || 'n/a'}]`,
            badgeText: badge ? badge.text : '',
            badgeClass: badge ? badge.className : '',
            value: `${item.suggested_test_name || 'no_test_name'} (robustness=${item.robustness != null ? item.robustness : 'n/a'})`
        };
    }));

    renderInspectorList(generatedQueueBox, queueItems.map((item) => {
        const leadPriority = orderedGeneratedPriorities(item)[0] || {};
        const badge = subconsciousSeamBadgeMeta(leadPriority.seam || item.family_id || '');
        return {
            label: `${item.file || 'generated session'} [${item.latest_status || 'never_run'}]`,
            badgeText: badge ? badge.text : '',
            badgeClass: badge ? badge.className : '',
            value: `${item.opportunity_reason || 'n/a'}${item.family_id ? ' | ' + item.family_id : ''}${summarizeGeneratedPriority(item) ? ' | ' + summarizeGeneratedPriority(item) : ''}`
        };
    }));

    if (generatedQueueCount) {
        const total = queueItems.length;
        const open = workQueue.open_count != null ? workQueue.open_count : total;
        generatedQueueCount.textContent = `${total} queued | ${open} open`;
    }
}

function renderScheduleTree(status) {
    const scheduleTree = Array.isArray(status && status.schedule_tree) ? status.schedule_tree : [];
    const items = scheduleTree.map((entry) => {
        const label = String(entry && (entry.label || entry.id) ? (entry.label || entry.id) : 'schedule item');
        const owner = String(entry && entry.owner ? entry.owner : 'n/a');
        const trigger = String(entry && entry.trigger ? entry.trigger : 'n/a');
        const interval = entry && entry.interval_sec != null ? `${entry.interval_sec}s` : 'n/a';
        const lastStatus = String(entry && entry.last_status ? entry.last_status : 'unknown');
        const lastRunAt = String(entry && entry.last_run_at ? entry.last_run_at : 'n/a');
        return {
            label: `${label} [${trigger}]`,
            value: `owner=${owner} | interval=${interval} | last=${lastStatus} @ ${lastRunAt}`,
        };
    });
    renderInspectorList(scheduleTreeBox, items.length ? items : [{label: 'Schedule Tree', value: 'No schedule entries available.'}]);
}

function renderMatrixTable(container, items, columnCount = 3) {
    if (!container) return;
    const safeItems = items && items.length ? items : [{label: 'Signal', value: 'Feed pending.'}];
    const rows = [];

    for (let index = 0; index < safeItems.length; index += columnCount) {
        rows.push(safeItems.slice(index, index + columnCount));
    }

    container.innerHTML = [
        '<tbody>',
        rows.map((row) => [
            '<tr class="system-matrix-row">',
            row.map((item) => [
                '<td class="system-matrix-cell">',
                '<table class="system-matrix-entry" aria-hidden="true">',
                '<tbody>',
                '<tr>',
                `<th scope="row" class="system-matrix-key">${escapeHtml(item.label)}</th>`,
                '</tr>',
                '<tr>',
                `<td class="system-matrix-value">${escapeHtml(item.value)}</td>`,
                '</tr>',
                '</tbody>',
                '</table>',
                '</td>'
            ].join('')).join(''),
            '</tr>'
        ].join('')).join(''),
        '</tbody>'
    ].join('');
}

function renderInspectorList(container, items) {
    if (!container) return;
    const safeItems = items && items.length ? items : [{label: 'Signal', value: 'Feed pending.'}];
    container.innerHTML = [
        '<table class="section-data-table" aria-hidden="true">',
        '<tbody>',
        safeItems.map((item) => [
            '<tr class="section-data-row">',
            '<th scope="row" class="section-data-key">',
            item.badgeText
                ? `<span class="section-data-key-wrap"><span class="${escapeHtml(item.badgeClass || 'status-pill status-pill-neutral')}">${escapeHtml(item.badgeText)}</span><span>${escapeHtml(item.label)}</span></span>`
                : escapeHtml(item.label),
            '</th>',
            `<td class="section-data-value">${escapeHtml(item.value)}</td>`,
            '</tr>'
        ].join('')).join(''),
        '</tbody>',
        '</table>'
    ].join('');
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
    const lastLogLine = String(status && status.patch_last_log_line ? status.patch_last_log_line : '').trim() || 'Patch log quiet.';

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
        patchPreviewBox.textContent = 'Preview queue is empty.';
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
        runtimeTimeline.innerHTML = [
            '<tbody>',
            '<tr class="runtime-timeline-row">',
            '<td class="runtime-timeline-cell" colspan="3">',
            '<table class="runtime-timeline-entry" aria-hidden="true">',
            '<tbody>',
            '<tr><th scope="row" class="runtime-timeline-key">Runtime Event Timeline</th></tr>',
            '<tr><td class="runtime-timeline-value">Runtime lane quiet.</td></tr>',
            '</tbody>',
            '</table>',
            '</td>',
            '</tr>',
            '</tbody>'
        ].join('');
        return;
    }
    const columnCount = 3;
    const maxRows = 8;
    const limitedEvents = events.slice(0, columnCount * maxRows);
    const rows = [];
    for (let index = 0; index < limitedEvents.length; index += columnCount) {
        rows.push(limitedEvents.slice(index, index + columnCount));
    }
    runtimeTimeline.innerHTML = [
        '<tbody>',
        rows.map((row) => [
            '<tr class="runtime-timeline-row">',
            row.map((event) => {
                const tone = String(runtimeTimelineClass(event.level || '')).split(' ').pop();
                const level = String(event.level || 'info').trim().toUpperCase();
                const meta = [event.source || 'runtime', event.service || 'runtime', formatRuntimeEventTime(event.ts)]
                    .map((value) => String(value || '').trim())
                    .filter(Boolean)
                    .join(' | ');
                const detail = String(event.detail || '').trim() || 'No additional detail.';
                return [
                    `<td class="runtime-timeline-cell runtime-timeline-cell-${escapeHtml(tone)}">`,
                    '<table class="runtime-timeline-entry" aria-hidden="true">',
                    '<tbody>',
                    '<tr>',
                    `<th scope="row" class="runtime-timeline-key"><span class="runtime-timeline-keyline"><span class="runtime-timeline-dot runtime-timeline-dot-${escapeHtml(tone)}" aria-hidden="true"></span><span>${escapeHtml(event.title || 'Runtime event')}</span></span></th>`,
                    '</tr>',
                    '<tr>',
                    `<td class="runtime-timeline-meta">${escapeHtml(level)} | ${escapeHtml(meta)}</td>`,
                    '</tr>',
                    '<tr>',
                    `<td class="runtime-timeline-value">${escapeHtml(detail)}</td>`,
                    '</tr>',
                    '</tbody>',
                    '</table>',
                    '</td>'
                ].join('');
            }).join(''),
            '</tr>'
        ].join('')).join(''),
        '</tbody>'
    ].join('');
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
        runtimeFailures.innerHTML = '<div class="runtime-card"><div class="runtime-card-label">Failure Reasons</div><div class="runtime-card-details"><div class="runtime-detail-value">Fault lane clear.</div></div></div>';
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
        runtimeArtifacts.innerHTML = '<div class="artifact-card"><div class="runtime-card-label">Runtime Artifacts</div><div class="runtime-detail-value">Artifact lane clear.</div></div>';
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
        renderInspectorList(artifactDetailMeta, [{label: 'Artifact', value: 'Select an artifact to open its trace.'}]);
        artifactDetailBox.textContent = 'Artifact trace pending.';
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

function renderReleaseStatus(status) {
    const payload = status && status.release_status ? status.release_status : {};
    const latestState = String(payload.latest_state || 'no-builds');
    const latestReadinessState = String(payload.latest_readiness_state || 'no-builds');
    const latestReadyToShip = Boolean(payload.latest_ready_to_ship);
    const latestVersion = String(payload.latest_version || 'n/a');
    const latestChannel = String(payload.latest_channel || 'n/a');
    const latestLabel = String(payload.latest_label || '');
    const latestArtifactPath = String(payload.latest_artifact_path || 'n/a');
    const latestVerifiedAt = String(payload.latest_verified_at || '');
    const latestVerificationTarget = String(payload.latest_verification_target || '');
    const latestResult = String(payload.latest_validation_result || 'pending');
    const latestNote = String(payload.latest_validation_note || 'No validation note recorded.');
    const latestReadinessNote = String(payload.latest_readiness_note || 'No readiness note recorded.');
    const latestSeed = String(payload.latest_validation_seed_path || 'n/a');
    const recentEntries = Array.isArray(payload.recent_entries) ? payload.recent_entries : [];

    renderInspectorList(releaseStatusGrid, [
        {label: 'State', value: latestState},
        {label: 'Readiness', value: `${latestReadinessState} | ready_to_ship=${latestReadyToShip ? 'yes' : 'no'}`},
        {label: 'Version', value: latestVersion},
        {label: 'Channel', value: latestChannel},
        {label: 'Label', value: latestLabel || 'n/a'},
        {label: 'Result', value: latestResult},
        {label: 'Verified At', value: latestVerifiedAt || 'n/a'},
        {label: 'Verify Target', value: latestVerificationTarget || 'n/a'},
        {label: 'Artifact', value: latestArtifactPath},
        {label: 'Validation Seed', value: latestSeed},
    ]);

    if (releaseNarrative) {
        releaseNarrative.textContent = `Latest release state: ${latestState}. Readiness: ${latestReadinessState}. Validation result: ${latestResult}. ${latestReadinessNote} ${latestNote}`;
    }

    if (!releaseLedgerGrid) return;
    if (!recentEntries.length) {
        releaseLedgerGrid.innerHTML = '<div class="artifact-card"><div class="runtime-card-label">Release Ledger</div><div class="runtime-detail-value">No release entries recorded yet.</div></div>';
        return;
    }
    releaseLedgerGrid.innerHTML = recentEntries.map((entry) => [
        '<div class="artifact-card">',
        '<div class="runtime-card-header">',
        `<div class="runtime-card-label">${escapeHtml(entry.event || 'entry')} | ${escapeHtml(entry.version || 'n/a')}</div>`,
        `<span class="${escapeHtml(artifactBadgeClass(entry.result || entry.event || 'present'))}">${escapeHtml(entry.result || entry.event || 'recorded')}</span>`,
        '</div>',
        `<div class="artifact-meta">channel=${escapeHtml(entry.channel || 'n/a')} | label=${escapeHtml(entry.label || 'n/a')} | at=${escapeHtml(entry.recorded_at || 'n/a')}</div>`,
        `<div class="runtime-detail-value artifact-summary">${escapeHtml(entry.note || entry.artifact_name || 'Release ledger event recorded.')}</div>`,
        `<pre class="artifact-excerpt">${escapeHtml(entry.artifact_path || entry.verification_target_path || entry.validation_record_seed_path || '')}</pre>`,
        '</div>'
    ].join('')).join('');
}

function renderRestartAnalytics(status) {
    const payload = status && status.runtime_restart_analytics ? status.runtime_restart_analytics : {};
    const recentOutcomes = Array.isArray(payload.recent_outcomes) ? payload.recent_outcomes : [];
    if (!restartAnalytics) return;
    const flapLevel = String(payload.flap_level || 'info').toUpperCase();
    const flapSummary = payload.flap_summary || 'Restart trace pending.';
    const latestOutcome = payload.latest_outcome || 'unknown';
    const latestReason = payload.latest_reason || 'n/a';
    const lastSuccess = payload.last_success_age_sec != null ? `${payload.last_success_age_sec}s` : 'none';
    const avgBoot = payload.avg_success_boot_sec ? `${payload.avg_success_boot_sec}s` : 'n/a';
    const recentHistory = recentOutcomes.length
        ? recentOutcomes.slice(0, 3).map((item) => `${item.outcome || 'unknown'}/${item.reason || 'n/a'}/${item.observed_sec != null ? item.observed_sec : 0}s`).join(' | ')
        : 'No recent restart observations.';
    const items = [
        {
            label: 'Stability',
            value: `${flapLevel}\n${latestOutcome}:${latestReason}`,
            title: `${flapLevel} | ${flapSummary} | latest=${latestOutcome} | reason=${latestReason}`
        },
        {
            label: 'Load',
            value: `t${payload.count != null ? payload.count : 0} | 24h ${payload.recent_restart_count_24h != null ? payload.recent_restart_count_24h : 0}\n15m ${payload.recent_restart_count_15m != null ? payload.recent_restart_count_15m : 0} | 1h ${payload.recent_restart_count_1h != null ? payload.recent_restart_count_1h : 0}`,
            title: `total=${payload.count != null ? payload.count : 0} | 15m=${payload.recent_restart_count_15m != null ? payload.recent_restart_count_15m : 0} | 1h=${payload.recent_restart_count_1h != null ? payload.recent_restart_count_1h : 0} | 24h=${payload.recent_restart_count_24h != null ? payload.recent_restart_count_24h : 0}`
        },
        {
            label: 'Mix',
            value: `ok ${payload.success_count != null ? payload.success_count : 0} | fail ${payload.failure_count != null ? payload.failure_count : 0}\ncons ${payload.consecutive_failures != null ? payload.consecutive_failures : 0}`,
            title: `success=${payload.success_count != null ? payload.success_count : 0} | failure=${payload.failure_count != null ? payload.failure_count : 0} | consecutive=${payload.consecutive_failures != null ? payload.consecutive_failures : 0}`
        },
        {
            label: 'Recovery',
            value: `ok ${lastSuccess}\nboot ${avgBoot}`,
            title: `last success=${payload.last_success_age_sec != null ? `${payload.last_success_age_sec}s ago` : 'none'} | avg boot=${avgBoot}`
        },
        {label: 'History', value: recentHistory, title: recentHistory, fullRow: true},
    ];

    restartAnalytics.innerHTML = [
        '<div class="restart-analytics-grid">',
        items.map((item) => [
            `<div class="restart-analytics-card${item.fullRow ? ' restart-analytics-card-history' : ''}" title="${escapeHtml(item.title || item.value)}">`,
            `<div class="restart-analytics-key">${escapeHtml(item.label)}</div>`,
            `<div class="restart-analytics-value">${escapeHtml(item.value)}</div>`,
            '</div>'
        ].join('')).join(''),
        '</div>'
    ].join('');
}

function renderTelemetrySummary(metrics, status) {
    if (!telemetrySummary) return;
    const points = Array.isArray(metrics && metrics.points) ? metrics.points : [];
    const recent = points.slice(-60);
    const last = recent.length ? recent[recent.length - 1] : null;
    const prev = recent.length > 1 ? recent[recent.length - 2] : null;
    if (!last) {
        telemetrySummary.innerHTML = [
            '<div class="telemetry-summary-card telemetry-summary-card-wide">',
            '<div class="telemetry-summary-key">Status</div>',
            '<div class="telemetry-summary-value">Telemetry lane warming.</div>',
            '</div>'
        ].join('');
        return;
    }

    const heartbeatNow = Number(last.heartbeat_age_sec || 0);
    const averageHeartbeat = recent.length
        ? recent.reduce((sum, point) => sum + Number(point.heartbeat_age_sec || 0), 0) / recent.length
        : heartbeatNow;
    const dt = prev ? Math.max(1, Number(last.ts || 0) - Number(prev.ts || 0)) : 1;
    const requestsDelta = prev ? Math.max(0, Number(last.requests_total || 0) - Number(prev.requests_total || 0)) : 0;
    const errorsDelta = prev ? Math.max(0, Number(last.errors_total || 0) - Number(prev.errors_total || 0)) : 0;
    const requestsPerMin = (requestsDelta * 60) / dt;
    const errorsPerMin = (errorsDelta * 60) / dt;
    const requestRates = [];
    const errorRates = [];

    for (let index = 1; index < recent.length; index += 1) {
        const current = recent[index] || {};
        const previous = recent[index - 1] || {};
        const deltaT = Math.max(1, Number(current.ts || 0) - Number(previous.ts || 0));
        requestRates.push((Math.max(0, Number(current.requests_total || 0) - Number(previous.requests_total || 0)) * 60) / deltaT);
        errorRates.push((Math.max(0, Number(current.errors_total || 0) - Number(previous.errors_total || 0)) * 60) / deltaT);
    }

    const peakRequestRate = requestRates.length ? Math.max(...requestRates) : requestsPerMin;
    const peakErrorRate = errorRates.length ? Math.max(...errorRates) : errorsPerMin;
    const healthScore = status && status.health_score != null ? Number(status.health_score) : null;
    const plannerDecision = status && status.last_planner_decision ? String(status.last_planner_decision) : 'n/a';
    const routeSummary = status && status.last_route_summary ? String(status.last_route_summary) : 'Route lane pending.';

    const cards = [
        {key: 'Heartbeat Now', value: `${heartbeatNow.toFixed(1)}s`},
        {key: 'Heartbeat Avg', value: `${averageHeartbeat.toFixed(1)}s`},
        {key: 'Requests / Min', value: requestsPerMin.toFixed(1)},
        {key: 'Peak Req / Min', value: peakRequestRate.toFixed(1)},
        {key: 'Errors / Min', value: errorsPerMin.toFixed(2)},
        {key: 'Peak Err / Min', value: peakErrorRate.toFixed(2)},
        {key: 'Health Score', value: healthScore != null ? `${healthScore}/100` : 'n/a'},
        {key: 'Planner', value: plannerDecision},
        {key: 'Route Trace', value: routeSummary, wide: true},
    ];

    telemetrySummary.innerHTML = cards.map((card) => [
        `<div class="telemetry-summary-card${card.wide ? ' telemetry-summary-card-wide' : ''}">`,
        `<div class="telemetry-summary-key">${escapeHtml(card.key)}</div>`,
        `<div class="telemetry-summary-value">${escapeHtml(card.value)}</div>`,
        '</div>'
    ].join('')).join('');
}

function telemetryWindowStats(points, seconds) {
    const rows = Array.isArray(points) ? points.filter((point) => point && Number.isFinite(Number(point.ts || 0))) : [];
    if (!rows.length) return null;
    const last = rows[rows.length - 1] || {};
    const endTs = Number(last.ts || 0);
    const startTs = Math.max(0, endTs - Math.max(1, Number(seconds || 0)));
    let windowPoints = rows.filter((point) => Number(point.ts || 0) >= startTs);
    if (windowPoints.length < 2) {
        windowPoints = rows.slice(-Math.min(rows.length, 12));
    }
    if (windowPoints.length < 2) return null;

    const first = windowPoints[0] || {};
    const latest = windowPoints[windowPoints.length - 1] || {};
    const elapsed = Math.max(1, Number(latest.ts || 0) - Number(first.ts || 0));
    const requestDelta = Math.max(0, Number(latest.requests_total || 0) - Number(first.requests_total || 0));
    const errorDelta = Math.max(0, Number(latest.errors_total || 0) - Number(first.errors_total || 0));
    const heartbeatValues = windowPoints.map((point) => Number(point.heartbeat_age_sec || 0));
    const heartbeatAvg = heartbeatValues.length
        ? heartbeatValues.reduce((sum, value) => sum + value, 0) / heartbeatValues.length
        : Number(latest.heartbeat_age_sec || 0);
    const heartbeatPeak = heartbeatValues.length ? Math.max(...heartbeatValues) : Number(latest.heartbeat_age_sec || 0);
    return {
        requestRate: (requestDelta * 60) / elapsed,
        errorRate: (errorDelta * 60) / elapsed,
        heartbeatAvg,
        heartbeatPeak,
    };
}

function renderTelemetryPressure(metrics, status) {
    if (!telemetryPressure) return;
    const points = Array.isArray(metrics && metrics.points) ? metrics.points : [];
    if (points.length < 2) {
        telemetryPressure.innerHTML = [
            '<div class="telemetry-pressure-card telemetry-pressure-card-wide">',
            '<div class="telemetry-pressure-key">Status Window</div>',
            '<div class="telemetry-pressure-value">Pressure lanes warming.</div>',
            '</div>'
        ].join('');
        return;
    }

    const windows = [
        {label: '1 Minute', meta: 'burst lane', seconds: 60},
        {label: '5 Minutes', meta: 'sustained lane', seconds: 300},
        {label: '15 Minutes', meta: 'drift lane', seconds: 900},
    ].map((window) => ({...window, stats: telemetryWindowStats(points, window.seconds)}));
    const last = points[points.length - 1] || {};
    const plannerDecision = status && status.last_planner_decision ? String(status.last_planner_decision) : 'n/a';
    const routeSummary = status && status.last_route_summary ? String(status.last_route_summary) : 'Route lane pending.';
    const healthScore = status && status.health_score != null ? `${Number(status.health_score)}/100` : 'n/a';
    const peakHeartbeat = Math.max(...windows.map((window) => Number(window.stats && window.stats.heartbeatPeak || 0)));

    const windowCards = windows.map((window) => {
        const stats = window.stats;
        if (!stats) {
            return [
                '<div class="telemetry-pressure-card">',
                '<div class="telemetry-pressure-head">',
                `<div class="telemetry-pressure-label">${escapeHtml(window.label)}</div>`,
                `<div class="telemetry-pressure-meta">${escapeHtml(window.meta)}</div>`,
                '</div>',
                '<div class="telemetry-pressure-value">Sampling window still warming up.</div>',
                '</div>'
            ].join('');
        }
        return [
            '<div class="telemetry-pressure-card">',
            '<div class="telemetry-pressure-head">',
            `<div class="telemetry-pressure-label">${escapeHtml(window.label)}</div>`,
            `<div class="telemetry-pressure-meta">${escapeHtml(window.meta)}</div>`,
            '</div>',
            '<div class="telemetry-pressure-metrics">',
            '<div>',
            '<div class="telemetry-pressure-key">Ingress / Min</div>',
            `<div class="telemetry-pressure-value">${escapeHtml(stats.requestRate.toFixed(1))}</div>`,
            '</div>',
            '<div>',
            '<div class="telemetry-pressure-key">Fault / Min</div>',
            `<div class="telemetry-pressure-value">${escapeHtml(stats.errorRate.toFixed(2))}</div>`,
            '</div>',
            '<div>',
            '<div class="telemetry-pressure-key">Heartbeat Drag</div>',
            `<div class="telemetry-pressure-value">${escapeHtml(`${stats.heartbeatAvg.toFixed(1)}s`)}</div>`,
            '</div>',
            '</div>',
            '</div>'
        ].join('');
    });

    telemetryPressure.innerHTML = [
        ...windowCards,
        [
            '<div class="telemetry-pressure-card telemetry-pressure-card-wide">',
            '<div class="telemetry-pressure-head">',
            '<div class="telemetry-pressure-label">Operator Signal</div>',
            `<div class="telemetry-pressure-meta">health ${escapeHtml(healthScore)}</div>`,
            '</div>',
            '<div class="telemetry-pressure-metrics">',
            '<div>',
            '<div class="telemetry-pressure-key">Lifetime Counters</div>',
            `<div class="telemetry-pressure-value">req ${escapeHtml(String(Number(last.requests_total || 0)))}\nerr ${escapeHtml(String(Number(last.errors_total || 0)))}</div>`,
            '</div>',
            '<div>',
            '<div class="telemetry-pressure-key">Heartbeat Envelope</div>',
            `<div class="telemetry-pressure-value">now ${escapeHtml(`${Number(last.heartbeat_age_sec || 0).toFixed(1)}s`)}\npeak ${escapeHtml(`${peakHeartbeat.toFixed(1)}s`)}</div>`,
            '</div>',
            '<div>',
            '<div class="telemetry-pressure-key">Planner Trace</div>',
            `<div class="telemetry-pressure-value">${escapeHtml(`${plannerDecision}\n${routeSummary}`)}</div>`,
            '</div>',
            '</div>',
            '</div>'
        ].join('')
    ].join('');
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
        renderInspectorList(sessionStateInspector, [{label: 'Session', value: 'Session focus pending.'}]);
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
    overrideBadges.innerHTML = [
        '<span class="override-status-icon-wrap" aria-hidden="true">',
        '<i class="bi bi-sliders2-vertical override-status-icon"></i>',
        '</span>',
        '<span class="override-status-copy">',
        '<span class="override-status-label">Overrides</span>',
        `<span class="override-status-value">${escapeHtml(overrides.length ? overrides.join(' | ') : 'No active overrides')}</span>`,
        '</span>',
    ].join('');
}

function renderHealthSummary(status) {
    const alerts = status && Array.isArray(status.alerts) ? status.alerts : [];
    renderInspectorList(healthSummary, [
        {label: 'Health Score', value: status && status.health_score != null ? status.health_score : 'n/a'},
        {label: 'Pass Ratio', value: status && status.self_check_pass_ratio != null ? status.self_check_pass_ratio : 'n/a'},
        {label: 'Alerts', value: alerts.length ? alerts.join('\n') : 'Alert board clear'},
    ]);
}

function compactRouteSummary(summary, maxSegments = 4) {
    const segments = String(summary || '').split('->').map((part) => part.trim()).filter(Boolean);
    if (!segments.length) return String(summary || 'route lane not available');
    if (segments.length > maxSegments) {
        return `${segments.slice(0, 2).join(' -> ')} -> ... -> ${segments[segments.length - 1]}`;
    }
    return segments.join(' -> ');
}

function shortArtifactName(value) {
    const clean = String(value || '').trim();
    if (!clean) return 'n/a';
    const parts = clean.split(/[\\/]/).filter(Boolean);
    return parts[parts.length - 1] || clean;
}

function renderHeroMeta(container, items) {
    if (!container) return;
    const safeItems = Array.isArray(items) ? items.filter((item) => item && item.value != null && String(item.value).trim()) : [];
    container.innerHTML = safeItems.map((item) => {
        const tone = String(item.tone || '').trim();
        return `<span class="hero-meta-pill${tone ? ` is-${escapeHtml(tone)}` : ''}">${escapeHtml(item.value)}</span>`;
    }).join('');
}

function recommendedCenterTab(status) {
    const alerts = status && Array.isArray(status.alerts) ? status.alerts : [];
    const queueOpen = Number(status && status.generated_work_queue_open_count != null ? status.generated_work_queue_open_count : 0);
    const patchStatus = String(status && status.patch_status ? status.patch_status : '').trim().toLowerCase();
    const releaseReadiness = String(status && status.release_status && status.release_status.latest_readiness_state ? status.release_status.latest_readiness_state : '').trim().toLowerCase();
    if (alerts.length) return {tab: 'failure-reasons', label: 'Failure Reasons', why: `${alerts.length} live alert${alerts.length === 1 ? '' : 's'} need attention`};
    if (queueOpen > 0) return {tab: 'subconscious-watch', label: 'Subconscious Watch', why: `${queueOpen} queue item${queueOpen === 1 ? '' : 's'} are still open`};
    if (patchStatus && !patchStatus.includes('eligible') && !patchStatus.includes('ready')) {
        return {tab: 'patch-readiness', label: 'Patch Readiness', why: 'patch governance needs review'};
    }
    if (releaseReadiness && releaseReadiness !== 'ready') {
        return {tab: 'release-governance', label: 'Release Governance', why: `release candidate is ${releaseReadiness}`};
    }
    return {tab: 'system-matrix', label: 'System Matrix', why: 'runtime posture is stable enough for a general scan'};
}

function recommendedInspectorTab(status, session) {
    const alerts = status && Array.isArray(status.alerts) ? status.alerts : [];
    if (alerts.length) return {tab: 'supervisor', label: 'Supervisor', why: 'alerts are active'};
    if (session) return {tab: 'session', label: 'Session', why: 'a live thread is already in focus'};
    if (status && (status.last_planner_decision || status.last_route_summary)) return {tab: 'planner', label: 'Planner', why: 'route trace is available'};
    return {tab: 'ledger', label: 'Ledger', why: 'trace history is the next best signal'};
}

function renderOverviewFocus(status) {
    if (!overviewFocusStrip) return;
    if (!status) {
        overviewFocusStrip.innerHTML = '<div class="overview-focus-card overview-focus-card-wide"><div class="overview-focus-key">Live Focus</div><div class="overview-focus-value">Focus strip will populate after live status lands.</div></div>';
        return;
    }
    const alerts = Array.isArray(status.alerts) ? status.alerts : [];
    const route = String(status.last_planner_decision || 'n/a');
    const routeSummary = compactRouteSummary(status.last_route_summary || 'route lane not available');
    const selected = selectedSession();
    const centerTarget = recommendedCenterTab(status);
    const inspectorTarget = recommendedInspectorTab(status, selected);
    const queueOpen = Number(status.generated_work_queue_open_count != null ? status.generated_work_queue_open_count : 0);
    const queueNext = shortArtifactName(status.generated_work_queue_next_file || '');
    const heartbeatAge = Number((status.runtime_summary && status.runtime_summary.core && status.runtime_summary.core.heartbeat_age_sec != null)
        ? status.runtime_summary.core.heartbeat_age_sec
        : (status.heartbeat_age_sec != null ? status.heartbeat_age_sec : 0));
    const focusCards = [
        {
            key: 'Route Lock',
            value: `${route}\n${routeSummary}`,
        },
        {
            key: 'Runtime Posture',
            value: alerts.length
                ? `${status.health_score}/100\n${alerts.length} alert${alerts.length === 1 ? '' : 's'} active`
                : `${status.health_score}/100\nhb ${heartbeatAge.toFixed(1)}s`,
        },
        {
            key: 'Standing Queue',
            value: queueOpen > 0 ? `${queueOpen} open\nnext ${queueNext}` : 'queue clear\nno open item',
        },
        {
            key: 'Operator Focus',
            value: `${centerTarget.label}\n${centerTarget.why}`,
            actions: [
                {label: centerTarget.label, center: centerTarget.tab},
                {label: inspectorTarget.label, inspector: inspectorTarget.tab},
            ],
        },
    ];
    overviewFocusStrip.innerHTML = focusCards.map((card) => [
        `<div class="overview-focus-card${card.wide ? ' overview-focus-card-wide' : ''}">`,
        `<div class="overview-focus-key">${escapeHtml(card.key)}</div>`,
        `<div class="overview-focus-value">${escapeHtml(card.value)}</div>`,
        Array.isArray(card.actions) && card.actions.length ? [
            '<div class="overview-focus-actions">',
            card.actions.map((action) => `<button type="button" class="focus-jump-button"${action.center ? ` data-focus-center-tab="${escapeHtml(action.center)}"` : ''}${action.inspector ? ` data-focus-inspector-tab="${escapeHtml(action.inspector)}"` : ''}>${escapeHtml(action.label)}</button>`).join(''),
            '</div>'
        ].join('') : '',
        '</div>'
    ].join('')).join('');
}

function renderCenterMissionBrief(status) {
    if (!centerMissionBrief) return;
    if (!status) {
        centerMissionBrief.innerHTML = '<div class="center-brief-card center-brief-card-wide"><div class="center-brief-key">Standby</div><div class="center-brief-value">Mission brief will populate after live status lands.</div></div>';
        return;
    }
    const alerts = Array.isArray(status.alerts) ? status.alerts : [];
    const selected = selectedSession();
    const centerTarget = recommendedCenterTab(status);
    const inspectorTarget = recommendedInspectorTab(status, selected);
    const queueOpen = Number(status.generated_work_queue_open_count != null ? status.generated_work_queue_open_count : 0);
    const queueNext = shortArtifactName(status.generated_work_queue_next_file || '');
    const sessions = Number(status.active_http_sessions != null ? status.active_http_sessions : 0);
    const route = String(status.last_planner_decision || 'n/a');
    const tool = String(status.last_action_tool || 'no tool');
    const routeSummary = compactRouteSummary(status.last_route_summary || 'route lane not available', 5);
    const briefCards = [
        {
            key: 'Risk Posture',
            value: alerts.length
                ? `${status.health_score}/100\n${alerts.join('\n')}`
                : `${status.health_score}/100\nno active alerts`,
        },
        {
            key: 'Operator Load',
            value: `${sessions} live session${sessions === 1 ? '' : 's'}\nqueue ${queueOpen > 0 ? `${queueOpen} open / ${queueNext}` : 'clear'}`,
        },
        {
            key: 'Route Chain',
            value: `${route}\n${tool}\n${routeSummary}`,
            wide: true,
        },
        {
            key: 'Recommended Surface',
            value: `${centerTarget.label}\n${centerTarget.why}`,
            actions: [
                {label: `Open ${centerTarget.label}`, center: centerTarget.tab},
                {label: `Lens ${inspectorTarget.label}`, inspector: inspectorTarget.tab},
            ],
            wide: true,
        },
    ];
    centerMissionBrief.innerHTML = briefCards.map((card) => [
        `<div class="center-brief-card${card.wide ? ' center-brief-card-wide' : ''}">`,
        `<div class="center-brief-key">${escapeHtml(card.key)}</div>`,
        `<div class="center-brief-value">${escapeHtml(card.value)}</div>`,
        Array.isArray(card.actions) && card.actions.length ? [
            '<div class="center-brief-actions">',
            card.actions.map((action) => `<button type="button" class="focus-jump-button"${action.center ? ` data-focus-center-tab="${escapeHtml(action.center)}"` : ''}${action.inspector ? ` data-focus-inspector-tab="${escapeHtml(action.inspector)}"` : ''}>${escapeHtml(action.label)}</button>`).join(''),
            '</div>'
        ].join('') : '',
        '</div>'
    ].join('')).join('');
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
    renderHeroMeta(heroHealthMeta, [
        {value: `${ratio}% pass`},
        alerts.length ? {value: `${alerts.length} alert${alerts.length === 1 ? '' : 's'}`, tone: alerts.length > 1 ? 'danger' : 'warn'} : {value: 'alerts clear'},
    ]);
    if (heroRouteSummary) {
        const route = status && status.last_planner_decision ? status.last_planner_decision : 'planner decision pending';
        const summary = status && status.last_route_summary ? status.last_route_summary : 'route lane not available';
        const tool = status && status.last_action_tool ? status.last_action_tool : 'no tool used';
        const compactSummary = compactRouteSummary(summary);
        heroRouteSummary.textContent = `${route} | ${compactSummary} | ${tool}`;
        renderHeroMeta(heroRouteMeta, [
            {value: route},
            {value: tool || 'no tool'},
        ]);
    }
    if (heroOpsSummary) {
        const sessions = Number(status && status.active_http_sessions != null ? status.active_http_sessions : 0);
        const provider = status && status.search_provider ? status.search_provider : 'n/a';
        const scope = status && status.memory_scope ? status.memory_scope : 'private';
        const processMode = status && status.process_counting_mode ? status.process_counting_mode : 'n/a';
        heroOpsSummary.textContent = `${sessions} live session${sessions === 1 ? '' : 's'} | ${provider} search | ${scope} memory | ${processMode}`;
        renderHeroMeta(heroOpsMeta, [
            {value: `${sessions} live`},
            {value: provider},
            {value: scope},
        ]);
    }
}

function renderSessionPreview() {
    const session = selectedSession();
    if (!sessionBox) return;
    if (!session) {
        sessionBox.textContent = 'Session focus pending.';
        if (sessionProbeBox) sessionProbeBox.textContent = 'Probe trace pending.';
        renderSessionState(null);
        renderSupervisorInspector(null, latestStatus);
        renderOverrideBadges(null);
        renderOverviewFocus(latestStatus);
        renderCenterMissionBrief(latestStatus);
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
    renderOverviewFocus(latestStatus);
    renderCenterMissionBrief(latestStatus);
}

function renderSessions() {
    const previous = sessionSelect ? (sessionSelect.value || '').trim() : '';
    if (!sessionSelect) return;
    const available = filteredSessions();
    sessionSelect.innerHTML = '';
    if (!available.length) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = '(no live sessions)';
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
        testRunBox.textContent = 'Parity run focus pending.';
        testRunProbeBox.textContent = 'Parity trace pending.';
        testRunDriftGrid.textContent = 'Drift view pending.';
        return;
    }

    const comparison = run.comparison || {};
    const diffs = Array.isArray(comparison.diffs) ? comparison.diffs : [];
    const leftMode = String(comparison.left_mode || 'cli');
    const rightMode = String(comparison.right_mode || 'http');
    const leftLabel = String(comparison.left_label || 'CLI');
    const rightLabel = String(comparison.right_label || 'HTTP');
    const leftTurns = Number(comparison.left_turns != null ? comparison.left_turns : comparison.cli_turns || 0);
    const rightTurns = Number(comparison.right_turns != null ? comparison.right_turns : comparison.http_turns || 0);
    const leftFlagged = Array.isArray(comparison.left_flagged_probes)
        ? comparison.left_flagged_probes
        : (Array.isArray(comparison.cli_flagged_probes) ? comparison.cli_flagged_probes : []);
    const rightFlagged = Array.isArray(comparison.right_flagged_probes)
        ? comparison.right_flagged_probes
        : (Array.isArray(comparison.http_flagged_probes) ? comparison.http_flagged_probes : []);
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
        `${leftLabel} turns / ${rightLabel} turns: ${leftTurns} / ${rightTurns}`,
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
        formatProbeRows(`${leftLabel} flagged probes`, leftFlagged),
        '',
        formatProbeRows(`${rightLabel} flagged probes`, rightFlagged),
    ].join('\n');

    if (diffs.length) {
        testRunDriftGrid.className = 'drift-grid';
        testRunDriftGrid.innerHTML = diffs.map((item) => {
            const issues = item.issues || {};
            const fields = Object.keys(issues);
            const rows = fields.map((fieldName) => {
                const values = issues[fieldName] || {};
                const leftValue = values[leftMode] != null ? values[leftMode] : values.left;
                const rightValue = values[rightMode] != null ? values[rightMode] : values.right;
                return [
                    '<div class="drift-field">',
                    `<div class="inspector-key">${escapeHtml(fieldName)}</div>`,
                    `<div class="inspector-value">${escapeHtml(leftLabel)}: ${escapeHtml(leftValue != null ? leftValue : '')}</div>`,
                    `<div class="inspector-value">${escapeHtml(rightLabel)}: ${escapeHtml(rightValue != null ? rightValue : '')}</div>`,
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
        option.textContent = '(no parity runs)';
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

function realWorldTaskDefinitions() {
    return testSessionDefinitions.filter((item) => String(item && item.source ? item.source : '').trim() === 'real_world' || String(item && item.file ? item.file : '').includes('real_world/'));
}

function selectedRealWorldTask() {
    const selected = taskManagerSelect ? String(taskManagerSelect.value || '').trim() : '';
    return realWorldTaskDefinitions().find((item) => String(item.file || '').trim() === selected) || null;
}

function renderRealWorldTaskPreview() {
    if (!taskManagerPreview) return;
    const task = selectedRealWorldTask();
    if (!task) {
        taskManagerPreview.textContent = 'No real-world task selected.';
        return;
    }
    const lines = [
        `Name: ${task.name || task.file || 'task'}`,
        `File: ${task.file || 'n/a'}`,
        `Category: ${task.category || 'operator'}`,
        `Turns: ${task.message_count != null ? task.message_count : 'n/a'}`,
        `Origin: ${task.origin || 'saved'}`,
    ];
    if (task.task_id) lines.push(`Task ID: ${task.task_id}`);
    if (task.objective) lines.push(`Objective: ${task.objective}`);
    taskManagerPreview.textContent = lines.join('\n');
}

function renderRealWorldTasks() {
    if (!taskManagerSelect) return;
    const previous = String(taskManagerSelect.value || '').trim();
    const tasks = realWorldTaskDefinitions();
    taskManagerSelect.innerHTML = '';
    if (!tasks.length) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = '(no real-world tasks)';
        taskManagerSelect.appendChild(option);
        renderRealWorldTaskPreview();
        return;
    }
    tasks.forEach((item) => {
        const option = document.createElement('option');
        option.value = item.file;
        const category = String(item.category || 'operator').trim();
        option.textContent = `${item.name || item.file} | ${category} | ${item.message_count || 0} turns`;
        taskManagerSelect.appendChild(option);
    });
    if (previous && tasks.some((item) => item.file === previous)) {
        taskManagerSelect.value = previous;
    }
    renderRealWorldTaskPreview();
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
        backendCommandOutput.textContent = 'Command deck idle.';
    }
}

function selectedOperatorMacro() {
    const macroId = operatorMacroSelect ? String(operatorMacroSelect.value || '').trim() : '';
    const macros = Array.isArray(latestStatus && latestStatus.operator_macros) ? latestStatus.operator_macros : [];
    return macros.find((item) => String(item.macro_id || '') === macroId) || null;
}

function renderGovernance(policy, status) {
    const memory = policy && policy.memory && typeof policy.memory === 'object' ? policy.memory : {};
    const web = policy && policy.web && typeof policy.web === 'object' ? policy.web : {};
    const chatAuth = policy && policy.chat_auth && typeof policy.chat_auth === 'object' ? policy.chat_auth : {};
    const users = Array.isArray(chatAuth.users) ? chatAuth.users : [];
    const scope = String(memory.scope || (status && status.memory_scope) || 'private').trim().toLowerCase();
    const provider = String(web.search_provider || (status && status.search_provider) || 'html').trim().toLowerCase();
    const endpoint = String(web.search_api_endpoint || (status && status.search_api_endpoint) || '').trim();
    const providerTelemetry = status && status.provider_telemetry && typeof status.provider_telemetry === 'object' ? status.provider_telemetry : {};
    const priority = Array.isArray(web.search_provider_priority) ? web.search_provider_priority : (Array.isArray(status && status.search_provider_priority) ? status.search_provider_priority : []);

    if (memoryScopeSelect && ['private', 'shared', 'hybrid'].includes(scope)) memoryScopeSelect.value = scope;
    const providerSelect = document.getElementById('searchProvider');
    if (providerSelect && ['html', 'searxng', 'brave'].includes(provider)) providerSelect.value = provider;
    if (searchEndpointInput) searchEndpointInput.value = endpoint;
    if (searchProviderPriorityInput) searchProviderPriorityInput.value = priority.join(', ');
    if (memoryScopeBox) {
        memoryScopeBox.textContent = [
            `Current scope: ${scope}`,
            `Memory enabled: ${Boolean(memory.enabled)}`,
            `Mode: ${String(memory.mode || '')}`,
            `Top K: ${String(memory.top_k || '')}`,
        ].join('\n');
    }
    if (searchEndpointBox) {
        const hitLines = Object.entries(providerTelemetry.hits_last_window || {}).map(([name, count]) => `${name}=${count}`);
        searchEndpointBox.textContent = [
            `Provider: ${provider}`,
            `Endpoint: ${endpoint || '(not set)'}`,
            `Web enabled: ${Boolean(web.enabled)}`,
            `Priority: ${priority.length ? priority.join(', ') : '(default)'}`,
            `Probe ok: ${status && status.searxng_ok != null ? Boolean(status.searxng_ok) : 'n/a'}`,
            `Probe note: ${String((status && status.searxng_note) || 'n/a')}`,
            `Last provider hit: ${String(providerTelemetry.last_provider_used || status.last_provider_hit || 'n/a')}`,
            `Last provider query: ${String(providerTelemetry.last_provider_query || 'n/a')}`,
            `StackExchange site: ${String(providerTelemetry.stackexchange_site || 'stackoverflow')}`,
            `Hits last window: ${hitLines.length ? hitLines.join(', ') : 'n/a'}`,
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
    const toneClass = numericScore >= 90 && !alertList.length
        ? 'health-status-tile-good'
        : (numericScore < 70 || alertList.length ? 'health-status-tile-danger' : 'health-status-tile-warn');
    healthBadge.className = `health-status-tile ${toneClass}`;
    healthBadge.innerHTML = [
        '<span class="health-status-icon-wrap" aria-hidden="true">',
        '<i class="bi bi-heart-pulse-fill health-status-icon"></i>',
        '</span>',
        '<span class="health-status-copy">',
        '<span class="health-status-label">Health</span>',
        `<span class="health-status-value">${numericScore}/100</span>`,
        `<span class="health-status-label">${pct}% pass</span>`,
        '</span>',
    ].join('');
    healthBadge.title = alertList.length ? ('Alerts: ' + alertList.join('; ')) : 'No active alerts';
}

function drawMetrics(points) {
    renderTelemetryGraph({points}, latestStatus);
}

async function getJson(url) {
    const response = await fetch(url, {headers: controlHeaders(), cache: 'no-store'});
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

async function performRefresh() {
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
        latestMetrics = metrics;
        if (latestStatus) {
            renderMetricGrid(latestStatus);
            renderSubconscious(latestStatus);
            renderScheduleTree(latestStatus);
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
            renderReleaseStatus(latestStatus);
            renderRestartAnalytics(latestStatus);
            renderHeroDeck(latestStatus);
            renderLiveTracking(latestStatus);
            runtimeNoteBar.textContent = String(latestStatus.runtime_process_note || '');
            renderGuardRuntime(latestStatus);
            setHealthBadge(latestStatus.health_score, latestStatus.self_check_pass_ratio, latestStatus.alerts || []);
        } else {
            renderSubconscious(null);
            renderScheduleTree(null);
            renderLiveTracking(null);
        }
        if (latestPolicy) {
            if (policyBox) policyBox.textContent = JSON.stringify(latestPolicy, null, 2);
            renderGovernance(latestPolicy, latestStatus);
        }
        renderTelemetrySummary(latestMetrics, latestStatus);
        renderTelemetryPressure(latestMetrics, latestStatus);
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
            renderRealWorldTasks();
        } else {
            renderTestRunPreview();
            renderRealWorldTaskPreview();
        }
        renderOverviewFocus(latestStatus);
        renderCenterMissionBrief(latestStatus);
        decorateActionButtons(document);
            maybeAutoArmLiveTracking();
        const failed = results.map((result, index) => ({result, index})).filter((entry) => entry.result.status !== 'fulfilled').map((entry) => ['status', 'policy', 'metrics', 'sessions', 'test-sessions'][entry.index]);
        if (!latestStatus && !latestPolicy && !metrics && !sessions && !testRuns) throw new Error('All control endpoints failed');
        setFeedback(failed.length ? 'Partial refresh (' + failed.join(', ') + ' failed) at ' + new Date().toLocaleTimeString() : 'Live status refreshed at ' + new Date().toLocaleTimeString(), failed.length ? 'warn' : 'muted');
    } catch (error) {
        setAction('Refresh failed: ' + error.message);
    }
}

async function refresh() {
    if (refreshInFlight) {
        refreshQueued = true;
        return refreshInFlight;
    }
    do {
        refreshQueued = false;
        refreshInFlight = performRefresh();
        try {
            await refreshInFlight;
        } finally {
            refreshInFlight = null;
        }
    } while (refreshQueued);
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
if (centerTabBar) {
    centerTabBar.addEventListener('click', (event) => {
        const button = resolveCenterTabButton(event.target);
        if (!button) {
            return;
        }
        event.preventDefault();
        setCenterTab(button.getAttribute('data-center-tab') || 'system-matrix');
    });
    centerTabBar.addEventListener('keydown', (event) => {
        const button = resolveCenterTabButton(event.target);
        if (!button) {
            return;
        }
        if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
            event.preventDefault();
            focusCenterTabByOffset(button, 1);
            return;
        }
        if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
            event.preventDefault();
            focusCenterTabByOffset(button, -1);
            return;
        }
        if (event.key === 'Home') {
            event.preventDefault();
            const firstButton = centerTabButtons[0];
            if (firstButton) {
                setCenterTab(firstButton.getAttribute('data-center-tab') || 'system-matrix');
                firstButton.focus();
            }
            return;
        }
        if (event.key === 'End') {
            event.preventDefault();
            const lastButton = centerTabButtons[centerTabButtons.length - 1];
            if (lastButton) {
                setCenterTab(lastButton.getAttribute('data-center-tab') || 'system-matrix');
                lastButton.focus();
            }
            return;
        }
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            setCenterTab(button.getAttribute('data-center-tab') || 'system-matrix');
        }
    });
}

if (telemetryGraphToolbar) {
    telemetryGraphToolbar.addEventListener('click', (event) => {
        const button = event.target && typeof event.target.closest === 'function' ? event.target.closest('[data-telemetry-graph]') : null;
        if (!button) {
            return;
        }
        event.preventDefault();
        setTelemetryGraphMode(button.getAttribute('data-telemetry-graph') || 'combined');
    });
    telemetryGraphToolbar.addEventListener('keydown', (event) => {
        const button = event.target && typeof event.target.closest === 'function' ? event.target.closest('[data-telemetry-graph]') : null;
        if (!button) {
            return;
        }
        const currentIndex = telemetryGraphButtons.indexOf(button);
        if (currentIndex < 0) {
            return;
        }
        if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
            event.preventDefault();
            const next = telemetryGraphButtons[(currentIndex + 1) % telemetryGraphButtons.length];
            if (next) {
                setTelemetryGraphMode(next.getAttribute('data-telemetry-graph') || 'combined');
                next.focus();
            }
            return;
        }
        if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
            event.preventDefault();
            const next = telemetryGraphButtons[(currentIndex - 1 + telemetryGraphButtons.length) % telemetryGraphButtons.length];
            if (next) {
                setTelemetryGraphMode(next.getAttribute('data-telemetry-graph') || 'combined');
                next.focus();
            }
            return;
        }
        if (event.key === 'Home') {
            event.preventDefault();
            const first = telemetryGraphButtons[0];
            if (first) {
                setTelemetryGraphMode(first.getAttribute('data-telemetry-graph') || 'combined');
                first.focus();
            }
            return;
        }
        if (event.key === 'End') {
            event.preventDefault();
            const last = telemetryGraphButtons[telemetryGraphButtons.length - 1];
            if (last) {
                setTelemetryGraphMode(last.getAttribute('data-telemetry-graph') || 'combined');
                last.focus();
            }
            return;
        }
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            setTelemetryGraphMode(button.getAttribute('data-telemetry-graph') || 'combined');
        }
    });
}

if (inspectorTabBar) {
    inspectorTabBar.addEventListener('click', (event) => {
        const button = resolveInspectorTabButton(event.target);
        if (!button) {
            return;
        }
        event.preventDefault();
        setInspectorTab(button.getAttribute('data-inspector-tab') || 'planner');
    });
    inspectorTabBar.addEventListener('keydown', (event) => {
        const button = resolveInspectorTabButton(event.target);
        if (!button) {
            return;
        }
        if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
            event.preventDefault();
            focusInspectorTabByOffset(button, 1);
            return;
        }
        if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
            event.preventDefault();
            focusInspectorTabByOffset(button, -1);
            return;
        }
        if (event.key === 'Home') {
            event.preventDefault();
            const firstButton = inspectorTabButtons[0];
            if (firstButton) {
                setInspectorTab(firstButton.getAttribute('data-inspector-tab') || 'planner');
                firstButton.focus();
            }
            return;
        }
        if (event.key === 'End') {
            event.preventDefault();
            const lastButton = inspectorTabButtons[inspectorTabButtons.length - 1];
            if (lastButton) {
                setInspectorTab(lastButton.getAttribute('data-inspector-tab') || 'planner');
                lastButton.focus();
            }
            return;
        }
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            setInspectorTab(button.getAttribute('data-inspector-tab') || 'planner');
        }
    });
}

layerTabShells.forEach((shell) => {
    const context = getLayerTabContext(shell);
    if (!context || !context.bar || !context.buttons.length) {
        return;
    }
    context.bar.addEventListener('click', (event) => {
        const button = resolveLayerTabButton(shell, event.target);
        if (!button) {
            return;
        }
        event.preventDefault();
        setLayerTab(shell, button.getAttribute('data-layer-tab') || '');
    });
    context.bar.addEventListener('keydown', (event) => {
        const button = resolveLayerTabButton(shell, event.target);
        if (!button) {
            return;
        }
        if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
            event.preventDefault();
            focusLayerTabByOffset(shell, button, 1);
            return;
        }
        if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
            event.preventDefault();
            focusLayerTabByOffset(shell, button, -1);
            return;
        }
        if (event.key === 'Home') {
            event.preventDefault();
            const firstButton = context.buttons[0];
            if (firstButton) {
                setLayerTab(shell, firstButton.getAttribute('data-layer-tab') || '');
                firstButton.focus();
            }
            return;
        }
        if (event.key === 'End') {
            event.preventDefault();
            const lastButton = context.buttons[context.buttons.length - 1];
            if (lastButton) {
                setLayerTab(shell, lastButton.getAttribute('data-layer-tab') || '');
                lastButton.focus();
            }
            return;
        }
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            setLayerTab(shell, button.getAttribute('data-layer-tab') || '');
        }
    });
    setLayerTab(shell, context.buttons[0].getAttribute('data-layer-tab') || '');
});

function syncShellToggleState() {
    const sidebarCollapsed = document.body.classList.contains('sidebar-collapsed');
    const inspectorCollapsed = document.body.classList.contains('inspector-collapsed');

    if (btnSidebarToggle) {
        btnSidebarToggle.setAttribute('aria-pressed', sidebarCollapsed ? 'true' : 'false');
        btnSidebarToggle.setAttribute('title', sidebarCollapsed ? 'Expand menu' : 'Collapse menu');
        btnSidebarToggle.setAttribute('aria-label', sidebarCollapsed ? 'Expand menu' : 'Collapse menu');
    }

    if (btnInspectorToggle) {
        btnInspectorToggle.setAttribute('aria-pressed', inspectorCollapsed ? 'true' : 'false');
        btnInspectorToggle.setAttribute('title', inspectorCollapsed ? 'Expand live inspector' : 'Collapse live inspector');
        btnInspectorToggle.setAttribute('aria-label', inspectorCollapsed ? 'Expand live inspector' : 'Collapse live inspector');
    }
}

bindClick('btnSidebarToggle', async () => {
    document.body.classList.toggle('sidebar-collapsed');
    syncShellToggleState();
    setFeedback(document.body.classList.contains('sidebar-collapsed') ? 'Menu collapsed.' : 'Menu expanded.', 'muted');
});

bindClick('btnInspectorToggle', async () => {
    document.body.classList.toggle('inspector-collapsed');
    syncShellToggleState();
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
    renderRealWorldTasks();
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
    renderRealWorldTasks();
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
    renderRealWorldTasks();
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
    renderRealWorldTasks();
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
bindClick('btnMaintenanceWorkerStart', async () => {
    await startAutonomyMaintenanceWorker();
});
bindClick('btnMaintenanceWorkerStop', async () => {
    await stopAutonomyMaintenanceWorker();
});
bindClick('btnMaintenanceWorkerStartOps', async () => {
    await startAutonomyMaintenanceWorker();
});
bindClick('btnMaintenanceWorkerStopOps', async () => {
    await stopAutonomyMaintenanceWorker();
});
bindClick('btnTaskManagerRefresh', async () => {
    const payload = await getJson('/api/control/test-sessions');
    testRunsCache = Array.isArray(payload.reports) ? payload.reports : testRunsCache;
    testSessionDefinitions = Array.isArray(payload.definitions) ? payload.definitions : testSessionDefinitions;
    renderTestRuns();
    renderTestSessionDefinitions();
    renderRealWorldTasks();
    setAction('Real-world task library refreshed.');
});
bindClick('btnTaskManagerRun', async () => {
    const task = selectedRealWorldTask();
    if (!task) {
        setAction('Select a real-world task first.');
        return;
    }
    setAction('Running real-world task: ' + String(task.file || task.name || 'task'));
    const payload = await postAction('test_session_run', {session_file: String(task.file || '').trim()});
    testRunsCache = Array.isArray(payload.reports) ? payload.reports : testRunsCache;
    testSessionDefinitions = Array.isArray(payload.definitions) ? payload.definitions : testSessionDefinitions;
    renderTestRuns();
    renderTestSessionDefinitions();
    renderRealWorldTasks();
    if (payload.latest_report && testRunSelect && payload.latest_report.run_id) {
        testRunSelect.value = payload.latest_report.run_id;
        renderTestRunPreview();
    }
    const summary = String(payload.message || 'real-world task run completed');
    const output = String(payload.stdout || '').trim();
    setAction(output ? `${summary}\n\n${output}` : summary);
});
bindClick('btnTaskManagerCreate', async () => {
    const payload = await postAction('real_world_task_create', {
        name: taskManagerName ? taskManagerName.value.trim() : '',
        task_id: taskManagerTaskId ? taskManagerTaskId.value.trim() : '',
        category: taskManagerCategory ? taskManagerCategory.value : 'operator',
        objective: taskManagerObjective ? taskManagerObjective.value.trim() : '',
        prompt: taskManagerPrompt ? taskManagerPrompt.value.trim() : '',
        followup: taskManagerFollowup ? taskManagerFollowup.value.trim() : '',
        notes: taskManagerNotes ? taskManagerNotes.value.trim() : '',
    });
    testSessionDefinitions = Array.isArray(payload.definitions) ? payload.definitions : testSessionDefinitions;
    renderTestSessionDefinitions();
    renderRealWorldTasks();
    if (payload.task && payload.task.file && taskManagerSelect) {
        taskManagerSelect.value = payload.task.file;
        renderRealWorldTaskPreview();
    }
    if (taskManagerName) taskManagerName.value = '';
    if (taskManagerTaskId) taskManagerTaskId.value = '';
    if (taskManagerObjective) taskManagerObjective.value = '';
    if (taskManagerPrompt) taskManagerPrompt.value = '';
    if (taskManagerFollowup) taskManagerFollowup.value = '';
    if (taskManagerNotes) taskManagerNotes.value = '';
    setAction(payload.message || 'Real-world task created.');
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
        setAction('Select an operator session to open its trace.');
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
syncShellToggleState();
decorateActionButtons(document);
clearCenterTabs();
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

    const focusButton = target.closest('.focus-jump-button');
    if (focusButton instanceof HTMLElement) {
        const centerTarget = String(focusButton.getAttribute('data-focus-center-tab') || '').trim();
        const inspectorTarget = String(focusButton.getAttribute('data-focus-inspector-tab') || '').trim();
        setActiveView('overview');
        if (centerTarget) {
            setCenterTab(centerTarget);
        }
        if (inspectorTarget) {
            setInspectorTab(inspectorTarget);
        }
        setAction(`Focus shifted${centerTarget ? ` to ${centerTarget}` : ''}${inspectorTarget ? ` with ${inspectorTarget} inspector` : ''}.`);
        return;
    }

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
bindClick('btnSearchEndpoint', async () => { const payload = await postAction('search_endpoint_set', {endpoint: searchEndpointInput ? searchEndpointInput.value.trim() : ''}); setAction(payload.message || 'search_endpoint_set done'); await refresh(); });
bindClick('btnSearchPriority', async () => { const payload = await postAction('search_provider_priority_set', {priority: searchProviderPriorityInput ? searchProviderPriorityInput.value.trim() : ''}); setAction(payload.message || 'search_provider_priority_set done'); await refresh(); });
bindClick('btnSearchProbe', async () => { const payload = await postAction('search_endpoint_probe', {endpoint: searchEndpointInput ? searchEndpointInput.value.trim() : ''}); const probe = payload.probe || {}; const message = payload.message || 'search_endpoint_probe done'; if (searchEndpointBox) { const checked = Array.isArray(probe.checked_endpoints) ? probe.checked_endpoints.join(', ') : ''; const resolved = String(probe.resolved_endpoint || '').trim(); searchEndpointBox.textContent = [`Provider: ${String((latestPolicy && latestPolicy.web && latestPolicy.web.search_provider) || (latestStatus && latestStatus.search_provider) || 'html')}`, `Endpoint: ${String(probe.endpoint || (searchEndpointInput ? searchEndpointInput.value.trim() : '') || '(not set)')}`, `Web enabled: ${Boolean(latestPolicy && latestPolicy.web && latestPolicy.web.enabled)}`, `Probe ok: ${Boolean(probe.ok)}`, `Resolved endpoint: ${resolved || 'n/a'}`, `Probe note: ${String(probe.note || 'n/a')}`, `Checked endpoints: ${checked || 'n/a'}`].join('\n'); } setAction(message); await refresh(); });
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
bindClick('btnLocationTrackStart', async () => { startLiveTracking(); });
bindClick('btnLocationTrackAutoArm', async () => { toggleLiveTrackingAutoArm(); });
bindClick('btnLocationTrackStop', async () => { stopLiveTracking(); });
bindClick('btnLocationTrackClear', async () => { await clearLiveTracking(); });

if (operatorPromptInput) {
    operatorPromptInput.addEventListener('keydown', async (event) => {
        if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
            event.preventDefault();
            await sendOperatorPrompt();
        }
    });
}

if (taskManagerSelect) {
    taskManagerSelect.addEventListener('change', () => {
        renderRealWorldTaskPreview();
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
setInspectorTab('planner');
renderLiveTracking(null);
refresh();
setInterval(refresh, 15000);