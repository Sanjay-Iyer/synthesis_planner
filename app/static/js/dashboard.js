/**
 * Dashboard Logic — Synthesis cost analysis, charts, and data management.
 * Migrated from python-polymer/frontend/app.js with updated API paths.
 */

const API_BASE = '';  // Same origin — no need for http://127.0.0.1:8000

let counters = { vA: 0, vB: 0 };
let lastAnalysis = { vA: null, vB: null };
let barInst = null, pieAInst = null, pieBInst = null;

function addStep(side, data = null) {
    counters[side]++;
    const id = counters[side];
    const container = document.getElementById(`steps-${side}`);
    
    let deps = "";
    for(let i=1; i < id; i++) {
        const checked = (data?.depends_on?.includes(i)) ? "checked" : "";
        deps += `<label style="margin-right:8px;"><input type="checkbox" class="dep-${side}-${id}" value="${i}" ${checked}> S${i}</label>`;
    }

    const html = `
        <div class="step-card" id="card-${side}-${id}">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                <strong style="color:var(--primary);">Step ${id}</strong>
                <input type="text" id="name-${side}-${id}" value="${data?.name || ''}" style="width:40%;">
                <label style="font-size:0.75em;">Prod MW: <input type="number" id="pmw-${side}-${id}" value="${data?.product_mw || 0}" step="any" style="width:65px;"></label>
            </div>
            
            <div style="display: flex; gap: 10px; margin-bottom: 10px; background: #fdf9f3; padding: 5px; border-radius: 4px; border: 1px solid #fae1c3;">
                <label style="font-size:0.7em;">Temp: <input type="text" id="temp-${side}-${id}" value="${data?.temperature || 'RT'}" style="width:75px;"></label>
                <label style="font-size:0.7em;">Time: <input type="text" id="time-${side}-${id}" value="${data?.time || 'N/A'}" style="width:75px;"></label>
                <div style="font-size:0.7em; color:var(--text-muted); padding-top:5px;">Feeds: ${deps || "Materials"}</div>
            </div>

            <table id="table-${side}-${id}">
                <thead><tr><th>Reagent</th><th>MW</th><th>$/g</th><th>Moles</th><th>Lim?</th></tr></thead>
                <tbody>${data?.reagents ? data.reagents.map(r => `<tr>
                    <td><input type="text" value="${r.name || ''}"></td>
                    <td><input type="number" step="any" value="${r.mw || ''}"></td>
                    <td><input type="number" step="any" value="${r.cost_per_g || 0}"></td>
                    <td><input type="number" step="any" value="${r.moles || ''}"></td>
                    <td><input type="checkbox" ${r.is_limiting ? 'checked' : ''}></td>
                </tr>`).join('') : '<tr><td><input type="text"></td><td><input type="number" step="any"></td><td><input type="number" step="any"></td><td><input type="number" step="any"></td><td><input type="checkbox"></td></tr>'}</tbody>
            </table>
            <button class="btn btn-ghost btn-sm" onclick="addReagentRow('${side}', ${id})">+ Reagent</button>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top:10px; background:#f1f2f6; padding:8px; border-radius:5px;">
                <label style="font-size:0.7em;">Solvent: <input type="text" id="sname-${side}-${id}" value="${data?.solvent_name || 'Solvent'}"></label>
                <label style="font-size:0.7em;">Conc (M): <input type="number" id="mol-${side}-${id}" value="${data?.molarity || 0.5}" step="any"></label>
                <label style="font-size:0.7em;">Solv $/L: <input type="number" id="sprc-${side}-${id}" value="${data?.solvent_price_per_l || 0}" step="any"></label>
                <label style="font-size:0.7em;">Yield %: <input type="number" id="yield-${side}-${id}" value="${data?.yield_percent || 100}" step="any"></label>
            </div>
            <textarea id="proc-${side}-${id}" style="margin-top:10px; height:70px; width:100%; font-size:0.8em;" placeholder="Procedure Notes..."></textarea>
        </div>`;
    
    container.insertAdjacentHTML('beforeend', html);
    if (data?.procedure) { document.getElementById(`proc-${side}-${id}`).value = data.procedure; }
}

function addReagentRow(side, stepId) {
    const tbody = document.getElementById(`table-${side}-${stepId}`).getElementsByTagName('tbody')[0];
    const row = tbody.insertRow();
    row.innerHTML = `<td><input type="text"></td><td><input type="number" step="any"></td><td><input type="number" step="any"></td><td><input type="number" step="any"></td><td><input type="checkbox"></td>`;
}

