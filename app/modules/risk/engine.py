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
    secondary_origin: Optional[str] = None
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
    secondary_origin: str = "Unknown"
    secondary_stability_score: float = 50.0
    mass_g: float
    cost: float
    risk_index: float
    secondary_risk_index: float = 0.0
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

def get_hs6_by_name_hint(name: str) -> Optional[str]:
    """Try to find an HS6 code by matching the name against name hints."""
    path = "/home/sanjay/AV/synthesis-architect/database/compound_hs6_map.json"
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r') as f:
            data = json.load(f)
            mappings = data.get("mappings", {})
            name_lower = name.lower()
            for key, val in mappings.items():
                hint = val.get("name_hint", "").lower()
                if hint and (hint in name_lower or name_lower in hint):
                    return val.get("hs6_code")
    except Exception:
        pass
    return None

def lookup_suggested_origins(reagent_inputs: List[dict]) -> List[dict]:
    """Look up suggested origins for a list of reagents based on trade data."""
    results = []
    df_mapping = load_reagent_mapping()
    
    for r in reagent_inputs:
        name = r.get("name", "")
        cas = r.get("cas", "")
        
        target_hs6 = None
        
        # 1. Try CAS Mapping
        if cas:
            mapping_row = df_mapping[df_mapping['Reagent_CAS'] == cas]
            if not mapping_row.empty:
                target_hs6 = str(mapping_row.iloc[0].get('HS_Code', ''))
        
        # 2. Try Name Hint
        if not target_hs6 and name:
            target_hs6 = get_hs6_by_name_hint(name)
            
        # 3. Try Database (normalized name)
        if not target_hs6 and name:
            try:
                from app.modules.database.db import connect_db, normalize_name
                conn = connect_db()
                cursor = conn.cursor()
                norm_name = normalize_name(name)
                cursor.execute("SELECT hs6_code, inchikey FROM compounds WHERE normalized_name = ?", (norm_name,))
                row = cursor.fetchone()
                if row:
                    target_hs6 = row["hs6_code"]
                    if not target_hs6 and row["inchikey"]:
                        target_hs6 = get_hs6_for_inchikey(row["inchikey"])
                conn.close()
            except: pass

        suggested = {"primary": "Unknown", "secondary": "Unknown", "hs6": target_hs6}
        if target_hs6:
            clean_hs6 = "".join(filter(str.isdigit, target_hs6)).zfill(6)
            suggested["hs6"] = clean_hs6
            concentration = get_supply_chain_concentration(clean_hs6)
            if concentration.get("status") == "success":
                exporters = concentration.get("top_exporters", [])
                if len(exporters) >= 1: suggested["primary"] = exporters[0]["reporter"]
                if len(exporters) >= 2: suggested["secondary"] = exporters[1]["reporter"]
        
        results.append(suggested)
    return results

