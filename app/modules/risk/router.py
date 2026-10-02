"""
Risk Router — API endpoint for supply chain risk assessment.
"""

from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .engine import (
    ReagentRiskInput,
    RiskRequest,
    run_risk_assessment,
    update_reagent_mapping,
)
from .risk_config import DEFAULT_LEAD_TIME_INCREASE_DAYS, DEFAULT_TARIFF_PCT
from .scenario import compute_scenario, items_from_assessment

# API Routes

router = APIRouter(prefix="/api/risk", tags=["risk"])


@router.post("/assess")
def assess_risk(request: RiskRequest):
    """Assess geographic supply chain risk for a list of reagents."""
    return run_risk_assessment(request.reagents)


class ScenarioSpec(BaseModel):
    type: Literal["dominant_supplier_loss", "country_disruption", "tariff", "lead_time"]
    # Required for country_disruption; optional for tariff / lead_time (blank =
    # each reagent's dominant supplier country); ignored for dominant loss.
    country: Optional[str] = None
    tariff_pct: float = Field(DEFAULT_TARIFF_PCT, ge=0, le=1000)
    lead_time_increase_days: float = Field(DEFAULT_LEAD_TIME_INCREASE_DAYS, ge=0, le=3650)


class ScenarioRequest(BaseModel):
    reagents: List[ReagentRiskInput]
    scenario: ScenarioSpec


@router.post("/scenario")
def run_scenario(request: ScenarioRequest):
    """Deterministic scenario / shock analysis on the assessed reagents.

    Re-runs the assessment so the scenario uses exactly the supplier shares
    and provenance the Risk Audit shows, then applies the shock.
    """
    spec = request.scenario.model_dump() if hasattr(request.scenario, "model_dump") else request.scenario.dict()
    assessment = run_risk_assessment(request.reagents)
    try:
        return compute_scenario(items_from_assessment(assessment["reagents"]), spec)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


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
