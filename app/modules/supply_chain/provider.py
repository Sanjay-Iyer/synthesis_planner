"""
Supply-chain data provider.

Live-scans the supply-chain drop folder (``config.SUPPLY_CHAIN_DIR``) for trade
data files, parses any USITC DataWeb exports it finds, and indexes them by HS6.
Results are cached in memory and only rebuilt when a file is added, removed, or
modified (detected via name/mtime/size signature), so per-request lookups stay
cheap even though the folder is the source of truth.

Imports drive origin/concentration risk: for a given HS6, the top source
countries by U.S. import value and the top-source share of total imports are
the headline "where does this come from / how concentrated is it" signal.
Exports are indexed too and surfaced as destination context.

Year selection prefers the latest *complete* calendar year. Partial-year (YTD)
columns — e.g. a single January — are only used when no complete year has data
or when the caller explicitly asks for YTD, and are always labelled as such.
See ``select_trade_year``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from app.config import SUPPLY_CHAIN_DIR
from app.modules.risk.concentration import assess_concentration
from app.modules.risk.risk_config import YOY_TOTAL_CHANGE_NOTE_PCT
from . import usitc_ingest

SOURCE_NAME = "USITC DataWeb"
SOURCE_URL = "https://dataweb.usitc.gov/"

_TOP_N = 5

# Valid calendar-year range for trade columns; anything outside is treated as
# malformed and ignored by select_trade_year.
_MIN_YEAR, _MAX_YEAR = 1900, 2100

# In-memory cache: rebuilt only when the folder signature changes.
_CACHE: Dict[str, object] = {"signature": None, "data": None}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _folder_signature() -> tuple:
    """A cheap fingerprint of the folder's data files (name, mtime, size)."""
    folder = Path(SUPPLY_CHAIN_DIR)
    if not folder.exists():
        return ()
    sig = []
    for p in sorted(folder.glob("*.xlsx")):
        if p.name.startswith("~$"):  # Excel lock/temp file
            continue
        st = p.stat()
        sig.append((p.name, int(st.st_mtime), st.st_size))
    return tuple(sig)


def _new_node() -> dict:
    return {
        "import": {},  # year(int) -> {country: value}
        "export": {},  # year(int) -> {country: value}
        "description": None,
        # Per-flow period coverage: flow -> year -> {"period_type", "period_label", "months"}.
        # Tracked per flow so a partial year in one file never marks the same
        # year as partial (or complete) for the other flow.
        "coverage": {"import": {}, "export": {}},
        "full_years": set(),
        "partial_years": set(),
        "sources": set(),
        "sources_by_flow": {"import": set(), "export": set()},
    }


def _record_coverage(node: dict, flow: str, parsed: dict) -> None:
    """Record which years a parsed file covers fully vs partially for ``flow``."""
    cov = node["coverage"].get(flow)
    if cov is None:
        return
    for year in parsed["full_years"]:
        cov[year] = {
            "period_type": "full_year",
            "period_label": f"Full-year {year}",
            "months": 12,
        }
    for year in parsed["partial_years"]:
        if cov.get(year, {}).get("period_type") == "full_year":
            continue  # another file covers this year completely
        period = (parsed.get("partial_periods") or {}).get(year) or {}
        cov[year] = {
            "period_type": "partial_year",
            "period_label": period.get("label") or f"Partial-year {year} (YTD)",
            "months": period.get("months"),
        }


