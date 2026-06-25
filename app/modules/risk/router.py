"""
Risk Router — API endpoint for supply chain risk assessment.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from .engine import RiskRequest, run_risk_assessment, update_reagent_mapping

# API Routes

router = APIRouter(prefix="/api/risk", tags=["risk"])


@router.post("/assess")
def assess_risk(request: RiskRequest):
    """Assess geographic supply chain risk for a list of reagents."""
    return run_risk_assessment(request.reagents)


class MappingUpdate(BaseModel):
    cas: str
    origin: str


@router.post("/update-mapping")
def update_mapping(data: MappingUpdate):
    """Save a new CAS-to-Origin mapping to the internal database."""
    success = update_reagent_mapping(data.cas, data.origin)
    return {"success": success}


@router.post("/lookup-origins")
def lookup_origins(request: RiskRequest):
    """Auto-fill suggested origins based on trade data and name matching."""
    from .engine import lookup_suggested_origins

    reagent_dicts = [r.dict() for r in request.reagents]
    return lookup_suggested_origins(reagent_dicts)


@router.get("/mappings")
def get_mappings():
    """Fetch the current CAS-to-Origin mapping database."""
    from .engine import load_reagent_mapping

    df = load_reagent_mapping()
    return df.to_dict(orient="records")
