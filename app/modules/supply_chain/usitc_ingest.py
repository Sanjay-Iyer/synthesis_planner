"""
Parser for USITC DataWeb (dataweb.usitc.gov) Excel exports.

The export workbook has two sheets:
  - "Query Parameters": metadata about how the query was built (ignored here).
  - "Query Results": the data, laid out as
        row 0: a title, e.g. "Imports For Consumption|Annual Data"
        row 1: "Data Row Count" | <n>
        row 2: column headers
        row 3+: one row per Country + HTS-code combination

Columns (11): Data Type, Country, HTS Number, Description, then one column per
full calendar year (2020..2025), then a partial-year column such as
"January_to_january_year_2026" covering a single month.

This module is intentionally tolerant: it locates the header row by scanning
for the "Data Type" cell and detects year columns by pattern, so small layout
shifts (extra blank rows, a moved partial-year column) do not break parsing.
"""
from __future__ import annotations

import re
import warnings
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

# USITC value cells can be large; openpyxl warns about missing default styles
# on these particular workbooks. The warning is harmless and noisy.
warnings.filterwarnings("ignore", message="Workbook contains no default style")

RESULTS_SHEET_CANDIDATES = ("query results",)
HEADER_FIRST_CELL = "data type"
REQUIRED_COLUMNS = ("Data Type", "Country", "HTS Number", "Description")


def normalize_hs6(value) -> Optional[str]:
    """Reduce an HTS/HS code to a 6-digit HS6 key (digits only, padded)."""
    if value is None:
        return None
    digits = re.sub(r"\D", "", str(value))
    if not digits:
        return None
    if len(digits) >= 6:
        return digits[:6]
    return digits.zfill(6)


def _to_float(value) -> float:
    """Parse a USITC value cell into a float; blanks / non-numeric -> 0.0."""
    if value is None:
        return 0.0
    try:
        f = float(str(value).replace(",", "").strip())
    except (ValueError, AttributeError):
        return 0.0
    if pd.isna(f):
        return 0.0
    return f


def _infer_trade_flow(title: str, data_type: str) -> str:
    """Classify the file as 'import', 'export', or 'unknown'."""
    t = (title or "").lower()
    d = (data_type or "").lower()
    if "import" in t or "customs value" in d:
        return "import"
    if "export" in t or "fas value" in d:
        return "export"
    return "unknown"


def _find_results_sheet(xl: pd.ExcelFile) -> Optional[str]:
    for sheet in xl.sheet_names:
        if sheet.strip().lower() in RESULTS_SHEET_CANDIDATES:
            return sheet
    return None


def _detect_header_row(path: str, sheet: str, max_scan: int = 12):
    """Return (header_row_index, title) by scanning for the 'Data Type' cell."""
    raw = pd.read_excel(path, sheet_name=sheet, header=None, nrows=max_scan)
    title = ""
    if len(raw) > 0:
        title = str(raw.iloc[0, 0]).strip()
        if title.lower() == "nan":
            title = ""
    for i in range(len(raw)):
        first = str(raw.iloc[i, 0]).strip().lower()
        if first == HEADER_FIRST_CELL:
            return i, title
    return None, title


def _classify_year_columns(columns: List[str]):
    """Split header columns into {full_year: col} and {partial_year: col}."""
    full_years: Dict[int, str] = {}
    partial_years: Dict[int, str] = {}
    for col in columns:
        cs = str(col).strip()
        # A bare 4-digit year (sometimes rendered "2024.0" by the reader).
        m = re.fullmatch(r"(\d{4})(?:\.0)?", cs)
        if m:
            full_years[int(m.group(1))] = col
            continue
        # A partial-year column, e.g. "January_to_january_year_2026".
        if "january" in cs.lower():
            ym = re.search(r"(\d{4})", cs)
            if ym:
                partial_years[int(ym.group(1))] = col
    return full_years, partial_years


def parse_usitc_file(path: str) -> dict:
    """Parse one USITC DataWeb export into a normalized record set.

    Returns a dict::

        {
            "trade_flow": "import" | "export" | "unknown",
            "value_measure": "Customs Value" | "FAS Value" | ...,
            "title": str,
            "full_years": [2020, ...],
            "partial_years": [2026, ...],
            "records": [
                {"country": str, "hts6": str, "description": str,
                 "values": {year_int: float, ...}},
                ...
            ],
        }

    Raises ValueError if the file is not a recognizable USITC export.
    """
    xl = pd.ExcelFile(path)
    sheet = _find_results_sheet(xl)
    if sheet is None:
        raise ValueError("No 'Query Results' sheet found (not a USITC DataWeb export?)")

    header_idx, title = _detect_header_row(path, sheet)
    if header_idx is None:
        raise ValueError("Could not locate the 'Data Type' header row in 'Query Results'")

    # Read everything as strings so HTS codes and large values are not coerced
    # into floats with precision loss; convert value columns explicitly below.
    df = pd.read_excel(path, sheet_name=sheet, header=header_idx, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]

    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            raise ValueError(f"Required column '{col}' is missing from 'Query Results'")

    full_years, partial_years = _classify_year_columns(list(df.columns))
    if not full_years and not partial_years:
        raise ValueError("No year columns detected in 'Query Results'")

    data_type = ""
    dt_series = df["Data Type"].dropna()
    if len(dt_series):
        data_type = str(dt_series.iloc[0]).strip()

    trade_flow = _infer_trade_flow(title, data_type)
    year_cols = {**full_years, **partial_years}

    records: List[dict] = []
    for _, row in df.iterrows():
        hts6 = normalize_hs6(row.get("HTS Number"))
        country = str(row.get("Country", "")).strip()
        if not hts6 or not country or country.lower() == "nan":
            continue
        description = str(row.get("Description", "")).strip()
        if description.lower() == "nan":
            description = ""

        values = {}
        for year, col in year_cols.items():
            val = _to_float(row.get(col))
            if val:
                values[year] = val
        if not values:
            continue

        records.append({
            "country": country,
            "hts6": hts6,
            "description": description,
            "values": values,
        })

    return {
        "trade_flow": trade_flow,
        "value_measure": data_type,
        "title": title,
        "full_years": sorted(full_years),
        "partial_years": sorted(partial_years),
        "records": records,
    }
