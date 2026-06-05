# Export & Import Features

The Synthesis Planner has a comprehensive set of export and import tools for saving, sharing, and re-loading your work.

---

## Toolbar Buttons

The toolbar at the top of the dashboard has four main buttons:

| Button | Label | Action |
|---|---|---|
| ⚡ | Run Analysis | Triggers backend cost estimation and yield audit (see [05_run_analysis.md](05_run_analysis.md)) |
| 📊 | Export Report | Downloads a CSV report + ZIP of chart PNGs |
| 📥 | Load Report | Uploads a previously exported CSV to restore the dashboard |
| 🌍 | Analyze Risk | Pushes reagent data to the Risk Audit page |

---

## 📊 Export Report — Detailed Breakdown

Clicking **Export Report** triggers **two simultaneous downloads**:

### 1. procurement_report.csv

A multi-section CSV file with clearly labeled headers:

**Section 1: Route Steps Details**
```
Route, Step, Name, Molarity, Solvent, Reagent, Mass_g, Cost
vA,    1,    "Amide Coupling", 0.5, "THF", "Aniline", 1234.56, 45.67
```
One row per reagent per step per route. Contains the scaled-up (production-scale) masses and costs from the engine output.

**Section 2: Yield Sensitivity Audit**
```
Route, Step, Name, Savings per 1% Yield Increase ($)
vA,    1,    "Amide Coupling", 12.34
```
Only rows with sensitivity > 0 are included.

**Section 3: Comprehensive Comparison Summary**
```
Metric, Route A, Route B
Target Goal, 1 kg, 1 kg
Budget / Total Cost, $567, $489
Cost per kg, $567.00, $489.00
E-Factor, 12.3, 8.7
```

**Section 4: Raw Input Data for Hydration**
This is the most important section — it contains the **complete raw input data** from the dashboard forms with 25 columns:
```
Route, Step, Name, Product_MW, Temperature, Time, Molarity, Solvent_Name,
Solvent_Volume, Solvent_Volume_Unit, Solvent_Bottle_L, Solvent_Bottle_Price,
Yield_Percent, Procedure, Depends_On, Reagent_Name, MW, Pkg_Size, Pkg_Price,
Equivalents, Mass, Mass_Unit, Is_Limiting, Solvent_Bottle_Amount, Solvent_Bottle_Unit
```
This section allows the CSV to be **re-imported** to fully reconstruct the dashboard (see Load Report below). Procedure text with commas or quotes is properly escaped.

### 2. synthesis_plots.zip

A ZIP file (built client-side with JSZip) containing PNG screenshots of 5 chart canvases:
- `route_efficiency.png` — Plot 1
- `step_wise_cost.png` — Plot 2
- `optimization_bottleneck.png` — Plot 4
- `yield_cascade_waterfall.png` — Plot 5
- `top_cost_drivers.png` — Plot 6

Note: The three small Route Comparison sub-charts (Plot 3a/b/c) are not included in the ZIP.

---

## 📥 Load Report — CSV Re-Hydration

Clicking **Load Report** opens a file picker for `.csv` files. The parser:

1. Reads the entire file as text
2. Scans for `--- SECTION 4` header
3. If found, uses a **full CSV parser** (handles quoted fields, escaped quotes, commas within quotes) to parse each data row
4. Groups rows by route (vA/vB) and step_id, reconstructing step objects with all fields:
   - Step metadata (name, product_mw, temperature, time, molarity, yield, procedure, depends_on)
   - Solvent info (name, volume, volume_unit, bottle_amount, bottle_unit, bottle_price)
   - Reagent list (name, mw, pkg_size, pkg_price, equivalents, mass, mass_unit, is_limiting)
5. Clears both route columns
6. Rebuilds all step cards via `addStep(side, data)`
7. Auto-runs analysis after 150ms

**Fallback**: If Section 4 is not found (e.g., an older or manually created CSV), the parser falls back to Section 1, extracting basic reagent data (name, mass, cost) with limited fidelity.

---

## 💾 Save Route / 📂 Load Route (JSON)

Each route column has its own Save and Load buttons in the header.

### Save
- Calls `collectStepData(side)` to gather all form values
- Wraps in: `{ routeA: { target: "1", steps: [...] } }` (or `routeB`)
- Downloads as a `.json` file with the custom filename from the "Save As" field
- Everything is preserved: reagent names, MWs, equivalents, masses with units, bottle sizes/prices with units, solvent details, yield, temperature, time, procedure, dependencies

### Load
- Accepts a `.json` file
- Clears the target column
- Reads steps from `routeA.steps` or `routeB.steps` (whichever exists)
- Rebuilds all step cards with full data population
- Stoichiometry auto-calculates after a 50ms delay

---

## 🌍 Analyze Risk — Dashboard-to-Risk Bridge

Clicking **Analyze Risk** on the dashboard:

1. Collects all reagents from both Route A and Route B
2. **Deduplicates by name/CAS** — if the same reagent appears in multiple steps, masses and costs are summed
3. Filters out reagents with no name
4. Stores the consolidated reagent list in `localStorage` as `pendingRiskData`
5. Navigates to `/risk.html`

On the Risk Audit page:
1. `DOMContentLoaded` handler checks for `pendingRiskData` in localStorage
2. If found, clears default rows, creates a row for each reagent with name, CAS, mass, and cost pre-populated
3. Auto-triggers `runRiskAssessment()` immediately
4. Clears the localStorage entry

---

## Scale Up (In Results Section)

After running analysis, each route's procurement section has a **Scale Up** control:

- **Input**: A numeric multiplier (default: 2)
- **Button**: "Scale Up" (blue for Route A, green for Route B)
- **Action**: Multiplies ALL reagent masses and solvent volumes by the multiplier, recalculates costs, and appends a new procurement card below the original
- **Stacking**: Multiple scale-ups can be added (e.g., 2×, then 5×, then 10×)
- **Deletion**: Each scaled section has an × button to remove it individually
- **Appearance**: Scaled sections have a tinted background (blue tint for A, green tint for B) and a dashed border to visually distinguish them from the original

---

## Match Route (Product Matching)

On each route's final step, a **"Match Route B"** (or A) button enables fair comparison:

1. Reads the other route's final "Produced (g)" value as the target
2. Back-calculates the required limiting reagent mass:
   ```
   new_mass = (target_g × lim_MW × lim_Eq) / (product_MW × (yield / 100))
   ```
3. Sets the limiting reagent's mass field
4. Triggers stoichiometry recalculation for all other reagents in that step
5. Re-runs full analysis after 150ms

This ensures both routes are compared at the same production output, making the cost comparison meaningful.
