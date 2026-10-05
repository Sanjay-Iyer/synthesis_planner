# WITS Trade Data & Supply Chain Risk Guide

This guide explains how to use the WITS (World Integrated Trade Solution) ingestion system and the integrated supply chain concentration risk features.

---

## 1. Overview
The Synthesis Architect now supports ingesting global export data to identify **geographic concentration risks**. This helps identify chemicals where the global supply is dominated by a single country or a small group of countries, which can lead to supply chain vulnerabilities.

## 2. Data Ingestion

### via Web UI
1. Navigate to the **Risk Audit** page.
2. Click on the **"Import WITS Excel"** zone (with the 🌍 icon).
3. Select an `.xlsx` file exported from WITS (specifically the `By-HS6Product` sheet format).
4. The system will parse the file, extract the top 5 exporters by quantity, and save them to the database.

### via CLI (Bulk Import)
For bulk processing, use the provided script:
```bash
python scripts/ingest_wits.py "/path/to/excel/files/*.xlsx"
```
Options:
- `--dry-run`: Parse and print results without saving.

## 3. How Risk is Calculated
> **Note:** the thresholds below are the `concentration_score` stored in
> `wits_exports.json` at ingest time. The Risk Audit now classifies
> concentration with one central rule for both USITC and WITS (see
> `guide/08_risk_audit.md` → *Concentration tiers*), excludes regional
> groupings, and labels WITS shares as top-5-only. USITC DataWeb data is
> preferred when available; see `guide/DATA_SOURCES.md`.

The system analyzes the share of the top exporters within the top 5 ranking.

| Risk Level | Thresholds |
| :--- | :--- |
| **🔴 HIGH** | Top-1 exporter > 50% share OR Top-3 exporters > 80% share. |
| **🟡 MEDIUM** | Top-1 exporter > 30% share OR Top-3 exporters > 60% share. |
| **🟢 LOW** | Otherwise. |

### Data Quality Warnings
The system emits warnings if major exporters (by trade value) are excluded because they failed to report quantity. This is surfaced as a **"Data Quality Note"** in the risk report.

## 4. Compound to HS6 Mapping
Enter a six-digit **HS6** beside the reagent name in the Planner or Risk Audit,
then press **Run Risk Assessment**. Explicit HS6 is the primary trade-data key;
the original name is retained and does not have to match a registry name.
**Auto-Lookup Origins** fills the input row's primary/secondary origin suggestions
and, if the reagent name is blank, the matched trade product description (for
example, `282580` → `Antimony oxides`). This is an editable category description;
it does not identify a unique chemical. User-entered names are preserved.
Changing HS6 and repeating lookup refreshes names previously filled automatically.
If no description is available, the name remains blank and is shown as `Unknown`
in the risk report. Lookup status appears beneath the HS6 input.

The assessed Origin column shows **Primary: country — share%** and
**Secondary: country — share%**, with the share basis. The export report retains
both origin shares and that basis. Unreported shares stay unavailable, not zero.
Higher dominant-country shares imply greater sourcing concentration: the
existing rules classify a top-country share of at least 50%, or a combined
top-two share of at least 80%, as HIGH. Thus 98% from China is HIGH concentration.
Concentration is tracked separately from the existing composite Risk Index.
WITS percentages here represent export quantity among the listed exporters,
not the fraction of all global production or of a user's purchases.

HS6 identifies a customs product category, which can be shared by several
chemicals. It does not establish a chemical's identity.

With HS6 blank, the existing CAS, structure/InChIKey, compound registry and
canonical-name resolver remains available. The InChIKey/name mapping is stored in:
`<repo-root>/database/compound_hs6_map.json`

Currently supported CONFIRMED mappings:
- **Terephthalic acid** (291736)
- **Dimethyl terephthalate** (291737)
- **Ethylene glycol** (290531)
- **Acrylic acid** (291611)
- **Phthalic anhydride** (291735)

## 5. Technical Details
- **Database**: `database/wits_exports.json` (Atomic JSON writes).
- **InchiKey Generation**: Performed automatically via RDKit on first load.
- **Filtering**: Only `TradeFlow == Export` and `Partner == World` rows are analyzed.
- **Ranking**: Strictly by **Quantity**, not Trade Value.
- **Join field**: `ProductCode` on the `By-HS6Product` sheet, normalized to a
  six-digit string and stored as `products[hs6].hs6_code`.
- **CSV input**: `Reagent_Name,HS6`; headers `hs6`, `HS6_Code`, `HS_Code` also
  work. Code cells remain strings, including leading zeroes. Whitespace is
  removed; malformed codes (including decimals or scientific notation) are
  flagged instead of repaired or replaced by automatic name lookup.
- **Audit statuses**: `MATCHED`, `NO WITS DATA` (known code, no usable indexed
  trade data), `HS6 MISSING`, `INVALID HS6`, and `TRADE LOOKUP ERROR` for a
  technical failure. Existing USITC import data remains preferred over WITS.
- **Persistence**: Optional `hs6` travels with the reagent through JSON routes,
  route-report CSV, SQLite `step_reagents.hs6` (TEXT), estimates, assessments
  and scenarios. Historical routes without HS6 still load; schema migration
  only adds a nullable column. `hs_code` remains a result alias for older clients.

For example, `antimony oxides,282580` matches the same WITS category as a
reagent called `Antimony trioxide catalyst` supplied with that code. Missing
HS6 never causes an unrecognized name to be associated with unrelated trade data.

---
*Created on 2026-05-13*
