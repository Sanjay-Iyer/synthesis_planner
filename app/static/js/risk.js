/**
 * Risk Assessment Frontend — CSV parsing, API calls, and Chart.js bubble chart.
 */

const API_BASE = '';
let lastRiskResults = null;
let knownMappings = []; // Cache for CAS -> Origin lookups
// Per-route process metrics (cost, E-factor, target kg) sent by the Planner.
let routeContext = null;

let bubbleChart = null;
let stackedBarChart = null;

/** Escape text for safe insertion into HTML (content and attributes). */
function esc(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

/** Mirror of the backend fmt_pct: 95 -> "95%", 86.24 -> "86.2%", 0.01 -> "<0.1%". */
function fmtPct(value) {
    if (value === null || value === undefined || isNaN(value)) return 'n/a';
    const v = Number(value);
    if (v > 0 && v < 0.05) return '<0.1%';
    const r = Math.round(v * 10) / 10;
    return Number.isInteger(r) ? `${r}%` : `${r.toFixed(1)}%`;
}

function userValue(value, autoFilled) {
    const v = (value || '').trim();
    return autoFilled && v === autoFilled ? '' : v;
}

function intOrNull(value) {
    const n = parseInt(value);
    return isNaN(n) ? null : n;
}

function fmtMoney(value) {
    if (value === null || value === undefined || isNaN(value)) return '—';
    return '$' + Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });
}

// Initialize with data from dashboard or 3 empty rows
document.addEventListener('DOMContentLoaded', async () => {
    // Load known mappings first
    try {
        const res = await fetch(`${API_BASE}/api/risk/mappings`);
        knownMappings = await res.json();
    } catch (e) { console.error("Failed to load mappings", e); }

    // Show what supply-chain data is indexed in data/supply_chain
    loadSupplyChainStatus();

    const pendingData = localStorage.getItem('pendingRiskData');
    if (pendingData) {
        try {
            const payload = JSON.parse(pendingData);
            // v2 payload: {version, reagents, routes}; older payloads are a bare array.
            const reagents = Array.isArray(payload) ? payload : (payload.reagents || []);
            routeContext = Array.isArray(payload) ? null : (payload.routes || null);
            document.getElementById('reagentRows').innerHTML = '';
            reagents.forEach(r => addReagentInputRow(r));
            runRiskAssessment(); // Auto-trigger assessment
            localStorage.removeItem('pendingRiskData');
        } catch (e) {
            console.error("Failed to load pending risk data:", e);
            for (let i = 0; i < 3; i++) addReagentInputRow();
        }
    } else {
        for (let i = 0; i < 3; i++) addReagentInputRow();
    }
});

/**
 * Loads and renders a summary of the supply-chain data files indexed in
 * data/supply_chain. These are searched automatically on every Run Risk
 * Assessment / Auto-Lookup Origins, so dropping a new file in makes it usable.
 */
async function loadSupplyChainStatus() {
    const el = document.getElementById('scStatus');
    if (!el) return;
    try {
        const res = await fetch(`${API_BASE}/api/supply-chain/status`);
        if (!res.ok) throw new Error(await res.text());
        const s = await res.json();

        if (!s.file_count) {
            el.style.display = 'block';
            el.innerHTML = `<b>Supply-chain data:</b> none indexed. Drop USITC DataWeb Excel files into <code>${s.folder}</code> — they are searched automatically.`;
            return;
        }

        const fileBits = s.files.map(f => {
            if (f.status !== 'ok') {
                return `<span style="color:var(--danger);">⚠ ${f.filename} (parse error)</span>`;
            }
            const yrs = (f.full_years || []).length ? `${f.full_years[0]}–${f.full_years[f.full_years.length - 1]}` : '—';
            return `${f.filename} <span style="color:var(--text-muted);">(${f.trade_flow}, ${f.hts6_count} HTS6, ${yrs})</span>`;
        }).join(' · ');

        el.style.display = 'block';
        el.innerHTML = `<b>Supply-chain data indexed:</b> ${s.hs6_with_imports} HTS6 with import origins, ${s.hs6_with_exports} with exports. ${fileBits} <a href="#" onclick="refreshSupplyChain(event)" style="color:var(--primary);">↻ rescan</a>`;
    } catch (e) {
        console.error('Failed to load supply-chain status', e);
    }
}

async function refreshSupplyChain(event) {
    if (event) event.preventDefault();
    try {
        await fetch(`${API_BASE}/api/supply-chain/refresh`, { method: 'POST' });
    } catch (e) { console.error('Supply-chain refresh failed', e); }
    loadSupplyChainStatus();
}

function addReagentInputRow(data = null) {
    const container = document.getElementById('reagentRows');
    const row = document.createElement('div');
    row.className = 'reagent-input-row fade-in';
    if (document.getElementById('advancedToggle').checked) row.classList.add('advanced');
    
    const routeUsage = (data?.routes && typeof data.routes === 'object') ? data.routes : null;
    const routeLabel = routeUsage ? Object.keys(routeUsage).join(',') : (data?.route || '');
    const round2 = v => (v === undefined || v === null || v === '') ? '' : Math.round(Number(v) * 100) / 100;

    row.innerHTML = `
        <input type="text" class="r-name" placeholder="e.g. CuCl2" value="${esc(data?.name || '')}">
        <div>
            <input type="text" class="r-hs6" placeholder="UNKNOWN" inputmode="numeric" title="Six-digit HS6 trade category; highest mapping priority" value="${esc(data?.hs6 || '')}" oninput="validateHS6(this)">
            <div class="r-trade-status muted-sm" role="status"></div>
        </div>
        <div style="position:relative; display:flex; align-items:center;">
            <input type="text" class="cas-input r-cas" placeholder="e.g. 7447-39-4" value="${esc(data?.cas || '')}" oninput="checkCAS(this)" style="width:100%;">
            <span class="status-dot" style="position:absolute; right:8px; width:8px; height:8px; border-radius:50%; background:#dfe6e9;" title="CAS Status"></span>
        </div>
        <input type="text" class="origin-input r-origin" placeholder="Primary" value="${esc(data?.origin || '')}">
        <input type="text" class="origin-input r-secondary-origin" placeholder="Secondary" value="${esc(data?.secondary_origin || '')}">
        <input type="number" step="any" class="r-mass" placeholder="Mass" value="${esc(round2(data?.mass_g) || '')}">
        <input type="number" step="any" class="r-cost" placeholder="Cost" value="${esc(round2(data?.cost) || '')}">
        <input type="text" class="r-route" placeholder="A,B" value="${esc(routeLabel)}" title="Route(s) using this reagent, e.g. A or A,B">
        <!-- Advanced fields -->
        <input type="number" step="any" class="r-lead adv-field" placeholder="Lead (d)" title="Lead time in days. Blank = default 14, marked as a default." value="${esc(data?.lead_time_days ?? '')}">
        <input type="number" step="any" class="r-haz adv-field" placeholder="Haz (1-10)" title="Hazard 1-10. Blank = default 5, marked as a default." value="${esc(data?.hazard_score ?? '')}">
        <input type="number" step="any" class="r-reg adv-field" placeholder="Reg (1-10)" title="Regulatory 1-10. Blank = default 5, marked as a default." value="${esc(data?.regulatory_score ?? '')}">
        <input type="number" step="any" class="r-sub adv-field" placeholder="Sub (1-10)" title="Substitutability 1-10 (10 = hardest to replace). Leave blank if unknown — a default of 5 is used and labelled as a default." value="${esc(data?.substitutability ?? '')}">

        <button class="btn btn-danger btn-sm" onclick="this.parentElement.remove()" style="padding:4px 8px;">✕</button>
    `;
    // Exact per-route usage from the Planner (kept even if the row total is rounded).
    if (routeUsage) row.dataset.routeUsage = JSON.stringify(routeUsage);
    // Structure identifier from the Planner (SMILES/InChI/InChIKey) for exact HS6 matching.
    if (data?.structure) row.dataset.structure = data.structure;
    container.appendChild(row);
    validateHS6(row.querySelector('.r-hs6'));
    if (data?.cas) checkCAS(row.querySelector('.cas-input'));
}

