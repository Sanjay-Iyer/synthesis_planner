"""
Risk Assessment Engine — Supply Chain Geographic Risk Analysis.
Migrated from risk_audit_folder/reagent_risk_tool.py
"""
import os
import math
import json
import sqlite3
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
    origin: Optional[str] = None
    mass_g: float = 0.0
    cost: float = 0.0
    # Advanced fields
    lead_time_days: int = 14
    hazard_score: int = 5  # 1-10 (Toxicity/Handling)
    regulatory_score: int = 5 # 1-10 (EPA/TSCA/Export Controls)
    supplier_count: int = 3
    substitutability: int = 5 # 1-10 (10 = hardest to replace)


class RiskRequest(BaseModel):
    reagents: List[ReagentRiskInput]


class RiskBreakdown(BaseModel):
    geographic: float
    operational: float
    regulatory: float
    economic: float


class ReagentRiskResult(BaseModel):
    name: str
    cas: str
    primary_origin: str
    stability_score: float
    mass_g: float
    cost: float
    risk_index: float
    risk_level: str
    hs_code: Optional[str] = None
    # New analytics fields
    breakdown: RiskBreakdown
    lead_time: int
    hazard: int
    substitutability: int
    warnings: List[str] = []
    supply_chain_data: Optional[dict] = None


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
# TRADE DATA & HS6 MAPPING
# =================================================================

def get_hs6_for_inchikey(inchikey: str) -> Optional[str]:
    """Look up HS6 code for a given InChIKey."""
    path = "/home/sanjay/AV/synthesis-architect/database/compound_hs6_map.json"
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r') as f:
            data = json.load(f)
            return data.get("mappings", {}).get(inchikey, {}).get("hs6_code")
    except Exception:
        return None

def get_supply_chain_concentration(hs6_code: str, year: int | None = None) -> dict:
    """
    Returns concentration metrics and risk flags for an HS6 code.
    Risk flag thresholds:
    - HIGH if top-1 share > 50% OR top-3 share > 80%
    - MEDIUM if top-1 share > 30% OR top-3 share > 60%
    - LOW otherwise
    """
    from app.modules.trade_data import db as trade_db
    
    data = trade_db.get_exporters(hs6_code, year)
    if not data:
        return {"status": "no_trade_data"}
        
    top_exporters = data.get("top_exporters", [])
    if not top_exporters:
        return {"status": "no_trade_data"}
        
    # Calculate top-1 and top-3 shares
    top1_share = top_exporters[0]["share_of_top5_pct"] if len(top_exporters) >= 1 else 0
    top3_share = sum(e["share_of_top5_pct"] for e in top_exporters[:3])
    
    risk_flag = "LOW"
    if top1_share > 50 or top3_share > 80:
        risk_flag = "HIGH"
    elif top1_share > 30 or top3_share > 60:
        risk_flag = "MEDIUM"
        
    # Data quality note
    note = None
    excluded = data.get("excluded_no_quantity", [])
    if excluded:
        # Check if any major player was excluded
        top1_val = top_exporters[0]["trade_value_1000_usd"]
        for excl in excluded:
            if excl["trade_value_1000_usd"] > (top1_val * 0.5):
                note = f"{excl['reporter']} (major exporter) excluded — no quantity reported"
                break

    return {
        "status": "success",
        "hs6_code": hs6_code,
        "year": data.get("year"),
        "top_exporters": top_exporters,
        "concentration_top1_pct": top1_share,
        "concentration_risk_flag": risk_flag,
        "data_quality_note": note
    }

# =================================================================
# RISK CALCULATION
# =================================================================

# CRITICAL MATERIALS & REGULATORY FLAGS (Static database for this demo)
CRITICAL_CAS = {
    "7440-06-4": "Platinum (Strategic Concentration: South Africa)",
    "7440-05-3": "Palladium (Strategic Concentration: Russia/SA)",
    "26628-22-8": "Sodium Azide (Niche Producer / High Hazard)",
}

REGULATORY_CAS = {
    "75-09-2": "DCM (EPA TSCA Section 6 - Commercial Ban in force)",
    "872-50-4": "NMP (Active TSCA Review)",
    "79-01-6": "TCE (Proposed Prohibition)",
    "50-00-0": "Formaldehyde (Active TSCA Review)",
}


