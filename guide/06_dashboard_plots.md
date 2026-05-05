# Dashboard Plots — All 9 Visualizations

All charts are rendered with [Chart.js](https://www.chartjs.org/) on dark backgrounds (`#2d3436`). They are created/destroyed on every Run Analysis call to prevent canvas conflicts.

---

## Plot 1: Route Efficiency Dashboard (Cost vs. E-Factor)

- **Chart type**: Grouped bar chart with dual y-axes
- **X-axis**: Route A, Route B
- **Left Y-axis**: Total Cost ($) — blue bars
- **Right Y-axis**: E-Factor — orange bars
- **What it shows**: A side-by-side comparison of the two most important route metrics: cost and environmental waste. Each route gets two bars.
- **What question it answers**: "Which route is cheaper AND greener?" If one route has both a lower blue bar and a lower orange bar, it is strictly superior. If the bars trade off (one route is cheaper but wastier), this chart highlights the tradeoff for decision-making.

---

## Plot 2: Step-wise Cost Breakdown (Where the Money Goes)

- **Chart type**: Stacked bar chart
- **X-axis**: Route A, Route B
- **Y-axis**: Cost ($), stacked
- **Segments**: One colored segment per synthesis step. Each segment's legend label includes the step name AND the name of the most expensive reagent in that step (the "dominant cost driver").
- **Colors**: Cycling palette of 7 colors (#0984e3, #00cec9, #6c5ce7, #fab1a0, #fdcb6e, #e17055, #2ecc71)
- **What it shows**: How the total route cost is distributed across synthesis steps.
- **What question it answers**: "Which steps consume the most budget?" and "Is cost concentrated in one step or spread evenly?" If one segment dominates the bar, that step (and its labeled reagent) is the primary cost driver worth optimizing.

---

## Plot 3: Overall Route Comparison (3 Sub-Charts)

Three simple grouped bar charts arranged in a 3-column grid:

### 3a — Total Cost
- **Chart type**: Bar chart
- **Bars**: Route A (blue), Route B (green)
- **Y-axis**: Total Cost ($)
- **What it answers**: "Which route costs less overall in absolute dollars?"

### 3b — Cost per kg
- **Chart type**: Bar chart
- **Bars**: Route A (blue), Route B (green)
- **Y-axis**: Cost per kg ($)
- **What it answers**: "Which route is more cost-efficient per unit of product?" This is the normalized metric — it accounts for different target masses between routes.

### 3c — E-Factor
- **Chart type**: Bar chart
- **Bars**: Route A (blue), Route B (green)
- **Y-axis**: E-Factor
- **What it answers**: "Which route generates less waste per unit product?" Lower E-factor = greener chemistry. Typical reference values: bulk chemicals (1–5), fine chemicals (5–50), pharmaceuticals (25–100+).

---

## Plot 4: Optimization Bottleneck (Sensitivity Analysis)

- **Chart type**: Horizontal bar chart (tornado-style)
- **Y-axis (labels)**: Every step from both routes, formatted as two lines: "Route A - Step 1" and "Step Name". Sorted by sensitivity value (highest at top).
- **X-axis**: Dollars saved per 1% yield increase
- **Colors**: Blue (#0984e3) for Route A steps, green (#27ae60) for Route B steps
- **Data source**: The `/api/synthesis/audit` endpoint
- **What it shows**: The cost sensitivity of each step to yield improvements, ranked from most impactful to least.
- **What question it answers**: "Where should I focus R&D effort to reduce costs?" The step at the top of this chart is the single highest-leverage optimization target. Even a small yield improvement there will have the largest cost reduction.

---

## Plot 5: Yield Cascade Waterfall (Theoretical → Actual Mass)

- **Chart type**: Floating bar chart (waterfall style)
- **X-axis labels**: "A Start", "A S1 → waste", "A S2 → waste", ..., "A Final", "B Start", "B S1 → waste", ..., "B Final"
- **Y-axis**: Mass Percentage (%) starting at 100%
- **Colors**:
  - Start bars: blue (#0984e3 for A, #27ae60 for B)
  - Waste bars: red (#ff7675)
  - Final bars: teal (#00cec9 for A, #2ecc71 for B)
- **What it shows**: Starting from 100% theoretical mass, each step's yield loss is shown as a red bar dropping down. The "Final" bar shows what percentage of mass actually makes it through. Both routes are shown sequentially.
- **What question it answers**: "How do yield losses compound across my synthesis?" Three steps at 80% yield each leave only 51.2% of theoretical mass — this chart makes that multiplicative compounding viscerally visible. A route with fewer steps or higher yields will have a taller final bar.

---

## Plot 6: Top Cost Drivers (Reagents & Solvents)

- **Chart type**: Horizontal bar chart
- **Y-axis (labels)**: Top 10 most expensive materials across both routes, ranked by cost
- **X-axis**: Total Cost ($)
- **Color**: Purple (#6c5ce7)
- **Data**: Aggregates all reagent `item_cost` values and solvent costs from both Route A and Route B. Reagents with the same name are summed together. Solvents are labeled as "SolventName (Solvent)".
- **What it shows**: The individual materials (reagents and solvents) that contribute the most to overall cost across your entire synthesis campaign.
- **What question it answers**: "Which single chemicals are eating the most budget?" This chart helps prioritize supplier negotiations, identify candidates for cheaper alternatives, or flag materials worth recovering/recycling.
