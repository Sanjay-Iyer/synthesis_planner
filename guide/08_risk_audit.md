# Risk Audit Tool — Detailed Guide

The Risk Audit module (`/risk.html`) performs multi-dimensional geographic supply chain risk assessment on your reagents. It can be used standalone or fed automatically from the Synthesis Planner via the "🌍 Analyze Risk" button.

---

## Input System

### Manual Entry

The input panel presents a grid of rows (3 empty rows by default). Each row has:

| Field | Description | Required? |
|---|---|---|
| **Reagent Name** | Chemical name (e.g. "CuCl2", "Platinum on Carbon"). Rows without a name are skipped during assessment. | Yes |
| **CAS Number** | CAS registry number (e.g. "7447-39-4"). As you type, a colored status dot appears on the right side of the input: 🟢 **green** = CAS found in the server's mapping database (origin auto-populated), 🟡 **yellow** = CAS not recognized (will use defaults), ⚪ **gray** = no CAS entered. | No |
| **Primary Origin** | Country of origin (e.g. "China", "Germany", "USA"). Auto-filled from CAS lookup if available, or entered manually. If left blank and CAS is unknown, the engine defaults to "Unknown" which triggers an opacity risk multiplier. | No |
| **Mass (g)** | Total mass of this reagent being used. Contributes to the exposure multiplier in the risk formula. | No (defaults to 0) |
| **Cost ($)** | Total cost. Also contributes to the exposure multiplier. | No (defaults to 0) |

### Advanced Mode

Toggling the **"Advanced Mode"** checkbox reveals four additional columns:

| Field | Range | Default | Description |
|---|---|---|---|
| **Lead Time (days)** | Any positive integer | 14 | Expected supplier delivery time. A lead time of 30+ days = maximum lead time risk score. Used in the operational risk component. |
| **Hazard Score** | 1–10 | 5 | Toxicity and handling difficulty rating. 10 = extremely hazardous. Contributes 40% weight to the regulatory risk component. |
| **Regulatory Score** | 1–10 | 5 | EPA/TSCA/export control exposure rating. 10 = actively banned or under review. Contributes 60% weight to the regulatory risk component. Auto-boosted to 10 for flagged chemicals. |
| **Substitutability** | 1–10 | 5 | How difficult this reagent is to replace. 10 = no viable alternatives exist. Drives the entire economic risk component. |

### CSV Upload

Click the dashed upload zone (or the 📄 icon) to load a CSV file. The parser uses **regex-based flexible column matching**, so these headers all work:
- `Reagent`, `Reagent_Name`, `reagent` → Reagent Name
- `CAS`, `Reagent_CAS`, `cas` → CAS Number
- `Origin`, `Primary_Origin` → Origin
- `Mass`, `Mass_g` → Mass
- `Cost` → Cost
- `Lead`, `Lead_Time` → Lead Time (auto-enables Advanced Mode)
- `Haz`, `Hazard` → Hazard Score
- `Reg`, `Regulatory` → Regulatory Score
- `Sub`, `Substitutability` → Substitutability

A **"Download Sample CSV"** link provides a template with 3 example reagents:
```csv
Reagent,Reagent_CAS,Mass_g,Cost
Platinum on Carbon,7440-06-4,10,1500
Copper(II) Chloride,7447-39-4,100,45
Benzene,71-43-2,2000,50
```

### Auto-Population from Dashboard

When you click **"🌍 Analyze Risk"** on the Synthesis Planner, reagent data is consolidated and stored in `localStorage`. The Risk page detects this on load, populates all rows, and auto-triggers the assessment.

---

## Risk Calculation Engine — Full Formula

**Endpoint**: `POST /api/risk/assess`

For each reagent, the engine computes four independent risk dimensions and combines them:

### 1. Geographic Risk (Weight: 30%)

Scale: 0–100

```
geo_base = 100 - country_stability_score

If origin is "Unknown":
    geo_risk = min(100, geo_base × 1.5)    ← "Opacity Multiplier"
Else:
    geo_risk = geo_base

concentration = top supplier share (%) from trade data, or None if unknown
geo_index_input = max(geo_risk, concentration)   ← used for the 30% weight
```

`breakdown.geographic` is **country conditions only**; `breakdown.concentration`
is reported separately (see *Geographic Exposure vs. Concentration Risk*
below). The composite index still uses the worse of the two for its 30%
geographic weight, as before.

