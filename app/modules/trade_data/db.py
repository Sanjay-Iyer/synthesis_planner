import json
import os
import shutil
from pathlib import Path
from datetime import datetime, timezone
import uuid
import re

DEFAULT_DB_PATH = "/home/sanjay/AV/synthesis-architect/database/wits_exports.json"

def get_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def load(db_path: str = DEFAULT_DB_PATH) -> dict:
    """Returns the full DB, or empty schema if file missing."""
    if not os.path.exists(db_path):
        return {
            "schema_version": 1,
            "last_updated": get_utc_now(),
            "trade_data": {}
        }
    try:
        with open(db_path, 'r') as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        data = {
            "metadata": {
                "schema_version": "1.1.0",
                "created_at": get_utc_now(),
                "last_updated": get_utc_now(),
                "source": "WITS / World Bank",
                "description": "Top exporters by HS6 product code, year, trade flow, and partner",
                "default_top_n": 5,
                "ranking_column": "Quantity",
                "currency_unit": "1000 USD"
            },
            "products": {}
        }
    
    # Version check
    metadata = data.get("metadata", {})
    ver = metadata.get("schema_version", "1.0.0")
    if ver > "1.1.0":
        raise ValueError(f"Unsupported trade DB schema version: {ver}. Expected <= 1.1.0.")

    # Auto-normalize/migrate legacy v1
    if is_legacy_trade_db(data):
        print("Legacy trade DB detected (v1). Migrating to v1.1.0...")
        data = migrate_trade_db_to_v1_1(data)
        save_atomic(data, db_path)
        
    return data

def is_legacy_trade_db(db: dict) -> bool:
    """True if schema is < 1.1.0."""
    if "metadata" not in db or "products" not in db:
        return True
    ver = db.get("metadata", {}).get("schema_version", "1.0.0")
    return ver < "1.1.0"

def make_record_key(year: int, trade_flow: str, partner: str) -> str:
    """Generate a stable key like 2024_export_world."""
    flow = trade_flow.lower().strip()
    part = partner.lower().strip()
    # Replace non-alphanumeric with underscores
    part = re.sub(r'[^a-z0-9]+', '_', part)
    # Collapse underscores
    part = re.sub(r'_+', '_', part).strip('_')
    return f"{year}_{flow}_{part}"

def normalize_product_description(description: str) -> str:
    """Lower case, strip, collapse spaces."""
    if not description: return ""
    return " ".join(description.lower().split())