function validateHS6(input) {
    const code = input.value.replace(/\s+/g, '');
    const invalid = code && !/^[0-9]{6}$/.test(code);
    input.setAttribute('aria-invalid', invalid ? 'true' : 'false');
    input.style.borderColor = invalid ? 'var(--danger)' : '';
    input.title = invalid ? 'INVALID HS6: enter exactly six digits (no decimal or scientific notation)' : 'Six-digit HS6 trade category; blank uses the automatic resolver';
    const status = input.parentElement.querySelector('.r-trade-status');
    if (status) status.textContent = invalid ? 'INVALID HS6' : '';
}

// CSV cells stay strings: leading zeroes and invalid code formatting survive.
function parseRiskCSVLine(line) {
    const cells = [];
    let text = '', quoted = false;
    for (let i = 0; i < line.length; i++) {
        const c = line[i];
        if (c === '"') {
            if (quoted && line[i + 1] === '"') { text += '"'; i++; }
            else quoted = !quoted;
        } else if (c === ',' && !quoted) { cells.push(text.trim()); text = ''; }
        else text += c;
    }
    cells.push(text.trim());
    return cells;
}

/**
 * Route usage for one input row. Planner rows keep their exact per-route
 * costs; a single-route or manually entered row attributes the row's cost and
 * mass to each listed route (enter separate rows when usage differs by route).
 */
function collectRouteUsage(row, mass, cost) {
    const labels = (row.querySelector('.r-route')?.value || '')
        .split(',').map(s => s.trim()).filter(Boolean);
    if (!labels.length) return {};
    let stored = {};
    try { stored = JSON.parse(row.dataset.routeUsage || '{}'); } catch (e) { stored = {}; }
    const sameRoutes = labels.slice().sort().join(',') === Object.keys(stored).sort().join(',');
    if (labels.length > 1 && sameRoutes) return stored;
    const usage = {};
    labels.forEach(l => { usage[l] = { cost: cost, mass_g: mass }; });
    return usage;
}

function checkCAS(el) {
    const cas = el.value.trim();
    const row = el.closest('.reagent-input-row');
    const dot = row.querySelector('.status-dot');
    const originInput = row.querySelector('.origin-input');
    
    if (!cas) {
        dot.style.background = '#dfe6e9';
        dot.title = "No CAS provided";
        return;
    }

    const match = knownMappings.find(m => m.Reagent_CAS === cas);
    if (match) {
        dot.style.background = '#27ae60';
        dot.title = `Recognized: ${match.Primary_Origin}`;
        if (!originInput.value) originInput.value = match.Primary_Origin;
    } else {
        dot.style.background = '#fdcb6e';
        dot.title = "Unknown CAS (will use defaults)";
    }
}

function toggleAdvancedMode() {
    const isAdv = document.getElementById('advancedToggle').checked;
    const header = document.getElementById('inputHeader');
    const rows = document.querySelectorAll('.reagent-input-row');
    
    if (isAdv) {
        header.classList.add('advanced');
        rows.forEach(r => r.classList.add('advanced'));
    } else {
        header.classList.remove('advanced');
        rows.forEach(r => r.classList.remove('advanced'));
    }
}

function activeRiskRows() {
    return Array.from(document.querySelectorAll('#reagentRows .reagent-input-row'))
        .filter(row => row.querySelector('.r-name').value.trim() || row.querySelector('.r-hs6').value.trim());
}

function collectReagentInputs() {
    const rows = activeRiskRows();
    const reagents = [];
    rows.forEach(row => {
        const name = row.querySelector('.r-name').value.trim();
        const mass = parseFloat(row.querySelector('.r-mass').value) || 0;
        const cost = parseFloat(row.querySelector('.r-cost').value) || 0;
        const sub = parseInt(row.querySelector('.r-sub').value);
        reagents.push({
            name: name,
            cas: row.querySelector('.r-cas').value.trim(),
            // Origins filled by Auto-Lookup are not user statements: send them
            // blank so the engine re-derives them and labels them as trade data.
            origin: userValue(row.querySelector('.r-origin').value, row.dataset.autoOrigin),
            secondary_origin: userValue(row.querySelector('.r-secondary-origin').value, row.dataset.autoSecondary),
            mass_g: mass,
            cost: cost,
            // Blank -> null: the engine uses its default and marks it as a default.
            lead_time_days: intOrNull(row.querySelector('.r-lead').value),
            hazard_score: intOrNull(row.querySelector('.r-haz').value),
            regulatory_score: intOrNull(row.querySelector('.r-reg').value),
            // null = not provided; the engine uses 5 and labels it as a default.
            substitutability: isNaN(sub) ? null : sub,
            routes: collectRouteUsage(row, mass, cost),
            hs6: (row.querySelector('.r-hs6')?.value || '').replace(/\s+/g, '') || null,
            structure: row.dataset.structure || null
        });
    });
    return reagents;
}

