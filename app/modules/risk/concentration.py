"""
Concentration risk, alternative sourcing and provenance for trade-derived data.

Kept separate from country stability ("geographic exposure"): this module only
describes *how concentrated* the reported supply of an HS6 product is, using
supplier-country shares from the trade data, and where those numbers came from.
It never judges a country — it reports measurable shares.

All logic is deterministic. Thresholds live in ``risk_config``.
"""

from __future__ import annotations

from typing import Iterable, List, Optional

from .risk_config import (
    CONCENTRATION_THRESHOLDS,
    LIMITED_ALTERNATIVES_SHARE_PCT,
    MAX_ALTERNATE_COUNTRIES_LISTED,
    canonical_country,
    is_aggregate_reporter,
)

# share_basis values
SHARE_OF_TOTAL = "share_of_total"  # shares of the full reported total (USITC)
SHARE_OF_LISTED = "share_of_listed"  # shares of the listed rows only (WITS top 5)

DEFAULT_BASIS_PHRASE = "the reported supply for this product"

# Data-quality levels, best first.
_QUALITY_ORDER = ["HIGH", "MEDIUM", "LOW"]


def fmt_pct(value: Optional[float]) -> str:
    """Format a percentage for explanations: 95.0 -> '95%', 86.24 -> '86.2%'."""
    if value is None:
        return "n/a"
    value = float(value)
    if 0 < value < 0.05:
        return "<0.1%"
    rounded = round(value, 1)
    return f"{rounded:.0f}%" if rounded.is_integer() else f"{rounded:.1f}%"


def _share(value) -> Optional[float]:
    try:
        share = float(value)
    except (TypeError, ValueError):
        return None
    if share != share or share <= 0:  # NaN / zero / negative -> no usable share
        return None
    return share


# =================================================================
# NORMALISING TRADE DATA
# =================================================================


def suppliers_from_trade_data(sc: Optional[dict]) -> List[dict]:
    """Normalise USITC / WITS supplier rows to ``[{country, share_pct, is_aggregate}]``.

    Uses the full country list when the source provides one (USITC), otherwise
    the listed top exporters (WITS). Shares keep the source's basis; see
    ``sc["share_basis"]``.
    """
    if not sc or sc.get("status") != "success":
        return []
    rows = sc.get("all_countries") or sc.get("top_exporters") or []
    suppliers = []
    for row in rows:
        name = row.get("reporter") or row.get("country")
        if not name:
            continue
        share = row.get("share_of_total_pct")
        if share is None:
            share = row.get("share_of_top5_pct")
        suppliers.append(
            {
                "country": str(name),
                "share_pct": _share(share),
                "is_aggregate": row.get("reporter_type") == "aggregate"
                or is_aggregate_reporter(name),
            }
        )
    return suppliers


# =================================================================
# CONCENTRATION RISK
# =================================================================


def _coverage_note(share_basis: str, known: int, total_count: Optional[int]) -> str:
    plural = "country" if known == 1 else "countries"
    if share_basis == SHARE_OF_TOTAL and total_count:
        total_plural = "country" if total_count == 1 else "countries"
        return (
            f"Based on all {total_count} supplier {total_plural} reported in the "
            "source data; shares are of the reported total."
        )
    if share_basis == SHARE_OF_LISTED:
        return (
            f"Concentration assessment is based on the top {known} reported supplier "
            f"{plural}; shares are relative to those listed suppliers, not to a world total."
        )
    return f"Concentration assessment is based on the top {known} reported supplier {plural}."


