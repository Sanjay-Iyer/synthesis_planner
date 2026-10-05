// Run with: node --test tests/test_hs6_frontend.cjs
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function runtime(script) {
    const elements = new Map();
    let downloaded;
    const context = vm.createContext({
        console, Blob,
        URL: { createObjectURL(blob) { downloaded = blob; return 'blob:test'; } },
        FileReader: class { readAsText(file) { this.onload({ target: { result: file.text } }); } },
        document: {
            addEventListener() {},
            getElementById(id) {
                if (!elements.has(id)) elements.set(id, {
                    value: '1', innerHTML: '', checked: false,
                    classList: { add() {}, remove() {} },
                    querySelector() { return { textContent: '' }; }
                });
                return elements.get(id);
            },
            createElement() { return { click() {} }; }
        },
        window: { location: { href: '' } },
        localStorage: { setItem(key, value) { context.saved = JSON.parse(value); } },
        setTimeout() {},
        alert(message) { throw new Error(message); }
    });
    const source = path.join(__dirname, '..', 'app', 'static', 'js', script);
    vm.runInContext(fs.readFileSync(source, 'utf8'), context);
    context.download = () => downloaded.text();
    return context;
}

test('risk CSV header aliases preserve code text and quoted reagent names', () => {
    for (const header of ['HS6', 'hs6', 'HS6_Code', 'HS_Code']) {
        const ctx = runtime('risk.js');
        const rows = [];
        ctx.addReagentInputRow = data => rows.push(data);
        ctx.loadCSV({ target: { files: [{ name: 'test.csv', text:
            `\uFEFFReagent_Name,${header}\n"oxides, catalyst",070951\nantiomy oxides,282580.0` }] } });
        assert.equal(rows[0].name, 'oxides, catalyst');
        assert.equal(rows[0].hs6, '070951');
        assert.equal(rows[1].hs6, '282580.0');
    }
});

test('Planner report CSV round-trips HS6 and still imports historical reports', async () => {
    const ctx = runtime('dashboard.js');
    const steps = [{ step_id: 1, name: 'reaction', product_mw: 100, molarity: 1,
        solvent_name: 'water', solvent_volume: 1, solvent_volume_unit: 'mL',
        solvent_bottle_l: 1, solvent_bottle_price: 1, yield_percent: 100,
        reagents: [{ name: 'antimony oxides', hs6: '070951', mw: 100,
            pkg_size: 1, pkg_price: 1, equivalents: 1, mass: 1, mass_unit: 'g', is_limiting: true }] }];
    ctx.collectStepData = side => side === 'vA' ? steps : [];
    vm.runInContext('lastAnalysis.vA = { steps: [] };', ctx);
    ctx.exportToCSV();
    const csv = await ctx.download();
    assert.ok(csv.includes('Reagent_Name,HS6,MW'));
    const restored = [];
    ctx.clearRouteUI = () => {};
    ctx.addStep = (side, step) => restored.push(step);
    ctx.loadFromCSV({ target: { files: [{ text: csv }] } });
    assert.equal(restored[0].reagents[0].hs6, '070951');
    assert.equal(restored[0].reagents[0].name, 'antimony oxides');
    assert.equal(restored[0].reagents[0].mw, 100);
    const legacy = csv.replace('Reagent_Name,HS6,MW', 'Reagent_Name,MW').replace(',"070951",', ',');
    restored.length = 0;
    ctx.loadFromCSV({ target: { files: [{ text: legacy }] } });
    assert.equal(restored[0].reagents[0].hs6, null);
    assert.equal(restored[0].reagents[0].mw, 100);
});

test('Planner hand-off keeps same-name different-HS6 and shared categories separate', async () => {
    for (const scaled of [false, true]) {
        const ctx = runtime('dashboard.js');
        const reagents = [
            { name: 'oxides', hs6: '282580', mass: 1, cost_per_g: 10 },
            { name: 'oxides', hs6: '282560', mass: 2, cost_per_g: 10 },
            { name: 'antiomy oxides', hs6: '282580', mass: 3, cost_per_g: 10 }
        ];
        ctx.collectStepData = side => side === 'vA' ? [{ reagents }] : [];
        ctx.getEstimate = async () => scaled ? { steps: [{ reagents: reagents.map(r => ({
            name: r.name, hs6: r.hs6, mass_g: r.mass * 10, item_cost: r.mass * 100
        })) }] } : null;
        await ctx.pushToRiskAudit();
        assert.equal(ctx.saved.reagents.length, 3);
        assert.equal(ctx.saved.reagents[0].hs6, '282580');
        assert.equal(ctx.saved.reagents[1].hs6, '282560');
        assert.equal(ctx.saved.reagents[2].name, 'antiomy oxides');
        assert.equal(ctx.saved.reagents[2].hs6, '282580');
        assert.equal(ctx.saved.reagents[0].routes.A.cost, scaled ? 100 : 10);
    }
});

