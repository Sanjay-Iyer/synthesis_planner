"""
Risk Assessment Engine — Supply Chain Geographic Risk Analysis.
Migrated from risk_audit_folder/reagent_risk_tool.py
"""

import os
import math
import json
import sqlite3
from pathlib import Path
import pandas as pd
from pydantic import BaseModel
from typing import Dict, List, Optional

from app.config import COMPOUND_HS6_MAP_PATH
from .concentration import (
    CONCENTRATION_THRESHOLDS,
    SHARE_OF_LISTED,
    build_geographic_profile,
    suppliers_from_trade_data,
    assess_concentration,
)
from .risk_config import (
    CONCENTRATION_TIER_RANK,
    LEAD_TIME_FULL_RISK_DAYS,
    canonical_country,
)

# Path to reference data files (lives alongside this module)
DATA_DIR = Path(__file__).resolve().parent / "data"

DEFAULT_SUBSTITUTABILITY = 5


# =================================================================
# DATA MODELS
# =================================================================


class RouteUsage(BaseModel):
    """How much of a reagent one route uses (sent by the Planner hand-off)."""

    cost: float = 0.0
    mass_g: float = 0.0


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
    regulatory_score: int = 5  # 1-10 (EPA/TSCA/Export Controls)
    supplier_count: int = 3
    # 1-10 (10 = hardest to replace). None = not provided -> default 5, and the
    # result says so (substitutability_source = "default").
    substitutability: Optional[int] = None
    # Route label -> usage, e.g. {"A": {"cost": 120.0, "mass_g": 400.0}}.
    routes: Dict[str, RouteUsage] = {}


class RiskRequest(BaseModel):
    reagents: List[ReagentRiskInput]


class RiskBreakdown(BaseModel):
    # Country conditions only (100 - stability, x1.5 if origin unknown).
    geographic: float
    operational: float
    regulatory: float
    economic: float
    # Top supplier share (%) from trade data; None when it cannot be assessed.
    concentration: Optional[float] = None
    # Value used for the 30% geographic weight of the composite index:
    # max(geographic, concentration) — unchanged from the previous engine.
    geo_index_input: Optional[float] = None


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
    # Geographic-risk detail, kept as separate concepts (see guide/08):
    geographic_exposure: Optional[dict] = None  # dominant origin + country conditions
    concentration: Optional[dict] = None  # how concentrated the reported supply is
    alternatives: Optional[dict] = None  # alternate countries / substitutability
    provenance: Optional[dict] = None  # where the trade numbers came from
    data_quality: Optional[dict] = None  # qualitative, rule-based
    supplier_shares: List[dict] = []  # countries with shares (for scenarios)
    routes: Dict[str, dict] = {}


# =================================================================
# REFERENCE DATA
# =================================================================


def load_reagent_mapping() -> pd.DataFrame:
    """Load the CAS → HS Code → Country mapping table."""
    path = DATA_DIR / "reagent_mapping.csv"
    if path.exists():
        # Strings, so HS codes like "2827.60" keep their trailing zero.
        return pd.read_csv(path, dtype={"Reagent_CAS": str, "HS_Code": str})

    # Generate default if missing
    mapping_data = {
        "Reagent_CAS": ["7440-06-4", "775-12-2", "7447-39-4", "7681-65-4", "106-92-3"],
        "HS_Code": ["3815.12", "2931.90", "2827.39", "2827.60", "2910.90"],
        "Primary_Origin": ["South Africa", "Germany", "China", "China", "USA"],
    }
    df = pd.DataFrame(mapping_data)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return df


def load_country_stability() -> pd.DataFrame:
    """Load country stability scores (0-100, based on World Bank WGI)."""
    path = DATA_DIR / "country_stability.csv"
    if path.exists():
        return pd.read_csv(path)

    # Generate default if missing
    stability_data = {
        "Country": [
            "Germany",
            "USA",
            "Japan",
            "China",
            "South Africa",
            "Russia",
            "Mexico",
            "India",
            "Chile",
        ],
        "Stability_Score": [92, 85, 88, 48, 35, 15, 42, 52, 75],
    }
    df = pd.DataFrame(stability_data)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return df