function loadCSV(event) {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
        const lines = e.target.result.split('\n').filter(l => l.trim());
        if (lines.length < 2) { alert('CSV has no data rows.'); return; }

        // Parse header
        const header = parseRiskCSVLine(lines[0].replace(/^\uFEFF/, ''));

        // Find column indices (flexible matching)
        const nameIdx = header.findIndex(h => /reagent(?!_cas)/i.test(h));
        const casIdx = header.findIndex(h => /cas/i.test(h));
        const originIdx = header.findIndex(h => /origin/i.test(h));
        const massIdx = header.findIndex(h => /mass/i.test(h));
        const costIdx = header.findIndex(h => /cost/i.test(h));
        const leadIdx = header.findIndex(h => /lead/i.test(h));
        const hazIdx = header.findIndex(h => /haz/i.test(h));
        const regIdx = header.findIndex(h => /reg/i.test(h));
        const subIdx = header.findIndex(h => /sub/i.test(h));
        const routeIdx = header.findIndex(h => /^route/i.test(h));
        const hs6Idx = header.findIndex(h => /^hs6$|^hs_?code$|^hs6_?code$/i.test(h));

        // Auto-enable advanced mode if advanced columns found
        if (leadIdx >= 0 || hazIdx >= 0 || subIdx >= 0) {
            document.getElementById('advancedToggle').checked = true;
            toggleAdvancedMode();
        }

        // Clear existing rows
        document.getElementById('reagentRows').innerHTML = '';

        // Parse data rows
        for (let i = 1; i < lines.length; i++) {
            const cols = parseRiskCSVLine(lines[i]);

            addReagentInputRow({
                name: nameIdx >= 0 ? cols[nameIdx] : cols[0],
                cas: casIdx >= 0 ? cols[casIdx] : '',
                origin: originIdx >= 0 ? cols[originIdx] : '',
                secondary_origin: '', 
                mass_g: massIdx >= 0 ? parseFloat(cols[massIdx]) || 0 : 0,
                cost: costIdx >= 0 ? parseFloat(cols[costIdx]) || 0 : 0,
                lead_time_days: leadIdx >= 0 ? (intOrNull(cols[leadIdx]) ?? '') : '',
                hazard_score: hazIdx >= 0 ? (intOrNull(cols[hazIdx]) ?? '') : '',
                regulatory_score: regIdx >= 0 ? (intOrNull(cols[regIdx]) ?? '') : '',
                substitutability: subIdx >= 0 && !isNaN(parseInt(cols[subIdx])) ? parseInt(cols[subIdx]) : '',
                route: routeIdx >= 0 ? (cols[routeIdx] || '').replace(/;/g, ',') : '',
                hs6: hs6Idx >= 0 ? cols[hs6Idx] : ''
            });
        }

        // Visual feedback
        const zone = document.getElementById('uploadZone');
        zone.classList.add('active');
        zone.querySelector('div:first-child').textContent = '✅';
        zone.querySelector('div:nth-child(2)').textContent = `Loaded ${lines.length - 1} reagents from ${file.name}`;
    };
    reader.readAsText(file);
}

async function uploadWitsExcel(event) {
    const file = event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    const zone = document.getElementById('witsUploadZone');
    zone.style.opacity = '0.5';
    zone.querySelector('div:nth-child(2)').textContent = 'Uploading...';

    try {
        const res = await fetch('/api/trade/import', {
            method: 'POST',
            body: formData
        });

        if (!res.ok) throw new Error(await res.text());

        const data = await res.json();
        const s = data.summary;
        alert(`✅ Success: Ingested ${s.compounds_processed} products.\nNew: ${s.new_entries.length}\nUpdated: ${s.updated_entries.length}\nWarnings: ${s.warnings.length}`);
        
        zone.classList.add('active');
        zone.querySelector('div:first-child').textContent = '✅';
        zone.querySelector('div:nth-child(2)').textContent = `Imported ${file.name}`;
    } catch (e) {
        console.error("WITS Upload Failed:", e);
        alert(`❌ Import Failed: ${e.message}`);
        zone.style.opacity = '1';
        zone.querySelector('div:nth-child(2)').textContent = 'Import WITS Excel';
    }
}

async function runRiskAssessment() {
    const reagents = collectReagentInputs();
    if (reagents.length === 0) { alert('Enter a reagent name or HS6 code in a row first.'); return; }

    try {
        const res = await fetch(`${API_BASE}/api/risk/assess`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reagents })
        });
        
        if (!res.ok) {
            const errData = await res.json();
            console.error("Server Error (422/500):", errData);
            alert(`Risk assessment failed: ${JSON.stringify(errData.detail || errData.error)}`);
            return;
        }

        const data = await res.json();
        lastRiskResults = data;
        displayRiskResults(data);
        prepareScenarioPanel(data);  // clears any previous scenario first
        renderRouteSummary(data);
        initVisualizations(data);
    } catch (e) {
        console.error("Client Error during assessment:", e);
        alert('Risk assessment failed. Check console for details.');
    }
}

function initVisualizations(data) {
    try {
        document.getElementById('vizSection').style.display = 'block';
        if (data.reagents && data.reagents.length > 0) {
            renderBubbleChart(data.reagents);
            renderCountryExposureChart(data);
            renderHeatmap(data.reagents);
        }
    } catch (err) {
        console.error("Visualization Rendering Error:", err);
        // Don't alert here to avoid blocking the table view
    }
}

function renderBubbleChart(reagents) {
    const ctx = document.getElementById('bubbleChart').getContext('2d');
    if (bubbleChart) bubbleChart.destroy();

    const chartData = reagents.map(r => ({
        x: Math.max(r.cost || 0, 0.01), // Log scale needs > 0
        y: r.risk_index || 0,
        r: Math.sqrt(Math.max(r.mass_g || 0, 0)) / 2 + 5,
        name: r.name || 'Unknown',
        hs6: r.hs6 || r.hs_code || 'UNKNOWN',
        trade_status: r.trade_status || 'HS6 MISSING'
    }));

    bubbleChart = new Chart(ctx, {
        type: 'bubble',
        data: {
            datasets: [{
                label: 'Reagents',
                data: chartData,
                backgroundColor: 'rgba(9, 132, 227, 0.6)',
                borderColor: 'var(--primary)',
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { 
                    title: { display: true, text: 'Total Cost ($)' }, 
                    type: 'logarithmic',
                    min: 0.01 // Crucial for log scale
                },
                y: { title: { display: true, text: 'Risk Index' }, min: 0 }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: (ctx) => `${ctx.raw.name} · HS6 ${ctx.raw.hs6} · ${ctx.raw.trade_status}: Cost $${ctx.raw.x.toFixed(2)}, Risk ${ctx.raw.y.toFixed(1)}`
                    }
                }
            }
        }
    });
}

/**
 * Spend exposure by country: for every reagent with trade data, reagent spend x
 * that country's share of reported trade, summed per country (and per route).
 * Reagents without trade data are not plotted (stated in the caption).
 */
