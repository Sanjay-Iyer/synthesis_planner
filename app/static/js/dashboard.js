/**
 * Dashboard Logic — Synthesis cost analysis, charts, and data management.
 * Migrated from python-polymer/frontend/app.js with updated API paths.
 */

const API_BASE = '';  // Same origin — no need for http://127.0.0.1:8000

let counters = { vA: 0, vB: 0 };
let lastAnalysis = { vA: null, vB: null };
let barInst = null, pieAInst = null, pieBInst = null, efficiencyChartInst = null, stepCostChartInst = null, bottleneckChartInst = null, rComp1Inst = null, rComp2Inst = null, rComp3Inst = null, waterfallChartInst = null, costDriversChartInst = null;

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

            <div id="reagents-container-${side}-${id}" class="reagents-container" style="display: flex; flex-direction: column; gap: 8px; margin-top: 5px;">
                ${data?.reagents ? data.reagents.map(r => {
                    const pkgsz = r.pkg_size || 1;
                    const pkgpr = r.pkg_price || (r.cost_per_g ? r.cost_per_g * pkgsz : 0);
                    const pkgu = r.pkg_unit || 'g';
                    const mass_u = r.mass_unit || 'g';
                    return `<div class="reagent-row" style="display: flex; flex-direction: column; gap: 8px; padding: 12px; background: #fafbfc; border: 1px solid #e1e4e8; border-radius: 6px;">
                        <!-- First Line -->
                        <div style="display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end;">
                            <div style="flex: 2; min-width: 150px; display: flex; flex-direction: column; gap: 4px;">
                                <label style="font-size:0.75em; font-weight:bold; color:var(--text);">Reagent</label>
                                <input type="text" class="r-name" value="${r.name || ''}" style="width:100%;" placeholder="e.g. Aniline">
                            </div>
                            <div style="flex: 1; min-width: 80px; display: flex; flex-direction: column; gap: 4px;">
                                <label style="font-size:0.75em; font-weight:bold; color:var(--text);">MW</label>
                                <input type="number" step="any" class="r-mw" value="${r.mw || ''}" oninput="calcStoich(this)" style="width:100%;" placeholder="MW">
                            </div>
                            <div style="flex: 1; min-width: 80px; display: flex; flex-direction: column; gap: 4px;">
                                <label style="font-size:0.75em; font-weight:bold; color:var(--text);">Equiv</label>
                                <input type="number" step="any" class="r-eq" value="${r.equivalents || ''}" oninput="calcStoich(this)" style="width:100%;" placeholder="Eq">
                            </div>
                            <div style="flex: 1.5; min-width: 120px; display: flex; flex-direction: column; gap: 4px;">
                                <label style="font-size:0.75em; font-weight:bold; color:var(--text);">Mass</label>
                                <div style="display: flex; align-items: center; gap: 4px; width:100%;">
                                    <input type="number" step="any" class="r-mass" value="${r.mass || ''}" oninput="calcStoich(this, true)" style="flex:1; min-width:60px;" placeholder="Mass">
                                    <select class="r-mass-unit" onchange="calcStoich(this)" style="width:50px; font-size:0.8em;"><option value="g">g</option><option value="mg" ${mass_u==='mg'?'selected':''}>mg</option><option value="kg" ${mass_u==='kg'?'selected':''}>kg</option></select>
                                </div>
                            </div>
                            <div style="display: flex; flex-direction: column; gap: 4px; align-items: center; justify-content: center; min-width: 60px;">
                                <label style="font-size:0.75em; font-weight:bold; color:var(--text); text-align: center;">Limiting?</label>
                                <input type="checkbox" class="r-lim" ${r.is_limiting ? 'checked' : ''} onchange="handleLimChange(this)">
                            </div>
                            <div style="display: flex; align-items: center; justify-content: flex-end;">
                                <button onclick="const c=this.closest('.reagents-container'); this.closest('.reagent-row').remove(); calcStoichByContainer(c);" style="background:transparent; border:none; color:#e74c3c; cursor:pointer; font-weight:bold; font-size:1.1em;" title="Delete Reagent">×</button>
                            </div>
                        </div>
                        <!-- Second Line -->
                        <div style="display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; padding-top: 4px; border-top: 1px dashed #e1e4e8;">
                            <div style="flex: 1; min-width: 150px; display: flex; flex-direction: column; gap: 4px;">
                                <label style="font-size:0.75em; font-weight:bold; color:#e74c3c;">Bottle Amount</label>
                                <div style="display: flex; align-items: center; gap: 4px; width:100%;">
                                    <input type="number" step="any" class="r-pkgsz" value="${pkgsz}" style="flex:1; min-width:60px;">
                                    <select class="r-pkgu" onchange="calcStoich(this)" style="width:50px; font-size:0.8em;"><option value="g">g</option><option value="mg" ${pkgu==='mg'?'selected':''}>mg</option><option value="kg" ${pkgu==='kg'?'selected':''}>kg</option></select>
                                </div>
                            </div>
                            <div style="flex: 1; min-width: 150px; display: flex; flex-direction: column; gap: 4px;">
                                <label style="font-size:0.75em; font-weight:bold; color:#e74c3c;">Bottle Cost ($)</label>
                                <input type="number" step="any" class="r-pkgpr" value="${pkgpr}" style="width:100%;" placeholder="Price">
                            </div>
                            <div style="flex: 2; min-width: 150px;"></div>
                        </div>
                    </div>`}).join('') : `<div class="reagent-row" style="display: flex; flex-direction: column; gap: 8px; padding: 12px; background: #fafbfc; border: 1px solid #e1e4e8; border-radius: 6px;">
                        <!-- First Line -->
                        <div style="display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end;">
                            <div style="flex: 2; min-width: 150px; display: flex; flex-direction: column; gap: 4px;">
                                <label style="font-size:0.75em; font-weight:bold; color:var(--text);">Reagent</label>
                                <input type="text" class="r-name" style="width:100%;" placeholder="e.g. Aniline">
                            </div>
                            <div style="flex: 1; min-width: 80px; display: flex; flex-direction: column; gap: 4px;">
                                <label style="font-size:0.75em; font-weight:bold; color:var(--text);">MW</label>
                                <input type="number" step="any" class="r-mw" oninput="calcStoich(this)" style="width:100%;" placeholder="MW">
                            </div>
                            <div style="flex: 1; min-width: 80px; display: flex; flex-direction: column; gap: 4px;">
                                <label style="font-size:0.75em; font-weight:bold; color:var(--text);">Equiv</label>
                                <input type="number" step="any" class="r-eq" oninput="calcStoich(this)" style="width:100%;" placeholder="Eq">
                            </div>
                            <div style="flex: 1.5; min-width: 120px; display: flex; flex-direction: column; gap: 4px;">
                                <label style="font-size:0.75em; font-weight:bold; color:var(--text);">Mass</label>
                                <div style="display: flex; align-items: center; gap: 4px; width:100%;">
                                    <input type="number" step="any" class="r-mass" oninput="calcStoich(this, true)" style="flex:1; min-width:60px;" placeholder="Mass">
                                    <select class="r-mass-unit" onchange="calcStoich(this)" style="width:50px; font-size:0.8em;"><option value="g">g</option><option value="mg">mg</option><option value="kg">kg</option></select>
                                </div>
                            </div>
                            <div style="display: flex; flex-direction: column; gap: 4px; align-items: center; justify-content: center; min-width: 60px;">
                                <label style="font-size:0.75em; font-weight:bold; color:var(--text); text-align: center;">Limiting?</label>
                                <input type="checkbox" class="r-lim" onchange="handleLimChange(this)">
                            </div>
                            <div style="display: flex; align-items: center; justify-content: flex-end;">
                                <button onclick="const c=this.closest('.reagents-container'); this.closest('.reagent-row').remove(); calcStoichByContainer(c);" style="background:transparent; border:none; color:#e74c3c; cursor:pointer; font-weight:bold; font-size:1.1em;" title="Delete Reagent">×</button>
                            </div>
                        </div>
                        <!-- Second Line -->
                        <div style="display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; padding-top: 4px; border-top: 1px dashed #e1e4e8;">
                            <div style="flex: 1; min-width: 150px; display: flex; flex-direction: column; gap: 4px;">
                                <label style="font-size:0.75em; font-weight:bold; color:#e74c3c;">Bottle Amount</label>
                                <div style="display: flex; align-items: center; gap: 4px; width:100%;">
                                    <input type="number" step="any" class="r-pkgsz" style="flex:1; min-width:60px;">
                                    <select class="r-pkgu" onchange="calcStoich(this)" style="width:50px; font-size:0.8em;"><option value="g">g</option><option value="mg">mg</option><option value="kg">kg</option></select>
                                </div>
                            </div>
                            <div style="flex: 1; min-width: 150px; display: flex; flex-direction: column; gap: 4px;">
                                <label style="font-size:0.75em; font-weight:bold; color:#e74c3c;">Bottle Cost ($)</label>
                                <input type="number" step="any" class="r-pkgpr" style="width:100%;" placeholder="Price">
                            </div>
                            <div style="flex: 2; min-width: 150px;"></div>
                        </div>
                    </div>`}
            </div>
            <div style="display:flex; gap:10px; margin-top:5px; align-items:center;">
                <button class="btn btn-ghost btn-sm" onclick="addReagentRow('${side}', ${id})">+ Manual Reagent</button>
                <div style="flex:1; display:flex; gap:5px;">
                    <input type="text" id="smiles-${side}-${id}" placeholder="Paste SMILES, SELFIES, or InChI..." style="flex:1; font-size:0.8em; padding:4px; border:1px solid var(--border); border-radius:3px;">
                    <button class="btn btn-primary btn-sm" onclick="addReagentFromSmiles('${side}', ${id})">+ Add Molecule</button>
                </div>
            </div>
            <div id="smiles-display-${side}-${id}" style="font-size:0.75em; color:var(--text); margin-top:5px; padding:5px; background:#eef2f3; border:1px solid var(--border); border-radius:4px; display:none;"></div>
            
            <div style="display: flex; flex-direction: column; gap: 8px; margin-top: 10px; background: #f1f2f6; padding: 12px; border: 1px solid #e1e4e8; border-radius: 6px;">
                <!-- First Line: Solvent & Volume -->
                <div style="display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end;">
                    <div style="flex: 2; min-width: 150px; display: flex; flex-direction: column; gap: 4px;">
                        <label style="font-size:0.75em; font-weight:bold; color:var(--text);">Solvent</label>
                        <input type="text" id="sname-${side}-${id}" value="${data?.solvent_name || 'Solvent'}" style="width:100%; font-weight:normal;">
                    </div>
                    <div style="flex: 1; min-width: 150px; display: flex; flex-direction: column; gap: 4px;">
                        <label style="font-size:0.75em; font-weight:bold; color:var(--text);">Volume</label>
                        <div style="display: flex; align-items: center; gap: 4px; width:100%;">
                            <input type="number" id="vol-${side}-${id}" value="${data?.solvent_volume_l || ''}" step="any" style="flex:1; min-width:60px; font-weight:normal;">
                            <select id="volu-${side}-${id}" onchange="calcProductProduced(this)" style="width:50px; font-size:0.8em;"><option value="L" ${data?.solvent_volume_unit==='L'?'selected':''}>L</option><option value="mL" ${data?.solvent_volume_unit==='mL'?'selected':''}>mL</option></select>
                        </div>
                    </div>
                    <div style="flex: 1; min-width: 80px;"></div>
                </div>
                <!-- Second Line: Bottle Info -->
                <div style="display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; padding-top: 8px; border-top: 1px dashed #e1e4e8;">
                    <div style="flex: 1; min-width: 150px; display: flex; flex-direction: column; gap: 4px;">
                        <label style="font-size:0.75em; font-weight:bold; color:#e74c3c;">Bottle Amount</label>
                        <div style="display: flex; align-items: center; gap: 4px; width:100%;">
                            <input type="number" id="sbotl-${side}-${id}" value="${data?.solvent_bottle_amount || data?.solvent_bottle_l || 1}" step="any" style="flex:1; min-width:60px; font-weight:normal; color:var(--text);">
                            <select id="sbotlu-${side}-${id}" style="width:50px; font-size:0.8em;"><option value="L" ${data?.solvent_bottle_unit==='L'?'selected':''}>L</option><option value="mL" ${data?.solvent_bottle_unit==='mL'?'selected':''}>mL</option></select>
                        </div>
                    </div>
                    <div style="flex: 1; min-width: 150px; display: flex; flex-direction: column; gap: 4px;">
                        <label style="font-size:0.75em; font-weight:bold; color:#e74c3c;">Bottle Cost ($)</label>
                        <input type="number" id="sbotp-${side}-${id}" value="${data?.solvent_bottle_price || (data?.solvent_price_per_l ? data?.solvent_price_per_l * (data?.solvent_bottle_l || 1) : 0)}" step="any" style="width:100%; font-weight:normal; color:var(--text);">
                    </div>
                    <div style="flex: 1; min-width: 150px;"></div>
                </div>
            </div>
            <div style="display:flex; gap:5px; margin-top:5px; align-items:center;">
                <input type="text" id="solvent-smiles-${side}-${id}" placeholder="Paste SMILES, SELFIES, or InChI for solvent..." style="flex:1; font-size:0.8em; padding:4px; border:1px solid var(--border); border-radius:3px;">
                <button class="btn btn-primary btn-sm" onclick="lookupSolventFromSmiles('${side}', ${id})">🔍 Lookup Solvent</button>
            </div>
            
            <div style="display: flex; flex-wrap: wrap; gap: 10px; margin-top:10px; background:#e8f4f8; padding:8px; border-radius:5px; align-items:center;">
                <label style="font-size:0.7em; font-weight:bold;">Final Product</label>
                <label style="font-size:0.7em;">Yield %: <input type="number" id="yield-${side}-${id}" value="${data?.yield_percent || 100}" step="any" style="width:60px;" oninput="calcProductProduced(this)"></label>
                <label style="font-size:0.7em;">Produced (g): <input type="number" id="prodg-${side}-${id}" value="" step="any" style="width:70px;" readonly disabled></label>
                <button class="btn btn-ghost btn-sm" onclick="matchProducedGrams('${side}', '${side==='vA'?'vB':'vA'}')" style="padding:2px 6px; font-size:0.7em; background:var(--primary); color:#fff; border-radius:3px; border:none;">Match Route ${side==='vA'?'B':'A'}</button>
            </div>
            <textarea id="proc-${side}-${id}" style="margin-top:10px; height:70px; width:100%; font-size:0.8em;" placeholder="Procedure Notes..."></textarea>
        </div>`;
    
    container.insertAdjacentHTML('beforeend', html);
    if (data?.procedure) { document.getElementById(`proc-${side}-${id}`).value = data.procedure; }
    
    if (data) {
        setTimeout(() => {
            const container = document.getElementById(`reagents-container-${side}-${id}`);
            if (container) calcStoichByContainer(container);
        }, 50);
    }
}

function addReagentRow(side, stepId) {
    const container = document.getElementById(`reagents-container-${side}-${stepId}`);
    if (!container) return;
    const div = document.createElement('div');
    div.className = 'reagent-row';
    div.style.cssText = 'display: flex; flex-direction: column; gap: 8px; padding: 12px; background: #fafbfc; border: 1px solid #e1e4e8; border-radius: 6px;';
    div.innerHTML = `
        <!-- First Line -->
        <div style="display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end;">
            <div style="flex: 2; min-width: 150px; display: flex; flex-direction: column; gap: 4px;">
                <label style="font-size:0.75em; font-weight:bold; color:var(--text);">Reagent</label>
                <input type="text" class="r-name" style="width:100%;" placeholder="e.g. Aniline">
            </div>
            <div style="flex: 1; min-width: 80px; display: flex; flex-direction: column; gap: 4px;">
                <label style="font-size:0.75em; font-weight:bold; color:var(--text);">MW</label>
                <input type="number" step="any" class="r-mw" oninput="calcStoich(this)" style="width:100%;" placeholder="MW">
            </div>
            <div style="flex: 1; min-width: 80px; display: flex; flex-direction: column; gap: 4px;">
                <label style="font-size:0.75em; font-weight:bold; color:var(--text);">Equiv</label>
                <input type="number" step="any" class="r-eq" oninput="calcStoich(this)" style="width:100%;" placeholder="Eq">
            </div>
            <div style="flex: 1.5; min-width: 120px; display: flex; flex-direction: column; gap: 4px;">
                <label style="font-size:0.75em; font-weight:bold; color:var(--text);">Mass</label>
                <div style="display: flex; align-items: center; gap: 4px; width:100%;">
                    <input type="number" step="any" class="r-mass" oninput="calcStoich(this, true)" style="flex:1; min-width:60px;" placeholder="Mass">
                    <select class="r-mass-unit" onchange="calcStoich(this)" style="width:50px; font-size:0.8em;"><option value="g">g</option><option value="mg">mg</option><option value="kg">kg</option></select>
                </div>
            </div>
            <div style="display: flex; flex-direction: column; gap: 4px; align-items: center; justify-content: center; min-width: 60px;">
                <label style="font-size:0.75em; font-weight:bold; color:var(--text); text-align: center;">Limiting?</label>
                <input type="checkbox" class="r-lim" onchange="handleLimChange(this)">
            </div>
            <div style="display: flex; align-items: center; justify-content: flex-end;">
                <button onclick="const c=this.closest('.reagents-container'); this.closest('.reagent-row').remove(); calcStoichByContainer(c);" style="background:transparent; border:none; color:#e74c3c; cursor:pointer; font-weight:bold; font-size:1.1em;" title="Delete Reagent">×</button>
            </div>
        </div>
        <!-- Second Line -->
        <div style="display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; padding-top: 4px; border-top: 1px dashed #e1e4e8;">
            <div style="flex: 1; min-width: 150px; display: flex; flex-direction: column; gap: 4px;">
                <label style="font-size:0.75em; font-weight:bold; color:#e74c3c;">Bottle Amount</label>
                <div style="display: flex; align-items: center; gap: 4px; width:100%;">
                    <input type="number" step="any" class="r-pkgsz" style="flex:1; min-width:60px;">
                    <select class="r-pkgu" onchange="calcStoich(this)" style="width:50px; font-size:0.8em;"><option value="g">g</option><option value="mg">mg</option><option value="kg">kg</option></select>
                </div>
            </div>
            <div style="flex: 1; min-width: 150px; display: flex; flex-direction: column; gap: 4px;">
                <label style="font-size:0.75em; font-weight:bold; color:#e74c3c;">Bottle Cost ($)</label>
                <input type="number" step="any" class="r-pkgpr" style="width:100%;" placeholder="Price">
            </div>
            <div style="flex: 2; min-width: 150px;"></div>
        </div>`;
    container.appendChild(div);
}

async function addReagentFromSmiles(side, stepId) {
    const inputEl = document.getElementById(`smiles-${side}-${stepId}`);
    const val = inputEl.value.trim();
    if (!val) return;
    
    const container = document.getElementById(`reagents-container-${side}-${stepId}`);
    if (!container) return;
    
    let targetRow = null;
    const rows = container.querySelectorAll('.reagent-row');
    if (rows.length === 1) {
        const firstRowInputs = rows[0].querySelectorAll('input[type="text"], input[type="number"]');
        let isEmpty = true;
        firstRowInputs.forEach(i => { if(i.value) isEmpty = false; });
        if (isEmpty) targetRow = rows[0];
    }
    
    if (!targetRow) {
        targetRow = document.createElement('div');
        targetRow.className = 'reagent-row';
        targetRow.style.cssText = 'display: flex; flex-direction: column; gap: 8px; padding: 12px; background: #fafbfc; border: 1px solid #e1e4e8; border-radius: 6px;';
        targetRow.innerHTML = `
            <!-- First Line -->
            <div style="display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end;">
                <div style="flex: 2; min-width: 150px; display: flex; flex-direction: column; gap: 4px;">
                    <label style="font-size:0.75em; font-weight:bold; color:var(--text);">Reagent</label>
                    <input type="text" class="r-name" style="width:100%;" placeholder="e.g. Aniline">
                </div>
                <div style="flex: 1; min-width: 80px; display: flex; flex-direction: column; gap: 4px;">
                    <label style="font-size:0.75em; font-weight:bold; color:var(--text);">MW</label>
                    <input type="number" step="any" class="r-mw" oninput="calcStoich(this)" style="width:100%;" placeholder="MW">
                </div>
                <div style="flex: 1; min-width: 80px; display: flex; flex-direction: column; gap: 4px;">
                    <label style="font-size:0.75em; font-weight:bold; color:var(--text);">Equiv</label>
                    <input type="number" step="any" class="r-eq" oninput="calcStoich(this)" style="width:100%;" placeholder="Eq">
                </div>
                <div style="flex: 1.5; min-width: 120px; display: flex; flex-direction: column; gap: 4px;">
                    <label style="font-size:0.75em; font-weight:bold; color:var(--text);">Mass</label>
                    <div style="display: flex; align-items: center; gap: 4px; width:100%;">
                        <input type="number" step="any" class="r-mass" oninput="calcStoich(this, true)" style="flex:1; min-width:60px;" placeholder="Mass">
                        <select class="r-mass-unit" onchange="calcStoich(this)" style="width:50px; font-size:0.8em;"><option value="g">g</option><option value="mg">mg</option><option value="kg">kg</option></select>
                    </div>
                </div>
                <div style="display: flex; flex-direction: column; gap: 4px; align-items: center; justify-content: center; min-width: 60px;">
                    <label style="font-size:0.75em; font-weight:bold; color:var(--text); text-align: center;">Limiting?</label>
                    <input type="checkbox" class="r-lim" onchange="handleLimChange(this)">
                </div>
                <div style="display: flex; align-items: center; justify-content: flex-end;">
                    <button onclick="const c=this.closest('.reagents-container'); this.closest('.reagent-row').remove(); calcStoichByContainer(c);" style="background:transparent; border:none; color:#e74c3c; cursor:pointer; font-weight:bold; font-size:1.1em;" title="Delete Reagent">×</button>
                </div>
            </div>
            <!-- Second Line -->
            <div style="display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; padding-top: 4px; border-top: 1px dashed #e1e4e8;">
                <div style="flex: 1; min-width: 150px; display: flex; flex-direction: column; gap: 4px;">
                    <label style="font-size:0.75em; font-weight:bold; color:#e74c3c;">Bottle Amount</label>
                    <div style="display: flex; align-items: center; gap: 4px; width:100%;">
                        <input type="number" step="any" class="r-pkgsz" style="flex:1; min-width:60px;">
                        <select class="r-pkgu" onchange="calcStoich(this)" style="width:50px; font-size:0.8em;"><option value="g">g</option><option value="mg">mg</option><option value="kg">kg</option></select>
                    </div>
                </div>
                <div style="flex: 1; min-width: 150px; display: flex; flex-direction: column; gap: 4px;">
                    <label style="font-size:0.75em; font-weight:bold; color:#e74c3c;">Bottle Cost ($)</label>
                    <input type="number" step="any" class="r-pkgpr" style="width:100%;" placeholder="Price">
                </div>
                <div style="flex: 2; min-width: 150px;"></div>
            </div>`;
        container.appendChild(targetRow);
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
        
        const displayDiv = document.getElementById(`smiles-display-${side}-${stepId}`);
        if (displayDiv) {
            displayDiv.style.display = "block";
            displayDiv.innerHTML += `<div style="margin-bottom:2px;"><b>${name}:</b> <code>${val}</code></div>`;
        }
        
        inputEl.value = ""; 
        
    } catch (err) {
        inputs[0].value = "Error";
    }
}

async function lookupSolventFromSmiles(side, stepId) {
    const inputEl = document.getElementById(`solvent-smiles-${side}-${stepId}`);
    const val = inputEl.value.trim();
    if (!val) return;

    const nameField = document.getElementById(`sname-${side}-${stepId}`);
    if (nameField) nameField.value = "Fetching...";

    try {
        const res = await fetch('/api/synthesis/molecule-name', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ string_input: val })
        });
        if (res.ok) {
            const data = await res.json();
            if (nameField) nameField.value = data.name || "Unknown";
        } else {
            if (nameField) nameField.value = "Not Found";
        }
        inputEl.value = "";
    } catch (err) {
        if (nameField) nameField.value = "Error";
    }
}

function handleLimChange(cb) {
    if (cb.checked) {
        const container = cb.closest('.reagents-container');
        if (container) {
            const cbs = container.querySelectorAll('.r-lim');
            cbs.forEach(c => { if(c !== cb) c.checked = false; });
        }
    }
    const container = cb.closest('.reagents-container');
    if (container) calcStoichByContainer(container);
}

function calcStoich(el, isMass = false) {
    const container = el.closest('.reagents-container');
    if (container) calcStoichByContainer(container, isMass ? el : null);
}

function calcStoichByContainer(container, changedMassInput = null) {
    if (!container) return;
    const rows = container.querySelectorAll('.reagent-row');
    let baseMoles = 0;
    
    if (changedMassInput) {
        const mw = parseFloat(changedMassInput.closest('.reagent-row').querySelector('.r-mw').value) || 0;
        const eq = parseFloat(changedMassInput.closest('.reagent-row').querySelector('.r-eq').value) || 1;
        const mass = parseFloat(changedMassInput.value) || 0;
        const unit = changedMassInput.closest('.reagent-row').querySelector('.r-mass-unit').value;
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
    
    const card = container.closest('.step-card');
    if (card) {
        const pmwInput = card.querySelector('input[id^="pmw-"]');
        if (pmwInput) calcProductProduced(pmwInput);
    }
}

const calcStoichByTbody = calcStoichByContainer;

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
    
    const container = card.querySelector('.reagents-container');
    if (!container) return;
    
    let limMw = 0;
    let limEq = 0;
    let limMass = 0;
    
    const rows = container.querySelectorAll('.reagent-row');
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
        const container = document.getElementById(`reagents-container-${side}-${i}`);
        if (!container) continue;
        const reagents = Array.from(container.querySelectorAll('.reagent-row')).map(row => {
            const name = row.querySelector('.r-name')?.value || '';
            const mw = parseFloat(row.querySelector('.r-mw')?.value) || 0;
            const pkgsz = parseFloat(row.querySelector('.r-pkgsz')?.value) || 1;
            const pkgpr = parseFloat(row.querySelector('.r-pkgpr')?.value) || 0;
            const pkgu = row.querySelector('.r-pkgu')?.value || 'g';
            let pkgSizeInG = pkgsz;
            if (pkgu === 'mg') pkgSizeInG = pkgsz / 1000;
            if (pkgu === 'kg') pkgSizeInG = pkgsz * 1000;
            const cost_per_g = pkgSizeInG > 0 ? pkgpr / pkgSizeInG : 0;
            const equivalents = parseFloat(row.querySelector('.r-eq')?.value) || 0;
            const massVal = parseFloat(row.querySelector('.r-mass')?.value) || 0;
            const unit = row.querySelector('.r-mass-unit')?.value || 'g';
            const is_limiting = row.querySelector('.r-lim')?.checked || false;
            return {
                name: name,
                mw: mw,
                pkg_size: pkgsz,
                pkg_price: pkgpr,
                pkg_unit: pkgu,
                cost_per_g: cost_per_g,
                equivalents: equivalents,
                mass: massVal,
                mass_unit: unit,
                is_limiting: is_limiting
            };
        });
        const sbotlVal = parseFloat(document.getElementById(`sbotl-${side}-${i}`).value) || 1;
        const sbotlUnit = document.getElementById(`sbotlu-${side}-${i}`).value;
        const sbotl = sbotlUnit === 'mL' ? sbotlVal / 1000 : sbotlVal;
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
            solvent_bottle_amount: sbotlVal,
            solvent_bottle_unit: sbotlUnit,
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

        // Unlock the "Add to Database" button now that we have fresh results
        setDatabaseButtonEnabled(true);
    } catch (e) {
        setDatabaseButtonEnabled(false);
        alert("Analysis failed. Is the server running?");
    }
}

async function runOptimizationAuditUI() {
    const stepsA = collectStepData('vA');
    const stepsB = collectStepData('vB');
    let html = `<h2 style="color:white; margin-top:30px; border-bottom:2px solid #555; padding-bottom:5px;">🔬 Section 2: Yield Sensitivity Audit</h2>`;
    html += `<div style="display:flex; gap:15px; flex-wrap:wrap; margin-top:15px;">`;
    
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
    const pA = getPieData(a), pB = getPieData(b);
    const labStepsA = collectStepData('vA');
    const labStepsB = collectStepData('vB');

    let html = `<h2 style="color:white; margin-top:20px; border-bottom:2px solid #555; padding-bottom:5px;">📋 Section 1: Route Procurement (Side-by-Side)</h2>`;
    html += `<div style="display:flex; gap:20px; flex-wrap:wrap; margin-bottom: 25px; margin-top:15px;">`;

    // Route A column
    html += `<div style="flex:1; min-width:350px; background:#2d3436; padding:15px; border-radius:8px; color:white; border-top:4px solid var(--primary);">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; margin-bottom:10px;">
            <h3 style="color:var(--primary); margin:0;">📋 Route A Analysis</h3>
            <div style="display:flex; gap:5px; align-items:center; background:rgba(255,255,255,0.05); padding:4px 8px; border-radius:4px;">
                <span style="font-size:0.75em; color:#b2bec3;">Scale:</span>
                <input type="number" id="scale-mult-vA" value="2" min="1" step="any" style="width:50px; font-size:0.8em; padding:2px; background:#1e272c; color:white; border:1px solid #555; border-radius:3px;">
                <button class="btn btn-primary" onclick="addScaledSection('vA')" style="padding:2px 8px; font-size:0.75em;">Scale Up</button>
            </div>
        </div>
        <div id="original-steps-vA">`;

    if (labStepsA.length > 0) {
        labStepsA.forEach(s => {
            let stepTotal = 0;
            let limMw = 0, limEq = 1, limMassInG = 0;
            s.reagents.forEach(r => {
                let inG = r.mass;
                if (r.mass_unit === 'mg') inG = r.mass / 1000;
                if (r.mass_unit === 'kg') inG = r.mass * 1000;
                const cost = inG * (r.cost_per_g || 0);
                r.lab_cost = cost;
                r.lab_mass_in_g = inG;
                stepTotal += cost;

                if (r.is_limiting && r.mw > 0) {
                    limMw = r.mw;
                    limEq = r.equivalents || 1;
                    limMassInG = inG;
                }
            });
            // solvent cost
            if (s.solvent_bottle_l > 0) {
                const sCost = s.solvent_volume_l * (s.solvent_bottle_price / s.solvent_bottle_l);
                stepTotal += sCost;
            }

            let productProduced = 0;
            if (limMw > 0 && s.product_mw > 0) {
                const baseMoles = limMassInG / limMw / limEq;
                productProduced = baseMoles * s.product_mw * (s.yield_percent / 100);
            }

            html += `<div style="margin-top:15px; border-top:1px solid #555; padding-top:8px;">
                <div style="display:flex; justify-content:space-between; font-size:0.85em; margin-bottom:5px;">
                    <span style="color:#00cec9;">S${s.step_id}: ${s.name}</span>
                    <span>Subtotal: $${stepTotal.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}</span>
                </div>
                <div style="display:flex; justify-content:space-between; font-size:0.8em; margin-bottom:5px; color:#ffeaa7;">
                    <span>Product Yield: ${s.yield_percent}%</span>
                    <span>Amt Produced: ${productProduced.toLocaleString(undefined, {minimumFractionDigits:3, maximumFractionDigits:3})} g</span>
                </div>
                <div style="font-size:0.75em; background:rgba(255,255,255,0.05); padding:8px; margin:5px 0; white-space: pre-wrap; border:1px solid #555;">${s.procedure || 'No notes.'}</div>
                <table style="width:100%; font-size:0.7em; color:#dfe6e9; border-collapse:collapse; margin-top:4px;">
                    <tr style="border-bottom:1px solid #555;"><th style="text-align:left; padding:4px 0;">Reagent</th><th style="text-align:left;">Amount Used</th><th style="text-align:left;">Cost</th></tr>`;
            s.reagents.forEach(r => {
                html += `<tr style="border-bottom:1px solid #444;"><td style="padding:4px 0;">${r.name}</td><td>${r.mass} ${r.mass_unit}</td><td>$${(r.lab_cost || 0).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}</td></tr>`;
            });
            if (s.solvent_volume > 0) {
                const sCost = s.solvent_volume_l * (s.solvent_bottle_price / s.solvent_bottle_l);
                html += `<tr style="border-bottom:1px solid #444;"><td style="padding:4px 0; color:#00cec9;">${s.solvent_name} (Solvent)</td><td>${s.solvent_volume} ${s.solvent_volume_unit}</td><td>$${sCost.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}</td></tr>`;
            }
            html += `</table></div>`;
        });
    } else {
        html += `<p style="font-size:0.85em; color:#b2bec3;">No steps found.</p>`;
    }
    html += `</div>`; // end original-steps-vA
    html += `<div id="scaled-sections-vA"></div>`;
    html += `</div>`; // end Route A column

    // Route B column
    html += `<div style="flex:1; min-width:350px; background:#2d3436; padding:15px; border-radius:8px; color:white; border-top:4px solid var(--secondary);">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; margin-bottom:10px;">
            <h3 style="color:var(--secondary); margin:0;">📋 Route B Analysis</h3>
            <div style="display:flex; gap:5px; align-items:center; background:rgba(255,255,255,0.05); padding:4px 8px; border-radius:4px;">
                <span style="font-size:0.75em; color:#b2bec3;">Scale:</span>
                <input type="number" id="scale-mult-vB" value="2" min="1" step="any" style="width:50px; font-size:0.8em; padding:2px; background:#1e272c; color:white; border:1px solid #555; border-radius:3px;">
                <button class="btn btn-secondary" onclick="addScaledSection('vB')" style="padding:2px 8px; font-size:0.75em;">Scale Up</button>
            </div>
        </div>
        <div id="original-steps-vB">`;

    if (labStepsB.length > 0) {
        labStepsB.forEach(s => {
            let stepTotal = 0;
            let limMw = 0, limEq = 1, limMassInG = 0;
            s.reagents.forEach(r => {
                let inG = r.mass;
                if (r.mass_unit === 'mg') inG = r.mass / 1000;
                if (r.mass_unit === 'kg') inG = r.mass * 1000;
                const cost = inG * (r.cost_per_g || 0);
                r.lab_cost = cost;
                r.lab_mass_in_g = inG;
                stepTotal += cost;

                if (r.is_limiting && r.mw > 0) {
                    limMw = r.mw;
                    limEq = r.equivalents || 1;
                    limMassInG = inG;
                }
            });
            // solvent cost
            if (s.solvent_bottle_l > 0) {
                const sCost = s.solvent_volume_l * (s.solvent_bottle_price / s.solvent_bottle_l);
                stepTotal += sCost;
            }

            let productProduced = 0;
            if (limMw > 0 && s.product_mw > 0) {
                const baseMoles = limMassInG / limMw / limEq;
                productProduced = baseMoles * s.product_mw * (s.yield_percent / 100);
            }

            html += `<div style="margin-top:15px; border-top:1px solid #555; padding-top:8px;">
                <div style="display:flex; justify-content:space-between; font-size:0.85em; margin-bottom:5px;">
                    <span style="color:#00cec9;">S${s.step_id}: ${s.name}</span>
                    <span>Subtotal: $${stepTotal.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}</span>
                </div>
                <div style="display:flex; justify-content:space-between; font-size:0.8em; margin-bottom:5px; color:#ffeaa7;">
                    <span>Product Yield: ${s.yield_percent}%</span>
                    <span>Amt Produced: ${productProduced.toLocaleString(undefined, {minimumFractionDigits:3, maximumFractionDigits:3})} g</span>
                </div>
                <div style="font-size:0.75em; background:rgba(255,255,255,0.05); padding:8px; margin:5px 0; white-space: pre-wrap; border:1px solid #555;">${s.procedure || 'No notes.'}</div>
                <table style="width:100%; font-size:0.7em; color:#dfe6e9; border-collapse:collapse; margin-top:4px;">
                    <tr style="border-bottom:1px solid #555;"><th style="text-align:left; padding:4px 0;">Reagent</th><th style="text-align:left;">Amount Used</th><th style="text-align:left;">Cost</th></tr>`;
            s.reagents.forEach(r => {
                html += `<tr style="border-bottom:1px solid #444;"><td style="padding:4px 0;">${r.name}</td><td>${r.mass} ${r.mass_unit}</td><td>$${(r.lab_cost || 0).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}</td></tr>`;
            });
            if (s.solvent_volume > 0) {
                const sCost = s.solvent_volume_l * (s.solvent_bottle_price / s.solvent_bottle_l);
                html += `<tr style="border-bottom:1px solid #444;"><td style="padding:4px 0; color:#00cec9;">${s.solvent_name} (Solvent)</td><td>${s.solvent_volume} ${s.solvent_volume_unit}</td><td>$${sCost.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}</td></tr>`;
            }
            html += `</table></div>`;
        });
    } else {
        html += `<p style="font-size:0.85em; color:#b2bec3;">No steps found.</p>`;
    }
    html += `</div>`; // end original-steps-vB
    html += `<div id="scaled-sections-vB"></div>`;
    html += `</div>`;

    html += `</div>`; // end flex row

    // Placeholder for Section 2 to be populated automatically
    html += `<div id="audit-container"></div>`;

    // Synthesis Summary at the bottom
    html += `<h2 style="color:white; margin-top:30px; border-bottom:2px solid #555; padding-bottom:5px;">📊 Section 3: Comprehensive Comparison Summary</h2>`;
    html += `<div style="margin-top:15px; background:#2d3436; padding:15px; border-radius:8px; color:white; border-left:4px solid #00cec9;">
        <h3 style="margin-top:0; color:#00cec9;">📊 Comprehensive Comparison Summary</h3>
        <table style="color:white; width:100%; border-collapse:collapse; margin-top:10px; font-size:0.9em; text-align:left;">
            <tr style="border-bottom:1px solid #555;"><th style="padding:6px 0;">Metric</th><th style="color:var(--primary);">Route A</th><th style="color:var(--secondary);">Route B</th></tr>
            <tr style="border-bottom:1px solid #444;"><td style="padding:6px 0;">Target Goal</td><td>${document.getElementById('target-vA')?.value || 1} kg</td><td>${document.getElementById('target-vB')?.value || 1} kg</td></tr>
            <tr style="border-bottom:1px solid #444;"><td style="padding:6px 0;">Budget / Total Cost</td><td>$${(a.total_cost || 0).toLocaleString()}</td><td>$${(b.total_cost || 0).toLocaleString()}</td></tr>
            <tr style="border-bottom:1px solid #444;"><td style="padding:6px 0;">Cost per kg</td><td>$${(a.cost_per_kg || 0).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}</td><td>$${(b.cost_per_kg || 0).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}</td></tr>
            <tr style="border-bottom:1px solid #444; color:#00cec9;"><td style="padding:6px 0;">E-Factor</td><td>${a.e_factor || 0}</td><td>${b.e_factor || 0}</td></tr>
        </table>
    </div>`;

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

async function updateCharts(a, b, pA, pB) {
    // 1. Efficiency Chart (Dual Y-Axis)
    if (efficiencyChartInst) efficiencyChartInst.destroy();
    const effCanvas = document.getElementById('efficiencyChart');
    if (effCanvas) {
        efficiencyChartInst = new Chart(effCanvas, {
            type: 'bar',
            data: {
                labels: ['Route A', 'Route B'],
                datasets: [
                    {
                        label: 'Total Cost ($)',
                        data: [a.total_cost || 0, b.total_cost || 0],
                        backgroundColor: '#0984e3',
                        yAxisID: 'y'
                    },
                    {
                        label: 'E-Factor',
                        data: [a.e_factor || 0, b.e_factor || 0],
                        backgroundColor: '#e17055',
                        yAxisID: 'y1'
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        title: { display: true, text: 'Cost ($)', color: '#fff' },
                        ticks: { color: '#fff' },
                        grid: { color: 'rgba(255,255,255,0.1)' }
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        title: { display: true, text: 'E-Factor', color: '#fff' },
                        ticks: { color: '#fff' },
                        grid: { drawOnChartArea: false }
                    },
                    x: {
                        ticks: { color: '#fff' },
                        grid: { color: 'rgba(255,255,255,0.1)' }
                    }
                },
                plugins: {
                    legend: {
                        labels: { color: '#fff' }
                    }
                }
            }
        });
    }

    // 2. Step-wise Cost Breakdown stacked chart
    if (stepCostChartInst) stepCostChartInst.destroy();
    const scCanvas = document.getElementById('stepCostChart');
    if (scCanvas) {
        const datasets = [];
        const maxSteps = Math.max(a.steps ? a.steps.length : 0, b.steps ? b.steps.length : 0);
        const colors = ['#0984e3', '#00cec9', '#6c5ce7', '#fab1a0', '#fdcb6e', '#e17055', '#2ecc71'];

        for (let i = 0; i < maxSteps; i++) {
            const stepA = a.steps && a.steps[i] ? a.steps[i] : null;
            const stepB = b.steps && b.steps[i] ? b.steps[i] : null;

            let domA = '', domB = '';
            if (stepA && stepA.reagents) {
                let maxCost = 0;
                stepA.reagents.forEach(r => {
                    if (r.item_cost > maxCost) {
                        maxCost = r.item_cost;
                        domA = r.name;
                    }
                });
            }
            if (stepB && stepB.reagents) {
                let maxCost = 0;
                stepB.reagents.forEach(r => {
                    if (r.item_cost > maxCost) {
                        maxCost = r.item_cost;
                        domB = r.name;
                    }
                });
            }

            let lbl = stepA?.name || stepB?.name || `Step ${i + 1}`;
            let dom = domA || domB;
            if (dom) lbl += ` (${dom})`;

            datasets.push({
                label: lbl,
                data: [stepA?.step_total || 0, stepB?.step_total || 0],
                backgroundColor: colors[i % colors.length]
            });
        }

        stepCostChartInst = new Chart(scCanvas, {
            type: 'bar',
            data: {
                labels: ['Route A', 'Route B'],
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                layout: {
                    padding: {
                        right: 35,
                        left: 15
                    }
                },
                scales: {
                    x: {
                        stacked: true,
                        ticks: { color: '#fff' },
                        grid: { color: 'rgba(255,255,255,0.1)' }
                    },
                    y: {
                        stacked: true,
                        ticks: { color: '#fff' },
                        grid: { color: 'rgba(255,255,255,0.1)' }
                    }
                },
                plugins: {
                    legend: {
                        labels: { color: '#fff' }
                    }
                }
            }
        });
    }

    // 3. Optimization Bottleneck chart (Tornado Plot)
    const stepsA = collectStepData('vA');
    const stepsB = collectStepData('vB');
    let auditData = [];

    if (stepsA.length > 0) {
        const targetA = parseFloat(document.getElementById(`target-vA`).value) || 1.0;
        const resA = await fetch(`${API_BASE}/api/synthesis/audit`, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ steps: stepsA, target_mass_kg: targetA }) });
        if (resA.ok) {
            const dataA = await resA.json();
            if (dataA.audit) {
                dataA.audit.forEach(i => {
                    auditData.push({ label: [`Route A - Step ${i.step_id}`, i.name], value: i.sensitivity || 0, color: '#0984e3' });
                });
            }
        }
    }
    if (stepsB.length > 0) {
        const targetB = parseFloat(document.getElementById(`target-vB`).value) || 1.0;
        const resB = await fetch(`${API_BASE}/api/synthesis/audit`, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ steps: stepsB, target_mass_kg: targetB }) });
        if (resB.ok) {
            const dataB = await resB.json();
            if (dataB.audit) {
                dataB.audit.forEach(i => {
                    auditData.push({ label: [`Route B - Step ${i.step_id}`, i.name], value: i.sensitivity || 0, color: '#27ae60' });
                });
            }
        }
    }

    auditData.sort((x, y) => y.value - x.value);

    if (bottleneckChartInst) bottleneckChartInst.destroy();
    const bnCanvas = document.getElementById('bottleneckChart');
    if (bnCanvas && auditData.length > 0) {
        bottleneckChartInst = new Chart(bnCanvas, {
            type: 'bar',
            data: {
                labels: auditData.map(i => i.label),
                datasets: [{
                    label: 'Savings ($ per 1% Yield Increase)',
                    data: auditData.map(i => i.value),
                    backgroundColor: auditData.map(i => i.color)
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                layout: {
                    padding: {
                        left: 25
                    }
                },
                scales: {
                    x: {
                        ticks: { color: '#fff' },
                        grid: { color: 'rgba(255,255,255,0.1)' }
                    },
                    y: {
                        ticks: { color: '#fff' },
                        grid: { color: 'rgba(255,255,255,0.1)' }
                    }
                },
                plugins: {
                    legend: {
                        labels: { color: '#fff' }
                    }
                }
            }
        });
    }

    // 4. Grouped Bar Plots for Overall Route Comparison
    if (rComp1Inst) rComp1Inst.destroy();
    const rc1Canvas = document.getElementById('routeComp1');
    if (rc1Canvas) {
        rComp1Inst = new Chart(rc1Canvas, {
            type: 'bar',
            data: {
                labels: ['Route A', 'Route B'],
                datasets: [{
                    label: 'Total Cost ($)',
                    data: [a.total_cost || 0, b.total_cost || 0],
                    backgroundColor: ['#0984e3', '#27ae60']
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                layout: { padding: { right: 15, left: 5 } },
                scales: {
                    x: { ticks: { color: '#fff' }, grid: { color: 'rgba(255,255,255,0.1)' } },
                    y: { ticks: { color: '#fff' }, grid: { color: 'rgba(255,255,255,0.1)' } }
                },
                plugins: { legend: { display: false } }
            }
        });
    }

    if (rComp2Inst) rComp2Inst.destroy();
    const rc2Canvas = document.getElementById('routeComp2');
    if (rc2Canvas) {
        rComp2Inst = new Chart(rc2Canvas, {
            type: 'bar',
            data: {
                labels: ['Route A', 'Route B'],
                datasets: [{
                    label: 'Cost per kg ($)',
                    data: [a.cost_per_kg || 0, b.cost_per_kg || 0],
                    backgroundColor: ['#0984e3', '#27ae60']
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                layout: { padding: { right: 15, left: 5 } },
                scales: {
                    x: { ticks: { color: '#fff' }, grid: { color: 'rgba(255,255,255,0.1)' } },
                    y: { ticks: { color: '#fff' }, grid: { color: 'rgba(255,255,255,0.1)' } }
                },
                plugins: { legend: { display: false } }
            }
        });
    }

    if (rComp3Inst) rComp3Inst.destroy();
    const rc3Canvas = document.getElementById('routeComp3');
    if (rc3Canvas) {
        rComp3Inst = new Chart(rc3Canvas, {
            type: 'bar',
            data: {
                labels: ['Route A', 'Route B'],
                datasets: [{
                    label: 'E-Factor',
                    data: [a.e_factor || 0, b.e_factor || 0],
                    backgroundColor: ['#0984e3', '#27ae60']
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                layout: { padding: { right: 15, left: 5 } },
                scales: {
                    x: { ticks: { color: '#fff' }, grid: { color: 'rgba(255,255,255,0.1)' } },
                    y: { ticks: { color: '#fff' }, grid: { color: 'rgba(255,255,255,0.1)' } }
                },
                plugins: { legend: { display: false } }
            }
        });
    }

    // 5. Yield Cascade Waterfall (Theoretical -> Actual Mass)
    if (waterfallChartInst) waterfallChartInst.destroy();
    const wfCanvas = document.getElementById('waterfallChart');
    if (wfCanvas) {
        const wfLabels = [];
        const wfAData = [];
        const wfBData = [];
        const wfAColors = [];
        const wfBColors = [];

        // Route A waterfall
        let runA = 100;
        wfLabels.push('A Start');
        wfAData.push([0, runA]);
        wfBData.push(null);
        wfAColors.push('#0984e3');
        wfBColors.push('transparent');

        const labStepsA = collectStepData('vA');
        labStepsA.forEach((s, idx) => {
            const lost = runA * (1 - (s.yield_percent || 100) / 100);
            const nextRun = runA - lost;
            wfLabels.push(`A S${s.step_id} → waste`);
            wfAData.push([nextRun, runA]);
            wfBData.push(null);
            wfAColors.push('#ff7675');
            wfBColors.push('transparent');
            runA = nextRun;
        });

        wfLabels.push('A Final');
        wfAData.push([0, runA]);
        wfBData.push(null);
        wfAColors.push('#00cec9');
        wfBColors.push('transparent');

        // Route B waterfall
        let runB = 100;
        wfLabels.push('B Start');
        wfAData.push(null);
        wfBData.push([0, runB]);
        wfAColors.push('transparent');
        wfBColors.push('#27ae60');

        const labStepsB = collectStepData('vB');
        labStepsB.forEach((s, idx) => {
            const lost = runB * (1 - (s.yield_percent || 100) / 100);
            const nextRun = runB - lost;
            wfLabels.push(`B S${s.step_id} → waste`);
            wfAData.push(null);
            wfBData.push([nextRun, runB]);
            wfAColors.push('transparent');
            wfBColors.push('#ff7675');
            runB = nextRun;
        });

        wfLabels.push('B Final');
        wfAData.push(null);
        wfBData.push([0, runB]);
        wfAColors.push('transparent');
        wfBColors.push('#2ecc71');

        waterfallChartInst = new Chart(wfCanvas, {
            type: 'bar',
            data: {
                labels: wfLabels,
                datasets: [
                    {
                        label: 'Route A Mass',
                        data: wfAData,
                        backgroundColor: wfAColors
                    },
                    {
                        label: 'Route B Mass',
                        data: wfBData,
                        backgroundColor: wfBColors
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { ticks: { color: '#fff' }, grid: { color: 'rgba(255,255,255,0.1)' } },
                    y: { 
                        title: { display: true, text: 'Mass Percentage (%)', color: '#fff' },
                        ticks: { color: '#fff' }, 
                        grid: { color: 'rgba(255,255,255,0.1)' } 
                    }
                },
                plugins: {
                    legend: { labels: { color: '#fff' } }
                }
            }
        });
    }

    // 6. Cost Drivers Plot (Reagents vs Solvents)
    if (costDriversChartInst) costDriversChartInst.destroy();
    const cdCanvas = document.getElementById('costDriversChart');
    if (cdCanvas) {
        const costMap = {};

        if (a.steps) {
            a.steps.forEach(s => {
                if (s.solvent_cost > 0) {
                    const name = `${s.solvent_name} (Solvent)`;
                    costMap[name] = (costMap[name] || 0) + s.solvent_cost;
                }
                if (s.reagents) {
                    s.reagents.forEach(r => {
                        if (r.item_cost > 0) {
                            costMap[r.name] = (costMap[r.name] || 0) + r.item_cost;
                        }
                    });
                }
            });
        }

        if (b.steps) {
            b.steps.forEach(s => {
                if (s.solvent_cost > 0) {
                    const name = `${s.solvent_name} (Solvent)`;
                    costMap[name] = (costMap[name] || 0) + s.solvent_cost;
                }
                if (s.reagents) {
                    s.reagents.forEach(r => {
                        if (r.item_cost > 0) {
                            costMap[r.name] = (costMap[r.name] || 0) + r.item_cost;
                        }
                    });
                }
            });
        }

        const sortedItems = Object.entries(costMap)
            .map(([name, cost]) => ({ name, cost }))
            .sort((x, y) => y.cost - x.cost)
            .slice(0, 10);

        costDriversChartInst = new Chart(cdCanvas, {
            type: 'bar',
            data: {
                labels: sortedItems.map(i => i.name),
                datasets: [{
                    label: 'Total Cost ($)',
                    data: sortedItems.map(i => i.cost),
                    backgroundColor: '#6c5ce7'
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { ticks: { color: '#fff' }, grid: { color: 'rgba(255,255,255,0.1)' } }
                },
                plugins: {
                    legend: { labels: { color: '#fff' } }
                }
            }
        });
    }
}

function exportToCSV() {
    if (!lastAnalysis.vA && !lastAnalysis.vB) { alert("Run analysis first!"); return; }

    let csv = "--- SECTION 1: ROUTE STEPS DETAILS ---\n";
    csv += "Route,Step,Name,Molarity,Solvent,Reagent,Mass_g,Cost\n";
    ['vA', 'vB'].forEach(side => {
        const res = lastAnalysis[side];
        if(res?.steps) res.steps.forEach(s => { 
            s.reagents.forEach(r => { csv += `${side},${s.step_id},"${s.name}",${s.molarity},"${s.solvent_name}","${r.name}",${r.mass_g},${r.item_cost}\n`; }); 
        });
    });

    csv += "\n--- SECTION 2: YIELD SENSITIVITY AUDIT ---\n";
    csv += "Route,Step,Name,Savings per 1% Yield Increase ($)\n";
    ['vA', 'vB'].forEach(side => {
        const res = lastAnalysis[side];
        if(res?.steps) res.steps.forEach(s => {
            const sensitivity = s.sensitivity || 0;
            if (sensitivity > 0) {
                csv += `${side},${s.step_id},"${s.name}",${sensitivity.toFixed(2)}\n`;
            }
        });
    });

    csv += "\n--- SECTION 3: COMPREHENSIVE COMPARISON SUMMARY ---\n";
    csv += "Metric,Route A,Route B\n";
    csv += `Target Goal,${document.getElementById('target-vA')?.value || 1} kg,${document.getElementById('target-vB')?.value || 1} kg\n`;
    csv += `Budget / Total Cost,$${(lastAnalysis.vA?.total_cost || 0).toLocaleString()},$${(lastAnalysis.vB?.total_cost || 0).toLocaleString()}\n`;
    csv += `Cost per kg,$${(lastAnalysis.vA?.cost_per_kg || 0).toFixed(2)},$${(lastAnalysis.vB?.cost_per_kg || 0).toFixed(2)}\n`;
    csv += `E-Factor,${lastAnalysis.vA?.e_factor || 0},${lastAnalysis.vB?.e_factor || 0}\n`;

    csv += "\n--- SECTION 4: RAW INPUT DATA FOR HYDRATION ---\n";
    csv += "Route,Step,Name,Product_MW,Temperature,Time,Molarity,Solvent_Name,Solvent_Volume,Solvent_Volume_Unit,Solvent_Bottle_L,Solvent_Bottle_Price,Yield_Percent,Procedure,Depends_On,Reagent_Name,MW,Pkg_Size,Pkg_Price,Equivalents,Mass,Mass_Unit,Is_Limiting,Solvent_Bottle_Amount,Solvent_Bottle_Unit\n";
    ['vA', 'vB'].forEach(side => {
        const steps = collectStepData(side);
        steps.forEach(s => {
            const depsStr = (s.depends_on || []).join(';');
            s.reagents.forEach(r => {
                csv += `${side},${s.step_id},"${s.name}",${s.product_mw},"${s.temperature}","${s.time}",${s.molarity},"${s.solvent_name}",${s.solvent_volume},"${s.solvent_volume_unit}",${s.solvent_bottle_l},${s.solvent_bottle_price},${s.yield_percent},"${(s.procedure || '').replace(/"/g, '""')}",${depsStr},"${r.name}",${r.mw},${r.pkg_size},${r.pkg_price},${r.equivalents},${r.mass},"${r.mass_unit}",${r.is_limiting},${s.solvent_bottle_amount},"${s.solvent_bottle_unit}"\n`;
            });
        });
    });

    const blob = new Blob([csv], {type: 'text/csv'});
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'procurement_report.csv'; a.click();
}

