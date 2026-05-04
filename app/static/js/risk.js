/**
 * Risk Assessment Frontend — CSV parsing, API calls, and Chart.js bubble chart.
 */

const API_BASE = '';
let riskChartInst = null;
let lastRiskResults = null;
let knownMappings = []; // Cache for CAS -> Origin lookups

let bubbleChart = null;
let stackedBarChart = null;

// Initialize with data from dashboard or 3 empty rows
document.addEventListener('DOMContentLoaded', async () => {
    // Load known mappings first
    try {
        const res = await fetch(`${API_BASE}/api/risk/mappings`);
        knownMappings = await res.json();
    } catch (e) { console.error("Failed to load mappings", e); }

    const pendingData = localStorage.getItem('pendingRiskData');
    if (pendingData) {
        try {
            const reagents = JSON.parse(pendingData);
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

function addReagentInputRow(data = null) {
    const container = document.getElementById('reagentRows');
    const row = document.createElement('div');
    row.className = 'reagent-input-row fade-in';
    if (document.getElementById('advancedToggle').checked) row.classList.add('advanced');
    
    row.innerHTML = `
        <input type="text" class="r-name" placeholder="e.g. CuCl2" value="${data?.name || ''}">
        <div style="position:relative; display:flex; align-items:center;">
            <input type="text" class="cas-input r-cas" placeholder="e.g. 7447-39-4" value="${data?.cas || ''}" oninput="checkCAS(this)" style="width:100%;">
            <span class="status-dot" style="position:absolute; right:8px; width:8px; height:8px; border-radius:50%; background:#dfe6e9;" title="CAS Status"></span>
        </div>
        <input type="text" class="origin-input r-origin" placeholder="Origin" value="${data?.origin || ''}">
        <input type="number" step="any" class="r-mass" placeholder="Mass" value="${data?.mass_g || ''}">
        <input type="number" step="any" class="r-cost" placeholder="Cost" value="${data?.cost || ''}">
        <!-- Advanced fields -->
        <input type="number" step="any" class="r-lead adv-field" placeholder="Lead (d)" value="${data?.lead_time_days || '14'}">
        <input type="number" step="any" class="r-haz adv-field" placeholder="Haz (1-10)" value="${data?.hazard_score || '5'}">
        <input type="number" step="any" class="r-reg adv-field" placeholder="Reg (1-10)" value="${data?.regulatory_score || '5'}">
        <input type="number" step="any" class="r-sub adv-field" placeholder="Sub (1-10)" value="${data?.substitutability || '5'}">
        
        <button class="btn btn-danger btn-sm" onclick="this.parentElement.remove()" style="padding:4px 8px;">✕</button>
    `;
    container.appendChild(row);
    if (data?.cas) checkCAS(row.querySelector('.cas-input'));
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

function collectReagentInputs() {
    const rows = document.querySelectorAll('#reagentRows .reagent-input-row');
    const reagents = [];
    rows.forEach(row => {
        const name = row.querySelector('.r-name').value.trim();
        if (!name) return;
        reagents.push({
            name: name,
            cas: row.querySelector('.r-cas').value.trim(),
            origin: row.querySelector('.r-origin').value.trim(),
            mass_g: parseFloat(row.querySelector('.r-mass').value) || 0,
            cost: parseFloat(row.querySelector('.r-cost').value) || 0,
            lead_time_days: parseInt(row.querySelector('.r-lead').value) || 14,
            hazard_score: parseInt(row.querySelector('.r-haz').value) || 5,
            regulatory_score: parseInt(row.querySelector('.r-reg').value) || 5,
            substitutability: parseInt(row.querySelector('.r-sub').value) || 5,
            supplier_count: 3 // Default
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
        const header = lines[0].split(',').map(h => h.trim().replace(/"/g, ''));

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

        // Auto-enable advanced mode if advanced columns found
        if (leadIdx >= 0 || hazIdx >= 0 || subIdx >= 0) {
            document.getElementById('advancedToggle').checked = true;
            toggleAdvancedMode();
        }

        // Clear existing rows
        document.getElementById('reagentRows').innerHTML = '';

        // Parse data rows
        for (let i = 1; i < lines.length; i++) {
            const cols = lines[i].split(',').map(c => c.trim().replace(/"/g, ''));
            if (cols.length < 2) continue;

            addReagentInputRow({
                name: nameIdx >= 0 ? cols[nameIdx] : cols[0],
                cas: casIdx >= 0 ? cols[casIdx] : '',
                origin: originIdx >= 0 ? cols[originIdx] : '',
                mass_g: massIdx >= 0 ? parseFloat(cols[massIdx]) || 0 : 0,
                cost: costIdx >= 0 ? parseFloat(cols[costIdx]) || 0 : 0,
                lead_time_days: leadIdx >= 0 ? parseInt(cols[leadIdx]) || 14 : 14,
                hazard_score: hazIdx >= 0 ? parseInt(cols[hazIdx]) || 5 : 5,
                regulatory_score: regIdx >= 0 ? parseInt(cols[regIdx]) || 5 : 5,
                substitutability: subIdx >= 0 ? parseInt(cols[subIdx]) || 5 : 5
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

async function runRiskAssessment() {
    const reagents = collectReagentInputs();
    if (reagents.length === 0) { alert('Please enter at least one reagent.'); return; }

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
            renderStackedBarChart(data.reagents);
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
        name: r.name || 'Unknown'
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
                        label: (ctx) => `${ctx.raw.name}: Cost $${ctx.raw.x.toFixed(2)}, Risk ${ctx.raw.y.toFixed(1)}`
                    }
                }
            }
        }
    });
}

function renderStackedBarChart(reagents) {
    const ctx = document.getElementById('stackedBarChart').getContext('2d');
    if (stackedBarChart) stackedBarChart.destroy();

    const countryMap = {};
    reagents.forEach(r => {
        const origin = r.primary_origin || 'Unknown';
        if (!countryMap[origin]) countryMap[origin] = 0;
        countryMap[origin] += r.risk_index;
    });

    const labels = Object.keys(countryMap);
    const data = Object.values(countryMap);

    stackedBarChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Total Risk Exposure',
                data: data,
                backgroundColor: 'rgba(214, 48, 49, 0.7)',
                borderRadius: 5
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: { beginAtZero: true, title: { display: true, text: 'Risk Exposure' } }
            }
        }
    });
}

function renderHeatmap(reagents) {
    const grid = document.getElementById('heatmapGrid');
    grid.innerHTML = '';
    
    const columns = ['Geographic', 'Operational', 'Regulatory', 'Economic'];
    
    // Header
    grid.style.gridTemplateColumns = `120px repeat(${columns.length}, 1fr)`;
    grid.innerHTML += `<div></div>` + columns.map(c => `<div class="heatmap-label">${c}</div>`).join('');
    
    reagents.forEach(r => {
        // Reagent Label
        grid.innerHTML += `<div class="heatmap-label" style="text-align:right; padding-right:10px; color:var(--dark);">${r.name}</div>`;
        
        // Cells
        columns.forEach(col => {
            const val = r.breakdown[col.toLowerCase()];
            const color = getHeatmapColor(val);
            grid.innerHTML += `<div class="heatmap-cell" style="background:${color}" title="${col}: ${val}">${val}</div>`;
        });
    });
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

    // Results table
    const tbody = document.getElementById('riskTableBody');
    tbody.innerHTML = '';
    document.getElementById('resultsCard').style.display = 'block';

    data.reagents.forEach(r => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td style="font-weight:600;">${r.name || 'Unknown'}</td>
            <td style="font-family:monospace; font-size:0.8rem;">${r.cas || 'No CAS'}</td>
            <td>${r.primary_origin || 'Unknown'}</td>
            <td>${Math.round(r.stability_score || 0)}/100</td>
            <td>${(r.mass_g || 0).toLocaleString()}</td>
            <td>$${(r.cost || 0).toLocaleString()}</td>
            <td>${r.risk_index ? r.risk_index.toFixed(1) : '0.0'}</td>
            <td>
                <span class="status-pill status-${(r.risk_level || 'UNKNOWN').split(' ')[0].toLowerCase()}">
                    ${r.risk_level || 'UNKNOWN'}
                </span>
            </td>
            <td>
                ${(r.warnings || []).map(w => `
                    <div style="font-size:0.7rem; color:${w.includes('REGULATORY') ? 'var(--danger)' : 'var(--orange)'}; margin-bottom:2px;">
                        ⚠️ ${w}
                    </div>
                `).join('')}
            </td>
        `;
        tbody.appendChild(row);
    });

    // Bubble chart
    renderRiskChart(data.reagents);
}

function getBadgeClass(level) {
    if (level.includes('MEDIUM-HIGH')) return 'badge-medium-high';
    if (level.includes('HIGH')) return 'badge-high';
    if (level.includes('MEDIUM')) return 'badge-medium';
    return 'badge-low';
}

function getRiskColor(level) {
    if (level.includes('MEDIUM-HIGH')) return '#FFA15A';
    if (level.includes('HIGH')) return '#EF553B';
    if (level.includes('MEDIUM')) return '#FFD700';
    return '#00CC96';
}

function renderRiskChart(reagents) {
    if (riskChartInst) riskChartInst.destroy();

    const chartData = reagents.map(r => ({
        x: Math.max(r.cost, 0.01),  // Avoid log(0)
        y: r.risk_index,
        r: Math.sqrt(r.mass_g) + 5,
        label: r.name,
        color: getRiskColor(r.risk_level)
    }));

    riskChartInst = new Chart(document.getElementById('riskChart'), {
        type: 'bubble',
        data: {
            datasets: [{
                data: chartData.map(d => ({ x: d.x, y: d.y, r: Math.min(d.r, 40) })),
                backgroundColor: chartData.map(d => d.color + '99'),
                borderColor: chartData.map(d => d.color),
                borderWidth: 2,
                hoverBorderWidth: 3
            }]
        },
        options: {
            maintainAspectRatio: false,
            scales: {
                x: {
                    type: 'logarithmic',
                    title: { display: true, text: 'Cost ($)', color: '#bdc3c7' },
                    ticks: { color: '#bdc3c7', callback: v => '$' + v.toLocaleString() },
                    grid: { color: 'rgba(255,255,255,0.08)' }
                },
                y: {
                    title: { display: true, text: 'Risk Index', color: '#bdc3c7' },
                    ticks: { color: '#bdc3c7' },
                    grid: { color: 'rgba(255,255,255,0.08)' }
                }
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) => {
                            const r = reagents[ctx.dataIndex];
                            return [
                                r.name,
                                `Origin: ${r.primary_origin} (${r.stability_score}/100)`,
                                `Mass: ${r.mass_g.toLocaleString()}g`,
                                `Cost: $${r.cost.toLocaleString()}`,
                                `Risk: ${r.risk_index.toLocaleString()}`
                            ];
                        }
                    }
                },
                annotation: {
                    annotations: {
                        threshold: {
                            type: 'line',
                            yMin: 300, yMax: 300,
                            borderColor: 'rgba(255,255,255,0.3)',
                            borderDash: [6, 6],
                            borderWidth: 1,
                            label: {
                                display: true,
                                content: 'Critical Bulk Threshold',
                                color: 'rgba(255,255,255,0.5)',
                                position: 'end'
                            }
                        }
                    }
                }
            }
        }
    });
}

function exportRiskCSV() {
    if (!lastRiskResults) { alert('Run assessment first!'); return; }
    let csv = 'Reagent,CAS,Origin,Stability_Score,Mass_g,Cost,HS_Code,Risk_Index,Risk_Level\n';
    lastRiskResults.reagents.forEach(r => {
        csv += `"${r.name}","${r.cas}","${r.primary_origin}",${r.stability_score},${r.mass_g},${r.cost},"${r.hs_code || ''}",${r.risk_index},"${r.risk_level}"\n`;
    });
    const blob = new Blob([csv], { type: 'text/csv' });
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
    const csv = "Reagent,Reagent_CAS,Mass_g,Cost\nPlatinum on Carbon,7440-06-4,10,1500\nCopper(II) Chloride,7447-39-4,100,45\nBenzene,71-43-2,2000,50";
    const blob = new Blob([csv], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'sample_risk_reagents.csv';
    a.click();
}