# =================================================================
# TRADE DATA & HS6 MAPPING
# =================================================================


def get_hs6_for_inchikey(inchikey: str) -> Optional[str]:
    """Look up HS6 code for a given InChIKey."""
    path = COMPOUND_HS6_MAP_PATH
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("mappings", {}).get(inchikey, {}).get("hs6_code")
    except Exception:
        return None


def get_hs6_by_name_hint(name: str) -> Optional[str]:
    """Try to find an HS6 code by matching the name against name hints."""
    path = COMPOUND_HS6_MAP_PATH
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
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


def _clean_hs6(value) -> Optional[str]:
    """Digits-only, zero-padded HS6 code, or None (also for NaN/blank)."""
    if value is None:
        return None
    digits = "".join(filter(str.isdigit, str(value)))
    if not digits:
        return None
    return digits[:6].zfill(6)


def _connect_compound_db():
    """One connection per request; None if the registry is unavailable."""
    try:
        from app.modules.database.db import connect_db

        return connect_db()
    except Exception:
        return None


def _compound_columns(conn) -> set:
    if conn is None:
        return set()
    try:
        return {row[1] for row in conn.execute("PRAGMA table_info(compounds)")}
    except sqlite3.Error:
        return set()


def resolve_hs6(
    name: str,
    cas: str = "",
    df_mapping: Optional[pd.DataFrame] = None,
    conn=None,
    columns: Optional[set] = None,
) -> dict:
    """Resolve a reagent to an HS6 code, recording where the code came from.

    Order: CAS mapping (reagent_mapping.csv) -> compound registry hs6_code ->
    compound registry InChIKey -> compound_hs6_map.json -> name hint. Also
    returns any origin stored alongside the CAS mapping / compound record.
    """
    out = {
        "hs6": None,
        "source": None,
        "mapped_origin": None,
        "db_primary_origin": None,
        "db_secondary_origin": None,
    }
    name = (name or "").strip()
    cas = (cas or "").strip()

    if cas and df_mapping is not None and not df_mapping.empty:
        rows = df_mapping[df_mapping["Reagent_CAS"].astype(str).str.strip() == cas]
        if not rows.empty:
            row = rows.iloc[0]
            origin = row.get("Primary_Origin")
            if isinstance(origin, str) and origin.strip():
                out["mapped_origin"] = origin.strip()
            hs6 = _clean_hs6(row.get("HS_Code"))
            if hs6:
                out.update(hs6=hs6, source="cas_mapping")

    if conn is not None and name:
        from app.modules.database.db import normalize_name

        cols = columns if columns is not None else _compound_columns(conn)
        wanted = [
            c
            for c in ("inchikey", "hs6_code", "primary_origin", "secondary_origin")
            if c in cols
        ]
        if "normalized_name" in cols and wanted:
            row = conn.execute(
                f"SELECT {', '.join(wanted)} FROM compounds WHERE normalized_name = ?",
                (normalize_name(name),),
            ).fetchone()
            if row:
                data = dict(zip(wanted, row))
                out["db_primary_origin"] = data.get("primary_origin") or None
                out["db_secondary_origin"] = data.get("secondary_origin") or None
                if not out["hs6"]:
                    db_hs6 = _clean_hs6(data.get("hs6_code"))
                    if db_hs6:
                        out.update(hs6=db_hs6, source="compound_db")
                    elif data.get("inchikey"):
                        mapped = _clean_hs6(get_hs6_for_inchikey(data["inchikey"]))
                        if mapped:
                            out.update(hs6=mapped, source="inchikey_map")

    if not out["hs6"] and name:
        hinted = _clean_hs6(get_hs6_by_name_hint(name))
        if hinted:
            out.update(hs6=hinted, source="name_hint")
    return out


def _country_suppliers(sc: dict) -> List[dict]:
    """Supplier rows that are single countries (regional groupings removed)."""
    return [s for s in suppliers_from_trade_data(sc) if not s["is_aggregate"]]


