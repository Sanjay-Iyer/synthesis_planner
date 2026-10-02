"""
Import World Bank WGI Political Stability scores into country_stability.csv.

Source: World Bank Worldwide Governance Indicators (WGI)
        https://www.worldbank.org/en/publication/worldwide-governance-indicators
Indicator: GOV_WGI_PV.SC — "Political Stability and Absence of
           Violence/Terrorism: governance score (0-100)", with its 90%
           confidence bounds (GOV_WGI_PV.SC_LB / GOV_WGI_PV.SC_UB).

The score is used as-is (it is already on a 0-100 scale). For each economy the
latest year with a non-missing score is kept. WGI is a governance perception
indicator, not a probability of supply disruption.

Usage (from the repository root):
    python scripts/import_wgi.py                    # World Bank API (needs internet)
    python scripts/import_wgi.py --input FILE.csv   # DataBank CSV export (offline)
    python scripts/import_wgi.py --dry-run          # print, do not write

Manual download (no internet on the target machine):
  1. https://databank.worldbank.org/source/worldwide-governance-indicators
  2. Country: select all economies. Series: "Political Stability ... Governance
     score (0-100)" plus its lower and upper bounds. Time: recent years.
  3. Download as CSV, then run with --input <file>.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.modules.risk.risk_config import canonical_country  # noqa: E402

DATA_DIR = PROJECT_ROOT / "app" / "modules" / "risk" / "data"
OUT_CSV = DATA_DIR / "country_stability.csv"
OUT_META = DATA_DIR / "country_stability_meta.json"

API = "https://api.worldbank.org/v2"
SOURCE_ID = 3  # Worldwide Governance Indicators
SCORE = "GOV_WGI_PV.SC"
LOWER = "GOV_WGI_PV.SC_LB"
UPPER = "GOV_WGI_PV.SC_UB"
SERIES = (SCORE, LOWER, UPPER)
INDICATOR_NAME = (
    "Political Stability and Absence of Violence/Terrorism - governance score (0-100)"
)


def _get_json(url: str):
    with urllib.request.urlopen(url, timeout=90) as resp:
        return json.load(resp)


def fetch_api() -> tuple[dict, dict]:
    """Return ({iso3: {name, series: {code: {year: value}}}}, api_meta)."""
    economies: dict = {}
    meta = {}
    for code in SERIES:
        # The API rejects ranges past the current year.
        url = (
            f"{API}/country/all/indicator/{code}?source={SOURCE_ID}"
            f"&format=json&per_page=20000&date=2000:{datetime.now(timezone.utc).year}"
        )
        page_meta, rows = _get_json(url)
        if code == SCORE:
            meta = {"api_url": url, "wgi_last_updated": page_meta.get("lastupdated")}
        for row in rows or []:
            if row.get("value") is None:
                continue
            iso = row.get("countryiso3code") or row["country"]["id"]
            entry = economies.setdefault(iso, {"name": row["country"]["value"], "series": {}})
            entry["series"].setdefault(code, {})[int(row["date"])] = float(row["value"])

    # Drop regional/income aggregates if the source ever includes them.
    countries = _get_json(f"{API}/country?format=json&per_page=500")[1]
    aggregates = {c["id"] for c in countries if c["region"]["value"] == "Aggregates"}
    aggregates |= {c["iso2Code"] for c in countries if c["region"]["value"] == "Aggregates"}
    return {k: v for k, v in economies.items() if k not in aggregates}, meta


def read_databank_csv(path: Path) -> tuple[dict, dict]:
    """Parse a DataBank CSV export (wide format, '..' for missing values)."""
    economies: dict = {}
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        year_cols = {
            col: int(m.group(1))
            for col in reader.fieldnames or []
            if (m := re.match(r"\s*(\d{4})", col))
        }
        for row in reader:
            code = (row.get("Series Code") or "").strip()
            if not code.endswith(("PV.SC", "PV.SC_LB", "PV.SC_UB")):
                continue
            series = SCORE if code.endswith("PV.SC") else LOWER if code.endswith("_LB") else UPPER
            iso = (row.get("Country Code") or "").strip()
            name = (row.get("Country Name") or "").strip()
            if not iso or not name:
                continue
            for col, year in year_cols.items():
                raw = (row.get(col) or "").strip()
                if raw in ("", ".."):
                    continue
                try:
                    value = float(raw)
                except ValueError:
                    continue
                entry = economies.setdefault(iso, {"name": name, "series": {}})
                entry["series"].setdefault(series, {})[year] = value
    return economies, {"input_file": str(path)}


def build_rows(economies: dict) -> list[dict]:
    """Latest non-missing score per economy, with bounds from the same year."""
    rows = []
    for iso, entry in economies.items():
        scores = entry["series"].get(SCORE) or {}
        if not scores:
            continue
        year = max(scores)
        rows.append(
            {
                "Country": canonical_country(entry["name"]),
                "Stability_Score": round(scores[year], 2),
                "Score_Lower_90": _round((entry["series"].get(LOWER) or {}).get(year)),
                "Score_Upper_90": _round((entry["series"].get(UPPER) or {}).get(year)),
                "Year": year,
                "ISO3": iso,
                "WGI_Country_Name": entry["name"],
                "Indicator": SCORE,
            }
        )
    rows.sort(key=lambda r: r["Country"])
    return rows


def _round(value):
    return round(value, 2) if value is not None else ""


def write_outputs(rows: list[dict], source_meta: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    years = sorted({r["Year"] for r in rows})
    meta = {
        "source": "World Bank Worldwide Governance Indicators (WGI)",
        "source_url": "https://www.worldbank.org/en/publication/worldwide-governance-indicators",
        "indicator": SCORE,
        "indicator_name": INDICATOR_NAME,
        "bounds": [LOWER, UPPER],
        "scale": "0-100, higher = better governance score on this dimension",
        "method": "Latest non-missing year per economy; score used without rescaling.",
        "years": years,
        "economies": len(rows),
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "interpretation": (
            "A governance perception indicator used as country-conditions context. "
            "It is not a probability of supply disruption."
        ),
        **source_meta,
    }
    with open(OUT_META, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--input", type=Path, help="DataBank CSV export to import offline")
    parser.add_argument("--dry-run", action="store_true", help="Print a summary, write nothing")
    args = parser.parse_args(argv)

    if args.input:
        economies, source_meta = read_databank_csv(args.input)
    else:
        economies, source_meta = fetch_api()
    rows = build_rows(economies)
    if not rows:
        print("No WGI scores found; nothing written.", file=sys.stderr)
        return 1

    years = sorted({r["Year"] for r in rows})
    print(f"{len(rows)} economies, years {years}")
    if args.dry_run:
        for r in rows[:10]:
            print(r)
        return 0
    write_outputs(rows, source_meta)
    print(f"Wrote {OUT_CSV.relative_to(PROJECT_ROOT)} and {OUT_META.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