def get_supply_chain_concentration(hs6_code: str, year: Optional[int] = None) -> dict:
    """
    Returns concentration metrics and risk flags for an HS6 code.
    Using the v1.1.0 schema structure.
    """
    from app.modules.trade_data import db as trade_db
    
    # Normalize HS6: digits only, padded to 6
    clean_hs6 = "".join(filter(str.isdigit, hs6_code)).zfill(6)
    
    db = trade_db.load()
    record = trade_db.get_trade_record(db, clean_hs6, year)
    
    if not record:
        return {"status": "no_trade_data"}
        
    top_exporters = record.get("top_exporters", [])
    if not top_exporters:
        return {"status": "no_trade_data"}
        
    risk_summary = record.get("risk_summary", {})
    top1_share = risk_summary.get("concentration_top1_pct", 0)
    
    # Simple thresholds for backward compatibility in results
    risk_flag = "LOW"
    if top1_share > 50:
        risk_flag = "HIGH"
    elif top1_share > 30:
        risk_flag = "MEDIUM"
        
    # Data quality note from source warnings
    note = None
    for warning in record.get("warnings", []):
        if warning.get("code") == "excluded_rows_missing_quantity":
            note = f"Data quality alert: {warning.get('count')} exporters excluded due to missing quantity."
            break

    return {
        "status": "success",
        "hs6_code": clean_hs6,
        "year": record.get("year"),
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
        # 1. Determine Origin (Priority: User > Mapping > DB > Fallback)
        origin = r.origin or "Unknown"
        secondary_origin = r.secondary_origin or "Unknown"
        hs_code_from_mapping = None
        
        if r.cas:
            mapping_row = df_mapping[df_mapping['Reagent_CAS'] == r.cas]
            if not mapping_row.empty:
                if not r.origin:
                    origin = mapping_row.iloc[0].get('Primary_Origin', 'Unknown')
                hs_code_from_mapping = str(mapping_row.iloc[0].get('HS_Code', ''))

        # 2. HS6 & Supply Chain Concentration (Defensive Handling)
        supply_chain_data = None
        warnings = []
        target_hs6 = hs_code_from_mapping
        
        try:
            from app.modules.database.db import connect_db, normalize_name
            conn = connect_db()
            cursor = conn.cursor()
            norm_name = normalize_name(r.name)
            
            cursor.execute("PRAGMA table_info(compounds)")
            cols = [c[1] for c in cursor.fetchall()]
            
            if "hs6_code" in cols:
                cursor.execute("SELECT inchikey, hs6_code, primary_origin, secondary_origin FROM compounds WHERE normalized_name = ?", (norm_name,))
            else:
                cursor.execute("SELECT inchikey FROM compounds WHERE normalized_name = ?")
            
            row = cursor.fetchone()
            
            if row:
                ikey = row["inchikey"]
                db_hs6 = row["hs6_code"] if "hs6_code" in cols else None
                if db_hs6:
                    target_hs6 = db_hs6
                elif ikey:
                    target_hs6 = get_hs6_for_inchikey(ikey)
                
                # If DB has origins and we don't have user/mapping input, use them
                if origin == "Unknown" and "primary_origin" in cols and row["primary_origin"]:
                    origin = row["primary_origin"]
                    secondary_origin = row["secondary_origin"] or "Unknown"
            
            if target_hs6:
                supply_chain_data = get_supply_chain_concentration(target_hs6)
                if supply_chain_data.get("status") == "success":
                    top_exporters = supply_chain_data.get("top_exporters", [])
                    if top_exporters:
                        # Trade Data Override
                        origin = top_exporters[0]["reporter"]
                        secondary_origin = top_exporters[1]["reporter"] if len(top_exporters) > 1 else "Unknown"
                        
                        # Sync back to DB for future use
                        if "primary_origin" in cols:
                            cursor.execute("UPDATE compounds SET primary_origin = ?, secondary_origin = ? WHERE normalized_name = ?", 
                                         (origin, secondary_origin, norm_name))
                            conn.commit()
            else:
                supply_chain_data = {"status": "no_hs6_mapping"}
                warnings.append(f"No HS6 code available for {r.name}; supply chain lookup skipped.")
            
            conn.close()
        except Exception as e:
            supply_chain_data = {"status": "error", "detail": str(e)}
            warnings.append(f"Technical error during HS6 lookup for {r.name}.")

        # 3. Stability Lookup for Primary & Secondary
        stability_row = df_stability[df_stability['Country'] == origin]
        if not stability_row.empty:
            stability = float(stability_row.iloc[0]['Stability_Score'])
        else:
            stability = 50.0 # Neutral default
            
        sec_stability_row = df_stability[df_stability['Country'] == secondary_origin]
        if not sec_stability_row.empty:
            sec_stability = float(sec_stability_row.iloc[0]['Stability_Score'])
        else:
            sec_stability = 50.0

        # Multi-dimensional Risk Calculation (Enhanced)
        if origin == "Unknown":
            warnings.append("Unverified Origin (Opacity Risk)")
        
        if r.cas in CRITICAL_CAS:
            warnings.append(f"CRITICAL MATERIAL: {CRITICAL_CAS[r.cas]}")
        
        if r.cas in REGULATORY_CAS:
            warnings.append(f"REGULATORY FLAG: {REGULATORY_CAS[r.cas]}")

        # 1. Geographic Risk & Opacity (0-100)
        geo_base = 100 - stability
        geo_risk = min(100, geo_base * 1.5) if origin == "Unknown" else geo_base
        
        sec_geo_base = 100 - sec_stability
        sec_geo_risk = min(100, sec_geo_base * 1.5) if secondary_origin == "Unknown" else sec_geo_base
        
        # 2. Operational Risk (Lead time + Supplier scarcity)
        lt_risk = min(100, (r.lead_time_days / 30) * 100)
        scarcity_risk = max(0, 100 - (r.supplier_count * 20))
        if r.cas in CRITICAL_CAS:
            scarcity_risk = 100
        oper_risk = (lt_risk * 0.5) + (scarcity_risk * 0.5)
        
        # 3. Regulatory & Hazard Risk (0-100)
        reg_val = r.regulatory_score
        if r.cas in REGULATORY_CAS:
            reg_val = 10  # Max risk
        reg_risk = (r.hazard_score * 4) + (reg_val * 6)
        
        # 4. Economic Risk (Substitutability & Cost-at-risk)
        econ_risk = r.substitutability * 10

        # Weighted Component Score (0-100)
        composite_score = (geo_risk * 0.30 + oper_risk * 0.20 + reg_risk * 0.30 + econ_risk * 0.20)
        sec_composite_score = (sec_geo_risk * 0.30 + oper_risk * 0.20 + reg_risk * 0.30 + econ_risk * 0.20)

        # Final Risk Index
        exposure_multiplier = (math.log10(r.mass_g + 1) * 0.7) + (math.log10(r.cost + 1) * 0.3) + 1
        risk_index = composite_score * exposure_multiplier
        secondary_risk_index = sec_composite_score * exposure_multiplier

        results.append(ReagentRiskResult(
            name=r.name,
            cas=r.cas,
            primary_origin=origin,
            stability_score=stability,
            secondary_origin=secondary_origin,
            secondary_stability_score=sec_stability,
            mass_g=r.mass_g,
            cost=r.cost,
            risk_index=round(risk_index, 2),
            secondary_risk_index=round(secondary_risk_index, 2),
            risk_level=label_risk(risk_index),
            hs_code=target_hs6,
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