def _build_index() -> dict:
    """Parse every data file in the folder and build the HS6 index."""
    folder = Path(SUPPLY_CHAIN_DIR)
    index: Dict[str, dict] = {}
    files_meta = []

    paths = []
    if folder.exists():
        paths = [
            p for p in sorted(folder.glob("*.xlsx")) if not p.name.startswith("~$")
        ]

    for path in paths:
        try:
            parsed = usitc_ingest.parse_usitc_file(str(path))
        except Exception as e:  # noqa: BLE001 - report, do not crash the page
            files_meta.append(
                {
                    "filename": path.name,
                    "status": "error",
                    "error": str(e),
                }
            )
            continue

        flow = parsed["trade_flow"]
        for rec in parsed["records"]:
            hs6 = rec["hts6"]
            node = index.setdefault(hs6, _new_node())
            if not node["description"] and rec["description"]:
                node["description"] = rec["description"]
            node["full_years"].update(parsed["full_years"])
            node["partial_years"].update(parsed["partial_years"])
            node["sources"].add(path.name)
            flow_sources = node["sources_by_flow"].get(flow)
            if flow_sources is not None and path.name not in flow_sources:
                flow_sources.add(path.name)
                _record_coverage(node, flow, parsed)

            flow_map = node.get(flow)
            if flow_map is None:  # unknown trade flow -> index for context only
                continue
            country = rec["country"]
            for year, val in rec["values"].items():
                year_map = flow_map.setdefault(year, {})
                year_map[country] = year_map.get(country, 0.0) + val

        files_meta.append(
            {
                "filename": path.name,
                "status": "ok",
                "trade_flow": flow,
                "value_measure": parsed["value_measure"],
                "record_count": len(parsed["records"]),
                "hts6_count": len({r["hts6"] for r in parsed["records"]}),
                "full_years": parsed["full_years"],
                "partial_years": parsed["partial_years"],
                "partial_period_labels": [
                    (p or {}).get("label")
                    for p in (parsed.get("partial_periods") or {}).values()
                ],
                "title": parsed["title"],
            }
        )

    return {
        "index": index,
        "files": files_meta,
        "indexed_at": _utc_now(),
        "folder": str(folder),
    }


def get_index(force: bool = False) -> dict:
    """Return the cached index, rebuilding only if the folder changed."""
    sig = _folder_signature()
    if not force and _CACHE["signature"] == sig and _CACHE["data"] is not None:
        return _CACHE["data"]  # type: ignore[return-value]
    data = _build_index()
    _CACHE["signature"] = sig
    _CACHE["data"] = data
    return data


def _coerce_year(value) -> Optional[int]:
    """Return ``value`` as a calendar year, or None if it is not a sane year."""
    if value is None or isinstance(value, bool):
        return None
    try:
        year_float = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if year_float != year_float or not year_float.is_integer():  # NaN / 2025.5
        return None
    year = int(year_float)
    return year if _MIN_YEAR <= year <= _MAX_YEAR else None


def _coerce_total(value) -> float:
    try:
        total = float(value)
    except (TypeError, ValueError):
        return 0.0
    return total if total == total else 0.0  # NaN -> 0


