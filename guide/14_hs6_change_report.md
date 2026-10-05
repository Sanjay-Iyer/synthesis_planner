# Explicit HS6 trade matching — implementation report

## Behavior

An explicitly supplied valid HS6 is now independent of reagent-name, registry,
CAS and structure resolution. A route containing `antimony oxides` or even
`antiomy oxides` with `hs6: "282580"` uses the same WITS category without
changing the original display name. Different reagents may share a category.

Previously, Risk Audit already had an advanced HS6 input, but Planner models,
estimates, route persistence, CSV reports and the hand-off did not reliably
retain it. Automatic name resolution was therefore often required in practice.
The old normalizer could strip letters, truncate long codes, or pad short ones.

The new canonical field is optional `hs6`, stored as a string. A shared
normalizer removes whitespace and accepts exactly six ASCII digits. It never
truncates, pads, removes letters, or converts decimal/scientific notation into
a valid explicit code. Invalid input remains visible as text and blocks trade
lookup and automatic fallback. Integer `282580` becomes string `"282580"`;
string `"070951"` keeps its leading zero.

Blank HS6 retains the existing CAS → structure/InChIKey → compound registry →
canonical-name resolver. Trusted historical CAS tables still support customs
notation such as `2917.36`; explicit user input must use `291736`.

## Storage, display and CSV

- `ReagentInput`, `RouteReagentInput`, `DraftReagent` and `ReagentRiskInput`
  include optional `hs6`. Risk results and scenario results carry `hs6` and
  `trade_status`; risk results retain the old `hs_code` alias.
- SQLite migration adds nullable `step_reagents.hs6 TEXT`. Raw reagent JSON
  also retains HS6. Historical hashes stay unchanged for routes without HS6;
  different explicit codes produce different route hashes when saving.
- HS6 appears immediately beside the name in Planner reagent cards, Risk
  Audit inputs/results, scenario tables, heatmaps and report CSV. Bubble-chart
  tooltips include HS6 and status. Missing codes display `UNKNOWN`.
- Reagent CSV accepts `Reagent_Name,HS6` and header variants `hs6`, `HS6_Code`,
  `HS_Code`. Cells stay strings, including quoted cells and leading zeroes.
- Planner report CSV exports HS6 beside reagent names and accepts both the
  new reports and historical reports without that column.
- Planner → Risk Audit consolidation keeps the same name with different
  explicit HS6 codes separate, and permits several names to share a code.
- Risk Audit accepts an HS6-only row. Auto-Lookup uses the same active-row
  selection as request collection, so blank rows cannot misplace suggestions.
  It refreshes earlier automatic origins while preserving user overrides.

## WITS join and risk equations

The exact WITS field is **`ProductCode` on sheet `By-HS6Product`**. It is read
as text, normalized, validated, and stored as `products[hs6].hs6_code` in the
WITS JSON database. Existing Export + World filtering, quantity ranking,
country shares, exporter values and concentration calculations remain intact.

The assessment joins the resolved explicit code to the trade category key.
Existing USITC import data remains preferred when available, with WITS as the
existing fallback. Geographic, concentration, composite and scenario equations
were not changed. Available suppliers, exporter quantities/values, shares,
geographic exposure, alternatives and scenario data flow through as before.

Statuses distinguish `MATCHED`, `NO WITS DATA` (known code without usable
indexed trade data), `HS6 MISSING`, `INVALID HS6`, and technical
`TRADE LOOKUP ERROR`. Lookup status is also shown beneath the HS6 input.

## Verification

- Full Python suite: **209 passed**, eight openpyxl workbook-style warnings.
- Frontend regression suite: **5 passed** (`node --test tests/test_hs6_frontend.cjs`).
- Both changed JavaScript files pass `node --check`.
- Added tests cover requested cases A–G, whitespace/string normalization,
  leading zeroes, malformed WITS codes, explicit-code independence from a
  working registry, HS6-only origin lookup, scenario propagation, route
  save/load/estimation, legacy hashes, additive migration, CSV aliases,
  CSV round trips and hand-off consolidation.
- Browser check using existing `282580` WITS data: `antimony oxides` remained
  unchanged; HS6 appeared next to its name; status was `MATCHED`; China was
  the top exporter at approximately **48%**, Belgium approximately **14.4%**;
  WGI stability was **66/100**, geographic risk approximately **34/100**,
  and concentration **MEDIUM**. Dominant-supplier-loss scenario used the same
  approximately 48% exposure (about $47.99 on $100 assessed spend).