/**
 * Consolidates all reagents from the dashboard and redirects to the Risk Audit tool.
 */
function pushToRiskAudit() {
    const stepsA = collectStepData('vA');
    const stepsB = collectStepData('vB');
    const allSteps = [...stepsA, ...stepsB];
    
    if (allSteps.length === 0) {
        alert("Add some synthesis steps first!");
        return;
    }

    // Consolidate reagents by name/CAS to avoid duplicates
    const reagentMap = {};
    allSteps.forEach(step => {
        step.reagents.forEach(r => {
            const key = (r.cas || r.name).toLowerCase().trim();
            if (!reagentMap[key]) {
                reagentMap[key] = {
                    name: r.name,
                    cas: r.cas || '',
                    mass_g: 0,
                    cost: 0
                };
            }
            const rMass = parseFloat(r.mass) || 0;
            const rCost = parseFloat(r.item_cost) || (rMass * (parseFloat(r.cost_per_g) || 0));
            
            reagentMap[key].mass_g += rMass;
            reagentMap[key].cost += rCost;
        });
    });

    const consolidated = Object.values(reagentMap).filter(r => r.name);
    
    if (consolidated.length === 0) {
        alert("No reagents found in the active routes.");
        return;
    }

    localStorage.setItem('pendingRiskData', JSON.stringify(consolidated));
    window.location.href = '/risk.html';
}