function renderCountryExposureChart(data) {
    const ctx = document.getElementById('stackedBarChart').getContext('2d');
    if (stackedBarChart) stackedBarChart.destroy();
    const ce = (data.summary && data.summary.country_exposure) || { routes: [], countries: [] };
    const top = (ce.countries || []).slice(0, 12);
    const palette = ['rgba(9, 132, 227, 0.75)', 'rgba(39, 174, 96, 0.75)', 'rgba(142, 68, 173, 0.75)', 'rgba(243, 156, 18, 0.75)'];
    const datasets = (ce.routes || []).map((route, i) => ({
        label: route === 'All reagents' ? 'All reagents' : `Route ${route}`,
        data: top.map(c => c.by_route[route] || 0),
        backgroundColor: palette[i % palette.length],
        borderRadius: 4
    }));

    stackedBarChart = new Chart(ctx, {
        type: 'bar',
        data: { labels: top.map(c => c.country), datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: true },
                tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${fmtMoney(c.raw)} of reagent spend` } }
            },
            scales: {
                x: { stacked: true, grid: { display: false } },
                y: { stacked: true, beginAtZero: true, title: { display: true, text: 'Assessed reagent spend exposed ($)' } }
            }
        }
    });
    const caption = document.getElementById('countryChartCaption');
    if (caption) {
        const unknown = ce.unknown_spend ? ` ${fmtMoney(ce.unknown_spend)} of spend has no trade data and is not shown.` : '';
        caption.textContent = 'Reagent spend × each country\'s share of reported trade (USITC: U.S. imports; WITS: top listed exporters), summed per country. Shows where reported sourcing is concentrated; it does not rate countries.' + unknown;
    }
}

function renderHeatmap(reagents) {
    const grid = document.getElementById('heatmapGrid');
    grid.innerHTML = '';
    
    // Geographic = country conditions; Concentration = top-supplier share from
    // trade data (n/a when it cannot be assessed — shown grey, not green).
    const columns = [
        ['Geographic', 'geographic', 'Country conditions (100 - stability)'],
        ['Concentration', 'concentration', 'Top supplier share (%) from trade data'],
        ['Operational', 'operational', 'Lead time + supplier count'],
        ['Regulatory', 'regulatory', 'Hazard + regulatory flags'],
        ['Economic', 'economic', 'Substitutability x 10']
    ];

    // Header
    grid.style.gridTemplateColumns = `120px 80px repeat(${columns.length}, 1fr)`;
    let html = `<div>Reagent</div><div class="heatmap-label">HS6</div>` + columns.map(([label, , tip]) => `<div class="heatmap-label" title="${esc(tip)}">${label}</div>`).join('');

    reagents.forEach(r => {
        // Reagent Label
        html += `<div class="heatmap-label" style="text-align:right; padding-right:10px; color:var(--dark);">${esc(r.name || 'Unknown')}</div>`;
        html += `<div class="heatmap-label" title="${esc(r.trade_status || 'HS6 MISSING')}">${esc(r.hs6 || r.hs_code || 'UNKNOWN')}</div>`;

        // Cells
        columns.forEach(([label, key]) => {
            const val = r.breakdown[key];
            if (val === null || val === undefined) {
                html += `<div class="heatmap-cell" style="background:#b2bec3" title="${label}: not assessed (insufficient data) — not treated as safe or risky">n/a</div>`;
                return;
            }
            const color = getHeatmapColor(val);
            html += `<div class="heatmap-cell" style="background:${color}" title="${label}: ${val}">${val}</div>`;
        });
    });
    grid.innerHTML = html;
}

function getHeatmapColor(val) {
    // 0 (green) -> 100 (red)
    const hue = ((100 - val) * 120 / 100).toString(10);
    return `hsl(${hue}, 70%, 45%)`;
}

function displayRiskResults(data) {
    // Summary cards
    const summary = data.summary;
    document.getElementById('summaryCards').style.display = 'grid';
    document.getElementById('sumTotal').textContent = summary.total_reagents || '0';
    document.getElementById('sumHighRisk').textContent = summary.high_risk_count || '0';
    document.getElementById('sumExposure').textContent = (summary.total_risk_exposure || 0).toFixed(1);
    document.getElementById('sumConcHigh').textContent = summary.concentration_high_count || '0';
    const unknownConc = summary.concentration_unknown_count || 0;
    document.getElementById('sumConcUnknown').textContent = unknownConc ? `${unknownConc} with unknown concentration` : '';

    // Results table
    const tbody = document.getElementById('riskTableBody');
    tbody.innerHTML = '';
    document.getElementById('resultsCard').style.display = 'block';

    data.reagents.forEach(r => {
        const row = document.createElement('tr');
        const geo = r.geographic_exposure || {};
        const comp = r.risk_index_components || {};
        let stabilityCell;
        if (geo.stability_known) {
            const ci = geo.stability_ci_90 ? ` (90% CI ${Math.round(geo.stability_ci_90[0])}–${Math.round(geo.stability_ci_90[1])})` : '';
            stabilityCell = `<span title="${esc((geo.stability_indicator || '') + ci + ' — ' + (geo.stability_source || ''))}">${Math.round(r.stability_score)}/100</span>
                <div class="muted-sm">WGI ${esc(geo.stability_year || '')}</div>`;
        } else {
            const why = geo.stability_status === 'origin_unknown' ? 'origin unknown' : 'no WGI score';
            stabilityCell = `<span title="${esc(geo.explanation || '')}">Unknown</span><div class="muted-sm">${why}; not assessed</div>`;
        }
        const indexBits = [];
        if (comp.missing && comp.missing.length) indexBits.push(`not assessed: ${esc(comp.missing.join(', '))}`);
        if (comp.defaults_used && comp.defaults_used.length) indexBits.push(`defaults: ${esc(comp.defaults_used.join(', '))}`);
        if (comp.exposure_multiplier) indexBits.push(`×${esc(comp.exposure_multiplier)} quantity factor`);
        const indexNote = indexBits.length
            ? `<div class="muted-sm" title="${esc(r.risk_index_note || '')}">${indexBits.join('<br>')}</div>`
            : '';

        row.innerHTML = `
            <td style="font-weight:600;">${esc(r.name || 'Unknown')}</td>
            <td style="font-family:monospace;">${esc(r.hs6 || r.hs_code || 'UNKNOWN')}</td>
            <td style="font-family:monospace; font-size:0.8rem;">${esc(r.cas || 'No CAS')}</td>
            <td class="origin-cell">
                <div style="font-weight:600; color:var(--primary);">Primary: ${originShareLabel(r.primary_origin, r.primary_origin_share_pct)}</div>
                <div class="muted-sm" title="${esc(geo.explanation || '')}">via ${esc(geo.origin_source_label || 'unknown source')}</div>
                <div style="font-size:0.7rem; color:var(--text-muted); border-top:1px solid #eee; margin-top:4px; padding-top:4px;">Secondary: ${originShareLabel(r.secondary_origin, r.secondary_origin_share_pct)}</div>
                <div class="muted-sm">${esc((r.provenance || {}).share_basis_label || 'Trade share unavailable')}</div>
            </td>
            <td>${stabilityCell}</td>
            <td>${concentrationCell(r)}</td>
            <td>${esc(r.trade_status || 'HS6 MISSING')}</td>
            <td>${(r.mass_g || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
            <td>${fmtMoney(r.cost || 0)}</td>
            <td title="${esc(r.risk_index_note || '')}">${r.risk_index ? r.risk_index.toFixed(1) : '0.0'}${indexNote}</td>
            <td>
                <span class="status-pill status-${esc((r.risk_level || 'UNKNOWN').split(' ')[0].toLowerCase())}">
                    ${esc(r.risk_level || 'UNKNOWN')}
                </span>
            </td>
            <td>
                ${(r.warnings || []).map(w => `
                    <div style="font-size:0.7rem; color:${w.includes('REGULATORY') ? 'var(--danger)' : 'var(--orange)'}; margin-bottom:2px;">
                        ⚠️ ${esc(w)}
                    </div>
                `).join('')}
            </td>
        `;
        tbody.appendChild(row);
    });
    // NOTE: the bubble chart is rendered by initVisualizations() -> renderBubbleChart()
    // on the #bubbleChart canvas (see initVisualizations -> renderBubbleChart).
}

function originShareLabel(country, share) {
    const label = esc(country || 'Unknown');
    return `${label} — ${share === null || share === undefined ? 'share unavailable' : fmtPct(share)}`;
}

/**
 * Concentration Risk card: tier, top suppliers, plain-language explanation and
 * the provenance of every number (source, scope, HS6 match, period, basis,
 * coverage, data quality).
 */
function concentrationCell(r) {
    const c = r.concentration || {};
    const p = r.provenance || {};
    const q = r.data_quality || {};
    const a = r.alternatives || {};
    const m = p.hs6_mapping || {};
    const tier = c.tier || 'UNKNOWN';
    const tierCls = tier.toLowerCase();

    let shares = '';
    if (c.top_supplier_country && c.top_supplier_share !== null && c.top_supplier_share !== undefined) {
        shares = `<b>${esc(c.top_supplier_country)}</b> — ${fmtPct(c.top_supplier_share)}`;
        if (c.second_supplier_country) {
            shares += `<br>${esc(c.second_supplier_country)} — ${fmtPct(c.second_supplier_share)}`;
        }
    }

    const mappingText = m.hs6
        ? `${esc(m.match_label || m.match_method)}${m.exact ? ' (exact)' : ' (not exact)'} · mapping quality <b>${esc(m.mapping_quality || 'n/a')}</b>${m.broad_category ? ' · broad category' : ''}`
        : 'none';

    const meta = [];
    if (p.status === 'success') {
        const src = p.source_url
            ? `<a href="${esc(p.source_url)}" target="_blank" rel="noopener">${esc(p.source)}</a>`
            : esc(p.source);
        meta.push(`Source: ${src}`);
        meta.push(`HS6: ${esc(p.hs6_code)}${p.description ? ` — ${esc(p.description)}` : ''}`);
        meta.push(`HS6 match: ${mappingText}`);
        const partial = p.is_partial_year ? ' <b style="color:var(--orange);">(partial year / YTD)</b>' : '';
        meta.push(`Period: ${esc(p.period_label)}${partial}`);
        meta.push(`Basis: ${esc(p.ranking_basis)}`);
        meta.push(`Coverage: ${esc(c.coverage_note || p.share_basis_label || '')}`);
        if (p.total_value_usd) {
            const v = p.volatility || {};
            const yoy = (v.total_change_pct !== null && v.total_change_pct !== undefined)
                ? ` (${v.total_change_pct > 0 ? '+' : ''}${esc(v.total_change_pct)}% vs ${esc(v.prior_year)}${v.top_supplier_changed ? `; top supplier was ${esc(v.prior_top_supplier)}` : ''})`
                : '';
            meta.push(`Total reported: ${fmtMoney(p.total_value_usd)}${yoy}`);
        }
        const tb = p.trade_balance;
        if (tb && tb.net_exporter) {
            meta.push(`<span class="conc-note">U.S. exports (${fmtMoney(tb.exports_value_usd)}) exceed imports in ${esc(tb.year)} — imports are only part of U.S. supply.</span>`);
        }
        if (p.scope_note) meta.push(`Scope: ${esc(p.scope_note)}`);
    } else if (r.trade_status === 'INVALID HS6') {
        meta.push(`INVALID HS6: ${esc(r.hs6)} — enter exactly six digits; lookup skipped`);
    } else if (p.hs6_code) {
        meta.push(`HS6: ${esc(p.hs6_code)} — no trade data indexed`);
        meta.push(`HS6 match: ${mappingText}`);
    } else {
        meta.push('No HS6 code mapped for this reagent');
    }
    meta.push(`Data quality: <b title="${esc((q.reasons || []).join(' '))}">${esc(q.level || 'n/a')}</b>`);

    const details = [];
    if (c.rule) details.push(`Rule: ${esc(c.rule)}`);
    if (c.caveat) details.push(`<span class="conc-note">${esc(c.caveat)}</span>`);
    (q.reasons || []).forEach(reason => details.push(`Quality: ${esc(reason)}`));
    if (m.hs6) details.push(`HS6 mapping source: ${esc(m.source || '')}${m.note ? ' — ' + esc(m.note) : ''}`);
    if (p.year_selection_note) details.push(`Year: ${esc(p.year_selection_note)}`);
    (p.notes || []).forEach(n => details.push(esc(n)));
    if (a.summary) details.push(`Alternatives: ${esc(a.summary)}`);
    if (a.substitutability_note) details.push(`Substitutability: ${esc(a.substitutability_score)} — ${esc(a.substitutability_note)}`);
    details.push('Qualified alternate suppliers / alternative chemistry: no information in the app.');

    return `
        <div class="conc-card tier-${esc(tierCls)}">
            <div class="conc-head">
                <span class="conc-title">CONCENTRATION RISK</span>
                <span class="status-pill status-${esc(tierCls)}" style="font-size:0.6rem; padding:2px 6px;">${esc(tier)}</span>
            </div>
            ${shares ? `<div class="conc-shares">${shares}</div>` : ''}
            <div class="conc-why">${esc(c.explanation || '')}</div>
            <div class="conc-meta">${meta.join('<br>')}</div>
            <details><summary>Why / provenance details</summary>
                <div class="conc-meta" style="margin-top:4px;">${details.join('<br>')}</div>
            </details>
        </div>`;
}

/**
 * Route comparison: process metrics (from the Planner) next to supply-geography
 * facts, as one compact table. Deliberately no combined score or ranking.
 */
let lastScenarioResult = null;

function renderRouteSummary(data) {
    const card = document.getElementById('routeSummaryCard');
    const grid = document.getElementById('routeSummaryGrid');
    const routes = (data && data.summary && data.summary.route_summary) || null;
    if (!routes || !routes.length) { card.style.display = 'none'; grid.innerHTML = ''; return; }

    const ctxFor = rt => (routeContext || {})[rt.route] || {};
    const pill = tier => `<span class="status-pill status-${esc((tier || 'unknown').toLowerCase())}" style="font-size:0.6rem; padding:1px 6px;">${esc(tier || 'UNKNOWN')}</span>`;
    const brief = b => b ? `${fmtPct(b.top_supplier_share)} ${esc(b.top_supplier_country)} ${pill(b.tier)}<div class="muted-sm">${esc(b.name)} · ${esc(b.source || '')} · quality ${esc(b.data_quality || 'n/a')}</div>` : '—';

    const scenarioRows = {};
    if (lastScenarioResult) {
        (lastScenarioResult.routes || []).forEach(r => { scenarioRows[r.route] = r; });
    }

    const rows = [
        ['section', 'Process metrics (Planner)'],
        ['Total route cost', rt => {
            const c = ctxFor(rt);
            return c.total_cost !== null && c.total_cost !== undefined ? `${fmtMoney(c.total_cost)}${c.target_kg ? ` for ${esc(c.target_kg)} kg` : ''}` : '—';
        }],
        ['E-factor', rt => { const c = ctxFor(rt); return c.e_factor !== null && c.e_factor !== undefined ? esc(c.e_factor) : '—'; }],
        ['section', 'Supply geography (Risk Audit)'],
        ['Assessed reagent spend', rt => {
            const c = ctxFor(rt);
            const share = c.total_cost ? ` <span class="muted-sm">(${fmtPct(rt.assessed_reagent_cost / c.total_cost * 100)} of total route cost)</span>` : '';
            return `${fmtMoney(rt.assessed_reagent_cost)}${share}`;
        }],
        ['Not assessed (solvents, other costs)', rt => {
            const c = ctxFor(rt);
            if (!c.total_cost) return '—';
            const rest = Math.max(c.total_cost - rt.assessed_reagent_cost, 0);
            return `${fmtMoney(rest)} <span class="muted-sm">(${fmtPct(rest / c.total_cost * 100)} of total route cost — no geographic data)</span>`;
        }],
        ['Reagents assessed / with trade data', rt => `${rt.reagent_count} / ${rt.reagents_with_trade_data}`],
        ['HIGH concentration reagents', rt => `${rt.high_concentration_count}${rt.high_concentration_reagents.length ? `<div class="muted-sm">${esc(rt.high_concentration_reagents.join(', '))}</div>` : ''}`],
        ['Highest single-country share', rt => brief(rt.largest_dominant_share)],
        ['Largest single-country exposure', rt => {
            const e = rt.largest_country_exposure;
            if (!e) return '—';
            const contrib = (e.contributions || []).slice(0, 3)
                .map(c => `${esc(c.name)} (${fmtMoney(c.cost)}, ${esc(c.source || '')}, quality ${esc(c.data_quality)})`).join('; ');
            const weak = e.weak_data_pct
                ? `<div class="conc-note">${fmtPct(e.weak_data_pct)} of this exposure rests on MEDIUM/LOW-quality data</div>`
                : '<div class="muted-sm">All contributing data HIGH quality</div>';
            return `<b>${esc(e.country)}</b> — ${fmtPct(e.pct_of_assessed_spend)} of assessed reagent spend${weak}<div class="muted-sm">via ${contrib}</div>`;
        }],
        ['Unknown trade-data exposure', rt => rt.unknown_concentration_reagents.length
            ? `${fmtPct(rt.unknown_data_pct)} of assessed reagent spend<div class="muted-sm">${esc(rt.unknown_concentration_reagents.join(', '))}</div>`
            : 'None'],
        ['Highest country-conditions score', rt => {
            const g = rt.highest_geographic_risk_reagent;
            return g ? `${esc(g.geographic_score)} <span class="muted-sm">(${esc(g.origin)}, WGI ${esc(Math.round(g.stability_score))}/100 · ${esc(g.name)})</span>` : '—';
        }],
    ];
    if (lastScenarioResult) {
        rows.push(['section', `Selected scenario: ${esc(lastScenarioResult.scenario.label)}`]);
        rows.push(['Exposed share of assessed reagent spend', rt => {
            const s = scenarioRows[rt.route];
            if (!s) return '—';
            const upper = s.exposure_tier_if_unknown_affected ? `<div class="muted-sm">up to ${esc(s.exposure_tier_if_unknown_affected)} if unknown-data reagents were affected</div>` : '';
            return `<b>${esc(s.affected_pct_label || fmtPct(s.affected_pct))}</b> ${pill(s.exposure_tier)} <span class="muted-sm">${esc(s.exposure_label)}</span>${upper}`;
        }]);
    }

    const header = `<tr><th>Metric</th>${routes.map(rt => `<th>Route ${esc(rt.route)}</th>`).join('')}</tr>`;
    const body = rows.map(([label, fn]) => {
        if (label === 'section') return `<tr class="section"><td colspan="${routes.length + 1}">${fn}</td></tr>`;
        return `<tr><td class="metric">${label}</td>${routes.map(rt => `<td>${fn(rt)}</td>`).join('')}</tr>`;
    }).join('');
    grid.innerHTML = `<table class="route-table">${header}${body}</table>`;
    card.style.display = 'block';
}

// ---------------------------------------------------------------------------
// Scenario / Shock analysis (calculations run server-side, deterministically)
// ---------------------------------------------------------------------------

let scenarioCountries = [];

function prepareScenarioPanel(data) {
    const set = new Set();
    (data.reagents || []).forEach(r => (r.supplier_shares || []).forEach(s => { if (s.country) set.add(s.country); }));
    scenarioCountries = Array.from(set).sort();
    lastScenarioResult = null;
    document.getElementById('scenarioCard').style.display = data.reagents && data.reagents.length ? 'block' : 'none';
    document.getElementById('scenarioResults').innerHTML = '';
    updateScenarioControls();
}

function updateScenarioControls() {
    const type = document.getElementById('scenarioType').value;
    const countrySel = document.getElementById('scenarioCountry');
    const previous = countrySel.value;
    const needsCountry = type !== 'dominant_supplier_loss';
    document.getElementById('scenarioCountryLabel').style.display = needsCountry ? 'flex' : 'none';
    document.getElementById('scenarioTariffLabel').style.display = type === 'tariff' ? 'flex' : 'none';
    document.getElementById('scenarioLeadLabel').style.display = type === 'lead_time' ? 'flex' : 'none';

    const options = [];
    if (type === 'tariff' || type === 'lead_time') {
        options.push(`<option value="">Each reagent's dominant supplier</option>`);
    }
    scenarioCountries.forEach(c => options.push(`<option value="${esc(c)}">${esc(c)}</option>`));
    countrySel.innerHTML = options.join('');
    if ([...countrySel.options].some(o => o.value === previous)) countrySel.value = previous;
}

async function runScenario() {
    const reagents = collectReagentInputs();
    if (!reagents.length) { alert('Please enter at least one reagent.'); return; }
    const type = document.getElementById('scenarioType').value;
    const scenario = { type };
    if (type !== 'dominant_supplier_loss') scenario.country = document.getElementById('scenarioCountry').value || null;
    if (type === 'country_disruption' && !scenario.country) {
        alert('No supplier countries are available in the assessed trade data.');
        return;
    }
    if (type === 'tariff') scenario.tariff_pct = parseFloat(document.getElementById('scenarioTariff').value) || 0;
    if (type === 'lead_time') scenario.lead_time_increase_days = parseFloat(document.getElementById('scenarioLead').value) || 0;

    const btn = document.getElementById('runScenarioBtn');
    const old = btn.textContent;
    btn.textContent = 'Running...';
    btn.disabled = true;
    try {
        const res = await fetch(`${API_BASE}/api/risk/scenario`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reagents, scenario })
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail || err));
        }
        lastScenarioResult = await res.json();
        renderScenarioResults(lastScenarioResult);
        renderRouteSummary(lastRiskResults);
    } catch (e) {
        console.error('Scenario failed', e);
        document.getElementById('scenarioResults').innerHTML = `<div class="conc-note">Scenario failed: ${esc(e.message)}</div>`;
    } finally {
        btn.textContent = old;
        btn.disabled = false;
    }
}