function collectStepData(side) {
    const steps = [];
    for (let i = 1; i <= counters[side]; i++) {
        const table = document.getElementById(`table-${side}-${i}`);
        if (!table) continue;
        const reagents = Array.from(table.rows).slice(1).map(row => ({
            name: row.cells[0].querySelector('input').value,
            mw: parseFloat(row.cells[1].querySelector('input').value) || 0,
            cost_per_g: parseFloat(row.cells[2].querySelector('input').value) || 0,
            moles: parseFloat(row.cells[3].querySelector('input').value) || 0,
            is_limiting: row.cells[4].querySelector('input').checked
        }));
        steps.push({
            step_id: i, name: document.getElementById(`name-${side}-${i}`).value,
            product_mw: parseFloat(document.getElementById(`pmw-${side}-${i}`).value) || 0,
            reagents, molarity: parseFloat(document.getElementById(`mol-${side}-${i}`).value) || 0.5,
            solvent_name: document.getElementById(`sname-${side}-${i}`).value,
            solvent_density: 0.85, solvent_price_per_l: parseFloat(document.getElementById(`sprc-${side}-${i}`).value) || 0,
            yield_percent: parseFloat(document.getElementById(`yield-${side}-${i}`).value) || 100,
            temperature: document.getElementById(`temp-${side}-${i}`).value,
            time: document.getElementById(`time-${side}-${i}`).value,
            procedure: document.getElementById(`proc-${side}-${i}`).value,
            depends_on: Array.from(document.querySelectorAll(`.dep-${side}-${i}:checked`)).map(cb => parseInt(cb.value))
        });
    }
    return steps;
}

async function runAnalysis() {
    try {
        lastAnalysis.vA = await getEstimate('vA');
        lastAnalysis.vB = await getEstimate('vB');
        displayDashboard(lastAnalysis.vA, lastAnalysis.vB);
    } catch (e) { alert("Analysis failed. Is the server running?"); }
}

async function getEstimate(side) {
    const steps = collectStepData(side);
    if (!steps.length) return { total_cost: 0, cost_per_kg: 0, steps: [] };
    const target = parseFloat(document.getElementById(`target-${side}`).value) || 1.0;
    const res = await fetch(`${API_BASE}/api/synthesis/estimate`, { 
        method: "POST", headers: {"Content-Type":"application/json"}, 
        body: JSON.stringify({ steps, target_mass_kg: target }) 
    });
    return await res.json();
}

function displayDashboard(a, b) {
    let html = `<h3>Synthesis Summary</h3><table style="color:white; width:100%;">
    <tr><th>Metric</th><th>Route A</th><th>Route B</th></tr>
    <tr><td>Budget</td><td>$${(a.total_cost || 0).toLocaleString()}</td><td>$${(b.total_cost || 0).toLocaleString()}</td></tr>
    <tr style="color:#00cec9;"><td>E-Factor</td><td>${a.e_factor || 0}</td><td>${b.e_factor || 0}</td></tr></table>`;

    const pA = getPieData(a), pB = getPieData(b);

    [a, b].forEach((route, idx) => {
        if (!route.steps) return;
        html += `<div style="margin-top:20px; background:#333; padding:15px; border-radius:8px; color:white; border-left:4px solid ${idx==0?'var(--primary)':'var(--secondary)'};">
            <strong>Route ${idx==0?'A':'B'} Procurement:</strong>`;
        route.steps.forEach(s => {
            html += `<div style="margin-top:15px; border-top:1px solid #555; padding-top:8px;">
                <div style="display:flex; justify-content:space-between; font-size:0.85em; margin-bottom:5px;">
                    <span style="color:#00cec9;">S${s.step_id}: ${s.name}</span>
                    <span>Subtotal: $${(s.step_total || 0).toLocaleString()}</span>
                </div>
                <div style="font-size:0.75em; background:rgba(255,255,255,0.05); padding:8px; margin:5px 0; white-space: pre-wrap; border:1px solid #555;">${s.procedure || 'No notes.'}</div>
                <table style="width:100%; font-size:0.7em; color:#dfe6e9;"><tr><th>Reagent</th><th>Mass(g)</th><th>Cost</th></tr>`;
            s.reagents.forEach(r => { html += `<tr><td>${r.name}</td><td>${r.mass_g.toLocaleString()}</td><td>$${r.item_cost.toLocaleString()}</td></tr>`; });
            html += `</table></div>`;
        });
        html += `</div>`;
    });
    document.getElementById("comp-stats").innerHTML = html;
    updateCharts(a, b, pA, pB);
}

