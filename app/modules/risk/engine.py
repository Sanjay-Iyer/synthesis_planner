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

from .concentration import (
    CONCENTRATION_THRESHOLDS,
    SHARE_OF_LISTED,
    build_geographic_profile,
    suppliers_from_trade_data,
    assess_concentration,
)
from .hs6_mapping import resolve_hs6
from .risk_config import (
    COMPOSITE_WEIGHTS,
    CONCENTRATION_TIER_RANK,
    LEAD_TIME_FULL_RISK_DAYS,
    SCENARIO_MINIMAL_EXPOSURE_PCT,
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
    # Optional explicit HS6 code (user-asserted; highest mapping priority).
    hs6: Optional[str] = None
    # Optional structure identifier (SMILES, InChI, InChIKey or SELFIES) used
    # for an exact InChIKey -> HS6 match.
    structure: Optional[str] = None


class RiskRequest(BaseModel):
    reagents: List[ReagentRiskInput]


class RiskBreakdown(BaseModel):
    # Country conditions only: 100 - WGI political-stability score of the
    # dominant origin. None when the origin or its score is unknown.
    geographic: Optional[float] = None
    operational: float
    regulatory: float
    economic: float
    # Top supplier share (%) from trade data; None when it cannot be assessed.
    # Reported separately — not part of the composite risk index.
    concentration: Optional[float] = None


class ReagentRiskResult(BaseModel):
    name: str
    cas: str
    primary_origin: str
    # None when the origin is unknown or has no WGI score (see geographic_exposure).
    stability_score: Optional[float] = None
    secondary_origin: str = "Unknown"
    secondary_stability_score: Optional[float] = None
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
    # How the composite risk index was built: per-component score, weight and
    # whether it was used; components that could not be assessed are listed.
    risk_index_components: Optional[dict] = None
    risk_index_note: Optional[str] = None


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


STABILITY_FILE = DATA_DIR / "country_stability.csv"
STABILITY_META_FILE = DATA_DIR / "country_stability_meta.json"


def load_country_stability() -> pd.DataFrame:
    """Load WGI political-stability scores (0-100) produced by scripts/import_wgi.py.

    A missing file yields an empty table — every country is then reported as
    "no stability data" — rather than writing made-up defaults.
    """
    if STABILITY_FILE.exists():
        return pd.read_csv(STABILITY_FILE, encoding="utf-8")
    return pd.DataFrame(columns=["Country", "Stability_Score"])


def load_stability_meta() -> dict:
    """Provenance of country_stability.csv (source, indicator, years, retrieval)."""
    try:
        with open(STABILITY_META_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


# =================================================================
# TRADE DATA & HS6 MAPPING
# =================================================================


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
                    r.get("name", ""),
                    r.get("cas", ""),
                    df_mapping,
                    conn,
                    columns,
                    hs6_input=r.get("hs6"),
                    structure=r.get("structure"),
                )
            except Exception:
                resolved = {"hs6": None, "match_method": None, "mapping_quality": None}
            suggested = {
                "primary": "Unknown",
                "secondary": "Unknown",
                "hs6": resolved["hs6"],
                "hs6_match_method": resolved["match_method"],
                "hs6_mapping_quality": resolved["mapping_quality"],
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
        "data_phrase": "the available WITS export data (top listed exporters only)",
        "scope_note": (
            f"World exports by the top {listed} listed exporting countries (by quantity). "
            "Not global production; shares are relative to the listed exporters only."
        ),
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

STABILITY_SOURCE_PATH = "app/modules/risk/data/country_stability.csv"


def _num_or_none(value) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None  # NaN -> None


def _stability_table(df_stability: pd.DataFrame) -> Dict[str, dict]:
    """canonical country -> {score, lower, upper, year, source_name}."""
    table = {}
    for row in df_stability.to_dict(orient="records"):
        score = _num_or_none(row.get("Stability_Score"))
        if score is None:
            continue
        table[canonical_country(row.get("Country"))] = {
            "score": score,
            "lower": _num_or_none(row.get("Score_Lower_90")),
            "upper": _num_or_none(row.get("Score_Upper_90")),
            "year": int(row["Year"]) if _num_or_none(row.get("Year")) else None,
            "source_name": row.get("WGI_Country_Name") or row.get("Country"),
        }
    return table


def _lookup_stability(table: Dict[str, dict], country: str):
    """(entry, status). status: known | origin_unknown | no_stability_data."""
    key = canonical_country(country)
    if not key or key.lower() == "unknown":
        return None, "origin_unknown"
    if key in table:
        return table[key], "known"
    return None, "no_stability_data"


def _provided(value: Optional[str]) -> Optional[str]:
    value = (value or "").strip()
    return value if value and value.lower() != "unknown" else None


def _geographic_exposure(origin, origin_source, secondary, entry, status, meta, sc_label) -> dict:
    """Country conditions for the dominant origin — no supplier-share input."""
    source_label = ORIGIN_SOURCE_LABELS[origin_source]
    source_long = (
        f"{source_label} ({sc_label})"
        if origin_source == "trade_data_top_supplier" and sc_label
        else source_label
    )
    indicator = meta.get("indicator_name") or "country stability score"
    dataset = meta.get("source") or "country_stability.csv"
    score = entry["score"] if entry else None
    geo = round(100 - score, 1) if score is not None else None

    if status == "origin_unknown":
        explanation = (
            "Origin unknown — insufficient geographic information. The geographic "
            "(country-conditions) component is not assessed and is left out of the "
            "composite index; it is not treated as safe or as high risk."
        )
    elif status == "no_stability_data":
        explanation = (
            f"Dominant origin {origin} ({source_long}). No score for {origin} is "
            f"available in {dataset}; the geographic component is not assessed."
        )
    else:
        ci = (
            f", 90% CI {entry['lower']:.0f}–{entry['upper']:.0f}"
            if entry.get("lower") is not None and entry.get("upper") is not None
            else ""
        )
        relative = "above" if score >= 50 else "below"
        explanation = (
            f"Dominant origin {origin} ({source_long}). {indicator}: {score:.0f}/100"
            f"{ci}{', ' + str(entry['year']) if entry.get('year') else ''} — {relative} "
            f"the midpoint of the 0–100 reference scale. Country-conditions score = "
            f"100 − {score:.0f} = {geo:.0f}. This is a governance indicator, not a "
            "probability of disruption."
        )
    return {
        "dominant_origin": origin,
        "origin_source": origin_source,
        "origin_source_label": source_label,
        "secondary_origin": secondary,
        "status": "ASSESSED" if status == "known" else "UNKNOWN",
        "stability_status": status,
        "stability_known": status == "known",
        "stability_score": score,
        "stability_ci_90": (
            [entry["lower"], entry["upper"]]
            if entry and entry.get("lower") is not None and entry.get("upper") is not None
            else None
        ),
        "stability_year": entry.get("year") if entry else None,
        "stability_indicator": indicator,
        "stability_source": (
            f"{dataset} ({STABILITY_SOURCE_PATH})" if status == "known" else None
        ),
        "geographic_risk_score": geo,
        "explanation": explanation,
    }


def composite_index(components: Dict[str, Optional[float]]) -> dict:
    """Weighted mean of the available components (weights renormalised).

    Missing components are listed, never replaced by a value. Concentration is
    not an input (it is reported separately).
    """
    used = {
        k: v for k, v in components.items() if v is not None and k in COMPOSITE_WEIGHTS
    }
    weight_sum = sum(COMPOSITE_WEIGHTS[k] for k in used)
    score = (
        sum(COMPOSITE_WEIGHTS[k] * v for k, v in used.items()) / weight_sum
        if weight_sum
        else None
    )
    return {
        "score": score,
        "components": {
            k: {
                "score": round(components[k], 1) if components.get(k) is not None else None,
                "weight": w,
                "used": k in used,
            }
            for k, w in COMPOSITE_WEIGHTS.items()
        },
        "weight_coverage": round(weight_sum, 2),
        "missing": [k for k in COMPOSITE_WEIGHTS if k not in used],
    }


def _assess_reagent(r: ReagentRiskInput, df_mapping, stability_table, meta, conn, columns):
    warnings = []

    # 1. HS6 code, how it was matched and how much the match can be trusted
    try:
        resolved = resolve_hs6(
            r.name, r.cas, df_mapping, conn, columns, hs6_input=r.hs6, structure=r.structure
        )
    except Exception:
        resolved = {
            "hs6": None,
            "match_method": None,
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
        supply_chain_data, resolved, substitutability, sub_source
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
    elif resolved.get("mapped_origin"):
        origin, origin_source = resolved["mapped_origin"], "cas_mapping"
    elif resolved.get("db_primary_origin"):
        origin, origin_source = resolved["db_primary_origin"], "compound_db"
    else:
        origin, origin_source = "Unknown", "none"

    secondary_origin = _provided(r.secondary_origin)
    if not secondary_origin:
        if origin_source == "trade_data_top_supplier":
            secondary_origin = conc["second_supplier_country"]
        elif origin_source == "compound_db":
            secondary_origin = _provided(resolved.get("db_secondary_origin"))
    secondary_origin = secondary_origin or "Unknown"

    # 5. Geographic risk = country conditions only (100 - WGI score).
    entry, stability_status = _lookup_stability(stability_table, origin)
    sec_entry, _ = _lookup_stability(stability_table, secondary_origin)
    geo_risk = 100 - entry["score"] if entry else None
    sec_geo_risk = 100 - sec_entry["score"] if sec_entry else None

    if stability_status == "origin_unknown":
        warnings.append(
            "Origin unknown — geographic component not assessed (insufficient geographic information)."
        )
    elif stability_status == "no_stability_data":
        warnings.append(f"No stability score for '{origin}'; geographic component not assessed.")
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

    # 6. Other components (unchanged formulas)
    lt_risk = min(100, (r.lead_time_days / LEAD_TIME_FULL_RISK_DAYS) * 100)
    scarcity_risk = max(0, 100 - (r.supplier_count * 20))
    if r.cas in CRITICAL_CAS:
        scarcity_risk = 100
    oper_risk = (lt_risk * 0.5) + (scarcity_risk * 0.5)

    reg_val = r.regulatory_score
    if r.cas in REGULATORY_CAS:
        reg_val = 10  # Max risk
    reg_risk = (r.hazard_score * 4) + (reg_val * 6)

    econ_risk = substitutability * 10

    # 7. Composite index: country conditions, operational, regulatory, economic.
    #    Concentration is NOT folded in; unknown components are left out.
    primary = composite_index(
        {"geographic": geo_risk, "operational": oper_risk, "regulatory": reg_risk, "economic": econ_risk}
    )
    secondary = composite_index(
        {"geographic": sec_geo_risk, "operational": oper_risk, "regulatory": reg_risk, "economic": econ_risk}
    )

    exposure_multiplier = (
        (math.log10(r.mass_g + 1) * 0.7) + (math.log10(r.cost + 1) * 0.3) + 1
    )
    risk_index = primary["score"] * exposure_multiplier
    secondary_risk_index = secondary["score"] * exposure_multiplier

    note = (
        "Composite of geographic (country conditions), operational, regulatory and "
        "economic components. Concentration is reported separately and is not part "
        "of this index."
    )
    if primary["missing"]:
        note = (
            f"Not assessed: {', '.join(primary['missing'])}; the index uses the other "
            f"components with weights renormalised (coverage {primary['weight_coverage']:.0%}). "
            + note
        )

    conc_score = conc["top_supplier_share"] if conc["tier"] != "UNKNOWN" else None
    return ReagentRiskResult(
        name=r.name,
        cas=r.cas,
        primary_origin=origin,
        stability_score=entry["score"] if entry else None,
        secondary_origin=secondary_origin,
        secondary_stability_score=sec_entry["score"] if sec_entry else None,
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
            geographic=round(geo_risk, 1) if geo_risk is not None else None,
            operational=round(oper_risk, 1),
            regulatory=round(reg_risk, 1),
            economic=round(econ_risk, 1),
            concentration=round(conc_score, 1) if conc_score is not None else None,
        ),
        supply_chain_data=supply_chain_data,
        geographic_exposure=_geographic_exposure(
            origin,
            origin_source,
            secondary_origin,
            entry,
            stability_status,
            meta,
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
        risk_index_components=primary,
        risk_index_note=note,
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
    prov = result.provenance or {}
    return {
        "name": result.name,
        "tier": conc.get("tier"),
        "top_supplier_country": conc.get("top_supplier_country"),
        "top_supplier_share": conc.get("top_supplier_share"),
        "source": prov.get("source"),
        "source_label": prov.get("source_label"),
        "data_quality": (result.data_quality or {}).get("level"),
    }


def _pct(part: float, whole: float) -> Optional[float]:
    return round(part / whole * 100, 2) if whole > 0 else None


def summarize_routes(results: List[ReagentRiskResult]) -> Optional[List[dict]]:
    """Per-route geographic summary — facts only, no combined score or ranking.

    Uses the per-route reagent spend sent by the Planner. Returns None when no
    reagent carries route information. All percentages are of the route's
    *assessed reagent spend* (reagents sent to the Risk Audit), which excludes
    solvents and other costs.
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
        spend = sum(float(u.get("cost") or 0) for _, u in items)
        known = [
            (res, u)
            for res, u in items
            if (res.concentration or {}).get("tier") in CONCENTRATION_TIER_RANK
        ]
        unknown = [(res, u) for res, u in items if (res, u) not in known]
        unknown_cost = sum(float(u.get("cost") or 0) for _, u in unknown)

        highest = max((res for res, _ in known), key=_concentration_rank, default=None)
        largest = max(
            (res for res, _ in known),
            key=lambda res: (res.concentration or {}).get("top_supplier_share") or 0,
            default=None,
        )

        # Spend exposed to each country = sum(route cost x that country's share).
        country_exposure: Dict[str, dict] = {}
        for res, usage in known:
            cost = float(usage.get("cost") or 0)
            for s in res.supplier_shares:
                share = s.get("share_pct") or 0
                if share <= 0:
                    continue
                entry = country_exposure.setdefault(
                    s["country"], {"country": s["country"], "cost": 0.0, "reagents": []}
                )
                entry["cost"] += cost * share / 100.0
                # Name only meaningful contributors; the cost total stays exact.
                if share >= SCENARIO_MINIMAL_EXPOSURE_PCT and res.name not in entry["reagents"]:
                    entry["reagents"].append(res.name)
        exposures = sorted(country_exposure.values(), key=lambda e: e["cost"], reverse=True)
        for e in exposures:
            e["pct_of_assessed_spend"] = _pct(e["cost"], spend)
            e["cost"] = round(e["cost"], 2)

        # Spend grouped by each reagent's dominant supplier country.
        by_dominant: Dict[str, dict] = {}
        for res, usage in known:
            country = (res.concentration or {}).get("top_supplier_country")
            if not country:
                continue
            entry = by_dominant.setdefault(country, {"country": country, "cost": 0.0, "reagents": []})
            entry["cost"] += float(usage.get("cost") or 0)
            entry["reagents"].append(res.name)
        dominant_sources = sorted(by_dominant.values(), key=lambda e: e["cost"], reverse=True)
        for e in dominant_sources:
            e["cost_share_pct"] = _pct(e["cost"], spend)
            e["cost"] = round(e["cost"], 2)

        geo_known = [
            res for res, _ in items if res.breakdown.geographic is not None
        ]
        highest_geo = max(geo_known, key=lambda res: res.breakdown.geographic, default=None)

        summaries.append(
            {
                "route": route,
                "reagent_count": len(items),
                "reagents_with_trade_data": len(known),
                "assessed_reagent_cost": round(spend, 2),
                "high_concentration_count": sum(
                    1 for res, _ in known if res.concentration["tier"] == "HIGH"
                ),
                "high_concentration_reagents": [
                    res.name for res, _ in known if res.concentration["tier"] == "HIGH"
                ],
                "highest_concentration_reagent": _reagent_brief(highest) if highest else None,
                "largest_dominant_share": _reagent_brief(largest) if largest else None,
                "largest_country_exposure": exposures[0] if exposures else None,
                "country_exposures": exposures[:5],
                "unknown_concentration_reagents": [res.name for res, _ in unknown],
                "unknown_data_cost": round(unknown_cost, 2),
                "unknown_data_pct": _pct(unknown_cost, spend),
                "highest_geographic_risk_reagent": (
                    {
                        "name": highest_geo.name,
                        "origin": highest_geo.primary_origin,
                        "stability_score": highest_geo.stability_score,
                        "geographic_score": highest_geo.breakdown.geographic,
                    }
                    if highest_geo
                    else None
                ),
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
    meta = load_stability_meta()

    conn = _connect_compound_db()
    columns = _compound_columns(conn)
    try:
        results = [
            _assess_reagent(r, df_mapping, stability_table, meta, conn, columns)
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
            "composite_weights": COMPOSITE_WEIGHTS,
            "stability_source": {
                k: meta.get(k)
                for k in ("source", "source_url", "indicator", "indicator_name", "years", "retrieved_at")
            },
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