function renderScenarioResults(res) {
    const s = res.scenario || {};
    const routeCards = (res.routes || []).map(rt => {
        const tierCls = (rt.exposure_tier || 'unknown').toLowerCase();
        const lines = [];
        if (rt.affected_pct !== null && rt.affected_pct !== undefined) {
            lines.push(`Exposed: <b>${esc(rt.affected_pct_label || fmtPct(rt.affected_pct))}</b> of assessed reagent spend (${fmtMoney(rt.affected_cost)} of ${fmtMoney(rt.assessed_reagent_cost)})`);
        }
        if (rt.unknown_pct) lines.push(`No trade data: ${esc(rt.unknown_pct_label || fmtPct(rt.unknown_pct))} of spend (${esc(rt.unknown_reagents.join(', '))})`);
        if (rt.high_dependency_reagents && rt.high_dependency_reagents.length) {
            lines.push(`High dependency: ${esc(rt.high_dependency_reagents.join(', '))}`);
        }
        if (rt.added_cost !== undefined) lines.push(`Added cost: ${fmtMoney(rt.added_cost)} (+${esc(rt.added_cost_pct_label || fmtPct(rt.added_cost_pct))} of reagent spend)`);
        if (rt.lead_time_increase_days !== undefined) lines.push(`Lead time +${esc(rt.lead_time_increase_days)} days on the affected share of supply`);
        if (rt.note) lines.push(`<span class="conc-note">${esc(rt.note)}</span>`);
        return `
            <div class="route-box">
                <h4>${rt.route === 'All reagents' ? 'All reagents' : `Route ${esc(rt.route)}`}
                    <span class="status-pill status-${esc(tierCls)}" style="font-size:0.6rem; padding:2px 6px; margin-left:6px;">${esc(rt.exposure_label || rt.exposure_tier)}</span>
                </h4>
                <div style="font-size:0.8rem; line-height:1.6;">${lines.join('<br>')}</div>
            </div>`;
    }).join('');

    const rows = (res.reagents || []).map(r => {
        const routes = Object.keys(r.routes || {}).join(', ');
        const affected = Object.values(r.routes || {}).reduce((sum, u) => sum + (u.affected_cost || 0), 0);
        const alts = (r.observed_alternatives || []).slice(0, 3).map(a => `${esc(a.country)} ${fmtPct(a.share_pct)}`).join(', ') || '—';
        const lead = r.lead_time_after_affected_supply !== undefined
            ? `<br><span class="muted-sm">Lead time ${esc(r.lead_time_before)} → ${esc(r.lead_time_after_affected_supply)} d (risk ${esc(r.lead_time_risk_before)} → ${esc(r.lead_time_risk_after_affected_supply)})</span>`
            : '';
        return `<tr>
            <td style="font-weight:600;">${esc(r.name || 'Unknown')}</td>
            <td>${esc(r.hs6 || 'UNKNOWN')}</td>
            <td>${esc(r.trade_status || 'HS6 MISSING')}</td>
            <td>${esc(routes)}</td>
            <td>${esc(r.target_country || '—')}</td>
            <td><span class="status-pill status-${r.status === 'EXPOSED' ? 'high' : (r.status === 'NOT_EXPOSED' ? 'low' : 'unknown')}" style="font-size:0.6rem; padding:1px 6px;">${esc(r.status === 'NOT_LISTED' ? 'NOT LISTED' : r.status)}</span> ${r.status === 'NOT_LISTED' ? '<span class="muted-sm">not in listed exporters</span>' : esc(r.exposure_share_label || '')}</td>
            <td>${r.status === 'UNKNOWN' || r.status === 'NOT_LISTED' ? '<span class="muted-sm">not counted</span>' : fmtMoney(affected)}</td>
            <td>${alts}</td>
            <td>${esc(r.assessment)}${lead}</td>
        </tr>`;
    }).join('');

    document.getElementById('scenarioResults').innerHTML = `
        <h4 style="margin:0 0 6px;">${esc(s.label || 'Scenario')}</h4>
        <p style="margin:0 0 6px; font-size:0.9rem;"><b>${esc(res.summary_text || '')}</b></p>
        <p class="muted-sm" style="margin:0 0 8px;">Hypothetical sensitivity analysis, not a prediction. ${esc(res.limitations || '')}</p>
        <details style="margin-bottom:10px;"><summary class="muted-sm" style="cursor:pointer;">Method & assumptions (deterministic)</summary>
            <ul class="muted-sm" style="margin:6px 0 0 18px;">${(s.assumptions || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul>
        </details>
        <div class="route-summary-grid">${routeCards}</div>
        <table class="risk-table scenario-table" style="margin-top:15px;">
            <thead><tr><th>Reagent</th><th>HS6</th><th>Trade Status</th><th>Routes</th><th>Affected country</th><th>Exposure</th><th>Affected cost</th><th>Other observed source countries</th><th>Assessment</th></tr></thead>
            <tbody>${rows}</tbody>
        </table>`;
}

