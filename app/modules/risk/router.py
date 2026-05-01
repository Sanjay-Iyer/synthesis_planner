"""
Risk Router — API endpoint for supply chain risk assessment.
"""
from fastapi import APIRouter
from .engine import RiskRequest, run_risk_assessment

router = APIRouter(prefix="/api/risk", tags=["risk"])


@router.post("/assess")
def assess_risk(request: RiskRequest):
    """Assess geographic supply chain risk for a list of reagents."""
    return run_risk_assessment(request.reagents)
