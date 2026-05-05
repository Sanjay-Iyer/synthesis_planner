# Step Card — Every Input Field Explained

Each synthesis step is rendered as a white card with a blue left border. A step card contains the following sections from top to bottom:

---

## Header Row

| Field | Type | Description |
|---|---|---|
| **Step N** | Label | Auto-incrementing step number (1, 2, 3, ...). Used as `step_id` in the backend engine and in chart labels. |
| **Step Name** | Text input | Free-text name for the reaction (e.g. "Amide Coupling", "Boc Deprotection", "Recrystallization"). Appears in all charts, audit tables, and export reports. |
| **Product MW** | Number input | Molecular weight of *this step's product* in g/mol. Critical for computing grams of product produced. If left at 0, the "Produced (g)" field stays blank and the waterfall chart skips this step's mass calculation. |
| **× (Delete)** | Button | Removes the entire step card from the route. Located in the top-right corner. |

---

## Conditions Row (Peach Background)

| Field | Type | Default | Description |
|---|---|---|---|
| **Temp** | Text input | "RT" | Reaction temperature as free text (e.g. "RT", "0°C", "80°C", "reflux"). Stored in JSON/CSV exports for lab notebook purposes. Not used in any calculation. |
| **Time** | Text input | "N/A" | Reaction duration as free text (e.g. "2h", "overnight", "30 min"). Also for record-keeping only — not used in calculations. |
| **Feeds** | Checkboxes | Unchecked | Only shown for Step 2+. One checkbox per preceding step (S1, S2, etc.). See the "Step Dependencies" section in [02_route_input_system.md](02_route_input_system.md). |

---

## Reagent Rows

Each step starts with one reagent row and can have unlimited rows added via **"+ Manual Reagent"** or **"+ Add Molecule"** (SMILES lookup). Each reagent row has two visual lines:

### Line 1 — Chemistry Fields

| Field | Type | Description |
|---|---|---|
| **Reagent Name** | Text input | Name of the chemical (e.g. "Aniline", "NaOH", "Pd(PPh3)4"). Can be typed manually or auto-populated by the SMILES/SELFIES/InChI lookup. |
| **MW** | Number input | Molecular weight in g/mol. Auto-populated from RDKit or PubChem when using molecule lookup. Used for stoichiometric mass calculation: `mass = baseMoles × Eq × MW`. |
| **Equiv (Eq)** | Number input | Molar equivalents relative to the base moles. The limiting reagent is typically 1.0. Excess reagents have values like 1.2, 2.0, 3.0, etc. The stoichiometry calculator uses this to compute each reagent's mass. |
| **Mass** | Number input + unit dropdown | Lab-scale mass with selectable unit (**g**, **mg**, or **kg**). This field is **bidirectionally linked** to the stoichiometry calculator (see below). The unit dropdown triggers recalculation on change. |
| **Limiting?** | Checkbox | Marks this reagent as the limiting reagent. **Only one reagent per step can be limiting.** Checking a box auto-unchecks any other limiting checkbox in the same step. The limiting reagent defines the base mole count for all stoichiometry calculations. |
| **× (Delete)** | Button | Removes this reagent row. Triggers stoichiometry recalculation for the remaining reagents. |

### Line 2 — Purchasing Fields (Red Labels)

| Field | Type | Description |
|---|---|---|
| **Bottle Amount** | Number input + unit dropdown | How many grams (or mg/kg) come in one supplier bottle. The unit dropdown supports g, mg, kg. Used to compute `cost_per_g = bottle_price / bottle_amount_in_grams`. |
| **Bottle Cost ($)** | Number input | The dollar price of one bottle from the supplier. Combined with Bottle Amount to derive per-gram cost for the scale-up engine. |

---

## Molecule Lookup Bar

Below the reagent rows, each step has a combined input + button:

| Element | Description |
|---|---|
| **Text input** | Accepts SMILES (e.g. `c1ccccc1`), SELFIES (e.g. `[C][=C][C][=C][C][=C][Ring1][Branch1]`), InChI (e.g. `InChI=1S/C6H6/c1-2-4-6-5-3-1/h1-6H`), or InChIKey (e.g. `UHOVQNZJYSORNB-UHFFFAOYSA-N`) |
| **"+ Add Molecule" button** | Fires two parallel API calls to resolve the identifier into a name and MW, then creates a new reagent row (or fills the first empty row) with the results |

### How Molecule Lookup Works

1. **Name resolution** (`POST /api/synthesis/molecule-name`):
   - Detects input type by pattern: InChIKey = `^[A-Z]{14}-[A-Z]{10}-[A-Z]$`, InChI = starts with `InChI=`, SELFIES = contains `[` and `]`, otherwise assumed SMILES
   - For InChI: converts to SMILES via RDKit first (if available), then queries PubChem
   - For SELFIES: decodes to SMILES via the `selfies` library, then queries PubChem
   - Queries PubChem PUG REST `/compound/{namespace}/{query}/synonyms/JSON` and returns the first synonym
   - Fallback: tries CID lookup, returns "PubChem CID NNNNN" or "Unknown Molecule"

2. **MW calculation** (`POST /api/synthesis/molecular-weight`):
   - **Priority 1**: RDKit `Descriptors.MolWt()` — exact monoisotopic-ish weight from SMILES
   - **Priority 2**: PubChem property lookup (for InChI/InChIKey inputs)
   - **Priority 3**: Regex formula parser — matches patterns like `C6H12O6` against a built-in periodic table (18 elements) and sums atomic weights
   - Returns 0.0 with method "Unrecognized Input" if all methods fail

3. **Display**: A collapsible log below the input shows all resolved molecules as `Name: SMILES_string`.

---

## Solvent Section (Gray Background)

| Field | Type | Default | Description |
|---|---|---|---|
| **Solvent Name** | Text input | "Solvent" | Name of the reaction solvent (e.g. "THF", "DCM", "Water", "EtOAc"). |
| **Volume** | Number input + unit dropdown | Empty, L | Amount of solvent used. Unit dropdown: **L** or **mL**. The engine converts to liters internally. Used to compute molarity: `molarity = limiting_reagent_moles / volume_in_L`. |
| **Bottle Amount** | Number input + unit dropdown | 1, L | Supplier bottle size. Unit dropdown: **L** or **mL**. Converted to liters for price-per-liter calculation. |
| **Bottle Cost ($)** | Number input | 0 | Price per supplier bottle. The engine computes `price_per_L = bottle_price / bottle_amount_in_L`. |

---

## Product Output Section (Blue Background)

| Field | Type | Description |
|---|---|---|
| **Yield %** | Number input (default: 100) | The percent yield for this step. Drives the mole cascade: `product_moles = input_moles × (yield / 100)`. Also drives the E-factor calculation and the waterfall chart. |
| **Produced (g)** | Number input (readonly, disabled) | Auto-calculated field showing actual grams of product: `(lim_mass / lim_MW / lim_Eq) × product_MW × (yield / 100)`. Updates whenever MW, mass, yield, or Product MW changes. |
| **Match Route A/B** | Button | Auto-adjusts the limiting reagent mass of this step so that the produced grams matches the other route's final step output. Enables fair cost comparisons. |

---

## Procedure Notes

| Field | Type | Description |
|---|---|---|
| **Textarea** | Multi-line text | Free-text area for experimental notes (e.g. "Add dropwise at 0°C, stir 2h, quench with sat. NH₄Cl, extract 3×50 mL EtOAc"). Preserved in JSON saves, CSV exports, and displayed in the procurement report. Height: 70px, full width. |
