/**
 * Experiment Setup — parse a free-text procedure into a partial route draft,
 * let the user review what was captured vs. what's missing, then hand it off
 * to the Planner (via localStorage) where the gaps are highlighted for editing.
 */

const API_BASE = '';
let lastDraft = null;
const NO_LLM_VALUE = '__none__';
let staged = { vA: null, vB: null };   // drafts queued for the Planner
let authInfo = null;                   // {llm_available, auth_mode} from server

// Load a procedure from a .txt or Word (.docx) file instead of pasting it.
// .docx text is extracted server-side (it's a zip of XML); the result drops
// into the textarea so the user can review/edit before parsing.
async function loadDocument(input) {
    const file = input.files && input.files[0];
    if (!file) return;
    const status = document.getElementById('loadStatus');
    status.textContent = `Reading ${file.name}…`;
    try {
        const form = new FormData();
        form.append('file', file);
        const res = await fetch(`${API_BASE}/api/experiment/extract-file`, { method: 'POST', body: form });
        if (!res.ok) {
            let msg = await res.text();
            try { msg = JSON.parse(msg).detail || msg; } catch (_) {}
            throw new Error(msg);
        }
        const { text } = await res.json();
        document.getElementById('elnText').value = text;
        status.textContent = `Loaded ${file.name} — review the text, then Parse.`;
    } catch (e) {
        console.error('Load document failed:', e);
        status.innerHTML = `<span class="draft-missing">Couldn't load ${escapeHtml(file.name)}: ${escapeHtml(e.message)}</span>`;
    } finally {
        input.value = '';  // allow re-selecting the same file
    }
}

// Populate the model dropdown from the editable server-side catalog
// (data/gemini_models.json). The first (LLM) entry is the default; a
// "No LLM" option is appended so the heuristic parser can be chosen too.
async function loadModels() {
    const select = document.getElementById('modelSelect');
    let opts = '';
    try {
        const res = await fetch(`${API_BASE}/api/experiment/models`);
        if (!res.ok) throw new Error(await res.text());
        const { models } = await res.json();
        opts = (models || [])
            .map(m => `<option value="${escapeHtml(m.id)}">${escapeHtml(m.name)}</option>`)
            .join('');
    } catch (e) {
        console.error('Failed to load models:', e);
    }
    // LLM stays the default (first option); heuristic is opt-in.
    opts += `<option value="${NO_LLM_VALUE}">No LLM (heuristic parser)</option>`;
    select.innerHTML = opts;
    updateStatusIndicator();
}

// Ask the server which auth backend is live (API key vs Vertex/gcloud vs none).
async function loadStatus() {
    try {
        const res = await fetch(`${API_BASE}/api/experiment/status`);
        if (res.ok) authInfo = await res.json();
    } catch (e) {
        console.error('Failed to load status:', e);
    }
    updateStatusIndicator();
}

// Reflect what will actually run for the current dropdown selection.
function updateStatusIndicator() {
    const el = document.getElementById('authStatus');
    if (!el) return;
    const sel = document.getElementById('modelSelect');
    const value = sel ? sel.value : '';
    const label = sel && sel.selectedOptions[0] ? sel.selectedOptions[0].text : '';

    if (value === NO_LLM_VALUE) {
        el.innerHTML = '🟡 Heuristic parser — no AI/LLM used.';
    } else if (authInfo && authInfo.auth_mode === 'mock') {
        el.textContent = 'Mock/simulation mode — no credentials or network used.';
    } else if (!authInfo) {
        el.textContent = 'Checking backend…';
    } else if (authInfo.llm_available) {
        const mode = authInfo.auth_mode === 'vertex' ? 'Vertex AI (gcloud)' : 'API key';
        el.innerHTML = `🟢 LLM active · <b>${escapeHtml(label)}</b> <span class="muted">via ${mode}</span>`;
    } else {
        el.innerHTML = '🔴 No Gemini credentials found — will fall back to the heuristic '
            + 'parser. Configure LLM_PROVIDER=vertexai + gcloud ADC, or set GEMINI_API_KEY.';
    }
}

document.addEventListener('DOMContentLoaded', () => { loadModels(); loadStatus(); });

async function parseProcedure() {
    const text = document.getElementById('elnText').value.trim();
    const target = document.getElementById('targetMolecule').value.trim();
    const model = document.getElementById('modelSelect').value || null;
    if (!text) { alert('Paste a procedure first.'); return; }

    const area = document.getElementById('reviewArea');
    area.innerHTML = '<p class="muted">Parsing…</p>';
    try {
        const res = await fetch(`${API_BASE}/api/experiment/parse`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text, target_molecule: target || null, model })
        });
        if (!res.ok) throw new Error(await res.text());
        lastDraft = await res.json();
        renderReview(lastDraft);
    } catch (e) {
        console.error('Parse failed:', e);
        area.innerHTML = `<p class="draft-missing">Parse failed: ${e.message}</p>`;
        document.getElementById('sendRow').style.display = 'none';
    }
}

