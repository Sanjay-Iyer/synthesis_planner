# Data Sources — Geographic Risk Workflow

Every geographic or concentration number in the Risk Audit carries its source
in the result (`provenance` per reagent). This page documents those sources,
how the app uses them, and their limitations.

> **Scope reminder.** USITC data describes **U.S. imports** (where U.S. imports
> of an HS6 product come from). It is not global production and does not
> include U.S. domestic production. WITS data describes **world exports by
> reporting country**. A "concentrated" result means the *reported trade* is
> concentrated; it is not a judgement about any country.

---

## 1. USITC DataWeb (primary)

| | |
|---|---|
| Source | U.S. International Trade Commission — DataWeb |
| Official site | <https://dataweb.usitc.gov/> |
| Files in repo | `data/supply_chain/usitc_hts29_imports_2020_2026.xlsx` (imports) · `data/supply_chain/usitc_hts29_exports_2020_2026.xlsx` (exports) |
| Downloaded | 2026-05-19 (per each file's *Query Parameters* sheet) |
| Classification | HTS chapter 29 (organic chemicals), aggregated to **6 digits (HS6)**, countries broken out (no regional groupings) |
| Imports | "Imports for Consumption", **Customs Value** (USD) — 408 HS6 codes, 7,772 country rows |
| Exports | "Domestic Exports", **FAS Value** (USD) — 414 HS6 codes, 18,517 country rows |
| Years | Full calendar years **2020–2025**, plus a partial column `January_to_january_year_2026` (**January 2026 only**) |

**How the app uses it**

* **Imports drive concentration.** For an HS6 code, each origin country's
  share = its customs value ÷ total customs value across *all* reporting
  countries in the selected year. Ranking basis: **U.S. import customs value**
  (not quantity).
* **Exports** are indexed for context (`/api/supply-chain/lookup/{hs6}`) and are
  not used in risk scoring.
* Only chapter 29 is covered. Reagents in other chapters (e.g. 2825 metal
  oxides, 2804 nitrogen, 3907 PET, 3812 stabilisers) fall back to WITS or have
  no trade data.

**Year selection** (`select_trade_year` in `app/modules/supply_chain/provider.py`)

1. Years that are not valid calendar years, or that have no positive total for
   the HS6 code, are ignored.
2. An explicitly requested year wins if it has data.
3. Otherwise the **latest complete calendar year** is used (currently 2025).
4. Partial-year / YTD data (e.g. Jan 2026) is used only when no complete year
   has data, or when explicitly requested (`?ytd=true` on
   `/api/supply-chain/lookup/{hs6}`). It is always labelled, e.g.
   `YTD Jan 2026 (1 month)`, and caps data quality at LOW.
5. Years whose coverage cannot be determined are used only as a last resort and
   are labelled "period coverage unknown".

When newer partial data exists but was skipped, the result says so
(`newer_partial_period_available`). The result also notes when the top supplier
changed versus the previous complete year, or when the total moved by ≥50%.

**Refreshing / replacing files**

1. On DataWeb, build an *Imports for Consumption* (and optionally *Domestic
   Exports*) query: HTS items, chapter 29 (or the chapters you need),
   aggregation level 6, "Break Out Countries", annual timeframe.
2. Export to Excel and drop the `.xlsx` into `data/supply_chain/`. Remove or
   replace the old file so years are not double-counted.
3. The folder is live-scanned; the Risk Audit page's "↻ rescan" link (or
   `POST /api/supply-chain/refresh`) forces a re-index. No code change is
   needed when a new complete year arrives — the selection logic is not
   hard-coded to any year.

---

## 2. WITS — World Integrated Trade Solution (fallback)

| | |
|---|---|
| Source | World Bank WITS (UN Comtrade data) |
| Official site | <https://wits.worldbank.org/> |
| Raw files | `database/data_to_add/WITS-By-HS6Product (17–22).xlsx` (2024 exporters for HS6 282560, 390760, 381230, 291529, 282580, 280430) |
| Processed | `database/wits_exports.json` — 21 HS6 products, year **2024**, partner **World**, trade flow **Export** (`database/trade_exports_db.backup.pre_v1_1.json` is the pre-migration copy) |
| Ingestion | `scripts/ingest_wits.py` or the "Import WITS Excel" zone on the Risk Audit page (`app/modules/trade_data/wits_ingest.py`) |

**How the app uses it**

* Consulted only when USITC has no data for the HS6 code.
* Exporters are ranked by **quantity**; rows with trade value but no quantity
  are excluded (noted in the result).
* **Only the top 5 exporters are stored.** Shares are each exporter's share of
  the *top-5 combined quantity*, not of world exports. This overstates
  concentration relative to a world total, so WITS-based results are labelled
  "listed-only" and data quality is capped at MEDIUM. A lone listed exporter is
  reported as concentration UNKNOWN (its 100% is an artefact).
* **Geographic groupings** such as "European Union", "Other Asia, nes",
  "Areas, nes" appear in WITS rankings. They are never named as a top supplier
  country and are listed separately in the result; if a grouping outranks every
  country, data quality drops to LOW. The list lives in
  `app/modules/risk/risk_config.py` (`AGGREGATE_REPORTERS`).
