from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional
import sqlite3
import json

from .models import (
    SaveRouteRequest, SaveRouteResponse, ValidateRouteResponse, 
    CompoundRecord, DatabaseSummaryResponse
)
from .db import (
    connect_db, save_route_transaction, validate_route_without_saving, 
    DB_PATH, get_utc_now
)

router = APIRouter(prefix="/api/database", tags=["database"])

@router.post("/save-route", response_model=SaveRouteResponse)
async def api_save_route(request: SaveRouteRequest):
    """Save a synthesis route and its analysis results to the database."""
    conn = connect_db()
    try:
        # Run a validation first to get counts
        validation = validate_route_without_saving(request)
        
        # Execute save transaction
        conn.execute("BEGIN")
        result = save_route_transaction(conn, request)
        conn.commit()
        
        return {
            "success": True,
            "route_uuid": result["route_uuid"],
            "route_hash": result["route_hash"],
            "analysis_run_uuid": result["analysis_run_uuid"],
            "new_compounds": validation["new_compounds"],
            "updated_compounds": validation["updated_compounds"],
            "ambiguous_compounds": validation["ambiguous_compounds"],
            "compound_assignments": validation["compound_assignments"]
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.post("/validate-route", response_model=ValidateRouteResponse)
async def api_validate_route(request: SaveRouteRequest):
    """Dry-run the save operation to see what would happen."""
    try:
        return validate_route_without_saving(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/compounds", response_model=List[CompoundRecord])
async def api_get_compounds(q: Optional[str] = Query(None)):
    """Retrieve all compounds or search by name/SMILES/SELFIES."""
    conn = connect_db()
    cursor = conn.cursor()
    try:
        query = "SELECT * FROM compounds"
        params = []
        if q:
            query += " WHERE name LIKE ? OR smiles LIKE ? OR selfies LIKE ?"
            search = f"%{q}%"
            params = [search, search, search]
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            d = dict(row)
            # Find routes where this compound is used
            cursor.execute("SELECT DISTINCT route_uuid FROM step_reagents WHERE compound_uuid = ?", (d["uuid"],))
            d["seen_in_routes"] = [r["route_uuid"] for r in cursor.fetchall()]
            results.append(d)
        return results
    finally:
        conn.close()

@router.get("/routes")
async def api_get_routes():
    """Retrieve all saved routes with their latest analysis summary."""
    conn = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT r.*, 
                   (SELECT COUNT(*) FROM analysis_runs WHERE route_uuid = r.uuid) as run_count,
                   (SELECT MAX(created_at) FROM analysis_runs WHERE route_uuid = r.uuid) as last_run_at
            FROM routes r
            ORDER BY r.updated_at DESC
        """)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

@router.get("/routes/{route_uuid}")
async def api_get_route_detail(route_uuid: str):
    """Retrieve full details for a specific route."""
    conn = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM routes WHERE uuid = ?", (route_uuid,))
        route = cursor.fetchone()
        if not route:
            raise HTTPException(status_code=404, detail="Route not found")
        
        res = dict(route)
        
        # Get Steps
        cursor.execute("SELECT * FROM route_steps WHERE route_uuid = ? ORDER BY step_number", (route_uuid,))
        steps = []
        for s_row in cursor.fetchall():
            s = dict(s_row)
            # Get Reagents for this step
            cursor.execute("SELECT * FROM step_reagents WHERE step_uuid = ?", (s["uuid"],))
            s["reagents"] = [dict(r) for r in cursor.fetchall()]
            steps.append(s)
        
        res["steps"] = steps
        
        # Get Analysis Runs
        cursor.execute("SELECT * FROM analysis_runs WHERE route_uuid = ? ORDER BY created_at DESC", (route_uuid,))
        res["analysis_runs"] = [dict(a) for a in cursor.fetchall()]
        
        return res
    finally:
        conn.close()

@router.get("/analysis-runs")
async def api_get_analysis_runs(route_uuid: Optional[str] = None):
    """Retrieve analysis runs, optionally filtered by route."""
    conn = connect_db()
    cursor = conn.cursor()
    try:
        query = "SELECT * FROM analysis_runs"
        params = []
        if route_uuid:
            query += " WHERE route_uuid = ?"
            params = [route_uuid]
        query += " ORDER BY created_at DESC"
        
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

@router.get("/summary", response_model=DatabaseSummaryResponse)
async def api_get_summary():
    """Return high-level database metrics."""
    conn = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM compounds")
        comp_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM routes")
        route_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM analysis_runs")
        run_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM compounds WHERE is_defined_structure = 0")
        ambig_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT uuid, route_label, target_molecule, updated_at FROM routes ORDER BY updated_at DESC LIMIT 5")
        recent = [dict(r) for r in cursor.fetchall()]
        
        cursor.execute("""
            SELECT c.name, COUNT(DISTINCT r.route_uuid) as reuse_count 
            FROM compounds c 
            JOIN step_reagents r ON c.uuid = r.compound_uuid 
            GROUP BY c.uuid 
            ORDER BY reuse_count DESC LIMIT 5
        """)
        reused = [dict(r) for r in cursor.fetchall()]
        
        return {
            "compound_count": comp_count,
            "route_count": route_count,
            "analysis_run_count": run_count,
            "ambiguous_compound_count": ambig_count,
            "most_recent_routes": recent,
            "most_reused_compounds": reused
        }
    finally:
        conn.close()
