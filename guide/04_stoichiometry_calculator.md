# Stoichiometry Auto-Calculator

The stoichiometry calculator is a **client-side real-time system** that fires on every keystroke in the MW, Equivalents, or Mass fields of any reagent row. It automatically computes and fills in the masses of all reagents based on the limiting reagent, so you never have to do manual stoichiometry math.

---

## How It Works

### Step 1: Identify Base Moles

The calculator first determines the `baseMoles` — the fundamental molar quantity that all other reagents scale from.

**If triggered by typing a mass** (the `isMass` flag is true):
```
baseMoles = typed_mass_in_grams / reagent_MW / reagent_Eq
```
This back-calculates base moles from whatever reagent you just typed a mass into.

**If triggered by any other change** (MW or Eq change):
The calculator finds the reagent marked as **Limiting** (checkbox checked) and computes:
```
baseMoles = limiting_mass_in_grams / limiting_MW / limiting_Eq
```

If no limiting reagent is set or the limiting reagent has no mass, `baseMoles` is 0 and no calculation occurs.

### Step 2: Unit Conversion

All mass values are internally converted to grams before calculation:
- If unit is **mg**: `mass_in_grams = mass / 1000`
- If unit is **g**: `mass_in_grams = mass` (no conversion)
- If unit is **kg**: `mass_in_grams = mass × 1000`

### Step 3: Calculate All Other Reagents

For every reagent row *except* the one that triggered the calculation:
```
mass_in_grams = baseMoles × reagent_Eq × reagent_MW
```

The result is then converted back to the reagent's displayed unit:
- If unit is **mg**: `displayed = mass_in_grams × 1000`
- If unit is **g**: `displayed = mass_in_grams`
- If unit is **kg**: `displayed = mass_in_grams / 1000`

The value is written to 3 decimal places.

### Step 4: Update Product Produced

After recalculating reagent masses, the calculator also updates the **Produced (g)** field:
```
baseMoles = limiting_mass_in_grams / limiting_MW / limiting_Eq
theoretical_mass = baseMoles × product_MW
actual_mass = theoretical_mass × (yield_percent / 100)
```

---

## Bidirectional Calculation

The system supports **two directions of calculation**:

### Forward (Limiting → Others)
Set the limiting reagent's mass, and all other reagents' masses fill in automatically based on their equivalents and MWs. This is the typical workflow: you know how much limiting reagent you have, and the calculator tells you how much of everything else to weigh out.

### Reverse (Any Mass → Back-Calculate)
Type a mass into *any* reagent (even a non-limiting one), and the system back-calculates `baseMoles` from that reagent's values, then fills in all *other* reagents. This is useful when you have a fixed amount of an expensive reagent and want to scale everything else to match.

---

## Limiting Reagent Enforcement

- Only **one reagent per step** can be marked as limiting
- Checking a limiting checkbox automatically unchecks all other limiting checkboxes in the same step
- After any limiting checkbox change, the stoichiometry is immediately recalculated

---

## Trigger Points

The calculator fires on:
- `oninput` on any **MW** field → recalculates from limiting reagent
- `oninput` on any **Eq** field → recalculates from limiting reagent
- `oninput` on any **Mass** field → back-calculates baseMoles from this mass, updates others
- `onchange` on any **Mass Unit** dropdown → recalculates with new unit conversion
- `onchange` on any **Limiting?** checkbox → recalculates from new limiting reagent
- `onclick` on any **Delete Reagent** button → recalculates remaining reagents
- `oninput` on **Product MW** → recalculates Produced (g)
- `oninput` on **Yield %** → recalculates Produced (g)

---

## Match Route Feature

The **"Match Route B"** button (on Route A's final step, and vice versa) uses the stoichiometry system to equalize output:

1. Reads the other route's final step "Produced (g)" value as the target
2. Back-calculates what the current route's limiting reagent mass needs to be:
   ```
   new_lim_mass_g = (target_grams × lim_MW × lim_Eq) / (product_MW × (yield / 100))
   ```
3. Sets the limiting reagent's mass field to this value
4. Triggers full stoichiometry recalculation for all other reagents
5. Re-runs analysis after 150ms

This ensures both routes produce the same amount of final product for a fair cost comparison.
