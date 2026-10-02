"""Provenance and data-quality of geographic-risk results (USITC, WITS fallback, YTD)."""

import pandas as pd
import pytest

from app.modules.risk import engine
from app.modules.risk.concentration import build_geographic_profile
from app.modules.risk.engine import ReagentRiskInput, run_risk_assessment
from app.modules.supply_chain import provider
from app.modules.trade_data import db as trade_db


HS6 = "291100"


def resolution(hs6, method):
    """A resolve_hs6()-style mapping record for profile-level tests."""
    exact = method in ("cas", "inchikey", "user_input")
    return {
        "hs6": hs6,
        "match_method": method,
        "match_label": method,
        "source": "test",
        "exact": exact,
        "mapping_quality": "HIGH" if exact else "MEDIUM",
        "broad_category": None,
        "note": None,
    }


@pytest.fixture
def cas_mapping(monkeypatch):
    df = pd.DataFrame(
        {"Reagent_CAS": ["TEST-CAS-1"], "HS_Code": ["2911.00"], "Primary_Origin": [""]}
    )
    monkeypatch.setattr(engine, "load_reagent_mapping", lambda: df)


def china_dominant_workbook(folder, write_usitc_workbook):
    write_usitc_workbook(
        folder / "imports.xlsx",
        [
            ("China", HS6, [80, 95, 0]),
            ("South Korea", HS6, [10, 3, 0]),
            ("Germany", HS6, [10, 2, 9]),
        ],
    )


def test_usitc_result_carries_source_year_hs6_and_basis(usitc_folder, write_usitc_workbook):
    china_dominant_workbook(usitc_folder, write_usitc_workbook)
    sc = engine.get_supply_chain_concentration(HS6)
    profile = build_geographic_profile(sc, resolution(HS6, "cas"))
    prov = profile["provenance"]

    assert prov["source"] == "USITC DataWeb"
    assert prov["source_url"] == "https://dataweb.usitc.gov/"
    assert prov["hs6_code"] == HS6
    assert prov["year"] == 2025
    assert prov["period_type"] == "full_year"
    assert prov["is_partial_year"] is False
    assert prov["ranking_basis"] == "U.S. import customs value (USD)"
    assert prov["coverage"] == "all_reported_countries"
    assert prov["country_count"] == 3
    assert prov["hs6_source"] == "cas"
    assert prov["hs6_mapping"]["mapping_quality"] == "HIGH"
    assert prov["hs6_mapping"]["exact"] is True
    assert "not global supply" in prov["scope_note"]
    assert prov["source_files"] == ["imports.xlsx"]

    conc = profile["concentration"]
    assert conc["tier"] == "HIGH"
    assert (conc["top_supplier_country"], conc["top_supplier_share"]) == ("China", 95.0)
    assert (conc["second_supplier_country"], conc["second_supplier_share"]) == ("South Korea", 3.0)
    assert conc["supplier_countries_available"] == 3
    assert profile["data_quality"]["level"] == "HIGH"


def test_wits_fallback_clearly_says_wits(monkeypatch):
    monkeypatch.setattr(
        provider, "get_origin_concentration", lambda *a, **k: {"status": "no_trade_data"}
    )
    fixture_db = {
        "products": {
            "282580": {
                "product_description": "Antimony oxides",
                "records": {
                    "2024_export_world": {
                        "year": 2024,
                        "trade_flow": "Export",
                        "partner": "World",
                        "top_n_actual": 4,
                        "top_exporters": [
                            {"rank": 1, "reporter": "China", "reporter_type": "country", "share_of_top5_pct": 48.0},
                            {"rank": 2, "reporter": "European Union", "reporter_type": "aggregate", "share_of_top5_pct": 20.0},
                            {"rank": 3, "reporter": "Belgium", "reporter_type": "country", "share_of_top5_pct": 17.0},
                            {"rank": 4, "reporter": "France", "reporter_type": "country", "share_of_top5_pct": 15.0},
                        ],
                        "warnings": [],
                        "source": {"filename": "WITS-By-HS6Product (21).xlsx"},
                    }
                },
            }
        }
    }
    monkeypatch.setattr(trade_db, "load", lambda *a, **k: fixture_db)

    sc = engine.get_supply_chain_concentration("282580")
    profile = build_geographic_profile(sc, resolution("282580", "compound_registry"))
    prov, conc = profile["provenance"], profile["concentration"]

    assert prov["source"] == "WITS"
    assert "WITS" in prov["source_label"]
    assert prov["source_url"] == "https://wits.worldbank.org/"
    assert prov["year"] == 2024
    assert prov["trade_flow"] == "export"
    assert prov["coverage"] == "listed_only"
    assert "quantity" in prov["ranking_basis"].lower()
    assert "not a world total" in prov["share_basis_label"]
    # The "European Union" grouping is never the top supplier country.
    assert conc["top_supplier_country"] == "China"
    assert conc["second_supplier_country"] == "Belgium"
    assert any("European Union" in note for note in prov["notes"])
    # Listed-only shares cap data quality at MEDIUM.
    assert profile["data_quality"]["level"] == "MEDIUM"