def lookup_suggested_origins(reagent_inputs: List[dict]) -> List[dict]:
    """Look up suggested origins for a list of reagents based on trade data.

    Regional groupings (e.g. "European Union", "Other Asia, nes") are never
    suggested as an origin country.
    """
    results = []
    df_mapping = load_reagent_mapping()
    conn = _connect_compound_db()
    columns = _compound_columns(conn)
    try:
        for r in reagent_inputs:
            try:
                resolved = resolve_hs6(
                    r.get("name", ""), r.get("cas", ""), df_mapping, conn, columns
                )
            except Exception:
                resolved = {"hs6": None, "source": None}
            suggested = {
                "primary": "Unknown",
                "secondary": "Unknown",
                "hs6": resolved["hs6"],
                "hs6_source": resolved["source"],
                "source_label": None,
            }
            if resolved["hs6"]:
                concentration = get_supply_chain_concentration(resolved["hs6"])
                if concentration.get("status") == "success":
                    countries = _country_suppliers(concentration)
                    if countries:
                        suggested["primary"] = countries[0]["country"]
                    if len(countries) > 1:
                        suggested["secondary"] = countries[1]["country"]
                    suggested["source_label"] = concentration.get("source_label")
            results.append(suggested)
    finally:
        if conn is not None:
            conn.close()
    return results


WITS_SOURCE_URL = "https://wits.worldbank.org/"


