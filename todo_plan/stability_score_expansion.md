> Part of the **[master TODO](TODO.md)** → section **3) Risk Assessment › 3b. Supply-chain data**.
> This file is the detailed sub-plan for the stability-table work.

# TODO: Expand country stability scores

**Goal:** Replace the tiny placeholder country-stability table with broad coverage so
geographic supply-chain risk is meaningful for the countries that actually show up
in the USITC trade data (163 import origins, 218 export destinations in HTS Ch. 29).

**File to edit:** `app/modules/risk/data/country_stability.csv`
Columns: `Country,Stability_Score` where `Stability_Score` is 0–100 (higher = more stable).

**How it's used:** `app/modules/risk/engine.py` → `load_country_stability()` does an
*exact* string match on `Country`. Unmatched origins fall back to a neutral **50**.
Geographic risk = `100 - Stability_Score` (×1.5, capped, if the origin is "Unknown").
Since USITC origins are matched by these exact names, the CSV names must match the
USITC `Country` spelling exactly (e.g. "United Kingdom", "South Korea", "Taiwan").

> Note: until this table is expanded, `run_risk_assessment` already blends in the
> **import-concentration %** (worst-of geo-stability vs. top-source share), so a
> 90%-from-one-country reagent still scores as high geographic risk even if that
> country is missing here. Expanding the table sharpens the *country-instability*
> half of that signal.

---

## What we have today (8 countries)

| Country      | Stability_Score |
|--------------|-----------------|
| Germany      | 92 |
| USA          | 85 |
| Japan        | 88 |
| China        | 48 |
| South Africa | 35 |
| Russia       | 15 |
| Mexico       | 42 |
| India        | 52 |
| Chile        | 75 |  ← present in the default seed in code; confirm it's in the CSV

## Major countries MISSING (ranked by 2024 U.S. import value, HTS Ch. 29)

These are the biggest origin gaps — add these first:

| Rank | Country         | 2024 imports | Notes |
|------|-----------------|--------------|-------|
| 1 | **Ireland**         | $17.4B | Largest single origin (pharma intermediates); currently → 50 |
| 3 | **Canada**          | $3.4B  | |
| 6 | **South Korea**     | $2.3B  | exact name "South Korea" |
| 7 | **Singapore**       | $2.2B  | |
| 8 | **Netherlands**     | $1.7B  | |
| 10 | **Switzerland**    | $1.3B  | |
| 11 | **Italy**          | $1.1B  | |
| 13 | **France**         | $1.0B  | |
| 14 | **United Kingdom** | $1.0B  | exact name "United Kingdom" |
| 15 | **Belgium**        | $1.0B  | |
| 16 | **Saudi Arabia**   | $0.77B | |
| 17 | **Argentina**      | $0.74B | |
| 18 | **Taiwan**         | $0.69B | name "Taiwan" |
| 19 | **Brazil**         | $0.67B | |
| 20 | **Spain**          | $0.65B | |
| 21 | **Venezuela**      | $0.48B | high-instability example |
| 22 | **Colombia**       | $0.30B | |
| 23 | **Denmark**        | $0.26B | |
| 24 | **Indonesia**      | $0.26B | |
| 25 | **Thailand**       | $0.25B | already in reagent_mapping as an origin |

(There are ~163 import origins total; the long tail is small by value but should still
get a score so risk isn't silently neutral. A bulk import of all WGI countries covers
them in one pass — see below.)

## Ideas for how to score (pick one, document the choice in the CSV header)

1. **World Bank WGI — Political Stability & Absence of Violence (recommended).**
   - Source: World Bank Worldwide Governance Indicators (info.worldbank.org/governance/wgi).
   - The "Political Stability" estimate is roughly −2.5..+2.5. Normalize to 0–100:
     `score = round((estimate + 2.5) / 5 * 100)`. Or use the published 0–100 **percentile rank** directly.
   - One download → one row per country → matches our 0–100 convention cleanly.

2. **Blend multiple WGI dimensions** for "supply reliability" rather than just unrest:
   average of Political Stability, Government Effectiveness, Rule of Law, Regulatory
   Quality (each normalized 0–100). Better captures customs/logistics reliability.

3. **Composite trade-risk index** (more work): blend WGI stability with a logistics
   measure (World Bank LPI) and an export-restriction/sanctions flag. Useful if we
   later want "how likely is this supply to be *disrupted*" vs. pure political risk.

4. **Quick interim hand-scores** for just the ~25 countries above using public risk
   tiers (e.g. EU/OECD ~85–92, stable Asia ~75–88, mid ~45–60, high-risk ~15–35),
   then backfill from WGI later. Fastest path to a meaningful demo.

## Implementation checklist

- [ ] Decide scoring method (default: WGI Political Stability percentile, 0–100).
- [ ] Generate `country_stability.csv` covering all USITC `Country` spellings (script:
      pull distinct `Country` values from both files in `data/supply_chain/`, left-join
      to WGI, fill gaps with method #4 or a documented default).
- [ ] Verify exact-name matches (USITC "Korea" vs "South Korea", "Russia" vs
      "Russian Federation", "Taiwan" vs "Chinese Taipei", "Turkey" vs "Türkiye").
      Add an alias map in `load_country_stability()` if spellings diverge.
- [ ] Add a `source` / `as_of_year` note in the CSV header comment for provenance.
- [ ] Re-run a sample risk assessment and confirm geo risk changed for Ireland, etc.
- [ ] Optional: expand `compound_hs6_map.json` / `reagent_mapping.csv` so more reagents
      resolve to an HTS6 and pick up these origins automatically.
