import sys
import os
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.modules.trade_data import db

def validate_db():
    print("Trade export DB validation")
    print("-------------------------")
    
    db_path = db.DEFAULT_DB_PATH
    if not os.path.exists(db_path):
        print(f"Error: Database file {db_path} not found.")
        return

    with open(db_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    errors = []
    
    # 1. Check top-level structure
    if "metadata" not in data: errors.append("Missing 'metadata' block")
    if "products" not in data: errors.append("Missing 'products' block")
    
    if errors:
        print("\n".join(errors))
        print("Validation: FAIL")
        return

    metadata = data["metadata"]
    print(f"Schema Version: {metadata.get('schema_version')}")
    
    products = data["products"]
    uuids = set()
    
    for hs6, p_data in products.items():
        if "hs6_code" not in p_data: errors.append(f"Product {hs6} missing hs6_code")
        if "records" not in p_data: errors.append(f"Product {hs6} missing records")
        
        for r_key, r_data in p_data.get("records", {}).items():
            # Check UUID
            ruuid = r_data.get("record_uuid")
            if not ruuid: errors.append(f"Record {hs6}/{r_key} missing record_uuid")
            if ruuid in uuids: errors.append(f"Duplicate record_uuid: {ruuid}")
            uuids.add(ruuid)
            
            # Check mandatory fields
            for field in ["year", "trade_flow", "partner", "top_exporters", "totals", "risk_summary", "source", "warnings"]:
                if field not in r_data: errors.append(f"Record {hs6}/{r_key} missing {field}")
            
            # Check exporters
            top_exporters = r_data.get("top_exporters", [])
            prev_qty = float('inf')
            sum_qty = 0.0
            sum_shares = 0.0
            for i, exp in enumerate(top_exporters, 1):
                for efield in ["rank", "reporter", "quantity", "quantity_unit", "share_of_top5_pct"]:
                    if efield not in exp: errors.append(f"Exporter in {hs6}/{r_key} missing {efield}")
                
                # Sorting check
                qty = exp.get("quantity", 0)
                if qty > prev_qty:
                    errors.append(f"Exporters in {hs6}/{r_key} not sorted by quantity descending")
                prev_qty = qty
                sum_qty += qty
                sum_shares += exp.get("share_of_top5_pct", 0)
                
                # Rank check
                if exp.get("rank") != i:
                    errors.append(f"Rank mismatch in {hs6}/{r_key}: expected {i}, got {exp.get('rank')}")

            # Total quantity check
            total_qty = r_data.get("totals", {}).get("total_top5_quantity", 0)
            if abs(sum_qty - total_qty) > 0.01:
                errors.append(f"Total quantity mismatch in {hs6}/{r_key}: sum={sum_qty}, stored={total_qty}")
            
            # Concentration check
            concen = r_data.get("risk_summary", {}).get("concentration_top1_pct", 0)
            if top_exporters:
                rank1_share = top_exporters[0].get("share_of_top5_pct", 0)
                if abs(concen - rank1_share) > 0.01:
                    errors.append(f"Concentration mismatch in {hs6}/{r_key}: summary={concen}, rank1={rank1_share}")
            
            # Share sum check
            if top_exporters and abs(sum_shares - 100.0) > 0.5:
                errors.append(f"Shares do not sum to ~100 in {hs6}/{r_key}: sum={sum_shares}")

            # Check key consistency
            expected_key = db.make_record_key(r_data.get("year"), r_data.get("trade_flow"), r_data.get("partner"))
            if r_key != expected_key:
                errors.append(f"Key mismatch for {hs6}: {r_key} != {expected_key}")

    if errors:
        print("\n".join(errors[:20])) # Show first 20 errors
        if len(errors) > 20: print(f"... and {len(errors)-20} more")
        print("Validation: FAIL")
    else:
        print(f"Validated {len(products)} products and {len(uuids)} records.")
        print("Validation: PASS")

if __name__ == "__main__":
    validate_db()