def get_supply_chain_concentration(hs6_code: str, year: Optional[int] = None) -> dict:
    """
    Returns concentration metrics, supplier shares and provenance for an HS6.

    Sources are consulted in priority order:
      1. The supply-chain drop folder (USITC DataWeb imports), live-scanned so
         any file added to ``data/supply_chain`` is used automatically. The
         latest complete year is preferred over partial-year (YTD) data.
      2. The legacy WITS JSON database (v1.1.0 schema) as a fallback.
    """
    from app.modules.trade_data import db as trade_db

    # Normalize HS6: digits only, padded to 6
    clean_hs6 = "".join(filter(str.isdigit, str(hs6_code))).zfill(6)

    # 1. Supply-chain folder (USITC) — primary, authoritative U.S. import origins
    try:
        from app.modules.supply_chain import provider as sc_provider

        usitc = sc_provider.get_origin_concentration(clean_hs6, year)
        if usitc.get("status") == "success":
            return usitc
    except Exception:
        # Never let a supply-chain parsing issue break the risk assessment;
        # fall through to the WITS database below.
        pass

    # 2. WITS JSON database — fallback
    db = trade_db.load()
    record = trade_db.get_trade_record(db, clean_hs6, year)

    if not record:
        return {"status": "no_trade_data", "hs6_code": clean_hs6}

    top_exporters = record.get("top_exporters", [])
    if not top_exporters:
        return {"status": "no_trade_data", "hs6_code": clean_hs6}

    rec_year = record.get("year")
    listed = len(top_exporters)
    wits_like = {"status": "success", "top_exporters": top_exporters}
    suppliers = suppliers_from_trade_data(wits_like)
    basis_phrase = f"export quantity among the top {listed} listed exporters for this HS6 product"
    concentration = assess_concentration(
        suppliers, share_basis=SHARE_OF_LISTED, basis_phrase=basis_phrase
    )

    notes = [
        "WITS shares are relative to the listed top exporters only, which "
        "overstates concentration compared with a world total."
    ]
    for warning in record.get("warnings", []):
        if warning.get("code") == "excluded_rows_missing_quantity":
            notes.append(
                f"{warning.get('count')} exporter(s) excluded because they reported "
                "trade value but no quantity."
            )
            break
    groupings = [s["country"] for s in suppliers if s["is_aggregate"]]
    if groupings:
        notes.append(
            "Regional groupings listed by WITS were not treated as countries: "
            + ", ".join(groupings)
            + "."
        )

    product = db.get("products", {}).get(clean_hs6, {})
    source_file = (record.get("source") or {}).get("filename")
    return {
        "status": "success",
        "source": "WITS",
        "source_url": WITS_SOURCE_URL,
        "source_label": f"WITS (World Bank) — world exports by reporter, full-year {rec_year}",
        "source_files": [source_file] if source_file else [],
        "hs6_code": clean_hs6,
        "description": product.get("product_description"),
        "year": rec_year,
        "period_type": "full_year",
        "period_label": f"Full-year {rec_year}",
        "is_partial_year": False,
        "year_selection_reason": "requested_year" if year else "latest_wits_record",
        "year_selection_note": "Latest annual WITS record stored for this HS6 code.",
        "newer_partial_period_available": None,
        "trade_flow": "export",
        "partner": record.get("partner"),
        "ranking_basis": "Export quantity reported to WITS (exporters with no quantity excluded)",
        "share_basis": SHARE_OF_LISTED,
        "share_basis_label": (
            f"Share of combined export quantity of the top {listed} listed exporters "
            "(not a world total)"
        ),
        "basis_phrase": basis_phrase,
        "coverage": "listed_only",
        "country_count": len([s for s in suppliers if not s["is_aggregate"]]),
        "listed_count": listed,
        "top_exporters": top_exporters,
        "concentration_top1_pct": concentration["top_supplier_share"],
        "concentration_risk_flag": concentration["tier"],
        "data_quality_note": " ".join(notes),
        "notes": notes,
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


ORIGIN_SOURCE_LABELS = {
    "user_input": "entered by user",
    "trade_data_top_supplier": "top supplier country in trade data",
    "cas_mapping": "CAS mapping (reagent_mapping.csv)",
    "compound_db": "stored in compound registry",
    "none": "no origin information",
}

STABILITY_FILE = "app/modules/risk/data/country_stability.csv"
NEUTRAL_STABILITY = 50.0


def _stability_table(df_stability: pd.DataFrame) -> Dict[str, float]:
    table = {}
    for country, score in zip(df_stability["Country"], df_stability["Stability_Score"]):
        try:
            table[canonical_country(country)] = float(score)
        except (TypeError, ValueError):
            continue
    return table


def _lookup_stability(table: Dict[str, float], country: str):
    """(score, known) — neutral 50 when the country is unknown or not listed."""
    key = canonical_country(country)
    if key and key.lower() != "unknown" and key in table:
        return table[key], True
    return NEUTRAL_STABILITY, False


def _provided(value: Optional[str]) -> Optional[str]:
    value = (value or "").strip()
    return value if value and value.lower() != "unknown" else None


def _geographic_exposure(
    origin, origin_source, secondary, stability, stability_known, geo_risk, sc_label
) -> dict:
    source_label = ORIGIN_SOURCE_LABELS[origin_source]
    if origin_source == "trade_data_top_supplier" and sc_label:
        source_label_long = f"{source_label} ({sc_label})"
    else:
        source_label_long = source_label
    if origin == "Unknown":
        explanation = (
            "Origin is unknown. The existing opacity adjustment (x1.5 on the "
            "country-conditions score) is applied; it reflects missing information, "
            "not a property of any country."
        )
    elif stability_known:
        explanation = (
            f"Dominant origin {origin} ({source_label_long}). Country stability score "
            f"{stability:.0f}/100 gives a country-conditions score of {geo_risk:.0f}/100."
        )
    else:
        explanation = (
            f"Dominant origin {origin} ({source_label_long}). {origin} is not in "
            "country_stability.csv, so a neutral default of 50 is used."
        )
    return {
        "dominant_origin": origin,
        "origin_source": origin_source,
        "origin_source_label": source_label,
        "secondary_origin": secondary,
        "stability_score": stability if stability_known else None,
        "stability_score_used": stability,
        "stability_known": stability_known,
        "stability_source": (
            STABILITY_FILE
            if stability_known
            else f"neutral default {NEUTRAL_STABILITY:.0f} (country not in table)"
        ),
        "stability_provenance_note": (
            "Provenance of country_stability.csv needs confirmation; see guide/DATA_SOURCES.md."
        ),
        "geographic_risk_score": round(geo_risk, 1),
        "opacity_multiplier_applied": origin == "Unknown",
        "explanation": explanation,
    }


def _assess_reagent(r: ReagentRiskInput, df_mapping, stability_table, conn, columns):
    warnings = []

    # 1. HS6 code and where it came from
    try:
        resolved = resolve_hs6(r.name, r.cas, df_mapping, conn, columns)
    except Exception:
        resolved = {
            "hs6": None,
            "source": None,
            "mapped_origin": None,
            "db_primary_origin": None,
            "db_secondary_origin": None,
        }
        warnings.append(f"Technical error during HS6 lookup for {r.name}.")
    target_hs6 = resolved["hs6"]

    # 2. Trade data (USITC first, WITS fallback)
    if target_hs6:
        try:
            supply_chain_data = get_supply_chain_concentration(target_hs6)
        except Exception as e:
            supply_chain_data = {"status": "error", "detail": str(e)}
            warnings.append(f"Technical error during trade-data lookup for {r.name}.")
    else:
        supply_chain_data = {"status": "no_hs6_mapping"}
        warnings.append(f"No HS6 code available for {r.name}; supply chain lookup skipped.")

    # 3. Concentration, alternatives, provenance, data quality
    sub_source = "user_input" if r.substitutability is not None else "default"
    substitutability = (
        r.substitutability if r.substitutability is not None else DEFAULT_SUBSTITUTABILITY
    )
    profile = build_geographic_profile(
        supply_chain_data, target_hs6, resolved["source"], substitutability, sub_source
    )
    conc = profile["concentration"]
    has_trade = profile["provenance"]["status"] == "success"

    # 4. Dominant origin. Priority: user input > top supplier in trade data >
    #    CAS mapping > value stored in the compound registry.
    user_origin = _provided(r.origin)
    if user_origin:
        origin, origin_source = user_origin, "user_input"
    elif has_trade and conc["top_supplier_country"]:
        origin, origin_source = conc["top_supplier_country"], "trade_data_top_supplier"
    elif resolved["mapped_origin"]:
        origin, origin_source = resolved["mapped_origin"], "cas_mapping"
    elif resolved["db_primary_origin"]:
        origin, origin_source = resolved["db_primary_origin"], "compound_db"
    else:
        origin, origin_source = "Unknown", "none"

    secondary_origin = _provided(r.secondary_origin)
    if not secondary_origin:
        if origin_source == "trade_data_top_supplier":
            secondary_origin = conc["second_supplier_country"]
        elif origin_source == "compound_db":
            secondary_origin = _provided(resolved["db_secondary_origin"])
    secondary_origin = secondary_origin or "Unknown"

    # 5. Country conditions (stability) — separate from concentration
    stability, stability_known = _lookup_stability(stability_table, origin)
    sec_stability, _ = _lookup_stability(stability_table, secondary_origin)

    if origin == "Unknown":
        warnings.append("Unverified Origin (Opacity Risk)")
    elif not stability_known:
        warnings.append(
            f"No stability score for '{origin}' in country_stability.csv; neutral 50 used."
        )
    if r.cas in CRITICAL_CAS:
        warnings.append(f"CRITICAL MATERIAL: {CRITICAL_CAS[r.cas]}")
    if r.cas in REGULATORY_CAS:
        warnings.append(f"REGULATORY FLAG: {REGULATORY_CAS[r.cas]}")
    if conc["tier"] == "HIGH":
        warnings.append(
            f"High sourcing concentration: {conc['top_supplier_country']} "
            f"{conc['top_supplier_share']:.0f}% of reported supply "
            f"({profile['provenance'].get('source')}, {profile['provenance'].get('period_label')})."
        )

    # Geographic (country conditions) risk, 0-100
    geo_base = 100 - stability
    geo_risk = min(100, geo_base * 1.5) if origin == "Unknown" else geo_base
    sec_geo_base = 100 - sec_stability
    sec_geo_risk = (
        min(100, sec_geo_base * 1.5) if secondary_origin == "Unknown" else sec_geo_base
    )

    # Concentration is reported separately. For continuity with the previous
    # composite index, the 30% geographic weight still uses the worse of the
    # two: max(country conditions, top-supplier share).
    conc_score = conc["top_supplier_share"] if conc["tier"] != "UNKNOWN" else None
    geo_index_input = min(100, max(geo_risk, conc_score)) if conc_score is not None else geo_risk

    # Operational Risk (Lead time + Supplier scarcity)
    lt_risk = min(100, (r.lead_time_days / LEAD_TIME_FULL_RISK_DAYS) * 100)
    scarcity_risk = max(0, 100 - (r.supplier_count * 20))
    if r.cas in CRITICAL_CAS:
        scarcity_risk = 100
    oper_risk = (lt_risk * 0.5) + (scarcity_risk * 0.5)

    # Regulatory & Hazard Risk (0-100)
    reg_val = r.regulatory_score
    if r.cas in REGULATORY_CAS:
        reg_val = 10  # Max risk
    reg_risk = (r.hazard_score * 4) + (reg_val * 6)

    # Economic Risk (Substitutability)
    econ_risk = substitutability * 10

    composite_score = (
        geo_index_input * 0.30 + oper_risk * 0.20 + reg_risk * 0.30 + econ_risk * 0.20
    )
    sec_composite_score = (
        sec_geo_risk * 0.30 + oper_risk * 0.20 + reg_risk * 0.30 + econ_risk * 0.20
    )

    exposure_multiplier = (
        (math.log10(r.mass_g + 1) * 0.7) + (math.log10(r.cost + 1) * 0.3) + 1
    )
    risk_index = composite_score * exposure_multiplier
    secondary_risk_index = sec_composite_score * exposure_multiplier

    return ReagentRiskResult(
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
        substitutability=substitutability,
        warnings=warnings,
        breakdown=RiskBreakdown(
            geographic=round(geo_risk, 1),
            operational=round(oper_risk, 1),
            regulatory=round(reg_risk, 1),
            economic=round(econ_risk, 1),
            concentration=round(conc_score, 1) if conc_score is not None else None,
            geo_index_input=round(geo_index_input, 1),
        ),
        supply_chain_data=supply_chain_data,
        geographic_exposure=_geographic_exposure(
            origin,
            origin_source,
            secondary_origin,
            stability,
            stability_known,
            geo_risk,
            profile["provenance"].get("source_label"),
        ),
        concentration=conc,
        alternatives=profile["alternatives"],
        provenance=profile["provenance"],
        data_quality=profile["data_quality"],
        # Canonical names so the same country from USITC and WITS ("South
        # Korea" / "Korea, Rep.") is one scenario choice.
        supplier_shares=[
            {
                "country": canonical_country(s["country"]),
                "reported_name": s["country"],
                "share_pct": s["share_pct"],
            }
            for s in profile["suppliers"]
            if s["share_pct"] is not None
        ],
        routes={k: _dump(v) for k, v in (r.routes or {}).items()},
    )


def _dump(model):
    return model.model_dump() if hasattr(model, "model_dump") else model.dict()


def _concentration_rank(result: ReagentRiskResult):
    conc = result.concentration or {}
    return (
        CONCENTRATION_TIER_RANK.get(conc.get("tier"), 0),
        conc.get("top_supplier_share") or 0,
    )


def _reagent_brief(result: ReagentRiskResult) -> dict:
    conc = result.concentration or {}
    return {
        "name": result.name,
        "tier": conc.get("tier"),
        "top_supplier_country": conc.get("top_supplier_country"),
        "top_supplier_share": conc.get("top_supplier_share"),
        "source_label": (result.provenance or {}).get("source_label"),
    }


def summarize_routes(results: List[ReagentRiskResult]) -> Optional[List[dict]]:
    """Per-route concentration summary (no combined score; the user decides).

    Uses the per-route reagent usage sent by the Planner. Returns None when no
    reagent carries route information.
    """
    by_route: Dict[str, list] = {}
    for res in results:
        for route, usage in (res.routes or {}).items():
            by_route.setdefault(route, []).append((res, usage or {}))
    if not by_route:
        return None

    summaries = []
    for route in sorted(by_route):
        items = by_route[route]
        assessed_cost = sum(float(u.get("cost") or 0) for _, u in items)
        known = [
            res
            for res, _ in items
            if (res.concentration or {}).get("tier") in CONCENTRATION_TIER_RANK
        ]
        highest = max(known, key=_concentration_rank, default=None)
        largest = max(
            known,
            key=lambda res: (res.concentration or {}).get("top_supplier_share") or 0,
            default=None,
        )

        # Share of the route's assessed reagent cost by each reagent's dominant
        # supplier country (reagents with unknown concentration are listed apart).
        by_country: Dict[str, dict] = {}
        for res, usage in items:
            country = (res.concentration or {}).get("top_supplier_country")
            if res not in known or not country:
                continue
            entry = by_country.setdefault(country, {"country": country, "cost": 0.0, "reagents": []})
            entry["cost"] += float(usage.get("cost") or 0)
            entry["reagents"].append(res.name)
        dominant_sources = sorted(by_country.values(), key=lambda e: e["cost"], reverse=True)
        for entry in dominant_sources:
            entry["cost_share_pct"] = (
                round(entry["cost"] / assessed_cost * 100, 1) if assessed_cost > 0 else None
            )
            entry["cost"] = round(entry["cost"], 2)

        summaries.append(
            {
                "route": route,
                "reagent_count": len(items),
                "assessed_reagent_cost": round(assessed_cost, 2),
                "highest_concentration_reagent": _reagent_brief(highest) if highest else None,
                "largest_dominant_share": _reagent_brief(largest) if largest else None,
                "high_concentration_reagents": [
                    res.name
                    for res, _ in items
                    if (res.concentration or {}).get("tier") == "HIGH"
                ],
                "unknown_concentration_reagents": [
                    res.name
                    for res, _ in items
                    if (res.concentration or {}).get("tier") not in CONCENTRATION_TIER_RANK
                ],
                "dominant_source_cost_shares": dominant_sources,
            }
        )
    return summaries


def run_risk_assessment(reagents: List[ReagentRiskInput]) -> dict:
    """
    Perform geographic risk assessment on a list of reagents.
    Returns enriched reagent data with risk scores and summary stats.

    Read-only with respect to the compound registry: trade-derived origins are
    reported with their provenance, not written back to the database.
    """
    df_mapping = load_reagent_mapping()
    stability_table = _stability_table(load_country_stability())

    conn = _connect_compound_db()
    columns = _compound_columns(conn)
    try:
        results = [
            _assess_reagent(r, df_mapping, stability_table, conn, columns)
            for r in reagents
        ]
    finally:
        if conn is not None:
            conn.close()

    # Summary statistics
    high_risk = [
        r for r in results if "HIGH" in r.risk_level and "MEDIUM" not in r.risk_level
    ]
    total_risk_exposure = sum(r.risk_index for r in results)
    conc_tiers = [(r.concentration or {}).get("tier") for r in results]

    return {
        "reagents": [_dump(r) for r in results],
        "summary": {
            "total_reagents": len(results),
            "high_risk_count": len(high_risk),
            "total_risk_exposure": round(total_risk_exposure, 2),
            "highest_risk": (
                max(results, key=lambda x: x.risk_index).name if results else None
            ),
            "concentration_high_count": conc_tiers.count("HIGH"),
            "concentration_unknown_count": conc_tiers.count("UNKNOWN"),
            "concentration_thresholds": CONCENTRATION_THRESHOLDS,
            "route_summary": summarize_routes(results),
        },
    }


def update_reagent_mapping(cas: str, origin: str) -> bool:
    """Persist a new or updated CAS -> Origin mapping to CSV."""
    if not cas or not origin:
        return False

    path = DATA_DIR / "reagent_mapping.csv"
    df = load_reagent_mapping()

    # Check if CAS already exists
    if cas in df["Reagent_CAS"].values:
        df.loc[df["Reagent_CAS"] == cas, "Primary_Origin"] = origin
    else:
        # Add new row
        new_row = pd.DataFrame(
            {"Reagent_CAS": [cas], "HS_Code": [""], "Primary_Origin": [origin]}
        )
        df = pd.concat([df, new_row], ignore_index=True)

    df.to_csv(path, index=False, encoding="utf-8-sig")
    return True