def assess_concentration(
    suppliers: Iterable[dict],
    share_basis: str = SHARE_OF_TOTAL,
    total_country_count: Optional[int] = None,
    basis_phrase: str = DEFAULT_BASIS_PHRASE,
    thresholds: Optional[dict] = None,
) -> dict:
    """Classify sourcing concentration from supplier-country shares.

    ``suppliers``: ``[{"country": str, "share_pct": float|None, "is_aggregate": bool}]``.
    Only the top one or two countries are needed. Countries that are not listed
    are *not* assumed to have a zero share.

    Rule (thresholds from ``risk_config.CONCENTRATION_THRESHOLDS``):
      * HIGH    if top-1 share >= high_top1_pct
                or top-1 + top-2 shares >= high_top2_combined_pct
      * MEDIUM  if top-1 share >= medium_top1_pct
      * LOW     otherwise
      * UNKNOWN if no usable share exists, or if the only share available is a
                lone listed supplier whose share is relative to the listed
                rows (it is 100% by construction, not a measurement).
    """
    th = {**CONCENTRATION_THRESHOLDS, **(thresholds or {})}
    suppliers = [
        {**s, "is_aggregate": bool(s.get("is_aggregate")) or is_aggregate_reporter(s.get("country"))}
        for s in (suppliers or [])
    ]
    groupings = [s for s in suppliers if s["is_aggregate"]]
    countries = [s for s in suppliers if not s["is_aggregate"] and s.get("country")]
    with_share = sorted(
        (
            {"country": s["country"], "share_pct": _share(s.get("share_pct"))}
            for s in countries
        ),
        key=lambda s: s["share_pct"] or 0,
        reverse=True,
    )
    with_share = [s for s in with_share if s["share_pct"] is not None]

    available = total_country_count if total_country_count else (len(countries) or None)
    result = {
        "tier": "UNKNOWN",
        "top_supplier_country": None,
        "top_supplier_share": None,
        "second_supplier_country": None,
        "second_supplier_share": None,
        "top_two_combined_share": None,
        "supplier_countries_available": available,
        "supplier_countries_with_shares": len(with_share),
        "share_basis": share_basis,
        "coverage_note": None,
        "rule": None,
        "explanation": None,
        "caveat": None,
        "grouping_outranks_countries": False,
        "excluded_groupings": [
            {"name": g["country"], "share_pct": _share(g.get("share_pct"))}
            for g in groupings
        ],
        "thresholds": th,
    }

    if not with_share:
        result["rule"] = "no usable supplier-country shares"
        result["explanation"] = (
            "No supplier-country shares are available in the source data, so "
            "concentration cannot be assessed."
        )
        return result

    top = with_share[0]
    second = with_share[1] if len(with_share) > 1 else None
    result["top_supplier_country"] = top["country"]
    result["coverage_note"] = _coverage_note(share_basis, len(with_share), total_country_count)

    if share_basis == SHARE_OF_LISTED and second is None:
        result["rule"] = "single listed supplier with listed-only shares"
        result["explanation"] = (
            f"Only one supplier country ({top['country']}) is listed and shares are "
            "relative to the listed suppliers, so its share is not a measured "
            "concentration. Concentration cannot be assessed from this data."
        )
        return result

    top1 = top["share_pct"]
    result["top_supplier_share"] = round(top1, 2)
    combined = None
    if second is not None:
        result["second_supplier_country"] = second["country"]
        result["second_supplier_share"] = round(second["share_pct"], 2)
        combined = top1 + second["share_pct"]
        result["top_two_combined_share"] = round(combined, 2)

    only_country = share_basis == SHARE_OF_TOTAL and total_country_count == 1

    if top1 >= th["high_top1_pct"]:
        tier = "HIGH"
        result["rule"] = f"top supplier share {fmt_pct(top1)} >= {fmt_pct(th['high_top1_pct'])}"
        if only_country:
            explanation = (
                f"{top['country']} is the only origin country in {basis_phrase} "
                f"({fmt_pct(top1)}). This creates high single-country concentration."
            )
        else:
            explanation = (
                f"{fmt_pct(top1)} of {basis_phrase} originated from {top['country']}. "
                "This creates high single-country concentration."
            )
    elif combined is not None and combined >= th["high_top2_combined_pct"]:
        tier = "HIGH"
        result["rule"] = (
            f"top two suppliers combined {fmt_pct(combined)} >= "
            f"{fmt_pct(th['high_top2_combined_pct'])}"
        )
        explanation = (
            f"{top['country']} ({fmt_pct(top1)}) and {second['country']} "
            f"({fmt_pct(second['share_pct'])}) together account for {fmt_pct(combined)} "
            f"of {basis_phrase}. This creates high two-country concentration."
        )
    elif top1 >= th["medium_top1_pct"]:
        tier = "MEDIUM"
        result["rule"] = f"top supplier share {fmt_pct(top1)} >= {fmt_pct(th['medium_top1_pct'])}"
        explanation = (
            f"The largest supplier, {top['country']}, accounts for {fmt_pct(top1)} of "
            f"{basis_phrase}. Sourcing is moderately concentrated."
        )
    else:
        tier = "LOW"
        result["rule"] = f"top supplier share {fmt_pct(top1)} < {fmt_pct(th['medium_top1_pct'])}"
        explanation = (
            f"The largest supplier, {top['country']}, accounts for {fmt_pct(top1)} of "
            f"{basis_phrase}. Sourcing appears relatively diversified based on the "
            "available data."
        )

    # The second supplier's share bounds the two-country rule. If it is not
    # reported, the tier may be understated — say so rather than assume zero.
    if (
        second is None
        and tier != "HIGH"
        and not only_country
        and 2 * top1 >= th["high_top2_combined_pct"]
    ):
        result["caveat"] = (
            "The second supplier's share is not reported; if it is close to the "
            "top supplier's, two-country concentration could be HIGH."
        )

    largest_grouping = max(
        (g for g in result["excluded_groupings"] if g["share_pct"]),
        key=lambda g: g["share_pct"],
        default=None,
    )
    if largest_grouping and largest_grouping["share_pct"] > top1:
        result["grouping_outranks_countries"] = True
        note = (
            f"The grouping '{largest_grouping['name']}' ({fmt_pct(largest_grouping['share_pct'])}) "
            "outranks every single country in the source data but is not a country, "
            "so it is excluded from the top-supplier calculation."
        )
        result["caveat"] = f"{result['caveat']} {note}".strip() if result["caveat"] else note

    result["tier"] = tier
    result["explanation"] = explanation
    return result