function csvCell(value) {
    return `"${String(value ?? '').replace(/"/g, '""')}"`;
}

function exportRiskCSV() {
    if (!lastRiskResults) { alert('Run assessment first!'); return; }
    const header = [
        'Reagent', 'HS6', 'Trade_Status', 'CAS', 'Origin', 'Primary_Origin_Share_Pct', 'Secondary_Origin', 'Secondary_Origin_Share_Pct', 'Origin_Share_Basis', 'Stability_Score', 'Mass_g', 'Cost', 'HS_Code', 'Risk_Index', 'Risk_Level',
        'Concentration_Pct', 'Concentration_Flag', 'Data_Source',
        'Origin_Source', 'Stability_Status', 'Geographic_Score', 'Top_Supplier', 'Top_Supplier_Share_Pct', 'Second_Supplier',
        'Second_Supplier_Share_Pct', 'Supplier_Countries', 'Concentration_Explanation', 'Trade_Source', 'Scope', 'Period',
        'Partial_Year', 'Ranking_Basis', 'Share_Basis', 'HS6_Match_Method', 'HS6_Mapping_Quality', 'HS6_Exact',
        'Data_Quality', 'Alternate_Country_Count', 'Substitutability', 'Substitutability_Source',
        'Risk_Index_Missing_Components', 'Routes'
    ];
    let csv = header.join(',') + '\n';
    lastRiskResults.reagents.forEach(r => {
        const c = r.concentration || {};
        const p = r.provenance || {};
        const g = r.geographic_exposure || {};
        const a = r.alternatives || {};
        const m = p.hs6_mapping || {};
        const cells = [
            r.name, r.hs6 || r.hs_code || 'UNKNOWN', r.trade_status, r.cas, r.primary_origin, r.primary_origin_share_pct ?? '', r.secondary_origin, r.secondary_origin_share_pct ?? '', p.share_basis_label || '', r.stability_score ?? '', r.mass_g, r.cost, r.hs_code || '', r.risk_index, r.risk_level,
            c.top_supplier_share ?? '', c.tier || '', p.source_label || '',
            g.origin_source || '', g.stability_status || '', (r.breakdown || {}).geographic ?? '', c.top_supplier_country || '',
            c.top_supplier_share ?? '', c.second_supplier_country || '', c.second_supplier_share ?? '',
            c.supplier_countries_available ?? '', c.explanation || '', p.source || '', p.scope_note || '', p.period_label || '',
            p.is_partial_year ?? '', p.ranking_basis || '', p.share_basis_label || '', m.match_method || '', m.mapping_quality || '',
            m.exact ?? '', (r.data_quality || {}).level || '', a.alternate_country_count ?? '',
            a.substitutability_score ?? '', a.substitutability_source || '',
            ((r.risk_index_components || {}).missing || []).join(';'), Object.keys(r.routes || {}).join(';')
        ];
        csv += cells.map(csvCell).join(',') + '\n';
    });
    // BOM so Excel reads the UTF-8 provenance text (e.g. em dashes) correctly.
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'geographic_risk_report.csv';
    a.click();
}

