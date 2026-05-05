# Run Analysis — Backend Engines

Clicking **⚡ Run Analysis** on the toolbar triggers two backend API calls per route (up to four total). The frontend collects all step/reagent data from the form, sends it to the server, and renders the results.

---

## Cost Estimation Engine

**Endpoint**: `POST /api/synthesis/estimate`

**Input**: A `SynthesisProject` object containing:
- `steps`: Array of `SynthesisStep` objects (each with reagents, solvent info, yield, dependencies)
- `target_mass_kg`: The desired production mass (from the "Target kg" input)

### Algorithm — Two-Pass Scale-Up

**Pass 1 — Mole Flow (Determine unit-scale throughput)**

The engine iterates steps in `step_id` order:

```python
for step in sorted_steps:
    # Sum product moles from all upstream steps this step depends on
    input_moles = sum(product_moles[dep_id] for dep_id in step.depends_on)
    
    # If no dependencies, use the limiting reagent's moles as anchor
    if input_moles == 0:
        anchor = limiting_reagent.moles  # (equivalents value from the form)
    else:
        anchor = input_moles
    
    start_moles[step.step_id] = anchor
    product_moles[step.step_id] = anchor × (step.yield_percent / 100)
```

This builds a mole-flow map from the first step to the last step, accounting for yield losses at each stage.

**Scale Factor Calculation**

```python
final_step = last step in sorted order
unit_final_grams = product_moles[final_step.id] × final_step.product_mw
scale_factor = (target_mass_kg × 1000) / unit_final_grams
```

The scale factor is a single multiplier that converts lab-scale quantities to production-scale.

**Pass 2 — Scaled Costs (Apply scale factor to everything)**

For each step:
```python
scaled_anchor_moles = start_moles[step.id] × scale_factor

for reagent in step.reagents:
    actual_moles = reagent.equivalents × scaled_anchor_moles
    mass_grams = actual_moles × reagent.mw
    cost = mass_grams × reagent.cost_per_gram
    total_input_mass += mass_grams

# Solvent
solvent_volume_liters = scaled_anchor_moles / step.molarity
solvent_cost = solvent_volume_liters × step.solvent_price_per_liter
total_input_mass += solvent_volume_liters × solvent_density × 1000
```

**E-Factor Calculation**

```python
e_factor = (total_input_mass_grams - target_mass_grams) / target_mass_grams
```

E-factor measures waste: a value of 5 means 5 kg of waste per 1 kg of product. Lower is greener. Typical values: bulk chemicals (1–5), fine chemicals (5–50), pharmaceuticals (25–100+).

### Output

```json
{
  "steps": [
    {
      "step_id": 1,
      "name": "Amide Coupling",
      "reagents": [{"name": "Aniline", "mass_g": 1234.56, "item_cost": 45.67}, ...],
      "solvent_name": "THF",
      "solvent_l": 12.5,
      "solvent_cost": 37.50,
      "step_total": 234.56,
      "temperature": "RT",
      "time": "2h",
      "procedure": "..."
    }
  ],
  "total_cost": 567.89,
  "cost_per_kg": 567.89,
  "e_factor": 12.3
}
```

---

## Yield Sensitivity Audit Engine

**Endpoint**: `POST /api/synthesis/audit`

**Input**: Same `SynthesisProject` object as the estimate endpoint.

### Algorithm — One-at-a-Time Simulation

1. Run the baseline cost estimate (with actual yields)
2. For each step `i`:
   - Create a deep copy of the project
   - Set step `i`'s yield to 100%
   - Re-run the cost estimate
   - Compute sensitivity:
     ```python
     sensitivity = (baseline_cost_per_kg - simulated_cost_per_kg) / (100 - step_i_actual_yield)
     ```
   - This gives **dollars saved per 1% yield improvement** at that step

3. Compute overall risk score as the average sensitivity across all steps

### What This Tells You

- **High sensitivity** = this step is a bottleneck. A small yield improvement here has a large cost impact.
- **Low sensitivity** = this step's yield barely affects cost. Focus R&D effort elsewhere.
- The step with the highest sensitivity is the single best optimization target in your entire route.

### Output

```json
{
  "audit": [
    {"step_id": 1, "name": "Amide Coupling", "sensitivity": 12.34},
    {"step_id": 2, "name": "Deprotection", "sensitivity": 3.21}
  ],
  "risk_score": 7.78
}
```

---

## Frontend Output Sections

After both engines return, the frontend renders:

### Section 1: Route Procurement (Side-by-Side)
Two dark-themed columns showing every step's breakdown:
- Step name and cost subtotal
- Product yield % and amount produced (g)
- Procedure notes (pre-formatted text)
- Reagent table: Name | Amount Used | Cost
- Solvent row: Name | Volume | Cost
- **Scale Up** control: enter a multiplier (e.g. 2×, 5×, 10×) and click to append a scaled procurement table below. Multiple scale-ups stack vertically and each can be individually deleted with an × button.

### Section 2: Yield Sensitivity Audit
One card per route (if that route has steps), showing a table:
- Step | Sensitivity ($/1% yield increase)
- Header: "Cost saved per 1% yield increase"

### Section 3: Comprehensive Comparison Summary
A table with rows: Target Goal (kg), Budget/Total Cost ($), Cost per kg ($), E-Factor — columns for Route A and Route B.