# =================================================================
# ALTERNATIVE SOURCING / SUBSTITUTABILITY
# =================================================================


def assess_alternatives(
    suppliers: Iterable[dict],
    concentration: dict,
    has_trade_data: bool,
    substitutability_score: Optional[int] = None,
    substitutability_source: str = "default",
) -> dict:
    """Describe alternative sourcing visible in the data, without overclaiming.

    Trade data shows *other origin countries*, not qualified suppliers, and the
    app has no evidence base for alternative chemistry, so those are reported
    as not known.
    """
    top = concentration.get("top_supplier_country")
    share_basis = concentration.get("share_basis")
    countries = [
        {"country": s["country"], "share_pct": _share(s.get("share_pct"))}
        for s in (suppliers or [])
        if s.get("country")
        and not (s.get("is_aggregate") or is_aggregate_reporter(s.get("country")))
    ]
    alternates = sorted(
        (
            c
            for c in countries
            if c["share_pct"] is not None
            and canonical_country(c["country"]) != canonical_country(top)
        ),
        key=lambda c: c["share_pct"],
        reverse=True,
    )

    total_available = concentration.get("supplier_countries_available")
    if not has_trade_data or top is None:
        count = None
        basis = "no_information"
    else:
        if share_basis == SHARE_OF_TOTAL and total_available:
            count = max(total_available - 1, 0)
        else:
            count = len(alternates)
        basis = "observed_in_trade_data" if count else "none_observed_in_trade_data"

    top_share = concentration.get("top_supplier_share")
    alternate_share = (
        round(max(100.0 - top_share, 0.0), 2)
        if top_share is not None and basis != "no_information"
        else None
    )
    limited = (
        alternate_share is not None and alternate_share < LIMITED_ALTERNATIVES_SHARE_PCT
    )

    if basis == "no_information":
        summary = "No information: no trade data is available for this reagent."
    elif basis == "none_observed_in_trade_data":
        summary = "No alternative sourcing countries are observed in the trade data."
    else:
        listed = ", ".join(
            f"{c['country']} ({fmt_pct(c['share_pct'])})"
            for c in alternates[:MAX_ALTERNATE_COUNTRIES_LISTED]
        )
        more = count - min(len(alternates), MAX_ALTERNATE_COUNTRIES_LISTED)
        if more > 0:
            listed += f" and {more} more"
        summary = (
            f"Alternative sourcing countries observed in trade data: {listed}. "
            "These are trade origins, not verified or qualified suppliers."
        )
        if limited:
            summary = (
                f"Limited observed alternative sourcing (all other countries together: "
                f"{fmt_pct(alternate_share)}). " + summary
            )

    user_sub = substitutability_source == "user_input"
    return {
        "alternate_supplier_countries": alternates[:MAX_ALTERNATE_COUNTRIES_LISTED],
        "alternate_country_count": count,
        "alternate_share_pct": alternate_share,
        "limited_alternatives": limited,
        "alternative_sourcing_basis": basis,
        # No procurement / qualified-supplier data exists in the app.
        "alternative_supply_known": False,
        # The app does not infer chemical substitutes.
        "alternative_chemistry_known": False,
        "summary": summary,
        "substitutability_score": substitutability_score,
        "substitutability_source": "user_input" if user_sub else "default",
        "substitutability_confidence": "user_asserted" if user_sub else "none",
        "substitutability_note": (
            "User-entered substitutability (1-10); not independently verified."
            if user_sub
            else "Default value (5) — no substitutability information provided."
        ),
    }


# =================================================================
# PROVENANCE & DATA QUALITY
# =================================================================

HS6_SOURCE_LABELS = {
    "cas_mapping": "CAS → HS mapping (reagent_mapping.csv)",
    "compound_db": "Compound registry (SQLite compounds.hs6_code)",
    "inchikey_map": "InChIKey → HS6 map (compound_hs6_map.json)",
    "name_hint": "Name match against compound_hs6_map.json hints",
}


