"""
Synthesis Router — API endpoints for stoichiometry and cost analysis.
"""
from fastapi import APIRouter
from .engine import SynthesisProject, calculate_engine, audit_optimization

router = APIRouter(prefix="/api/synthesis", tags=["synthesis"])


@router.post("/estimate")
def estimate_synthesis(project: SynthesisProject):
    """Scale-up cost estimation for a synthesis route."""
    return calculate_engine(project)


@router.post("/audit")
def run_audit(project: SynthesisProject):
    """Yield sensitivity audit — find where to optimize."""
    return audit_optimization(project)