function exportReport() {
    if (!lastAnalysis.vA && !lastAnalysis.vB) { alert("Run analysis first!"); return; }
    exportToCSV();

    const ids = {
        'efficiencyChart': 'route_efficiency',
        'stepCostChart': 'step_wise_cost',
        'bottleneckChart': 'optimization_bottleneck',
        'waterfallChart': 'yield_cascade_waterfall',
        'costDriversChart': 'top_cost_drivers'
    };
    
    if (typeof JSZip !== 'undefined') {
        const zip = new JSZip();
        Object.entries(ids).forEach(([id, filename]) => {
            const canvas = document.getElementById(id);
            if (canvas) {
                try {
                    const imgData = canvas.toDataURL('image/png').split(',')[1];
                    zip.file(`${filename}.png`, imgData, {base64: true});
                } catch (e) {
                    console.error("Could not add chart to zip:", id, e);
                }
            }
        });

        zip.generateAsync({type: 'blob'}).then(function(content) {
            const link = document.createElement('a');
            link.href = URL.createObjectURL(content);
            link.download = 'synthesis_plots.zip';
            link.click();
        });
    } else {
        alert("The ZIP creation library is still loading, please try again in a few seconds.");
    }
}

function loadFromCSV(event) {
    const file = event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = function(e) {
        const text = e.target.result;
        const lines = text.split('\n');
        
        let inSection4 = false;
        const data = { vA: {}, vB: {} };

        function parseCSVLine(line) {
            const parts = [];
            let inQuotes = false;
            let currentPart = '';
            for (let i = 0; i < line.length; i++) {
                const c = line[i];
                if (c === '"') {
                    if (inQuotes && line[i + 1] === '"') {
                        currentPart += '"';
                        i++;
                    } else {
                        inQuotes = !inQuotes;
                    }
                } else if (c === ',' && !inQuotes) {
                    parts.push(currentPart);
                    currentPart = '';
                } else {
                    currentPart += c;
                }
            }
            parts.push(currentPart);
            return parts;
        }

        lines.forEach(line => {
            if (line.includes('--- SECTION 4')) { inSection4 = true; return; }
            if (line.includes('---') && inSection4) { inSection4 = false; return; }

            if (inSection4 && line.trim()) {
                const parts = parseCSVLine(line);
                if (parts && parts.length >= 23 && parts[0] !== 'Route') {
                    const side = parts[0].trim();
                    const stepId = parseInt(parts[1]);
                    const name = parts[2].replace(/"/g, '').trim();
                    const pmw = parseFloat(parts[3]) || 0;
                    const temp = parts[4].replace(/"/g, '').trim();
                    const time = parts[5].replace(/"/g, '').trim();
                    const molarity = parseFloat(parts[6]) || 0;
                    const solvent = parts[7].replace(/"/g, '').trim();
                    const vol = parseFloat(parts[8]) || 0;
                    const volu = parts[9].replace(/"/g, '').trim();
                    const sbotl = parseFloat(parts[10]) || 1;
                    const sbotp = parseFloat(parts[11]) || 0;
                    const yieldVal = parseFloat(parts[12]) || 100;
                    const proc = parts[13].replace(/"/g, '').trim();
                    const deps = parts[14].trim() ? parts[14].split(';').map(d => parseInt(d)) : [];
                    const reagentName = parts[15].replace(/"/g, '').trim();
                    const mw = parseFloat(parts[16]) || 0;
                    const pkgsz = parseFloat(parts[17]) || 1;
                    const pkgpr = parseFloat(parts[18]) || 0;
                    const eq = parseFloat(parts[19]) || 0;
                    const mass = parseFloat(parts[20]) || 0;
                    const unit = parts[21].replace(/"/g, '').trim();
                    const isLim = parts[22].trim() === 'true';

                    if (side === 'vA' || side === 'vB') {
                        if (!data[side][stepId]) {
                            data[side][stepId] = {
                                step_id: stepId,
                                name: name,
                                product_mw: pmw,
                                temperature: temp,
                                time: time,
                                molarity: molarity,
                                solvent_name: solvent,
                                solvent_volume: vol,
                                solvent_volume_l: volu === 'mL' ? vol / 1000 : vol,
                                solvent_volume_unit: volu,
                                solvent_bottle_l: sbotl,
                                solvent_bottle_price: sbotp,
                                solvent_bottle_amount: (parts.length >= 25) ? parseFloat(parts[23]) : sbotl,
                                solvent_bottle_unit: (parts.length >= 25) ? parts[24].replace(/"/g, '').trim() : 'L',
                                yield_percent: yieldVal,
                                procedure: proc,
                                depends_on: deps,
                                reagents: []
                            };
                        }
                        data[side][stepId].reagents.push({
                            name: reagentName,
                            mw: mw,
                            pkg_size: pkgsz,
                            pkg_price: pkgpr,
                            equivalents: eq,
                            mass: mass,
                            mass_unit: unit,
                            is_limiting: isLim
                        });
                    }
                }
            }
        });

        const hasSection4 = Object.keys(data.vA).length > 0 || Object.keys(data.vB).length > 0;
        if (hasSection4) {
            ['vA', 'vB'].forEach(side => {
                const steps = Object.values(data[side]).sort((a, b) => a.step_id - b.step_id);
                clearRouteUI(side);
                steps.forEach(s => addStep(side, s));
            });
        } else {
            let inSection1 = false;
            const data1 = { vA: {}, vB: {} };
            lines.forEach(line => {
                if (line.includes('--- SECTION 1')) { inSection1 = true; return; }
                if (line.includes('---')) { inSection1 = false; return; }
                
                if (inSection1 && line.trim()) {
                    const parts = line.split(',');
                    if (parts.length >= 8 && parts[0] !== 'Route') {
                        const side = parts[0].trim();
                        const stepId = parseInt(parts[1]);
                        const name = parts[2].replace(/"/g, '').trim();
                        const molarity = parseFloat(parts[3]) || 0;
                        const solvent = parts[4].replace(/"/g, '').trim();
                        const reagentName = parts[5].replace(/"/g, '').trim();
                        const mass = parseFloat(parts[6]) || 0;
                        const cost = parseFloat(parts[7]) || 0;

                        if (side === 'vA' || side === 'vB') {
                            if (!data1[side][stepId]) {
                                data1[side][stepId] = {
                                    step_id: stepId,
                                    name: name,
                                    molarity: molarity,
                                    solvent_name: solvent,
                                    reagents: []
                                };
                            }
                            data1[side][stepId].reagents.push({
                                name: reagentName,
                                mass: mass,
                                cost_per_g: cost / (mass || 1)
                            });
                        }
                    }
                }
            });

            ['vA', 'vB'].forEach(side => {
                const steps = Object.values(data1[side]).sort((a, b) => a.step_id - b.step_id);
                if (steps.length > 0) {
                    clearRouteUI(side);
                    steps.forEach(s => addStep(side, s));
                }
            });
        }

        setTimeout(() => {
            runAnalysis();
        }, 150);
    };
    reader.readAsText(file);
}

function loadFromFile(ev, target) {
    const reader = new FileReader();
    reader.onload = (e) => {
        const d = JSON.parse(e.target.result);
        const loaded = [];
        if (target === 'both') {
            clearRouteUI('vA'); clearRouteUI('vB');
            if(d.routeA?.steps) { d.routeA.steps.forEach(s => addStep('vA', s)); loaded.push('vA'); }
            if(d.routeB?.steps) { d.routeB.steps.forEach(s => addStep('vB', s)); loaded.push('vB'); }
        } else {
            clearRouteUI(target);
            const steps = d.routeA?.steps || d.routeB?.steps || [];
            steps.forEach(s => addStep(target, s));
            loaded.push(target);
        }
        // A loaded JSON may be partial — flag any missing required fields.
        loaded.forEach(side => activateDraftHighlight(side));
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

function addScaledSection(side) {
    const mult = parseFloat(document.getElementById(`scale-mult-${side}`).value) || 1;
    if (mult <= 0) return;

    const labSteps = collectStepData(side);
    if (!labSteps.length) return;

    const color = side === 'vA' ? 'var(--primary)' : 'var(--secondary)';
    const bg = side === 'vA' ? 'rgba(9, 132, 227, 0.15)' : 'rgba(46, 204, 113, 0.15)';
    const borderColor = side === 'vA' ? 'rgba(9, 132, 227, 0.35)' : 'rgba(46, 204, 113, 0.35)';

    let html = `<div style="position:relative; margin-top:20px; background:${bg}; border:1px solid ${borderColor}; padding:15px; border-radius:8px;">
        <span style="position:absolute; top:8px; right:12px; cursor:pointer; color:#ff7675; font-size:1.4em; font-weight:bold; line-height:1;" onclick="this.parentElement.remove()" title="Delete Section">×</span>
        <h4 style="color:${color}; margin-top:0; font-size:0.9em; margin-bottom:10px;">📋 Route ${side === 'vA'?'A':'B'} (${mult}x Scale-Up)</h4>`;

    labSteps.forEach(s => {
        let stepTotal = 0;
        let limMw = 0, limEq = 1, limMassInG = 0;
        s.reagents.forEach(r => {
            let inG = r.mass * mult;
            if (r.mass_unit === 'mg') inG = (r.mass * mult) / 1000;
            if (r.mass_unit === 'kg') inG = (r.mass * mult) * 1000;
            const cost = inG * (r.cost_per_g || 0);
            r.lab_cost = cost;
            r.lab_mass_in_g = inG;
            stepTotal += cost;

            if (r.is_limiting && r.mw > 0) {
                limMw = r.mw;
                limEq = r.equivalents || 1;
                limMassInG = inG;
            }
        });
        // solvent cost
        if (s.solvent_bottle_l > 0) {
            const sCost = s.solvent_volume_l * mult * (s.solvent_bottle_price / s.solvent_bottle_l);
            stepTotal += sCost;
        }

        let productProduced = 0;
        if (limMw > 0 && s.product_mw > 0) {
            const baseMoles = limMassInG / limMw / limEq;
            productProduced = baseMoles * s.product_mw * (s.yield_percent / 100);
        }

        html += `<div style="margin-top:15px; border-top:1px solid #555; padding-top:8px;">
            <div style="display:flex; justify-content:space-between; font-size:0.85em; margin-bottom:5px;">
                <span style="color:#00cec9;">S${s.step_id}: ${s.name}</span>
                <span>Subtotal: $${stepTotal.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}</span>
            </div>
            <div style="display:flex; justify-content:space-between; font-size:0.8em; margin-bottom:5px; color:#ffeaa7;">
                <span>Product Yield: ${s.yield_percent}%</span>
                <span>Amt Produced: ${productProduced.toLocaleString(undefined, {minimumFractionDigits:3, maximumFractionDigits:3})} g</span>
            </div>
            <div style="font-size:0.75em; background:rgba(255,255,255,0.05); padding:8px; margin:5px 0; white-space: pre-wrap; border:1px solid #555;">${s.procedure || 'No notes.'}</div>
            <table style="width:100%; font-size:0.7em; color:#dfe6e9; border-collapse:collapse; margin-top:4px;">
                <tr style="border-bottom:1px solid #555;"><th style="text-align:left; padding:4px 0;">Reagent</th><th style="text-align:left;">Amount Used</th><th style="text-align:left;">Cost</th></tr>`;
        s.reagents.forEach(r => {
            html += `<tr style="border-bottom:1px solid #444;"><td style="padding:4px 0;">${r.name}</td><td>${(r.mass * mult).toLocaleString()} ${r.mass_unit}</td><td>$${(r.lab_cost || 0).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}</td></tr>`;
        });
        if (s.solvent_volume > 0) {
            const sCost = s.solvent_volume_l * mult * (s.solvent_bottle_price / s.solvent_bottle_l);
            html += `<tr style="border-bottom:1px solid #444;"><td style="padding:4px 0; color:#00cec9;">${s.solvent_name} (Solvent)</td><td>${(s.solvent_volume * mult).toLocaleString()} ${s.solvent_volume_unit}</td><td>$${sCost.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}</td></tr>`;
        }
        html += `</table></div>`;
    });

    html += `</div>`;
    document.getElementById(`scaled-sections-${side}`).insertAdjacentHTML('beforeend', html);
}

function matchProducedGrams(fromSide, toSide) {
    const fromId = counters[fromSide];
    const toId = counters[toSide];
    if (!fromId || !toId) { alert(`Add steps to both routes first!`); return; }

    const targetGrams = parseFloat(document.getElementById(`prodg-${toSide}-${toId}`).value) || 0;
    if (targetGrams <= 0) { alert(`Run analysis or calculate limiting reagents for Route ${toSide === 'vB' ? 'B' : 'A'} first.`); return; }

    const pmw = parseFloat(document.getElementById(`pmw-${fromSide}-${fromId}`).value) || 0;
    const yieldPct = parseFloat(document.getElementById(`yield-${fromSide}-${fromId}`).value) || 0;
    
    if (pmw <= 0 || yieldPct <= 0) { alert(`Set Product MW and Yield % for Route ${fromSide === 'vA' ? 'A' : 'B'} first.`); return; }

    const container = document.getElementById(`reagents-container-${fromSide}-${fromId}`);
    if (!container) return;

    let limMw = 0;
    let limEq = 0;
    let limRow = null;

    const rows = container.querySelectorAll('.reagent-row');
    for (let i=0; i<rows.length; i++) {
        const limCb = rows[i].querySelector('.r-lim');
        if (limCb && limCb.checked) {
            limMw = parseFloat(rows[i].querySelector('.r-mw').value) || 0;
            limEq = parseFloat(rows[i].querySelector('.r-eq').value) || 1;
            limRow = rows[i];
            break;
        }
    }

    if (!limRow || limMw <= 0 || limEq <= 0) { alert(`Please select a limiting reagent with a valid MW and Eq for Route ${fromSide === 'vA' ? 'A' : 'B'}'s final step.`); return; }

    const newLimMassInG = (targetGrams * limMw * limEq) / (pmw * (yieldPct / 100));

    const unit = limRow.querySelector('.r-mass-unit').value;
    let massInUnit = newLimMassInG;
    if (unit === 'mg') massInUnit = newLimMassInG * 1000;
    if (unit === 'kg') massInUnit = newLimMassInG / 1000;

    limRow.querySelector('.r-mass').value = massInUnit.toFixed(4);

    calcStoichByContainer(container);

    setTimeout(() => {
        runAnalysis();
    }, 150);
}

/**
 * Enables or disables the "Add to Database" button.
 */
function setDatabaseButtonEnabled(enabled) {
    const btn = document.getElementById('addToDatabaseBtn');
    if (btn) btn.disabled = !enabled;
}

/**
 * Collects current analysis state and saves both routes to the SQLite database.
 */
async function addToDatabase() {
    const targetMol = document.querySelector('h1').textContent.split(' — ')[0].trim() || "Unknown Target";
    
    const tasks = [];
    
    // Process Route A
    const stepsA = collectStepData('vA');
    if (stepsA && stepsA.length > 0 && lastAnalysis.vA) {
        tasks.push(saveRouteToDb("Route A", targetMol, "vA", stepsA, lastAnalysis.vA));
    }
    
    // Process Route B
    const stepsB = collectStepData('vB');
    if (stepsB && stepsB.length > 0 && lastAnalysis.vB) {
        tasks.push(saveRouteToDb("Route B", targetMol, "vB", stepsB, lastAnalysis.vB));
    }
    
    if (tasks.length === 0) {
        showDatabaseToast("No valid analysis data to save.", "error");
        return;
    }
    
    setDatabaseButtonEnabled(false);
    try {
        await Promise.all(tasks);
    } catch (err) {
        console.error("Database save error:", err);
    } finally {
        // We leave it disabled or re-enable if needed. Re-enabling for now.
        setDatabaseButtonEnabled(true);
    }
}

/**
 * Internal helper to POST a route to the database.
 */
async function saveRouteToDb(label, targetMol, side, steps, analysisResults) {
    const sourceFile = document.getElementById(`filename-${side}`)?.value || null;
    const targetMass = parseFloat(document.getElementById(`target-${side}`)?.value) || 1.0;
    
    const payload = {
        route_label: label,
        target_molecule: targetMol,
        target_mass_kg: targetMass,
        source_file: sourceFile,
        route: { steps: steps },
        analysis_results: {
            total_cost: analysisResults.total_cost || 0,
            cost_per_kg: analysisResults.cost_per_kg || 0,
            e_factor: analysisResults.e_factor || 0,
            overall_yield_percent: analysisResults.overall_yield || 100
        }
    };
    
    try {
        const response = await fetch('/api/database/save-route', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        const result = await response.json();
        if (response.ok && result.success) {
            let msg = `✅ ${label} saved — ${result.new_compounds} new, ${result.updated_compounds} updated`;
            if (result.ambiguous_compounds.length > 0) {
                msg += ` (${result.ambiguous_compounds.length} need review)`;
            }
            showDatabaseToast(msg, "success");
        } else {
            showDatabaseToast(`❌ Failed to save ${label}: ${result.detail || 'Unknown error'}`, "error");
        }
    } catch (err) {
        showDatabaseToast(`❌ Network error saving ${label}`, "error");
        throw err;
    }
}

/**
 * Displays a professional toast notification for database actions.
 */
function showDatabaseToast(message, type = "success") {
    const toast = document.getElementById('db-toast');
    if (!toast) return;
    
    toast.textContent = message;
    toast.style.background = type === "success" ? "#00b894" : (type === "warning" ? "#fdcb6e" : "#d63031");
    toast.style.color = "white";
    toast.style.display = "block";
    toast.style.opacity = "1";
    
    setTimeout(() => {
        toast.style.transition = "opacity 0.6s ease";
        toast.style.opacity = "0";
        setTimeout(() => {
            toast.style.display = "none";
            toast.style.transition = "";
        }, 600);
    }, 5000);
}

/* =================================================================
   PARTIAL-DATA HIGHLIGHTING
   Drafts from Experiment Setup (and any partial JSON load) may be
   missing fields. We highlight the empty required ones in red and show
   a banner per route so it's obvious what still needs input.
   ================================================================= */

let draftActive = { vA: false, vB: false };

// Reagent fields required before analysis is meaningful.
const REQUIRED_REAGENT_SELECTORS = ['.r-name', '.r-mw', '.r-eq', '.r-mass'];

function isEmptyVal(v) { return v === null || v === undefined || String(v).trim() === ''; }

/** Turn on highlighting for a side after a draft/partial load, then evaluate. */
function activateDraftHighlight(side) {
    draftActive[side] = true;
    // addStep schedules a stoich recalc at ~50ms; flag just after so values settle.
    setTimeout(() => flagIncompleteRoute(side, true), 150);
}

/** Mark empty required inputs in a route, render its banner, return the count. */
function flagIncompleteRoute(side, announce) {
    const container = document.getElementById(`steps-${side}`);
    if (!container) return 0;
    let missing = 0;

    container.querySelectorAll('.reagent-row').forEach(row => {
        REQUIRED_REAGENT_SELECTORS.forEach(sel => {
            const el = row.querySelector(sel);
            if (!el) return;
            if (isEmptyVal(el.value)) { el.classList.add('field-missing'); missing++; }
            else el.classList.remove('field-missing');
        });
    });

    // Step-level: product MW (defaults to 0, which is not a valid weight).
    container.querySelectorAll('.step-card').forEach(card => {
        const pmw = card.querySelector('input[id^="pmw-"]');
        if (!pmw) return;
        if (isEmptyVal(pmw.value) || parseFloat(pmw.value) === 0) { pmw.classList.add('field-missing'); missing++; }
        else pmw.classList.remove('field-missing');
    });

    renderDraftBanner(side, missing);
    if (announce && missing > 0) {
        const b = document.getElementById(`draft-banner-${side}`);
        if (b) b.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    return missing;
}

/** Insert/update the per-route banner above the steps list. */
function renderDraftBanner(side, missing) {
    const steps = document.getElementById(`steps-${side}`);
    if (!steps) return;
    let banner = document.getElementById(`draft-banner-${side}`);
    if (!banner) {
        banner = document.createElement('div');
        banner.id = `draft-banner-${side}`;
        steps.parentNode.insertBefore(banner, steps);
    }
    const label = side === 'vA' ? 'A' : 'B';
    if (missing > 0) {
        banner.className = 'draft-banner';
        banner.innerHTML = `<span class="draft-badge">${missing}</span> field(s) in Route ${label} still need input — highlighted in red below. Fill them in, then Run Analysis.`;
    } else {
        banner.className = 'draft-banner complete';
        banner.innerHTML = `✅ Route ${label}: all required fields filled.`;
    }
    banner.style.display = 'flex';
}

// Re-evaluate highlights as the user fills fields (only for activated routes).
['vA', 'vB'].forEach(side => {
    document.addEventListener('DOMContentLoaded', () => {
        const c = document.getElementById(`steps-${side}`);
        if (c) c.addEventListener('input', () => { if (draftActive[side]) flagIncompleteRoute(side, false); });
    });
});

// On load, pick up draft(s) handed over from the Experiment Setup page.
document.addEventListener('DOMContentLoaded', () => {
    const raw = localStorage.getItem('pendingRouteDraft');
    if (!raw) return;
    localStorage.removeItem('pendingRouteDraft');
    let payload;
    try { payload = JSON.parse(raw); } catch (e) { console.error('Bad route draft:', e); return; }

    // New format hands over one or two routes as { routes: [...] }; the legacy
    // format was a single draft object ({ target, steps, ... }). Support both.
    const routes = Array.isArray(payload.routes) ? payload.routes : [payload];
    routes.forEach(draft => {
        const side = draft.target === 'vB' ? 'vB' : 'vA';
        clearRouteUI(side);
        (draft.steps || []).forEach(s => addStep(side, s));
        activateDraftHighlight(side);
    });
});

