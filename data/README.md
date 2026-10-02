# Demo data

> **Demo routes are illustrative examples intended to demonstrate the
> application's analysis workflow.** Chemical pathways and reagents may
> correspond to real chemistry, but demo yields, prices, sourcing assumptions,
> and route choices should not be interpreted as validated current industrial
> manufacturing data.

| File | What it is |
|---|---|
| `RouteA_PET.json` | Route A — PET via direct esterification of terephthalic acid (TPA) + ethylene glycol, GeO₂ catalyst (2 steps). Load into the Planner's Route A. |
| `RouteB_PET.json` | Route B — PET via transesterification of dimethyl terephthalate (DMT), Mn(OAc)₂ / Sb₂O₃ catalysts, solid-state polymerisation (3 steps). Load into Route B. |
| `setup/routeA_demo.txt`, `setup/routeB_demo.txt` | The same routes as free-text procedures, for the Setup (extraction) page. |
| `archive/` | Older example routes (CFBI variants) kept for reference. |
| `supply_chain/` | USITC trade data used by the Risk Audit — real data, see [`guide/DATA_SOURCES.md`](../guide/DATA_SOURCES.md). |

## Demo walkthrough: route economics vs. supply geography

Numbers below were reproduced on 2026-10-02 with the data in this repo (USITC
full-year 2025, WITS 2024, WGI 2025). Re-run the steps; do not quote them if the
data files change.

1. **Planner** (`python start.py` → Planner). Route A → 📂 Load →
   `data/RouteA_PET.json`; Route B → 📂 Load → `data/RouteB_PET.json`.
   Click **⚡ Run Analysis**.
   - Route A (TPA direct esterification, 2 steps): **$2,287.26/kg, E-factor 4.27**
   - Route B (DMT transesterification, 3 steps): **$1,769.20/kg, E-factor 20.9**
   - On cost alone Route B looks cheaper; on E-factor Route A looks greener.
2. Click **🌍 Analyze Risk**. Both routes' reagents arrive with route
   membership (Route column = A or B), production-scale spend and, where the
   JSON has one, the SMILES used for exact HS6 matching.
3. In **Detailed Risk Report**, find *Dimethyl terephthalate (HPLC Grade)*
   (Route B): **South Korea 96.6% · China 2.8% — Concentration Risk HIGH**.
   Open *Why / provenance details*: USITC DataWeb, HS6 291737 DIMETHYL
   TEREPHTHALATE, full-year 2025 (newer Jan-2026 YTD data not used), basis U.S.
   import customs value, 3 supplier countries reported, HS6 match = structure
   (InChIKey, exact), data quality HIGH. Scope: U.S. imports only — not global
   supply and not U.S. domestic production.
   For Route A the counterpart is *Terephthalic acid*: **Mexico 86.2% · South
   Korea 13.5% — HIGH**, 6 supplier countries, data quality HIGH.
4. **Route Comparison** table:

   | | Route A | Route B |
   |---|---|---|
   | Total route cost / E-factor | $2,287.26 / 4.27 | $1,769.20 / 20.9 |
   | Assessed reagent spend | $2,286.92 (100% of route cost) | $706.87 (40% — solvents not assessed) |
   | Reagents with trade data | 4 of 5 | 5 of 5 |
   | HIGH concentration reagents | 4 | 3 |
   | Highest single-country share | Canada 99.2% (ethylene glycol) | Canada 99.2% (ethylene glycol) |
   | Largest single-country exposure | China 39.7% of reagent spend | **South Korea 62.5%** (DMT) |
   | Unknown trade-data exposure | 6.1% (UV stabilizer) | none |

5. **Scenario / Shock Analysis** → *Selected country supply interruption* →
   **South Korea** → Run Scenario:
   > Under a hypothetical South Korea supply interruption, approximately 7.7% of
   > the assessed reagent spend for Route A is exposed versus 62.5% for Route B.

   Route B: highly exposed (DMT, high dependency, limited observed alternative
   sourcing). Route A: lower exposure (could be up to MEDIUM if its unknown-data
   reagent were affected). Then try **Mexico**: Route A 23.1% vs Route B 0.1% —
   the picture reverses.

**What this shows.** The cheaper route (B) concentrates most of its assessed
reagent spend in one reagent whose reported U.S. imports come almost entirely
from one country; the other route is exposed to different countries. Neither
route is "safe" — each has a different geographic dependency that a cost / yield
/ E-factor comparison does not reveal. The app does not pick a route.

**What it does not show.** A prediction that any disruption will happen; global
production shares (USITC is U.S. imports only); qualified alternate suppliers;
domestic U.S. production or inventories.

**Known demo-data quirks** (illustrative routes):
- Route A step 2 lists *PET Intermediate (Oligomer)* — the product of step 1 —
  as a purchased reagent ($1,230.77, 54% of Route A reagent spend). Its HS6
  (390760, PET in primary forms) comes from a name-matched registry record and
  WITS top-5 export data (data quality MEDIUM). It drives most of Route A's
  China exposure (39.7%); treat that figure as weaker than the South Korea /
  Mexico results, which rest on exact structure matches and full-year USITC data.
- Route B's E-factor is dominated by solvent/atmosphere entries ("N2 Atmosphere"
  modelled as a solvent).
- Manganese(II) acetate maps to 291529 "SALTS OF ACETIC ACID, NESOI" — a broad
  category, so its mapping and data quality are LOW.

The trade data is real (USITC / WITS); the routes' yields and prices are not.
Concentration results describe the reported trade for each HS6 product, not
the specific suppliers a real plant would use.