def select_trade_year(
    years: Mapping[Any, Mapping[str, Any]],
    requested_year: Any = None,
    allow_partial: bool = False,
) -> Optional[dict]:
    """Choose which trade year to report.

    ``years`` maps a year to ``{"total": float, "period_type": str, "period_label": str}``
    where ``period_type`` is ``"full_year"`` or ``"partial_year"``. Anything else
    (missing, misspelled) is treated as ``"unknown"`` coverage.

    Rules, in order:
      1. Years that are not valid calendar years, or whose total is not
         positive, are ignored.
      2. An explicitly requested year wins if it has data.
      3. ``allow_partial=True`` (an explicit YTD request) picks the newest
         partial year that is newer than every complete year.
      4. Otherwise the latest *complete* year is used.
      5. If no complete year has data, the latest partial year is used (and is
         labelled partial); failing that, the latest year of unknown coverage.

    Returns None when nothing usable exists, else::

        {"year", "period_type", "period_label", "is_partial_year",
         "reason", "newer_partial_year", "newer_partial_label",
         "requested_year_unavailable", "ignored_years"}
    """
    usable: Dict[int, dict] = {}
    ignored = []
    for raw_year, info in (years or {}).items():
        year = _coerce_year(raw_year)
        if year is None:
            ignored.append(raw_year)
            continue
        info = info or {}
        if _coerce_total(info.get("total")) <= 0:
            continue
        ptype = info.get("period_type")
        if ptype not in ("full_year", "partial_year"):
            ptype = "unknown"
        current = usable.get(year)
        # Two entries for one year (e.g. "2025" and 2025): prefer a full year.
        if current is None or current["period_type"] != "full_year":
            usable[year] = {"period_type": ptype, "period_label": info.get("period_label")}

    if not usable:
        return None

    complete = sorted(y for y, v in usable.items() if v["period_type"] == "full_year")
    partial = sorted(y for y, v in usable.items() if v["period_type"] == "partial_year")
    unknown = sorted(y for y, v in usable.items() if v["period_type"] == "unknown")
    latest_complete = complete[-1] if complete else None
    newer_partial = [y for y in partial if latest_complete is None or y > latest_complete]

    def _result(year: int, reason: str) -> dict:
        entry = usable[year]
        ptype = entry["period_type"]
        label = entry.get("period_label")
        if not label:
            label = {
                "full_year": f"Full-year {year}",
                "partial_year": f"Partial-year {year} (YTD)",
            }.get(ptype, f"{year} (period coverage unknown)")
        unused_partial = [y for y in newer_partial if y != year]
        newer_year = unused_partial[-1] if unused_partial else None
        newer_label = None
        if newer_year is not None:
            newer_label = (
                usable[newer_year].get("period_label")
                or f"Partial-year {newer_year} (YTD)"
            )
        return {
            "year": year,
            "period_type": ptype,
            "period_label": label,
            "is_partial_year": {"full_year": False, "partial_year": True}.get(ptype),
            "reason": reason,
            "newer_partial_year": newer_year,
            "newer_partial_label": newer_label,
            "requested_year_unavailable": False,
            "ignored_years": ignored,
        }

    requested = _coerce_year(requested_year)
    if requested is not None and requested in usable:
        return _result(requested, "requested_year")

    if allow_partial and newer_partial:
        chosen = _result(newer_partial[-1], "explicit_ytd_requested")
    elif latest_complete is not None:
        chosen = _result(latest_complete, "latest_complete_year")
    elif partial:
        chosen = _result(partial[-1], "no_complete_year_available")
    else:
        chosen = _result(unknown[-1], "coverage_unknown_fallback")

    chosen["requested_year_unavailable"] = requested_year is not None
    return chosen


YEAR_SELECTION_REASONS = {
    "requested_year": "Year explicitly requested.",
    "explicit_ytd_requested": "Partial-year (YTD) data explicitly requested.",
    "latest_complete_year": "Latest complete calendar year with data.",
    "no_complete_year_available": (
        "No complete year has data for this code; using partial-year (YTD) data."
    ),
    "coverage_unknown_fallback": (
        "Period coverage of the available data could not be determined."
    ),
}


def _year_total(country_map: dict) -> float:
    return sum(v for v in country_map.values() if v > 0)


def _year_table(node: dict, flow: str) -> Dict[int, dict]:
    """Build the ``years`` argument for select_trade_year from an index node."""
    coverage = node.get("coverage", {}).get(flow, {})
    table = {}
    for year, country_map in (node.get(flow) or {}).items():
        cov = coverage.get(year, {})
        table[year] = {
            "total": _year_total(country_map),
            "period_type": cov.get("period_type"),
            "period_label": cov.get("period_label"),
        }
    return table


def _rank_countries(country_map: dict):
    ranked = sorted(
        ((c, v) for c, v in country_map.items() if v > 0),
        key=lambda kv: kv[1],
        reverse=True,
    )
    total = sum(v for _, v in ranked)
    return ranked, total


def _country_rows(ranked, total) -> list:
    return [
        {
            "rank": i + 1,
            "reporter": country,
            "reporter_type": "country",
            "trade_value_usd": round(value, 2),
            "trade_value_1000_usd": round(value / 1000.0, 2),
            # 4 decimals so small origins keep a non-zero share.
            "share_of_total_pct": round(value / total * 100, 4) if total else 0,
        }
        for i, (country, value) in enumerate(ranked)
    ]