test('risk report export has HS6 beside reagent and explicit trade status', async () => {
    const ctx = runtime('risk.js');
    vm.runInContext(`lastRiskResults = {reagents: [
        {name:'antiomy oxides', hs6:'282580', trade_status:'MATCHED', primary_origin:'China', primary_origin_share_pct:98, secondary_origin:'Belgium', secondary_origin_share_pct:2, provenance:{share_basis_label:'Listed WITS exporter quantity'}},
        {name:'unknown', hs6:null, trade_status:'HS6 MISSING'},
        {name:'bad', hs6:'ABC123', trade_status:'INVALID HS6'}
    ]};`, ctx);
    ctx.exportRiskCSV();
    const csv = await ctx.download();
    assert.ok(csv.includes('Reagent,HS6,Trade_Status,'));
    assert.ok(csv.includes('"antiomy oxides","282580","MATCHED"'));
    assert.ok(csv.includes('"unknown","UNKNOWN","HS6 MISSING"'));
    assert.ok(csv.includes('"bad","ABC123","INVALID HS6"'));
    assert.ok(csv.includes('Origin,Primary_Origin_Share_Pct,Secondary_Origin,Secondary_Origin_Share_Pct,Origin_Share_Basis'));
    assert.ok(csv.includes('"China","98","Belgium","2","Listed WITS exporter quantity"'));
});

test('origin labels show supplier percentages without inventing missing shares', () => {
    const ctx = runtime('risk.js');
    assert.equal(ctx.originShareLabel('China', 98), 'China — 98%');
    assert.equal(ctx.originShareLabel('Belgium', 4), 'Belgium — 4%');
    assert.equal(ctx.originShareLabel('Belgium', 0), 'Belgium — 0%');
    assert.equal(ctx.originShareLabel('Peru', null), 'Peru — share unavailable');
});

test('Auto-Lookup fills HS6-only names/origins and refreshes automatic values while preserving edits', async () => {
    const ctx = runtime('risk.js');
    function row(name, hs6) {
        const fields = Object.fromEntries([
            '.r-name', '.r-hs6', '.r-origin', '.r-secondary-origin', '.r-mass',
            '.r-cost', '.r-sub', '.r-cas', '.r-lead', '.r-haz', '.r-reg', '.r-route', '.r-trade-status'
        ].map(key => [key, { value: '', textContent: '', style: {} }]));
        fields['.r-name'].value = name;
        fields['.r-hs6'].value = hs6;
        return { fields, dataset: {}, querySelector: key => fields[key] };
    }
    const blank = row('', ''), active = row('', '282580');
    ctx.document.querySelectorAll = () => [blank, active];
    ctx.document.querySelector = () => ({ textContent: 'Auto-Lookup', disabled: false });
    let received;
    ctx.fetch = async (url, options) => {
        received = JSON.parse(options.body);
        return { ok: true, json: async () => [{
            primary: 'China', secondary: 'Belgium', hs6: '282580', trade_status: 'MATCHED', product_description: 'Antimony oxides'
        }] };
    };
    await ctx.autoLookupOrigins();
    assert.equal(received.reagents.length, 1);
    assert.equal(received.reagents[0].name, '');
    assert.equal(received.reagents[0].hs6, '282580');
    assert.equal(blank.fields['.r-origin'].value, '');
    assert.equal(blank.fields['.r-name'].value, '');
    assert.equal(active.fields['.r-name'].value, 'Antimony oxides');
    assert.equal(ctx.collectReagentInputs()[0].name, 'Antimony oxides');
    assert.equal(active.fields['.r-origin'].value, 'China');
    assert.equal(active.fields['.r-secondary-origin'].value, 'Belgium');
    assert.equal(active.fields['.r-trade-status'].textContent, 'MATCHED');
    ctx.fetch = async () => ({ ok: true, json: async () => [{
        primary: 'France', secondary: 'USA', trade_status: 'MATCHED', product_description: 'Germanium oxides'
    }] });
    active.fields['.r-hs6'].value = '282560';
    await ctx.autoLookupOrigins();
    assert.equal(active.fields['.r-origin'].value, 'France');
    assert.equal(active.fields['.r-name'].value, 'Germanium oxides');
    active.fields['.r-origin'].value = 'Germany'; // Preserve an intentional user override.
    active.fields['.r-name'].value = 'My catalyst';
    await ctx.autoLookupOrigins();
    assert.equal(active.fields['.r-origin'].value, 'Germany');
    assert.equal(active.fields['.r-name'].value, 'My catalyst');
    ctx.fetch = async () => ({ ok: true, json: async () => [{
        primary: 'Unknown', secondary: 'Unknown', trade_status: 'NO WITS DATA', product_description: null
    }] });
    await ctx.autoLookupOrigins();
    assert.equal(active.fields['.r-name'].value, 'My catalyst');
    active.fields['.r-name'].value = '   ';
    await ctx.autoLookupOrigins();
    assert.equal(active.fields['.r-name'].value, '');
    active.fields['.r-name'].value = active.dataset.autoName = 'Old category';
    await ctx.autoLookupOrigins();
    assert.equal(active.fields['.r-name'].value, '');
    // Names entered before the first lookup also stay intact.
    active.fields['.r-name'].value = 'Antimony trioxide catalyst';
    ctx.fetch = async () => ({ ok: true, json: async () => [{
        primary: 'China', secondary: 'Belgium', trade_status: 'MATCHED', product_description: 'Antimony oxides'
    }] });
    await ctx.autoLookupOrigins();
    assert.equal(active.fields['.r-name'].value, 'Antimony trioxide catalyst');
});