function escapeHtml(s) {
    return String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

function field(label, value, missing) {
    const v = missing
        ? `<span class="draft-missing">— missing —</span>`
        : `<span class="v">${escapeHtml(value)}</span>`;
    return `<span class="draft-field"><span class="k">${label}:</span> ${v}</span>`;
}

function renderReview(draft) {
    document.getElementById('extractorTag').textContent = draft.extractor || '';
    const area = document.getElementById('reviewArea');
    const totalMissing = draft.missing_required_count || 0;

    let html = `<div class="draft-banner ${totalMissing === 0 ? 'complete' : ''}">
        ${totalMissing === 0
            ? '✅ All key fields captured — review and send.'
            : `⚠ <b>${totalMissing}</b> field(s) need your input. They'll be highlighted in the Planner after loading.`}
    </div>`;

    if (draft.warnings && draft.warnings.length) {
        html += `<div class="muted" style="margin-bottom:10px;">${draft.warnings.map(w => '• ' + escapeHtml(w)).join('<br>')}</div>`;
    }

    (draft.steps || []).forEach(s => {
        html += `<div class="draft-step">
            <h4>Step ${s.step_id}${s.name ? ': ' + escapeHtml(s.name) : ''}</h4>
            <div style="margin-bottom:6px;">
                ${field('Product MW', s.product_mw, s.product_mw == null)}
                ${field('Yield %', s.yield_percent, s.yield_percent == null)}
                ${field('Temp', s.temperature, !s.temperature)}
                ${field('Time', s.time, !s.time)}
                ${s.solvent_name
                    ? field('Solvent', s.solvent_name + (s.solvent_volume ? ` (${s.solvent_volume} ${s.solvent_volume_unit || ''})` : ''), false)
                    : field('Solvent', '', true)}
            </div>`;

        if (!s.reagents || s.reagents.length === 0) {
            html += `<div class="muted">No reagents detected — add them in the Planner.</div>`;
        } else {
            s.reagents.forEach(r => {
                html += `<div class="reagent-line">
                    <span class="v" style="min-width:130px;">${r.name ? escapeHtml(r.name) : '<span class="draft-missing">unnamed</span>'}</span>
                    ${field('MW', r.mw, r.mw == null)}
                    ${field('Equiv', r.equivalents, r.equivalents == null)}
                    ${field('Mass', r.mass != null ? r.mass + ' ' + (r.mass_unit || 'g') : '', r.mass == null)}
                    ${r.is_limiting ? '<span class="draft-badge review">limiting?</span>' : ''}
                </div>`;
            });
        }
        html += `</div>`;
    });

    area.innerHTML = html;
    document.getElementById('sendRow').style.display = 'flex';
}

// Stage the current draft as Route A or B. Staging lets you assemble two
// routes (parse one → stage A, parse another → stage B) and send them together.
function stageDraft() {
    if (!lastDraft) { alert('Parse a procedure first.'); return; }
    const side = document.getElementById('sendTarget').value; // 'vA' | 'vB'
    staged[side] = lastDraft;
    renderStaged();
}

function renderStaged() {
    const fmt = (d) => {
        if (!d) return '<span class="muted">—</span>';
        const n = (d.steps || []).length;
        return `${escapeHtml(d.target_molecule || 'untitled')} (${n} step${n === 1 ? '' : 's'})`;
    };
    document.getElementById('stagedSummary').innerHTML =
        `Staged → <b>Route A:</b> ${fmt(staged.vA)} &nbsp;·&nbsp; <b>Route B:</b> ${fmt(staged.vB)}`;
}

function draftToPayloadRoute(draft, side) {
    const steps = (draft.steps || []).map(s => ({
        ...s,
        // The Planner's volume box reads `solvent_volume_l`; pass the raw amount
        // (in its unit) so it displays correctly, and give the bottle a default.
        solvent_volume_l: s.solvent_volume != null ? s.solvent_volume : '',
        solvent_bottle_l: 1,
    }));
    return { target: side, target_molecule: draft.target_molecule || '', steps };
}

function sendToPlanner() {
    // If nothing was explicitly staged, treat the current draft as the selected
    // side so the simple one-route flow still works in a single click.
    if (!staged.vA && !staged.vB && lastDraft) {
        staged[document.getElementById('sendTarget').value] = lastDraft;
    }

    const routes = [];
    if (staged.vA) routes.push(draftToPayloadRoute(staged.vA, 'vA'));
    if (staged.vB) routes.push(draftToPayloadRoute(staged.vB, 'vB'));

    if (!routes.length) { alert('Parse and stage at least one route first.'); return; }

    // Multi-route hand-off; the Planner loads each route into its own side.
    localStorage.setItem('pendingRouteDraft', JSON.stringify({ routes }));
    window.location.href = '/dashboard.html';
}