def _prior_complete_year(node: dict, flow: str, chosen_year: int) -> Optional[dict]:
    """Top supplier and total for the latest complete year before ``chosen_year``."""
    table = _year_table(node, flow)
    earlier = sorted(
        y
        for y, info in table.items()
        if y < chosen_year and info["period_type"] == "full_year" and info["total"] > 0
    )
    if not earlier:
        return None
    year = earlier[-1]
    ranked, total = _rank_countries(node[flow][year])
    top_country, top_value = ranked[0]
    return {
        "year": year,
        "top_supplier_country": top_country,
        "top_supplier_share": round(top_value / total * 100, 2) if total else None,
        "total_value_usd": round(total, 2),
    }


def _fmt_usd(value: float) -> str:
    if value >= 1e9:
        return f"${value / 1e9:.2f}B"
    if value >= 1e6:
        return f"${value / 1e6:.1f}M"
    if value >= 1e3:
        return f"${value / 1e3:.1f}K"
    return f"${value:.0f}"


def get_origin_concentration(
    hs6_code: str, year: Optional[int] = None, allow_partial: bool = False
) -> dict:
    """Origin concentration for an HS6, from U.S. import data.

    Returns a dict compatible with the risk engine's supply-chain contract
    (status, top_exporters[].reporter, concentration_top1_pct,
    concentration_risk_flag, data_quality_note) plus provenance: source, year,
    period type/label, why the year was chosen, ranking/share basis and
    coverage. Status is "no_trade_data" when no import data is indexed.
    """
    hs6 = usitc_ingest.normalize_hs6(hs6_code)
    if not hs6:
        return {"status": "no_trade_data", "reason": "invalid_hs6"}

    data = get_index()
    node = data["index"].get(hs6)
    if not node or not node["import"]:
        return {"status": "no_trade_data", "hs6_code": hs6}

    selection = select_trade_year(
        _year_table(node, "import"), requested_year=year, allow_partial=allow_partial
    )
    if selection is None:
        return {"status": "no_trade_data", "hs6_code": hs6}

    chosen = selection["year"]
    ranked, total = _rank_countries(node["import"][chosen])
    if not ranked:
        return {"status": "no_trade_data", "hs6_code": hs6}

    all_countries = _country_rows(ranked, total)
    top_exporters = all_countries[:_TOP_N]
    top1_share = top_exporters[0]["share_of_total_pct"]
    is_partial = selection["is_partial_year"]

    notes = []
    if is_partial:
        notes.append(
            f"{selection['period_label']} is partial-year data; shares cover only "
            "that period and are not comparable with a full year."
        )
    elif selection["period_type"] == "unknown":
        notes.append("Period coverage could not be determined from the file.")
    if selection["newer_partial_label"]:
        notes.append(
            f"Newer partial-year data ({selection['newer_partial_label']}) exists but "
            "was not used; the latest complete year is preferred."
        )

    prior = _prior_complete_year(node, "import", chosen)
    if prior:
        if prior["top_supplier_country"] != top_exporters[0]["reporter"]:
            notes.append(
                f"Top supplier changed: {prior['year']} was "
                f"{prior['top_supplier_country']} ({prior['top_supplier_share']:.1f}%)."
            )
        if prior["total_value_usd"] > 0:
            change = (total - prior["total_value_usd"]) / prior["total_value_usd"] * 100
            if abs(change) >= YOY_TOTAL_CHANGE_NOTE_PCT:
                direction = "higher" if change > 0 else "lower"
                notes.append(
                    f"Total reported imports ({_fmt_usd(total)}) were "
                    f"{abs(change):.0f}% {direction} than {prior['year']} "
                    f"({_fmt_usd(prior['total_value_usd'])})."
                )

    flag = assess_concentration(
        [
            {"country": e["reporter"], "share_pct": e["share_of_total_pct"]}
            for e in top_exporters
        ],
        share_basis="share_of_total",
        total_country_count=len(ranked),
    )["tier"]

    period_label = selection["period_label"]
    return {
        "status": "success",
        "source": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "source_label": f"{SOURCE_NAME} — U.S. imports for consumption, {period_label}",
        "source_files": sorted(node.get("sources_by_flow", {}).get("import", [])),
        "hs6_code": hs6,
        "description": node.get("description"),
        "year": chosen,
        "period_type": selection["period_type"],
        "period_label": period_label,
        "is_partial_year": is_partial,
        "year_selection_reason": selection["reason"],
        "year_selection_note": YEAR_SELECTION_REASONS.get(selection["reason"]),
        "newer_partial_period_available": selection["newer_partial_label"],
        "trade_flow": "import",
        "value_measure": "Customs Value",
        "ranking_basis": "U.S. import customs value (USD)",
        "share_basis": "share_of_total",
        "share_basis_label": "Share of total reported U.S. imports (all origin countries)",
        "basis_phrase": "reported U.S. imports for this HS6 product",
        "data_phrase": "the available U.S. import data",
        "scope_note": (
            "U.S. imports for consumption only: shows where U.S. imports come from. "
            "Does not include U.S. domestic production and is not global supply."
        ),
        "coverage": "all_reported_countries",
        "country_count": len(ranked),
        "listed_count": len(top_exporters),
        "total_value_usd": round(total, 2),
        "top_exporters": top_exporters,
        "all_countries": all_countries,
        "concentration_top1_pct": top1_share,
        "concentration_risk_flag": flag,
        "prior_year": prior,
        "data_quality_note": " ".join(notes) if notes else None,
        "notes": notes,
    }


