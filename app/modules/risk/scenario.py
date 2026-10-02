"""
Scenario / shock analysis — deterministic sensitivity on observed sourcing.

This is *not* forecasting. Each scenario applies a stated shock to the supplier
shares already shown in the Risk Audit and reports how much of each route's
assessed reagent cost is touched. Nothing here claims a material becomes
unavailable; results are phrased as sourcing *exposure*.

Scenarios:
  dominant_supplier_loss  each reagent loses its own top supplier country
  country_disruption      a chosen country's supply is interrupted
  tariff                  +X% tariff on supply from a chosen country
                          (or from each reagent's dominant supplier)
  lead_time               +N days lead time on supply from a chosen country
                          (or from each reagent's dominant supplier)

Core calculation for every reagent ``r`` and target country ``c``:

    exposure_share(r)   = share of r's reported supply from c   (0-100)
    affected_cost(r, R) = cost of r in route R x exposure_share(r) / 100

    route affected fraction = sum(affected_cost) / sum(cost of all assessed
                              reagents in R) x 100

Reagents with no trade data are UNKNOWN — their cost is reported separately and
never counted as unaffected.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from .concentration import SHARE_OF_TOTAL, fmt_pct
from .risk_config import (
    DEFAULT_LEAD_TIME_INCREASE_DAYS,
    DEFAULT_TARIFF_PCT,
    LEAD_TIME_FULL_RISK_DAYS,
    LIMITED_ALTERNATIVES_SHARE_PCT,
    SCENARIO_EXPOSURE_THRESHOLDS,
    SCENARIO_HIGH_DEPENDENCY_PCT,
    SCENARIO_MINIMAL_EXPOSURE_PCT,
    canonical_country,
)

SCENARIO_TYPES = ("dominant_supplier_loss", "country_disruption", "tariff", "lead_time")

ALL_REAGENTS_ROUTE = "All reagents"

ROUTE_TIER_LABELS = {
    "HIGH": "highly exposed",
    "MEDIUM": "moderately exposed",
    "LOW": "lower exposure",
    "UNKNOWN": "exposure unknown",
}

_TIER_ORDER = ["LOW", "MEDIUM", "HIGH"]


def lead_time_risk(days: float) -> float:
    """Operational lead-time sub-score used by the risk engine (0-100)."""
    return round(min(100.0, (max(days, 0) / LEAD_TIME_FULL_RISK_DAYS) * 100), 1)


def classify_route_exposure(affected_pct: Optional[float]) -> str:
    """Route exposure tier from the % of assessed reagent cost affected."""
    if affected_pct is None:
        return "UNKNOWN"
    if affected_pct >= SCENARIO_EXPOSURE_THRESHOLDS["high_pct"]:
        return "HIGH"
    if affected_pct >= SCENARIO_EXPOSURE_THRESHOLDS["medium_pct"]:
        return "MEDIUM"
    return "LOW"


def _num(value, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number else default


def items_from_assessment(reagent_results: Iterable[dict]) -> List[dict]:
    """Build scenario inputs from ``run_risk_assessment`` reagent results."""
    items = []
    for r in reagent_results:
        prov = r.get("provenance") or {}
        conc = r.get("concentration") or {}
        items.append(
            {
                "name": r.get("name"),
                "cost": _num(r.get("cost")),
                "routes": r.get("routes") or {},
                "lead_time_days": _num(r.get("lead_time"), 14),
                "suppliers": r.get("supplier_shares") or [],
                "share_basis": prov.get("share_basis", SHARE_OF_TOTAL),
                "coverage": prov.get("coverage"),
                "has_trade_data": prov.get("status") == "success",
                "top_supplier_country": conc.get("top_supplier_country"),
                "source_label": prov.get("source_label"),
            }
        )
    return items


def _target_country(item: dict, scenario: dict) -> Optional[str]:
    if scenario["type"] == "dominant_supplier_loss" or not scenario.get("country"):
        return item.get("top_supplier_country")
    return scenario.get("country")


def _assess_item(item: dict, scenario: dict) -> dict:
    """Per-reagent exposure to the scenario's target country."""
    target = _target_country(item, scenario)
    suppliers = [s for s in item.get("suppliers") or [] if s.get("country")]
    usable = [s for s in suppliers if _num(s.get("share_pct"), -1) > 0]
    out = {
        "name": item.get("name"),
        "target_country": target,
        "exposure_share_pct": None,
        "status": "UNKNOWN",
        "remaining_share_pct": None,
        "observed_alternatives": [],
        "assessment": None,
        "source_label": item.get("source_label"),
    }

    if not item.get("has_trade_data") or not usable:
        out["assessment"] = "Exposure unknown — no trade data for this reagent."
        return out
    if not target:
        out["assessment"] = "Exposure unknown — no dominant supplier could be identified."
        return out

    key = canonical_country(target)
    share = sum(_num(s["share_pct"]) for s in usable if canonical_country(s["country"]) == key)
    share = round(min(share, 100.0), 4)
    complete = item.get("coverage") == "all_reported_countries"
    alternatives = sorted(
        (
            {"country": s["country"], "share_pct": round(_num(s["share_pct"]), 2)}
            for s in usable
            if canonical_country(s["country"]) != key
        ),
        key=lambda s: s["share_pct"],
        reverse=True,
    )
    out["observed_alternatives"] = alternatives[:5]
    out["exposure_share_pct"] = round(share, 2)

    if share > 0:
        remaining = round(max(100.0 - share, 0.0), 2)
        out["remaining_share_pct"] = remaining
        out["status"] = "EXPOSED"
        if share >= SCENARIO_HIGH_DEPENDENCY_PCT:
            dependency = "high dependency on disrupted country"
        elif share >= SCENARIO_MINIMAL_EXPOSURE_PCT:
            dependency = "partial exposure"
        else:
            dependency = "minimal exposure"
        out["dependency"] = dependency
        text = f"{fmt_pct(share)} sourcing exposure affected — {dependency}"
        if remaining < LIMITED_ALTERNATIVES_SHARE_PCT:
            text += "; limited observed alternative sourcing"
        elif alternatives:
            text += "; alternative sourcing countries observed in trade data"
        out["assessment"] = text + "."
    elif complete:
        out["status"] = "NOT_EXPOSED"
        out["remaining_share_pct"] = 100.0
        out["assessment"] = f"No supply from {target} observed in trade data — lower exposure."
    else:
        # Listed-only data (e.g. WITS top 5): the country may supply an unlisted share.
        out["status"] = "NOT_LISTED"
        out["assessment"] = (
            f"{target} is not among the listed exporters — lower observed exposure "
            "(unlisted share unknown)."
        )
    return out


