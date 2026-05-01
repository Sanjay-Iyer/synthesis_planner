"""
Risk Assessment Engine — Supply Chain Geographic Risk Analysis.
Migrated from risk_audit_folder/reagent_risk_tool.py
"""
import os
import math
import pandas as pd
from pydantic import BaseModel
from typing import List, Optional

# Path to reference data files
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


# =================================================================
# DATA MODELS
# =================================================================

class ReagentRiskInput(BaseModel):
    name: str
    cas: str = ""
    mass_g: float = 0.0
    cost: float = 0.0


class RiskRequest(BaseModel):
    reagents: List[ReagentRiskInput]


class RiskResult(BaseModel):
    name: str
    cas: str
    mass_g: float
    cost: float
    hs_code: Optional[str] = None
    primary_origin: str = "Unknown"
    stability_score: float = 50.0
    risk_index: float = 0.0
    bubble_size: float = 15.0
    risk_level: str = "UNKNOWN"


# =================================================================
# REFERENCE DATA
# =================================================================

def load_reagent_mapping() -> pd.DataFrame:
    """Load the CAS → HS Code → Country mapping table."""
    path = os.path.join(DATA_DIR, "reagent_mapping.csv")
    if os.path.exists(path):
        return pd.read_csv(path)

    # Generate default if missing
    mapping_data = {
        'Reagent_CAS': ['7440-06-4', '775-12-2', '7447-39-4', '7681-65-4', '106-92-3'],
        'HS_Code': ['3815.12', '2931.90', '2827.39', '2827.60', '2910.90'],
        'Primary_Origin': ['South Africa', 'Germany', 'China', 'China', 'USA']
    }
    df = pd.DataFrame(mapping_data)
    df.to_csv(path, index=False, encoding='utf-8-sig')
    return df


def load_country_stability() -> pd.DataFrame:
    """Load country stability scores (0-100, based on World Bank WGI)."""
    path = os.path.join(DATA_DIR, "country_stability.csv")
    if os.path.exists(path):
        return pd.read_csv(path)

    # Generate default if missing
    stability_data = {
        'Country': ['Germany', 'USA', 'Japan', 'China', 'South Africa', 'Russia', 'Mexico', 'India', 'Chile'],
        'Stability_Score': [92, 85, 88, 48, 35, 15, 42, 52, 75]
    }
    df = pd.DataFrame(stability_data)
    df.to_csv(path, index=False, encoding='utf-8-sig')
    return df


# =================================================================
# RISK CALCULATION
# =================================================================

def label_risk(stability_score: float, risk_index: float) -> str:
    """Classify risk level based on stability and mass dependency."""
    if stability_score < 40:
        return "HIGH (Origin Vulnerability)"
    elif risk_index > 300:
        return "MEDIUM-HIGH (Mass Dependency)"
    elif stability_score < 70:
        return "MEDIUM (General Supply Chain)"
    else:
        return "LOW (Stable Source)"


def run_risk_assessment(reagents: List[ReagentRiskInput]) -> dict:
    """
    Perform geographic risk assessment on a list of reagents.
    Returns enriched reagent data with risk scores and summary stats.
    """
    df_mapping = load_reagent_mapping()
    df_stability = load_country_stability()

    results = []

    for r in reagents:
        # Look up country of origin via CAS number
        origin = "Unknown"
        hs_code = None
        stability = 50.0  # Default for unknown

        if r.cas:
            mapping_row = df_mapping[df_mapping['Reagent_CAS'] == r.cas]
            if not mapping_row.empty:
                origin = mapping_row.iloc[0].get('Primary_Origin', 'Unknown')
                hs_code = str(mapping_row.iloc[0].get('HS_Code', ''))

            stability_row = df_stability[df_stability['Country'] == origin]
            if not stability_row.empty:
                stability = float(stability_row.iloc[0]['Stability_Score'])

        # Calculate risk index: mass * (100 - stability) / 100
        risk_index = (r.mass_g * (100 - stability)) / 100
        bubble_size = math.sqrt(max(r.mass_g, 0)) + 15

        results.append(RiskResult(
            name=r.name,
            cas=r.cas,
            mass_g=r.mass_g,
            cost=r.cost,
            hs_code=hs_code,
            primary_origin=origin,
            stability_score=stability,
            risk_index=round(risk_index, 4),
            bubble_size=round(bubble_size, 2),
            risk_level=label_risk(stability, risk_index)
        ))

    # Summary statistics
    high_risk = [r for r in results if "HIGH" in r.risk_level and "MEDIUM" not in r.risk_level]
    total_risk_exposure = sum(r.risk_index for r in results)

    return {
        "reagents": [r.model_dump() for r in results],
        "summary": {
            "total_reagents": len(results),
            "high_risk_count": len(high_risk),
            "total_risk_exposure": round(total_risk_exposure, 2),
            "highest_risk": max(results, key=lambda x: x.risk_index).name if results else None
        }
    }