Country stability scores come from `country_stability.csv` (modeled on World Bank Worldwide Governance Indicators):

| Country | Stability Score | Resulting geo_base |
|---|---|---|
| Germany | 92 | 8 (low risk) |
| Japan | 88 | 12 |
| USA | 85 | 15 |
| Chile | 75 | 25 |
| India | 52 | 48 |
| China | 48 | 52 |
| Mexico | 42 | 58 |
| South Africa | 35 | 65 |
| Russia | 15 | 85 (high risk) |
| Unknown | 50 (default) | 75 (50 × 1.5, opacity penalty) |

### 2. Operational Risk (Weight: 20%)

Scale: 0–100

```
lead_time_risk = min(100, (lead_time_days / 30) × 100)
scarcity_risk = max(0, 100 - (supplier_count × 20))

If CAS is in CRITICAL_CAS list:
    scarcity_risk = 100    ← auto-override

operational_risk = (lead_time_risk × 0.5) + (scarcity_risk × 0.5)
```

**Critical materials** (auto-boosted to 100% scarcity):
| CAS | Material | Reason |
|---|---|---|
| 7440-06-4 | Platinum | Strategic concentration in South Africa |
| 7440-05-3 | Palladium | Strategic concentration in Russia/South Africa |
| 26628-22-8 | Sodium Azide | Niche producer, high hazard |

### 3. Regulatory Risk (Weight: 30%)

Scale: 0–100

```
reg_value = user_regulatory_score    (1-10 input)

If CAS is in REGULATORY_CAS list:
    reg_value = 10    ← auto-boost to maximum

regulatory_risk = (hazard_score × 4) + (reg_value × 6)
```

**Regulatory-flagged chemicals** (auto-boosted):
| CAS | Chemical | Flag |
|---|---|---|
| 75-09-2 | DCM (Dichloromethane) | EPA TSCA Section 6 — Commercial ban in force |
| 872-50-4 | NMP (N-Methyl-2-pyrrolidone) | Active TSCA review |
| 79-01-6 | TCE (Trichloroethylene) | Proposed prohibition |
| 50-00-0 | Formaldehyde | Active TSCA review |

### 4. Economic Risk (Weight: 20%)

Scale: 0–100

```
economic_risk = substitutability × 10
```

A substitutability of 10 (hardest to replace) = 100 economic risk.

### Composite Score and Final Risk Index

```
composite_score = geo × 0.30 + oper × 0.20 + reg × 0.30 + econ × 0.20

exposure_multiplier = log₁₀(mass_g + 1) × 0.7 + log₁₀(cost + 1) × 0.3 + 1

risk_index = composite_score × exposure_multiplier
```

The exposure multiplier scales risk by how much material is at stake. A reagent used at 10 kg with $5,000 cost has a higher risk_index than the same reagent at 1 g and $5, even if the composite score is identical.

### Risk Level Classification

| Risk Index Range | Level |
|---|---|
| 0 – 50 | **LOW** (Stable) |
| 50 – 100 | **MEDIUM** (Monitored) |
| 100 – 150 | **MEDIUM-HIGH** (Elevated Concern) |
| > 150 | **HIGH** (Critical Supply Chain) |

---

## Geographic Exposure vs. Concentration Risk

The two are reported as separate concepts for every reagent:

| | Geographic exposure (`geographic_exposure`) | Concentration risk (`concentration`) |
|---|---|---|
| Question | Where does it come from, and what are conditions there? | How concentrated is the reported supply? |
| Inputs | Dominant origin + `country_stability.csv` | Supplier-country shares from USITC / WITS |
| Example | "Dominant origin China, stability 48/100" | "95% of reported U.S. imports for this HS6 product originated from China. This creates high single-country concentration." |

No country is labelled risky by name; results describe measurable shares.

**Dominant origin priority:** user-entered origin → top supplier country in trade
data → CAS mapping → value stored in the compound registry → Unknown. The
source is shown (`origin_source`). The assessment no longer writes origins back
to the database.

### Concentration tiers (`app/modules/risk/risk_config.py`)

