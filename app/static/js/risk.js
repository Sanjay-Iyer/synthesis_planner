/**
 * Risk Assessment Frontend — CSV parsing, API calls, and Chart.js bubble chart.
 */

const API_BASE = '';
let riskChartInst = null;
let lastRiskResults = null;

// Initialize with 3 empty rows
document.addEventListener('DOMContentLoaded', () => {
    for (let i = 0; i < 3; i++) addReagentInputRow();
});

function addReagentInputRow(data = null) {
    const container = document.getElementById('reagentRows');
    const row = document.createElement('div');
    row.className = 'reagent-input-row fade-in';
    row.innerHTML = `
        <input type="text" placeholder="e.g. CuCl2" value="${data?.name || ''}">
        <input type="text" placeholder="e.g. 7447-39-4" value="${data?.cas || ''}">
        <input type="number" step="any" placeholder="0" value="${data?.mass_g || ''}">
        <input type="number" step="any" placeholder="0" value="${data?.cost || ''}">
        <button class="btn btn-danger btn-sm" onclick="this.parentElement.remove()" style="padding:4px 8px;">✕</button>
    `;
    container.appendChild(row);
}

function collectReagentInputs() {
    const rows = document.querySelectorAll('#reagentRows .reagent-input-row');
    const reagents = [];
    rows.forEach(row => {
        const inputs = row.querySelectorAll('input');
        const name = inputs[0].value.trim();
        if (!name) return;
        reagents.push({
            name: name,
            cas: inputs[1].value.trim(),
            mass_g: parseFloat(inputs[2].value) || 0,
            cost: parseFloat(inputs[3].value) || 0
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
        const massIdx = header.findIndex(h => /mass/i.test(h));
        const costIdx = header.findIndex(h => /cost/i.test(h));

        // Clear existing rows
        document.getElementById('reagentRows').innerHTML = '';

        // Parse data rows
        for (let i = 1; i < lines.length; i++) {
            const cols = lines[i].split(',').map(c => c.trim().replace(/"/g, ''));
            if (cols.length < 2) continue;

            addReagentInputRow({
                name: nameIdx >= 0 ? cols[nameIdx] : cols[0],
                cas: casIdx >= 0 ? cols[casIdx] : '',
                mass_g: massIdx >= 0 ? parseFloat(cols[massIdx]) || 0 : 0,
                cost: costIdx >= 0 ? parseFloat(cols[costIdx]) || 0 : 0
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
        const data = await res.json();
        lastRiskResults = data;
        displayRiskResults(data);
    } catch (e) {
        alert('Risk assessment failed. Is the server running?');
    }
}

function displayRiskResults(data) {
    // Summary cards
    const summary = data.summary;
    document.getElementById('summaryCards').style.display = 'grid';
    document.getElementById('sumTotal').textContent = summary.total_reagents;
    document.getElementById('sumHighRisk').textContent = summary.high_risk_count;
    document.getElementById('sumExposure').textContent = summary.total_risk_exposure.toLocaleString();

    // Results table
    const tbody = document.getElementById('riskTableBody');
    tbody.innerHTML = '';
    document.getElementById('resultsCard').style.display = 'block';

    data.reagents.forEach(r => {
        const badgeClass = getBadgeClass(r.risk_level);
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${r.name}</strong></td>
            <td style="font-family:monospace; font-size:0.8em;">${r.cas || '—'}</td>
            <td>${r.primary_origin}</td>
            <td>${r.stability_score}/100</td>
            <td>${r.mass_g.toLocaleString()}</td>
            <td>$${r.cost.toLocaleString()}</td>
            <td>${r.risk_index.toLocaleString()}</td>
            <td><span class="badge ${badgeClass}">${r.risk_level.split('(')[0].trim()}</span></td>
        `;
        tbody.appendChild(tr);
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
