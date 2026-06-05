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
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from app.config import SUPPLY_CHAIN_DIR
from . import usitc_ingest

# Concentration thresholds (top-source share of total, %). Kept aligned with the
# legacy WITS path in the risk engine so flags read consistently across sources.
HIGH_CONCENTRATION_PCT = 50
MEDIUM_CONCENTRATION_PCT = 30

_TOP_N = 5

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
        "import": {},   # year(int) -> {country: value}
        "export": {},   # year(int) -> {country: value}
        "description": None,
        "full_years": set(),
        "partial_years": set(),
        "sources": set(),
    }


def _build_index() -> dict:
    """Parse every data file in the folder and build the HS6 index."""
    folder = Path(SUPPLY_CHAIN_DIR)
    index: Dict[str, dict] = {}
    files_meta = []

    paths = []
    if folder.exists():
        paths = [p for p in sorted(folder.glob("*.xlsx")) if not p.name.startswith("~$")]

    for path in paths:
        try:
            parsed = usitc_ingest.parse_usitc_file(str(path))
        except Exception as e:  # noqa: BLE001 - report, do not crash the page
            files_meta.append({
                "filename": path.name,
                "status": "error",
                "error": str(e),
            })
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

            flow_map = node.get(flow)
            if flow_map is None:  # unknown trade flow -> index for context only
                continue
            country = rec["country"]
            for year, val in rec["values"].items():
                year_map = flow_map.setdefault(year, {})
                year_map[country] = year_map.get(country, 0.0) + val

        files_meta.append({
            "filename": path.name,
            "status": "ok",
            "trade_flow": flow,
            "value_measure": parsed["value_measure"],
            "record_count": len(parsed["records"]),
            "hts6_count": len({r["hts6"] for r in parsed["records"]}),
            "full_years": parsed["full_years"],
            "partial_years": parsed["partial_years"],
        })

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


def _concentration_flag(top1_share: float) -> str:
    if top1_share > HIGH_CONCENTRATION_PCT:
        return "HIGH"
    if top1_share > MEDIUM_CONCENTRATION_PCT:
        return "MEDIUM"
    return "LOW"


def _pick_year(flow_map: Dict[int, dict], requested: Optional[int]):
    """Pick the reference year.

    Preference, per project decision: use the most recent year that has data
    (closest to today, including a partial current-year column), falling back to
    progressively older years — "any data is better than no data". An explicit
    requested year wins if it has data.
    """
    if requested is not None and _year_total(flow_map.get(requested, {})) > 0:
        return requested
    for year in sorted(flow_map.keys(), reverse=True):
        if _year_total(flow_map[year]) > 0:
            return year
    return None


def _year_total(country_map: dict) -> float:
    return sum(v for v in country_map.values() if v > 0)


def get_origin_concentration(hs6_code: str, year: Optional[int] = None) -> dict:
    """Origin concentration for an HS6, from U.S. import data.

    Returns a dict compatible with the risk engine's supply-chain contract
    (status, top_exporters[].reporter, concentration_top1_pct,
    concentration_risk_flag, data_quality_note) plus source/year provenance.
    Status is "no_trade_data" when no import data is indexed for the code.
    """
    hs6 = usitc_ingest.normalize_hs6(hs6_code)
    if not hs6:
        return {"status": "no_trade_data"}

    data = get_index()
    node = data["index"].get(hs6)
    if not node or not node["import"]:
        return {"status": "no_trade_data"}

    chosen = _pick_year(node["import"], year)
    if chosen is None:
        return {"status": "no_trade_data"}

    countries = node["import"][chosen]
    ranked = sorted(
        ((c, v) for c, v in countries.items() if v > 0),
        key=lambda kv: kv[1],
        reverse=True,
    )
    if not ranked:
        return {"status": "no_trade_data"}

    total = sum(v for _, v in ranked)
    top = ranked[:_TOP_N]
    top_exporters = [{
        "rank": i + 1,
        "reporter": country,
        "reporter_type": "country",
        "trade_value_usd": round(value, 2),
        "trade_value_1000_usd": round(value / 1000.0, 2),
        "share_of_total_pct": round(value / total * 100, 2) if total else 0,
    } for i, (country, value) in enumerate(top)]

    top1_share = top_exporters[0]["share_of_total_pct"]
    is_partial = chosen in node["partial_years"]

    notes = []
    if is_partial:
        notes.append(f"{chosen} is partial-year data (single month); use shares, not totals.")
    elif chosen == 2025:
        notes.append("2025 import totals run well above prior years; verify magnitudes before relying on them.")

    source = f"USITC Imports {chosen}" + (" (partial)" if is_partial else "")

    return {
        "status": "success",
        "hs6_code": hs6,
        "year": chosen,
        "trade_flow": "import",
        "value_measure": "Customs Value",
        "source": source,
        "share_basis": "total_imports",
        "top_exporters": top_exporters,
        "concentration_top1_pct": top1_share,
        "concentration_risk_flag": _concentration_flag(top1_share),
        "country_count": len(ranked),
        "total_value_usd": round(total, 2),
        "is_partial_year": is_partial,
        "data_quality_note": " ".join(notes) if notes else None,
    }


def get_trade_profile(hs6_code: str) -> dict:
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
        "imports": get_origin_concentration(hs6),
        "exports": None,
    }

    export_map = node.get("export") or {}
    chosen = _pick_year(export_map, None)
    if chosen is not None:
        dests = export_map[chosen]
        ranked = sorted(((c, v) for c, v in dests.items() if v > 0),
                        key=lambda kv: kv[1], reverse=True)[:_TOP_N]
        total = sum(v for _, v in ranked)
        profile["exports"] = {
            "year": chosen,
            "value_measure": "FAS Value",
            "top_destinations": [{
                "rank": i + 1,
                "country": c,
                "trade_value_usd": round(v, 2),
                "share_of_total_pct": round(v / total * 100, 2) if total else 0,
            } for i, (c, v) in enumerate(ranked)],
            "is_partial_year": chosen in node["partial_years"],
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
