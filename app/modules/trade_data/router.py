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
    """Return high-level trade database metrics."""
    from . import db
    database = db.load()
    trade_data = database.get("trade_data", {})
    
    hs6_count = len(trade_data)
    # Count unique years across all products
    all_years = set()
    for hs6 in trade_data:
        all_years.update(trade_data[hs6].get("years", {}).keys())
        
    return {
        "hs6_code_count": hs6_count,
        "years_available": sorted(list(all_years)),
        "last_updated": database.get("last_updated")
    }
