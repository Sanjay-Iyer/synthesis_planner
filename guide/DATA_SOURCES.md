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

## 3. Country stability / governance scores

| | |
|---|---|
| File | `app/modules/risk/data/country_stability.csv` (8 countries, 0–100, higher = more stable) |
| Current provenance | **Current provenance needs confirmation.** The file was added in the first commit (2026-05-01). Code comments and `guide/08_risk_audit.md` describe it as "based on / modeled on World Bank WGI", but no WGI indicator, release year or normalisation is recorded, and the values cannot be traced to a specific WGI release from the repository. |
| Planned source | World Bank **Worldwide Governance Indicators (WGI)** — <https://www.worldbank.org/en/publication/worldwide-governance-indicators>. **Planned, not implemented.** See `todo_plan/stability_score_expansion.md`. |

Countries not in the table (e.g. Canada, South Korea, Netherlands) get a
neutral default of 50, and the result says so (`stability_known: false`).
Stability describes country conditions only; it is reported separately from
sourcing concentration.

---

## 4. Reagent → HS6 mapping (needed before any trade lookup)

Resolved in this order (`resolve_hs6` in `app/modules/risk/engine.py`); the
source used is reported as `provenance.hs6_source`:

1. `app/modules/risk/data/reagent_mapping.csv` — CAS → HS code (hand-curated,
   6 rows; also stores a manually entered origin).
2. Compound registry `database/synthesis_architect.db` (`compounds.hs6_code`) —
   values seeded by project scripts.
3. `database/compound_hs6_map.json` — InChIKey → HS6 (5 entries, seeded by
   `scripts/seed_hs6_map.py`).
4. Name hint from `compound_hs6_map.json` (substring match; data quality capped
   at MEDIUM).

Most reagents have no mapping today, which means no trade data — reported as
UNKNOWN, never as low risk.

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