/**
 * Saves all current CAS-to-Origin mappings from the input table to the server's database.
 */
async function saveMappings() {
    const reagents = collectReagentInputs();
    const mappings = reagents.filter(r => r.cas && r.origin);
    
    if (mappings.length === 0) {
        alert("Enter at least one reagent with both a CAS number and an Origin to save.");
        return;
    }

    let successCount = 0;
    for (const m of mappings) {
        try {
            const res = await fetch(`${API_BASE}/api/risk/update-mapping`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ cas: m.cas, origin: m.origin })
            });
            const data = await res.json();
            if (data.success) successCount++;
        } catch (e) {
            console.error("Failed to save mapping for", m.name, e);
        }
    }

    alert(`Successfully saved/updated ${successCount} mappings to the database.`);
}

function downloadSampleCSV() {
    const csv = "Reagent_Name,HS6,Reagent_CAS,Mass_g,Cost\nantimony oxides,282580,,10,100\nPlatinum on Carbon,,7440-06-4,10,1500\nCopper(II) Chloride,,7447-39-4,100,45";
    const blob = new Blob([csv], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'sample_risk_reagents.csv';
    a.click();
}

async function autoLookupOrigins() {
    const reagents = collectReagentInputs();
    if (reagents.length === 0) { alert('Enter a reagent name or HS6 code in a row first.'); return; }

    const btn = document.querySelector('button[onclick="autoLookupOrigins()"]');
    const oldText = btn.textContent;
    btn.textContent = 'Searching...';
    btn.disabled = true;

    try {
        const res = await fetch(`${API_BASE}/api/risk/lookup-origins`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reagents })
        });
        
        if (!res.ok) throw new Error(await res.text());

        const suggestions = await res.json();
        const rows = activeRiskRows();
        
        suggestions.forEach((s, i) => {
            if (i < rows.length) {
                const row = rows[i];
                const nameInput = row.querySelector('.r-name');
                const pInput = row.querySelector('.r-origin');
                const sInput = row.querySelector('.r-secondary-origin');
                // HS6 describes a trade category; keep any user-entered chemical name.
                const description = s.trade_status === 'MATCHED' && typeof s.product_description === 'string'
                    ? s.product_description.trim() : '';
                if (!nameInput.value.trim() || nameInput.value === row.dataset.autoName) {
                    nameInput.value = description;
                    row.dataset.autoName = description;
                    nameInput.title = description ? 'Product description from the matched trade data. You can edit this name.' : '';
                } else if (row.dataset.autoName) {
                    delete row.dataset.autoName;
                    nameInput.title = '';
                }
                
                if (!pInput.value || pInput.value === 'Unknown' || pInput.value === row.dataset.autoOrigin) { pInput.value = s.primary; row.dataset.autoOrigin = s.primary; }
                if (!sInput.value || sInput.value === 'Unknown' || sInput.value === row.dataset.autoSecondary) { sInput.value = s.secondary; row.dataset.autoSecondary = s.secondary; }
                const status = row.querySelector('.r-trade-status');
                if (status) status.textContent = s.trade_status || 'HS6 MISSING';
                
                // Add visual highlight
                if (description && nameInput.value === row.dataset.autoName) nameInput.style.background = '#e3f2fd';
                pInput.style.background = '#e3f2fd';
                sInput.style.background = '#e3f2fd';
                setTimeout(() => {
                    nameInput.style.background = '';
                    pInput.style.background = '';
                    sInput.style.background = '';
                }, 1000);
            }
        });
    } catch (e) {
        console.error("Auto-lookup failed:", e);
        alert('Lookup failed. Check console.');
    } finally {
        btn.textContent = oldText;
        btn.disabled = false;
    }
}