def label_risk(risk_index: float) -> str:
    """Classify risk level based on aggregated score."""
    if risk_index > 150:
        return "HIGH (Critical Supply Chain)"
    elif risk_index > 100:
        return "MEDIUM-HIGH (Elevated Concern)"
    elif risk_index > 50:
        return "MEDIUM (Monitored)"
    else:
        return "LOW (Stable)"


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

        if r.origin:
            origin = r.origin
        
        if r.cas:
            mapping_row = df_mapping[df_mapping['Reagent_CAS'] == r.cas]
            if not mapping_row.empty:
                if not r.origin: # Only override if user didn't provide one
                    origin = mapping_row.iloc[0].get('Primary_Origin', 'Unknown')
                hs_code = str(mapping_row.iloc[0].get('HS_Code', ''))

            if stability_row.empty:
                stability = 50.0 # fallback
            else:
                stability = float(stability_row.iloc[0]['Stability_Score'])

        # Trade Data Integration (Phase 3)
        supply_chain_data = None
        # 1. Try to get InChIKey from Compound DB
        from app.modules.database.db import connect_db, normalize_name
        conn = connect_db()
        cursor = conn.cursor()
        norm_name = normalize_name(r.name)
        cursor.execute("SELECT inchikey, hs6_code FROM compounds WHERE normalized_name = ?", (norm_name,))
        row = cursor.fetchone()
        conn.close()
        
        target_hs6 = None
        if row:
            ikey = row["inchikey"]
            target_hs6 = row["hs6_code"] # Maybe it's already there?
            if not target_hs6 and ikey:
                target_hs6 = get_hs6_for_inchikey(ikey)
        
        if target_hs6:
            supply_chain_data = get_supply_chain_concentration(target_hs6)
        else:
            # Check if we have data by name hint in our mapping? No, user said InChIKey.
            supply_chain_data = {"status": "no_hs6_mapping"}

        # Multi-dimensional Risk Calculation (Enhanced)
        warnings = []
        if origin == "Unknown":
            warnings.append("Unverified Origin (Opacity Risk)")
        
        if r.cas in CRITICAL_CAS:
            warnings.append(f"CRITICAL MATERIAL: {CRITICAL_CAS[r.cas]}")
        
        if r.cas in REGULATORY_CAS:
            warnings.append(f"REGULATORY FLAG: {REGULATORY_CAS[r.cas]}")

        # 1. Geographic Risk & Opacity (0-100)
        # Apply Opacity Multiplier (1.5x) if origin is unknown
        geo_base = 100 - stability
        if origin == "Unknown":
            geo_risk = min(100, geo_base * 1.5)
        else:
            geo_risk = geo_base
        
        # 2. Operational Risk (Lead time + Supplier scarcity)
        lt_risk = min(100, (r.lead_time_days / 30) * 100)
        scarcity_risk = max(0, 100 - (r.supplier_count * 20))
        # Boost scarcity if it's a critical mineral
        if r.cas in CRITICAL_CAS:
            scarcity_risk = 100
        oper_risk = (lt_risk * 0.5) + (scarcity_risk * 0.5)
        
        # 3. Regulatory & Hazard Risk (0-100)
        # Combine Hazard Score and Regulatory Score
        # Auto-boost for flagged materials (DCM, etc)
        reg_val = r.regulatory_score
        if r.cas in REGULATORY_CAS:
            reg_val = 10  # Max risk
        reg_risk = (r.hazard_score * 4) + (reg_val * 6)
        
        # 4. Economic Risk (Substitutability & Cost-at-risk)
        # Harder to replace = higher risk
        econ_risk = r.substitutability * 10

        # Weighted Component Score (0-100)
        # Shifting weights to emphasize Regulatory and Geographic risk as requested
        composite_score = (
            geo_risk * 0.30 + 
            oper_risk * 0.20 + 
            reg_risk * 0.30 + 
            econ_risk * 0.20
        )

        # Final Risk Index: Composite Score * Exposure Multiplier
        # Exposure multiplier accounts for Mass and Cost influence
        # Logarithmic mass + normalized cost factor
        exposure_multiplier = (math.log10(r.mass_g + 1) * 0.7) + (math.log10(r.cost + 1) * 0.3) + 1
        risk_index = composite_score * exposure_multiplier

        results.append(ReagentRiskResult(
            name=r.name,
            cas=r.cas,
            primary_origin=origin,
            stability_score=stability,
            mass_g=r.mass_g,
            cost=r.cost,
            risk_index=round(risk_index, 2),
            risk_level=label_risk(risk_index),
            hs_code=hs_code,
            lead_time=r.lead_time_days,
            hazard=r.hazard_score,
            substitutability=r.substitutability,
            warnings=warnings,
            breakdown=RiskBreakdown(
                geographic=round(geo_risk, 1),
                operational=round(oper_risk, 1),
                regulatory=round(reg_risk, 1),
                economic=round(econ_risk, 1)
            ),
            supply_chain_data=supply_chain_data
        ))

    # Summary statistics
    high_risk = [r for r in results if "HIGH" in r.risk_level and "MEDIUM" not in r.risk_level]
    total_risk_exposure = sum(r.risk_index for r in results)

    return {
        "reagents": [r.model_dump() if hasattr(r, "model_dump") else r.dict() for r in results],
        "summary": {
            "total_reagents": len(results),
            "high_risk_count": len(high_risk),
            "total_risk_exposure": round(total_risk_exposure, 2),
            "highest_risk": max(results, key=lambda x: x.risk_index).name if results else None
        }
    }


def update_reagent_mapping(cas: str, origin: str) -> bool:
    """Persist a new or updated CAS -> Origin mapping to CSV."""
    if not cas or not origin:
        return False
    
    path = os.path.join(DATA_DIR, "reagent_mapping.csv")
    df = load_reagent_mapping()
    
    # Check if CAS already exists
    if cas in df['Reagent_CAS'].values:
        df.loc[df['Reagent_CAS'] == cas, 'Primary_Origin'] = origin
    else:
        # Add new row
        new_row = pd.DataFrame({'Reagent_CAS': [cas], 'HS_Code': [''], 'Primary_Origin': [origin]})
        df = pd.concat([df, new_row], ignore_index=True)
    
    df.to_csv(path, index=False, encoding='utf-8-sig')
    return True