def build_provenance(sc: Optional[dict], hs6: Optional[str], hs6_source: Optional[str]) -> dict:
    """Collect the 'where did this number come from' fields for one reagent."""
    prov = {
        "status": (sc or {}).get("status", "no_hs6_mapping" if not hs6 else "no_trade_data"),
        "hs6_code": hs6,
        "hs6_source": hs6_source,
        "hs6_source_label": HS6_SOURCE_LABELS.get(hs6_source),
    }
    if not sc or sc.get("status") != "success":
        return prov
    keys = (
        "source",
        "source_url",
        "source_label",
        "source_files",
        "description",
        "year",
        "period_type",
        "period_label",
        "is_partial_year",
        "year_selection_reason",
        "year_selection_note",
        "newer_partial_period_available",
        "trade_flow",
        "partner",
        "ranking_basis",
        "share_basis",
        "share_basis_label",
        "coverage",
        "country_count",
        "listed_count",
        "total_value_usd",
        "prior_year",
        "notes",
    )
    prov.update({k: sc.get(k) for k in keys if k in sc})
    prov["hs6_code"] = sc.get("hs6_code") or hs6
    return prov


def assess_data_quality(provenance: dict, concentration: dict) -> dict:
    """Qualitative data-quality flag from deterministic criteria (no percentages).

    Starts at HIGH and is capped by each limitation found:
      LOW    — partial-year/YTD period; unknown period coverage; concentration
               UNKNOWN; a non-country grouping outranks every country
      MEDIUM — shares relative to listed suppliers only (not a world total);
               fewer than 3 supplier countries reported; HS6 matched by name only
    """
    if provenance.get("status") != "success":
        reason = (
            "No HS6 code is mapped for this reagent."
            if provenance.get("status") == "no_hs6_mapping"
            else "No trade data is available for the mapped HS6 code."
        )
        return {"level": "NO_DATA", "reasons": [reason]}

    caps = []
    if provenance.get("is_partial_year"):
        caps.append(("LOW", f"Partial-year data ({provenance.get('period_label')})."))
    elif provenance.get("period_type") not in ("full_year",):
        caps.append(("LOW", "Period coverage of the data could not be determined."))
    if concentration.get("tier") == "UNKNOWN":
        caps.append(("LOW", "Concentration could not be assessed from the shares available."))
    if concentration.get("grouping_outranks_countries"):
        caps.append(("LOW", "A regional grouping outranks every single country in the source."))
    if provenance.get("share_basis") == SHARE_OF_LISTED:
        caps.append(
            ("MEDIUM", "Shares are relative to the listed top exporters, not a world total.")
        )
    countries = concentration.get("supplier_countries_available") or 0
    if countries < 3:
        caps.append(("MEDIUM", f"Only {countries} supplier countr{'y' if countries == 1 else 'ies'} reported."))
    if provenance.get("hs6_source") == "name_hint":
        caps.append(("MEDIUM", "HS6 code matched by reagent name, not by CAS or structure."))

    level = "HIGH"
    for cap_level, _ in caps:
        if _QUALITY_ORDER.index(cap_level) > _QUALITY_ORDER.index(level):
            level = cap_level
    reasons = [reason for _, reason in caps] or [
        "Complete-year data covering all reported supplier countries, with a mapped HS6 code."
    ]
    return {"level": level, "reasons": reasons}


def build_geographic_profile(
    sc: Optional[dict],
    hs6: Optional[str],
    hs6_source: Optional[str],
    substitutability_score: Optional[int] = None,
    substitutability_source: str = "default",
) -> dict:
    """Concentration + alternatives + provenance + data quality for one reagent."""
    sc = sc or {}
    suppliers = suppliers_from_trade_data(sc)
    has_data = sc.get("status") == "success"
    # A full country count is only meaningful when every reporting country is
    # in the data (USITC); WITS stores the top exporters only.
    total_count = (
        sc.get("country_count") if sc.get("coverage") == "all_reported_countries" else None
    )
    concentration = assess_concentration(
        suppliers,
        share_basis=sc.get("share_basis", SHARE_OF_TOTAL),
        total_country_count=total_count,
        basis_phrase=sc.get("basis_phrase", DEFAULT_BASIS_PHRASE),
    )
    if not has_data:
        concentration["explanation"] = (
            "No HS6 code is mapped for this reagent, so no trade data could be looked up."
            if not hs6
            else f"No trade data is available for HS6 {hs6}."
        ) + " Concentration is unknown (not assumed safe or risky)."
        concentration["rule"] = "no trade data"
    provenance = build_provenance(sc, hs6, hs6_source)
    alternatives = assess_alternatives(
        suppliers,
        concentration,
        has_data,
        substitutability_score=substitutability_score,
        substitutability_source=substitutability_source,
    )
    return {
        "suppliers": [s for s in suppliers if not s["is_aggregate"]],
        "concentration": concentration,
        "alternatives": alternatives,
        "provenance": provenance,
        "data_quality": assess_data_quality(provenance, concentration),
    }