def migrate_trade_db_to_v1_1(old_db: dict) -> dict:
    """Migrate from v1 (trade_data) to v1.1.0 (products/records)."""
    if not is_legacy_trade_db(old_db):
        return old_db

    print(f"Migrating trade database to v1.1.0...")
    
    new_db = {
        "metadata": {
            "schema_version": "1.1.0",
            "created_at": old_db.get("last_updated", get_utc_now()),
            "last_updated": get_utc_now(),
            "source": "WITS / World Bank",
            "description": "Top exporters by HS6 product code, year, trade flow, and partner",
            "default_top_n": 5,
            "ranking_column": "Quantity",
            "currency_unit": "1000 USD"
        },
        "products": {}
    }

    legacy_data = old_db.get("trade_data", {})
    
    # Try to find earliest creation time
    earliest_ingest = None

    for hs6, p_data in legacy_data.items():
        desc = p_data.get("product_description", "")
        new_product = {
            "hs6_code": hs6,
            "product_description": desc,
            "normalized_product_description": normalize_product_description(desc),
            "product_aliases": [],
            "records": {}
        }
        
        years_map = p_data.get("years", {})
        for year_str, y_data in years_map.items():
            year = int(year_str)
            flow = y_data.get("trade_flow", "Export")
            partner = y_data.get("partner", "World")
            record_key = make_record_key(year, flow, partner)
            
            ingested_at = y_data.get("ingested_at")
            if ingested_at:
                if not earliest_ingest or ingested_at < earliest_ingest:
                    earliest_ingest = ingested_at

            # Build record
            top_exporters = []
            total_val = 0.0
            for exp in y_data.get("top_exporters", []):
                val = exp.get("trade_value_1000_usd", 0.0)
                total_val += val
                
                reporter = exp.get("reporter", "Unknown")
                is_aggregate = reporter in ["European Union", "Other Asia, nes", "World", "Areas, nes", "Other Europe, nes"]
                
                top_exporters.append({
                    "rank": exp.get("rank"),
                    "reporter": reporter,
                    "reporter_type": "aggregate" if is_aggregate else "country",
                    "reporter_normalized": reporter,
                    "reporter_iso3": None,
                    "quantity": exp.get("quantity"),
                    "quantity_unit": y_data.get("quantity_unit"),
                    "trade_value_1000_usd": val,
                    "share_of_top5_pct": exp.get("share_of_top5_pct")
                })

            share = y_data.get("concentration_top1_pct", 0)
            score = "Unknown"
            if share >= 50: score = "High"
            elif share >= 25: score = "Medium"
            elif share >= 0: score = "Low"

            excluded = y_data.get("excluded_no_quantity", [])
            warnings = []
            if excluded:
                warnings.append({
                    "code": "excluded_rows_missing_quantity",
                    "message": "Rows with missing Quantity were excluded from top exporter ranking.",
                    "count": len(excluded)
                })
            
            # Truncation check
            if desc.endswith(("...", "diphen", "for")):
                warnings.append({
                    "code": "possibly_truncated_product_description",
                    "message": "Product description may be truncated in source data."
                })

            new_record = {
                "record_uuid": str(uuid.uuid4()),
                "year": year,
                "trade_flow": flow,
                "partner": partner,
                "quantity_unit": y_data.get("quantity_unit"),
                "top_n_requested": 5,
                "top_n_actual": y_data.get("top_n_actual"),
                "top_exporters": top_exporters,
                "totals": {
                    "total_top5_quantity": y_data.get("total_top5_quantity"),
                    "total_top5_trade_value_1000_usd": round(total_val, 2)
                },
                "risk_summary": {
                    "top_country": top_exporters[0]["reporter"] if top_exporters else None,
                    "top_country_share_of_top5_pct": share,
                    "concentration_top1_pct": share,
                    "concentration_score": score,
                    "share_basis": "top5_quantity",
                    "risk_basis": "Top exporter share of top 5 exporters by quantity"
                },
                "source": {
                    "filename": y_data.get("source_file"),
                    "sheet_name": None,
                    "ingested_at": ingested_at,
                    "parser_version": "1.0.0",
                    "row_count_raw": None,
                    "row_count_valid_quantity": y_data.get("top_n_actual"),
                    "row_count_excluded_no_quantity": len(excluded)
                },
                "excluded_rows": {
                    "missing_quantity": excluded
                },
                "warnings": warnings
            }
            new_product["records"][record_key] = new_record
            
        new_db["products"][hs6] = new_product

    if earliest_ingest:
        new_db["metadata"]["created_at"] = earliest_ingest
        
    return new_db

def save_atomic(data: dict, db_path: str = DEFAULT_DB_PATH):
    """Tmp file + validation + os.replace."""
    # Basic structural validation before saving
    if "metadata" not in data or "products" not in data:
        raise ValueError("Cannot save malformed trade database (missing metadata or products)")
    
    data["metadata"]["last_updated"] = get_utc_now()
    tmp_path = f"{db_path}.tmp"
    
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    with open(tmp_path, 'w') as f:
        json.dump(data, f, indent=2)
    
    # Verify we can reload it before replacing
    try:
        with open(tmp_path, 'r') as f:
            json.load(f)
    except Exception as e:
        if os.path.exists(tmp_path): os.remove(tmp_path)
        raise ValueError(f"Failed to verify atomic write for trade DB: {e}")

    os.replace(tmp_path, db_path)

from typing import Optional, Dict, List

def get_exporters(hs6: str, year: Optional[int] = None, db_path: str = DEFAULT_DB_PATH) -> Optional[dict]:
    """
    Backward-compatible helper. Returns the most recent record's data.
    """
    db = load(db_path)
    product = db.get("products", {}).get(hs6)
    if not product:
        return None
    
    records = product.get("records", {})
    if not records:
        return None
    
    if year is not None:
        # Try to find exact year (Export World)
        key = make_record_key(year, "Export", "World")
        if key in records:
            return records[key]
        # Fallback to any record for that year
        for k, v in records.items():
            if v.get("year") == year:
                return v
    
    # Get latest year
    sorted_keys = sorted(records.keys(), key=lambda k: (records[k].get("year", 0), k), reverse=True)
    return records[sorted_keys[0]]

def get_trade_record(db: dict, hs6_code: str, year: Optional[int] = None, trade_flow: str = "Export", partner: str = "World") -> Optional[dict]:
    """Modern helper for new schema."""
    product = db.get("products", {}).get(hs6_code)
    if not product:
        return None
    
    records = product.get("records", {})
    if year is not None:
        key = make_record_key(year, trade_flow, partner)
        return records.get(key)
    
    # Return latest matching flow/partner
    matches = [v for v in records.values() if v.get("trade_flow") == trade_flow and v.get("partner") == partner]
    if not matches:
        return None
    
    return sorted(matches, key=lambda x: x.get("year", 0), reverse=True)[0]