def _route_usage(item: dict) -> Dict[str, float]:
    routes = item.get("routes") or {}
    if not routes:
        return {ALL_REAGENTS_ROUTE: _num(item.get("cost"))}
    usage = {}
    for route, info in routes.items():
        cost = info.get("cost") if isinstance(info, dict) else info
        usage[str(route)] = _num(cost)
    return usage


def normalize_scenario(scenario: dict) -> dict:
    stype = scenario.get("type")
    if stype not in SCENARIO_TYPES:
        raise ValueError(f"Unknown scenario type: {stype!r}")
    country = (scenario.get("country") or "").strip() or None
    if stype == "country_disruption" and not country:
        raise ValueError("country_disruption requires a country.")
    return {
        "type": stype,
        "country": country if stype != "dominant_supplier_loss" else None,
        "tariff_pct": max(_num(scenario.get("tariff_pct"), DEFAULT_TARIFF_PCT), 0.0),
        "lead_time_increase_days": max(
            _num(scenario.get("lead_time_increase_days"), DEFAULT_LEAD_TIME_INCREASE_DAYS),
            0.0,
        ),
    }


def _describe(s: dict) -> dict:
    target = s["country"] or "each reagent's dominant supplier country"
    labels = {
        "dominant_supplier_loss": "Loss of each reagent's dominant supplier country",
        "country_disruption": f"Supply interruption: {s['country']}",
        "tariff": f"Tariff +{fmt_pct(s['tariff_pct'])} on supply from {target}",
        "lead_time": f"Lead time +{s['lead_time_increase_days']:.0f} days on supply from {target}",
    }
    assumptions = [
        "Uses the supplier-country shares shown in the Risk Audit (USITC: share of "
        "U.S. import value; WITS: share of listed exporters' quantity).",
        "Assumes each route's purchases follow the observed trade mix; actual "
        "supplier contracts may differ.",
        "Exposure is the share of sourcing affected, not a claim that the material "
        "becomes unavailable.",
        "Reagents with no trade data are reported as UNKNOWN, never as unaffected.",
    ]
    if s["type"] == "tariff":
        assumptions.append(
            "The tariff applies to the affected share of each reagent's cost with full "
            "pass-through; no substitution or re-sourcing is modelled."
        )
    if s["type"] == "lead_time":
        assumptions.append(
            "The lead-time increase applies to the affected share of each reagent's "
            "supply; the rest keeps its current lead time. Lead-time risk = "
            f"min(100, days / {LEAD_TIME_FULL_RISK_DAYS} x 100)."
        )
    return {"label": labels[s["type"]], "assumptions": assumptions}