def get_trade_profile(hs6_code: str, allow_partial: bool = False) -> dict:
    """Full two-sided profile for an HS6: import concentration + export context."""
    hs6 = usitc_ingest.normalize_hs6(hs6_code)
    if not hs6:
        return {"status": "no_trade_data"}

    data = get_index()
    node = data["index"].get(hs6)
    if not node:
        return {"status": "no_trade_data"}

    profile = {
        "status": "success",
        "hs6_code": hs6,
        "description": node["description"],
        "sources": sorted(node["sources"]),
        "imports": get_origin_concentration(hs6, allow_partial=allow_partial),
        "exports": None,
    }

    selection = select_trade_year(
        _year_table(node, "export"), allow_partial=allow_partial
    )
    if selection is not None:
        # Shares are of total exports across all destinations, not the top N.
        ranked, total = _rank_countries(node["export"][selection["year"]])
        ranked = ranked[:_TOP_N]
        profile["exports"] = {
            "year": selection["year"],
            "period_type": selection["period_type"],
            "period_label": selection["period_label"],
            "value_measure": "FAS Value",
            "top_destinations": [
                {
                    "rank": i + 1,
                    "country": c,
                    "trade_value_usd": round(v, 2),
                    "share_of_total_pct": round(v / total * 100, 2) if total else 0,
                }
                for i, (c, v) in enumerate(ranked)
            ],
            "is_partial_year": selection["is_partial_year"],
        }

    return profile


def get_status() -> dict:
    """Summarize what supply-chain data is currently indexed (for the UI)."""
    data = get_index()
    index = data["index"]
    hs6_with_imports = sum(1 for n in index.values() if n["import"])
    hs6_with_exports = sum(1 for n in index.values() if n["export"])
    return {
        "folder": data["folder"],
        "indexed_at": data["indexed_at"],
        "files": data["files"],
        "file_count": len(data["files"]),
        "ok_file_count": sum(1 for f in data["files"] if f.get("status") == "ok"),
        "total_hs6": len(index),
        "hs6_with_imports": hs6_with_imports,
        "hs6_with_exports": hs6_with_exports,
    }


def refresh() -> dict:
    """Force a re-scan of the folder and return the new status."""
    get_index(force=True)
    return get_status()