- `WITS-By-HS6Product (21).xlsx` was checked directly: `ProductCode` is
  `282580`, description `Antimony oxides`, with five ranked exporter rows.
- Browser check of HS6-only second row with a blank first row: Auto-Lookup
  filled **China / Belgium** in the correct row and showed `MATCHED`.
- Compared all historical columns/rows in the local SQLite database against
  the original: routes (2), route steps (5), step reagents (10), analysis
  runs (6), and compounds (10) were unchanged. Migration only added HS6 storage.

Name matching remains only an automatic fallback when HS6 is absent, and in
existing chemical-registry identity/de-duplication workflows. It is never a
requirement for an explicit valid HS6 trade association.

## Follow-up: primary and secondary country percentages

The assessment now stores `primary_origin_share_pct` and
`secondary_origin_share_pct` alongside the displayed countries. The Origin
column displays both percentages with their denominator, and the CSV export
retains both country shares and the share basis. Shares follow the displayed
country, including a user-selected origin and country aliases; absent shares
remain unavailable instead of defaulting to zero or borrowing the top share.

An ingested test workbook with 98% China and 2% Belgium verifies that these
shares populate and the existing concentration classification is HIGH.
No risk equation changed. WITS shares refer to listed exporter quantities;
USITC shares refer to reported import origins. Concentration remains a
separate measure from the composite Risk Index.

Follow-up verification: **59 relevant Python tests** and **six frontend tests**
passed, covering the 98% concentration example, country overrides/aliases,
unknown shares and CSV preservation.

## Files changed

| File | Purpose |
|---|---|
| [app/hs6.py](C:/code/synthesis_planner/app/hs6.py) | Shared string normalization and validation |
| [database/models.py](C:/code/synthesis_planner/app/modules/database/models.py) | Route reagent HS6 |
| [database/db.py](C:/code/synthesis_planner/app/modules/database/db.py) | Additive TEXT migration, save and route hash |
| [extraction/schemas.py](C:/code/synthesis_planner/app/modules/extraction/schemas.py) | Draft reagent HS6 |
| [synthesis/engine.py](C:/code/synthesis_planner/app/modules/synthesis/engine.py) | Estimate input/output propagation |
| [risk/hs6_mapping.py](C:/code/synthesis_planner/app/modules/risk/hs6_mapping.py) | Explicit priority and strict validation; preserved fallback |
| [risk/engine.py](C:/code/synthesis_planner/app/modules/risk/engine.py) | Canonical results, statuses, summaries and origin lookup |
| [risk/concentration.py](C:/code/synthesis_planner/app/modules/risk/concentration.py) | Invalid-code data-quality explanation |
| [risk/scenario.py](C:/code/synthesis_planner/app/modules/risk/scenario.py) | HS6/status propagation |
| [trade_data/wits_ingest.py](C:/code/synthesis_planner/app/modules/trade_data/wits_ingest.py) | ProductCode normalization and validation |
| [static/js/dashboard.js](C:/code/synthesis_planner/app/static/js/dashboard.js) | Planner input, CSV and hand-off |
| [static/js/risk.js](C:/code/synthesis_planner/app/static/js/risk.js) | Risk input, statuses, CSV, displays and HS6-only lookup |
| [static/risk.html](C:/code/synthesis_planner/app/static/risk.html) | Visible HS6 columns and usage help |
| [test_explicit_hs6.py](C:/code/synthesis_planner/tests/test_explicit_hs6.py) | 35 backend regression cases |
| [test_hs6_frontend.cjs](C:/code/synthesis_planner/tests/test_hs6_frontend.cjs) | Six frontend regression tests |
| [test_hs6_mapping.py](C:/code/synthesis_planner/tests/test_hs6_mapping.py) | Update explicit-code test to six-digit input |
| [11_trade_risk_integration.md](C:/code/synthesis_planner/guide/11_trade_risk_integration.md) | User guidance |
| [14_hs6_change_report.md](C:/code/synthesis_planner/guide/14_hs6_change_report.md) | This implementation/verification report |

The local `database/synthesis_architect.db` also received the additive runtime
schema migration. Existing unrelated workspace changes and the user's WITS
upload were preserved.