| Tier | Rule |
|---|---|
| **HIGH** | top supplier ≥ 50%, **or** top two combined ≥ 80% |
| **MEDIUM** | top supplier ≥ 30% |
| **LOW** | otherwise ("relatively diversified based on the available data") |
| **UNKNOWN** | no usable shares (no HS6 mapping, no trade data, or a lone WITS-listed exporter) |

Only the top one or two countries are needed. Unlisted countries are never
assumed to be 0%; when only the top N are known the result says
"Concentration assessment is based on the top N reported supplier countries."
If the second share is missing and could push the tier to HIGH, a caveat says
so. Regional groupings ("European Union", "Other Asia, nes") are excluded from
the top-supplier calculation and listed separately. No HHI is computed.

### Provenance and data quality

Each reagent's `provenance` gives: source (USITC DataWeb / WITS) and URL,
source file, HS6 code and how it was mapped, year, period type and label
(full year vs. partial/YTD), why that year was chosen, trade flow, ranking
basis (U.S. import customs value / export quantity), share basis, coverage and
number of supplier countries. The trade year is the latest **complete** year;
see `guide/DATA_SOURCES.md`.

`data_quality.level` is qualitative and rule-based: starts HIGH, capped at
LOW for partial-year data, unknown period, unknown concentration or a grouping
outranking all countries; capped at MEDIUM for listed-only (WITS top-5) shares,
fewer than 3 supplier countries, or an HS6 matched by name only. `NO_DATA`
when there is no HS6 mapping or trade data. Reasons are listed.

### Alternatives and substitutability (`alternatives`)

* `alternate_supplier_countries` / `alternate_country_count` — other origin
  countries **observed in trade data** (not qualified suppliers).
* `alternative_supply_known` and `alternative_chemistry_known` are always
  `false`: the app has no procurement data and does not infer substitutes.
* `substitutability_score` / `_source` / `_confidence` — `user_input`
  ("user_asserted") when entered in Advanced Mode, otherwise the default 5
  with source `default` and confidence `none`.

---

## Route Comparison

When reagents arrive from the Planner they carry which route uses them and
the production-scale cost per route. The Risk Audit then shows, per route:
total cost and E-factor (from the Planner), the highest-concentration reagent,
the largest dominant-country share, HIGH and UNKNOWN concentration reagents,
and reagent cost grouped by each reagent's dominant source country. There is
no combined score; the user makes the route decision.

Manual rows can use the **Route** column (`A`, `B` or `A,B`); a manual row's
cost is attributed to each listed route.

---

## Scenario / Shock Analysis

`POST /api/risk/scenario` (`app/modules/risk/scenario.py`) — deterministic
sensitivity on the shares above, not forecasting:

| Scenario | Target country |
|---|---|
| Loss of dominant supplier | each reagent's own top supplier |
| Country supply interruption | chosen country |
| Tariff (+X%, default 25) | chosen country, or each reagent's top supplier |
| Lead time (+N days, default 90) | chosen country, or each reagent's top supplier |

```
exposure_share(r)    = share of r's reported supply from the target country
affected_cost(r, R)  = route R's cost of r × exposure_share / 100
route affected %     = Σ affected_cost / Σ assessed reagent cost in R × 100
tariff added cost    = affected_cost × tariff %
lead time (affected) = current lead time + N days, on the affected share only
```

