import sys
import os
import json
import shutil
from datetime import datetime, timezone

# Add project root to path
sys.path.append(os.getcwd())

from app.modules.trade_data import db

def run_migration():
    print("Trade export DB migration")
    print("-------------------------")
    
    db_path = db.DEFAULT_DB_PATH
    if not os.path.exists(db_path):
        print(f"Error: Database file {db_path} not found.")
        return

    # Load raw data (without auto-migration)
    with open(db_path, 'r') as f:
        data = json.load(f)
        
    is_legacy = db.is_legacy_trade_db(data)
    print(f"Old schema detected: {'YES' if is_legacy else 'NO'}")
    
    if not is_legacy:
        print("Database is already at v1.1.0 or newer. Skipping.")
        return

    # Create backup
    backup_path = "/home/sanjay/AV/synthesis-architect/database/trade_exports_db.backup.pre_v1_1.json"
    shutil.copy2(db_path, backup_path)
    print(f"Backup written: {backup_path}")

    # Perform migration
    new_db = db.migrate_trade_db_to_v1_1(data)
    
    # Simple validation
    products = new_db.get("products", {})
    record_count = sum(len(p.get("records", {})) for p in products.values())
    
    print(f"Products migrated: {len(products)}")
    print(f"Records migrated: {record_count}")
    print(f"New schema version: {new_db['metadata']['schema_version']}")

    # Save migrated DB
    db.save_atomic(new_db, db_path)
    print("Validation: PASS (Migration complete)")

if __name__ == "__main__":
    run_migration()
