import sys
import os
import argparse
import glob
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.modules.trade_data import wits_ingest

def main():
    parser = argparse.ArgumentParser(description="Ingest WITS Excel files into the trade database.")
    parser.add_argument("path", help="Path to an .xlsx file or a glob pattern (e.g. 'data/*.xlsx')")
    parser.add_argument("--dry-run", action="store_true", help="Parse and print results without writing to disk")
    
    args = parser.parse_args()
    
    files = []
    if '*' in args.path:
        files = glob.glob(args.path)
    elif os.path.isdir(args.path):
        files = glob.glob(os.path.join(args.path, "*.xlsx"))
    else:
        files = [args.path]
        
    if not files:
        print(f"No files found for path: {args.path}")
        sys.exit(1)
        
    print(f"Processing {len(files)} file(s)...")
    
    for f in files:
        try:
            if args.dry_run:
                results = wits_ingest.parse_wits_file(f)
                for item in results:
                    excluded_names = [e["reporter"] for e in item["excluded_no_quantity"]]
                    excluded_str = f", {', '.join(excluded_names[:2])} excluded (no quantity)" if excluded_names else ""
                    print(f"DRY-RUN: ✓ HS {item['hs6_code']} ({item['product_description'][:30]}): {item['top_n_actual']} exporters{excluded_str}, {item['year']}")
            else:
                summary = wits_ingest.ingest(f)
                # We need to get the parsed results again or modify ingest to return more detail
                # For simplicity, let's just use the summary
                for hs6 in summary["new_entries"] + summary["updated_entries"]:
                    # We'll just print the success for each HS6 in the summary
                    status = "New" if hs6 in summary["new_entries"] else "Updated"
                    print(f"✓ HS {hs6}: {status} entry ingested from {os.path.basename(f)}")
                
                for w in summary["warnings"]:
                    print(f"  ⚠ WARNING: {w}")
                    
        except Exception as e:
            print(f"✗ ERROR processing {os.path.basename(f)}: {str(e)}")

if __name__ == "__main__":
    main()
