# Route Input System

## Dual-Route Layout

The Synthesis Planner dashboard (`/dashboard.html`) presents **two side-by-side route columns — Route A and Route B** — on a gray background. Each route is fully independent and can hold any number of sequential synthesis steps. This dual-route layout exists so you can directly compare two different synthetic pathways to the same target molecule (e.g., comparing a palladium-catalyzed coupling vs. a classical condensation route to the same product).

The two columns are rendered in a CSS `grid-2` layout that collapses to a single column on screens narrower than 768px.

---

## Route-Level Controls

Each route column has a header with the following controls:

### Target kg
- **What it is**: A numeric input specifying the desired final production mass in kilograms.
- **Default**: 1.0 kg
- **How it works**: This is the "goal" that drives all scale-up math. The backend engine works backward from the final step: it calculates how many moles of final product are needed, then traces backward through every step (accounting for yield losses) to determine how much of every reagent is needed. Changing this value and re-running analysis instantly rescales the entire route.
- **Live update**: Typing a new value fires `runAnalysis()` on input, so results update in real time.

### Save As (Filename)
- **What it is**: A text input for a custom filename for JSON export.
- **Default**: Auto-generated as `YYYYMMDD_RouteA` (or `RouteB`) on page load.
- **How it works**: When you click 💾 Save, the route's full data is serialized to JSON and downloaded with this filename (`.json` is appended if missing).

### Load (📂)
- **What it is**: A file picker button that accepts a `.json` file.
- **How it works**: Reads a previously saved route JSON file, clears the current column, and reconstructs all step cards with every field (reagent names, MWs, equivalents, masses, solvent info, yields, procedures, and step dependencies) fully populated.
- **File format**: Expects a JSON object with either a `routeA` or `routeB` key containing `{ target, steps: [...] }`.

### Save (💾)
- **What it is**: A button that exports the current route to a JSON file.
- **How it works**: Calls `collectStepData(side)` to gather all current form values, wraps them in a JSON object keyed by `routeA` or `routeB`, and triggers a browser download with the custom filename.
- **What's saved**: Every field — step name, product MW, temperature, time, all reagent details (name, MW, eq, mass, mass unit, bottle size, bottle unit, bottle price, limiting flag), solvent (name, volume, volume unit, bottle amount, bottle unit, bottle price), yield %, procedure notes, and `depends_on` array.

### Clear (🗑️)
- **What it is**: A button that wipes all steps from the route column.
- **How it works**: Shows a confirmation dialog, then empties the step container and resets the step counter to 0.

### + Add Manual Step
- **What it is**: A full-width button at the top of the route column.
- **How it works**: Appends a new blank step card to the bottom of the route. The step is assigned an auto-incrementing ID (1, 2, 3, ...). The new card comes with one blank reagent row and default solvent fields.

---

## Step Dependencies (Feeds / Depends On)

When a step has `step_id > 1`, checkboxes appear in the conditions row for each preceding step (labeled S1, S2, etc.).

- **Purpose**: Checking "S1" means this step uses the product from Step 1 as its starting material. This creates the **mole flow chain** in the backend engine.
- **Convergent syntheses**: You can check multiple dependencies (e.g., S1 and S2) for a convergent step that combines intermediates from two parallel branches.
- **No dependencies**: If a step has no boxes checked (e.g., the first step), the engine uses the limiting reagent's moles as the anchor.
- **How the engine uses it**: During Pass 1 (mole flow), the engine sums the product moles from all `depends_on` steps to determine the input moles for the current step. The output moles are then `input_moles × (yield / 100)`.

---

## Loading Routes from Files

### JSON Load
Each route has its own file input. Loading a JSON file into Route A clears Route A and reconstructs all steps from the saved data. You can load different JSON files into Route A and Route B simultaneously for comparison.

### CSV Load (Load Report)
The toolbar has a **📥 Load Report** button that accepts a CSV file (typically one previously exported via **📊 Export Report**). The parser:
1. Looks for `--- SECTION 4` header to find the raw input data section
2. Parses each row using a full CSV parser that handles quoted fields and escaped quotes
3. Groups rows by route (vA/vB) and step_id
4. Clears both route columns and reconstructs all step cards
5. Auto-runs analysis after a 150ms delay

If Section 4 is not found (older CSV format), it falls back to parsing Section 1 for basic reagent data.
