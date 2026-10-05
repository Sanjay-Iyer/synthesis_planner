import pandas as pd
import os
import json
from . import db
from datetime import datetime, timezone
import uuid

from typing import List, Dict
from app.hs6 import normalize_hs6


def parse_wits_file(xlsx_path: str) -> List[dict]:
    """Returns one dict per unique HS6 code in the file."""
    # Real data lives on By-HS6Product
    try:
        df = pd.read_excel(
            xlsx_path, sheet_name="By-HS6Product", dtype={"ProductCode": str}
        )
    except ValueError:
        raise ValueError("Sheet 'By-HS6Product' is missing")

    required_cols = [
        "Reporter",
        "TradeFlow",
        "ProductCode",
        "Product Description",
        "Year",
        "Partner",
        "Trade Value 1000USD",
        "Quantity",
        "Quantity Unit",
    ]

    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Required column '{col}' is missing")

    # ProductCode on By-HS6Product is the HS6 join key, never the description.
    df["ProductCode"] = df["ProductCode"].map(normalize_hs6)

    # Filter strictly: TradeFlow == Export AND Partner.strip() == World
    df["PartnerClean"] = df["Partner"].astype(str).str.strip()
    mask = (df["TradeFlow"].str.strip() == "Export") & (df["PartnerClean"] == "World")
    df_filtered = df[mask].copy()

    if df_filtered["ProductCode"].isna().any():
        raise ValueError("Invalid HS6 in WITS ProductCode: expected exactly six digits")

    if df_filtered.empty:
        raise ValueError("No rows survive the Export+World filter")

    results = []
    for hs6, group in df_filtered.groupby("ProductCode"):
        # Validate same Year and same Quantity Unit
        years = group["Year"].unique()
        if len(years) > 1:
            raise ValueError(f"Multiple Years appear for HS6 {hs6}")

        # Check units but only for rows that HAVE quantity
        units = group[group["Quantity"].notna()]["Quantity Unit"].unique()
        if len(units) > 1:
            raise ValueError(f"Multiple Quantity Units appear for HS6 {hs6}")

        product_desc = group["Product Description"].iloc[0]
        year = str(years[0])
        unit = units[0] if len(units) > 0 else group["Quantity Unit"].iloc[0]

        # Split into valid and excluded (no quantity)
        valid_rows = group[group["Quantity"].notna()].copy()
        excluded_rows = group[group["Quantity"].isna()].copy()

        # Sort valid by Quantity descending
        valid_rows = valid_rows.sort_values(by="Quantity", ascending=False)
        top_5 = valid_rows.head(5)

        total_top5_qty = float(top_5["Quantity"].sum())

        top_exporters = []
        for i, (idx, row) in enumerate(top_5.iterrows(), 1):
            share = (
                (float(row["Quantity"]) / total_top5_qty * 100)
                if total_top5_qty > 0
                else 0
            )
            reporter = str(row["Reporter"])
            is_aggregate = reporter in [
                "European Union",
                "Other Asia, nes",
                "World",
                "Areas, nes",
                "Other Europe, nes",
            ]

            top_exporters.append(
                {
                    "rank": i,
                    "reporter": reporter,
                    "reporter_type": "aggregate" if is_aggregate else "country",
                    "reporter_normalized": reporter,
                    "reporter_iso3": None,
                    "quantity": float(row["Quantity"]),
                    "quantity_unit": unit,
                    "trade_value_1000_usd": float(row["Trade Value 1000USD"]),
                    "share_of_top5_pct": round(share, 2),
                }
            )

        excluded_no_quantity = []
        for idx, row in excluded_rows.iterrows():
            excluded_no_quantity.append(
                {
                    "reporter": row["Reporter"],
                    "trade_value_1000_usd": float(row["Trade Value 1000USD"]),
                }
            )

        concentration_top1 = (
            top_exporters[0]["share_of_top5_pct"] if top_exporters else 0
        )
        total_trade_val = sum(e["trade_value_1000_usd"] for e in top_exporters)

        score = "Unknown"
        if concentration_top1 >= 50:
            score = "High"
        elif concentration_top1 >= 25:
            score = "Medium"
        elif concentration_top1 >= 0:
            score = "Low"

        warnings = []
        if not excluded_rows.empty:
            warnings.append(
                {
                    "code": "excluded_rows_missing_quantity",
                    "message": "Rows with missing Quantity were excluded from top exporter ranking.",
                    "count": len(excluded_rows),
                }
            )

        if product_desc.endswith(("...", "diphen", "for")):
            warnings.append(
                {
                    "code": "possibly_truncated_product_description",
                    "message": "Product description may be truncated in source data.",
                }
            )

        results.append(
            {
                "hs6_code": hs6,
                "product_description": product_desc,
                "year": int(year),
                "trade_flow": "Export",
                "partner": "World",
                "quantity_unit": unit,
                "top_n_actual": len(top_exporters),
                "top_exporters": top_exporters,
                "totals": {
                    "total_top5_quantity": total_top5_qty,
                    "total_top5_trade_value_1000_usd": round(total_trade_val, 2),
                },
                "risk_summary": {
                    "top_country": (
                        top_exporters[0]["reporter"] if top_exporters else None
                    ),
                    "top_country_share_of_top5_pct": concentration_top1,
                    "concentration_top1_pct": concentration_top1,
                    "concentration_score": score,
                    "share_basis": "top5_quantity",
                    "risk_basis": "Top exporter share of top 5 exporters by quantity",
                },
                "excluded_rows": {"missing_quantity": excluded_no_quantity},
                "warnings": warnings,
            }
        )

    return results