function getPieData(route) {
    const pie = { labels: [], data: [], colors: [] };
    const palette = ['#0984e3', '#00cec9', '#6c5ce7', '#fab1a0', '#fdcb6e', '#e17055', '#2ecc71'];
    if (!route.steps) return pie;
    route.steps.forEach(s => {
        if (s.solvent_cost > 0) { pie.labels.push(`S${s.step_id} ${s.solvent_name}`); pie.data.push(s.solvent_cost); pie.colors.push('#b2bec3'); }
        s.reagents.forEach(r => { 
            if (r.item_cost > 0) { pie.labels.push(r.name); pie.data.push(r.item_cost); pie.colors.push(palette[pie.data.length % palette.length]); }
        });
    });
    return pie;
}

function updateCharts(a, b, pA, pB) {
    if (barInst) barInst.destroy();
    barInst = new Chart(document.getElementById('compareChart'), { type: 'bar', data: { labels: ['A', 'B'], datasets: [{ data: [a.total_cost || 0, b.total_cost || 0], backgroundColor: ['#0984e3', '#27ae60'] }] }, options: { maintainAspectRatio: false } });

    if (pieAInst) pieAInst.destroy();
    if (pA.data.length) pieAInst = new Chart(document.getElementById('pieA'), { type: 'doughnut', data: { labels: pA.labels, datasets: [{ data: pA.data, backgroundColor: pA.colors }] }, options: { maintainAspectRatio: false, plugins: { legend: { display: false } } } });
    
    if (pieBInst) pieBInst.destroy();
    if (pB.data.length) pieBInst = new Chart(document.getElementById('pieB'), { type: 'doughnut', data: { labels: pB.labels, datasets: [{ data: pB.data, backgroundColor: pB.colors }] }, options: { maintainAspectRatio: false, plugins: { legend: { display: false } } } });
}

function exportToCSV() {
    if (!lastAnalysis.vA && !lastAnalysis.vB) { alert("Run analysis first!"); return; }
    let csv = "Route,Step,Name,Molarity,Solvent,Reagent,Mass_g,Cost\n";
    ['vA', 'vB'].forEach(side => {
        const res = lastAnalysis[side];
        if(res?.steps) res.steps.forEach(s => { 
            s.reagents.forEach(r => { csv += `${side},${s.step_id},"${s.name}",${s.molarity},"${s.solvent_name}","${r.name}",${r.mass_g},${r.item_cost}\n`; }); 
        });
    });
    const blob = new Blob([csv], {type: 'text/csv'});
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'procurement_report.csv'; a.click();
}

function loadFromFile(ev, target) {
    const reader = new FileReader();
    reader.onload = (e) => {
        const d = JSON.parse(e.target.result);
        if (target === 'both') {
            clearRouteUI('vA'); clearRouteUI('vB');
            if(d.routeA?.steps) d.routeA.steps.forEach(s => addStep('vA', s));
            if(d.routeB?.steps) d.routeB.steps.forEach(s => addStep('vB', s));
        } else {
            clearRouteUI(target);
            const steps = d.routeA?.steps || d.routeB?.steps || [];
            steps.forEach(s => addStep(target, s));
        }
    };
    reader.readAsText(ev.target.files[0]);
}

function saveToFile() {
    const data = { routeA: { target: document.getElementById('target-vA').value, steps: collectStepData('vA') }, routeB: { target: document.getElementById('target-vB').value, steps: collectStepData('vB') } };
    const blob = new Blob([JSON.stringify(data)], {type: 'application/json'});
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'project.json'; a.click();
}

async function runOptimizationAudit() {
    const steps = collectStepData('vA');
    const target = parseFloat(document.getElementById(`target-vA`).value) || 1.0;
    const res = await fetch(`${API_BASE}/api/synthesis/audit`, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ steps, target_mass_kg: target }) });
    const data = await res.json();
    let html = `<div style="background:var(--purple); padding:15px; border-radius:10px; margin-top:15px; color:white;"><h4>🚀 Yield Impact Audit</h4><table style="width:100%; color:white; font-size:0.8em;"><tr><th>Step</th><th>Sensitivity</th></tr>`;
    data.audit.forEach(i => { html += `<tr><td>${i.step_id}</td><td>$${i.sensitivity}/% yield</td></tr>`; });
    document.getElementById("audit-container").innerHTML = html + "</table></div>";
}

function clearRoute(side) { if (confirm(`Clear Route ${side}?`)) clearRouteUI(side); }
function clearRouteUI(side) { document.getElementById(`steps-${side}`).innerHTML = ""; counters[side] = 0; }
