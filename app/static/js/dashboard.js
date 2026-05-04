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
        <div class="step-card" id="card-${side}-${id}" style="position:relative;">
            <button onclick="this.closest('.step-card').remove()" style="position:absolute; top:8px; right:8px; background:transparent; border:none; color:#b2bec3; cursor:pointer; font-size:1.2em; line-height:1;" title="Delete Step">×</button>
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; padding-right:20px;">
                <strong style="color:var(--primary);">Step ${id}</strong>
                <input type="text" id="name-${side}-${id}" value="${data?.name || ''}" style="width:40%;">
                <label style="font-size:0.75em;">Prod MW: <input type="number" id="pmw-${side}-${id}" value="${data?.product_mw || 0}" step="any" style="width:65px;" oninput="calcProductProduced(this)"></label>
            </div>
            
            <div style="display: flex; gap: 10px; margin-bottom: 10px; background: #fdf9f3; padding: 5px; border-radius: 4px; border: 1px solid #fae1c3;">
                <label style="font-size:0.7em;">Temp: <input type="text" id="temp-${side}-${id}" value="${data?.temperature || 'RT'}" style="width:75px;"></label>
                <label style="font-size:0.7em;">Time: <input type="text" id="time-${side}-${id}" value="${data?.time || 'N/A'}" style="width:75px;"></label>
                <div style="font-size:0.7em; color:var(--text-muted); padding-top:5px;">Feeds: ${deps || "Materials"}</div>
            </div>

            <table id="table-${side}-${id}">
                <thead><tr><th>Reagent</th><th>MW</th><th style="color:#e74c3c;">Pkg(g)</th><th style="color:#e74c3c;">Pkg($)</th><th>Eq</th><th>Mass</th><th>Lim?</th><th></th></tr></thead>
                <tbody>${data?.reagents ? data.reagents.map(r => {
                    const pkgsz = r.pkg_size || 1;
                    const pkgpr = r.pkg_price || (r.cost_per_g ? r.cost_per_g * pkgsz : 0);
                    return `<tr>
                    <td><input type="text" class="r-name" value="${r.name || ''}"></td>
                    <td><input type="number" step="any" class="r-mw" value="${r.mw || ''}" oninput="calcStoich(this)"></td>
                    <td><input type="number" step="any" class="r-pkgsz" value="${pkgsz}" style="width:55px;"></td>
                    <td><input type="number" step="any" class="r-pkgpr" value="${pkgpr}" style="width:55px;"></td>
                    <td><input type="number" step="any" class="r-eq" value="${r.moles || ''}" oninput="calcStoich(this)"></td>
                    <td>
                        <input type="number" step="any" class="r-mass" value="${r.mass || ''}" oninput="calcStoich(this, true)" style="width:65px; display:inline-block;">
                        <select class="r-mass-unit" onchange="calcStoich(this)" style="width:42px; display:inline-block; font-size:0.7em; padding:2px;"><option value="g">g</option><option value="mg" ${r.mass_unit==='mg'?'selected':''}>mg</option><option value="kg" ${r.mass_unit==='kg'?'selected':''}>kg</option></select>
                    </td>
                    <td><input type="checkbox" class="r-lim" ${r.is_limiting ? 'checked' : ''} onchange="handleLimChange(this)"></td>
                    <td><button onclick="const tb=this.closest(&apos;tbody&apos;); this.closest(&apos;tr&apos;).remove(); calcStoichByTbody(tb);" style="background:transparent; border:none; color:#e74c3c; cursor:pointer; font-weight:bold;" title="Delete Reagent">×</button></td>
                </tr>`}).join('') : `<tr>
                    <td><input type="text" class="r-name"></td>
                    <td><input type="number" step="any" class="r-mw" oninput="calcStoich(this)"></td>
                    <td><input type="number" step="any" class="r-pkgsz" style="width:55px;"></td>
                    <td><input type="number" step="any" class="r-pkgpr" style="width:55px;"></td>
                    <td><input type="number" step="any" class="r-eq" oninput="calcStoich(this)"></td>
                    <td>
                        <input type="number" step="any" class="r-mass" oninput="calcStoich(this, true)" style="width:65px; display:inline-block;">
                        <select class="r-mass-unit" onchange="calcStoich(this)" style="width:42px; display:inline-block; font-size:0.7em; padding:2px;"><option value="g">g</option><option value="mg">mg</option><option value="kg">kg</option></select>
                    </td>
                    <td><input type="checkbox" class="r-lim" onchange="handleLimChange(this)"></td>
                    <td><button onclick="const tb=this.closest(&apos;tbody&apos;); this.closest(&apos;tr&apos;).remove(); calcStoichByTbody(tb);" style="background:transparent; border:none; color:#e74c3c; cursor:pointer; font-weight:bold;" title="Delete Reagent">×</button></td>
                </tr>`}</tbody>
            </table>
            <div style="display:flex; gap:10px; margin-top:5px; align-items:center;">
                <button class="btn btn-ghost btn-sm" onclick="addReagentRow('${side}', ${id})">+ Manual Reagent</button>
                <div style="flex:1; display:flex; gap:5px;">
                    <input type="text" id="smiles-${side}-${id}" placeholder="Paste SMILES, SELFIES, or InChI..." style="flex:1; font-size:0.8em; padding:4px; border:1px solid var(--border); border-radius:3px;">
                    <button class="btn btn-primary btn-sm" onclick="addReagentFromSmiles('${side}', ${id})">+ Add Molecule</button>
                </div>
            </div>
            <div id="smiles-display-${side}-${id}" style="font-size:0.75em; color:var(--text); margin-top:5px; padding:5px; background:#eef2f3; border:1px solid var(--border); border-radius:4px; display:none;"></div>
            
            <div style="display: flex; flex-wrap: wrap; gap: 10px; margin-top:10px; background:#f1f2f6; padding:8px; border-radius:5px;">
                <label style="font-size:0.7em;">Solvent: <input type="text" id="sname-${side}-${id}" value="${data?.solvent_name || 'Solvent'}" style="width:90px;"></label>
                <label style="font-size:0.7em;">Volume: <input type="number" id="vol-${side}-${id}" value="${data?.solvent_volume_l || ''}" step="any" style="width:65px; display:inline-block;">
                <select id="volu-${side}-${id}" onchange="calcProductProduced(this)" style="width:42px; display:inline-block; font-size:0.7em; padding:2px;"><option value="L" ${data?.solvent_volume_unit==='L'?'selected':''}>L</option><option value="mL" ${data?.solvent_volume_unit==='mL'?'selected':''}>mL</option></select></label>
                <label style="font-size:0.7em; color:#e74c3c; font-weight:bold;">Bottle (L): <input type="number" id="sbotl-${side}-${id}" value="${data?.solvent_bottle_l || 1}" step="any" style="width:75px; font-weight:normal; color:var(--text);"></label>
                <label style="font-size:0.7em; color:#e74c3c; font-weight:bold;">Bottle ($): <input type="number" id="sbotp-${side}-${id}" value="${data?.solvent_bottle_price || (data?.solvent_price_per_l ? data?.solvent_price_per_l * (data?.solvent_bottle_l || 1) : 0)}" step="any" style="width:75px; font-weight:normal; color:var(--text);"></label>
            </div>
            
            <div style="display: flex; flex-wrap: wrap; gap: 10px; margin-top:10px; background:#e8f4f8; padding:8px; border-radius:5px;">
                <label style="font-size:0.7em; font-weight:bold;">Final Product</label>
                <label style="font-size:0.7em;">Yield %: <input type="number" id="yield-${side}-${id}" value="${data?.yield_percent || 100}" step="any" style="width:60px;" oninput="calcProductProduced(this)"></label>
                <label style="font-size:0.7em;">Produced (g): <input type="number" id="prodg-${side}-${id}" value="" step="any" style="width:70px;" readonly disabled></label>
            </div>
            <textarea id="proc-${side}-${id}" style="margin-top:10px; height:70px; width:100%; font-size:0.8em;" placeholder="Procedure Notes..."></textarea>
        </div>`;
    
    container.insertAdjacentHTML('beforeend', html);
    if (data?.procedure) { document.getElementById(`proc-${side}-${id}`).value = data.procedure; }
    
    if (data) {
        setTimeout(() => {
            const table = document.getElementById(`table-${side}-${id}`);
            if (table) {
                const tbody = table.getElementsByTagName('tbody')[0];
                if (tbody) calcStoichByTbody(tbody);
            }
        }, 50);
    }
}

function addReagentRow(side, stepId) {
    const tbody = document.getElementById(`table-${side}-${stepId}`).getElementsByTagName('tbody')[0];
    const row = tbody.insertRow();
    row.innerHTML = `<td><input type="text" class="r-name"></td><td><input type="number" step="any" class="r-mw" oninput="calcStoich(this)"></td><td><input type="number" step="any" class="r-pkgsz"></td><td><input type="number" step="any" class="r-pkgpr"></td><td><input type="number" step="any" class="r-eq" oninput="calcStoich(this)"></td><td><input type="number" step="any" class="r-mass" oninput="calcStoich(this, true)" style="width:65px; display:inline-block;"><select class="r-mass-unit" onchange="calcStoich(this)" style="width:42px; display:inline-block; font-size:0.7em; padding:2px;"><option value="g">g</option><option value="mg">mg</option><option value="kg">kg</option></select></td><td><input type="checkbox" class="r-lim" onchange="handleLimChange(this)"></td><td><button onclick="const tb=this.closest(&apos;tbody&apos;); this.closest(&apos;tr&apos;).remove(); calcStoichByTbody(tb);" style="background:transparent; border:none; color:#e74c3c; cursor:pointer; font-weight:bold;" title="Delete Reagent">×</button></td>`;
}

async function addReagentFromSmiles(side, stepId) {
    const inputEl = document.getElementById(`smiles-${side}-${stepId}`);
    const val = inputEl.value.trim();
    if (!val) return;
    
    // Add row first with loading state
    const tbody = document.getElementById(`table-${side}-${stepId}`).getElementsByTagName('tbody')[0];
    
    // if the very first row is completely empty, we can just overwrite it instead of adding a new one
    let targetRow = null;
    if (tbody.rows.length === 1) {
        const firstRowInputs = tbody.rows[0].querySelectorAll('input[type="text"], input[type="number"]');
        let isEmpty = true;
        firstRowInputs.forEach(i => { if(i.value) isEmpty = false; });
        if (isEmpty) targetRow = tbody.rows[0];
    }
    
    if (!targetRow) {
        targetRow = tbody.insertRow();
        targetRow.innerHTML = `<td><input type="text" class="r-name"></td><td><input type="number" step="any" class="r-mw" oninput="calcStoich(this)"></td><td><input type="number" step="any" class="r-pkgsz"></td><td><input type="number" step="any" class="r-pkgpr"></td><td><input type="number" step="any" class="r-eq" oninput="calcStoich(this)"></td><td><input type="number" step="any" class="r-mass" oninput="calcStoich(this, true)"></td><td><input type="checkbox" class="r-lim" onchange="handleLimChange(this)"></td><td><button onclick="const tb=this.closest(&apos;tbody&apos;); this.closest(&apos;tr&apos;).remove(); calcStoichByTbody(tb);" style="background:transparent; border:none; color:#e74c3c; cursor:pointer; font-weight:bold;" title="Delete Reagent">×</button></td>`;
    }
    
    const inputs = targetRow.querySelectorAll('input');
    inputs[0].value = "Fetching...";
    
    try {
        const [nameRes, mwRes] = await Promise.all([
            fetch('/api/synthesis/molecule-name', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ string_input: val }) }),
            fetch('/api/synthesis/molecular-weight', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ string_input: val }) })
        ]);
        
        let name = "Unknown";
        let mw = 0;
        
        if (nameRes.ok) {
            const nd = await nameRes.json();
            name = nd.name;
        }
        if (mwRes.ok) {
            const md = await mwRes.json();
            if (md.mw > 0) mw = md.mw;
        }
        
        inputs[0].value = name;
        inputs[1].value = mw > 0 ? mw : '';
        if (mw > 0) calcStoich(inputs[1]);
        
        // Update SMILES display container
        const displayDiv = document.getElementById(`smiles-display-${side}-${stepId}`);
        displayDiv.style.display = "block";
        displayDiv.innerHTML += `<div style="margin-bottom:2px;"><b>${name}:</b> <code>${val}</code></div>`;
        
        inputEl.value = ""; // clear input
        
    } catch (err) {
        inputs[0].value = "Error";
    }
}

function handleLimChange(cb) {
    if (cb.checked) {
        const tbody = cb.closest('tbody');
        const cbs = tbody.querySelectorAll('.r-lim');
        cbs.forEach(c => { if(c !== cb) c.checked = false; });
    }
    calcStoichByTbody(cb.closest('tbody'));
}

function calcStoich(el, isMass = false) {
    calcStoichByTbody(el.closest('tbody'), isMass ? el : null);
}

function calcStoichByTbody(tbody, changedMassInput = null) {
    const rows = tbody.rows;
    let baseMoles = 0;
    
    if (changedMassInput) {
        const mw = parseFloat(changedMassInput.closest('tr').querySelector('.r-mw').value) || 0;
        const eq = parseFloat(changedMassInput.closest('tr').querySelector('.r-eq').value) || 1;
        const mass = parseFloat(changedMassInput.value) || 0;
        const unit = changedMassInput.closest('tr').querySelector('.r-mass-unit').value;
        let massInG = mass;
        if (unit === 'mg') massInG = mass / 1000;
        if (unit === 'kg') massInG = mass * 1000;
        
        if (mw > 0 && eq > 0) {
            baseMoles = massInG / mw / eq;
        }
    } else {
        let limRow = null;
        for (let i=0; i<rows.length; i++) {
            const limCb = rows[i].querySelector('.r-lim');
            if (limCb && limCb.checked) { limRow = rows[i]; break; }
        }
        if (limRow) {
            const limMw = parseFloat(limRow.querySelector('.r-mw').value) || 0;
            const limEq = parseFloat(limRow.querySelector('.r-eq').value) || 1;
            const limMass = parseFloat(limRow.querySelector('.r-mass').value) || 0;
            const unit = limRow.querySelector('.r-mass-unit').value;
            let massInG = limMass;
            if (unit === 'mg') massInG = limMass / 1000;
            if (unit === 'kg') massInG = limMass * 1000;
            
            if (limMw > 0 && limEq > 0) {
                baseMoles = massInG / limMw / limEq;
            }
        }
    }
    
    if (baseMoles <= 0) return;
    
    for (let i=0; i<rows.length; i++) {
        const massInput = rows[i].querySelector('.r-mass');
        if (massInput === changedMassInput) continue;
        
        const mw = parseFloat(rows[i].querySelector('.r-mw').value) || 0;
        const eq = parseFloat(rows[i].querySelector('.r-eq').value) || 0;
        const unit = rows[i].querySelector('.r-mass-unit').value;
        
        if (mw > 0 && eq > 0) {
            let massInG = baseMoles * eq * mw;
            let val = massInG;
            if (unit === 'mg') val = massInG * 1000;
            if (unit === 'kg') val = massInG / 1000;
            massInput.value = val.toFixed(3);
        }
    }
    
    const card = tbody.closest('.step-card');
    if (card) {
        const pmwInput = card.querySelector('input[id^="pmw-"]');
        if (pmwInput) calcProductProduced(pmwInput);
    }
}

function calcProductProduced(el) {
    if (!el) return;
    const card = el.closest('.step-card');
    if (!card) return;
    
    const sideMatch = card.id.match(/card-(vA|vB)-(\d+)/);
    if (!sideMatch) return;
    const side = sideMatch[1];
    const id = sideMatch[2];
    
    const pmw = parseFloat(document.getElementById(`pmw-${side}-${id}`).value) || 0;
    const yieldPct = parseFloat(document.getElementById(`yield-${side}-${id}`).value) || 0;
    const prodgInput = document.getElementById(`prodg-${side}-${id}`);
    
    const tbody = card.querySelector('tbody');
    if (!tbody) return;
    
    let limMw = 0;
    let limEq = 0;
    let limMass = 0;
    
    const rows = tbody.rows;
    for (let i=0; i<rows.length; i++) {
        const limCb = rows[i].querySelector('.r-lim');
        if (limCb && limCb.checked) {
            limMw = parseFloat(rows[i].querySelector('.r-mw').value) || 0;
            limEq = parseFloat(rows[i].querySelector('.r-eq').value) || 1;
            let massVal = parseFloat(rows[i].querySelector('.r-mass').value) || 0;
            const unit = rows[i].querySelector('.r-mass-unit').value;
            if (unit === 'mg') massVal = massVal / 1000;
            if (unit === 'kg') massVal = massVal * 1000;
            limMass = massVal;
            break;
        }
    }
    
    if (limMw > 0 && pmw > 0) {
        const baseMoles = limMass / limMw / limEq;
        const theoreticalMass = baseMoles * pmw;
        const actualMass = theoreticalMass * (yieldPct / 100);
        if (prodgInput) prodgInput.value = actualMass.toFixed(3);
    } else {
        if (prodgInput) prodgInput.value = '';
    }
}

function collectStepData(side) {
    const steps = [];
    for (let i = 1; i <= counters[side]; i++) {
        const table = document.getElementById(`table-${side}-${i}`);
        if (!table) continue;
        const reagents = Array.from(table.rows).slice(1).map(row => {
            const inputs = row.querySelectorAll('input');
            const pkgsz = parseFloat(inputs[2].value) || 1;
            const pkgpr = parseFloat(inputs[3].value) || 0;
            const massVal = parseFloat(inputs[5].value) || 0;
            const unit = row.querySelector('.r-mass-unit').value;
            return {
                name: inputs[0].value,
                mw: parseFloat(inputs[1].value) || 0,
                pkg_size: pkgsz,
                pkg_price: pkgpr,
                cost_per_g: pkgpr / pkgsz,
                moles: parseFloat(inputs[4].value) || 0,
                mass: massVal,
                mass_unit: unit,
                is_limiting: inputs[6].checked
            };
        });
        const sbotl = parseFloat(document.getElementById(`sbotl-${side}-${i}`).value) || 1;
        const sbotp = parseFloat(document.getElementById(`sbotp-${side}-${i}`).value) || 0;
        const sprc = sbotp / sbotl;
        
        const volVal = parseFloat(document.getElementById(`vol-${side}-${i}`).value) || 0;
        const volUnit = document.getElementById(`volu-${side}-${i}`).value;
        const volL = volUnit === 'mL' ? volVal / 1000 : volVal;
        
        let labLimMoles = 0;
        for (let j=0; j<reagents.length; j++) {
            if (reagents[j].is_limiting && reagents[j].mw > 0) {
                let massInG = reagents[j].mass;
                if (reagents[j].mass_unit === 'mg') massInG = reagents[j].mass / 1000;
                if (reagents[j].mass_unit === 'kg') massInG = reagents[j].mass * 1000;
                labLimMoles = massInG / reagents[j].mw;
                break;
            }
        }
        let molarity = 0.5;
        if (labLimMoles > 0 && volL > 0) {
            molarity = labLimMoles / volL;
        }

        steps.push({
            step_id: i, name: document.getElementById(`name-${side}-${i}`).value,
            product_mw: parseFloat(document.getElementById(`pmw-${side}-${i}`).value) || 0,
            reagents, 
            molarity: molarity,
            solvent_volume: volVal,
            solvent_volume_unit: volUnit,
            solvent_volume_l: volL,
            solvent_name: document.getElementById(`sname-${side}-${i}`).value,
            solvent_density: 0.85, 
            solvent_bottle_l: sbotl,
            solvent_bottle_price: sbotp,
            solvent_price_per_l: sprc,
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
        
        // Also run and display the optimization audit automatically
        await runOptimizationAuditUI();
    } catch (e) { alert("Analysis failed. Is the server running?"); }
}

async function runOptimizationAuditUI() {
    const stepsA = collectStepData('vA');
    const stepsB = collectStepData('vB');
    let html = `<div style="display:flex; gap:15px; flex-wrap:wrap;">`;
    
    if (stepsA.length > 0) {
        const targetA = parseFloat(document.getElementById(`target-vA`).value) || 1.0;
        const resA = await fetch(`${API_BASE}/api/synthesis/audit`, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ steps: stepsA, target_mass_kg: targetA }) });
        if (resA.ok) {
            const dataA = await resA.json();
            html += renderAuditCard('Route A', dataA.audit, 'var(--primary)');
        }
    }
    
    if (stepsB.length > 0) {
        const targetB = parseFloat(document.getElementById(`target-vB`).value) || 1.0;
        const resB = await fetch(`${API_BASE}/api/synthesis/audit`, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ steps: stepsB, target_mass_kg: targetB }) });
        if (resB.ok) {
            const dataB = await resB.json();
            html += renderAuditCard('Route B', dataB.audit, 'var(--secondary)');
        }
    }
    
    html += `</div>`;
    document.getElementById("audit-container").innerHTML = html;
}

function renderAuditCard(title, auditData, color) {
    if (!auditData || auditData.length === 0) return '';
    let html = `<div style="flex:1; min-width:250px; background:#2d3436; padding:15px; border-radius:8px; margin-top:20px; color:white; border-top: 4px solid ${color}; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
        <h4 style="margin-top:0; color:${color}; margin-bottom:5px;">🔬 Yield Sensitivity Audit - ${title}</h4>
        <div style="font-size:0.8em; color:#b2bec3; margin-bottom:15px; font-style:italic;">Cost saved per 1% yield increase</div>
        <table style="width:100%; color:white; font-size:0.85em; text-align:left; border-collapse: collapse;">
        <tr style="border-bottom: 1px solid #636e72;">
            <th style="padding:6px 0;">Step</th>
            <th style="padding:6px 0;">Sensitivity ($/1%)</th>
        </tr>`;
    auditData.forEach(i => { 
        html += `<tr style="border-bottom: 1px solid #454d50;">
            <td style="padding:6px 0;">Step ${i.step_id}</td>
            <td style="padding:6px 0; color:#00cec9; font-weight:bold;">$${(i.sensitivity || 0).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}</td>
        </tr>`; 
    });
    html += `</table></div>`;
    return html;
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



function saveRouteToFile(side) {
    const routeKey = side === 'vA' ? 'routeA' : 'routeB';
    const data = { 
        [routeKey]: { 
            target: document.getElementById(`target-${side}`).value, 
            steps: collectStepData(side) 
        } 
    };
    
    // Get custom filename
    let filename = document.getElementById(`filename-${side}`).value.trim();
    if (!filename) filename = `project_${routeKey}`;
    if (!filename.endsWith('.json')) filename += '.json';
    
    const blob = new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'});
    const a = document.createElement('a'); 
    a.href = URL.createObjectURL(blob); 
    a.download = filename; 
    a.click();
}

function clearRoute(side) { if (confirm(`Clear Route ${side}?`)) clearRouteUI(side); }
function clearRouteUI(side) { document.getElementById(`steps-${side}`).innerHTML = ""; counters[side] = 0; }

// Initialize default filenames on load
document.addEventListener('DOMContentLoaded', () => {
    const d = new Date();
    const yyyymmdd = d.getFullYear() + String(d.getMonth()+1).padStart(2,'0') + String(d.getDate()).padStart(2,'0');
    
    const fnA = document.getElementById('filename-vA');
    if (fnA) fnA.value = `${yyyymmdd}_RouteA`;
    
    const fnB = document.getElementById('filename-vB');
    if (fnB) fnB.value = `${yyyymmdd}_RouteB`;
});
