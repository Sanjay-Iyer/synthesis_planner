import json
import os
import shutil
from pathlib import Path
from datetime import datetime, timezone

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
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {
            "schema_version": 1,
            "last_updated": get_utc_now(),
            "trade_data": {}
        }

def save_atomic(data: dict, db_path: str = DEFAULT_DB_PATH):
    """Tmp file + os.replace."""
    data["last_updated"] = get_utc_now()
    tmp_path = f"{db_path}.tmp"
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    with open(tmp_path, 'w') as f:
        json.dump(data, f, indent=2)
    
    os.replace(tmp_path, db_path)

from typing import Optional, Dict, List

def get_exporters(hs6: str, year: Optional[int] = None, db_path: str = DEFAULT_DB_PATH) -> Optional[dict]:
    """
    If year is None, returns the most recent year's data.
    Returns None if HS6 not in DB.
    """
    db = load(db_path)
    product_data = db.get("trade_data", {}).get(hs6)
    if not product_data:
        return None
    
    years_data = product_data.get("years", {})
    if not years_data:
        return None
    
    if year is None:
        # Get the most recent year
        available_years = sorted(years_data.keys(), reverse=True)
        year_str = available_years[0]
    else:
        year_str = str(year)
        
    return years_data.get(year_str)