Route tiers: **highly exposed** ≥ 25% of assessed reagent cost, **moderately
exposed** ≥ 10%, **lower exposure** otherwise. Reagents without trade data are
**UNKNOWN** and their cost is reported separately; when it could raise the
tier, the result shows the upper bound. Wording describes exposure ("95%
sourcing exposure affected", "high dependency on disrupted country", "limited
observed alternative sourcing") and never claims a material becomes
unavailable. Solvents are not part of the assessed reagent cost.

### Auto-Generated Warnings

The engine appends warning strings for:
- `"Unverified Origin (Opacity Risk)"` — when origin is "Unknown"
- `"CRITICAL MATERIAL: Platinum (Strategic Concentration: South Africa)"` — when CAS is in the critical list
- `"REGULATORY FLAG: DCM (EPA TSCA Section 6 - Commercial Ban in force)"` — when CAS is in the regulatory list

---

## Results Display

### Summary Cards
Three stat cards appear after assessment:
- **Total Reagents** — count of assessed reagents (blue)
- **High Risk Items** — count of reagents classified as HIGH (red)
- **Total Risk Exposure** — sum of all risk indices (orange)

### Detailed Risk Report Table
A full-width table with columns:
| Column | Description |
|---|---|
| Reagent | Chemical name (bold) |
| CAS | CAS number (monospace font) |
| Origin | Dominant origin, how it was determined, and secondary origin |
| Stability | Country stability score out of 100, or "50 (default)" when the country is not in the table |
| Concentration | Concentration Risk card: tier, top two suppliers with shares, explanation, source, HS6, period, basis, coverage, data quality; "Why / provenance details" expands notes and alternatives |
| Mass (g) | Total mass |
| Cost ($) | Total cost |
| Risk Index | Numerical risk score (1 decimal) |
| Risk Level | Color-coded pill badge (green/yellow/orange/red) |
| Warnings | Orange or red warning text for critical/regulatory flags |

---

## Risk Visualizations

### Cost vs. Risk Priority (Bubble Chart)
- **Type**: Chart.js bubble chart
- **X-axis**: Cost ($), logarithmic scale
- **Y-axis**: Risk Index
- **Bubble size**: Proportional to √(mass) — larger bubbles = more material at risk
- **What it shows**: Each reagent plotted by cost vs. risk. Top-right quadrant = expensive AND high-risk = critical threats needing immediate attention.

### Risk Exposure by Country (Bar Chart)
- **Type**: Vertical bar chart
- **X-axis**: Countries of origin
- **Y-axis**: Sum of risk indices for all reagents from that country
- **Color**: Red with rounded corners
- **What it shows**: Geographic concentration risk. If one country has a very tall bar, your supply chain is dangerously dependent on that single source.

### Diagnostic Risk Heatmap
- **Type**: CSS grid (not a Chart.js canvas)
- **Y-axis**: Reagent names
- **X-axis**: Five dimensions — Geographic (country conditions), Concentration (top supplier share), Operational, Regulatory, Economic
- **Cell values**: Raw scores (0–100); Concentration shows a grey "n/a" when it cannot be assessed
- **Cell colors**: HSL gradient — green (0, safe) → yellow (50) → red (100, critical)
- **What it shows**: Pinpoints exactly *why* each reagent is risky. Is it the country of origin (Geographic)? Long lead times (Operational)? An EPA ban (Regulatory)? No substitutes (Economic)?

---

## Risk Export Features

### 📊 Export Risk Report
Downloads `geographic_risk_report.csv` with columns:
```
Reagent, CAS, Origin, Stability_Score, Mass_g, Cost, HS_Code, Risk_Index, Risk_Level,
Concentration_Pct, Concentration_Flag, Data_Source, Origin_Source, Stability_Known,
Top_Supplier, Top_Supplier_Share_Pct, Second_Supplier, Second_Supplier_Share_Pct,
Supplier_Countries, Concentration_Explanation, Trade_Source, Period, Partial_Year,
Ranking_Basis, Share_Basis, HS6_Source, Data_Quality, Alternate_Country_Count,
Substitutability, Substitutability_Source, Routes
```

### 💾 Save Mappings
Iterates all input rows that have both a CAS and an origin. For each, sends `POST /api/risk/update-mapping` with `{ cas, origin }`. The server upserts into `reagent_mapping.csv`. Future assessments will auto-populate the origin when the same CAS is entered.

### Download Sample CSV
Generates and downloads a 3-row template CSV with Platinum on Carbon, Copper(II) Chloride, and Benzene.

---

## Internal Databases

Two CSV files in `app/modules/risk/data/`:

### reagent_mapping.csv
Maps CAS numbers to HS trade codes and primary manufacturing countries:
```
Reagent_CAS, HS_Code, Primary_Origin
7440-06-4,   3815.12, South Africa
775-12-2,    2931.90, Germany
7447-39-4,   2827.39, China
7681-65-4,   2827.60, China
106-92-3,    2910.90, USA
```
Grows over time as users save mappings via the "💾 Save Mappings" button.

### country_stability.csv
Political/economic stability scores (0–100, higher = more stable):
```
Country, Stability_Score
Germany, 92
USA,     85
Japan,   88
China,   48
South Africa, 35
Russia,  15
Mexico,  42
India,   52
```

Both files are **auto-generated with defaults** if missing on first server start.