def ingest(xlsx_path: str, db_path: str = db.DEFAULT_DB_PATH) -> dict:
    """Parses the file, merges into the JSON database atomically."""
    try:
        parsed_results = parse_wits_file(xlsx_path)
    except Exception as e:
        raise ValueError(f"Parsing failed: {str(e)}")

    database = db.load(db_path)
    source_filename = os.path.basename(xlsx_path)
    ingested_at = datetime.now(timezone.utc).isoformat()

    summary = {
        "compounds_processed": len(parsed_results),
        "new_entries": [],
        "updated_entries": [],
        "warnings": [],
    }

    for item in parsed_results:
        hs6 = item["hs6_code"]
        year = item["year"]
        flow = item["trade_flow"]
        partner = item["partner"]
        record_key = db.make_record_key(year, flow, partner)

        if hs6 not in database.get("products", {}):
            if "products" not in database:
                database["products"] = {}
            database["products"][hs6] = {
                "hs6_code": hs6,
                "product_description": item["product_description"],
                "normalized_product_description": db.normalize_product_description(
                    item["product_description"]
                ),
                "product_aliases": [],
                "records": {},
            }

        product = database["products"][hs6]
        is_new = record_key not in product["records"]

        # Preserve record_uuid
        record_uuid = str(uuid.uuid4())
        if not is_new:
            record_uuid = product["records"][record_key].get("record_uuid", record_uuid)
            summary["updated_entries"].append(f"{hs6}_{record_key}")
        else:
            summary["new_entries"].append(f"{hs6}_{record_key}")

        # Check warnings for summary
        if item["top_n_actual"] < 5:
            summary["warnings"].append(
                f"HS {hs6}: Fewer than 5 valid rows available ({item['top_n_actual']})"
            )

        product["records"][record_key] = {
            "record_uuid": record_uuid,
            "year": year,
            "trade_flow": flow,
            "partner": partner,
            "quantity_unit": item["quantity_unit"],
            "top_n_requested": 5,
            "top_n_actual": item["top_n_actual"],
            "top_exporters": item["top_exporters"],
            "totals": item["totals"],
            "risk_summary": item["risk_summary"],
            "source": {
                "filename": source_filename,
                "sheet_name": "By-HS6Product",
                "ingested_at": ingested_at,
                "parser_version": "1.0.0",
                "row_count_raw": None,
                "row_count_valid_quantity": item["top_n_actual"],
                "row_count_excluded_no_quantity": len(
                    item["excluded_rows"]["missing_quantity"]
                ),
            },
            "excluded_rows": item["excluded_rows"],
            "warnings": item["warnings"],
        }

    db.save_atomic(database, db_path)
    return summary
