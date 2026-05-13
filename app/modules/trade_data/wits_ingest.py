import pandas as pd
import os
import json
from . import db
from datetime import datetime, timezone

from typing import List, Dict

def parse_wits_file(xlsx_path: str) -> List[dict]:
    """Returns one dict per unique HS6 code in the file."""
    # Real data lives on By-HS6Product
    try:
        df = pd.read_excel(xlsx_path, sheet_name='By-HS6Product', dtype={'ProductCode': str})
    except ValueError:
        raise ValueError("Sheet 'By-HS6Product' is missing")
    
    required_cols = [
        'Reporter', 'TradeFlow', 'ProductCode', 'Product Description', 
        'Year', 'Partner', 'Trade Value 1000USD', 'Quantity', 'Quantity Unit'
    ]
    
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Required column '{col}' is missing")
    
    # Clean ProductCode: pad to 6 chars
    df['ProductCode'] = df['ProductCode'].astype(str).str.zfill(6)
    
    # Filter strictly: TradeFlow == Export AND Partner.strip() == World
    df['PartnerClean'] = df['Partner'].astype(str).str.strip()
    mask = (df['TradeFlow'].str.strip() == 'Export') & (df['PartnerClean'] == 'World')
    df_filtered = df[mask].copy()
    
    if df_filtered.empty:
        raise ValueError("No rows survive the Export+World filter")
    
    results = []
    for hs6, group in df_filtered.groupby('ProductCode'):
        # Validate same Year and same Quantity Unit
        years = group['Year'].unique()
        if len(years) > 1:
            raise ValueError(f"Multiple Years appear for HS6 {hs6}")
        
        # Check units but only for rows that HAVE quantity
        units = group[group['Quantity'].notna()]['Quantity Unit'].unique()
        if len(units) > 1:
            raise ValueError(f"Multiple Quantity Units appear for HS6 {hs6}")
        
        product_desc = group['Product Description'].iloc[0]
        year = str(years[0])
        unit = units[0] if len(units) > 0 else group['Quantity Unit'].iloc[0]
        
        # Split into valid and excluded (no quantity)
        valid_rows = group[group['Quantity'].notna()].copy()
        excluded_rows = group[group['Quantity'].isna()].copy()
        
        # Sort valid by Quantity descending
        valid_rows = valid_rows.sort_values(by='Quantity', ascending=False)
        top_5 = valid_rows.head(5)
        
        total_top5_qty = float(top_5['Quantity'].sum())
        
        top_exporters = []
        for i, (idx, row) in enumerate(top_5.iterrows(), 1):
            share = (float(row['Quantity']) / total_top5_qty * 100) if total_top5_qty > 0 else 0
            top_exporters.append({
                "rank": i,
                "reporter": row['Reporter'],
                "quantity": float(row['Quantity']),
                "trade_value_1000_usd": float(row['Trade Value 1000USD']),
                "share_of_top5_pct": round(share, 2)
            })
            
        excluded_no_quantity = []
        for idx, row in excluded_rows.iterrows():
            excluded_no_quantity.append({
                "reporter": row['Reporter'],
                "trade_value_1000_usd": float(row['Trade Value 1000USD'])
            })
            
        concentration_top1 = top_exporters[0]['share_of_top5_pct'] if top_exporters else 0
        
        results.append({
            "hs6_code": hs6,
            "product_description": product_desc,
            "year": year,
            "quantity_unit": unit,
            "top_exporters": top_exporters,
            "excluded_no_quantity": excluded_no_quantity,
            "total_top5_quantity": total_top5_qty,
            "concentration_top1_pct": concentration_top1,
            "top_n_actual": len(top_exporters)
        })
        
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
        "warnings": []
    }
    
    for item in parsed_results:
        hs6 = item["hs6_code"]
        year = item["year"]
        
        if hs6 not in database["trade_data"]:
            database["trade_data"][hs6] = {
                "hs6_code": hs6,
                "product_description": item["product_description"],
                "years": {}
            }
            
        is_new = year not in database["trade_data"][hs6]["years"]
        if is_new:
            summary["new_entries"].append(hs6)
        else:
            summary["updated_entries"].append(hs6)
            
        # Check warnings
        if item["top_n_actual"] < 5:
            summary["warnings"].append(f"HS {hs6}: Fewer than 5 valid rows available ({item['top_n_actual']})")
            
        # EU warning
        reporters = [e["reporter"] for e in item["top_exporters"]]
        if "European Union" in reporters:
            summary["warnings"].append(f"HS {hs6}: 'European Union' appears alongside member states in top exporters")
            
        # Excluded outranks warning
        if item["top_exporters"] and item["excluded_no_quantity"]:
            min_top5_val = min(e["trade_value_1000_usd"] for e in item["top_exporters"])
            for excl in item["excluded_no_quantity"]:
                if excl["trade_value_1000_usd"] > min_top5_val:
                    summary["warnings"].append(f"HS {hs6}: {excl['reporter']} excluded but has higher trade value than some top-5 exporters")
                    item["data_quality_note"] = f"{excl['reporter']} excluded — no quantity reported"
                    break

        database["trade_data"][hs6]["years"][year] = {
            "trade_flow": "Export",
            "partner": "World",
            "quantity_unit": item["quantity_unit"],
            "source_file": source_filename,
            "ingested_at": ingested_at,
            "top_n_actual": item["top_n_actual"],
            "top_exporters": item["top_exporters"],
            "excluded_no_quantity": item["excluded_no_quantity"],
            "total_top5_quantity": item["total_top5_quantity"],
            "concentration_top1_pct": item["concentration_top1_pct"]
        }
        
    db.save_atomic(database, db_path)
    return summary
