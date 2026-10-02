"""Shared fixtures for the geographic-risk tests."""

import openpyxl
import pytest

from app.modules.supply_chain import provider


def _write_usitc_workbook(
    path, rows, years=("2024", "2025"), partial_col="January_to_january_year_2026"
):
    """Write a minimal USITC DataWeb-style export (Query Results layout).

    ``rows``: ``[(country, hts_code, [value per year column...]), ...]``.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Query Results"
    ws.append(["Imports For Consumption|Annual Data"])
    ws.append(["Data Row Count", len(rows)])
    header = ["Data Type", "Country", "HTS Number", "Description", *years]
    if partial_col:
        header.append(partial_col)
    ws.append(header)
    for country, hts, values in rows:
        ws.append(["Customs Value", country, hts, "TEST CHEMICAL", *values])
    wb.create_sheet("Query Parameters")
    wb.save(path)


@pytest.fixture
def write_usitc_workbook():
    return _write_usitc_workbook


@pytest.fixture
def usitc_folder(tmp_path, monkeypatch):
    """Point the supply-chain provider at an empty temp folder."""
    folder = tmp_path / "supply_chain"
    folder.mkdir()
    monkeypatch.setattr(provider, "SUPPLY_CHAIN_DIR", folder)
    provider._CACHE.update(signature=None, data=None)
    yield folder
    provider._CACHE.update(signature=None, data=None)
