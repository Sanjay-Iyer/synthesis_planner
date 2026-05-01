/**
 * Labeller Logic — Procedure tagging and JSON/CSV export.
 * Extracted from inline script in the original labeller.html.
 */

function applyTag(tag) {
    const sel = window.getSelection();
    if (!sel.rangeCount || sel.toString().length === 0) return;
    const range = sel.getRangeAt(0);
    const tagged = `{${tag}:${sel.toString()}}`;
    range.deleteContents();
    range.insertNode(document.createTextNode(tagged));
}

function triggerDownload(content, filename, type) {
    const blob = new Blob([content], { type: type });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
}

function processAll() {
    const text = document.getElementById('editor').innerText;
    const sections = text.split(/===.*?===/).filter(s => {
        const clean = s.trim();
        return clean.length > 10 && !clean.includes("Paste your lab notes here");
    });

    if (sections.length === 0) {
        alert("No valid procedure found. Make sure you edited the placeholder text.");
        return;
    }

    const steps = [];
    let csvContent = "Step,Type,Name,Amount,Units,Notes\n";

    sections.forEach((rxn, idx) => {
        const step_id = idx + 1;
        const reagents = [];
        const rRegex = /\{R:([^}]+)\}/g;
        let rMatch;
        let stepLimitingMoles = 0;

        while ((rMatch = rRegex.exec(rxn)) !== null) {
            const name = rMatch[1];
            const context = rxn.substring(rMatch.index, rMatch.index + 120);
            const gMatch = context.match(/([\d\.]+)\s*g/);
            const molMatch = context.match(/([\d\.]+)\s*mol/);
            const mmolMatch = context.match(/([\d\.]+)\s*mmol/);

            const g = gMatch ? parseFloat(gMatch[1]) : 0;
            let moles = 0;
            if (molMatch) moles = parseFloat(molMatch[1]);
            else if (mmolMatch) moles = parseFloat(mmolMatch[1]) / 1000;

            if (reagents.length === 0) stepLimitingMoles = moles;

            reagents.push({
                name: name.trim(),
                mw: moles > 0 ? (g / moles).toFixed(3) : 0,
                moles: moles || 1.0,
                is_limiting: reagents.length === 0
            });
            csvContent += `${step_id},Reagent,"${name.trim().replace(/"/g, '""')}",${g},g,"MW: ${moles > 0 ? (g / moles).toFixed(2) : 'N/A'}"\n`;
        }

        let solventName = "Solvent";
        let molarity = 0.5;
        const sMatch = rxn.match(/\{S:([^}]+)\}/);
        if (sMatch) {
            solventName = sMatch[1];
            const searchArea = rxn.substring(Math.max(0, sMatch.index - 60), sMatch.index + 100);
            const volMatch = searchArea.match(/([\d\.]+)\s*(mL|L)/i);
            if (volMatch) {
                let liters = parseFloat(volMatch[1]);
                if (volMatch[2].toLowerCase() === 'ml') liters /= 1000;
                if (liters > 0 && stepLimitingMoles > 0) molarity = (stepLimitingMoles / liters).toFixed(4);
            }
            csvContent += `${step_id},Solvent,"${solventName.replace(/"/g, '""')}",${volMatch ? volMatch[1] : 0},${volMatch ? volMatch[2] : 'mL'},"Molarity: ${molarity}"\n`;
        }

        const yMatch = rxn.match(/\{Y:(\d+\.?\d*)\s*%?\}/);
        const pMatch = rxn.match(/\{P:([^}]+)\}/);
        const tMatch = rxn.match(/\{T:([^}]+)\}/);
        const hMatch = rxn.match(/\{H:([^}]+)\}/);

        steps.push({
            step_id: step_id,
            name: pMatch ? pMatch[1].trim() : `Step ${step_id}`,
            reagents: reagents,
            molarity: parseFloat(molarity),
            solvent_name: solventName,
            yield_percent: yMatch ? parseFloat(yMatch[1]) : 100,
            temperature: tMatch ? tMatch[1] : "RT",
            time: hMatch ? hMatch[1] : "N/A",
            procedure: rxn.trim()
        });
    });

    // Download JSON
    const jsonData = JSON.stringify({
        routeA: { target: 1, steps: steps },
        routeB: { target: 1, steps: [] }
    }, null, 2);
    triggerDownload(jsonData, 'project.json', 'application/json');

    // Small delay for second download
    setTimeout(() => {
        triggerDownload(csvContent, 'extraction.csv', 'text/csv');
    }, 500);
}