def test_partial_year_data_is_clearly_marked(usitc_folder, write_usitc_workbook):
    write_usitc_workbook(
        usitc_folder / "imports.xlsx",
        [("Mexico", HS6, [0, 0, 40]), ("Canada", HS6, [0, 0, 60])],
    )
    sc = engine.get_supply_chain_concentration(HS6)
    profile = build_geographic_profile(sc, resolution(HS6, "cas"))
    prov = profile["provenance"]
    assert prov["is_partial_year"] is True
    assert prov["period_type"] == "partial_year"
    assert "YTD" in prov["period_label"]
    assert prov["year_selection_reason"] == "no_complete_year_available"
    assert profile["data_quality"]["level"] == "LOW"
    assert any("Partial-year" in r for r in profile["data_quality"]["reasons"])


def test_no_hs6_mapping_is_unknown_and_no_data():
    profile = build_geographic_profile({"status": "no_hs6_mapping"}, None)
    assert profile["concentration"]["tier"] == "UNKNOWN"
    assert profile["data_quality"]["level"] == "NO_DATA"
    assert profile["alternatives"]["alternative_sourcing_basis"] == "no_information"


# -----------------------------------------------------------------
# Through the full risk assessment
# -----------------------------------------------------------------


def test_assessment_separates_geography_from_concentration(
    usitc_folder, isolated_db, cas_mapping, write_usitc_workbook
):
    china_dominant_workbook(usitc_folder, write_usitc_workbook)
    result = run_risk_assessment(
        [
            ReagentRiskInput(
                name="Test aldehyde", cas="TEST-CAS-1", cost=100, routes={"A": {"cost": 100}}
            )
        ]
    )
    r = result["reagents"][0]

    geo = r["geographic_exposure"]
    assert geo["dominant_origin"] == "China"
    assert geo["origin_source"] == "trade_data_top_supplier"
    assert geo["stability_known"] is True
    # Country conditions (100 - stability) vs concentration (top share) are separate.
    assert r["breakdown"]["geographic"] == round(100 - geo["stability_score"], 1)
    assert r["breakdown"]["concentration"] == 95.0
    # The composite index does not use the concentration share.
    used = r["risk_index_components"]["components"]
    assert "concentration" not in used
    assert used["geographic"]["score"] == r["breakdown"]["geographic"]

    assert r["concentration"]["tier"] == "HIGH"
    assert r["provenance"]["source"] == "USITC DataWeb"
    assert r["provenance"]["hs6_code"] == HS6
    assert r["alternatives"]["substitutability_source"] == "default"
    assert {s["country"] for s in r["supplier_shares"]} == {"China", "South Korea", "Germany"}

    route = result["summary"]["route_summary"][0]
    assert route["route"] == "A"
    assert route["high_concentration_reagents"] == ["Test aldehyde"]
    assert route["largest_dominant_share"]["top_supplier_country"] == "China"


def test_user_entered_origin_wins_and_concentration_still_reported(
    usitc_folder, isolated_db, cas_mapping, write_usitc_workbook
):
    china_dominant_workbook(usitc_folder, write_usitc_workbook)
    r = run_risk_assessment(
        [ReagentRiskInput(name="Test aldehyde", cas="TEST-CAS-1", origin="Germany", substitutability=8)]
    )["reagents"][0]
    assert r["primary_origin"] == "Germany"
    assert r["geographic_exposure"]["origin_source"] == "user_input"
    assert r["concentration"]["top_supplier_country"] == "China"
    assert r["alternatives"]["substitutability_source"] == "user_input"
    assert r["breakdown"]["economic"] == 80.0


def test_unknown_concentration_is_not_reported_as_zero(isolated_db, monkeypatch):
    monkeypatch.setattr(engine, "load_reagent_mapping", lambda: pd.DataFrame(
        {"Reagent_CAS": [], "HS_Code": [], "Primary_Origin": []}
    ))
    r = run_risk_assessment([ReagentRiskInput(name="Mystery Molecule XYZ")])["reagents"][0]
    assert r["concentration"]["tier"] == "UNKNOWN"
    assert r["breakdown"]["concentration"] is None
    assert r["data_quality"]["level"] == "NO_DATA"
