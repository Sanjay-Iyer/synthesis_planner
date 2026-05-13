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
The system analyzes the share of the top exporters within the top 5 ranking.

| Risk Level | Thresholds |
| :--- | :--- |
| **🔴 HIGH** | Top-1 exporter > 50% share OR Top-3 exporters > 80% share. |
| **🟡 MEDIUM** | Top-1 exporter > 30% share OR Top-3 exporters > 60% share. |
| **🟢 LOW** | Otherwise. |

### Data Quality Warnings
The system emits warnings if major exporters (by trade value) are excluded because they failed to report quantity. This is surfaced as a **"Data Quality Note"** in the risk report.

## 4. Compound to HS6 Mapping
To analyze a compound, the system must map its InChIKey to a 6-digit HS code. This mapping is stored in:
`/home/sanjay/AV/synthesis-architect/database/compound_hs6_map.json`

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

---
*Created on 2026-05-13*
