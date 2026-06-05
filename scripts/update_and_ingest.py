import sys
import os
import sqlite3

# Add project root to path
sys.path.append(os.getcwd())

from app.modules.trade_data.wits_ingest import ingest
from app.modules.database.db import connect_db, normalize_name

def update_db():
    print("Updating database and ingesting trade data...")
    
    # 1. Ingest new Excel files
    data_dir = "/home/sanjay/AV/synthesis-architect/database/data_to_add"
    for filename in os.listdir(data_dir):
        if filename.endswith(".xlsx"):
            path = os.path.join(data_dir, filename)
            try:
                print(f"Ingesting {filename}...")
                summary = ingest(path)
                print(f"  Result: New={len(summary['new_entries'])}, Updated={len(summary['updated_entries'])}")
            except Exception as e:
                print(f"  Error ingesting {filename}: {e}")

    # 2. Update compounds table with HS6 mappings
    mappings = {
        "Germanium dioxide catalyst": "282560",
        "PET Intermediate (Oligomer)": "390760",
        "High-Performance UV Stabilizer": "381239",
        "Manganese(II) acetate": "291529",
        "Antimony trioxide catalyst": "282580",
        "Nitrogen Gas (UHP Grade)": "280430"
    }
    
    conn = connect_db()
    cursor = conn.cursor()
    
    for name, hs6 in mappings.items():
        norm_name = normalize_name(name)
        # Check if exists
        cursor.execute("SELECT uuid FROM compounds WHERE normalized_name = ?", (norm_name,))
        if cursor.fetchone():
            print(f"Updating {name} with HS6 {hs6}...")
            cursor.execute("UPDATE compounds SET hs6_code = ? WHERE normalized_name = ?", (hs6, norm_name))
        else:
            # If not exists, insert it
            import uuid
            print(f"Inserting {name} with HS6 {hs6}...")
            cursor.execute("""
                INSERT INTO compounds (uuid, name, normalized_name, hs6_code, first_seen, last_seen)
                VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
            """, (str(uuid.uuid4()), name, norm_name, hs6))
            
    conn.commit()
    conn.close()
    print("Database update complete.")

if __name__ == "__main__":
    update_db()