* Country spellings differ from USITC (e.g. "Korea, Rep." vs "South Korea");
  `COUNTRY_ALIASES` in `risk_config.py` maps them for matching.

---

## 3. Country stability / governance scores (World Bank WGI)

| | |
|---|---|
| Source | World Bank **Worldwide Governance Indicators (WGI)** — <https://www.worldbank.org/en/publication/worldwide-governance-indicators> |
| Status | **Implemented.** Imported 2026-10-02 from the World Bank API (WGI source, dataset last updated 2026-09-25). |
| Indicator | `GOV_WGI_PV.SC` — *Political Stability and Absence of Violence/Terrorism: governance score (0–100)*, with its 90% confidence bounds `GOV_WGI_PV.SC_LB` / `_UB` |
| Year | 2025 for all 208 economies (latest non-missing year per economy) |
| Files | `app/modules/risk/data/country_stability.csv` (Country, Stability_Score, Score_Lower_90, Score_Upper_90, Year, ISO3, WGI_Country_Name, Indicator) and `country_stability_meta.json` (source, indicator, retrieval time, API URL) |
| Import script | `scripts/import_wgi.py` — `python scripts/import_wgi.py` (API) or `--input <DataBank CSV>` (offline); see the script header for the manual download steps |

**How it is used.** Geographic (country-conditions) score = 100 − WGI score of the
reagent's dominant origin. The score is used as published (already 0–100); no
rescaling. It is a **governance perception indicator**, not a probability of
supply disruption, and it is reported separately from sourcing concentration.
Results describe the score relative to the 0–100 scale ("above/below the
midpoint"), never a judgement of a country.

**Coverage gaps.** Economies the World Bank API does not cover (e.g. **Taiwan**,
French overseas departments such as Réunion, and several small territories)
have no score. They are reported as `no_stability_data` — the geographic
component is *not assessed*; no neutral value is substituted.

**Replaced table.** The previous 8-country table (unknown provenance; e.g. China
48, Russia 15) was replaced. Its values are not comparable with WGI governance
scores (WGI 2025: China 66.0, Russia 49.1, Mexico 55.0, Canada 79.8, South Korea
81.7) — the old table is in git history (commit `1c45ac7` and earlier).

**Country names.** WGI uses World Bank spellings ("Korea, Rep.", "Viet Nam",
"Turkiye", "Bahamas, The", …). All sources are matched through
`canonical_country()` / `COUNTRY_ALIASES` in `app/modules/risk/risk_config.py`
(accent-, case- and backtick-insensitive). Canonical names follow USITC.

---

## 4. Reagent → HS6 mapping (needed before any trade lookup)

Resolved in this order (`resolve_hs6` in `app/modules/risk/hs6_mapping.py`).
Each result carries `provenance.hs6_mapping` = {hs6, match_method, source, exact,
mapping_quality, broad_category, note}:

| # | match_method | Source | Exact | Quality |
|---|---|---|---|---|
| 1 | `user_input` | HS6 typed in the Risk Audit (Advanced Mode) or CSV `HS6` column | yes | HIGH (user-asserted) |
| 2 | `cas` | `app/modules/risk/data/reagent_mapping.csv` (6 hand-curated rows) | yes | HIGH |
| 3 | `inchikey` | `database/compound_hs6_map.json` (5 entries), InChIKey computed with RDKit from the reagent's SMILES/InChI/SELFIES (passed from the Planner) | yes | HIGH |
| 4 | `compound_registry` | `compounds.hs6_code` in `database/synthesis_architect.db`, record found by normalised **name** (values seeded by project scripts) | no | MEDIUM |
| 5 | `compound_registry_inchikey` | InChIKey of a registry record found by name → `compound_hs6_map.json` | no | MEDIUM |
| 6 | `name_hint` | `compound_hs6_map.json` name hint, **exact** match after removing grade/purity qualifiers (substring matches are rejected) | no | MEDIUM |

**Broad categories.** If the trade-data description marks a residual category
("NESOI", "n.e.s.", "Other …") — or, when no description is available, the HS6
ends in 9 (the HS convention for "Other" subheadings) — the mapping is
downgraded to **LOW** and labelled "broad product category": the trade data
then describes many products, not the reagent. Example: manganese(II) acetate →
291529 "SALTS OF ACETIC ACID, NESOI".

Mapping quality caps the result's data quality (LOW → LOW, MEDIUM → MEDIUM).
No LLM suggests codes. Reagents with no mapping have no trade data and are
reported as UNKNOWN, never as low risk.

---

## 5. PubChem (molecule names / weights)

| | |
|---|---|
| Source | NCBI PubChem PUG REST |
| Official site | <https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest> |
| Used by | Planner "+ Add Molecule": `/api/synthesis/molecule-name` (name from SMILES/SELFIES/InChI/InChIKey) and `/api/synthesis/molecular-weight` (MW fallback after RDKit) |

PubChem is not used by the geographic-risk calculations.

---

## 6. Static flags in code

`CRITICAL_CAS` and `REGULATORY_CAS` in `app/modules/risk/engine.py` are a small
hand-written demo list (Pt, Pd, sodium azide; DCM, NMP, TCE, formaldehyde). They
are not sourced from a maintained regulatory database.