def compute_scenario(items: Iterable[dict], scenario: dict) -> dict:
    """Run one deterministic scenario over the assessed reagents.

    ``items`` come from ``items_from_assessment`` (or tests). Returns per-reagent
    and per-route results; see the module docstring for the formulas.
    """
    s = normalize_scenario(scenario)
    items = list(items)
    tariff_rate = s["tariff_pct"] / 100.0
    delta_days = s["lead_time_increase_days"]

    reagent_rows = []
    routes: Dict[str, dict] = {}
    for item in items:
        row = _assess_item(item, s)
        share = row["exposure_share_pct"] or 0.0
        exposed = row["status"] == "EXPOSED"
        high_dependency = exposed and share >= SCENARIO_HIGH_DEPENDENCY_PCT
        row["routes"] = {}
        for route, cost in _route_usage(item).items():
            agg = routes.setdefault(
                route,
                {
                    "route": route,
                    "total_cost": 0.0,
                    "affected_cost": 0.0,
                    "unknown_cost": 0.0,
                    "added_cost": 0.0,
                    "exposed_reagents": [],
                    "high_dependency_reagents": [],
                    "unknown_reagents": [],
                    "reagent_count": 0,
                },
            )
            agg["reagent_count"] += 1
            agg["total_cost"] += cost
            affected = cost * share / 100.0 if exposed else 0.0
            added = affected * tariff_rate if s["type"] == "tariff" else 0.0
            if row["status"] == "UNKNOWN":
                agg["unknown_cost"] += cost
                agg["unknown_reagents"].append(row["name"])
            elif exposed:
                agg["affected_cost"] += affected
                agg["added_cost"] += added
                agg["exposed_reagents"].append(
                    {
                        "name": row["name"],
                        "exposure_share_pct": round(share, 2),
                        "affected_cost": round(affected, 2),
                    }
                )
                if high_dependency:
                    agg["high_dependency_reagents"].append(row["name"])
            row["routes"][route] = {
                "cost": round(cost, 2),
                "affected_cost": round(affected, 2),
                "added_cost": round(added, 2),
            }
        if s["type"] == "lead_time":
            # The increase applies to the affected share of supply only.
            base_lead = _num(item.get("lead_time_days"), 14)
            after = base_lead + delta_days if exposed else base_lead
            row["lead_time_before"] = base_lead
            row["lead_time_after_affected_supply"] = after
            row["lead_time_risk_before"] = lead_time_risk(base_lead)
            row["lead_time_risk_after_affected_supply"] = lead_time_risk(after)
        reagent_rows.append(row)

    route_rows = []
    for agg in routes.values():
        total = agg["total_cost"]
        known_any = len(agg["unknown_reagents"]) < agg["reagent_count"]
        if total > 0:
            affected_pct = round(agg["affected_cost"] / total * 100, 2)
            unknown_pct = round(agg["unknown_cost"] / total * 100, 2)
        else:
            affected_pct = unknown_pct = None
        tier = (
            classify_route_exposure(affected_pct)
            if known_any and affected_pct is not None
            else "UNKNOWN"
        )
        upper = None
        if tier != "UNKNOWN" and unknown_pct:
            upper_tier = classify_route_exposure(affected_pct + unknown_pct)
            if _TIER_ORDER.index(upper_tier) > _TIER_ORDER.index(tier):
                upper = upper_tier
        note = None
        if total <= 0:
            note = "No reagent costs were provided, so cost exposure cannot be computed."
        elif not known_any:
            note = "No assessed reagent in this route has trade data; exposure is unknown."
        elif upper:
            note = (
                f"{fmt_pct(unknown_pct)} of assessed reagent cost has no trade data; "
                f"exposure could be up to {upper} if that portion were also affected."
            )
        route_row = {
            "route": agg["route"],
            "reagent_count": agg["reagent_count"],
            "assessed_reagent_cost": round(total, 2),
            "affected_cost": round(agg["affected_cost"], 2),
            "affected_pct": affected_pct,
            "unknown_cost": round(agg["unknown_cost"], 2),
            "unknown_pct": unknown_pct,
            "exposure_tier": tier,
            "exposure_label": ROUTE_TIER_LABELS[tier],
            "exposure_tier_if_unknown_affected": upper,
            "exposed_reagents": sorted(
                agg["exposed_reagents"], key=lambda e: e["affected_cost"], reverse=True
            ),
            "high_dependency_reagents": agg["high_dependency_reagents"],
            "unknown_reagents": agg["unknown_reagents"],
            "note": note,
        }
        if s["type"] == "tariff":
            route_row["added_cost"] = round(agg["added_cost"], 2)
            route_row["added_cost_pct"] = (
                round(agg["added_cost"] / total * 100, 2) if total > 0 else None
            )
        if s["type"] == "lead_time":
            route_row["lead_time_increase_days"] = delta_days
        route_rows.append(route_row)

    route_rows.sort(key=lambda r: r["route"])
    return {
        "scenario": {**s, **_describe(s)},
        "routes": route_rows,
        "reagents": reagent_rows,
        "method": "deterministic",
    }
