from fastapi import APIRouter, UploadFile, File, HTTPException
import os
import shutil
from . import wits_ingest

router = APIRouter(prefix="/api/trade", tags=["trade"])

@router.post("/import")
async def import_wits_data(file: UploadFile = File(...)):
    """Upload one Excel file, parse it, and save to the trade database."""
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="Only Excel files (.xlsx, .xls) are supported.")
    
    # Save to temp file
    temp_path = f"/tmp/{file.filename}"
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    try:
        summary = wits_ingest.ingest(temp_path)
        return {
            "success": True,
            "filename": file.filename,
            "summary": summary
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

@router.get("/summary")
async def get_trade_summary():
    """Return high-level trade database metrics (v1.1.0)."""
    from . import db
    database = db.load()
    products = database.get("products", {})
    
    product_count = len(products)
    record_count = 0
    all_years = set()
    high_risk = 0
    med_risk = 0
    low_risk = 0
    latest_ingest = None

    for hs6, p_data in products.items():
        records = p_data.get("records", {})
        record_count += len(records)
        for r_key, r_data in records.items():
            all_years.add(r_data.get("year"))
            score = r_data.get("risk_summary", {}).get("concentration_score")
            if score == "High": high_risk += 1
            elif score == "Medium": med_risk += 1
            elif score == "Low": low_risk += 1
            
            ingest_at = r_data.get("source", {}).get("ingested_at")
            if ingest_at:
                if not latest_ingest or ingest_at > latest_ingest:
                    latest_ingest = ingest_at
                    
    return {
        "product_count": product_count,
        "record_count": record_count,
        "years_available": sorted(list(all_years)),
        "latest_ingested_at": latest_ingest,
        "high_concentration_count": high_risk,
        "medium_concentration_count": med_risk,
        "low_concentration_count": low_risk,
        "schema_version": database.get("metadata", {}).get("schema_version")
    }

@router.get("/exports")
async def list_trade_exports():
    """Return a flattened list of all trade export record summaries."""
    from . import db
    database = db.load()
    products = database.get("products", {})
    
    summaries = []
    for hs6, p_data in products.items():
        desc = p_data.get("product_description")
        for r_key, r_data in p_data.get("records", {}).items():
            risk = r_data.get("risk_summary", {})
            summaries.append({
                "hs6_code": hs6,
                "product_description": desc,
                "record_key": r_key,
                "record_uuid": r_data.get("record_uuid"),
                "year": r_data.get("year"),
                "trade_flow": r_data.get("trade_flow"),
                "partner": r_data.get("partner"),
                "top_country": risk.get("top_country"),
                "concentration_score": risk.get("concentration_score"),
                "concentration_top1_pct": risk.get("concentration_top1_pct"),
                "total_top5_quantity": r_data.get("totals", {}).get("total_top5_quantity"),
                "quantity_unit": r_data.get("quantity_unit")
            })
    return summaries

@router.get("/exports/{record_uuid}")
async def get_trade_export_by_uuid(record_uuid: str):
    """Fetch a full trade record by its unique UUID."""
    from . import db
    database = db.load()
    for hs6, p_data in database.get("products", {}).items():
        for r_key, r_data in p_data.get("records", {}).items():
            if r_data.get("record_uuid") == record_uuid:
                # Inject product info for context
                return {
                    "hs6_code": hs6,
                    "product_description": p_data.get("product_description"),
                    "record": r_data
                }
    raise HTTPException(status_code=404, detail=f"Record with UUID {record_uuid} not found")
